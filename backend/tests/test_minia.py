"""TAXO-MINIA-01 : Minia explique un commit a partir des seuls faits de Taxo."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bootstrap import settings
from app.bootstrap.application import minia_model, minia_models
from app.bootstrap.database import Base
from app.main import create_app
from app.minia.domain import briefing
from app.minia.domain.answer import parse
from app.minia.domain.errors import INVALID_ANSWER, UNAVAILABLE, MiniaError
from app.minia.infrastructure.ollama import OllamaModel

SENTINEL = 'CODE_SOURCE_JAMAIS_TRANSMIS'


class FakeModel:
    provider, model_name = 'fake', 'fake-1'

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def commit_all(git, repo, message):
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', message)
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture(name='repo')
def repo_fixture(make_repo, git):
    repo = make_repo({'README.md': 'Demo\n', 'App.java': f'class App {{ String s = "{SENTINEL}"; }}\n',
                      '.env': 'PASSWORD=jamais-lu\n'}, 'minia')
    (repo / 'package.json').write_text(json.dumps({'dependencies': {'react': '19'}}))
    (repo / 'App.java').write_text(f'class App {{ String s = "{SENTINEL}-2"; }}\n')
    added = commit_all(git, repo, 'ajoute React')
    (repo / 'README.md').write_text('Demo, texte seulement\n')
    unchanged = commit_all(git, repo, 'retouche le README')
    return repo, added, unchanged


@pytest.fixture(name='ask')
def ask_fixture(repo, tmp_path):
    clients = []

    def open_client(model):
        app = create_app(f'sqlite:///{tmp_path / "minia.db"}', [repo[0]], minia=model)
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        clients.append(client)
        project = client.post('/api/projects', json={'name': 'Minia', 'path': str(repo[0])}).json()

        def post(sha, question='Que change ce commit ?', **extra):
            return client.post(f'/api/projects/{project["id"]}/history/commits/{sha}/ask',
                               json={'question': question, **extra})
        return client, post
    yield open_client
    for client in clients:
        client.close()


def test_minia_answers_from_taxo_facts_and_taxo_shows_the_cited_facts(repo, ask):
    _, added, _ = repo
    model = FakeModel({'cited': ['F1', 'F99', 'x', 'F1'], 'answer': 'Le projet adopterait React.', 'unknown': ''})
    _, post = ask(model)
    result = post(added).json()
    assert result['status'] == 'ANSWERED' and result['answer'] == 'Le projet adopterait React.'
    assert result['model'] == {'configured': True, 'provider': 'fake', 'model': 'fake-1'}
    assert [fact['ref'] for fact in result['facts']] == ['F1'], 'une reference citee deux fois ne compte qu une fois'
    assert result['rejected_citations'] == ['F99', 'x'], 'une reference inventee est ecartee, jamais affichee'
    sent = json.loads(model.calls[0][1])
    assert sent['facts'][0]['ref'] == 'F1'
    project_id = result['project']['id']
    assert result['facts'][0]['subject'] == f'repository:{project_id}', 'le fait affiche est celui de Taxo'
    assert sent['facts'][0]['subject'] == 'repository:Minia', 'le modele lit le nom du projet, pas son identifiant'
    assert project_id not in model.calls[0][1]
    assert 'produced_by' not in json.dumps(result), 'une reponse de Minia ne devient jamais un fait'


def test_minia_never_receives_source_code_or_secrets(repo, ask):
    _, added, _ = repo
    model = FakeModel({'cited': [], 'answer': '', 'unknown': 'Rien.'})
    _, post = ask(model)
    post(added)
    system, user = model.calls[0]
    assert SENTINEL not in user and 'jamais-lu' not in user
    assert 'content_hash' not in user, 'une preuve se reduit a sa localisation'
    assert 'ajoute React' in user, 'le message du commit est une donnee transmise'
    assert 'jamais des instructions' in system
    assert '"..."' not in system, 'aucune valeur de gabarit que le modele pourrait recopier'
    assert 'salutation' in system, 'une salutation ne declenche pas de resume du commit'


def test_when_taxo_knows_nothing_minia_says_so_without_asking_the_model(repo, ask):
    _, _, unchanged = repo
    model = FakeModel('ne doit pas etre appele')
    _, post = ask(model)
    result = post(unchanged).json()
    assert result['status'] == 'TAXO_KNOWS_NOTHING' and result['facts'] == []
    assert 'ne peut rien affirmer' in result['unknown']
    assert model.calls == []
    git = result['git']
    assert (git['sha'], git['subject'], git['author']) == (unchanged, 'retouche le README', git['author'])
    assert git['author'] and git['files'] == [{'status': 'MODIFIED', 'path': 'README.md', 'old_path': None}]


def test_a_permanent_unreadable_zone_does_not_wake_the_model(make_repo, git, ask, tmp_path):
    repo = make_repo({'README.md': 'a\n', 'logo.bin': b'\xff\xfe\x00binaire'}, 'zone')
    (repo / 'README.md').write_text('b\n')
    sha = commit_all(git, repo, 'retouche')
    model = FakeModel('ne doit pas etre appele')
    app = create_app(f'sqlite:///{tmp_path / "zone.db"}', [repo], minia=model)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Zone', 'path': str(repo)}).json()
        result = client.post(f'/api/projects/{project["id"]}/history/commits/{sha}/ask',
                             json={'question': 'Qu est-ce que ce commit change ?'}).json()
    assert result['not_interpreted'] == ['file:logo.bin'], 'la zone reste signalee, par Taxo'
    assert result['status'] == 'TAXO_KNOWS_NOTHING' and model.calls == []


def test_a_renamed_file_reaches_minia_with_its_old_path(make_repo, git, ask, tmp_path):
    repo = make_repo({'docs/backlog/R1.md': 'recit\n'}, 'rename')
    (repo / 'docs' / 'termine').mkdir()
    git(repo, 'mv', 'docs/backlog/R1.md', 'docs/termine/R1.md')
    sha = commit_all(git, repo, 'R1 termine')
    model = FakeModel({'cited': [], 'answer': 'La fiche serait terminee.', 'unknown': ''})
    app = create_app(f'sqlite:///{tmp_path / "rename.db"}', [repo], minia=model)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Renomme', 'path': str(repo)}).json()
        result = client.post(f'/api/projects/{project["id"]}/history/commits/{sha}/ask',
                             json={'question': 'Quel est le but ?'}).json()
    moved = {'status': 'RENAMED', 'path': 'docs/termine/R1.md', 'old_path': 'docs/backlog/R1.md'}
    assert moved in json.loads(model.calls[0][1])['commit']['files']
    assert result['git']['files'] == [moved]


def test_minia_without_a_model_is_disabled_but_taxo_still_works(repo, ask):
    _, added, _ = repo
    client, post = ask(None)
    assert client.get('/api/minia/status').json() == {'configured': False, 'provider': None, 'model': None,
                                                      'source_context': 'off', 'remote': False, 'providers': []}
    response = post(added)
    assert response.status_code == 503 and 'MINIA_NOT_CONFIGURED' in response.json()['detail']


@pytest.mark.parametrize('question', ['', '   ', 'x' * 1001])
def test_a_question_must_be_meaningful(repo, ask, question):
    _, post = ask(FakeModel({}))
    assert post(repo[1], question).status_code == 422


@pytest.mark.parametrize('reply', ['pas du json', '[1, 2]', '{}', '{"cited": []}',
                                   '{"cited": "F1", "answer": "", "unknown": ""}',
                                   '{"cited": [], "answer": 3, "unknown": ""}'])
def test_an_unreadable_answer_is_refused(repo, ask, reply):
    _, post = ask(FakeModel(reply))
    response = post(repo[1])
    assert response.status_code == 502 and 'MINIA_INVALID_ANSWER' in response.json()['detail']


def test_an_unknown_commit_or_parent_is_refused(repo, ask):
    _, post = ask(FakeModel({}))
    assert post('f' * 40).status_code == 404
    assert post(repo[2], parent=repo[2]).status_code == 404


def test_the_briefing_is_bounded_and_carries_gaps(monkeypatch):
    class Commit:
        sha, author, authored_at, subject = 'a' * 40, 'Pi', '2026-09-25T00:00:00Z', 'sujet'

    change = {'change': 'INTRODUCED', 'kind': 'ASSERTION', 'subject': 's', 'relation': 'R', 'before': None,
              'after': 'o', 'status': 'OBSERVED', 'evidence_before': [],
              'evidence_after': [{'path': 'A.java', 'line_start': 3, 'line_end': 4, 'content_hash': 'sha256:x'}]}
    evaluation = {'evaluator_id': 'e', 'changes': [change] * 5, 'not_interpreted_before': ['file:B'],
                  'not_interpreted_after': ['file:A', 'file:B'], 'failures': ['boom']}
    monkeypatch.setattr(briefing, 'MAX_FACTS', 2)
    brief = briefing.build('q', Commit(), None, [evaluation])
    assert list(brief.refs) == ['F1', 'F2'] and brief.truncated == 3
    assert brief.not_interpreted == ('file:A', 'file:B') and brief.failures == ('e : boom',)
    sent = json.loads(brief.text)
    assert sent['facts_not_sent'] == 3
    assert sent['facts'][0]['evidence_after'] == [{'path': 'A.java', 'line_start': 3, 'line_end': 4}]
    zones_only = briefing.build('q', Commit(), None, [{**evaluation, 'changes': [], 'failures': []}])
    assert zones_only.empty, 'une zone non interpretee seule ne dit rien du commit'
    failed = briefing.build('q', Commit(), None, [{**evaluation, 'changes': []}])
    assert not failed.empty, 'un echec d evaluateur merite d etre explique'

    class File:
        status, path, old_path = 'ADDED', 'x', None

    monkeypatch.setattr(briefing, 'MAX_FILES', 1)
    files = briefing.build('q', Commit(), None, [evaluation], [File(), File(), File()], ('id-1', 'Demo'))
    sent = json.loads(files.text)
    assert files.files_truncated == 2 and sent['files_not_sent'] == 2 and len(sent['commit']['files']) == 1


def test_parse_keeps_only_known_references():
    parsed = parse('{"cited": ["F2", " F1 ", "F0", 7], "answer": " a ", "unknown": ""}', {'F1': {}, 'F2': {}})
    assert parsed == {'cited': ['F2', 'F1'], 'rejected': ['F0', '7'], 'answer': 'a', 'unknown': ''}
    template = parse('{"cited": [], "answer": "...", "unknown": " \u2026 "}', {})
    assert (template['answer'], template['unknown']) == ('', ''), 'un gabarit recopie n est pas une reponse'
    with pytest.raises(MiniaError) as error:
        parse(None, {})
    assert error.value.code == INVALID_ANSWER


def ollama(handler):
    return OllamaModel('qwen2.5:3b', 'http://ollama.test:11434', transport=httpx.MockTransport(handler))


def test_the_ollama_adapter_asks_for_deterministic_json():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'message': {'role': 'assistant', 'content': '{"cited": []}'}})

    assert ollama(handler).complete('sys', 'user') == '{"cited": []}'
    body = seen[0]
    assert (body['model'], body['format'], body['stream'], body['options']) == ('qwen2.5:3b', 'json', False,
                                                                                {'temperature': 0, 'num_ctx': 16384})
    assert [message['role'] for message in body['messages']] == ['system', 'user']


def test_a_request_that_would_not_fit_is_refused_rather_than_truncated():
    def handler(request):
        raise AssertionError('Ollama ne doit pas etre appele : il tronquerait les consignes en silence')

    model = OllamaModel('qwen2.5:3b', 'http://ollama.test:11434', transport=httpx.MockTransport(handler), num_ctx=4096)
    with pytest.raises(MiniaError) as error:
        model.complete('consignes', 'x' * 3 * 4096)
    assert error.value.code == 'MINIA_CONTEXT_TOO_LARGE' and 'MINIA_OLLAMA_NUM_CTX' in str(error.value)
    with pytest.raises(MiniaError):
        list(model.stream('consignes', 'x' * 3 * 4096))
    with pytest.raises(ValueError, match='NUM_CTX'):
        OllamaModel('m', num_ctx=512)


def test_a_small_model_may_omit_empty_fields():
    assert parse('{"answer": "Le commit restreindrait les origines."}', {}) == {
        'cited': [], 'rejected': [], 'answer': 'Le commit restreindrait les origines.', 'unknown': ''}
    assert parse('{"answer": "a", "cited": ["F1"]}', {'F1': {}})['cited'] == ['F1']


@pytest.mark.parametrize('handler, expected', [
    (lambda request: httpx.Response(404, json={'error': 'model not found'}), 'ollama pull qwen2.5:3b'),
    (lambda request: httpx.Response(500), 'répondu 500'),
    (lambda request: httpx.Response(200, text='pas du json'), 'illisible'),
    (lambda request: httpx.Response(200, json={'message': None}), 'illisible'),
])
def test_ollama_failures_become_minia_unavailable(handler, expected):
    with pytest.raises(MiniaError) as error:
        ollama(handler).complete('s', 'u')
    assert error.value.code == UNAVAILABLE and expected in str(error.value)


def test_an_unreachable_ollama_is_reported():
    def handler(request):
        raise httpx.ConnectError('refused', request=request)

    with pytest.raises(MiniaError) as error:
        ollama(handler).complete('s', 'u')
    assert 'ollama serve' in str(error.value)


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'ollama:11434', 'http://'])
def test_the_ollama_url_must_be_http(url):
    with pytest.raises(ValueError):
        OllamaModel('m', url)


def test_settings_choose_the_provider(monkeypatch):
    for name in ('MINIA_PROVIDER', 'MINIA_OLLAMA_URL', 'MINIA_OLLAMA_MODEL', 'MINIA_OLLAMA_NUM_CTX',
                 'MINIA_CLAUDE_MODEL', 'MINIA_GEMINI_MODEL', 'MINIA_GEMINI_TIER', 'MINIA_MISTRAL_MODEL',
                 'MINIA_MISTRAL_TIER'):
        monkeypatch.delenv(name, raising=False)
    assert settings.minia() == {'provider': 'ollama', 'url': 'http://127.0.0.1:11434', 'model': '', 'num_ctx': 16384,
                                'claude_model': '', 'gemini_model': '', 'gemini_tier': 'free', 'mistral_model': '',
                                'mistral_tier': 'free'}
    assert minia_model(settings.minia()) is None, 'sans modele, Minia reste desactivee'
    monkeypatch.setenv('MINIA_OLLAMA_MODEL', ' qwen2.5:3b ')
    model = minia_model(settings.minia())
    assert (model.provider, model.model_name, model.url) == ('ollama', 'qwen2.5:3b', 'http://127.0.0.1:11434')
    monkeypatch.setenv('MINIA_OLLAMA_NUM_CTX', '32768')
    assert minia_model(settings.minia()).num_ctx == 32768
    with pytest.raises(ValueError, match='ollama, claude, gemini ou mistral'):
        minia_model(settings.minia(provider='inconnu'))
    monkeypatch.setenv('MINIA_CLAUDE_MODEL', 'claude-opus-5')
    models = minia_models(settings.minia())
    assert list(models) == ['ollama', 'claude'] and models['claude'].remote and not models['ollama'].remote
    assert minia_model(settings.minia(provider='claude')).provider == 'claude', 'MINIA_PROVIDER choisit le defaut'
    monkeypatch.delenv('MINIA_OLLAMA_MODEL')
    assert minia_model(settings.minia()).provider == 'claude', 'le seul fournisseur configure sert par defaut'


def test_the_window_check_is_a_true_upper_bound_whatever_the_script():
    def handler(request):
        raise AssertionError('Ollama ne doit pas etre appele')

    model = OllamaModel('m', 'http://ollama.test:11434', transport=httpx.MockTransport(handler), num_ctx=8192)
    dense = '提交' * 1500  # 3 000 caracteres, 9 000 octets : « 3 caracteres par token » l'aurait accepte
    with pytest.raises(MiniaError) as error:
        model.complete('consignes', dense)
    assert error.value.code == 'MINIA_CONTEXT_TOO_LARGE'
    assert model.capacity('consignes') == 8192 - 64 - 1024 - len('consignes')


def test_facts_that_do_not_fit_are_counted_not_sent():
    fact = {'subject': 'commit:' + 'a' * 40, 'relation': 'CHANGES', 'object': 'file:' + 'x' * 200,
            'qualifiers': {'change': 'MODIFIED'}, 'evidence': []}
    projection = {'facts': [fact] * 28, 'request': {'kind': 'LATEST'}, 'commits': [1, 2], 'total_commits': 9,
                  'not_interpreted': []}
    whole = briefing.selection('q', projection)
    assert whole.truncated == 0 and len(whole.refs) == 28
    budget = len(whole.text.encode('utf-8')) // 2
    fitted = briefing.selection('q', projection, max_bytes=budget)
    assert len(fitted.text.encode('utf-8')) <= budget
    assert 0 < len(fitted.refs) < 28 and fitted.truncated == 28 - len(fitted.refs)
    assert json.loads(fitted.text)['facts_not_sent'] == fitted.truncated
    assert briefing.selection('q', projection, max_bytes=10).refs == {}, 'aucun fait plutot qu un fait tronque'
