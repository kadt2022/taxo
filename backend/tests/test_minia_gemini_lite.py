"""Un second modèle Gemini à côté du premier : même adaptateur, même clé, même contrat ; seuls l'identifiant du
fournisseur et le modèle changent. Le fournisseur Gemini existant ne change pas."""
import json

import httpx

from app.bootstrap import settings
from app.bootstrap.application import minia_models
from app.minia.infrastructure.gemini import GeminiLiteModel, GeminiModel

ANSWER = '{"cited": [], "answer": "Rien.", "unknown": ""}'


def answered(request):
    body = {'candidates': [{'content': {'parts': [{'text': ANSWER}]}, 'finishReason': 'STOP'}]}
    return httpx.Response(200, json=body)


def test_both_gemini_models_are_offered_side_by_side(monkeypatch):
    monkeypatch.setenv('MINIA_GEMINI_MODEL', 'gemini-3.5-flash')
    monkeypatch.setenv('MINIA_GEMINI_LITE_MODEL', 'gemini-3.1-flash-lite')
    models = minia_models(settings.minia())
    assert {'gemini', 'gemini-lite'} <= set(models)
    assert (models['gemini'].provider, models['gemini'].model_name) == ('gemini', 'gemini-3.5-flash')
    assert (models['gemini-lite'].provider, models['gemini-lite'].model_name) == ('gemini-lite', 'gemini-3.1-flash-lite')


def test_the_lite_model_is_off_without_its_own_setting(monkeypatch):
    monkeypatch.setenv('MINIA_GEMINI_MODEL', 'gemini-3.5-flash')
    monkeypatch.delenv('MINIA_GEMINI_LITE_MODEL', raising=False)
    assert 'gemini-lite' not in minia_models(settings.minia())


def test_the_lite_model_alone_does_not_enable_the_first_one(monkeypatch):
    monkeypatch.delenv('MINIA_GEMINI_MODEL', raising=False)
    monkeypatch.setenv('MINIA_GEMINI_LITE_MODEL', 'gemini-3.1-flash-lite')
    models = minia_models(settings.minia())
    assert 'gemini' not in models
    assert 'gemini-lite' in models


def test_the_lite_model_is_the_same_adapter_with_the_same_protections():
    lite = GeminiLiteModel('gemini-3.1-flash-lite')
    assert isinstance(lite, GeminiModel)
    assert lite.remote is True
    assert lite.explores is True
    assert lite.data_use is True, 'niveau gratuit : les données peuvent servir à Google, le portail le dit'
    assert GeminiLiteModel('gemini-3.1-flash-lite', tier='paid').data_use is False


def test_the_lite_model_asks_its_own_model_with_the_key_in_a_header():
    seen = []

    def handler(request):
        seen.append(request)
        return answered(request)

    model = GeminiLiteModel('gemini-3.1-flash-lite', api_key='cle-test', transport=httpx.MockTransport(handler))
    assert model.complete('consignes', 'faits') == ANSWER
    request = seen[0]
    assert 'gemini-3.1-flash-lite' in str(request.url)
    assert request.headers['x-goog-api-key'] == 'cle-test'
    assert 'cle-test' not in str(request.url)
    assert json.loads(request.content)['generationConfig']['responseMimeType'] == 'application/json'


def test_the_first_gemini_model_keeps_its_identifier():
    assert GeminiModel.provider == 'gemini'
    assert GeminiLiteModel.provider == 'gemini-lite'
