"""Historique Git en lecture seule (TAXO-HIST-01).

Memes garanties que la lecture des instantanes : seules des commandes de lecture sont lancees, sans
hook, filtre ni fsmonitor. Aucun contenu de fichier n'est lu ici : seulement les commits, leurs parents
et la liste des fichiers touches.
"""
import os
import re
import subprocess
from pathlib import Path

from app.history.domain.commit import ChangedFile, Commit, is_confidential
from app.history.domain.errors import (GIT_READ_ERROR, NOT_A_GIT_REPOSITORY, UNKNOWN_COMMIT,
                                       HistoryError)

GIT_TIMEOUT = 60
MAX_COMMITS = 100
_COMMIT_ID = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')
_GIT = ['git', '-c', 'safe.directory=*', '-c', 'core.fsmonitor=false', '-c', 'core.quotepath=false']
_ENV = {'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
_FORMAT = '%H%x00%P%x00%an%x00%aI%x00%s%x1e'
_STATUS = {'A': 'ADDED', 'M': 'MODIFIED', 'D': 'DELETED', 'R': 'RENAMED', 'C': 'COPIED', 'T': 'TYPE_CHANGED'}


def _run(root, *args):
    try:
        return subprocess.run([*_GIT, '-C', str(root), *args], capture_output=True, timeout=GIT_TIMEOUT,
                              env={**os.environ, **_ENV})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HistoryError(GIT_READ_ERROR, 'Git est indisponible ou trop lent.') from exc


def _output(root, *args):
    result = _run(root, *args)
    if result.returncode:
        raise HistoryError(GIT_READ_ERROR, 'Git a refusé de lire l\'historique.')
    return result.stdout


def _text(raw):
    return raw.decode('utf-8', errors='replace')


def _repository(root):
    root = Path(root).resolve()
    top = _run(root, 'rev-parse', '--show-toplevel')
    if not (root / '.git').exists() or top.returncode or Path(_text(top.stdout).strip()).resolve() != root:
        raise HistoryError(NOT_A_GIT_REPOSITORY, "Le dossier n'est pas la racine d'un dépôt Git.")
    return root


def _commits(raw):
    commits = []
    for record in filter(None, (part.strip(b'\n') for part in raw.split(b'\x1e'))):
        sha, parents, author, authored_at, subject = (_text(field) for field in record.split(b'\x00'))
        commits.append(Commit(sha, tuple(parents.split()), author, authored_at, subject))
    return commits


class GitHistoryReader:
    def commits(self, root, limit=10):
        """Les `limit` derniers commits de HEAD, du plus recent au plus ancien ; vide sans commit."""
        root = _repository(root)
        if not 1 <= limit <= MAX_COMMITS:
            raise ValueError(f'Nombre de commits attendu entre 1 et {MAX_COMMITS}.')
        if _run(root, 'rev-parse', '--verify', '--quiet', 'HEAD^{commit}').returncode:
            return []
        return _commits(_output(root, 'log', f'--max-count={limit}', f'--format={_FORMAT}', 'HEAD'))

    def commit(self, root, sha):
        root = _repository(root)
        if not (isinstance(sha, str) and _COMMIT_ID.fullmatch(sha)):
            raise HistoryError(UNKNOWN_COMMIT, 'Commit attendu : 40 ou 64 caractères hexadécimaux minuscules.')
        if _run(root, 'cat-file', '-e', f'{sha}^{{commit}}').returncode:
            raise HistoryError(UNKNOWN_COMMIT, 'Commit introuvable dans le dépôt.')
        return _commits(_output(root, 'show', '--no-patch', f'--format={_FORMAT}', sha))[0]

    def files(self, root, sha, parent):
        """Fichiers touches entre `parent` et `sha` ; `parent` absent pour un commit racine."""
        root = _repository(root)
        span = [parent, sha] if parent else ['--root', sha]
        statuses = _output(root, 'diff-tree', '-r', '-z', '-M', '--no-commit-id', '--name-status', *span)
        counts = _output(root, 'diff-tree', '-r', '-z', '-M', '--no-commit-id', '--numstat', *span)
        return _merge(_name_status(statuses), _numstat(counts))


def _name_status(raw):
    fields = [_text(field) for field in raw.split(b'\x00')]
    entries, index = [], 0
    while index < len(fields) and fields[index]:
        code = fields[index]
        if code[0] in 'RC':
            entries.append((_STATUS[code[0]], fields[index + 2], fields[index + 1]))
            index += 3
        else:
            entries.append((_STATUS.get(code[0], code), fields[index + 1], None))
            index += 2
    return entries


def _numstat(raw):
    fields = [_text(field) for field in raw.split(b'\x00')]
    counts, index = {}, 0
    while index < len(fields) and fields[index]:
        added, deleted, path = fields[index].split('\t', 2)
        if not path:
            path, index = fields[index + 2], index + 3
        else:
            index += 1
        counts[path] = (None if added == '-' else int(added), None if deleted == '-' else int(deleted))
    return counts


def _merge(entries, counts):
    return [ChangedFile(path, status, old_path, *counts.get(path, (None, None)), is_confidential(path))
            for status, path, old_path in entries]
