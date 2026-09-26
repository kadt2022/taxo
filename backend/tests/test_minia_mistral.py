"""TAXO-MINIA-10 : Minia servie par Mistral, avec le meme contrat que les autres fournisseurs."""
import json

import httpx
import pytest

from app.bootstrap import settings
from app.bootstrap.application import minia_models
from app.minia.domain import exploration
from app.minia.domain.errors import MiniaError
from app.minia.infrastructure.mistral import ANSWER_SCHEMA, API_URL, MistralModel

ANSWER = '{"cited": [], "answer": "Le commit restreindrait les origines.", "unknown": ""}'


def mistral(handler, **options):
    options.setdefault('sleep', lambda seconds: None)
    return MistralModel('mistral-test', api_key='cle-test', transport=httpx.MockTransport(handler), **options)


def reply(content, finish='stop', **extra):
    return {'model': 'mistral-test-2609', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content},
                                                      'finish_reason': finish}], **extra}


def chunk(content, finish=None):
    return f'data: {json.dumps({"model": "mistral-test-2609", "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish}]})}'


def test_mistral_is_asked_for_the_answer_object_with_the_key_in_a_header():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=reply(ANSWER))

    assert mistral(handler).complete('consignes', 'faits') == ANSWER
    request = seen[0]
    assert str(request.url) == API_URL
    assert request.headers['authorization'] == 'Bearer cle-test' and 'cle-test' not in str(request.url)
    body = json.loads(request.content)
    assert (body['model'], body['temperature'], body['stream']) == ('mistral-test', 0, False)
    assert body['messages'] == [{'role': 'system', 'content': 'consignes'}, {'role': 'user', 'content': 'faits'}]
    assert body['response_format'] == {'type': 'json_schema', 'json_schema': {
        'name': 'minia', 'schema': ANSWER_SCHEMA, 'strict': True}}


def test_the_exploration_step_is_constrained_by_its_schema():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply('{}'))

    model = mistral(handler)
    assert model.explores
    model.complete('s', 'u', exploration.STEP_SCHEMA)
    assert seen[0]['response_format']['json_schema']['schema'] == exploration.STEP_SCHEMA


def test_mistral_streams_and_names_the_model_that_answered():
    lines = [chunk('{"cited": [], "answer": "Le '), chunk('commit", "unknown": ""}'), chunk('', 'stop'),
             'data: [DONE]']

    def handler(request):
        assert json.loads(request.content)['stream'] is True
        return httpx.Response(200, text='\n\n'.join(lines) + '\n\n')

    pieces, chunks = mistral(handler).stream('s', 'u'), []
    while True:
        try:
            chunks.append(next(pieces))
        except StopIteration as end:
            served = end.value
            break
    assert ''.join(chunks) == '{"cited": [], "answer": "Le commit", "unknown": ""}'
    assert served == 'mistral-test-2609'


def test_reasoning_is_never_part_of_the_answer():
    content = [{'type': 'thinking', 'thinking': [{'type': 'text', 'text': 'je réfléchis'}]}, {'type': 'text', 'text': ANSWER}]
    assert mistral(lambda request: httpx.Response(200, json=reply(content))).complete('s', 'u') == ANSWER


@pytest.mark.parametrize('finish, expected', [('length', 'coupée'), ('model_length', 'coupée'), ('error', 'terminer')])
def test_a_cut_or_failed_answer_is_not_shown(finish, expected):
    with pytest.raises(MiniaError, match=expected):
        mistral(lambda request: httpx.Response(200, json=reply('{', finish))).complete('s', 'u')
    with pytest.raises(MiniaError, match=expected):
        list(mistral(lambda request: httpx.Response(200, text=chunk('{', finish) + '\n\n')).stream('s', 'u'))


@pytest.mark.parametrize('status, body, expected', [
    (401, {'message': 'Unauthorized'}, 'MISTRAL_API_KEY'),
    (404, {'message': 'not found'}, 'non accessible avec cette clé.*MINIA_MISTRAL_MODEL.*not found'),
    (400, {'message': 'Invalid model: mistral-inconnu'}, 'MINIA_MISTRAL_MODEL'),
    (429, {'message': 'Requests rate limit exceeded'}, 'Quota'),
    (422, {'detail': [{'msg': 'schema invalide'}]}, 'schema invalide'),
    (400, {}, 'requête invalide'),
    (503, {'message': 'overloaded'}, 'surchargé.*overloaded'),
    (500, None, 'répondu 500'),
])
def test_api_errors_are_said_plainly(status, body, expected):
    def handler(request):
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status, text='panne')

    for call in (lambda model: model.complete('s', 'u'), lambda model: list(model.stream('s', 'u'))):
        with pytest.raises(MiniaError, match=expected):
            call(mistral(handler))


def test_a_transient_overload_is_retried_before_any_text():
    answers = [httpx.Response(503, json={'message': 'overloaded'}), httpx.Response(200, json=reply(ANSWER))]
    waits = []
    model = mistral(lambda request: answers.pop(0), sleep=waits.append)
    assert model.complete('s', 'u') == ANSWER and waits == [1.5]
    quota = [httpx.Response(429, json={}), httpx.Response(200, json=reply(ANSWER))]
    with pytest.raises(MiniaError, match='Quota'):
        mistral(lambda request: quota.pop(0)).complete('s', 'u')


def test_network_failures_and_unreadable_answers_are_reported():
    def refuse(request):
        raise httpx.ConnectError('refused', request=request)

    with pytest.raises(MiniaError, match='injoignable'):
        mistral(refuse).complete('s', 'u')
    with pytest.raises(MiniaError, match='illisible'):
        mistral(lambda request: httpx.Response(200, text='pas du json')).complete('s', 'u')
    with pytest.raises(MiniaError, match='illisible'):
        list(mistral(lambda request: httpx.Response(200, text='data: pas du json\n\n')).stream('s', 'u'))
    assert mistral(lambda request: httpx.Response(200, json={'choices': []})).complete('s', 'u') == ''


def test_the_key_comes_from_the_environment_and_its_absence_is_said(monkeypatch):
    monkeypatch.delenv('MISTRAL_API_KEY', raising=False)
    model = MistralModel('mistral-test', transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(MiniaError, match='MISTRAL_API_KEY'):
        model.complete('s', 'u')
    monkeypatch.setenv('MISTRAL_API_KEY', 'depuis-env')
    assert model._headers()['Authorization'] == 'Bearer depuis-env'


def test_a_request_that_would_not_fit_is_refused_before_calling_mistral():
    model = mistral(lambda request: pytest.fail('Mistral ne doit pas etre appele'), max_input_bytes=100)
    with pytest.raises(MiniaError, match='place réservée'):
        model.complete('consignes', 'x' * 200)


def test_the_free_tier_is_said_to_share_data(monkeypatch):
    assert MistralModel('m').data_use and MistralModel('m').remote
    assert not MistralModel('m', tier='paid').data_use
    with pytest.raises(ValueError, match='MINIA_MISTRAL_TIER'):
        MistralModel('m', tier='pro')
    for name in ('MINIA_OLLAMA_MODEL', 'MINIA_CLAUDE_MODEL', 'MINIA_GEMINI_MODEL', 'MINIA_MISTRAL_TIER', 'MINIA_PROVIDER'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MINIA_MISTRAL_MODEL', 'mistral-small-latest')
    models = minia_models(settings.minia())
    assert list(models) == ['mistral'] and models['mistral'].data_use and models['mistral'].provider == 'mistral'
