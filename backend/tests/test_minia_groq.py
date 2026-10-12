"""Minia servie par Groq, avec le même contrat que les autres fournisseurs distants. Aucun appel réel : un transport
simulé, et une clé de test."""
import json

import httpx
import pytest

from app.bootstrap import settings
from app.bootstrap.application import minia_models
from app.minia.domain import exploration
from app.minia.domain.errors import MiniaError
from app.minia.infrastructure.groq import ANSWER_SCHEMA, API_URL, STRICT_MODELS, GroqModel

ANSWER = '{"cited": [], "answer": "Le commit restreindrait les origines.", "unknown": ""}'
STRICT = 'openai/gpt-oss-120b'


def groq(handler, model=STRICT, **options):
    options.setdefault('sleep', lambda seconds: None)
    return GroqModel(model, api_key='cle-test', transport=httpx.MockTransport(handler), **options)


def reply(content, finish='stop', **extra):
    return {'model': 'served-1', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content},
                                              'finish_reason': finish}], **extra}


def chunk(content, finish=None, **delta):
    payload = {'model': 'served-1', 'choices': [{'index': 0, 'delta': {'content': content, **delta},
                                                 'finish_reason': finish}]}
    return f'data: {json.dumps(payload)}'


def refusing(status, message=''):
    return lambda request: httpx.Response(status, json={'error': {'message': message}})


def test_groq_is_asked_for_the_answer_object_with_the_key_in_a_header():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=reply(ANSWER))

    assert groq(handler).complete('consignes', 'faits') == ANSWER
    request = seen[0]
    assert str(request.url) == API_URL
    assert request.headers['authorization'] == 'Bearer cle-test'
    assert 'cle-test' not in str(request.url)
    body = json.loads(request.content)
    assert (body['model'], body['temperature'], body['stream']) == (STRICT, 0, False)
    assert body['max_completion_tokens'] == 8192
    assert body['messages'] == [{'role': 'system', 'content': 'consignes'}, {'role': 'user', 'content': 'faits'}]
    assert body['response_format'] == {'type': 'json_schema', 'json_schema': {
        'name': 'minia', 'schema': ANSWER_SCHEMA, 'strict': True}}


def test_a_model_without_strict_schema_gets_a_json_object_and_the_schema_in_the_instructions():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply(ANSWER))

    groq(handler, model='un-autre-modele').complete('consignes', 'faits')
    assert seen[0]['response_format'] == {'type': 'json_object'}
    system = seen[0]['messages'][0]['content']
    assert system.startswith('consignes')
    assert '"cited"' in system


def test_the_strict_models_are_the_ones_groq_documents():
    assert STRICT in STRICT_MODELS
    assert 'openai/gpt-oss-20b' in STRICT_MODELS


def test_the_exploration_step_is_constrained_by_its_schema():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply('{}'))

    model = groq(handler)
    assert model.explores
    model.complete('s', 'u', exploration.STEP_SCHEMA)
    assert seen[0]['response_format']['json_schema']['schema'] == exploration.STEP_SCHEMA


def test_the_reasoning_of_the_model_is_never_returned():
    message = {'role': 'assistant', 'content': ANSWER, 'reasoning': 'je réfléchis au secret'}
    model = groq(lambda request: httpx.Response(200, json={'choices': [{'message': message, 'finish_reason': 'stop'}]}))
    assert model.complete('s', 'u') == ANSWER


def test_the_stream_gives_the_content_and_ends_with_the_model_that_answered():
    lines = [chunk('', reasoning='réflexion'), chunk('{"cited": [],'), chunk(' "answer": "x", "unknown": ""}'),
             chunk('', 'stop'), 'data: [DONE]']
    model = groq(lambda request: httpx.Response(200, text='\n\n'.join(lines) + '\n\n'))
    parts = model.stream('s', 'u')
    received = []
    while True:
        try:
            received.append(next(parts))
        except StopIteration as done:
            served = done.value
            break
    assert ''.join(received) == '{"cited": [], "answer": "x", "unknown": ""}'
    assert served == 'served-1'


def test_an_answer_cut_by_the_length_limit_is_not_an_answer():
    model = groq(lambda request: httpx.Response(200, json=reply('{"cited"', finish='length')))
    with pytest.raises(MiniaError, match='coupée'):
        model.complete('s', 'u')


def test_without_a_key_minia_says_which_variable_to_define(monkeypatch):
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    model = GroqModel(STRICT, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=reply(ANSWER))))
    with pytest.raises(MiniaError, match='GROQ_API_KEY'):
        model.complete('s', 'u')


@pytest.mark.parametrize('status, expected', [
    (401, 'Clé Groq refusée'), (403, 'Clé Groq refusée'), (404, 'Modèle Groq introuvable'),
    (413, 'limite de tokens'), (429, 'Quota de l’API Groq'), (400, 'Requête refusée par l’API Groq'),
    (500, 'a répondu 500')])
def test_the_errors_of_the_api_are_said_in_clear_without_the_key(status, expected):
    with pytest.raises(MiniaError) as raised:
        groq(refusing(status, 'détail du service')).complete('s', 'u')
    assert expected in str(raised.value)
    assert 'cle-test' not in str(raised.value)


def test_a_request_larger_than_the_room_is_refused_before_leaving_the_machine():
    calls = []
    model = groq(lambda request: calls.append(request) or httpx.Response(200, json=reply(ANSWER)))
    with pytest.raises(MiniaError, match='MINIA_GROQ_NUM_CTX'):
        model.complete('s', 'x' * model.num_ctx)
    assert calls == []


def test_groq_is_a_remote_service_and_the_free_tier_may_use_the_data():
    free, paid = GroqModel(STRICT), GroqModel(STRICT, tier='paid')
    assert free.remote is True
    assert free.data_use is True
    assert paid.data_use is False


def test_the_options_are_checked():
    with pytest.raises(ValueError, match='MINIA_GROQ_TIER'):
        GroqModel(STRICT, tier='gratuit')
    with pytest.raises(ValueError, match='MINIA_GROQ_NUM_CTX'):
        GroqModel(STRICT, num_ctx=1000)


def test_the_settings_enable_groq_only_with_a_model(monkeypatch):
    for name in ('MINIA_GROQ_MODEL', 'MINIA_GROQ_TIER', 'MINIA_GROQ_NUM_CTX'):
        monkeypatch.delenv(name, raising=False)
    assert 'groq' not in minia_models(settings.minia())
    monkeypatch.setenv('MINIA_GROQ_MODEL', f' {STRICT} ')
    monkeypatch.setenv('MINIA_GROQ_TIER', 'paid')
    monkeypatch.setenv('MINIA_GROQ_NUM_CTX', '65536')
    model = minia_models(settings.minia())['groq']
    assert (model.provider, model.model_name, model.num_ctx, model.data_use) == ('groq', STRICT, 65536, False)


def test_groq_can_be_the_default_provider_and_the_other_providers_are_kept(monkeypatch):
    monkeypatch.setenv('MINIA_GROQ_MODEL', STRICT)
    monkeypatch.setenv('MINIA_CLAUDE_MODEL', 'claude-test')
    models = minia_models(settings.minia(provider='groq'))
    assert {'groq', 'claude'} <= set(models)
    assert models['claude'].provider == 'claude'
