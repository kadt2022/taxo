"""Read-only Git snapshots (TAXO-01C).

Only plumbing commands that never run repository-configured programs are used:
rev-parse, ls-tree, ls-files and cat-file. Working-tree bytes are read directly, so
clean/smudge filters, hooks and fsmonitor are never invoked. `.env` files are listed
but never read, not even to compute a digest.
"""
from dataclasses import dataclass, field
from functools import partial
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

COMMIT, WORKING_TREE = 'COMMIT', 'WORKING_TREE'
GIT_TIMEOUT = 120
_GIT = ['git', '-c', 'safe.directory=*', '-c', 'core.fsmonitor=false']
_ENV = {'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
_CHUNK = 1 << 16


class SnapshotError(ValueError):
    """The repository cannot provide a versioned snapshot."""


@dataclass(frozen=True)
class Entry:
    path: str
    size: int
    read: Callable[[], bytes] = field(repr=False, compare=False)


@dataclass(frozen=True)
class Snapshot:
    repository: str
    commit: str
    mode: str
    dirty: bool
    content_fingerprint: str | None
    entries: tuple[Entry, ...] = field(repr=False)
    warnings: tuple[str, ...] = ()

    def reference(self):
        """Snapshot fields of the fact contract (ADR 0002)."""
        reference = {'repository': self.repository, 'commit': self.commit, 'mode': self.mode}
        if self.content_fingerprint:
            reference['content_fingerprint'] = self.content_fingerprint
        return reference


def _git(root, *args):
    try:
        result = subprocess.run([*_GIT, '-C', str(root), *args], capture_output=True,
                                timeout=GIT_TIMEOUT, env={**os.environ, **_ENV})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnapshotError("Git est indisponible ou trop lent pour créer l'instantané.") from exc
    if result.returncode:
        raise SnapshotError('Git a refusé de lire le dépôt.')
    return result.stdout


def _is_env(path):
    name = path.rsplit('/', 1)[-1]
    return name == '.env' or name.startswith('.env.')


def _decode(raw, warnings):
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        warnings.append('Chemin non UTF-8 ignoré.')
        return None


def _fingerprint(digests):
    """SHA-256 over (path, LF-normalized content digest) pairs sorted by UTF-8 path bytes."""
    digest = hashlib.sha256()
    for path in sorted(digests, key=lambda p: p.encode('utf-8')):
        digest.update(path.encode('utf-8') + b'\0' + digests[path].encode('ascii') + b'\n')
    return 'sha256:' + digest.hexdigest()


def _file_digest(file):
    digest = hashlib.sha256()
    with open(file, 'rb') as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk.replace(b'\r', b''))
    return digest.hexdigest()


def _blob_digests(root, oids):
    """Stream each committed blob once and keep only its LF-normalized digest."""
    digests = {}
    with tempfile.TemporaryFile() as batch:
        batch.write(b''.join(oid.encode('ascii') + b'\n' for oid in oids))
        batch.seek(0)
        try:
            process = subprocess.Popen([*_GIT, '-C', str(root), 'cat-file', '--batch'], stdin=batch,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={**os.environ, **_ENV})
        except OSError as exc:
            raise SnapshotError("Git est indisponible pour lire l'instantané.") from exc
        with process.stdout as out:
            for oid in oids:
                header = out.readline().split()
                if len(header) != 3:
                    process.kill()
                    raise SnapshotError('Objet Git illisible.')
                remaining, digest = int(header[2]), hashlib.sha256()
                while remaining:
                    chunk = out.read(min(remaining, _CHUNK))
                    if not chunk:
                        process.kill()
                        raise SnapshotError('Objet Git tronqué.')
                    digest.update(chunk.replace(b'\r', b''))
                    remaining -= len(chunk)
                out.read(1)
                digests[oid] = digest.hexdigest()
        if process.wait(timeout=GIT_TIMEOUT):
            raise SnapshotError('Git a refusé de lire les objets du commit.')
    return digests


def open_snapshot(root, mode=COMMIT):
    """Return a Snapshot of the repository at root, or None if root is not a Git top level."""
    if mode not in (COMMIT, WORKING_TREE):
        raise ValueError('Mode d\'instantané inconnu.')
    root = Path(root).resolve()
    if not (root / '.git').exists():
        return None
    if Path(_git(root, 'rev-parse', '--show-toplevel').decode('utf-8').strip()).resolve() != root:
        return None
    try:
        commit = _git(root, 'rev-parse', '--verify', '--quiet', 'HEAD^{commit}').decode('ascii').strip()
    except SnapshotError as exc:
        raise SnapshotError('Le dépôt ne contient encore aucun commit.') from exc
    warnings = []

    committed = {}
    for record in filter(None, _git(root, 'ls-tree', '-r', '-z', '-l', '--full-tree', commit).split(b'\0')):
        meta, raw_path = record.split(b'\t', 1)
        file_mode, kind, oid, size = meta.split()
        path = _decode(raw_path, warnings)
        # Symlinks (120000) and submodules (commit objects) are never followed.
        if path and kind == b'blob' and file_mode != b'120000':
            committed[path] = (oid.decode('ascii'), int(size))

    working = {}
    listed = _git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')
    for raw_path in dict.fromkeys(filter(None, listed)):
        path = _decode(raw_path, warnings)
        file = root / path if path else None
        try:
            if file and not file.is_symlink() and file.is_file() and file.resolve().is_relative_to(root):
                working[path] = file
        except OSError:
            warnings.append(f'Fichier illisible : {path}')

    readable = [p for p in committed if not _is_env(p)]
    oids = list(dict.fromkeys(committed[p][0] for p in readable))
    blob_digests = _blob_digests(root, oids) if oids else {}
    committed_digests = {p: blob_digests[committed[p][0]] for p in readable}
    working_digests = {}
    for path, file in working.items():
        if _is_env(path):
            continue
        try:
            working_digests[path] = _file_digest(file)
        except OSError:
            warnings.append(f'Fichier illisible : {path}')

    if mode == COMMIT:
        entries = tuple(Entry(p, size, partial(_git, root, 'cat-file', 'blob', oid))
                        for p, (oid, size) in sorted(committed.items()))
        fingerprint = None
    else:
        entries = tuple(Entry(p, f.stat().st_size, f.read_bytes) for p, f in sorted(working.items()))
        fingerprint = _fingerprint(working_digests)
    return Snapshot(root.name, commit, mode, committed_digests != working_digests, fingerprint,
                    entries, tuple(warnings))
