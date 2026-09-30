"""One-hop Tile on both storages (TAXO-01E-B): same synthetic graphs, same `get_neighborhood`.

The two storages receive exactly the same contract facts in the same order. Their answers must give
the same nodes, facts, order, evidence, frontier, consumption, stop reason and paging. Only
`facts_revision` and the continuation token may differ, with the same meaning; each page resumes
with the token its own storage issued.
"""
import copy
import threading
import unicodedata
from types import SimpleNamespace

import pytest
from datetime import datetime, timezone

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.projects.infrastructure.sqlalchemy.project_repository import ProjectRow
from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow
from storage_engines import POSTGRES, fresh_engine
from app.facts.contract import validate_fact
from app.facts.domain.provenance import ProducerExecution
from app.protocol.application.exchange import Exchange
from app.protocol.domain.envelope import size
from app.scans.infrastructure.sqlalchemy import fact_memory
from app.scans.infrastructure.sqlalchemy.fact_memory import SqlAlchemyFactMemory
from app.scans.infrastructure.sqlalchemy.fact_store import SqlAlchemyAnalysisFacts

ROOT = 'module:root'
SNAPSHOT = {'repository': 'fixture', 'commit': 'a' * 40, 'mode': 'COMMIT'}
RUN = ProducerExecution('EVALUATOR', 'fixture', '1.0.0', 'run-1', 'fixture-rules', '1')
STORAGES = ('analysis_facts', 'fact_memory')


def edge(target='module:child', relation='DEPENDS_ON', subject=ROOT, line=1, **extra):
    fact = {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'relation': relation, 'object': target, 'qualifiers': {},
            'snapshot': dict(SNAPSHOT), 'produced_by': RUN.produced_by(),
            'evidence': [{'repository': SNAPSHOT['repository'], 'commit': SNAPSHOT['commit'], 'path': 'build.gradle',
                          'line_start': line, 'line_end': line, 'method': 'fixture.build',
                          'content_hash': 'sha256:' + 'b' * 64}], **extra}
    validate_fact(fact)
    return fact


def coverage(subject=ROOT):
    fact = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'coverage_type': 'ANALYSED', 'scope': {'include': [subject]},
            'snapshot': dict(SNAPSHOT), 'produced_by': RUN.produced_by()}
    validate_fact(fact)
    return fact


def _analyses(engine):
    """Project and analyses rows: PostgreSQL enforces the foreign keys."""
    with Session(engine) as db:
        if db.get(ProjectRow, 'project') is None:
            db.add(ProjectRow(id='project', name='fixture', path='/fixture'))
            db.add_all(ScanRow(id=scan, project_id='project', created_at=datetime.now(timezone.utc), result={})
                       for scan in ('analysis-1', 'analysis-2'))
            db.commit()


class Twin:
    """The same analysis kept by both storages."""

    def __init__(self, tmp_path):
        self.stores, self.engines = {}, {}
        shared = fresh_engine(tmp_path) if POSTGRES else None
        for name in STORAGES:
            engine = shared or fresh_engine(tmp_path, name)
            _analyses(engine)
            store = SqlAlchemyAnalysisFacts(engine) if name == 'analysis_facts' else SqlAlchemyFactMemory(engine)
            if name == 'fact_memory':
                for scan in ('analysis-1', 'analysis-2'):
                    store.record_snapshot(scan, SNAPSHOT)
                    store.record_execution(scan, RUN)
            self.stores[name], self.engines[name] = store, engine
        self.evaluation = {'evaluator_id': 'fixture', 'status': 'SUCCESS',
                           'snapshot': {'repository': SNAPSHOT['repository'], 'commit': SNAPSHOT['commit']},
                           'coverage': [{'coverage_type': 'ANALYSED', 'count': 1, 'subjects': ['repository:fixture']}]}

    def add(self, facts, scan='analysis-1'):
        for store in self.stores.values():
            store.add(scan, 'fixture', copy.deepcopy(facts))

    def exchange(self, name):
        service = SimpleNamespace(facts=self.stores[name], source_context='off',
                                  catalogs={'fixture': frozenset({'CONTAINS', 'DEPENDS_ON'})})
        scan = SimpleNamespace(id='analysis-1', result={'evaluations': [self.evaluation]})
        return Exchange(service, 'project', scan, False, 200_000)

    @staticmethod
    def ask(exchange, **arguments):
        budget = arguments.pop('max_bytes', 20_000)
        result = exchange.call({'operation': 'get_neighborhood', 'max_bytes': budget, 'arguments': {
            'analysis': 'analysis-1', 'root': ROOT, 'follow': ['DEPENDS_ON'], 'direction': 'OUTGOING', **arguments}})
        assert result['bytes'] == size(result)
        return result

    def pages(self, name, limit=6, **arguments):
        """Every page of one walk, each resumed with the token of the previous page, with its evidence."""
        pages, token = [], None
        while len(pages) < limit:
            exchange = self.exchange(name)
            page = self.ask(exchange, **arguments, **({'continuation': token} if token else {}))
            proofs = [exchange.call({'operation': 'get_evidence', 'arguments': {'fact': item['ref']}})
                      for item in page.get('items', [])]
            pages.append((page, proofs))
            token = page.get('continuation')
            if token is None:
                break
        return pages

    def compare(self, **arguments):
        walks = {name: self.pages(name, **arguments) for name in STORAGES}
        assert comparable(walks['analysis_facts']) == comparable(walks['fact_memory'])
        return walks['fact_memory']


