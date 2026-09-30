"""Versioned fact memory (TAXO-01E-A): identity once, one occurrence per analysis, exact restitution.

The port suite runs on the current storage and on the new memory; the truths come from the contract
conformance cases and from hand-built synthetic facts, never from Taxo judging its own output.
"""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from storage_engines import fresh_engine
from app.facts.contract import fact_identity, validate_fact
from app.facts.domain.provenance import ProducerExecution
from app.projects.infrastructure.sqlalchemy.project_repository import ProjectRow
from app.scans.domain.occurrence import OccurrenceError, same
from app.scans.infrastructure.sqlalchemy.fact_memory import (FactEvidenceRow, FactIdentityRow, FactOccurrenceRow,
                                                             ProducerExecutionRow, SqlAlchemyFactMemory)
from app.scans.infrastructure.sqlalchemy.fact_store import SqlAlchemyAnalysisFacts
from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow

CONFORMANCE = Path(__file__).parents[1] / 'app/facts/infrastructure/contract/conformance'
VALID = sorted((CONFORMANCE / 'v1').glob('valid-*.json'))
VECTORS = json.loads((CONFORMANCE / 'identity/identity-vectors-v1.json').read_text(encoding='utf-8'))['cases']
SNAPSHOT = {'repository': 'fixture', 'commit': 'a' * 40, 'mode': 'COMMIT'}


def execution(version='1.0.0', run='run-1', catalog='1', producer='fixture'):
    return ProducerExecution('EVALUATOR', producer, version, run, 'fixture-rules', catalog)


def assertion(obj='module:child', line=87, run=execution(), status='OBSERVED', snapshot=SNAPSHOT, **extra):
    fact = {'contract_version': 1, 'kind': 'ASSERTION', 'status': status, 'validity': 'VALID',
            'subject': 'module:root', 'relation': 'DEPENDS_ON', 'object': obj, 'qualifiers': {},
            'snapshot': dict(snapshot), 'produced_by': run.produced_by(),
            'evidence': [{'repository': snapshot['repository'], 'commit': snapshot['commit'], 'path': 'build.gradle',
                          'line_start': line, 'line_end': line, 'method': 'fixture.build',
                          'content_hash': 'sha256:' + 'b' * 64}], **extra}
    validate_fact(fact)
    return fact


class Stores:
    def __init__(self, engine, store):
        self.engine, self.store = engine, store
        self.memory = isinstance(store, SqlAlchemyFactMemory)

    def analysis(self, scan_id, snapshot=SNAPSHOT, executions=()):
        with Session(self.engine) as db:
            if db.get(ProjectRow, 'project') is None:
                db.add(ProjectRow(id='project', name='fixture', path='/fixture'))
            db.add(ScanRow(id=scan_id, project_id='project', created_at=datetime.now(timezone.utc), result={}))
            db.commit()
        if self.memory:
            self.store.record_snapshot(scan_id, snapshot)
            for item in executions:
                self.store.record_execution(scan_id, item)
        return scan_id

    def count(self, row):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(row))


def producer_of(fact):
    produced_by = fact['produced_by']
    if produced_by['producer_type'] == 'HUMAN':
        return ()
    return (ProducerExecution(produced_by['producer_type'], produced_by['producer_id'],
                              produced_by['producer_version'], produced_by['execution_id'],
                              produced_by.get('catalog_id'), produced_by.get('catalog_version')),)


@pytest.fixture(params=['analysis_facts', 'fact_memory'])
def stores(request, tmp_path):
    engine = fresh_engine(tmp_path)
    store = SqlAlchemyAnalysisFacts(engine) if request.param == 'analysis_facts' else SqlAlchemyFactMemory(engine)
    yield Stores(engine, store)
    engine.dispose()


@pytest.fixture
def memory(tmp_path):
    engine = fresh_engine(tmp_path)
    yield Stores(engine, SqlAlchemyFactMemory(engine))
    engine.dispose()


# ——— Port suite: both implementations ———

