"""TAXO-MINIA-05 : Minia servie par Claude, au choix de chaque demande, avec le meme contrat que Minia Ollama."""
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.minia.domain.errors import MiniaError
from app.minia.infrastructure.claude import ANSWER_SCHEMA, ClaudeModel


def text_message(text, stop_reason='end_turn'):
    return SimpleNamespace(content=[SimpleNamespace(type='thinking', thinking=''), SimpleNamespace(type='text', text=text)],
                           stop_reason=stop_reason)


class FakeStream:
    def __init__(self, chunks, stop_reason='end_turn'):
        self.text_stream, self.stop_reason = iter(chunks), stop_reason

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return text_message('', self.stop_reason)


class FakeMessages:
    def __init__(self, reply=None, chunks=(), error=None, stop_reason='end_turn'):
        self.reply, self.chunks, self.error, self.stop_reason, self.calls = reply, chunks, error, stop_reason, []

    def create(self, **request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return text_message(self.reply, self.stop_reason)

    def stream(self, **request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return FakeStream(self.chunks, self.stop_reason)


def claude(messages, model='claude-opus-5', **options):
    return ClaudeModel(model, client=SimpleNamespace(beta=SimpleNamespace(messages=messages)), **options)


def test_claude_is_asked_for_the_answer_object_and_nothing_else():
    messages = FakeMessages(reply='{"cited": [], "answer": "ok", "unknown": ""}')
    assert claude(messages).complete('consignes', 'faits') == '{"cited": [], "answer": "ok", "unknown": ""}'
    request = messages.calls[0]
    assert (request['model'], request['system'], request['messages']) == (
        'claude-opus-5', 'consignes', [{'role': 'user', 'content': 'faits'}])
    assert request['output_config'] == {'format': {'type': 'json_schema', 'schema': ANSWER_SCHEMA}}
    assert request['fallbacks'] == 'default' and request['betas'] == ['server-side-fallback-2026-07-01']
    assert 'fallbacks' not in (claude(FakeMessages(reply='{}'), model='claude-haiku-4-5')._request('s', 'u'))


def test_claude_streams_its_answer():
    messages = FakeMessages(chunks=['{"cited": [], "answer": "Le ', 'commit restreindrait"', ', "unknown": ""}'])
    assert ''.join(claude(messages).stream('s', 'u')) == '{"cited": [], "answer": "Le commit restreindrait", "unknown": ""}'


@pytest.mark.parametrize('stop_reason, expected', [('refusal', 'décliné'), ('max_tokens', 'coupée')])
def test_a_declined_or_cut_answer_is_not_shown(stop_reason, expected):
    with pytest.raises(MiniaError, match=expected):
        claude(FakeMessages(reply='{}', stop_reason=stop_reason)).complete('s', 'u')
    with pytest.raises(MiniaError, match=expected):
        list(claude(FakeMessages(chunks=['{'], stop_reason=stop_reason)).stream('s', 'u'))


def _api_error(kind, status):
    request = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')
    return kind('erreur', response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize('error, expected', [
    (lambda: _api_error(anthropic.AuthenticationError, 401), 'ANTHROPIC_API_KEY'),
    (lambda: _api_error(anthropic.PermissionDeniedError, 403), 'pas accès'),
    (lambda: _api_error(anthropic.NotFoundError, 404), 'MINIA_CLAUDE_MODEL'),
    (lambda: _api_error(anthropic.RateLimitError, 429), 'Limite de débit'),
    (lambda: _api_error(anthropic.BadRequestError, 400), 'Requête refusée'),
    (lambda: _api_error(anthropic.InternalServerError, 500), 'répondu 500'),
    (lambda: anthropic.APIConnectionError(request=httpx2.Request('POST', 'https://api.anthropic.com')), 'injoignable'),
])
def test_api_errors_are_said_plainly(error, expected):
    for call in (lambda model: model.complete('s', 'u'), lambda model: list(model.stream('s', 'u'))):
        with pytest.raises(MiniaError, match=expected) as raised:
            call(claude(FakeMessages(error=error())))
        assert raised.value.code == 'MINIA_UNAVAILABLE'


def test_a_request_that_would_not_fit_is_refused_before_calling_claude():
    messages = FakeMessages(reply='{}')
    model = claude(messages, max_input_bytes=100)
    assert model.capacity('consignes') == 100 - len('consignes')
    with pytest.raises(MiniaError, match='place réservée'):
        model.complete('consignes', 'x' * 200)
    assert messages.calls == []


def test_missing_credentials_are_reported_at_use_not_at_startup(monkeypatch):
    def refuse(*args, **kwargs):
        raise anthropic.AnthropicError('pas d identifiants')

    monkeypatch.setattr(anthropic, 'Anthropic', refuse)
    model = ClaudeModel('claude-opus-5')
    with pytest.raises(MiniaError, match='ANTHROPIC_API_KEY'):
        model.complete('s', 'u')


class Named:
    def __init__(self, provider, remote):
        self.provider, self.model_name, self.remote, self.calls = provider, f'{provider}-1', remote, []

    def complete(self, system, user):
        self.calls.append(user)
        return json.dumps({'cited': [], 'answer': f'Réponse de {self.provider}.', 'unknown': ''})


@pytest.fixture(name='both')
def both_fixture(make_repo, git, tmp_path):
    repo = make_repo({'README.md': 'a\n'}, 'choix')
    (repo / 'package.json').write_text(json.dumps({'dependencies': {'react': '19'}}))
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'ajoute React')
    sha = git(repo, 'rev-parse', 'HEAD')
    ollama, remote = Named('ollama', False), Named('claude', True)
    app = create_app(f'sqlite:///{tmp_path / "choix.db"}', [repo], minia={'ollama': ollama, 'claude': remote})
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Choix', 'path': str(repo)}).json()
        yield client, f'/api/projects/{project["id"]}/history/commits/{sha}/ask', ollama, remote


def test_each_question_chooses_its_provider(both):
    client, url, ollama, remote = both
    status = client.get('/api/minia/status').json()
    assert status['provider'] == 'ollama' and not status['remote'], 'le premier fournisseur sert par defaut'
    assert status['providers'] == [{'provider': 'ollama', 'model': 'ollama-1', 'remote': False},
                                   {'provider': 'claude', 'model': 'claude-1', 'remote': True}]
    by_default = client.post(url, json={'question': 'Que change ce commit ?'}).json()
    chosen = client.post(url, json={'question': 'Que change ce commit ?', 'provider': 'claude'}).json()
    assert by_default['answer'] == 'Réponse de ollama.' and by_default['model']['provider'] == 'ollama'
    assert chosen['answer'] == 'Réponse de claude.' and chosen['model'] == {'configured': True, 'provider': 'claude',
                                                                              'model': 'claude-1'}
    assert remote.calls == [ollama.calls[0]], 'meme travail, meme message, quel que soit le fournisseur'


def test_an_unconfigured_provider_is_refused(both):
    client, url, _, _ = both
    response = client.post(url, json={'question': 'Que change ce commit ?', 'provider': 'gemini'})
    assert response.status_code == 422 and 'MINIA_UNKNOWN_PROVIDER' in response.json()['detail']