def comparable(walk):
    """What must be equal: everything but the storage generation and the token's spelling."""
    kept = []
    for page, proofs in walk:
        page = copy.deepcopy(page)
        page.pop('facts_revision', None)
        page.pop('bytes', None)
        resumable = page.pop('continuation', None) is not None
        for boundary in page.get('frontier', []):
            boundary['resumable'] = boundary.pop('continuation', None) is not None
        kept.append((page, resumable, proofs))
    return kept


@pytest.fixture
def twin(tmp_path):
    pair = Twin(tmp_path)
    yield pair
    for engine in set(pair.engines.values()):
        engine.dispose()


def objects(walk):
    return [item['fact']['object'] for page, _ in walk for item in page.get('items', [])]


def test_outgoing_priority_order_and_self_loop(twin):
    twin.add([edge('module:z'), edge(ROOT), edge('module:a'), edge('module:b', 'CONTAINS'), coverage()])
    walk = twin.compare(follow=['CONTAINS', 'DEPENDS_ON'], priority=['DEPENDS_ON', 'CONTAINS'])
    assert objects(walk) == ['module:a', ROOT, 'module:z', 'module:b']
    assert walk[0][0]['stop_reason'] == 'ADJACENCY_COMPLETE'


def test_incoming_with_several_parents(twin):
    twin.add([edge('module:a', subject=parent) for parent in ('module:p3', 'module:p1', 'module:p2')]
             + [edge('module:x', subject='module:a')])
    walk = twin.compare(root='module:a', direction='INCOMING')
    assert [item['fact']['subject'] for item in walk[0][0]['items']] == ['module:p1', 'module:p2', 'module:p3']


@pytest.mark.parametrize('root,direction', [('module:a', 'OUTGOING'), ('module:a', 'INCOMING'),
                                            ('module:b', 'OUTGOING'), ('module:b', 'INCOMING')])
def test_cycles(twin, root, direction):
    twin.add([edge('module:b', subject='module:a'), edge('module:a', subject='module:b'),
              edge('module:c', subject='module:b')])
    twin.compare(root=root, direction=direction)


def test_high_degree_pages(twin):
    twin.add([edge(f'module:{index:04}') for index in reversed(range(300))])
    walk = twin.compare(max_edges=2, max_work=2)
    assert objects(walk) == [f'module:{index:04}' for index in range(12)]


@pytest.mark.parametrize('arguments', [{'max_nodes': 1}, {'max_edges': 2}, {'max_work': 1},
                                       {'max_nodes': 2, 'max_edges': 3}],
                         ids=['max-nodes', 'max-edges', 'max-work', 'nodes-and-edges'])
def test_selection_budgets_and_resumption(twin, arguments):
    twin.add([edge('module:b'), edge('module:a'), edge('module:c', 'CONTAINS'), edge('module:d')])
    walk = twin.compare(follow=['CONTAINS', 'DEPENDS_ON'], **arguments)
    # With a single node allowed, every page stops before its first neighbour: the walk never ends.
    assert (walk[-1][0]['continuation'] is None) == (arguments.get('max_nodes') != 1)


def test_a_neighbour_refused_by_max_nodes_is_not_lost(twin):
    twin.add([edge('module:b'), edge('module:a')])
    for name in STORAGES:
        refused = twin.ask(twin.exchange(name), max_nodes=1)
        assert refused['stop_reason'] == 'NODES'
        assert refused['items'] == []
        assert refused['continuation'] is not None
        resumed = twin.ask(twin.exchange(name), continuation=refused['continuation'], max_nodes=3)
        assert [item['fact']['object'] for item in resumed['items']] == ['module:a', 'module:b']
        assert resumed['stop_reason'] == 'ADJACENCY_COMPLETE'


