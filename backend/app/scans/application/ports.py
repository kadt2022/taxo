from typing import Protocol
from app.evaluations.domain.evaluator import Evaluator
from app.evaluations.domain.execution import EvaluatorExecution
from app.scans.domain.scan import Scan
from app.snapshots.domain.snapshot import Snapshot

class ScanRepository(Protocol):
    def list(self, project_id: str) -> list[Scan]: ...
    def add(self, scan: Scan) -> Scan: ...

class EvaluationRunner(Protocol):
    def __call__(self, evaluator: Evaluator, snapshot: Snapshot) -> EvaluatorExecution: ...
