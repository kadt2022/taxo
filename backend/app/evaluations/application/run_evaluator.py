from uuid import uuid4

from app.evaluations.domain.execution import EvaluatorExecution
from app.evaluations.domain.status import EvaluationStatus
from app.facts import validate_fact


class RunEvaluator:
    def __init__(self, validator=validate_fact):
        self.validator = validator

    def __call__(self, evaluator, snapshot):
        execution_id = str(uuid4())
        try:
            output = evaluator.evaluate(snapshot)
            facts = tuple(self._with_provenance(fact, evaluator, snapshot, execution_id)
                          for fact in output.facts)
            coverage = tuple(self._with_provenance(fact, evaluator, snapshot, execution_id)
                             for fact in output.coverage)
            for fact in (*facts, *coverage):
                self.validator(fact)
            return EvaluatorExecution(
                execution_id, evaluator.evaluator_id, evaluator.producer_version,
                evaluator.catalog, snapshot, output.status, facts, coverage,
                output.warnings, output.legacy)
        except Exception as exc:
            return EvaluatorExecution(
                execution_id, evaluator.evaluator_id, evaluator.producer_version,
                evaluator.catalog, snapshot, EvaluationStatus.FAILED,
                warnings=(f'{type(exc).__name__}: {exc}',))

    @staticmethod
    def _with_provenance(fact, evaluator, snapshot, execution_id):
        result = {**fact}
        result['snapshot'] = snapshot.reference()
        result['produced_by'] = {
            'producer_type': 'EVALUATOR',
            'producer_id': evaluator.evaluator_id,
            'producer_version': evaluator.producer_version,
            'execution_id': execution_id,
            'catalog_id': evaluator.catalog.catalog_id,
            'catalog_version': evaluator.catalog.catalog_version,
        }
        return result