def test_byte_budget_refused_and_cut(twin):
    twin.add([edge('module:a'), edge('module:b'), edge('module:c', qualifiers={'label': 'x' * 6000})])
    refused = twin.compare(max_bytes=100)
    assert refused[0][0]['error']['code'] == 'BUDGET_EXHAUSTED'
    walk = twin.compare(max_bytes=4500)
    assert walk[0][0]['stop_reason'] == 'BYTES'


@pytest.mark.parametrize('arguments', [{'root': 'module:missing'}, {'follow': ['CALLS']}, {'follow': ['CONTAINS']},
                                       {'follow': ['CALLS', 'DEPENDS_ON']}, {'analysis': 'analysis-2'},
                                       {'root': 'repository:foreign'}],
                         ids=['unknown-root', 'no-producer', 'covered-empty', 'producer-and-context',
                              'other-analysis', 'out-of-scope'])
def test_anchors_context_and_boundaries(twin, arguments):
    twin.add([edge(), edge('module:foreign')])
    twin.add([edge('module:elsewhere')], scan='analysis-2')
    twin.compare(**arguments)


def test_knowledge_coverage(twin):
    twin.add([edge()])
    twin.evaluation['coverage'].append({'coverage_type': 'NOT_INTERPRETED', 'count': 10, 'subjects': ['file:x']})
    walk = twin.compare()
    assert any(boundary['nature'] == 'KNOWLEDGE' for boundary in walk[0][0]['frontier'])


def test_long_unicode_and_spelling(twin):
    root = 'module:' + ''.join(chr(0x4e00 + index) for index in range(300))
    prefix = 'module:' + ''.join(chr(0x5000 + index) for index in range(300))
    targets = [prefix + suffix for suffix in ('z', '\U00010000', '', '', 'café', 'café')]
    twin.add([edge(target, subject=root) for target in targets])
    walk = twin.compare(root=root, max_edges=2, max_bytes=32_000)
    # Order compares NFC references: both spellings of « café » tie and follow their identity.
    order = [unicodedata.normalize('NFC', target) for target in objects(walk)]
    assert order == sorted(order, key=lambda value: value.encode('utf-16-be'))
    assert sorted(objects(walk)) == sorted(targets)
    for spelling in ('café', 'café'):
        twin.compare(root=prefix + spelling, direction='INCOMING', max_bytes=32_000)


def test_append_invalidates_the_continuation_on_both(twin):
    twin.add([edge('module:b'), edge('module:c')])
    first = {name: twin.ask(twin.exchange(name), max_edges=1) for name in STORAGES}
    twin.add([edge('module:a')])
    for name in STORAGES:
        refused = twin.ask(twin.exchange(name), continuation=first[name]['continuation'])
        assert refused['error']['code'] == 'INVALID_ARGUMENT'
    walk = twin.compare()
    assert objects(walk) == ['module:a', 'module:b', 'module:c']


@pytest.mark.parametrize('name', STORAGES)
def test_mutation_during_the_walk_refuses_the_page(twin, monkeypatch, name):
    twin.add([edge()])
    store = twin.stores[name]
    neighbor = store.neighbor

    def mutate(*args, **kwargs):
        found = neighbor(*args, **kwargs)
        store.add('analysis-1', 'fixture', [edge('module:a')])
        return found

    monkeypatch.setattr(store, 'neighbor', mutate)
    exchange = twin.exchange(name)
    assert twin.ask(exchange, max_edges=1)['error']['code'] == 'INVALID_ARGUMENT'
    assert not exchange.refs.facts


# ——— Versioned memory only: traversal stays indexed and anchored ———

def test_memory_walk_never_loads_the_adjacency(twin):
    twin.add([edge(f'module:{index:04}') for index in reversed(range(1000))])
    statements = []
    event.listen(twin.engines['fact_memory'], 'before_cursor_execute',
                 lambda conn, cursor, sql, params, context, many: statements.append(sql))
    result = twin.ask(twin.exchange('fact_memory'), max_edges=2, max_work=2)
    assert [item['fact']['object'] for item in result['items']] == ['module:0000', 'module:0001']
    occurrences = [sql for sql in statements if sql.lstrip().startswith('SELECT') and 'fact_occurrences' in sql
                   and 'fact_evidence' not in sql.split('FROM', 1)[1].split()[0]]
    assert occurrences
    assert all('LIMIT' in sql for sql in occurrences)


def test_memory_writers_of_one_analysis_are_serialized(twin):
    store = twin.stores['fact_memory']
    batches = [[edge(f'module:{index:03}', line=writer + 1) for index in range(writer, 120, 3)] for writer in range(3)]
    start, errors = threading.Barrier(len(batches)), []

    def write(batch):
        start.wait()
        try:
            store.add('analysis-1', 'fixture', batch)
        except Exception as error:  # reported by the assertion below
            errors.append(error)

    threads = [threading.Thread(target=write, args=(batch,)) for batch in batches]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    walked, after = [], ''
    while (found := store.neighbor('analysis-1', ROOT, 'DEPENDS_ON', 'OUTGOING', after)) is not None:
        after = found[0]
        walked.append(found[1]['object'])
    assert walked == [f'module:{index:03}' for index in range(120)]


