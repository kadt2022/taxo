from datetime import datetime, timezone
from uuid import uuid4

from app.evaluations.domain.execution import EvaluatorExecution
from app.evaluations.domain.status import EvaluationStatus
from app.facts import validate_fact


class RunEvaluator:
    def __init__(self, validator=validate_fact):
        self.validator = validator

    def __call__(self, evaluator, snapshot):
        execution_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        repository = f'repository:{snapshot.repository}'
        scope = {'include': [repository], 'exclude': []}
        try:
            output = evaluator.evaluate(snapshot)
            facts = tuple(self._with_provenance(fact, evaluator, snapshot, execution_id)
                          for fact in output.facts)
            coverage = tuple(self._with_provenance(fact, evaluator, snapshot, execution_id)
                             for fact in output.coverage)
            if not coverage:
                raise ValueError("L'évaluateur doit déclarer au moins une couverture.")
            for fact in (*facts, *coverage):
                self.validator(fact)
            return EvaluatorExecution(
                execution_id, evaluator.evaluator_id, evaluator.producer_version,
                evaluator.catalog, snapshot, started_at, datetime.now(timezone.utc),
                scope, output.status, facts, coverage,
                output.warnings, output.legacy)
        except Exception as exc:
            fallback = self._with_provenance({
                'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED',
                'validity': 'VALID', 'subject': repository,
                'coverage_type': 'NOT_INTERPRETED', 'scope': scope,
            }, evaluator, snapshot, execution_id)
            self.validator(fallback)
            return EvaluatorExecution(
                execution_id, evaluator.evaluator_id, evaluator.producer_version,
                evaluator.catalog, snapshot, started_at, datetime.now(timezone.utc),
                scope, EvaluationStatus.FAILED, coverage=(fallback,),
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
