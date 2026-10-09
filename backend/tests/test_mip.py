"""MIP 0.1 : une Tuile bornée servie sans modèle de langage, par un adaptateur sur `taxo-query/1`.

Récit TAXO-01N / MIP-01 § 4. La vérité est écrite à la main à partir du dépôt scénarisé des appels Java
(`test_java_calls.fixture_files`) : `CourseController#register(String)` appelle `CourseController#audit()` et
`CourseService#register(String)` ; deux de ses sites d'appel ne sont pas interprétés (un inconnu, un ambigu).
"""
import pytest

from app.mip.application.service import MipService
from app.mip.domain.query import EXPAND, MipError, read_query
from app.protocol.application.neighborhood_request import V2_CEILINGS
from test_coverage_bounds import taxo_on_fixture  # noqa: F401  (fixture partagée)
from test_java_calls import fixture_files

CONTROLLER = 'symbol:java:com.example.demo.controller.CourseController'
REGISTER = f'{CONTROLLER}#register(String)'
SERVICE = 'symbol:java:com.example.demo.service.CourseService#register(String)'


def expand(reference, relations=('CALLS',), direction='OUTGOING', **fields):
    return {'expression': EXPAND, 'target': {'reference': reference}, 'relations': list(relations),
            'direction': direction, **fields}