def walk(store, root, direction='OUTGOING', relation='DEPENDS_ON'):
    found, after = [], ''
    while (step := store.neighbor('analysis-1', root, relation, direction, after)) is not None:
        after = step[0]
        found.append(step[1]['object' if direction == 'OUTGOING' else 'subject'])
    return found


def test_memory_batch_ranks_only_the_adjacencies_it_touches(twin, monkeypatch):
    store = twin.stores['fact_memory']
    store.add('analysis-1', 'fixture', [edge(f'module:{index:03}') for index in range(200)]
              + [edge('module:x', subject='module:other'), edge('module:y', 'CONTAINS', subject='module:other')])
    read, statements = [], []
    adjacency_rows = fact_memory._adjacency_rows

    def spy(db, scan_id, direction, groups):
        rows = adjacency_rows(db, scan_id, direction, groups)
        read.extend((direction, row.anchor, row.relation) for row in rows)
        return rows

    monkeypatch.setattr(fact_memory, '_adjacency_rows', spy)
    event.listen(twin.engines['fact_memory'], 'before_cursor_execute',
                 lambda conn, cursor, sql, params, context, many: statements.append(sql))
    store.add('analysis-1', 'fixture', [edge('module:w', subject='module:other')])
    other, root = fact_memory._reference_hash('module:other'), fact_memory._reference_hash(ROOT)
    assert ('OUTGOING', other, 'DEPENDS_ON') in read
    assert len([item for item in read if item[0] == 'OUTGOING']) == 2  # module:x and module:w, never CONTAINS
    assert not any(anchor == root for direction, anchor, _ in read if direction == 'OUTGOING')
    assert not any('fact_evidence' in sql for sql in statements if sql.lstrip().startswith('SELECT'))
    assert walk(store, 'module:other') == ['module:w', 'module:x']
    assert walk(store, ROOT)[:2] == ['module:000', 'module:001']


def test_memory_ranks_are_local_to_each_adjacency(twin):
    store = twin.stores['fact_memory']
    store.add('analysis-1', 'fixture', [edge('module:b'), edge('module:a', subject='module:other'), edge('module:a')])
    with Session(twin.engines['fact_memory']) as db:
        ranks = db.execute(select(fact_memory.FactOccurrenceRow.subject_hash,
                                  fact_memory.FactOccurrenceRow.outgoing_rank)).all()
    by_anchor = {}
    for anchor, rank in ranks:
        by_anchor.setdefault(anchor, []).append(rank)
    assert sorted(sorted(values) for values in by_anchor.values()) == [[1], [1, 2]]


def test_memory_colliding_anchors_keep_their_own_order(twin, monkeypatch):
    monkeypatch.setattr(fact_memory, '_reference_hash', lambda reference: '0' * 64)
    store = twin.stores['fact_memory']
    store.add('analysis-1', 'fixture', [edge('module:c', subject='module:other'), edge('module:b'),
                                        edge('module:a', subject='module:other'), edge('module:d')])
    store.add('analysis-1', 'fixture', [edge('module:0', subject='module:other')])
    assert walk(store, ROOT) == ['module:b', 'module:d']
    assert walk(store, 'module:other') == ['module:0', 'module:a', 'module:c']


def test_memory_reference_hash_collision_never_returns_another_anchor(twin, monkeypatch):
    monkeypatch.setattr(fact_memory, '_reference_hash', lambda reference: '0' * 64)
    store = twin.stores['fact_memory']
    store.add('analysis-1', 'fixture', [edge('module:a', subject='module:other'), edge('module:b')])
    assert store.neighbor('analysis-1', ROOT, 'DEPENDS_ON', 'OUTGOING')[1]['object'] == 'module:b'
    assert not store.has_reference('analysis-1', 'module:missing')


def test_memory_ranks_only_assertions_can_be_walked(twin):
    store = twin.stores['fact_memory']
    store.add('analysis-1', 'fixture', [coverage(), edge()])
    assert store.has_reference('analysis-1', ROOT)
    assert not store.has_reference('analysis-1', 'module:elsewhere')
    assert store.neighbor('analysis-1', ROOT, 'DEPENDS_ON', 'OUTGOING')[1]['kind'] == 'ASSERTION'
    assert store.revision('analysis-1') > store.revision('analysis-2') == 0
