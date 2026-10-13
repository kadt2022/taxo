"""La trajectoire compacte (MINIA_COMPACT_AFTER) : au-delà des N dernières réponses, celles envoyées au modèle sont
résumées (références apportées, taille) ; le code lu reste entier ; une demande répétée rend la réponse entière, sans
appel à Taxo. Désactivée par défaut : rien ne change sans le réglage."""
import json

import pytest

from app.bootstrap import settings
from app.minia.application.ask import MAX_COMPACT_AFTER, AskMinia
from test_minia_explore import answer, call, statement
from test_minia_general import Scripted
from test_minia_source_reading import FIND, ask, found, sent

DONE = answer(statement('unknown', 'Rien de plus.'))


def steps(model, turn):
    return sent(model, turn)['trajectory']


def test_the_setting_is_off_by_default(monkeypatch):
    monkeypatch.delenv('MINIA_COMPACT_AFTER', raising=False)
    assert settings.minia_compact_after() == 0


@pytest.mark.parametrize('value', [-1, MAX_COMPACT_AFTER + 1])
def test_a_setting_out_of_bounds_is_refused_at_start(value):
    with pytest.raises(ValueError, match='MINIA_COMPACT_AFTER'):
        AskMinia(None, {}, None, compact_after=value)


def test_without_the_setting_every_response_stays_whole(make_repo, tmp_path, monkeypatch):
    monkeypatch.delenv('MINIA_COMPACT_AFTER', raising=False)
    model = Scripted(found, call('get_tile', reference=FIND, profile='method-context/1'), DONE)
    ask(make_repo, tmp_path, model)
    assert not any(item['response'].get('compacted') for item in steps(model, 2))


def test_older_responses_are_summarised_with_their_references(make_repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_COMPACT_AFTER', '1')
    model = Scripted(found, call('get_tile', reference=FIND, profile='method-context/1'), DONE)
    ask(make_repo, tmp_path, model)
    describe, search, tile = steps(model, 2)
    assert describe['response']['compacted'] and search['response']['compacted']
    assert FIND in search['response']['references'], 'ce que la recherche a rendu reste dit'
    assert describe['response']['snapshot']['analysis'], 'l’analyse reste nommée pour les opérations suivantes'
    assert 'items' not in search['response']
    assert not tile['response'].get('compacted'), 'la dernière réponse reste entière'


def test_code_read_is_never_summarised(make_repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_COMPACT_AFTER', '1')
    model = Scripted(found, call('get_source', reference=FIND),
                     call('get_tile', reference=FIND, profile='method-context/1'), DONE)
    ask(make_repo, tmp_path, model)
    piece = next(item for item in steps(model, 3) if item['operation'] == 'get_source')
    assert not piece['response'].get('compacted') and piece['response']['items'][0]['text']


def test_a_summarised_reference_stays_received_and_readable(make_repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_COMPACT_AFTER', '1')
    model = Scripted(found, call('get_tile', reference=FIND, profile='method-context/1'),
                     call('get_source', reference=FIND), DONE)
    result = ask(make_repo, tmp_path, model)
    assert result['trajectory'][-1]['operation'] == 'get_source'
    assert result['trajectory'][-1]['outcome'] == 'OK'


def test_asking_again_gives_the_whole_response_without_asking_taxo(make_repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_COMPACT_AFTER', '1')
    model = Scripted(found, call('get_tile', reference=FIND, profile='method-context/1'), found, DONE)
    result = ask(make_repo, tmp_path, model)
    again = steps(model, 3)[-1]
    assert again['response'].get('reused') and again['response']['items'], 'la réponse entière, de nouveau'
    assert result['trajectory'][3]['reused'] and result['trajectory'][3]['bytes'] == 0, 'rien redemandé à Taxo'


def test_compaction_reduces_what_the_model_receives(make_repo, tmp_path, monkeypatch):
    sizes = {}
    for setting in ('0', '1'):
        monkeypatch.setenv('MINIA_COMPACT_AFTER', setting)
        model = Scripted(found, call('get_tile', reference=FIND, profile='method-context/1'), DONE)
        (tmp_path / setting).mkdir()
        ask(make_repo, tmp_path / setting, model)
        sizes[setting] = len(json.dumps(steps(model, 2)))
    assert sizes['1'] < sizes['0']
