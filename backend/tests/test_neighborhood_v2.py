"""TAXO-01J : `neighborhood/2` par le protocole, sur les deux stockages.

La Tuile attendue est écrite à la main ; les deux stockages doivent la rendre à l'identique (seuls la
génération des faits et les jetons de reprise peuvent différer, avec le même sens).
"""
import pytest

from app.facts.domain.provenance import ProducerExecution
from app.protocol.domain.envelope import size
from test_neighborhood_conformance import STORAGES, Twin, edge

A, B, C, D = (f'module:{name}' for name in 'abcd')
V2 = {'engine': 'neighborhood/2'}


@pytest.fixture
def twin(tmp_path):
    found = Twin(tmp_path)
    # Un losange, un cycle et une boucle : D a deux parents, A est revisité.
    found.add([edge(B, subject=A), edge(C, subject=A), edge(D, subject=B), edge(D, subject=C), edge(A, subject=D),
               edge(A, subject=A)])
    return found


def ask(twin, name, **arguments):
    result = twin.ask(twin.exchange(name), **{'root': A, **arguments})
    assert result['bytes'] == size(result)
    return result


def shape(result):
    """Ce que la réponse dit, sans ce qui dépend du stockage : la génération des faits et les jetons."""
    return {'items': [(item['fact']['subject'], item['fact']['object'], item['level'], item['revisit'],
                       item['via']['from'], item['via']['direction']) for item in result['items']],
            'nodes': [(node['reference'], node['level'], node['parents'], node['expanded'], node['discovered_by'])
                      for node in result['node_details']],
            'frontier': [(entry['node'], entry['reason'], entry['count']['kind'], entry.get('remaining_depth'),
                          'continuation' in entry) for entry in result['frontier'] if entry['nature'] == 'SELECTION'],
            'stop': result['stop_reason'], 'consumed': result['consumed']}


@pytest.mark.parametrize('name', STORAGES)
def test_a_three_level_tile_is_written_by_hand(twin, name):
    result = ask(twin, name, depth=3, **V2)
    assert result['engine_version'] == 'neighborhood/2'
    assert shape(result) == {
        'items': [(A, A, 1, True, A, 'OUTGOING'), (A, B, 1, False, A, 'OUTGOING'), (A, C, 1, False, A, 'OUTGOING'),
                  (B, D, 2, False, B, 'OUTGOING'), (C, D, 2, True, C, 'OUTGOING'), (D, A, 3, True, D, 'OUTGOING')],
        'nodes': [(A, 0, 2, True, None), (B, 1, 1, True, 1), (C, 1, 1, True, 2), (D, 2, 2, True, 3)],
        'frontier': [], 'stop': 'ADJACENCY_COMPLETE', 'consumed': {'nodes': 4, 'edges': 6, 'work': 4}}
    assert result['continuation'] is None
    assert result['parameters'] == {'root': A, 'steps': [{'relation': 'DEPENDS_ON', 'direction': 'OUTGOING'}],
                                    'depth': 3, 'max_fanout': None, 'evidence': 'NONE'}


@pytest.mark.parametrize('name', STORAGES)
def test_depth_cut_both_directions_and_fanout_are_written_by_hand(twin, name):
    assert shape(ask(twin, name, depth=1, **V2))['frontier'] == [(B, 'DEPTH', 'UNKNOWN', 0, False),
                                                                 (C, 'DEPTH', 'UNKNOWN', 0, False)]
    both = shape(ask(twin, name, depth=1, direction='BOTH'))
    assert both['items'] == [(A, A, 1, True, A, 'OUTGOING'), (A, B, 1, False, A, 'OUTGOING'),
                             (A, C, 1, False, A, 'OUTGOING'), (D, A, 1, False, A, 'INCOMING')]
    assert both['stop'] == 'DEPTH'
    fanned = shape(ask(twin, name, depth=2, max_fanout=2, **V2))
    assert fanned['items'] == [(A, A, 1, True, A, 'OUTGOING'), (A, B, 1, False, A, 'OUTGOING'),
                               (B, D, 2, False, B, 'OUTGOING')]
    assert fanned['frontier'] == [(A, 'FANOUT', 'AT_LEAST', 2, True), (D, 'DEPTH', 'UNKNOWN', 0, False)]
    assert fanned['stop'] == 'FANOUT'


