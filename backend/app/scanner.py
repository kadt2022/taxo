"""Bounded, read-only inventory of a Git snapshot. No repository code, build script or Git filter is executed."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

from .snapshots import COMMIT, WORKING_TREE, open_snapshot

IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '__pycache__', '.python-packages'}
EXTENSIONS = {'.java': 'Java', '.py': 'Python', '.ts': 'TypeScript', '.tsx': 'TypeScript', '.js': 'JavaScript', '.jsx': 'JavaScript', '.sql': 'SQL'}
MANIFESTS = {'package.json', 'pom.xml', 'requirements.txt'}
MAX_FILES = 50000
MAX_MANIFEST_BYTES = 1024 * 1024
PYTHON_PACKAGES = {'fastapi': 'FastAPI', 'django': 'Django', 'flask': 'Flask', 'sqlalchemy': 'SQLAlchemy', 'psycopg': 'PostgreSQL client', 'alembic': 'Alembic'}
NODE_PACKAGES = {'react': 'React', 'typescript': 'TypeScript', 'vite': 'Vite', 'next': 'Next.js', 'express': 'Express', '@nestjs/core': 'NestJS'}
REQUIREMENT = re.compile(r'^\s*([A-Za-z0-9_-]+)(?:\[|[<>=!~;\s]|$)')


def _requirements(content, add):
    for line in content.splitlines():
        match = REQUIREMENT.match(line)
        name = match and PYTHON_PACKAGES.get(match.group(1).lower().replace('_', '-'))
        if name:
            add(name)


def _package_json(content, add):
    package = json.loads(content)
    deps = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
    for key, name in NODE_PACKAGES.items():
        if key in deps:
            add(name)
    add('Node.js ecosystem')


def _pom(content, add):
    tree = ET.fromstring(content)
    add('Maven')
    if any(e.tag.split('}')[-1] == 'groupId' and e.text == 'org.springframework.boot' for e in tree.iter()):
        add('Spring Boot')


MANIFEST_READERS = {'requirements.txt': _requirements, 'package.json': _package_json, 'pom.xml': _pom}


def _technologies_by_name(path):
    filename = path.rsplit('/', 1)[-1]
    suffix = PurePosixPath(filename).suffix
    if suffix in EXTENSIONS:
        yield EXTENSIONS[suffix]
    if filename == 'Dockerfile' or filename.startswith('Dockerfile.'):
        yield 'Docker'
    if path.startswith('.github/workflows/') and suffix in {'.yml', '.yaml'}:
        yield 'GitHub Actions'


def _read_manifests(snapshot, manifests, facts, warnings):
    # Read errors propagate: a partial snapshot is never presented as complete.
    for path, data in snapshot.read_many(manifests):
        def add(name, path=path):
            facts.add((name, path))
        try:
            MANIFEST_READERS[PurePosixPath(path).name](data.decode('utf-8-sig'), add)
        except (ValueError, TypeError, AttributeError, ET.ParseError):
            warnings.append(f'Manifeste illisible ou invalide : {path}')


def inspect_repository(root, repository, mode=COMMIT, commit=None) -> dict:
    snapshot = open_snapshot(root, repository, mode, commit)
    files = [f for f in snapshot.iter_files() if not IGNORED.intersection(f.path.split('/')[:-1])]
    if len(files) > MAX_FILES:
        raise ValueError('Projet trop volumineux : limite de 50 000 fichiers.')
    facts = {(name, f.path) for f in files for name in _technologies_by_name(f.path)}
    manifests = [f for f in files if PurePosixPath(f.path).name in MANIFESTS]
    warnings = [f'Manifeste trop volumineux : {f.path}' for f in manifests if f.size > MAX_MANIFEST_BYTES]
    _read_manifests(snapshot, [f.path for f in manifests if f.size <= MAX_MANIFEST_BYTES], facts, warnings)
    reference = snapshot.reference()
    if snapshot.mode == WORKING_TREE:
        reference['dirty'] = snapshot.dirty
    return {'files_count': len(files), 'commit': snapshot.commit,
            'source': 'commit' if snapshot.mode == COMMIT else 'working-tree', 'snapshot': reference,
            'facts': [{'technology': name, 'file': path, 'status': 'OBSERVED', 'method': 'manifest' if PurePosixPath(path).name in MANIFESTS else 'filename'} for name, path in sorted(facts)],
            'warnings': warnings}