@pytest.mark.parametrize('path', VALID, ids=lambda path: path.stem)
def test_every_valid_contract_case_is_given_back_exactly(stores, path):
    fact = json.loads(path.read_text(encoding='utf-8'))
    scan = stores.analysis('analysis', fact['snapshot'], producer_of(fact))
    stores.store.add(scan, fact['produced_by']['producer_id'], [fact])
    [found] = stores.store.query(scan)
    assert same(found, fact)


@pytest.mark.parametrize('case', VECTORS, ids=lambda case: case['name'])
def test_identity_vectors_keep_their_own_spelling(stores, case):
    fact = case['input']
    scan = stores.analysis('analysis', fact['snapshot'], producer_of(fact))
    stores.store.add(scan, fact['produced_by']['producer_id'], [fact])
    [found] = stores.store.query(scan)
    assert same(found, fact)


def test_query_filters_and_order(stores):
    runs = (execution(), execution(run='run-2', producer='other'))
    scan = stores.analysis('analysis', executions=runs)
    first = [assertion('module:b'), assertion('module:a', relation='CONTAINS')]
    other = [assertion('module:c', run=runs[1])]
    stores.store.add(scan, 'fixture', first)
    stores.store.add(scan, 'other', other)
    assert [fact['object'] for fact in stores.store.query(scan)] == ['module:b', 'module:a', 'module:c']
    assert stores.store.query(scan, evaluator_id='other') == other
    assert stores.store.query(scan, relation='CONTAINS') == [first[1]]
    assert stores.store.query(scan, subject='module:root', object='module:c') == other
    assert stores.store.query(scan, kind='COVERAGE') == []
    assert stores.store.query('another-analysis') == []


@pytest.mark.parametrize('spelling', ['module:cafe\u0301', 'module:caf\u00e9'], ids=['nfd', 'nfc'])
def test_filters_compare_the_submitted_spelling(stores, spelling):
    other = 'module:caf\u00e9' if spelling.endswith('\u0301') else 'module:cafe\u0301'
    scan = stores.analysis('analysis', executions=[execution()])
    fact = assertion(spelling)
    stores.store.add(scan, 'fixture', [fact])
    assert stores.store.query(scan, object=spelling) == [fact]
    assert stores.store.query(scan, object=other) == []
    assert stores.store.query(scan, subject='module:root', object=spelling) == [fact]


def test_any_iterable_of_facts_is_written_once(stores):
    scan = stores.analysis('analysis', executions=[execution()])
    facts = [assertion('module:a'), assertion('module:b')]
    stores.store.add(scan, 'fixture', (fact for fact in facts))
    assert stores.store.query(scan) == facts


def mixed_batch(size=1200):
    """Assertions with one to three proofs, and coverage without any, interleaved."""
    batch = []
    for index in range(size):
        if index % 4 == 3:
            coverage = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                        'subject': f'file:src/F{index}.java', 'coverage_type': 'ANALYSED',
                        'scope': {'include': [f'file:src/F{index}.java']}, 'snapshot': dict(SNAPSHOT),
                        'produced_by': execution().produced_by()}
            validate_fact(coverage)
            batch.append(coverage)
            continue
        fact = assertion(f'module:m{(index * 7919) % size:05}', line=index + 1)
        fact['evidence'] += [{**fact['evidence'][0], 'line_start': index + 1 + extra, 'line_end': index + 1 + extra}
                             for extra in range(1, index % 3 + 1)]
        batch.append(fact)
    return batch


def test_a_large_batch_keeps_submission_order_and_each_evidence(stores):
    scan = stores.analysis('analysis', executions=[execution()])
    batch = mixed_batch()
    stores.store.add(scan, 'fixture', batch)
    assert same(stores.store.query(scan), batch)
    later = mixed_batch(50)[::-1]
    stores.store.add(scan, 'fixture', later)
    assert same(stores.store.query(scan), batch + later)


# ——— Versioned memory ———