@pytest.mark.parametrize('name', STORAGES)
def test_a_global_stop_names_its_cut_and_the_nodes_not_reached(twin, name):
    result = ask(twin, name, depth=3, max_edges=3, **V2)
    assert shape(result)['frontier'] == [(B, 'EDGES', 'UNKNOWN', 2, True), (C, 'NOT_REACHED', 'UNKNOWN', 2, False)]
    assert result['continuation'] == result['frontier'][-2]['continuation']
    resumed = ask(twin, name, **{**V2, 'root': B}, depth=2, continuation=result['continuation'])
    assert shape(resumed)['items'] == [(B, D, 1, False, B, 'OUTGOING'), (D, A, 2, False, D, 'OUTGOING')]


@pytest.mark.parametrize('name', STORAGES)
def test_two_occurrences_of_one_fact_keep_their_own_provenance_and_evidence(tmp_path, name):
    twin = Twin(tmp_path)
    other = ProducerExecution('EVALUATOR', 'other', '2.0.0', 'run-2', 'other-rules', '1')
    store = twin.stores[name]
    if name == 'fact_memory':
        store.record_execution('analysis-1', other)
    twin.add([edge(B, subject=A, line=3)])
    store.add('analysis-1', 'other', [edge(B, subject=A, line=9, produced_by=other.produced_by())])
    exchange = twin.exchange(name)
    result = twin.ask(exchange, root=A, **V2)
    first, second = result['items']
    assert first['ref'] != second['ref']
    assert first['identity'] == second['identity']
    assert second['revisit'] is True
    assert {item['fact']['produced_by']['producer_id'] for item in (first, second)} == {'fixture', 'other'}
    lines = [exchange.call({'operation': 'get_evidence', 'arguments': {'fact': item['ref']}})['evidence'][0]
             ['location']['line_start'] for item in (first, second)]
    assert sorted(lines) == [3, 9]


# Table de sélection de version, écrite à la main (TAXO-01J, § 8).
VERSIONS = [
    ({}, 'neighborhood/1'),
    ({'depth': 1, 'max_edges': 200, 'max_work': 1000}, 'neighborhood/1'),
    ({'depth': 2}, 'neighborhood/2'),
    ({'direction': 'BOTH'}, 'neighborhood/2'),
    ({'max_edges': 201}, 'neighborhood/2'),
    ({'max_work': 1001}, 'neighborhood/2'),
    ({'max_fanout': 3}, 'neighborhood/2'),
    ({'engine': 'neighborhood/2'}, 'neighborhood/2'),
    ({'engine': 'neighborhood/1'}, 'neighborhood/1'),
    ({'engine': 'neighborhood/1', 'depth': 2}, 'INVALID_ARGUMENT'),
    ({'engine': 'neighborhood/1', 'max_fanout': 2}, 'INVALID_ARGUMENT'),
    ({'engine': 'neighborhood/9'}, 'INVALID_ARGUMENT'),
    ({'depth': 5}, 'INVALID_ARGUMENT'),
    ({'steps': [{'relation': 'DEPENDS_ON', 'direction': 'INCOMING'}]}, 'neighborhood/2'),
    ({'steps': [{'relation': 'DEPENDS_ON', 'direction': 'OUTGOING'}], 'follow': ['DEPENDS_ON']}, 'INVALID_ARGUMENT'),
    ({'steps': [{'relation': 'DEPENDS_ON', 'direction': 'OUTGOING'}] * 2}, 'INVALID_ARGUMENT'),
    ({'steps': [{'relation': 'DEPENDS_ON', 'direction': 'BOTH'}]}, 'INVALID_ARGUMENT'),
    ({'steps': [{'relation': ['DEPENDS_ON'], 'direction': 'OUTGOING'}]}, 'INVALID_ARGUMENT'),
]


@pytest.mark.parametrize('arguments, expected', VERSIONS)
def test_the_version_is_chosen_by_exact_validity(twin, arguments, expected):
    shortcut = {} if 'steps' in arguments else {'follow': ['DEPENDS_ON'], 'direction': 'OUTGOING'}
    request = {'root': A, **shortcut, **arguments}
    result = twin.exchange('fact_memory').call({'operation': 'get_neighborhood', 'max_bytes': 20_000,
                                                'arguments': {'analysis': 'analysis-1', **request}})
    found = result['engine_version'] if result['outcome'] == 'OK' else result['error']['code']
    assert found == expected