def ask(taxo, body):
    response = taxo.client.post(f'{taxo.base}/mip/query', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def calls(tile):
    return [(item['fact']['subject'], item['fact']['relation'], item['fact']['object']) for item in tile['facts']]


@pytest.fixture(name='courses')
def courses_fixture(taxo_on):
    taxo, _ = taxo_on(fixture_files())
    return taxo, taxo.analyse()['id']


# --- Lecture de la requête : refusée en entier, jamais devinée ------------------------------------------------

@pytest.mark.parametrize('payload', [
    'EXPAND',
    {**expand(REGISTER), 'question': 'qui appelle ?'},
    {**expand(REGISTER), 'mip': 'mip/9'},
    {**expand(REGISTER), 'expression': 'GUESS'},
    {**expand(REGISTER), 'target': REGISTER},
    {**expand(REGISTER), 'target': {'reference': REGISTER, 'kind': 'method'}},
    {**expand(REGISTER), 'target': {'reference': ''}},
    expand(REGISTER, relations=()),
    expand(REGISTER, relations=('CALLS', 'CALLS')),
    expand(REGISTER, direction='AROUND'),
    {key: value for key, value in expand(REGISTER).items() if key != 'direction'},
    expand(REGISTER, bounds={'depth': 0}),
    expand(REGISTER, bounds={'depth': '2'}),
    expand(REGISTER, bounds={'max_edges': 10}),
    expand(REGISTER, analysis=7),
])
def test_an_invalid_query_is_a_protocol_error_never_a_knowledge_frontier(payload):
    with pytest.raises(MipError) as refused:
        read_query(payload)
    assert refused.value.code == 'INVALID_ARGUMENT'


def test_project_is_part_of_the_contract_but_refused_until_a_projection_rule_is_served():
    with pytest.raises(MipError) as refused:
        read_query({**expand(REGISTER), 'expression': 'PROJECT'})
    assert refused.value.code == 'NOT_AVAILABLE'


def test_a_query_is_read_whole_and_keeps_what_was_asked():
    query = read_query(expand(REGISTER, relations=('CALLS', 'HANDLED_BY'), direction='BOTH',
                              bounds={'depth': 2, 'max_facts': 5}, analysis='a1', mip='mip/0.1'))
    assert (query.reference, query.relations, query.direction) == (REGISTER, ('CALLS', 'HANDLED_BY'), 'BOTH')
    assert (query.bounds, query.analysis, query.continuation) == ({'depth': 2, 'max_facts': 5}, 'a1', None)


# --- La Tuile, sans modèle de langage ------------------------------------------------------------------------

def test_who_calls_a_method_is_answered_by_a_tile_without_any_language_model(courses):
    taxo, scan = courses
    assert not taxo.client.app.state.minia.models, 'aucun fournisseur configuré'
    tile = ask(taxo, expand(SERVICE, direction='INCOMING'))
    assert tile['outcome'] == 'OK' and tile['mip'] == 'mip/0.1' and tile['expression'] == EXPAND
    assert tile['snapshot']['analysis'] == scan
    assert tile['root'] == {'reference': SERVICE, 'known': True}
    assert calls(tile) == [(REGISTER, 'CALLS', SERVICE)]
    fact, = tile['facts']
    assert fact['via'] == {'from': SERVICE, 'relation': 'CALLS', 'direction': 'INCOMING'}
    assert fact['fact']['status'] in {'OBSERVED', 'INFERRED'}
    assert fact['evidence'] and fact['evidence'][0]['path'].endswith('CourseController.java')
    assert tile['coverage'], 'la couverture est toujours rendue'
    # La profondeur demandée est atteinte : une borne choisie, pas une coupe par un budget.
    assert (tile['stop_reason'], tile['truncated'], tile['not_sent']) == ('DEPTH', False, [])
    assert tile['wire'] == {'protocol': 'taxo-query/1', 'operation': 'get_neighborhood',
                            'engine': 'neighborhood/2', 'facts_revision': tile['wire']['facts_revision']}


def test_the_tile_carries_the_engine_facts_unchanged(courses):
    """Un seul moteur : les faits de la Tuile MIP sont ceux de `get_neighborhood`, à l'identique."""
    taxo, scan = courses
    tile = ask(taxo, expand(REGISTER, bounds={'depth': 2}))
    wire, = taxo.ask(('get_neighborhood', {'analysis': scan, 'engine': 'neighborhood/2', 'root': REGISTER,
                                           'follow': ['CALLS'], 'direction': 'OUTGOING', 'depth': 2,
                                           'evidence': 'SUMMARY'}), analysis=scan)
    assert tile['facts'] == wire['items'] and tile['nodes'] == wire['node_details']
    assert tile['frontier'] == wire['frontier'] and tile['coverage'] == wire['coverage']


def test_the_service_answers_without_any_http_server(courses):
    taxo, scan = courses
    project = taxo.base.rsplit('/', 1)[-1]
    tile = MipService(taxo.client.app.state.taxo_query).query(project, expand(SERVICE, direction='INCOMING'))
    assert calls(tile) == [(REGISTER, 'CALLS', SERVICE)] and tile['snapshot']['analysis'] == scan


def test_calls_that_were_not_interpreted_are_a_frontier_never_invented_arrows(courses):
    taxo, _ = courses
    tile = ask(taxo, expand(REGISTER))
    assert calls(tile) == [(REGISTER, 'CALLS', f'{CONTROLLER}#audit()'), (REGISTER, 'CALLS', SERVICE)]
    unread, = [entry for entry in tile['frontier']
               if entry.get('node') == REGISTER and entry.get('producer') == 'taxo.java-calls']
    assert unread['reason'] == 'NOT_INTERPRETED'
    assert unread['categories'] == [{'category': 'UNKNOWN', 'count': {'kind': 'EXACT', 'value': 1}},
                                    {'category': 'AMBIGUOUS', 'count': {'kind': 'EXACT', 'value': 1}}]


def test_a_reference_absent_from_the_analysis_is_said_never_declared_inexistent(courses):
    taxo, _ = courses
    missing = f'{CONTROLLER}#forget()'
    tile = ask(taxo, expand(missing, direction='INCOMING'))
    assert tile['outcome'] == 'OK'
    assert tile['root'] == {'reference': missing, 'known': False}
    assert (tile['stop_reason'], tile['facts']) == ('ROOT_UNKNOWN', [])


# --- Bornes, troncature, reprise -----------------------------------------------------------------------------

def test_requested_bounds_are_capped_by_the_server_never_the_reverse(courses):
    taxo, _ = courses
    tile = ask(taxo, expand(REGISTER, bounds={'depth': 99, 'max_nodes': 10_000, 'max_facts': 10_000}))
    assert tile['outcome'] == 'OK'
    assert tile['bounds']['requested'] == {'depth': 99, 'max_nodes': 10_000, 'max_facts': 10_000}
    applied = tile['bounds']['applied']
    assert (applied['depth'], applied['max_nodes'], applied['max_facts']) == (
        V2_CEILINGS['depth'], V2_CEILINGS['max_nodes'], V2_CEILINGS['max_edges'])


def test_a_tile_cut_by_a_budget_says_so_and_resumes_where_it_stopped(courses):
    taxo, scan = courses
    first = ask(taxo, expand(REGISTER, bounds={'max_facts': 1}))
    assert calls(first) == [(REGISTER, 'CALLS', f'{CONTROLLER}#audit()')]
    assert (first['stop_reason'], first['truncated']) == ('EDGES', True)
    cut, = [entry for entry in first['frontier'] if entry['nature'] == 'SELECTION' and entry.get('continuation')]
    rest = ask(taxo, expand(REGISTER, bounds={'max_facts': 1}, analysis=scan, continuation=cut['continuation']))
    assert calls(rest) == [(REGISTER, 'CALLS', SERVICE)]


def test_a_frontier_node_stopped_by_depth_is_expanded_as_a_new_tile_on_that_node(courses):
    taxo, scan = courses
    first = ask(taxo, expand(SERVICE, direction='INCOMING'))
    stopped, = [entry for entry in first['frontier'] if entry['nature'] == 'SELECTION' and entry['node'] == REGISTER]
    assert (stopped['reason'], stopped.get('continuation')) == ('DEPTH', None)
    further = ask(taxo, expand(stopped['node'], relations=('HANDLED_BY',), direction='INCOMING', analysis=scan,
                              bounds={'depth': 1}))
    assert further['root'] == {'reference': REGISTER, 'known': True}
    assert calls(further) == [('endpoint:POST /api/courses', 'HANDLED_BY', REGISTER)]


def test_a_byte_budget_too_small_is_refused_by_the_engine_not_hidden(courses):
    taxo, _ = courses
    tile = ask(taxo, expand(REGISTER, bounds={'max_bytes': 1}))
    assert tile['outcome'] == 'ERROR' and tile['error']['code'] == 'BUDGET_EXHAUSTED'
    assert tile['snapshot']['analysis']


# --- Même instantané, périmètre, accès ----------------------------------------------------------------------

def test_a_pinned_analysis_is_kept_even_when_a_newer_one_exists(courses):
    taxo, first = courses
    second = taxo.analyse()['id']
    assert second != first
    assert ask(taxo, expand(SERVICE, direction='INCOMING', analysis=first))['snapshot']['analysis'] == first
    assert ask(taxo, expand(SERVICE, direction='INCOMING'))['snapshot']['analysis'] == second


def test_an_unknown_analysis_or_project_is_refused_before_any_read(courses):
    taxo, _ = courses
    assert taxo.client.post(f'{taxo.base}/mip/query', json=expand(REGISTER, analysis='nope')).status_code == 409
    assert taxo.client.post('/api/projects/nope/mip/query', json=expand(REGISTER)).status_code == 404


def test_a_reference_of_another_repository_is_out_of_scope(courses):
    taxo, _ = courses
    tile = ask(taxo, expand('repository:another', relations=('HAS_COMMIT',)))
    assert tile['outcome'] == 'ERROR' and tile['error']['code'] == 'OUT_OF_SCOPE'


def test_a_refusal_over_http_is_an_answer_of_the_contract_not_an_http_error(courses):
    taxo, _ = courses
    refused = ask(taxo, {**expand(REGISTER), 'expression': 'PROJECT'})
    assert refused == {'mip': 'mip/0.1', 'expression': 'PROJECT', 'outcome': 'ERROR',
                       'error': {'code': 'NOT_AVAILABLE', 'message': refused['error']['message']}}
    assert ask(taxo, ['not', 'an', 'object'])['error']['code'] == 'INVALID_ARGUMENT'


def test_the_relation_vocabulary_is_checked_once_by_the_wire_operation(courses):
    taxo, _ = courses
    refused = ask(taxo, expand(REGISTER, relations=('CALLED_MAYBE',)))
    assert refused['outcome'] == 'ERROR' and refused['error']['code'] == 'INVALID_ARGUMENT'
    assert refused['snapshot']['analysis'], 'refusé par l’opération de l’échange, sur son instantané'


def test_a_query_reads_the_maille_and_writes_nothing(courses):
    taxo, _ = courses
    before = taxo.client.get(f'{taxo.base}/scans').json()
    ask(taxo, expand(REGISTER, bounds={'depth': 4}))
    assert taxo.client.get(f'{taxo.base}/scans').json() == before
