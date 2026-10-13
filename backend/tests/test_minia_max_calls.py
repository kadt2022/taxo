"""La limite des opérations que Minia choisit dans une exploration est réglable (MINIA_MAX_CALLS, défaut 8, de 1 à
MAX_ALLOWED_CALLS). Les vérifications d'affirmations viennent en plus, dans la limite de l'échange avec Taxo : une
affirmation qui n'y tient plus est dite non vérifiée, jamais tue ni confirmée."""
import json

import pytest

from app.bootstrap import settings
from app.minia.application.ask import MAX_ALLOWED_CALLS, MAX_CALLS, AskMinia
from app.protocol.application.exchange import MAX_OPERATIONS
from test_minia_explore import ScriptedModel, answer, call, completed, repo_fixture, run, statement  # noqa: F401


def test_the_default_limit_is_unchanged(monkeypatch):
    monkeypatch.delenv('MINIA_MAX_CALLS', raising=False)
    assert settings.minia_max_calls() == MAX_CALLS == 8


def test_the_limit_is_read_from_the_setting(monkeypatch):
    monkeypatch.setenv('MINIA_MAX_CALLS', '12')
    assert settings.minia_max_calls() == 12


@pytest.mark.parametrize('value', [0, MAX_ALLOWED_CALLS + 1])
def test_a_limit_out_of_bounds_is_refused_at_start(value):
    with pytest.raises(ValueError, match='MINIA_MAX_CALLS'):
        AskMinia(None, {}, None, max_calls=value)


def test_the_model_is_given_the_configured_limit(repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_MAX_CALLS', '12')
    model = ScriptedModel(answer(statement('unknown', 'Rien.')))
    run(repo[0], tmp_path, model)
    assert json.loads(model.calls[0][1])['calls_left'] == 12


def test_the_exploration_stops_at_the_configured_limit(repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_MAX_CALLS', '10')
    replies = [call('find_facts', subject=f'file:f{index}.txt') for index in range(10)]
    model = ScriptedModel(*replies, answer(statement('unknown', 'Rien de plus.')))
    result = completed(run(repo[0], tmp_path, model))
    assert result['mode'] == 'exploration'
    assert len(result['trajectory']) == 1 + 10
    assert json.loads(model.calls[-1][1])['calls_left'] == 0


def test_claims_beyond_the_exchange_limit_are_said_unverified(repo, tmp_path, monkeypatch):
    repo, sha = repo
    monkeypatch.setenv('MINIA_MAX_CALLS', str(MAX_ALLOWED_CALLS))
    replies = [call('find_facts', subject=f'file:f{index}.txt') for index in range(MAX_ALLOWED_CALLS)]
    claims = [statement('claim', f'Affirmation {index}.', f'commit:{sha}', 'CHANGES', 'file:src/app.txt')
              for index in range(6)]
    model = ScriptedModel(*replies, answer(*claims))
    result = completed(run(repo, tmp_path, model))
    room = MAX_OPERATIONS - 1 - MAX_ALLOWED_CALLS
    found = [item['found'] for item in result['statements']]
    assert found[:room] == [True] * room
    assert found[room:] == [None] * (6 - room)
    assert all(item['error']['code'] == 'NOT_VERIFIED' and 'limite' in item['error']['message']
               for item in result['statements'][room:])
