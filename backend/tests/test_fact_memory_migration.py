"""Migration 004 (TAXO-01E): analysis_facts copied into the versioned memory, verified, resumable.

Analyses are written through the current storage at revision 003, as Taxo does today; after the
migration, the new memory must give back exactly the same facts, filters and one-hop walks.
"""
from datetime import datetime, timezone
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, func, inspect, select, text, update
from sqlalchemy.orm import Session

from app.facts.contract import validate_fact
from app.facts.domain.provenance import ProducerExecution
from app.projects.infrastructure.sqlalchemy.project_repository import ProjectRow
from app.scans.domain.occurrence import same
from app.scans.infrastructure.sqlalchemy.fact_memory import (AnalysisSnapshotRow, FactIdentityRow,
                                                             FactOccurrenceRow, SqlAlchemyFactMemory)
from app.scans.infrastructure.sqlalchemy.fact_store import AnalysisFactRow, SqlAlchemyAnalysisFacts
from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow
from storage_engines import fresh_url

FIRST, SECOND = 'analysis-a', 'analysis-b'


def snapshot(commit):
    return {'repository': 'fixture', 'commit': commit * 40, 'mode': 'COMMIT'}


def runs(commit):
    return (ProducerExecution('EVALUATOR', 'fixture', '1.0.0', f'run-{commit}', 'fixture-rules', '1'),
            ProducerExecution('EVALUATOR', 'other', '2.0.0', f'other-{commit}', 'other-rules', '3'))


def facts_of(commit, shift=0, weight=1):
    state, (run, other) = snapshot(commit), runs(commit)

    def edge(subject, target, relation='DEPENDS_ON', proofs=1, producer=run, **extra):
        evidence = [{'repository': state['repository'], 'commit': state['commit'], 'path': 'build.gradle',
                     'line_start': line + shift, 'line_end': line + shift, 'method': 'fixture.build',
                     'content_hash': 'sha256:' + 'b' * 64} for line in range(1, proofs + 1)]
        fact = {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
                'subject': subject, 'relation': relation, 'object': target, 'qualifiers': {},
                'snapshot': dict(state), 'produced_by': producer.produced_by(), 'evidence': evidence, **extra}
        validate_fact(fact)
        return fact

    coverage = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                'subject': 'module:root', 'coverage_type': 'NOT_INTERPRETED', 'reason': 'fixture',
                'scope': {'include': ['module:root', 'module:a', 'module:root']},
                'snapshot': dict(state), 'produced_by': run.produced_by()}
    validate_fact(coverage)
    fixture = [edge('module:root', f'module:{index:02}') for index in reversed(range(12))]
    fixture += [edge('module:root', 'module:café', proofs=3), edge('module:a', 'module:root', 'CONTAINS'),
                edge('module:root', 'module:root', qualifiers={'weight': weight}),
                edge('module:' + 'l' * 6000, 'module:root'), coverage]
    others = [edge('module:b', 'module:root', producer=other), edge('module:b', 'module:café', producer=other)]
    return {'fixture': fixture, 'other': others}


def summary(commit):
    return {'evaluations': [{'execution_id': run.execution_id, 'evaluator_id': run.producer_id,
                             'producer_version': run.producer_version, 'snapshot': snapshot(commit)}
                            for run in runs(commit)]}


class Database:
    def __init__(self, tmp_path):
        self.url = fresh_url(tmp_path, 'migration')
        self.env = {**os.environ, 'DATABASE_URL': self.url}
        self.alembic('upgrade', '003')
        self.engine = create_engine(self.url)
        self.old, self.memory = SqlAlchemyAnalysisFacts(self.engine), SqlAlchemyFactMemory(self.engine)

    def alembic(self, action, target, check=True):
        return subprocess.run([sys.executable, '-m', 'alembic', action, target], env=self.env, check=check,
                              capture_output=True, text=True)

    def analysis(self, scan_id, commit, result=None, **facts):
        with Session(self.engine) as db:
            if db.get(ProjectRow, 'project') is None:
                db.add(ProjectRow(id='project', name='fixture', path='/fixture'))
            db.add(ScanRow(id=scan_id, project_id='project', created_at=datetime.now(timezone.utc),
                           result=summary(commit) if result is None else result))
            db.commit()
        for evaluator, batch in (facts or facts_of(commit)).items():
            self.old.add(scan_id, evaluator, batch)

    def count(self, row):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(row))


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path)
    yield db
    db.engine.dispose()


def walks(store, scan_id, facts):
    """Every one-hop walk of every anchor, relation and direction of the given facts."""
    found = {}
    for fact in facts:
        if fact['kind'] != 'ASSERTION':
            continue
        for direction, anchor in (('OUTGOING', fact['subject']), ('INCOMING', fact['object'])):
            key, after, walked = (anchor, fact['relation'], direction), '', []
            while (step := store.neighbor(scan_id, *key, after)) is not None:
                after = step[0]
                walked.append(step[1])
            found[key] = walked
    return found


