"""Existing inventory behavior; structured Facts/Coverage arrive in TAXO-01D."""
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from app.snapshots.domain.mode import COMMIT, WORKING_TREE
from .detectors.manifests import MANIFEST_READERS
from .detectors.filenames import _technologies_by_name

IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '__pycache__', '.python-packages'}
MANIFESTS = {'package.json', 'pom.xml', 'requirements.txt'}
MAX_FILES = 50000
MAX_MANIFEST_BYTES = 1024 * 1024

def _read_manifests(snapshot, manifests, facts, warnings):
    # Read errors propagate: a partial snapshot is never presented as complete.
    for path, data in snapshot.read_many(manifests):
        def add(name, path=path):
            facts.add((name, path))
        try:
            MANIFEST_READERS[PurePosixPath(path).name](data.decode('utf-8-sig'), add)
        except (ValueError, TypeError, AttributeError, ET.ParseError):
            warnings.append(f'Manifeste illisible ou invalide : {path}')


def evaluate(snapshot) -> dict:
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
