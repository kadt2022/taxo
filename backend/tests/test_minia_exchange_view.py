"""Récit TAXO-RECIT-REDUCTION-PAYLOAD-MINIA, R4 : vues de `describe` (B, C), des voisinages (D) et vue stricte des Tuiles
(E), sous `MINIA_EXCHANGE_PROJECTION` (désactivé par défaut).

Principe : la plus petite représentation **suffisante**. Chaque vue est contrôlée sur des réponses réellement servies
par Taxo : aucun champ non classé, et aucune information utile à la décision perdue (`sufficiency.lost` vide).
"""
import copy
import json

import pytest

from app.bootstrap import settings
from app.minia.application import ask as ask_module, exchange_view, sufficiency, tile_view
from test_coverage_bounds import taxo_on_fixture  # noqa: F401  (fixture partagée)
from test_minia_explore import answer, call, statement
from test_minia_general import REGISTER, SERVICE, Scripted, analysis_of
from test_minia_tiles import ask, sent
from test_spring_boot import repository

ROUTE = 'endpoint:GET /orders'


def query(taxo, scan, operation, **arguments):
    response = taxo.client.post(f'{taxo.base}/taxo-query', json={'analysis': scan, 'requests': [
        {'operation': operation, 'max_bytes': 64_000, 'arguments': arguments}]})
    assert response.status_code == 200, response.text
    found, = response.json()['responses']
    assert found['outcome'] == 'OK', found
    return found


def tile_of(taxo, scan, reference, profile):
    response = taxo.client.post(f'{taxo.base}/mip/query', json={
        'expression': 'EXPAND', 'target': {'reference': reference}, 'profile': profile, 'analysis': scan,
        'bounds': {'max_bytes': 16_000}})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(name='served')
def served_fixture(taxo_on):
    """Des réponses réellement servies par Taxo sur le dépôt scénarisé Spring Boot."""
    taxo, _ = taxo_on(repository())
    scan = taxo.analyse()['id']
    return {
        'describe': query(taxo, scan, 'describe'),
        'neighborhood/1': query(taxo, scan, 'get_neighborhood', analysis=scan, root=ROUTE,
                                follow=['HANDLED_BY', 'SERVED_BY', 'MATCHED_BY'], direction='OUTGOING', depth=2),
        'neighborhood/2': query(taxo, scan, 'get_neighborhood', analysis=scan, engine='neighborhood/2', root=ROUTE,
                                steps=[{'relation': relation, 'direction': 'OUTGOING'}
                                       for relation in ('HANDLED_BY', 'SERVED_BY', 'MATCHED_BY', 'AUTHORIZED_BY')],
                                depth=3),
        'tile': tile_of(taxo, scan, ROUTE, 'security/2'),
    }


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


# --- Contrat et suffisance, sur des réponses réelles -------------------------------------------------------------

def test_every_field_taxo_really_serves_is_classified(served):
    assert exchange_view.unclassified_describe(served['describe']) == []
    assert exchange_view.unclassified_neighborhood(served['neighborhood/1']) == []
    assert exchange_view.unclassified_neighborhood(served['neighborhood/2']) == []
    assert tile_view.unclassified(served['tile']) == []


@pytest.mark.parametrize('name, operation, view', [
    ('describe', 'describe', exchange_view.describe_view),
    ('neighborhood/1', 'get_neighborhood', exchange_view.neighborhood_view),
    ('neighborhood/2', 'get_neighborhood', exchange_view.neighborhood_view),
    ('tile', 'get_tile', tile_view.project),
    ('tile', 'get_tile', lambda response: tile_view.project(response, strict=True)),
])
def test_no_view_loses_an_information_useful_to_the_decision(served, name, operation, view):
    response = served[name]
    shown = view(copy.deepcopy(response))
    assert sufficiency.lost(operation, response, shown) == {}
    assert size(shown) < size(response)


def test_the_sufficiency_check_does_catch_a_lost_proof_a_lost_status_or_a_lost_exclusion(served):
    """Le contrôle lui-même : il voit une preuve, un statut ou une couverture perdus."""
    response = served['neighborhood/2']
    shown = exchange_view.neighborhood_view(copy.deepcopy(response))
    without_proof = copy.deepcopy(shown)
    without_proof['items'][0].pop('evidence', None)
    without_proof['items'][0]['evidence_count'] = None
    assert 'facts' in sufficiency.lost('get_neighborhood', response, without_proof)
    deduced = copy.deepcopy(shown)
    deduced['items'][-1]['fact']['status'] = 'OBSERVED' if deduced['items'][-1]['fact']['status'] != 'OBSERVED' else 'X'
    assert 'facts' in sufficiency.lost('get_neighborhood', response, deduced)
    uncovered = {**shown, 'coverage': []}
    assert 'coverage' in sufficiency.lost('get_neighborhood', response, uncovered)


# --- B : le doublon des opérations -------------------------------------------------------------------------------

def test_b_every_operation_removed_from_describe_is_still_offered_or_deliberately_withheld(make_repo, tmp_path):
    model = Scripted(answer(statement('unknown', 'Rien.')))
    ask(make_repo, tmp_path, model)
    message = sent(model, 0)
    describe = message['trajectory'][0]['response']
    listed = {item['operation'] for item in describe['items'] if item.get('kind') == 'operation'}
    offered = {item['operation'] for item in message['operations']}
    assert listed <= offered | ask_module._JUDGING, 'la liste retirée de describe est déjà envoyée à part'
    assert not [item for item in exchange_view.describe_without_operations(describe)['items']
                if item.get('kind') == 'operation']


