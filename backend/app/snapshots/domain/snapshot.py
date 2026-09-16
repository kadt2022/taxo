from dataclasses import dataclass, field
from typing import Iterable, Iterator, Protocol

class SnapshotContent(Protocol):
    def read_many(self, paths: Iterable[str]) -> Iterator[tuple[str, bytes]]: ...

@dataclass(frozen=True)
class SnapshotFile:
    path: str
    size: int


@dataclass(frozen=True)
class Snapshot:
    repository: str
    commit: str
    mode: str
    files: tuple[SnapshotFile, ...] = field(repr=False)
    content_fingerprint: str | None = None
    dirty: bool | None = None
    skipped: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    content: SnapshotContent | None = field(default=None, repr=False, compare=False)

    def iter_files(self):
        return iter(self.files)

    def read_bytes(self, path):
        return next(self.read_many([path]))[1]

    def read_many(self, paths):
        """Yield (path, bytes) in order through the snapshot's content port."""
        yield from self.content.read_many(paths)

    def reference(self):
        """Snapshot fields of the fact contract (ADR 0002)."""
        reference = {'repository': self.repository, 'commit': self.commit, 'mode': self.mode}
        if self.content_fingerprint:
            reference['content_fingerprint'] = self.content_fingerprint
        return reference
