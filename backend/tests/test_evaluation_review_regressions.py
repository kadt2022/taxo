import pytest

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.evaluator import EvaluationOutput, EvaluatorCatalog
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.projects.domain.project import Project
from app.scans.application.run_scan import RunScan
from app.scans.domain.scan import ScanError
from app.snapshots.domain.errors import GIT_READ_ERROR, SnapshotError
from app.snapshots.domain.mode import COMMIT
from app.snapshots.domain.snapshot import Snapshot, SnapshotFile


class EmptyContent:
    def read_many(self, paths):
        yield from ()


def empty_snapshot(*, skipped=()):
    return Snapshot('project-key', 'a' * 40, COMMIT, (), content=EmptyContent(), skipped=skipped)


def test_failed_evaluation_is_not_persisted_as_successful_scan():
    class Projects:
        def get(self, project_id):
            return Project(project_id, 'demo', 'logical-location')

    class Paths:
        def resolve(self, value):
            return value

    class Reader:
        def open(self, *args):
            return empty_snapshot()

    class Scans:
        def add(self, scan):
            pytest.fail('A FAILED evaluator execution must never be persisted')

    class FailedExecution:
        status = EvaluationStatus.FAILED
        warnings = ('ValueError: Projet trop volumineux : limite de 50 000 fichiers.',)

        def summary(self):
            return {'status': 'FAILED'}

    class Runner:
        def __call__(self, evaluator, snapshot, progress=None):
            return FailedExecution()

    run = RunScan(Projects(), Scans(), Paths(), Reader(), object(), Runner())
    with pytest.raises(ScanError, match='Projet trop volumineux'):
        run('project-key')


def test_run_evaluator_rejects_non_coverage_items_in_coverage_collection():
    class BadEvaluator:
        evaluator_id = 'taxo.bad'
        producer_version = '1.0.0'
        catalog = EvaluatorCatalog('bad', '1', (), ('ANALYSED',))

        def evaluate(self, snapshot):
            return EvaluationOutput(coverage=({'kind': 'ASSERTION'},))

    execution = RunEvaluator()(BadEvaluator(), empty_snapshot())

    assert execution.status is EvaluationStatus.FAILED
    assert execution.coverage[0]['kind'] == 'COVERAGE'
    assert any('output.coverage' in warning for warning in execution.warnings)


def test_summary_accepts_contract_valid_absence_facts_without_relation():
    class AbsenceEvaluator:
        evaluator_id = 'taxo.absence'
        producer_version = '1.0.0'
        catalog = EvaluatorCatalog('absence', '1', (), ('ANALYSED',))

        def evaluate(self, snapshot):
            repository = f'repository:{snapshot.repository}'
            absence = {
                'contract_version': 1,
                'kind': 'ABSENCE',
                'status': 'OBSERVED',
                'validity': 'VALID',
                'pattern': {'type': 'relation', 'value': 'CALLS'},
                'scope': {'include': [repository]},
                'method': 'exhaustive-search',
            }
            coverage = {
                'contract_version': 1,
                'kind': 'COVERAGE',
                'status': 'OBSERVED',
                'validity': 'VALID',
                'subject': repository,
                'coverage_type': 'ANALYSED',
                'scope': {'include': [repository]},
            }
            return EvaluationOutput(facts=(absence,), coverage=(coverage,))

    execution = RunEvaluator()(AbsenceEvaluator(), empty_snapshot())
    summary = execution.summary()

    assert execution.status is EvaluationStatus.SUCCESS
    assert summary['fact_count'] == 1
    assert summary['relations'] == {}


def test_read_error_declares_gap_coverage_for_every_unattempted_suffix_path():
    class FailingContent:
        def read_many(self, paths):
            for path in paths:
                if path == 'unreadable.py':
                    raise SnapshotError(GIT_READ_ERROR, 'Objet Git illisible.')
                yield path, b'print(1)\n'

    current = Snapshot(
        'project-key',
        'a' * 40,
        COMMIT,
        (
            SnapshotFile('good.py', 9),
            SnapshotFile('unreadable.py', 9),
            SnapshotFile('not-attempted.py', 9),
        ),
        content=FailingContent(),
    )

    execution = RunEvaluator()(InventoryEvaluator(), current)
    read_errors = {
        item['subject']
        for item in execution.coverage
        if item['coverage_type'] == 'READ_ERROR'
    }

    assert execution.status is EvaluationStatus.PARTIAL
    assert read_errors == {'file:unreadable.py', 'file:not-attempted.py'}
    assert any(fact['subject'] == 'file:good.py' for fact in execution.facts)


def test_snapshot_skipped_entries_are_excluded_from_repository_scope():
    class Content:
        def read_many(self, paths):
            for path in paths:
                yield path, b'print(1)\n'

    current = Snapshot(
        'project-key',
        'a' * 40,
        COMMIT,
        (SnapshotFile('good.py', 9),),
        content=Content(),
        skipped=(('.env', 'confidential'), ('link.py', 'symlink'), ('vendor', 'submodule')),
    )

    execution = RunEvaluator()(InventoryEvaluator(), current)

    assert execution.status is EvaluationStatus.SUCCESS
    assert execution.scope['exclude'] == ['directory:vendor', 'file:.env', 'file:link.py']
    assert execution.coverage[0]['scope']['exclude'] == execution.scope['exclude']
