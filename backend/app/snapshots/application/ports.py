from typing import Protocol
from app.snapshots.domain.snapshot import Snapshot
from app.snapshots.domain.mode import COMMIT

class SnapshotReader(Protocol):
    def open(self, root, repository: str, mode=COMMIT, commit=None) -> Snapshot: ...
