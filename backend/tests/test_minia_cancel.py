"""TAXO-UX-03 : arreter Minia. L'arret empeche tout nouveau tour, coupe l'appel au fournisseur en cours et ne
produit aucune reponse finale ; la trajectoire deja parcourue reste visible."""
import json
import threading
import time
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.minia.domain.cancellation import STOPPED, Cancellation
from app.minia.domain.errors import CANCELLED, MiniaError
from app.minia.infrastructure.claude import ClaudeModel
from app.minia.infrastructure.gemini import GeminiModel
from app.minia.infrastructure.mistral import MistralModel
from app.minia.infrastructure.ollama import OllamaModel
from app.protocol.application.exchange import Exchange
from tests.test_minia_explore import ScriptedModel, answer, call, statement


@pytest.fixture(name='repo')
def repo_fixture(make_repo, git):
    repo = make_repo({'README.md': 'Taxo\n', 'src/app.txt': 'un\n'}, 'arret')
    (repo / 'src/app.txt').write_text('deux\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'change app')
    return repo, git(repo, 'rev-parse', 'HEAD')


def events_of(text):
    return [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
            for block in text.strip().split('\n\n') if not block.startswith(':')]


def ask(repo, sha, tmp_path, model, prepare=None):
    app = create_app(f'sqlite:///{tmp_path / "arret.db"}', [repo], minia=model)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Arret', 'path': str(repo)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        minia = app.state.minia

        def running():
            with minia._running_lock:
                return next(iter(minia._running))

        def stop():
            """Arret depuis l'interieur de la demande (le client de test ne peut pas s'appeler lui-meme)."""
            return minia.stop(running())

        def stop_over_http():
            """Arret par l'API, comme le portail, depuis un autre fil."""
            assert client.post(f'/api/minia/requests/{running()}/cancel').status_code == 202

        if prepare:
            prepare(stop, stop_over_http)
        text = client.post(f'/api/projects/{project["id"]}/history/commits/{sha}/ask/stream',
                           json={'question': 'Que change ce commit ?'}).text
        leftover = client.post('/api/minia/requests/inconnue/cancel')
        return events_of(text), leftover, minia


def kinds(events):
    return [kind for kind, _ in events]


def assert_stopped(events):
    assert kinds(events)[0] == 'minia.started' and events[0][1]['request_id']
    assert events[-1] == ('minia.cancelled', {'message': STOPPED}), 'un arret, pas une erreur'
    assert 'minia.completed' not in kinds(events) and 'minia.failed' not in kinds(events), 'aucune reponse finale'


def test_stop_during_a_taxo_operation(repo, tmp_path, monkeypatch):
    repo, sha = repo
    model = ScriptedModel(answer(statement('unknown', 'Jamais lu.')))
    original, stopper = Exchange.call, {}

    def call_then_stop(self, request):
        response = original(self, request)
        if request.get('operation') == 'get_commit':
            stopper['stop']()
        return response

    monkeypatch.setattr(Exchange, 'call', call_then_stop)
    events, _, minia = ask(repo, sha, tmp_path, model, prepare=lambda stop, _: stopper.update(stop=stop))
    assert_stopped(events)
    assert [data['operation'] for kind, data in events if kind == 'minia.operation'] == ['describe', 'get_commit'], \
        'la trajectoire deja parcourue reste visible'
    assert model.calls == [], 'plus aucun tour du modele apres l arret'
    assert minia._running == {}, 'la demande arretee est oubliee'


def test_stop_while_waiting_for_the_model_cuts_the_provider_call(repo, tmp_path):
    repo, sha = repo
    cut = threading.Event()

    class Waiting(ScriptedModel):
        def complete(self, system, user, schema=None, cancel=None):
            self.calls.append((system, user, schema))
            cancel.on_cancel(cut.set)  # comme un vrai fournisseur : l'arret ferme sa connexion
            cut.wait(timeout=10)
            raise MiniaError(CANCELLED, STOPPED)

    model = Waiting()
    started = time.monotonic()
    events, _, _ = ask(repo, sha, tmp_path, model,
                       prepare=lambda _, stop_over_http: threading.Timer(0.5, stop_over_http).start())
    assert_stopped(events)
    assert cut.is_set(), 'l appel au fournisseur est coupe, pas seulement masque'
    assert time.monotonic() - started < 8, 'l arret n attend pas la fin du tour'


def test_stop_between_two_exploration_turns(repo, tmp_path):
    repo, sha = repo
    stopper = {}

    class StopsAfterAsking(ScriptedModel):
        def complete(self, system, user, schema=None, cancel=None):
            reply = super().complete(system, user, schema)
            stopper['stop']()
            return reply

    model = StopsAfterAsking(call('find_facts', relation='CHANGES'), answer(statement('unknown', 'Jamais lu.')))
    events, _, _ = ask(repo, sha, tmp_path, model, prepare=lambda stop, _: stopper.update(stop=stop))
    assert_stopped(events)
    assert 'find_facts' not in [data['operation'] for kind, data in events if kind == 'minia.operation'], \
        'l operation demandee au dernier tour n est pas executee'
    assert len(model.calls) == 1


def test_stop_during_a_packet_answer(repo, tmp_path, git):
    repo, _ = repo
    (repo / 'main.py').write_text('print(1)\n')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'ajoute main.py')
    sha = git(repo, 'rev-parse', 'HEAD')
    stopper = {}

    class Streaming(ScriptedModel):
        explores = False

        def stream(self, system, user, cancel=None):
            yield '{"cited": [], "answer": "Un '
            stopper['stop']()
            yield 'fichier aurait changé.", "unknown": ""}'

    events, _, _ = ask(repo, sha, tmp_path, Streaming(), prepare=lambda stop, _: stopper.update(stop=stop))
    assert_stopped(events)