# --- C : describe condensé -------------------------------------------------------------------------------------

def test_c_describe_keeps_coverage_consent_snapshot_and_what_was_not_sent(served):
    response = served['describe']
    shown = exchange_view.describe_view(copy.deepcopy(response))
    for name in ('coverage', 'consent', 'snapshot', 'not_sent', 'outcome'):
        assert shown[name] == response[name], name
    assert 'items' not in shown
    assert shown['relations'] and shown['families'] and shown['analyzers']
    assert shown['projection']['version'] == exchange_view.VERSION


def test_c_an_unknown_kind_or_field_of_describe_is_never_sent():
    response = {'outcome': 'OK', 'snapshot': {'analysis': 'a'}, 'items': [
        {'kind': 'mystere', 'secret': 's1'}, {'kind': 'family', 'type': 'symbol', 'count': 3, 'interne': 's2'}],
        'nouveau': 's3'}
    shown = exchange_view.describe_view(response)
    text = json.dumps(shown)
    assert 's1' not in text
    assert 's2' not in text
    assert 's3' not in text
    assert shown['projection']['withheld'] == ['items.family.interne', 'items.mystere', 'nouveau']


# --- D : voisinages ----------------------------------------------------------------------------------------------

def test_d_a_neighborhood_keeps_its_page_frontier_and_coverage_and_drops_audit(served):
    response = served['neighborhood/2']
    shown = exchange_view.neighborhood_view(copy.deepcopy(response))
    for name in ('frontier', 'coverage', 'not_sent', 'stop_reason', 'continuation'):
        assert shown[name] == response[name], name
    text = json.dumps(shown, ensure_ascii=False)
    for kept_out in ('sha256:', '"occurrence"', '"produced_by"', '"parameters"', '"facts_revision"', '"engine_version"'):
        assert kept_out not in text, kept_out


# --- E : vue stricte des Tuiles --------------------------------------------------------------------------------

def test_e_the_strict_tile_drops_only_proven_duplicates(served):
    response = served['tile']
    loose, strict = tile_view.project(copy.deepcopy(response)), tile_view.project(copy.deepcopy(response), strict=True)
    assert all('via' not in item for item in strict['facts'])
    assert 'commit' not in strict['snapshot']
    assert 'note' not in strict['projection']
    assert [item['fact'] for item in strict['facts']] == [item['fact'] for item in loose['facts']]
    assert [item.get('evidence') for item in strict['facts']] == [item.get('evidence') for item in loose['facts']]
    assert [item.get('selection') for item in strict['facts']] == [item.get('selection') for item in loose['facts']], \
        'le chemin de sélection reste : il distingue deux chaînes à profondeur 2'
    assert strict['projection']['version'] == tile_view.STRICT_VERSION


def test_e_an_unknown_root_and_a_node_without_fact_stay_said():
    tile = {'outcome': 'OK', 'snapshot': {'analysis': 'a', 'commit': 'c'}, 'root': {'reference': 'x', 'known': False},
            'nodes': [{'reference': 'x', 'expanded': True}, {'reference': 'seul', 'expanded': False}], 'facts': []}
    shown = tile_view.project(tile, strict=True)
    assert shown['root'] == {'reference': 'x', 'known': False}
    assert shown['nodes'] == {'references': ['seul'], 'not_expanded': ['seul']}


# --- Dans une vraie exploration ----------------------------------------------------------------------------------

def test_with_the_setting_the_model_reads_the_views_and_the_verification_is_unchanged(make_repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_TILE_PROJECTION', 'on')
    monkeypatch.setenv('MINIA_EXCHANGE_PROJECTION', 'on')
    model = Scripted(
        lambda message: call('find_references', analysis=analysis_of(message), prefix='CourseController.register',
                             match='NAME'),
        call('get_tile', reference=REGISTER, profile='method-context/1'),
        answer(statement('claim', 'CourseController#register appelle CourseService#register.', REGISTER, 'CALLS',
                         SERVICE)))
    result = ask(make_repo, tmp_path, model)
    message = sent(model, 2)
    describe, tile = message['trajectory'][0]['response'], message['trajectory'][2]['response']
    assert describe['projection']['version'] == exchange_view.VERSION and 'items' not in describe
    assert tile['projection']['version'] == tile_view.STRICT_VERSION
    assert result['statements'][0]['found'] is True, 'la vérification lit Taxo, jamais la vue'
    assert result['usage']['projection'] == (f'{tile_view.STRICT_VERSION} (Tuiles), '
                                             f'{exchange_view.VERSION} (describe, voisinages)')


def test_without_the_setting_nothing_changes(make_repo, tmp_path, monkeypatch):
    monkeypatch.setenv('MINIA_TILE_PROJECTION', 'on')
    monkeypatch.delenv('MINIA_EXCHANGE_PROJECTION', raising=False)
    model = Scripted(answer(statement('unknown', 'Rien.')))
    result = ask(make_repo, tmp_path, model)
    describe = sent(model, 0)['trajectory'][0]['response']
    assert 'items' in describe and 'projection' not in describe
    assert result['usage']['projection'] == tile_view.VERSION


def test_the_setting_accepts_only_on_or_off(monkeypatch):
    monkeypatch.delenv('MINIA_EXCHANGE_PROJECTION', raising=False)
    assert settings.minia_exchange_projection() is False
    assert settings.minia_exchange_projection('on') is True
    with pytest.raises(ValueError, match='MINIA_EXCHANGE_PROJECTION'):
        settings.minia_exchange_projection('parfois')
