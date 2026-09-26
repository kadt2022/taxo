"""TAXO-MINIA-06 : Minia servie par Gemini, avec le meme contrat que Minia Ollama et Minia Claude."""
import json

import httpx
import pytest

from app.bootstrap import settings
from app.bootstrap.application import minia_models
from app.minia.domain.errors import MiniaError
from app.minia.infrastructure.gemini import ANSWER_SCHEMA, GeminiModel

ANSWER = '{"cited": [], "answer": "Le commit restreindrait les origines.", "unknown": ""}'


def gemini(handler, **options):
    return GeminiModel('gemini-test', api_key='cle-test', transport=httpx.MockTransport(handler), **options)


def reply(text, finish='STOP', **extra):
    return {'candidates': [{'content': {'parts': [{'text': text}]}, 'finishReason': finish}], **extra}


def test_gemini_is_asked_for_the_answer_object_with_the_key_in_a_header():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=reply(ANSWER))

    assert gemini(handler).complete('consignes', 'faits') == ANSWER
    request = seen[0]
    assert request.url.path.endswith('/models/gemini-test:generateContent')
    assert request.headers['x-goog-api-key'] == 'cle-test' and 'key=' not in str(request.url), 'jamais dans l URL'
    body = json.loads(request.content)
    assert body['systemInstruction'] == {'parts': [{'text': 'consignes'}]}
    assert body['contents'] == [{'role': 'user', 'parts': [{'text': 'faits'}]}]
    config = body['generationConfig']
    assert (config['temperature'], config['responseMimeType'], config['responseSchema']) == (
        0, 'application/json', ANSWER_SCHEMA)


def test_gemini_streams_and_names_the_model_version_that_answered():
    lines = [f'data: {json.dumps(reply(chunk, finish=None))}' for chunk in ('{"cited": [], "answer": "Le ', 'commit"')]
    end = json.dumps(reply(', "unknown": ""}', modelVersion='gemini-test-002'))
    lines.append(f'data: {end}')

    def handler(request):
        assert request.url.path.endswith(':streamGenerateContent') and request.url.params['alt'] == 'sse'
        return httpx.Response(200, text='\n\n'.join(lines) + '\n\n')

    pieces, chunks = gemini(handler).stream('s', 'u'), []
    while True:
        try:
            chunks.append(next(pieces))
        except StopIteration as end:
            served = end.value
            break
    assert ''.join(chunks) == '{"cited": [], "answer": "Le commit", "unknown": ""}'
    assert served == 'gemini-test-002'


def test_thoughts_are_never_part_of_the_answer():
    def handler(request):
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [
            {'text': 'je réfléchis', 'thought': True}, {'text': ANSWER}]}, 'finishReason': 'STOP'}]})

    assert gemini(handler).complete('s', 'u') == ANSWER


@pytest.mark.parametrize('payload, expected', [
    (reply('{', finish='MAX_TOKENS'), 'coupée'),
    (reply('', finish='SAFETY'), 'décliné'),
    ({'promptFeedback': {'blockReason': 'SAFETY'}}, 'décliné'),
])
def test_a_blocked_or_cut_answer_is_not_shown(payload, expected):
    with pytest.raises(MiniaError, match=expected):
        gemini(lambda request: httpx.Response(200, json=payload)).complete('s', 'u')
    with pytest.raises(MiniaError, match=expected):
        list(gemini(lambda request: httpx.Response(200, text=f'data: {json.dumps(payload)}\n\n')).stream('s', 'u'))


@pytest.mark.parametrize('status, body, expected', [
    (400, {'error': {'message': 'API key not valid.', 'status': 'INVALID_ARGUMENT'}}, 'GEMINI_API_KEY'),
    (403, {'error': {'status': 'PERMISSION_DENIED'}}, 'GEMINI_API_KEY'),
    (404, {'error': {'message': 'not found'}}, 'non accessible avec cette clé.*MINIA_GEMINI_MODEL.*not found'),
    (404, {}, 'Google AI Studio\\.$'),
    (429, {'error': {'status': 'RESOURCE_EXHAUSTED'}}, 'Quota'),
    (400, {'error': {'message': 'schema invalide'}}, 'schema invalide'),
    (500, {}, 'répondu 500'),
    (502, None, 'répondu 502'),
])
def test_api_errors_are_said_plainly(status, body, expected):
    def handler(request):
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status, text='panne')

    for call in (lambda model: model.complete('s', 'u'), lambda model: list(model.stream('s', 'u'))):
        with pytest.raises(MiniaError, match=expected):
            call(gemini(handler))


def test_network_failures_and_unreadable_answers_are_reported():
    def refuse(request):
        raise httpx.ConnectError('refused', request=request)

    with pytest.raises(MiniaError, match='injoignable'):
        gemini(refuse).complete('s', 'u')
    with pytest.raises(MiniaError, match='injoignable'):
        list(gemini(refuse).stream('s', 'u'))
    with pytest.raises(MiniaError, match='illisible'):
        gemini(lambda request: httpx.Response(200, text='pas du json')).complete('s', 'u')
    with pytest.raises(MiniaError, match='illisible'):
        list(gemini(lambda request: httpx.Response(200, text='data: pas du json\n\n')).stream('s', 'u'))


def test_the_key_comes_from_the_environment_and_its_absence_is_said(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    model = GeminiModel('gemini-test', transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(MiniaError, match='GEMINI_API_KEY'):
        model.complete('s', 'u')
    monkeypatch.setenv('GEMINI_API_KEY', 'depuis-env')
    assert model._headers()['x-goog-api-key'] == 'depuis-env'


def test_a_request_that_would_not_fit_is_refused_before_calling_gemini():
    model = gemini(lambda request: pytest.fail('Gemini ne doit pas etre appele'), max_input_bytes=100)
    with pytest.raises(MiniaError, match='place réservée'):
        model.complete('consignes', 'x' * 200)


def test_the_free_tier_is_said_to_share_data(monkeypatch):
    assert GeminiModel('m').data_use and GeminiModel('m').remote
    assert not GeminiModel('m', tier='paid').data_use
    with pytest.raises(ValueError, match='MINIA_GEMINI_TIER'):
        GeminiModel('m', tier='pro')
    for name in ('MINIA_OLLAMA_MODEL', 'MINIA_CLAUDE_MODEL', 'MINIA_GEMINI_TIER', 'MINIA_PROVIDER'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MINIA_GEMINI_MODEL', 'gemini-test')
    models = minia_models(settings.minia())
    assert list(models) == ['gemini'] and models['gemini'].data_use
    monkeypatch.setenv('MINIA_GEMINI_TIER', 'paid')
    assert not minia_models(settings.minia())['gemini'].data_use


def test_the_chunk_carrying_a_refusal_is_never_streamed():
    lines = [f'data: {json.dumps(reply("début ", finish=None))}', f'data: {json.dumps(reply("suite refusée", finish="SAFETY"))}']
    pieces, seen = gemini(lambda request: httpx.Response(200, text='\n\n'.join(lines) + '\n\n')).stream('s', 'u'), []
    with pytest.raises(MiniaError, match='décliné'):
        for piece in pieces:
            seen.append(piece)
    assert seen == ['début '], 'seul le brouillon deja produit est passe ; le portail l efface a l echec'
