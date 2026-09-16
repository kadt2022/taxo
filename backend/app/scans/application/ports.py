from typing import Protocol
from app.scans.domain.scan import Scan
from app.snapshots.domain.snapshot import Snapshot

class ScanRepository(Protocol):
    def list(self, project_id: str) -> list[Scan]: ...
    def add(self, scan: Scan) -> Scan: ...

class Inventory(Protocol):
    def __call__(self, snapshot: Snapshot) -> dict: ...
