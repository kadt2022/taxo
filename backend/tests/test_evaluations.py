from dataclasses import replace

import pytest

from app.evaluations.application.registry import EvaluatorRegistry
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.evaluator import EvaluationOutput, EvaluatorCatalog
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.inventory.evaluator import InventoryEvaluator, MAX_MANIFEST_BYTES
from app.facts import fact_identity, validate_fact
from app.snapshots.domain.mode import COMMIT
from app.snapshots.domain.snapshot import Snapshot, SnapshotFile
from app.snapshots.domain.errors import GIT_READ_ERROR, SnapshotError


CATALOG = EvaluatorCatalog('dummy', '1', ('CONTAINS',), ('ANALYSED',))


class DummyEvaluator:
    evaluator_id = 'taxo.dummy'
    producer_version = '1.0.0'
    catalog = CATALOG

    def __init__(self, status=EvaluationStatus.SUCCESS):
        self.status = status

    def evaluate(self, snapshot):
        if self.status is EvaluationStatus.FAILED:
            raise RuntimeError('broken evaluator')
        coverage = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED',
                    'validity': 'VALID', 'subject': f'repository:{snapshot.repository}',
                    'coverage_type': 'ANALYSED',
                    'scope': {'include': [f'repository:{snapshot.repository}']}}
        return EvaluationOutput(coverage=(coverage,), status=self.status)


def snapshot():
    class EmptyContent:
        def read_many(self, paths):
            yield from ()
    return Snapshot('project-key', 'a' * 40, COMMIT, (), content=EmptyContent())


@pytest.mark.parametrize('status', EvaluationStatus)
def test_run_evaluator_preserves_all_technical_statuses(status):
    execution = RunEvaluator()(DummyEvaluator(status), snapshot())
    expected = EvaluationStatus.FAILED if status is EvaluationStatus.FAILED else status
    assert execution.status is expected
    assert execution.started_at.tzinfo is not None
    assert execution.started_at <= execution.finished_at
    assert execution.scope == {'include': ['repository:project-key'], 'exclude': []}
    assert execution.coverage
    assert execution.result()['scope'] == execution.scope


def test_missing_coverage_is_failed_with_declared_fallback():
    evaluator = DummyEvaluator()
    evaluator.evaluate = lambda _snapshot: EvaluationOutput()
    execution = RunEvaluator()(evaluator, snapshot())
    assert execution.status is EvaluationStatus.FAILED
    assert len(execution.coverage) == 1
    assert execution.coverage[0]['coverage_type'] == 'NOT_INTERPRETED'
    validate_fact(execution.coverage[0])
    with pytest.raises(ValueError, match='déclarer sa couverture'):
        replace(execution, coverage=())


def test_execution_summary_aggregates_facts_and_bounds_coverage_subjects():
    execution = RunEvaluator()(DummyEvaluator(), snapshot())
    facts = tuple({'kind': 'ASSERTION', 'relation': relation}
                  for relation in ('CONTAINS', 'CONTAINS', 'WRITTEN_IN'))
    coverage = tuple({'coverage_type': 'NOT_INTERPRETED', 'subject': f'file:{index}.py'}
                     for index in range(7))
    execution = replace(execution, facts=facts, coverage=coverage, warnings=('unreadable',))

    summary = execution.summary()
    assert summary['execution_id'] == execution.execution_id
    assert summary['status'] == 'SUCCESS'
    assert summary['fact_count'] == 3
    assert summary['coverage_count'] == 7
    assert summary['warning_count'] == 1
    assert summary['relations'] == {'CONTAINS': 2, 'WRITTEN_IN': 1}
    assert summary['coverage'] == [{
        'coverage_type': 'NOT_INTERPRETED', 'count': 7,
        'subjects': [f'file:{index}.py' for index in range(5)]}]
    assert summary['snapshot']['commit'] == 'a' * 40
    assert summary['duration_seconds'] >= 0
    assert 'facts' not in summary


def test_registry_is_explicit_deterministic_and_rejects_duplicates():
    registry = EvaluatorRegistry([DummyEvaluator()])
    assert [e.evaluator_id for e in registry.all()] == ['taxo.dummy']
    assert registry.get('taxo.dummy').evaluator_id == 'taxo.dummy'
    duplicate = DummyEvaluator()
    with pytest.raises(ValueError, match='existe déjà'):
        registry.register(duplicate)