@pytest.mark.parametrize('name', STORAGES)
def test_a_continuation_is_never_accepted_by_the_other_version_nor_elsewhere(twin, name):
    v1 = ask(twin, name, max_edges=1)
    v2 = ask(twin, name, max_edges=1, depth=2, **V2)
    assert v1['continuation'] and v2['continuation']
    refused = [ask(twin, name, continuation=v1['continuation'], **V2),
               ask(twin, name, continuation=v2['continuation'], engine='neighborhood/1'),
               ask(twin, name, continuation=v2['continuation'], **{**V2, 'root': B}),
               ask(twin, name, continuation=v2['continuation'], follow=['CONTAINS'], **V2)]
    assert [item['error']['code'] for item in refused] == ['INVALID_ARGUMENT'] * 4
    assert ask(twin, name, continuation=v2['continuation'], max_edges=5)['engine_version'] == 'neighborhood/2', \
        'une reprise de neighborhood/2 désigne sa version, même sans engine ; les budgets peuvent changer'
    twin.add([edge('module:e', subject=A)])
    assert ask(twin, name, continuation=v2['continuation'])['error']['code'] == 'INVALID_ARGUMENT'


@pytest.mark.parametrize('name', STORAGES)
def test_every_byte_budget_is_respected_and_a_larger_one_extends_the_same_items(twin, name):
    twin.add([edge(f'module:n{index}', subject=D, qualifiers={'label': 'x' * (index * 150)}) for index in range(8)])
    previous = []
    for budget in range(3000, 20_000, 700):
        result = ask(twin, name, depth=3, max_bytes=budget, **V2)
        if result['outcome'] == 'ERROR':
            assert result['error']['code'] == 'BUDGET_EXHAUSTED'
            assert not previous, 'un budget plus grand ne refuse jamais ce qu’un plus petit a servi'
            continue
        assert result['bytes'] <= budget
        items = [item['fact']['object'] for item in result['items']]
        assert items[:len(previous)] == previous
        previous = items
    assert len(previous) == 14


def test_both_storages_render_the_same_tile(twin):
    walks = {name: shape(ask(twin, name, depth=3, direction='BOTH', max_edges=5)) for name in STORAGES}
    assert walks['analysis_facts'] == walks['fact_memory']


@pytest.mark.parametrize('name', STORAGES)
def test_when_the_final_cut_does_not_fit_the_largest_admitted_tile_is_served(tmp_path, name):
    """La coupure finale porte sur un nœud de référence très longue, absent de la Tuile provisoire mesurée : il
    existe des budgets où elle ne tient pas. `neighborhood/2` rend alors la dernière Tuile admise, arrêtée par
    les octets, au lieu d'un refus ; `neighborhood/1` ne change pas."""
    twin = Twin(tmp_path)
    long = 'module:' + 'l' * 900
    twin.add([edge(long, subject=A), edge(B, subject=long)])
    full = ask(twin, name, depth=2, max_edges=1, max_bytes=30_000, **V2)
    assert (full['stop_reason'], len(full['items'])) == ('EDGES', 1)
    served = {}
    for budget in range(full['bytes'] - 3000, full['bytes'] + 1, 50):
        result = ask(twin, name, depth=2, max_edges=1, max_bytes=budget, **V2)
        assert result['outcome'] == 'ERROR' or result['bytes'] <= budget
        served[budget] = result.get('stop_reason') or result['error']['code']
    fallbacks = [budget for budget, reason in served.items() if reason == 'BYTES']
    assert fallbacks, served
    assert all(served[budget] != 'BUDGET_EXHAUSTED' for budget in served if budget >= fallbacks[0])


@pytest.mark.parametrize('name', STORAGES)
def test_evidence_summaries_are_locations_and_handles_retrieve_them_in_another_exchange(twin, name):
    result = ask(twin, name, depth=2, evidence='SUMMARY', **V2)
    first = result['items'][0]
    assert first['evidence'] == [{'path': 'build.gradle', 'line_start': 1, 'line_end': 1,
                                  'method': 'fixture.build'}], 'une localisation, jamais un contenu ni une empreinte'
    other = twin.exchange(name)
    proof = other.call({'operation': 'get_evidence', 'arguments': {'occurrence': first['occurrence']}})
    assert proof['outcome'] == 'OK'
    assert proof['evidence'][0]['location']['path'] == 'build.gradle'
    assert proof['fact'] == 'F1', 'la poignée donne au fait une référence de cet échange'
    assert all('evidence' not in item for item in ask(twin, name, depth=2, **V2)['items'])


