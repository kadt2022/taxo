from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.evaluations.domain.evaluator import EvaluatorCatalog
from app.evaluations.domain.status import EvaluationStatus
from app.snapshots.domain.snapshot import Snapshot


@dataclass(frozen=True)
class EvaluatorExecution:
    execution_id: str
    evaluator_id: str
    producer_version: str
    catalog: EvaluatorCatalog
    snapshot: Snapshot
    started_at: datetime
    finished_at: datetime
    scope: dict
    status: EvaluationStatus
    facts: tuple[dict[str, Any], ...] = ()
    coverage: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    legacy: dict[str, Any] | None = None

    def __post_init__(self):
        if not self.coverage:
            raise ValueError("Une exécution d'évaluateur doit déclarer sa couverture.")

    def result(self):
        return {
            'execution_id': self.execution_id,
            'evaluator_id': self.evaluator_id,
            'producer_version': self.producer_version,
            'catalog_id': self.catalog.catalog_id,
            'catalog_version': self.catalog.catalog_version,
            'started_at': self.started_at.isoformat(),
            'finished_at': self.finished_at.isoformat(),
            'scope': self.scope,
            'status': self.status.value,
            'facts': list(self.facts),
            'coverage': list(self.coverage),
            'warnings': list(self.warnings),
        }
