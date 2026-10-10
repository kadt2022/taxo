"""Tuile adaptative : des profils fermés, déclarés et versionnés, servis par le moteur existant.

Récit TAXO-MIP-ADT-01, PR A ; ARCHITECTURE § 9.5. La vérité vient du dépôt scénarisé des appels Java
(`test_java_calls.fixture_files`), comme pour `test_mip` : `CourseController#register(String)` traite `POST
/api/courses`, appelle `CourseController#audit()` et `CourseService#register(String)`, et sa classe le contient.
"""
import json

import pytest

from app.facts.domain.fact import RELATIONS
from app.mip.domain.profiles import CALLS, METHOD_CONTEXT, PROFILES
from app.mip.domain.query import EXPAND, MipError, read_query
from test_coverage_bounds import taxo_on_fixture  # noqa: F401  (fixture partagée)
from test_java_calls import fixture_files
from test_mip import CONTROLLER, REGISTER, SERVICE, ask, calls, expand

AUDIT = f'{CONTROLLER}#audit()'


def profiled(reference, profile, **fields):
    return {'expression': EXPAND, 'target': {'reference': reference}, 'profile': profile, **fields}


def without_selection(facts):
    return [{key: value for key, value in fact.items() if key != 'selection'} for fact in facts]


@pytest.fixture(name='courses')
def courses_fixture(taxo_on):
    taxo, _ = taxo_on(fixture_files())
    return taxo, taxo.analyse()['id']


@pytest.fixture(name='route')
def route_fixture(courses):
    """La route traitée par `register`, telle que la Maille la nomme : elle n'est jamais devinée par le test."""
    taxo, _ = courses
    tile = ask(taxo, expand(REGISTER, relations=('HANDLED_BY',), direction='INCOMING'))
    (endpoint, _, _), = calls(tile)
    return endpoint


# --- Les manifestes ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('profile', sorted(PROFILES.values(), key=lambda item: item.identifier),
                         ids=lambda item: item.identifier)
def test_a_profile_is_a_closed_manifest_of_the_relation_vocabulary(profile):
    steps = [(step.relation, step.direction) for step in profile.steps]
    assert len(set(steps)) == len(steps), 'un pas une seule fois : sa règle est sans ambiguïté'
    assert {step.relation for step in profile.steps} <= set(RELATIONS)
    assert len({step.rule for step in profile.steps}) == len(profile.steps)
    assert profile.version == 1 and profile.identifier == f'{profile.name}/1' and profile.anchors
    manifest = profile.manifest()
    assert manifest['id'] == profile.identifier and len(manifest['steps']) == len(profile.steps)


def test_the_profiles_documented_by_the_architecture_are_the_served_ones():
    assert set(PROFILES) == {'method-context/1', 'calls/1', 'structure/1', 'security/1'}
    assert [step.relation for step in PROFILES['security/1'].steps] == [
        'HANDLED_BY', 'SERVED_BY', 'MATCHED_BY', 'AUTHORIZED_BY', 'PROTECTED_BY']


# --- La requête : un profil nommé, jamais improvisé -----------------------------------------------------------

@pytest.mark.parametrize('payload', [
    profiled(REGISTER, 'method-context'),
    profiled(REGISTER, 'method-context/9'),
    profiled(REGISTER, 'Est-ce protégé ?'),
    profiled(REGISTER, ['calls/1']),
    profiled(REGISTER, 'calls/1', relations=['CALLS']),
    profiled(REGISTER, 'calls/1', direction='OUTGOING'),
    profiled(REGISTER, 'security/1'),
    profiled('module:demo', 'method-context/1'),
])
def test_an_unknown_profile_or_anchor_is_refused_never_interpreted(payload):
    with pytest.raises(MipError) as refused:
        read_query(payload)
    assert refused.value.code == 'INVALID_ARGUMENT'


