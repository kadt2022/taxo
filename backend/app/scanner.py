"""Bounded, read-only inventory. No repository code, build script or Git filter is executed."""
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .snapshots import COMMIT, Entry, open_snapshot

IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '__pycache__', '.python-packages'}
EXTENSIONS = {'.java': 'Java', '.py': 'Python', '.ts': 'TypeScript', '.tsx': 'TypeScript', '.js': 'JavaScript', '.jsx': 'JavaScript', '.sql': 'SQL'}
MANIFESTS = {'package.json', 'pom.xml', 'requirements.txt'}
MAX_FILES = 50000


def _file_size(file):
    try:
        return file.stat().st_size
    except OSError:
        return 0


def _unversioned_entries(root):
    """Working-tree walk for folders that are not the top level of a Git repository."""
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED and not (Path(directory) / d).is_symlink() and not (Path(directory) / d).is_junction())
        for filename in sorted(files):
            file = Path(directory) / filename
            if file.is_symlink() or not file.resolve().is_relative_to(root):
                continue
            yield Entry(file.relative_to(root).as_posix(), _file_size(file), file.read_bytes)


def inspect_repository(root: Path, mode: str = COMMIT) -> dict:
    root = Path(root).resolve()
    snapshot = open_snapshot(root, mode)
    facts, warnings = set(), []
    if snapshot is None:
        entries = _unversioned_entries(root)
        warnings.append('Dossier non versionné par Git : analyse du dossier de travail, sans instantané.')
    else:
        entries = (e for e in snapshot.entries if not IGNORED.intersection(e.path.split('/')[:-1]))
        warnings.extend(snapshot.warnings)
    count = 0
    def add(name, path):
        facts.add((name, path))
    for entry in entries:
        count += 1
        if count > MAX_FILES:
            raise ValueError('Projet trop volumineux : limite de 50 000 fichiers.')
        relative = entry.path
        filename = relative.rsplit('/', 1)[-1]
        suffix = Path(filename).suffix
        if suffix in EXTENSIONS:
            add(EXTENSIONS[suffix], relative)
        if filename == 'Dockerfile' or filename.startswith('Dockerfile.'):
            add('Docker', relative)
        if relative.startswith('.github/workflows/') and suffix in {'.yml', '.yaml'}:
            add('GitHub Actions', relative)
        if filename not in MANIFESTS:
            continue
        try:
            if entry.size > 1024 * 1024:
                warnings.append(f'Manifeste trop volumineux : {relative}')
                continue
            content = entry.read().decode('utf-8-sig')
            if filename == 'requirements.txt':
                for line in content.splitlines():
                    match = re.match(r'^\s*([A-Za-z0-9_-]+)(?:\[|[<>=!~;\s]|$)', line)
                    if match:
                        dependency = match.group(1).lower().replace('_', '-')
                        name = {'fastapi': 'FastAPI', 'django': 'Django', 'flask': 'Flask', 'sqlalchemy': 'SQLAlchemy', 'psycopg': 'PostgreSQL client', 'alembic': 'Alembic'}.get(dependency)
                        if name:
                            add(name, relative)
            elif filename == 'package.json':
                package = json.loads(content)
                deps = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
                for key, name in {'react': 'React', 'typescript': 'TypeScript', 'vite': 'Vite', 'next': 'Next.js', 'express': 'Express', '@nestjs/core': 'NestJS'}.items():
                    if key in deps:
                        add(name, relative)
                add('Node.js ecosystem', relative)
            else:
                tree = ET.fromstring(content)
                add('Maven', relative)
                for element in tree.iter():
                    if element.tag.split('}')[-1] == 'groupId' and element.text == 'org.springframework.boot':
                        add('Spring Boot', relative)
        except (OSError, ValueError, TypeError, AttributeError, ET.ParseError):
            warnings.append(f'Manifeste illisible ou invalide : {relative}')
    if snapshot is None:
        source, reference = 'unversioned', None
    else:
        source = 'commit' if snapshot.mode == COMMIT else 'working-tree'
        reference = {**snapshot.reference(), 'dirty': snapshot.dirty}
    return {'files_count': count, 'commit': snapshot.commit if snapshot else None, 'source': source,
            'snapshot': reference,
            'facts': [{'technology': name, 'file': path, 'status': 'OBSERVED', 'method': 'manifest' if Path(path).name in MANIFESTS else 'filename'} for name, path in sorted(facts)],
            'warnings': warnings}
