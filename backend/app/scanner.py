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


def _read_manifest(filename, relative, content, add):
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


def inspect_repository(root, repository, mode=COMMIT, commit=None) -> dict:
    snapshot = open_snapshot(root, repository, mode, commit)
    files = [f for f in snapshot.iter_files() if not IGNORED.intersection(f.path.split('/')[:-1])]
    if len(files) > MAX_FILES:
        raise ValueError('Projet trop volumineux : limite de 50 000 fichiers.')
    facts, warnings, manifests = set(), [], []
    def add(name, path):
        facts.add((name, path))
    for file in files:
        filename = file.path.rsplit('/', 1)[-1]
        suffix = PurePosixPath(filename).suffix
        if suffix in EXTENSIONS:
            add(EXTENSIONS[suffix], file.path)
        if filename == 'Dockerfile' or filename.startswith('Dockerfile.'):
            add('Docker', file.path)
        if file.path.startswith('.github/workflows/') and suffix in {'.yml', '.yaml'}:
            add('GitHub Actions', file.path)
        if filename in MANIFESTS:
            if file.size > MAX_MANIFEST_BYTES:
                warnings.append(f'Manifeste trop volumineux : {file.path}')
            else:
                manifests.append(file.path)
    # Read errors propagate: a partial snapshot is never presented as complete.
    for path, data in snapshot.read_many(manifests):
        try:
            _read_manifest(path.rsplit('/', 1)[-1], path, data.decode('utf-8-sig'), add)
        except (ValueError, TypeError, AttributeError, ET.ParseError):
            warnings.append(f'Manifeste illisible ou invalide : {path}')
    reference = snapshot.reference()
    if snapshot.mode == WORKING_TREE:
        reference['dirty'] = snapshot.dirty
    return {'files_count': len(files), 'commit': snapshot.commit,
            'source': 'commit' if snapshot.mode == COMMIT else 'working-tree', 'snapshot': reference,
            'facts': [{'technology': name, 'file': path, 'status': 'OBSERVED', 'method': 'manifest' if PurePosixPath(path).name in MANIFESTS else 'filename'} for name, path in sorted(facts)],
            'warnings': warnings}
