"""Pour les essais, une demande fixe son nombre d'opérations et le budget de son échange, dans les bornes du serveur
(MINIA_MAX_CALLS, MINIA_EXCHANGE_BYTES) ; sans valeur, ce sont les réglages du serveur. Le statut les propose au
portail, et la réponse dit le budget réellement appliqué."""
import json

import pytest

from app.bootstrap import settings
from app.minia.application.ask import (MAX_ALLOWED_CALLS, MAX_EXCHANGE_SETTING, MIN_EXCHANGE_SETTING, AskMinia)
from app.minia.domain.errors import MiniaError
from test_minia_explore import ScriptedModel, answer, completed, repo_fixture, statement  # noqa: F401


def ask(repo, tmp_path, model, **limits):
    from fastapi.testclient import TestClient
    from app.bootstrap.database import Base
    from app.main import create_app
    app = create_app(f'sqlite:///{tmp_path / "limits.db"}', [repo], minia=model)
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Essais', 'path': str(repo)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        status = client.get('/api/minia/status').json()
        stream = client.post(f'/api/projects/{project["id"]}/ask/stream',
                             json={'question': 'Que change le dernier commit ?', **limits})
        if stream.status_code != 200:
            return status, stream
        events = [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                  for block in stream.text.strip().split('\n\n') if not block.startswith(':')]
    return status, completed(events)


def test_the_server_budget_is_read_from_its_setting(monkeypatch):
    monkeypatch.delenv('MINIA_EXCHANGE_BYTES', raising=False)
    assert settings.minia_exchange_bytes() == 64_000
    monkeypatch.setenv('MINIA_EXCHANGE_BYTES', '120000')
    assert settings.minia_exchange_bytes() == 120_000


@pytest.mark.parametrize('limits', [{'max_calls': 0}, {'max_calls': MAX_ALLOWED_CALLS + 1},
                                    {'exchange_bytes': MIN_EXCHANGE_SETTING - 1},
                                    {'exchange_bytes': MAX_EXCHANGE_SETTING + 1}])
def test_server_settings_out_of_bounds_are_refused_at_start(limits):
    with pytest.raises(ValueError):
        AskMinia(None, {}, None, **limits)


def test_the_status_offers_the_limits_and_their_bounds(repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_MAX_CALLS', '12')
    status, _ = ask(repo[0], tmp_path, ScriptedModel(answer(statement('unknown', 'Rien.'))))
    assert status['limits'] == {'max_calls': 12, 'max_calls_range': [1, MAX_ALLOWED_CALLS], 'max_bytes': 64_000,
                                'max_bytes_range': [MIN_EXCHANGE_SETTING, MAX_EXCHANGE_SETTING]}


def test_a_request_sets_its_own_operations_and_budget(repo, tmp_path):
    model = ScriptedModel(answer(statement('unknown', 'Rien.')))
    _, result = ask(repo[0], tmp_path, model, max_calls=5, max_bytes=100_000)
    assert json.loads(model.calls[0][1])['calls_left'] == 5
    assert result['budget']['max_bytes'] == 100_000


def test_without_values_the_server_settings_apply(repo, tmp_path):
    model = ScriptedModel(answer(statement('unknown', 'Rien.')))
    _, result = ask(repo[0], tmp_path, model)
    assert json.loads(model.calls[0][1])['calls_left'] == 8
    assert result['budget']['max_bytes'] == 64_000


@pytest.mark.parametrize('limits', [{'max_calls': 0}, {'max_calls': MAX_ALLOWED_CALLS + 1},
                                    {'max_bytes': 1000}, {'max_bytes': MAX_EXCHANGE_SETTING + 1},
                                    {'max_calls': True}, {'max_calls': '12'}, {'max_bytes': 64000.5}])
def test_a_request_out_of_bounds_is_refused_before_any_model_call(repo, tmp_path, limits):
    model = ScriptedModel()
    _, refused = ask(repo[0], tmp_path, model, **limits)
    assert refused.status_code == 422 and model.calls == []


def test_a_limited_minia_leaves_the_server_minia_unchanged():
    minia = AskMinia(None, {}, None)
    chosen = minia.limited(max_calls=3, max_bytes=50_000)
    assert (chosen.max_calls, chosen.exchange_bytes) == (3, 50_000)
    assert (minia.max_calls, minia.exchange_bytes) == (8, 64_000)
    assert minia.limited() is minia
    with pytest.raises(MiniaError):
        minia.limited(max_calls=True)
