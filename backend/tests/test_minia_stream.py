"""TAXO-UX-02 : Minia annonce ses etapes reelles et diffuse sa reponse pendant qu'elle l'ecrit."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.minia.domain.answer import AnswerStream
from app.minia.domain.errors import UNAVAILABLE, MiniaError
from app.minia.infrastructure.ollama import OllamaModel

REPLY = {'cited': ['F1'], 'answer': 'Le projet adopterait « React ».\nC’est une hypothèse.', 'unknown': ''}


class StreamingModel:
    provider, model_name = 'fake', 'fake-stream'

    def __init__(self, reply=REPLY, fail_after=None):
        self.raw, self.fail_after, self.calls = json.dumps(reply, ensure_ascii=False), fail_after, 0

    def complete(self, system, user):
        return self.raw

    def stream(self, system, user):
        self.calls += 1
        for index in range(0, len(self.raw), 7):
            if self.fail_after is not None and index >= self.fail_after:
                raise MiniaError(UNAVAILABLE, 'Ollama a répondu 500.')
            yield self.raw[index:index + 7]


class BlockModel(StreamingModel):
    stream = None


def events_of(response):
    parsed = []
    for block in response.text.strip().split('\n\n'):
        lines = dict(line.split(': ', 1) for line in block.splitlines())
        parsed.append((lines['event'], json.loads(lines['data'])))
    return parsed


@pytest.fixture(name='repo')
def repo_fixture(make_repo, git):
    repo = make_repo({'README.md': 'Demo\n'}, 'stream')
    (repo / 'package.json').write_text('{"dependencies":{"react":"19"}}')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'ajoute React')
    return repo, git(repo, 'rev-parse', 'HEAD')


def client_for(repo, tmp_path, model):
    app = create_app(f'sqlite:///{tmp_path / "stream.db"}', [repo], minia=model)
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    project = client.post('/api/projects', json={'name': 'Flux', 'path': str(repo)}).json()
    return client, f'/api/projects/{project["id"]}'


def test_minia_announces_real_steps_then_streams_then_validates(repo, tmp_path):
    path, sha = repo
    model = StreamingModel()
    client, base = client_for(path, tmp_path, model)
    response = client.post(f'{base}/history/commits/{sha}/ask/stream', json={'question': 'Que change ce commit ?'})
    assert response.headers['content-type'].startswith('text/event-stream')
    events = events_of(response)
    stages = [(data['stage'], data['state']) for event_type, data in events if event_type == 'minia.stage']
    assert stages == [('facts', 'running'), ('facts', 'done'), ('context', 'done'),
                      ('interpretation', 'running'), ('interpretation', 'done')]
    interpreting = next(data for event_type, data in events if event_type == 'minia.stage'
                        and data['stage'] == 'interpretation')
    assert interpreting['label'] == f"Minia interprète {interpreting['count']} faits Taxo" and interpreting['count'] > 1
    streamed = ''.join(data['text'] for event_type, data in events if event_type == 'minia.delta')
    assert streamed == REPLY['answer'], 'le texte provisoire est celui de la reponse'
    assert len([1 for event_type, _ in events if event_type == 'minia.delta']) > 1, 'au fil de l eau'
    final_type, final = events[-1]
    assert final_type == 'minia.completed' and final['answer'] == REPLY['answer']
    assert [fact['ref'] for fact in final['facts']] == ['F1'], 'les citations sont validees a la fin'
    synchronous = client.post(f'{base}/history/commits/{sha}/ask', json={'question': 'Que change ce commit ?'}).json()
    assert synchronous['answer'] == final['answer'] and synchronous['facts'] == final['facts']


def test_a_provider_without_streaming_still_shows_its_steps(repo, tmp_path):
    path, sha = repo
    client, base = client_for(path, tmp_path, BlockModel())
    events = events_of(client.post(f'{base}/history/commits/{sha}/ask/stream', json={'question': 'Pourquoi ?'}))
    assert 'minia.delta' not in {event_type for event_type, _ in events}
    assert events[-1][0] == 'minia.completed' and events[-1][1]['answer'] == REPLY['answer']


def test_a_model_failure_ends_the_stream_with_its_reason(repo, tmp_path):
    path, sha = repo
    client, base = client_for(path, tmp_path, StreamingModel(fail_after=14))
    events = events_of(client.post(f'{base}/history/commits/{sha}/ask/stream', json={'question': 'Pourquoi ?'}))
    assert events[-1] == ('minia.failed', {'code': UNAVAILABLE, 'message': 'Ollama a répondu 500.'})


def test_invalid_requests_are_refused_before_the_stream_opens(repo, tmp_path):
    path, sha = repo
    client, base = client_for(path, tmp_path, StreamingModel())
    assert client.post(f'{base}/history/commits/{sha}/ask/stream', json={'question': ' '}).status_code == 422
    assert client.post(f'{base}/history/commits/{"0" * 40}/ask/stream', json={'question': 'x'}).status_code == 404
    assert client.post(f'{base}/ask/stream', json={'question': '3 derniers commits'}).status_code == 409


def test_a_project_question_streams_only_the_selected_facts(repo, tmp_path):
    path, sha = repo
    model = StreamingModel({'cited': ['F1'], 'answer': 'Un commit ajouterait React.', 'unknown': ''})
    client, base = client_for(path, tmp_path, model)
    client.post(f'{base}/scans')
    events = events_of(client.post(f'{base}/ask/stream', json={'question': 'Résume le dernier commit'}))
    facts = next(data for event_type, data in events if event_type == 'minia.stage' and data['stage'] == 'facts')
    assert facts['state'] == 'done' and facts['count'] > 0
    assert ''.join(data['text'] for event_type, data in events if event_type == 'minia.delta') == 'Un commit ajouterait React.'
    assert events[-1][1]['commits'][0]['sha'] == sha
    vague = events_of(client.post(f'{base}/ask/stream', json={'question': 'Analyse le projet'}))
    assert vague[-1][1]['status'] == 'NEEDS_SELECTION' and model.calls == 1


def test_the_answer_text_is_decoded_across_chunk_boundaries():
    stream = AnswerStream()
    raw = '{"cited":[],"answer":"a\\"b\\\\c\\nd\\u00e9\\u12G4e/f","unknown":"x"}'
    text = ''.join(stream.feed(char) for char in raw)
    assert text == 'a"b\\c\ndée/f'
    assert stream.feed('"answer":"encore"') == '', 'rien apres la fin du champ'
    assert AnswerStream().feed('{"cited":[]') == ''


def test_the_ollama_adapter_streams_ndjson():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        lines = [{'message': {'content': '{"answer":'}}, {}, {'message': {'content': '"ok"}'}}, {'done': True}]
        body = '\n'.join(json.dumps(line) for line in lines) + '\n\n'
        return httpx.Response(200, content=body.encode())

    model = OllamaModel('m', 'http://ollama.test', transport=httpx.MockTransport(handler))
    assert list(model.stream('s', 'u')) == ['{"answer":', '"ok"}']
    assert seen[0]['stream'] is True


@pytest.mark.parametrize('handler, expected', [
    (lambda request: httpx.Response(404), 'ollama pull m'),
    (lambda request: httpx.Response(200, content=b'pas du json\n'), 'illisible'),
])
def test_ollama_streaming_failures_become_minia_unavailable(handler, expected):
    model = OllamaModel('m', 'http://ollama.test', transport=httpx.MockTransport(handler))
    with pytest.raises(MiniaError) as error:
        list(model.stream('s', 'u'))
    assert error.value.code == UNAVAILABLE and expected in str(error.value)


def test_an_unreachable_ollama_is_reported_while_streaming():
    def handler(request):
        raise httpx.ConnectError('refused', request=request)

    with pytest.raises(MiniaError, match='ollama serve'):
        list(OllamaModel('m', 'http://ollama.test', transport=httpx.MockTransport(handler)).stream('s', 'u'))


def test_escaped_emoji_and_lone_surrogates_never_break_the_stream(repo, tmp_path):
    raw = '{"cited":[],"answer":"ok \\ud83d\\ude00 \\udc00 \\ud800x","unknown":""}'
    stream = AnswerStream()
    assert ''.join(stream.feed(char) for char in raw) == 'ok 😀 � �x'

    class EscapingModel(StreamingModel):
        def __init__(self):
            super().__init__()
            self.raw = raw

    path, sha = repo
    client, base = client_for(path, tmp_path, EscapingModel())
    events = events_of(client.post(f'{base}/history/commits/{sha}/ask/stream', json={'question': 'Pourquoi ?'}))
    streamed = ''.join(data['text'] for event_type, data in events if event_type == 'minia.delta')
    assert streamed == 'ok 😀 � �x' and events[-1][0] == 'minia.completed'