@pytest.mark.parametrize('name', STORAGES)
def test_a_handle_never_opens_another_analysis_another_generation_or_anything_else(twin, name):
    from app.neighborhood.domain import handle
    result = ask(twin, name, **V2)
    occurrence = result['items'][0]['occurrence']
    key = handle.decode(occurrence, 'analysis-1', result['facts_revision'])
    foreign = handle.encode('analysis-2', result['facts_revision'], key)

    def evidence(**arguments):
        found = twin.exchange(name).call({'operation': 'get_evidence', 'arguments': arguments})
        return found['outcome'] if found['outcome'] == 'OK' else (found['error']['code'], found['error']['message'])

    refused = ('INVALID_ARGUMENT', handle.REFUSED)
    assert evidence(occurrence=foreign) == refused
    assert evidence(occurrence=handle.encode('analysis-1', result['facts_revision'], '999999')) == refused
    assert evidence(occurrence='not a handle') == refused
    assert evidence(occurrence=occurrence, fact='F1')[0] == 'INVALID_ARGUMENT'
    twin.add([edge('module:e', subject=A)])
    assert evidence(occurrence=occurrence) == refused, 'une autre génération de faits'


@pytest.mark.parametrize('name', STORAGES)
def test_summaries_are_added_in_order_while_they_fit_and_the_rest_is_counted(twin, name):
    complete = ask(twin, name, depth=3, evidence='SUMMARY', max_bytes=30_000, **V2)
    assert all(item['evidence'] for item in complete['items'])
    assert not any(entry['what'] == 'evidence_summary' for entry in complete['not_sent'])
    partial = None
    for budget in range(complete['bytes'] - 1, 3000, -40):
        result = ask(twin, name, depth=3, evidence='SUMMARY', max_bytes=budget, **V2)
        if result['outcome'] != 'OK':
            break
        assert result['bytes'] <= budget
        sent = [item['evidence'] is not None for item in result['items']]
        assert sent == sorted(sent, reverse=True), 'les résumés suivent l’ordre des éléments'
        missing = sent.count(False)
        counted = [entry['count'] for entry in result['not_sent'] if entry['what'] == 'evidence_summary']
        assert counted == ([missing] if missing else [])
        if 0 < missing < len(sent):
            partial = result
    assert partial is not None, 'un budget où les éléments tiennent, mais pas tous leurs résumés'


def gap(subject, kind):
    from app.facts.contract import validate_fact
    from test_neighborhood_conformance import RUN, SNAPSHOT
    fact = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID', 'subject': subject,
            'coverage_type': kind, 'scope': {'include': [subject]}, 'snapshot': dict(SNAPSHOT),
            'produced_by': RUN.produced_by()}
    validate_fact(fact)
    return fact


def local(result):
    return [(entry['node'], entry['subject'], entry['reason']) for entry in result['frontier']
            if entry['nature'] == 'KNOWLEDGE' and entry.get('scope') == 'NODE']


@pytest.mark.parametrize('name', STORAGES)
def test_local_gaps_are_attached_to_the_nodes_they_concern(twin, name):
    """Écrit à la main : D n'a pas été interprété ; le fichier cité par chaque preuve n'a pas pu être lu, ce qui
    concerne chaque nœud atteint par un élément (A, B, C, D) ; une couverture lue n'est pas une lacune."""
    twin.add([gap(D, 'NOT_INTERPRETED'), gap('file:build.gradle', 'READ_ERROR'), gap(B, 'ANALYSED')])
    result = ask(twin, name, depth=3, **V2)
    assert local(result) == [(A, 'file:build.gradle', 'READ_ERROR'), (B, 'file:build.gradle', 'READ_ERROR'),
                             (C, 'file:build.gradle', 'READ_ERROR'), (D, 'file:build.gradle', 'READ_ERROR'),
                             (D, D, 'NOT_INTERPRETED')]
    assert local(ask(twin, name, depth=1, **V2)) == [
        (A, 'file:build.gradle', 'READ_ERROR'), (B, 'file:build.gradle', 'READ_ERROR'),
        (C, 'file:build.gradle', 'READ_ERROR')], 'seulement les nœuds rendus'
    assert local(ask(twin, name, root='module:missing', **V2)) == []
    assert local(ask(twin, name, depth=1)) == [], 'neighborhood/1 ne change pas'


