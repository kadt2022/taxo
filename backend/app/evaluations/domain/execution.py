from collections import Counter
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

    def summary(self):
        coverage_counts = Counter()
        coverage_subjects = {}
        for fact in self.coverage:
            coverage_type = fact['coverage_type']
            coverage_counts[coverage_type] += 1
            subjects = coverage_subjects.setdefault(coverage_type, [])
            if len(subjects) < 5 and fact['subject'] not in subjects:
                subjects.append(fact['subject'])
        return {
            'execution_id': self.execution_id,
            'evaluator_id': self.evaluator_id,
            'producer_version': self.producer_version,
            'status': self.status.value,
            'started_at': self.started_at.isoformat(),
            'finished_at': self.finished_at.isoformat(),
            'duration_seconds': round((self.finished_at - self.started_at).total_seconds(), 3),
            'fact_count': len(self.facts),
            'coverage_count': len(self.coverage),
            'warning_count': len(self.warnings),
            'relations': dict(sorted(Counter(fact['relation'] for fact in self.facts).items())),
            'coverage': [
                {'coverage_type': kind, 'count': coverage_counts[kind], 'subjects': coverage_subjects[kind]}
                for kind in sorted(coverage_counts)
            ],
            'snapshot': self.snapshot.reference(),
        }

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
