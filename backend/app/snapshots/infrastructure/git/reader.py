"""Read-only Git snapshots (TAXO-01C).

COMMIT reads Git objects only and never touches the working tree. WORKING_TREE reads the
files Git tracks or would track (not ignored) and is identified by a content fingerprint.
Only rev-parse, ls-tree, ls-files, cat-file and log are run, with core.fsmonitor disabled:
no hook, filter, fsmonitor, external diff or signature check configured by the repository is ever
executed. `.env` files
are neither exposed nor read.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unicodedata

from app.snapshots.domain.mode import COMMIT, WORKING_TREE
from app.snapshots.domain.errors import (SnapshotError, NOT_A_GIT_REPOSITORY, UNKNOWN_COMMIT,
    GIT_READ_ERROR, UNSUPPORTED_GIT_ENTRY, WORKING_TREE_READ_ERROR)
from app.snapshots.domain.history import HistoryChange, HistoryCommit
from app.snapshots.domain.snapshot import Snapshot, SnapshotFile

GIT_TIMEOUT = 120
# Same object id rule as the fact contract: 40 or 64 lowercase hexadecimal characters.
_COMMIT_ID = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')
_GIT = ['git', '-c', 'safe.directory=*', '-c', 'core.fsmonitor=false']
_ENV = {'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
_FILE_MODES = {b'100644', b'100755'}
_CHUNK = 1 << 16
# Historique (ADR 0007) : lecture seule, sans diff externe, textconv ni verification de signature.
_LOG = ['-c', 'log.showSignature=false', '-c', 'diff.external=', 'log', '-z', '--no-color', '--no-ext-diff',
        '--no-textconv', '--format=%x1e%H%x00%P%x00%an%x00%ae%x00%aI%x00%s', '--name-status', '-M',
        '--diff-merges=first-parent']
_CHANGES = {'A': 'ADDED', 'M': 'MODIFIED', 'D': 'DELETED', 'R': 'RENAMED', 'C': 'COPIED', 'T': 'TYPE_CHANGED'}


def _git(root, *args):
    try:
        return subprocess.run([*_GIT, '-C', str(root), *args], capture_output=True,
                              timeout=GIT_TIMEOUT, env={**os.environ, **_ENV})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnapshotError(GIT_READ_ERROR, 'Git est indisponible ou trop lent.') from exc


def _git_output(root, *args):
    result = _git(root, *args)
    if result.returncode:
        raise SnapshotError(GIT_READ_ERROR, 'Git a refusé de lire le dépôt.')
    return result.stdout


def _read_blobs(root, oids):
    """Stream blobs in order through a single `git cat-file --batch` process."""
    if not oids:
        return
    with tempfile.TemporaryFile() as batch:
        batch.write(b''.join(oid.encode('ascii') + b'\n' for oid in oids))
        batch.seek(0)
        try:
            process = subprocess.Popen([*_GIT, '-C', str(root), 'cat-file', '--batch'], stdin=batch,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={**os.environ, **_ENV})
        except OSError as exc:
            raise SnapshotError(GIT_READ_ERROR, 'Git est indisponible.') from exc
        try:
            for _ in oids:
                header = process.stdout.readline().split()
                if len(header) != 3 or header[1] != b'blob':
                    raise SnapshotError(GIT_READ_ERROR, 'Objet Git manquant ou illisible.')
                size = int(header[2])
                data = process.stdout.read(size)
                if len(data) != size or process.stdout.read(1) != b'\n':
                    raise SnapshotError(GIT_READ_ERROR, 'Objet Git tronqué.')
                yield data
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
            process.wait()


def _read_file(root, raw_path, path):
    file = root / raw_path
    try:
        if not stat.S_ISREG(file.lstat().st_mode) or not file.resolve().is_relative_to(root):
            raise OSError('Not a regular file inside the repository.')
        return file.read_bytes()
    except OSError as exc:
        raise SnapshotError(WORKING_TREE_READ_ERROR, f'Fichier du dossier de travail illisible : {path}') from exc


def _is_env(path):
    name = path.rsplit('/', 1)[-1]
    return name == '.env' or name.startswith('.env.')


def _digest(data):
    return hashlib.sha256(data.replace(b'\r', b'')).hexdigest()


def _file_digest(file):
    digest = hashlib.sha256()
    with open(file, 'rb') as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk.replace(b'\r', b''))
    return digest.hexdigest()


def _fingerprint(digests):
    """SHA-256 over (NFC path, LF-normalized content digest), sorted by UTF-8 path bytes."""
    digest = hashlib.sha256()
    for path in sorted(digests, key=lambda p: p.encode('utf-8')):
        digest.update(path.encode('utf-8') + b'\0' + digests[path].encode('ascii') + b'\n')
    return 'sha256:' + digest.hexdigest()


def _logical_paths(raw_paths):
    """Map NFC repository-relative paths to Git paths; refuse instead of choosing."""
    logical = {}
    for raw in raw_paths:
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise SnapshotError(UNSUPPORTED_GIT_ENTRY, 'Chemin Git non UTF-8.') from exc
        path = unicodedata.normalize('NFC', text)
        parts = path.split('/')
        if path.startswith('/') or '' in parts or '.' in parts or '..' in parts:
            raise SnapshotError(UNSUPPORTED_GIT_ENTRY, 'Chemin Git hors du dépôt logique.')
        if path in logical:
            raise SnapshotError(UNSUPPORTED_GIT_ENTRY, 'Deux chemins Git sont identiques après normalisation NFC.')
        logical[path] = text
    return logical


def _tree(root, commit):
    """Readable committed files {path: (oid, size)} and skipped special entries."""
    records = []
    for record in filter(None, _git_output(root, 'ls-tree', '-r', '-z', '-l', '--full-tree', commit).split(b'\0')):
        meta, raw_path = record.split(b'\t', 1)
        records.append((raw_path, meta.split()))
    files, skipped = {}, []
    for path, (_, (mode, kind, oid, size)) in zip(_logical_paths(raw for raw, _ in records), records):
        if kind == b'blob' and mode in _FILE_MODES:
            if _is_env(path):
                skipped.append((path, 'confidential'))
            else:
                files[path] = (oid.decode('ascii'), int(size))
        elif kind == b'blob' and mode == b'120000':
            skipped.append((path, 'symlink'))
        elif kind == b'commit':
            skipped.append((path, 'submodule'))
        else:
            raise SnapshotError(UNSUPPORTED_GIT_ENTRY, f'Entrée Git non supportée : {path}')
    return files, skipped


def _sorted_files(sizes):
    return tuple(SnapshotFile(p, sizes[p]) for p in sorted(sizes, key=lambda p: p.encode('utf-8')))


def _unreadable(path):
    return SnapshotError(WORKING_TREE_READ_ERROR, f'Fichier du dossier de travail illisible : {path}')


def _working_entry(root, path, text, skipped):
    """(digest, size) of an analysed working-tree file; None if absent or not analysed."""
    file = root / text
    try:
        info = file.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise _unreadable(path) from exc
    if stat.S_ISLNK(info.st_mode):
        skipped.append((path, 'symlink'))
        return None
    if stat.S_ISDIR(info.st_mode):
        skipped.append((path, 'submodule'))
        return None
    if not stat.S_ISREG(info.st_mode):
        raise SnapshotError(WORKING_TREE_READ_ERROR, f'Entrée du dossier de travail non supportée : {path}')
    if _is_env(path):
        skipped.append((path, 'confidential'))
        return None
    try:
        if not file.resolve().is_relative_to(root):
            skipped.append((path, 'symlink'))
            return None
        return _file_digest(file), info.st_size
    except OSError as exc:
        raise _unreadable(path) from exc


def _head_digests(root, head):
    files, _ = _tree(root, head)
    paths = list(files)
    return {p: _digest(data) for p, data in zip(paths, _read_blobs(root, [files[p][0] for p in paths]))}


def _working_tree(root, repository, head):
    listed = _git_output(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')
    sizes, sources, digests, skipped = {}, {}, {}, []
    for path, text in _logical_paths(dict.fromkeys(filter(None, listed))).items():
        entry = _working_entry(root, path, text, skipped)
        if entry:
            digests[path], sizes[path] = entry
            sources[path] = text
    return Snapshot(repository, head, WORKING_TREE, _sorted_files(sizes),
                    GitSnapshotContent(root, sources, WORKING_TREE), _fingerprint(digests),
                    _head_digests(root, head) != digests, tuple(skipped))


def open_snapshot(root, repository, mode=COMMIT, commit=None):
    """Snapshot of the Git repository whose top level is root, identified by the caller's key."""
    if mode not in (COMMIT, WORKING_TREE):
        raise ValueError("Mode d'instantané inconnu.")
    if not isinstance(repository, str) or not repository.strip():
        raise ValueError("La clé du dépôt doit être fournie par l'appelant.")
    if commit is not None and mode != COMMIT:
        raise ValueError('Un commit explicite ne peut être demandé qu\'en mode COMMIT.')
    if commit is not None and not (isinstance(commit, str) and _COMMIT_ID.fullmatch(commit)):
        raise SnapshotError(UNKNOWN_COMMIT, 'Commit attendu : 40 ou 64 caractères hexadécimaux minuscules.')
    root = Path(root).resolve()
    if not (root / '.git').exists():
        raise SnapshotError(NOT_A_GIT_REPOSITORY, "Le dossier n'est pas la racine d'un dépôt Git.")
    top = _git(root, 'rev-parse', '--show-toplevel')
    if top.returncode or Path(top.stdout.decode('utf-8', 'replace').strip()).resolve() != root:
        raise SnapshotError(NOT_A_GIT_REPOSITORY, "Le dossier n'est pas la racine d'un dépôt Git.")
    resolved = _git(root, 'rev-parse', '--verify', '--quiet', (commit or 'HEAD') + '^{commit}')
    if resolved.returncode:
        raise SnapshotError(UNKNOWN_COMMIT, 'Commit introuvable dans le dépôt.')
    sha = resolved.stdout.decode('ascii').strip()
    if mode == WORKING_TREE:
        return _working_tree(root, repository, sha)
    files, skipped = _tree(root, sha)
    return Snapshot(repository, sha, COMMIT, _sorted_files({p: size for p, (_, size) in files.items()}),
                    GitSnapshotContent(root, {p: oid for p, (oid, _) in files.items()}, COMMIT), skipped=tuple(skipped))