def test_project_stays_refused_with_a_profile():
    with pytest.raises(MipError) as refused:
        read_query({**profiled(REGISTER, 'calls/1'), 'expression': 'PROJECT'})
    assert refused.value.code == 'NOT_AVAILABLE'


def test_a_profiled_query_carries_the_manifest_and_no_free_relations():
    query = read_query(profiled(REGISTER, 'method-context/1', bounds={'depth': 2}))
    assert query.profile is METHOD_CONTEXT and (query.relations, query.direction) == ((), None)
    assert query.bounds == {'depth': 2}


# --- La Tuile adaptative -------------------------------------------------------------------------------------

def test_the_same_profile_on_the_same_analysis_gives_the_same_tile(courses):
    """A1 : mêmes faits, même ordre."""
    taxo, scan = courses
    first = ask(taxo, profiled(REGISTER, 'method-context/1', analysis=scan))
    second = ask(taxo, profiled(REGISTER, 'method-context/1', analysis=scan))
    assert first == second and first['outcome'] == 'OK'


def test_a_profiled_tile_is_replayed_exactly_by_its_resolved_parameters(courses):
    """§ 9.5, règle 2 : la Tuile rend ses paramètres résolus ; rejoués en mode explicite, ils donnent la même
    sélection, dans le même ordre, du même moteur."""
    taxo, scan = courses
    tile = ask(taxo, profiled(REGISTER, 'method-context/1', analysis=scan, bounds={'max_bytes': 32_000}))
    assert not tile['truncated']
    resolved = tile['profile']['resolved']
    assert resolved['steps'] == [{'relation': step.relation, 'direction': step.direction}
                                 for step in METHOD_CONTEXT.steps]
    assert resolved['depth'] == METHOD_CONTEXT.depth
    arguments = {'analysis': scan, 'engine': 'neighborhood/2', 'root': REGISTER, 'steps': resolved['steps'],
                 'depth': resolved['depth'], 'evidence': 'SUMMARY'}
    response = taxo.client.post(f'{taxo.base}/taxo-query', json={'analysis': scan, 'requests': [
        {'operation': 'get_neighborhood', 'arguments': arguments, 'max_bytes': 32_000}]})
    wire, = response.json()['responses']
    assert without_selection(tile['facts']) == wire['items']
    assert tile['nodes'] == wire['node_details'] and tile['frontier'] == wire['frontier']


def test_each_fact_says_which_rule_kept_it_and_relations_keep_their_orientation(courses):
    """A2 et § 9.5, règle 4 : un appelant est rendu tel que la Maille l'écrit (appelant → appelé), retenu par la
    règle des appelants ; la classe est la propriétaire, par `CONTAINS` entrant."""
    taxo, _ = courses
    tile = ask(taxo, profiled(SERVICE, 'method-context/1'))
    by_rule = {}
    for fact in tile['facts']:
        by_rule.setdefault(fact['selection']['rule'], []).append(
            (fact['fact']['subject'], fact['fact']['relation'], fact['fact']['object']))
    assert by_rule['callers'] == [(REGISTER, 'CALLS', SERVICE)]
    owner, = by_rule['owner']
    assert owner == ('symbol:java:com.example.demo.service.CourseService', 'CONTAINS', SERVICE)
    assert all(fact['selection']['path'] == [fact['ref']] for fact in tile['facts']), 'un niveau : un fait'


def test_a_fact_reached_through_a_handler_carries_its_whole_path(courses, route):
    taxo, _ = courses
    tile = ask(taxo, profiled(route, 'calls/1'))
    handler, = [fact for fact in tile['facts'] if fact['selection']['rule'] == 'handler']
    assert (handler['fact']['subject'], handler['fact']['object']) == (route, REGISTER)
    assert handler['selection']['path'] == [handler['ref']]
    callees = [fact for fact in tile['facts'] if fact['selection']['rule'] == 'callees']
    assert {fact['fact']['object'] for fact in callees} >= {AUDIT, SERVICE}
    assert all(fact['selection']['path'] == [handler['ref'], fact['ref']] for fact in callees)
    assert all(fact['level'] == 2 for fact in callees)