def test_same_fact_in_two_analyses_is_one_identity_and_two_occurrences(memory):
    for scan in ('a', 'b'):
        memory.analysis(scan, executions=[execution()])
        memory.store.add(scan, 'fixture', [assertion()])
    assert memory.count(FactIdentityRow) == 1
    assert memory.count(FactOccurrenceRow) == 2


def test_reanalysis_of_the_same_snapshot_keeps_its_own_occurrence(memory):
    for scan, run in (('a', 'run-1'), ('b', 'run-2')):
        memory.analysis(scan, executions=[execution(run=run)])
        memory.store.add(scan, 'fixture', [assertion(run=execution(run=run))])
    assert memory.count(FactIdentityRow) == 1
    assert [memory.store.query(scan)[0]['produced_by']['execution_id'] for scan in 'ab'] == ['run-1', 'run-2']


def test_moved_evidence_same_identity_own_evidence(memory):
    for scan, line in (('a', 87), ('b', 91)):
        memory.analysis(scan, executions=[execution()])
        memory.store.add(scan, 'fixture', [assertion(line=line)])
    assert memory.count(FactIdentityRow) == 1
    assert [memory.store.query(scan)[0]['evidence'][0]['line_start'] for scan in 'ab'] == [87, 91]


def test_new_producer_version_same_identity_distinct_provenance(memory):
    for scan, version in (('a', '1.0.0'), ('b', '2.0.0')):
        run = execution(version=version)
        memory.analysis(scan, executions=[run])
        memory.store.add(scan, 'fixture', [assertion(run=run)])
    assert memory.count(FactIdentityRow) == 1
    assert [memory.store.query(scan)[0]['produced_by']['producer_version'] for scan in 'ab'] == ['1.0.0', '2.0.0']


def test_status_change_keeps_the_identity(memory):
    human = json.loads((CONFORMANCE / 'v1/valid-human.json').read_text(encoding='utf-8'))
    inferred = json.loads((CONFORMANCE / 'v1/valid-inferred-evaluator.json').read_text(encoding='utf-8'))
    inferred |= {'relation': human['relation'], 'object': human['object'], 'snapshot': human['snapshot']}
    validate_fact(inferred)
    memory.analysis('a', human['snapshot'], producer_of(inferred))
    memory.store.add('a', inferred['produced_by']['producer_id'], [inferred])
    memory.analysis('b', human['snapshot'])
    memory.store.add('b', human['produced_by']['producer_id'], [human])
    assert memory.count(FactIdentityRow) == 1
    assert memory.store.query('a') == [inferred]
    assert memory.store.query('b') == [human]
    with Session(memory.engine) as db:
        assert db.scalar(select(FactOccurrenceRow.execution).where(FactOccurrenceRow.scan_id == 'b')) is None


@pytest.mark.parametrize('produced', [execution(run='unknown'), execution(catalog='2'), execution(version='9')],
                         ids=['unknown-execution', 'other-catalog', 'other-version'])
def test_fact_without_its_recorded_execution_is_refused_and_nothing_is_written(memory, produced):
    memory.analysis('a', executions=[execution()])
    batch = [assertion('module:ok'), assertion(run=produced)]
    with pytest.raises(OccurrenceError):
        memory.store.add('a', 'fixture', batch)
    assert memory.count(FactOccurrenceRow) == 0
    assert memory.count(FactIdentityRow) == 0
    assert memory.count(ProducerExecutionRow) == 1


def test_add_never_creates_an_execution(memory):
    memory.analysis('a')
    batch = [assertion()]
    with pytest.raises(OccurrenceError):
        memory.store.add('a', 'fixture', batch)
    assert memory.count(ProducerExecutionRow) == 0


def test_producer_must_be_the_one_recording(memory):
    memory.analysis('a', executions=[execution()])
    batch = [assertion()]
    with pytest.raises(OccurrenceError):
        memory.store.add('a', 'someone-else', batch)


OTHER = {**SNAPSHOT, 'commit': 'c' * 40}


def evidence_from_elsewhere():
    fact = assertion()
    fact['evidence'][0]['commit'] = OTHER['commit']
    return fact


def unknown_evidence_field():
    fact = assertion()
    fact['evidence'][0]['note'] = 'unknown'
    return fact


