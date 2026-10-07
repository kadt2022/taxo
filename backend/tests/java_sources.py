"""Un instantane en memoire, fait de sources ecrites dans le test, pour les evaluateurs Java."""
from app.snapshots.domain.mode import COMMIT
from app.snapshots.domain.snapshot import Snapshot, SnapshotFile


class Content:
    def __init__(self, files):
        self.files = files

    def read_many(self, paths):
        for path in paths:
            yield path, self.files[path]


def snapshot(files):
    encoded = {path: text.encode('utf-8') if isinstance(text, str) else text for path, text in files.items()}
    return Snapshot('depot', 'a' * 40, COMMIT, tuple(SnapshotFile(path, len(data)) for path, data in encoded.items()),
                    content=Content(encoded))
