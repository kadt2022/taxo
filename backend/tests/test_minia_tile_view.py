"""Récit TAXO-RECIT-REDUCTION-PAYLOAD-MINIA, R2 : la vue condensée d'une Tuile pour le modèle (`vue-minia/1`).

Taxo sert la Tuile entière et Minia la garde entière ; seul le message envoyé au modèle reçoit la vue, par liste blanche,
avant la protection de la demande. Ce qui n'est pas classé n'est jamais transmis ; ce qui change le sens d'une
conclusion (couverture, frontière, limites, statut déduit) l'est toujours.
"""
import copy
import json

import pytest

from app.bootstrap import settings
from app.minia.application import tile_view
from test_minia_explore import answer, call, statement
from test_minia_general import REGISTER, SERVICE, Scripted, analysis_of
from test_minia_tiles import QUESTION, ask, sent

DEDUCED = {
    'ref': 'F2', 'evidence_count': 1, 'identity': 'sha256:' + 'a' * 64, 'occurrence': 'oW' + 'b' * 98,
    'via': {'from': 'endpoint:GET /x', 'relation': 'MATCHED_BY', 'direction': 'OUTGOING'}, 'level': 1,
    'revisit': False, 'selection': {'rule': 'route-rule', 'path': ['F2']},
    'evidence': [{'path': 'src/Security.java', 'line_start': 22, 'line_end': 23, 'symbol': 'symbol:java:a.S#c()',
                  'method': 'java.spring-security.request-matcher'}],
    'fact': {'kind': 'ASSERTION', 'subject': 'endpoint:GET /x', 'relation': 'MATCHED_BY', 'object': 'route-pattern:/**',
             'qualifiers': {'filter_chain': 'symbol:java:a.S#c()'}, 'contract_version': 1, 'status': 'INFERRED',
             'validity': 'VALID', 'snapshot': {'repository': 'r', 'commit': 'c' * 40, 'mode': 'COMMIT'},
             'produced_by': {'producer_type': 'EVALUATOR', 'producer_id': 'taxo.spring-security',
                             'producer_version': '0.6.0', 'execution_id': 'exec-123', 'catalog_id': 'spring-security',
                             'catalog_version': '5'},
             'derivation': {'premises': ['HANDLED_BY : endpoint:GET /x -> symbol:java:a.C#x()'],
                            'rule': 'spring-security.first-matching-pattern',
                            'counter_examples_checked': ['ligne 21 : /y -> authenticated() : ne correspond pas'],
                            'known_gaps': ['antMatchers : variantes non modélisées']}},
}
TILE = {
    'mip': 'mip/0.1', 'expression': 'EXPAND', 'outcome': 'OK', 'snapshot': {'analysis': 'an-1', 'commit': 'c' * 40},
    'root': {'reference': 'endpoint:GET /x', 'known': True},
    'nodes': [{'reference': 'endpoint:GET /x', 'level': 0, 'known': True, 'expanded': True},
              {'reference': 'route-pattern:/**', 'level': 1, 'known': True, 'expanded': False}],
    'facts': [DEDUCED],
    'coverage': [{'producer': 'taxo.spring-security', 'status': 'PARTIAL',
                  'coverage': [{'coverage_type': 'NOT_INTERPRETED', 'count': 1, 'subjects': ['endpoint:GET /x']}]}],
    'frontier': [{'nature': 'CONTEXT', 'relation': 'CONFIGURES', 'reason': 'NOT_IN_PROFILE'}],
    'bounds': {'requested': {'max_bytes': 16000}}, 'stop_reason': 'BUDGET', 'truncated': True,
    'not_sent': [{'what': 'facts', 'count': 2, 'reason': 'BUDGET'}], 'continuation': 'cursor-secret',
    'wire': {'protocol': 'taxo-query/1'}, 'classification': {'version': 'tile-classification/1'},
    'profile': {'id': 'security/2', 'anchors': ['endpoint'], 'steps': [], 'limits': ['Ne démontre pas la protection.']},
    'disclosure': {'version': 'tile-disclosure/1', 'restrictions': []}, 'bytes': 9999,
}