def test_a_relation_without_producer_is_a_context_frontier_never_an_absence(courses):
    """A4, A5 : `DISPATCHES_TO` n'a pas de producteur ; le profil ne la promet pas, la Tuile le dit."""
    taxo, _ = courses
    tile = ask(taxo, profiled(REGISTER, 'calls/1'))
    assert {'nature': 'CONTEXT', 'node': REGISTER, 'relation': 'DISPATCHES_TO', 'reason': 'NO_ANALYZER',
            'count': {'kind': 'UNKNOWN'}} in tile['frontier']
    assert not any(fact['fact']['relation'] == 'DISPATCHES_TO' for fact in tile['facts'])


def test_a_partially_produced_relation_is_declared_by_the_profile_limits(courses):
    """A5 : `ANNOTATED_WITH` a un producteur qui ne relève pas toutes les annotations ; le moteur ne peut pas le
    savoir, le manifeste le dit."""
    taxo, _ = courses
    tile = ask(taxo, profiled(REGISTER, 'method-context/1'))
    assert tile['profile']['id'] == 'method-context/1'
    assert any(limit.startswith('ANNOTATED_WITH') for limit in tile['profile']['limits'])


def test_a_requested_depth_replaces_the_profile_depth_and_is_rendered(courses):
    taxo, _ = courses
    tile = ask(taxo, profiled(REGISTER, 'calls/1', bounds={'depth': 1}))
    assert tile['profile']['depth'] == CALLS.depth and tile['profile']['resolved']['depth'] == 1
    assert {fact['level'] for fact in tile['facts']} == {1}


def test_a_query_without_profile_is_unchanged(courses):
    """MIP 0.1 `EXPAND` reste compatible : ni manifeste, ni sélection ajoutés à une requête explicite."""
    taxo, _ = courses
    tile = ask(taxo, expand(REGISTER))
    assert 'profile' not in tile and all('selection' not in fact for fact in tile['facts'])


@pytest.mark.parametrize('budget', [None, 5_000, 6_000])
def test_a_profiled_tile_fits_the_consumer_budget_rules_and_paths_included(courses, route, budget):
    """Le budget d'octets vaut pour la Tuile reçue : le moteur est redemandé une fois avec moins de place si ce que
    le profil ajoute la ferait dépasser. Ce qui ne tient pas est coupé et le dit, jamais tu."""
    taxo, _ = courses
    tile = ask(taxo, profiled(route, 'calls/1', **({'bounds': {'max_bytes': budget}} if budget else {})))
    assert tile['outcome'] == 'OK', tile
    applied = tile['bounds']['applied']['max_bytes']
    assert applied == (budget or 8_000)
    assert len(json.dumps(tile, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) <= applied
    assert all(fact['selection']['path'] is not None for fact in tile['facts'])


def test_a_budget_too_small_for_the_engine_envelope_is_refused_never_emptied(courses, route):
    taxo, _ = courses
    tile = ask(taxo, profiled(route, 'calls/1', bounds={'max_bytes': 1_000}))
    assert (tile['outcome'], tile['error']['code']) == ('ERROR', 'BUDGET_EXHAUSTED')


def test_a_tile_that_the_profile_would_push_over_budget_is_served_by_a_smaller_engine_request(courses):
    """Au budget par défaut, règles et chemins ne tiennent pas avec tout ce que le moteur rend pour `register` : la
    Tuile est redemandée avec moins de place, coupée par les octets, et le dit."""
    taxo, _ = courses
    tile = ask(taxo, profiled(REGISTER, 'method-context/1'))
    assert tile['outcome'] == 'OK' and tile['bounds']['applied']['max_bytes'] == 8_000
    assert len(json.dumps(tile, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) <= 8_000
    assert tile['truncated'] and (tile['stop_reason'] == 'BYTES' or tile['not_sent'])
