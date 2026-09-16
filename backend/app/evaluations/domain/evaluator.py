from dataclasses import dataclass, field
from typing import Any, Protocol

from app.evaluations.domain.status import EvaluationStatus
from app.snapshots.domain.snapshot import Snapshot


@dataclass(frozen=True)
class EvaluatorCatalog:
    catalog_id: str
    catalog_version: str
    relations: tuple[str, ...] = ()
    coverage_types: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.catalog_id.strip() or not self.catalog_version.strip():
            raise ValueError('Le catalogue doit avoir une identité stable.')
        if tuple(sorted(self.relations)) != self.relations:
            raise ValueError('Les relations du catalogue doivent être triées.')
        if tuple(sorted(self.coverage_types)) != self.coverage_types:
            raise ValueError('Les couvertures du catalogue doivent être triées.')


@dataclass(frozen=True)
class EvaluationOutput:
    facts: tuple[dict[str, Any], ...] = ()
    coverage: tuple[dict[str, Any], ...] = ()
    status: EvaluationStatus = EvaluationStatus.SUCCESS
    warnings: tuple[str, ...] = ()
    legacy: dict[str, Any] = field(default_factory=dict)


class Evaluator(Protocol):
    evaluator_id: str
    producer_version: str
    catalog: EvaluatorCatalog

    def evaluate(self, snapshot: Snapshot) -> EvaluationOutput: ...