def test_migration_gives_back_every_fact_filter_and_walk(database):
    database.analysis(FIRST, 'a')
    database.analysis(SECOND, 'c', **facts_of('c', shift=4, weight=1.0))
    before = database.count(AnalysisFactRow)
    output = database.alembic('upgrade', 'head').stdout
    assert 'Mesure : ratio occurrences / identités' in output
    assert database.count(AnalysisFactRow) == before
    assert database.count(FactOccurrenceRow) == before
    assert database.count(FactIdentityRow) < before  # both analyses share their identities
    for scan_id in (FIRST, SECOND):
        old = database.old.query(scan_id)
        assert same(database.memory.query(scan_id), old)
        for filters in ({'relation': 'CONTAINS'}, {'subject': 'module:root'}, {'evaluator_id': 'other'},
                        {'kind': 'COVERAGE'}, {'object': 'module:café'}, {'object': 'module:café'}):
            assert same(database.memory.query(scan_id, **filters), database.old.query(scan_id, **filters))
        assert walks(database.memory, scan_id, old) == walks(database.old, scan_id, old)
        assert database.memory.has_reference(scan_id, 'module:b')
        assert database.memory.revision(scan_id) > 0


def test_the_migrated_memory_keeps_accepting_facts(database):
    database.analysis(FIRST, 'a')
    database.alembic('upgrade', 'head')
    latest = database.memory.revision(FIRST)
    run = runs('a')[0]
    database.memory.record_snapshot(FIRST, snapshot('a'))
    database.memory.record_execution(FIRST, run)
    added = facts_of('a')['fixture'][0] | {'object': 'module:new'}
    database.memory.add(FIRST, 'fixture', [added])
    assert database.memory.revision(FIRST) > latest
    assert database.memory.query(FIRST)[-1] == added


def test_an_inconsistent_analysis_stops_and_the_next_run_resumes(database):
    database.analysis(FIRST, 'a')
    database.analysis(SECOND, 'c', result={'evaluations': summary('c')['evaluations'][:1]})
    failed = database.alembic('upgrade', 'head', check=False)
    assert failed.returncode != 0
    assert "l'exécution other-c n'est pas dans le résumé" in failed.stderr + failed.stdout
    assert 'Migration arrêtée' in failed.stderr + failed.stdout
    with database.engine.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '003'
    with Session(database.engine) as db:
        assert db.get(AnalysisSnapshotRow, FIRST) is not None
        assert db.get(AnalysisSnapshotRow, SECOND) is None
        assert db.scalar(select(func.count()).select_from(FactOccurrenceRow)
                         .where(FactOccurrenceRow.scan_id == SECOND)) == 0
        db.execute(update(ScanRow).where(ScanRow.id == SECOND).values(result=summary('c')))
        db.commit()
    resumed = database.alembic('upgrade', 'head').stdout
    assert 'analyse 1/2 : déjà migrée (reprise)' in resumed
    for scan_id in (FIRST, SECOND):
        assert same(database.memory.query(scan_id), database.old.query(scan_id))


def _other_snapshot(facts):
    moved = facts['fixture'][0]
    moved['snapshot'] = snapshot('d')
    moved['evidence'][0]['commit'] = 'd' * 40
    return facts


def _foreign_producer(facts):
    facts['fixture'].append(facts['other'].pop())
    return facts


def _lossy(facts):
    facts['fixture'][0]['evidence'][0]['note'] = 'unknown'
    return facts


def _two_provenances(facts):
    facts['fixture'][0]['produced_by']['catalog_version'] = '2'
    return facts


@pytest.mark.parametrize('damage,reason', [
    (_other_snapshot, "les faits n'ont pas tous le même instantané"),
    (_foreign_producer, "le producteur d'un fait n'est pas l'évaluateur"),
    (_lossy, 'une preuve porte un champ'),
    (_two_provenances, 'une même exécution porte deux provenances'),
], ids=['other-snapshot', 'foreign-producer', 'lossy', 'two-provenances'])
def test_what_cannot_be_migrated_stops_before_writing_it(database, damage, reason):
    database.analysis(FIRST, 'a', **damage(facts_of('a')))
    before = database.count(AnalysisFactRow)
    failed = database.alembic('upgrade', 'head', check=False)
    assert failed.returncode != 0
    assert reason in failed.stderr + failed.stdout
    assert database.count(AnalysisFactRow) == before
    assert database.count(FactOccurrenceRow) == 0
    assert database.count(AnalysisSnapshotRow) == 0


def test_an_index_missing_after_an_interruption_is_created_on_resume(database):
    database.analysis(FIRST, 'a')
    database.alembic('upgrade', 'head')
    with database.engine.begin() as connection:
        connection.execute(text('DROP INDEX ix_fact_occurrences_outgoing'))
        connection.execute(text("UPDATE alembic_version SET version_num = '003'"))
    resumed = database.alembic('upgrade', 'head').stdout
    assert 'déjà migrée (reprise)' in resumed
    assert 'ix_fact_occurrences_outgoing' in {index['name'] for index in inspect(database.engine).get_indexes(
        'fact_occurrences')}
    assert same(database.memory.query(FIRST), database.old.query(FIRST))


def test_downgrade_keeps_analysis_facts(database):
    database.analysis(FIRST, 'a')
    before = database.count(AnalysisFactRow)
    database.alembic('upgrade', 'head')
    database.alembic('downgrade', '003')
    assert database.count(AnalysisFactRow) == before
    with database.engine.connect() as connection:
        tables = connection.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name = 'fact_occurrences'")
                                    if database.engine.dialect.name == 'postgresql' else
                                    text("SELECT 1 FROM sqlite_master WHERE name = 'fact_occurrences'")).all()
    assert tables == []