@pytest.mark.parametrize('name', STORAGES)
def test_local_gaps_are_never_read_beyond_their_bound_and_the_tile_says_so(twin, name, monkeypatch):
    twin.add([gap(D, 'NOT_INTERPRETED')])
    monkeypatch.setattr('app.neighborhood.application.knowledge_frontier.MAX_LOCAL_REFERENCES', 2)
    result = ask(twin, name, depth=3, **V2)
    assert local(result) == []
    assert [entry['reason'] for entry in result['frontier'] if entry['nature'] == 'KNOWLEDGE'] == [
        'LOCAL_COVERAGE_NOT_READ']


@pytest.mark.parametrize('name', STORAGES)
def test_local_gaps_that_do_not_fit_are_counted_never_silently_dropped(twin, name):
    twin.add([gap(D, 'NOT_INTERPRETED'), gap('file:build.gradle', 'READ_ERROR')])
    complete = ask(twin, name, depth=3, max_bytes=30_000, **V2)
    seen = set()
    for budget in range(complete['bytes'], 3000, -60):
        result = ask(twin, name, depth=3, max_bytes=budget, **V2)
        if result['outcome'] != 'OK':
            break
        rendered = {node['reference'] for node in result['node_details']}
        concerned = [entry for entry in local(complete) if entry[0] in rendered]
        counted = sum(entry['count'] for entry in result['not_sent'] if entry['what'] == 'local_coverage')
        assert len(local(result)) + counted == len(concerned), 'ce qui manque est compté, exactement'
        assert local(result) == concerned[:len(local(result))], 'dans l’ordre, sans trou'
        seen.add((len(local(result)) == len(concerned), counted > 0))
    assert (False, True) in seen, 'un budget où des lacunes locales ne tiennent pas, et sont comptées'


def test_migration_007_anchors_existing_coverage_and_downgrades(tmp_path):
    import os
    import subprocess
    import sys
    from sqlalchemy import create_engine, text
    url = f'sqlite:///{tmp_path / "anchor.db"}'
    env = {**os.environ, 'DATABASE_URL': url}

    def migrate(action, target):
        return subprocess.run([sys.executable, '-m', 'alembic', action, target], check=True, env=env,
                              capture_output=True, text=True).stdout
    migrate('upgrade', '006')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO projects (id, name, path) VALUES ('p', 'p', '/p')"))
        db.execute(text("INSERT INTO scans (id, project_id, created_at, result) VALUES ('s', 'p', '2026-10-03', '{}')"))
        db.execute(text("INSERT INTO fact_identities (identity_hash, kind, subject, identity) VALUES "
                        "('c', 'COVERAGE', 'file:a.java', '{}'), ('x', 'ASSERTION', 'module:a', '{}'), "
                        "('n', 'COVERAGE', 'module:\u00f3', '{}')"))
        db.execute(text("INSERT INTO fact_occurrences (scan_id, identity_hash, status, validity, has_evidence, "
                        "raw_identity) VALUES ('s', 'c', 'OBSERVED', 'VALID', 0, NULL), "
                        "('s', 'x', 'OBSERVED', 'VALID', 0, NULL), ('s', 'n', 'OBSERVED', 'VALID', 0, :raw)"),
                   {'raw': '{"subject": "module:o\u0301"}'})
    assert '2 couvertures ancrées' in migrate('upgrade', '007')
    import hashlib
    with engine.connect() as db:
        anchors = dict(db.execute(text('SELECT identity_hash, subject_hash FROM fact_occurrences')).all())
    assert anchors == {'c': hashlib.sha256(b'file:a.java').hexdigest(), 'x': None,
                       'n': hashlib.sha256('module:o\u0301'.encode()).hexdigest()}, \
        'l’orthographe soumise, comme à l’enregistrement'
    migrate('downgrade', '006')
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM fact_occurrences WHERE subject_hash IS NOT NULL')) == 0
    engine.dispose()


@pytest.mark.parametrize('name', STORAGES)
def test_a_local_gap_on_a_reference_spelled_otherwise_than_nfc_is_found(tmp_path, name):
    """Une référence soumise en NFD : la Tuile la rend telle quelle, et sa lacune locale doit être trouvée."""
    twin = Twin(tmp_path)
    spelled = 'module:órders'
    twin.add([edge(spelled, subject=A), gap(spelled, 'NOT_INTERPRETED')])
    assert local(ask(twin, name, **V2)) == [(spelled, spelled, 'NOT_INTERPRETED')]
