import inspect
from datetime import datetime, timezone
from uuid import uuid4

from app.evaluations.domain.capability import unsupported_reason
from app.evaluations.domain.execution import EvaluatorExecution
from app.evaluations.domain.status import EvaluationStatus
from app.facts import validate_fact


class RunEvaluator:
    def __init__(self, validator=validate_fact):
        self.validator = validator

    def __call__(self, evaluator, snapshot, progress=None):
        execution_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        repository = f'repository:{snapshot.repository}'
        scope = {'include': [repository], 'exclude': []}
        try:
            # Un evaluateur qui sait rapporter sa progression la recoit ; les autres sont appeles comme avant.
            if progress is not None and 'progress' in inspect.signature(evaluator.evaluate).parameters:
                output = evaluator.evaluate(snapshot, progress=progress)
            else:
                output = evaluator.evaluate(snapshot)
            facts = tuple(self._with_provenance(fact, evaluator, snapshot, execution_id)
                          for fact in output.facts)
            coverage = tuple(self._with_provenance(fact, evaluator, snapshot, execution_id)
                             for fact in output.coverage)
            if not coverage:
                raise ValueError("L'évaluateur doit déclarer au moins une couverture.")
            if any(fact.get('kind') != 'COVERAGE' for fact in coverage):
                raise ValueError("output.coverage ne peut contenir que des faits COVERAGE.")
            if any(fact.get('kind') == 'COVERAGE' for fact in facts):
                raise ValueError("Les faits COVERAGE doivent être placés dans output.coverage.")
            for fact in (*facts, *coverage):
                self.validator(fact)
            declared_scope = next((fact['scope'] for fact in coverage
                                   if fact['subject'] == repository), scope)
            scope = {'include': declared_scope['include'], 'exclude': declared_scope.get('exclude', [])}
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

    def unsupported(self, evaluator, snapshot):
        """L'execution d'un analyseur qui ne lit aucun langage present (TAXO-COV-01) : il n'est pas appele.
        Sa seule couverture dit que le depot est hors de son perimetre, et pourquoi ; jamais `ANALYSED`."""
        execution_id, now = str(uuid4()), datetime.now(timezone.utc)
        repository = f'repository:{snapshot.repository}'
        scope = {'include': [repository], 'exclude': []}
        coverage = self._with_provenance({
            'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': repository, 'coverage_type': 'OUT_OF_SCOPE', 'scope': scope,
            'reason': unsupported_reason(evaluator.catalog.languages),
        }, evaluator, snapshot, execution_id)
        self.validator(coverage)
        return EvaluatorExecution(
            execution_id, evaluator.evaluator_id, evaluator.producer_version, evaluator.catalog, snapshot,
            now, now, scope, EvaluationStatus.UNSUPPORTED, coverage=(coverage,))

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