def test_inventory_produces_contract_facts_coverage_and_provenance():
    class Content:
        def read_many(self, paths):
            values = {'App.tsx': b'export const App = 1\n',
                      'package.json': b'{"dependencies":{"react":"19"}}'}
            for path in paths:
                yield path, values[path]

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       (SnapshotFile('App.tsx', 21), SnapshotFile('package.json', 43)),
                       content=Content())
    execution = RunEvaluator()(InventoryEvaluator(), current)
    assert execution.status is EvaluationStatus.SUCCESS
    assert execution.facts
    assert execution.coverage
    assert {fact['relation'] for fact in execution.facts} == {
        'CONTAINS', 'WRITTEN_IN', 'USES_TECHNOLOGY', 'DECLARED_BY'}
    assert {fact['coverage_type'] for fact in execution.coverage} == {'ANALYSED'}
    assert all(fact['produced_by']['execution_id'] == execution.execution_id
               for fact in (*execution.facts, *execution.coverage))
    assert all(fact['snapshot']['repository'] == 'project-key'
               for fact in (*execution.facts, *execution.coverage))


def test_inventory_fact_identities_are_reproducible():
    class Content:
        def read_many(self, paths):
            values = {'App.tsx': b'export const App = 1\n'}
            for path in paths:
                yield path, values[path]

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       (SnapshotFile('App.tsx', 21),), content=Content())
    first = RunEvaluator()(InventoryEvaluator(), current)
    second = RunEvaluator()(InventoryEvaluator(), current)
    assert first.execution_id != second.execution_id
    assert [fact_identity(fact) for fact in first.facts] == [fact_identity(fact) for fact in second.facts]
    assert [fact['coverage_type'] for fact in first.coverage] == [fact['coverage_type'] for fact in second.coverage]


def test_inventory_coverage_excludes_ignored_directories():
    requested = []

    class Content:
        def read_many(self, paths):
            for path in paths:
                requested.append(path)
                yield path, b'print(1)\n'

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       tuple(SnapshotFile(path, 9) for path in (
                           'build/generated.py', 'node_modules/hidden.py',
                           'src/target/Generated.java', 'src/good.py')),
                       content=Content())
    execution = RunEvaluator()(InventoryEvaluator(), current)

    assert execution.status is EvaluationStatus.SUCCESS
    assert requested == ['src/good.py']
    assert execution.scope['exclude'] == [
        'directory:build', 'directory:node_modules', 'directory:src/target']
    assert execution.coverage[0]['coverage_type'] == 'ANALYSED'
    assert execution.coverage[0]['scope'] == execution.scope
    assert execution.legacy['files_count'] == 1
    assert all(evidence['path'] == 'src/good.py'
               for fact in execution.facts for evidence in fact['evidence'])


@pytest.mark.parametrize('bad_path', ['bad:name.py', 'bad\\name.py', 'bad\nname.py'])
def test_contract_invalid_git_path_does_not_fail_inventory(bad_path):
    requested = []

    class Content:
        def read_many(self, paths):
            for path in paths:
                requested.append(path)
                yield path, b'print(1)\n'

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       (SnapshotFile('good.py', 9), SnapshotFile(bad_path, 9)),
                       content=Content())
    execution = RunEvaluator()(InventoryEvaluator(), current)

    assert execution.status is EvaluationStatus.SUCCESS
    assert requested == ['good.py']
    assert any(fact['subject'] == 'file:good.py' for fact in execution.facts)
    assert all(evidence['path'] != bad_path
               for fact in execution.facts for evidence in fact['evidence'])
    assert any('Chemin Git non représentable comme preuve' in warning
               for warning in execution.warnings)
    assert execution.coverage[0]['coverage_type'] == 'NOT_INTERPRETED'
    assert execution.coverage[0]['subject'] == 'repository:project-key'
    for fact in (*execution.facts, *execution.coverage):
        validate_fact(fact)