@pytest.mark.parametrize('make', [lambda: assertion(snapshot=OTHER), evidence_from_elsewhere, unknown_evidence_field],
                         ids=['other-snapshot', 'evidence-from-elsewhere', 'unknown-evidence-field'])
def test_fact_that_does_not_belong_or_cannot_be_kept_is_refused(memory, make):
    memory.analysis('a', executions=[execution()])
    batch = [make()]
    with pytest.raises(OccurrenceError):
        memory.store.add('a', 'fixture', batch)


def test_an_analysis_keeps_its_snapshot(memory):
    memory.analysis('a', executions=[execution()])
    with pytest.raises(OccurrenceError):
        memory.store.record_snapshot('a', OTHER)


def test_an_execution_keeps_its_provenance(memory):
    memory.analysis('a', executions=[execution()])
    changed = execution(version='2.0.0')
    with pytest.raises(OccurrenceError):
        memory.store.record_execution('a', changed)


def test_facts_before_the_snapshot_are_refused(memory):
    batch = [assertion()]
    with pytest.raises(OccurrenceError):
        memory.store.add('nowhere', 'fixture', batch)


def test_evidence_does_not_repeat_repository_or_commit(memory):
    columns = {column['name'] for column in inspect(memory.engine).get_columns(FactEvidenceRow.__tablename__)}
    assert not columns & {'repository', 'commit'}


def test_same_spelling_whatever_came_first(memory):
    one, decimal = assertion(qualifiers={'weight': 1}), assertion(qualifiers={'weight': 1.0})
    for scan, fact in (('a', one), ('b', decimal)):
        memory.analysis(scan, executions=[execution()])
        memory.store.add(scan, 'fixture', [fact])
    assert memory.count(FactIdentityRow) == 1
    assert same(memory.store.query('a'), [one])
    assert same(memory.store.query('b'), [decimal])


def test_identity_hash_is_the_contract_identity(memory):
    memory.analysis('a', executions=[execution()])
    fact = assertion()
    memory.store.add('a', 'fixture', [fact])
    with Session(memory.engine) as db:
        assert db.scalar(select(FactIdentityRow.identity_hash)) == fact_identity(fact)


def test_concurrent_analyses_share_one_new_identity(memory):
    scans = [memory.analysis(f'scan-{index}', executions=[execution()]) for index in range(4)]
    errors = []

    def write(scan):
        try:
            memory.store.add(scan, 'fixture', [copy.deepcopy(assertion())])
        except Exception as error:  # the assertion below reports it
            errors.append(error)

    threads = [threading.Thread(target=write, args=(scan,)) for scan in scans]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert memory.count(FactIdentityRow) == 1
    assert memory.count(FactOccurrenceRow) == 4


def test_evaluator_execution_names_its_catalog():
    from app.evaluations.domain.evaluator import EvaluatorCatalog
    from app.evaluations.domain.execution import EvaluatorExecution
    from app.evaluations.domain.status import EvaluationStatus
    from app.snapshots.domain.snapshot import Snapshot

    snapshot = Snapshot('fixture', 'a' * 40, 'COMMIT', (), None)
    now = datetime.now(timezone.utc)
    run = EvaluatorExecution('run-1', 'fixture', '1.0.0', EvaluatorCatalog('fixture-rules', '1'), snapshot, now, now,
                             {'include': ['repository:fixture']}, EvaluationStatus.SUCCESS, coverage=({},))
    assert run.producer_execution() == execution()


def test_producer_execution_follows_the_contract():
    assert 'catalog_id' not in ProducerExecution('PROJECTION', 'tree', '1', 'run').produced_by()
    for invalid in (('HUMAN', 'someone', '1', 'run'), ('EVALUATOR', 'fixture', '1', 'run'),
                    ('PROJECTION', 'tree', '1', 'run', 'catalog', '1'), ('EVALUATOR', '', '1', 'run', 'c', '1')):
        with pytest.raises(ValueError):
            ProducerExecution(*invalid)