def shown(tile=TILE):
    return json.dumps(tile_view.project(copy.deepcopy(tile)), ensure_ascii=False)


# --- SEC-04 : ce qui sert l'audit reste dans Taxo ------------------------------------------------------------

def test_internal_handles_provenance_and_audit_never_reach_the_model():
    text = shown()
    for kept_out in ('sha256:', 'oW', 'exec-123', 'producer_version', 'cursor-secret', 'tile-classification/1',
                     'taxo-query/1', '"contract_version"', '"bytes"'):
        assert kept_out not in text, kept_out


def test_the_short_reference_and_the_triple_are_sent_unchanged():
    [fact] = tile_view.project(copy.deepcopy(TILE))['facts']
    assert fact['ref'] == 'F2'
    assert (fact['fact']['subject'], fact['fact']['relation'], fact['fact']['object']) == (
        'endpoint:GET /x', 'MATCHED_BY', 'route-pattern:/**')
    assert fact['fact']['qualifiers'] == {'filter_chain': 'symbol:java:a.S#c()'}, 'la chaîne de filtres reste dite'
    assert fact['evidence'] == ['src/Security.java:22-23 (java.spring-security.request-matcher)']


# --- SEC-05 / I-07 : le sens d'une conclusion ne change pas --------------------------------------------------

def test_a_deduced_fact_stays_deduced_with_its_rule_premises_and_known_gaps():
    derivation = tile_view.project(copy.deepcopy(TILE))['facts'][0]['fact']
    assert derivation['status'] == 'INFERRED'
    assert derivation['derivation']['rule'] == 'spring-security.first-matching-pattern'
    assert derivation['derivation']['premises'] == DEDUCED['fact']['derivation']['premises']
    assert derivation['derivation']['known_gaps'] == ['antMatchers : variantes non modélisées']
    assert derivation['derivation']['counter_examples'] == 1


def test_coverage_frontier_truncation_and_profile_limits_are_kept():
    view = tile_view.project(copy.deepcopy(TILE))
    assert view['coverage'] == TILE['coverage']
    assert view['frontier'] == TILE['frontier']
    assert (view['truncated'], view['stop_reason'], view['not_sent']) == (True, 'BUDGET', TILE['not_sent'])
    assert view['profile'] == {'id': 'security/2', 'limits': ['Ne démontre pas la protection.']}
    assert view['nodes'] == {'references': ['endpoint:GET /x', 'route-pattern:/**'],
                             'not_expanded': ['route-pattern:/**']}
    assert view['snapshot'] == TILE['snapshot'], 'l’analyse sert d’argument aux opérations suivantes'


def test_a_refused_tile_goes_through_the_same_whitelist():
    error = {'code': 'INVALID_ARGUMENT', 'message': 'référence non reçue'}
    refusal = {'mip': 'mip/0.1', 'expression': 'EXPAND', 'outcome': 'ERROR', 'snapshot': {'analysis': 'an-1'},
               'error': error, 'bytes': 120, 'inattendu': 'x'}
    view = tile_view.project(refusal)
    assert view['error'] == error
    assert view['outcome'] == 'ERROR'
    assert 'mip' not in view
    assert 'bytes' not in view
    assert view['projection']['withheld'] == ['inattendu']


def test_a_compacted_summary_or_a_bare_resend_is_left_to_the_trajectory():
    assert not tile_view.projectable({'outcome': 'OK', 'compacted': True, 'references': ['symbol:java:a.B']})
    assert not tile_view.projectable({'outcome': 'OK', 'reused': True, 'note': 'tour 3'})
    resent = {**copy.deepcopy(TILE), 'reused': True, 'note': 'redonnée'}
    assert tile_view.projectable(resent)
    view = tile_view.project(resent)
    assert (view['reused'], view['note']) == (True, 'redonnée')
    assert 'withheld' not in view['projection']


# --- SEC-02 / SEC-08 : liste blanche, échec sûr ----------------------------------------------------------------