def test_an_unknown_or_finished_request_cannot_be_stopped(repo, tmp_path):
    repo, sha = repo
    events, leftover, minia = ask(repo, sha, tmp_path, ScriptedModel(answer(statement('unknown', 'Fini.'))))
    assert kinds(events)[-1] == 'minia.completed'
    assert leftover.status_code == 404 and minia._running == {}


def test_a_cancellation_cuts_each_call_once():
    cancel, cut = Cancellation(), []
    forget = cancel.on_cancel(lambda: cut.append('a'))
    cancel.on_cancel(lambda: cut.append('b'))
    forget()
    cancel.cancel()
    cancel.cancel()
    assert cut == ['b'] and cancel.cancelled
    cancel.on_cancel(lambda: cut.append('c'))
    assert cut == ['b', 'c'], 'un appel commence apres l arret est coupe tout de suite'
    with pytest.raises(MiniaError) as stopped:
        cancel.check()
    assert stopped.value.code == CANCELLED


class Lines(httpx.SyncByteStream):
    """Le flux d'une reponse d'Ollama, qui arrete la demande apres son premier morceau."""

    def __init__(self, cancel):
        self.cancel, self.closed = cancel, False

    def __iter__(self):
        yield json.dumps({'message': {'content': '{"action":'}}).encode() + b'\n'
        self.cancel.cancel()
        yield json.dumps({'message': {'content': '"answer"}'}, 'done': True}).encode() + b'\n'

    def close(self):
        self.closed = True


def test_the_ollama_call_is_really_closed_when_stopped():
    cancel = Cancellation()
    body = Lines(cancel)
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, stream=body)

    model = OllamaModel('qwen2.5-coder:7b', 'http://127.0.0.1:11434', transport=httpx.MockTransport(handler))
    with pytest.raises(MiniaError) as stopped:
        model.complete('sys', 'user', {'type': 'object'}, cancel=cancel)
    assert stopped.value.code == CANCELLED
    assert seen[0]['stream'] is True and seen[0]['format'] == {'type': 'object'}, 'avec un jeton, le tour passe par le flux'
    assert body.closed, 'la connexion est fermee : Ollama cesse de generer'


def remote_models(handler, waits):
    transport = httpx.MockTransport(handler)
    return [MistralModel('mistral-test', api_key='cle-test', transport=transport, sleep=waits.append),
            GeminiModel('gemini-test', api_key='cle-test', transport=transport, sleep=waits.append)]


@pytest.mark.parametrize('index', [0, 1], ids=['mistral', 'gemini'])
def test_a_stop_during_the_retry_backoff_sends_nothing_more(index):
    cancel, seen, waits = Cancellation(), [], []

    def handler(request):
        seen.append(request)
        cancel.cancel()
        return httpx.Response(503, json={'message': 'overloaded'})

    with pytest.raises(MiniaError) as stopped:
        remote_models(handler, waits)[index].complete('s', 'u', cancel=cancel)
    assert stopped.value.code == CANCELLED
    assert len(seen) == 1, 'aucune nouvelle tentative apres l arret'
    assert waits == [], 'l attente entre deux tentatives est celle du jeton, que l arret interrompt'


@pytest.mark.parametrize('index', [0, 1], ids=['mistral', 'gemini'])
def test_the_dedicated_client_of_a_call_is_closed_when_stopped_before_the_answer(index):
    cancel, seen, clients = Cancellation(), [], []

    def handler(request):
        seen.append(request)
        cancel.cancel()
        assert clients[-1].is_closed, 'l arret ferme le client de l appel avant meme la reponse'
        raise httpx.ConnectError('coupe', request=request)

    model = remote_models(handler, [])[index]
    make = model._new_client

    def tracked():
        clients.append(make())
        return clients[-1]

    model._new_client = tracked
    with pytest.raises(MiniaError) as stopped:
        model.complete('s', 'u', cancel=cancel)
    assert stopped.value.code == CANCELLED and len(seen) == 1 and len(clients) == 1
    assert not model._client.is_closed, 'le client partage reste utilisable pour les autres demandes'


def test_a_stopped_claude_call_closes_its_own_client(monkeypatch):
    cancel, closed = Cancellation(), []

    class Stream:
        def __enter__(self):
            cancel.cancel()
            return self

        def __exit__(self, *error):
            return False

        @property
        def text_stream(self):
            raise anthropic.APIConnectionError(request=httpx.Request('POST', 'https://api.anthropic.com'))

    class Client:
        def __init__(self):
            self.beta = SimpleNamespace(messages=SimpleNamespace(stream=lambda **request: Stream()))

        def close(self):
            closed.append(self)

    monkeypatch.setattr(anthropic, 'Anthropic', Client)
    with pytest.raises(MiniaError) as stopped:
        ClaudeModel('claude-test').complete('s', 'u', cancel=cancel)
    assert stopped.value.code == CANCELLED
    assert len(closed) >= 1, 'le client de l appel est ferme par l arret'
