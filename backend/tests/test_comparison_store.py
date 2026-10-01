"""Every comparison category, from facts written directly into the memory (SQLite, and PostgreSQL in CI).

The Git bench cannot produce a status change or a change in the number of occurrences: these facts are
built by hand, so the expected answer is known before Taxo computes it.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.comparison.application.compare import CompareAnalyses
from app.facts.contract import validate_fact
from app.facts.domain.provenance import ProducerExecution
from app.projects.infrastructure.sqlalchemy.project_repository import ProjectRow, SqlAlchemyProjectRepository
from app.scans.infrastructure.sqlalchemy.fact_comparison import SqlAlchemyComparisonStore
from app.scans.infrastructure.sqlalchemy.fact_memory import SqlAlchemyFactMemory
from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow, SqlAlchemyScanRepository
from storage_engines import fresh_engine

HUMAN = 'reviewer@example.invalid'


def snapshot(commit):
    return {'repository': 'fixture', 'commit': commit * 40, 'mode': 'COMMIT'}


def run(commit, version='1.0.0'):
    return ProducerExecution('EVALUATOR', 'fixture', version, f'run-{commit}', 'fixture-rules', '1')


def edge(commit, target, relation='DEPENDS_ON', line=1, validity='VALID', subject='module:root', **extra):
    state = snapshot(commit)
    fact = {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': validity,
            'subject': subject, 'relation': relation, 'object': target, 'qualifiers': {},
            'snapshot': state, 'produced_by': run(commit).produced_by(),
            'evidence': [{'repository': 'fixture', 'commit': state['commit'], 'path': 'build.gradle',
                          'line_start': line, 'line_end': line, 'method': 'fixture.build',
                          'content_hash': 'sha256:' + 'b' * 64}], **extra}
    validate_fact(fact, submission=validity == 'VALID')
    return fact


@pytest.fixture
def compared(tmp_path):
    engine = fresh_engine(tmp_path)
    memory = SqlAlchemyFactMemory(engine)
    with Session(engine) as db:
        db.add(ProjectRow(id='project', name='fixture', path='/fixture'))
        for scan_id, commit in (('before', 'a'), ('after', 'c')):
            db.add(ScanRow(id=scan_id, project_id='project', created_at=datetime.now(timezone.utc), result={
                'memory': 'COMPLETE', 'evaluations': [{'execution_id': f'run-{commit}', 'evaluator_id': 'fixture',
                                                       'status': 'SUCCESS'}]}))
        db.commit()
    for scan_id, commit in (('before', 'a'), ('after', 'c')):
        memory.record_snapshot(scan_id, snapshot(commit))
        memory.record_execution(scan_id, run(commit))
    memory.add('before', 'fixture', [
        edge('a', 'module:kept'), edge('a', 'module:moved', line=1), edge('a', 'module:gone', subject='module:left'),
        edge('a', 'module:old', 'CONTAINS', subject='module:slot'), edge('a', 'module:twice'),
        edge('a', 'module:twice', line=2), edge('a', 'module:aged', subject='module:aging'),
        edge('a', 'module:caf\u00e9', subject='module:spelling')])
    memory.add('after', 'fixture', [
        edge('c', 'module:kept'), edge('c', 'module:moved', line=9), edge('c', 'module:new', subject='module:right'),
        edge('c', 'module:fresh', 'CONTAINS', subject='module:slot'), edge('c', 'module:twice'),
        edge('c', 'module:aged', subject='module:aging', validity='STALE'),
        edge('c', 'module:cafe\u0301', subject='module:spelling')])
    compare = CompareAnalyses(SqlAlchemyProjectRepository(engine), SqlAlchemyScanRepository(engine),
                              SqlAlchemyComparisonStore(engine))
    yield compare
    engine.dispose()


def objects(compare, category, side):
    page = compare.changes('project', 'before', 'after', category, 'fixture', limit=200)
    return sorted(fact['object'] for item in page['items'] for fact in item[side])


def test_every_category_is_counted_from_the_memory(compared):
    [entry] = compared.summary('project', 'before', 'after')['evaluators']
    assert entry['comparable']
    assert entry['counts'] == {'ADDED': 1, 'REMOVED': 1, 'MODIFIED': 1, 'EVIDENCE_CHANGED': 1, 'STATUS_CHANGED': 1,
                               'OCCURRENCE_COUNT_CHANGED': 1, 'OCCURRENCES_CHANGED': 1, 'UNCHANGED': 5}


def test_each_category_lists_its_own_facts(compared):
    assert objects(compared, 'ADDED', 'after') == ['module:new']
    assert objects(compared, 'REMOVED', 'before') == ['module:gone']
    assert objects(compared, 'MODIFIED', 'before') == ['module:old']
    assert objects(compared, 'MODIFIED', 'after') == ['module:fresh']
    [moved] = compared.changes('project', 'before', 'after', 'EVIDENCE_CHANGED', 'fixture')['items']
    assert (moved['before'][0]['evidence'][0]['line_start'], moved['after'][0]['evidence'][0]['line_start']) == (1, 9)
    [aged] = compared.changes('project', 'before', 'after', 'STATUS_CHANGED', 'fixture')['items']
    assert (aged['before'][0]['validity'], aged['after'][0]['validity']) == ('VALID', 'STALE')
    [twice] = compared.changes('project', 'before', 'after', 'OCCURRENCE_COUNT_CHANGED', 'fixture')['items']
    assert (len(twice['before']), len(twice['after'])) == (2, 1)


def test_pages_follow_each_other_without_loss(compared):
    seen, cursor = [], None
    while True:
        page = compared.changes('project', 'before', 'after', 'REMOVED', 'fixture', cursor, limit=1)
        seen += [fact['object'] for item in page['items'] for fact in item['before']]
        cursor = page['next']
        if cursor is None:
            break
    assert seen == ['module:gone']


def test_a_change_of_occurrence_content_is_never_silent(compared):
    """Same identity, other spelling of the object: the occurrence says something else."""
    [spelled] = compared.changes('project', 'before', 'after', 'OCCURRENCES_CHANGED', 'fixture')['items']
    assert (spelled['before'][0]['object'], spelled['after'][0]['object']) == ('module:caf\u00e9', 'module:cafe\u0301')


def test_following_pages_never_read_the_analyses_again(compared, monkeypatch):
    calls = []
    for name in ('only', 'common'):
        original = getattr(compared.store, name)
        monkeypatch.setattr(compared.store, name,
                            lambda *args, _original=original, _name=name: calls.append(_name) or _original(*args))
    compared.summary('project', 'before', 'after')
    first = len(calls)
    for category in ('ADDED', 'REMOVED', 'EVIDENCE_CHANGED'):
        compared.changes('project', 'before', 'after', category, 'fixture', limit=1)
    assert first == 3
    assert len(calls) == first