def test_an_unknown_field_is_never_sent_and_is_named_as_withheld():
    tile = copy.deepcopy(TILE)
    tile['nouveau_champ'] = 'valeur-inconnue'
    tile['facts'][0]['marque'] = 'interne'
    tile['facts'][0]['fact']['secret_audit'] = 'xyz'
    view = tile_view.project(tile)
    text = json.dumps(view, ensure_ascii=False)
    assert 'valeur-inconnue' not in text
    assert 'interne' not in text
    assert 'xyz' not in text
    assert view['projection']['withheld'] == ['facts.fact.secret_audit', 'facts.marque', 'nouveau_champ']
    assert view['projection']['version'] == tile_view.VERSION


def test_the_contract_classifies_every_field_of_a_real_tile(make_repo, tmp_path, monkeypatch):
    """Le test de contrat : une Tuile réellement servie par Taxo ne porte aucun champ que la table ignore."""
    monkeypatch.setenv('MINIA_TILE_PROJECTION', 'on')
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        answer(statement('claim', 'CourseController#register appelle CourseService#register.', REGISTER, 'CALLS',
                         SERVICE)))
    ask(make_repo, tmp_path, model)
    # La Tuile entière, telle que Taxo l'a servie à Minia : la table doit en classer chaque champ.
    assert _FULL['tile']['outcome'] == 'OK'
    assert tile_view.unclassified(_FULL['tile']) == []


_FULL = {}


@pytest.fixture(autouse=True)
def _capture_tiles(monkeypatch):
    """Garde la Tuile entière servie à Minia, pour le test de contrat."""
    from app.minia.application import tiles
    original = tiles._sized

    def keep(tile):
        sized = original(tile)
        _FULL['tile'] = sized
        return sized
    monkeypatch.setattr(tiles, '_sized', keep)
    yield
    _FULL.clear()


# --- Dans une vraie exploration ---------------------------------------------------------------------------------

def test_with_the_projection_the_model_reads_the_view_and_minia_keeps_the_whole_tile(make_repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_TILE_PROJECTION', 'on')
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        answer(statement('claim', 'CourseController#register appelle CourseService#register.', REGISTER, 'CALLS',
                         SERVICE)))
    result = ask(make_repo, tmp_path, model)
    tile = sent(model, 2)['trajectory'][2]['response']
    assert tile['projection']['version'] == tile_view.VERSION
    assert all('occurrence' not in item and 'identity' not in item for item in tile['facts'])
    assert result['statements'][0]['found'] is True, 'la vérification lit Taxo, jamais la vue'
    assert result['trajectory'][2]['bytes'] == _FULL['tile']['bytes'], 'la trajectoire garde la taille servie'
    assert result['usage']['projection'] == tile_view.VERSION


def test_without_the_setting_the_model_reads_the_whole_tile(make_repo, tmp_path, monkeypatch):
    monkeypatch.delenv('MINIA_TILE_PROJECTION', raising=False)
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        answer(statement('unknown', 'Rien de plus.')))
    result = ask(make_repo, tmp_path, model)
    tile = sent(model, 2)['trajectory'][2]['response']
    assert 'projection' not in tile
    assert all('occurrence' in item for item in tile['facts'])
    assert result['usage']['projection'] is None


def test_the_setting_accepts_only_on_or_off(monkeypatch):
    monkeypatch.delenv('MINIA_TILE_PROJECTION', raising=False)
    assert settings.minia_tile_projection() is False
    assert settings.minia_tile_projection('on') is True
    with pytest.raises(ValueError, match='MINIA_TILE_PROJECTION'):
        settings.minia_tile_projection('peut-être')


def test_the_view_is_smaller_than_the_tile():
    full = len(json.dumps(TILE, ensure_ascii=False))
    assert len(shown()) < full


def test_a_fallback_after_a_projected_tile_still_says_the_projection(make_repo, tmp_path, monkeypatch):
    """L'exploration se replie (réponse illisible) après une Tuile projetée : le relevé dit toujours la vue appliquée."""
    from test_minia_general import packet_answer
    monkeypatch.setenv('MINIA_TILE_PROJECTION', 'on')
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        'pas du json', packet_answer())
    result = ask(make_repo, tmp_path, model)
    assert result['mode'] == 'paquet'
    assert result['usage']['projection'] == tile_view.VERSION