def _text(raw):
    return raw.decode('utf-8', 'surrogateescape')


def _changes(tokens):
    changes, index = [], 0
    while index < len(tokens):
        code = _text(tokens[index])
        if code[:1] in 'RC':
            changes.append(HistoryChange(_CHANGES[code[0]], _text(tokens[index + 2]), _text(tokens[index + 1])))
            index += 3
        else:
            changes.append(HistoryChange(_CHANGES.get(code[:1], 'UNKNOWN'), _text(tokens[index + 1])))
            index += 2
    return tuple(changes)


def _history(root, commit, limit):
    """Commits atteignables depuis `commit`, du plus recent au plus ancien, fichiers compares au premier parent."""
    if type(limit) is not int or limit < 1:
        raise ValueError("Le nombre de commits de l'historique doit etre un entier positif.")
    raw = _git_output(root, *_LOG, f'--max-count={limit}', commit, '--')
    for record in raw.split(b'\x1e')[1:]:
        fields = record.split(b'\x00')
        sha, parents, name, email, date, subject = (_text(field) for field in fields[:6])
        tokens = [token.lstrip(b'\n') for token in fields[6:]]
        yield HistoryCommit(sha, tuple(parents.split()), name, email, date, subject,
                            _changes([token for token in tokens if token]))


class GitSnapshotContent:
    def __init__(self, root, sources, mode):
        self.root, self.sources, self.mode = root, sources, mode

    def history(self, commit, limit):
        yield from _history(self.root, commit, limit)

    def read_many(self, paths):
        paths = list(paths)
        sources = [self.sources[path] for path in paths]
        if self.mode == COMMIT:
            yield from zip(paths, _read_blobs(self.root, sources))
        else:
            for path, raw_path in zip(paths, sources):
                yield path, _read_file(self.root, raw_path, path)

class GitSnapshotReader:
    def open(self, root, repository, mode=COMMIT, commit=None):
        return open_snapshot(root, repository, mode, commit)
