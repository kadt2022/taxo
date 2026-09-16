from dataclasses import replace

import pytest

from app.evaluations.application.registry import EvaluatorRegistry
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.evaluator import EvaluationOutput, EvaluatorCatalog
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.facts import fact_identity
from app.snapshots.domain.mode import COMMIT
from app.snapshots.domain.snapshot import Snapshot, SnapshotFile


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
        return EvaluationOutput(status=self.status)


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


def test_registry_is_explicit_deterministic_and_rejects_duplicates():
    registry = EvaluatorRegistry([DummyEvaluator()])
    assert [e.evaluator_id for e in registry.all()] == ['taxo.dummy']
    assert registry.get('taxo.dummy').evaluator_id == 'taxo.dummy'
    with pytest.raises(ValueError, match='existe déjà'):
        registry.register(DummyEvaluator())


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
    assert execution.facts and execution.coverage
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


def test_invalid_manifest_is_partial_with_not_interpreted_coverage():
    class Content:
        def read_many(self, paths):
            values = {'package.json': b'{broken'}
            for path in paths:
                yield path, values[path]

    current = Snapshot('project-key', 'a' * 40, COMMIT,
                       (SnapshotFile('package.json', 7),), content=Content())
    execution = RunEvaluator()(InventoryEvaluator(), current)
    assert execution.status is EvaluationStatus.PARTIAL
    assert [item['coverage_type'] for item in execution.coverage] == ['ANALYSED', 'NOT_INTERPRETED']