def test_invalid_manifest_is_success_with_not_interpreted_coverage():
    class Content:
        def read_many(self, paths):
            values = {'package.json': b'{broken'}
            for path in paths:
                yield path, values[path]

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       (SnapshotFile('package.json', 7),), content=Content())
    execution = RunEvaluator()(InventoryEvaluator(), current)
    assert execution.status is EvaluationStatus.SUCCESS
    assert [item['coverage_type'] for item in execution.coverage] == ['ANALYSED', 'NOT_INTERPRETED']


@pytest.mark.parametrize('unreadable_path', ['logo.png', 'legacy.py', 'package.json'])
def test_non_utf8_file_does_not_discard_other_inventory_facts(unreadable_path):
    values = {'App.tsx': b'export const App = 1\n', unreadable_path: b'\x89PNG\r\n\xff'}

    class Content:
        def read_many(self, paths):
            for path in paths:
                yield path, values[path]

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       tuple(SnapshotFile(path, len(data)) for path, data in values.items()),
                       content=Content())
    execution = RunEvaluator()(InventoryEvaluator(), current)
    assert execution.status is EvaluationStatus.SUCCESS
    assert any(fact['relation'] == 'WRITTEN_IN' and fact['subject'] == 'file:App.tsx'
               for fact in execution.facts)
    assert all(evidence['path'] != unreadable_path
               for fact in execution.facts for evidence in fact['evidence'])
    assert any(item['subject'] == f'file:{unreadable_path}' and item['coverage_type'] == 'NOT_INTERPRETED'
               for item in execution.coverage)
    assert execution.legacy['files_count'] == 2
    for fact in (*execution.facts, *execution.coverage):
        validate_fact(fact)


def test_size_limit_is_enforced_before_reading_any_file():
    oversized = ('package.json', 'archive.bin', 'generated.py')
    requested = []
    data = b'print(1)\n'

    class Content:
        def read_many(self, paths):
            for path in paths:
                assert path not in oversized, 'Oversized content must never be requested'
                requested.append(path)
                yield path, data

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       tuple(SnapshotFile(path, MAX_MANIFEST_BYTES + 1) for path in oversized)
                       + (SnapshotFile('main.py', len(data)),), content=Content())
    execution = RunEvaluator()(InventoryEvaluator(), current)
    assert requested == ['main.py']
    assert execution.status is EvaluationStatus.SUCCESS
    assert {item['subject'] for item in execution.coverage if item['coverage_type'] == 'NOT_INTERPRETED'} == {
        f'file:{path}' for path in oversized}
    assert any(fact['object'] == 'file:main.py' for fact in execution.facts)
    assert all(evidence['path'] == 'main.py' for fact in execution.facts for evidence in fact['evidence'])


def test_inventory_releases_file_contents_while_reading():
    class TrackedBytes(bytes):
        live = 0

        def __new__(cls):
            instance = super().__new__(cls, b'print(1)\n')
            cls.live += 1
            return instance

        def __del__(self):
            type(self).live -= 1

    class Content:
        def read_many(self, paths):
            for path in paths:
                assert TrackedBytes.live <= 1, 'Previous file contents are retained'
                yield path, TrackedBytes()

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       tuple(SnapshotFile(f'file{index}.py', 9) for index in range(4)),
                       content=Content())
    output = InventoryEvaluator().evaluate(current)
    assert output.status is EvaluationStatus.SUCCESS
    assert len([fact for fact in output.facts if fact['relation'] == 'CONTAINS']) == 4
    assert TrackedBytes.live == 0


def test_read_error_is_partial_with_read_error_coverage():
    class Content:
        def read_many(self, paths):
            for path in paths:
                if path == 'unreadable.py':
                    raise SnapshotError(GIT_READ_ERROR, 'Objet Git illisible.')
                yield path, b'print(1)\n'

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       (SnapshotFile('good.py', 9), SnapshotFile('unreadable.py', 9)),
                       content=Content())
    execution = RunEvaluator()(InventoryEvaluator(), current)
    assert execution.status is EvaluationStatus.PARTIAL
    assert any(item['subject'] == 'file:unreadable.py' and item['coverage_type'] == 'READ_ERROR'
               for item in execution.coverage)
    assert any(fact['subject'] == 'file:good.py' for fact in execution.facts)
    for item in execution.coverage:
        validate_fact(item)
