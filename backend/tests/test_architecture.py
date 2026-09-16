"""Executable dependency boundaries for ADR 0004."""
import ast
from importlib.util import resolve_name
from pathlib import Path
import subprocess
import sys

import pytest

from app.evaluators.inventory.evaluator import evaluate
from app.projects.domain.project import Project
from app.scans.application.run_scan import RunScan
from app.scans.domain.scan import ScanError
from app.snapshots.domain.errors import GIT_READ_ERROR, SnapshotError
from app.snapshots.domain.mode import COMMIT
from app.snapshots.domain.snapshot import Snapshot, SnapshotFile


APP = Path(__file__).parents[1] / 'app'


def imports(path):
    package = '.'.join(path.relative_to(APP.parent).parts[:-1])
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = '.' * node.level + (node.module or '')
            yield resolve_name(name, package) if node.level else name


def test_dependency_boundaries():
    violations = []
    for path in APP.rglob('*.py'):
        parts = path.relative_to(APP).parts
        for name in imports(path):
            external = name.split('.')[0]
            if 'domain' in parts:
                forbidden = external in {'fastapi', 'sqlalchemy', 'psycopg', 'subprocess', 'pathlib', 'os', 'jsonschema'}
                forbidden |= name.startswith('app.') and '.domain' not in name
            elif 'application' in parts:
                forbidden = external in {'fastapi', 'sqlalchemy', 'psycopg', 'subprocess', 'jsonschema'}
                forbidden |= any(segment in name.split('.') for segment in ('infrastructure', 'api', 'bootstrap', 'evaluators'))
            elif parts[0] == 'evaluators':
                forbidden = external in {'fastapi', 'sqlalchemy', 'psycopg', 'subprocess', 'os'}
                forbidden |= any(segment in name.split('.') for segment in ('infrastructure', 'api', 'bootstrap'))
            elif 'api' in parts:
                forbidden = external in {'sqlalchemy', 'psycopg', 'subprocess'} or '.infrastructure' in name
            else:
                forbidden = False
            if forbidden:
                violations.append(f'{path.relative_to(APP)} imports {name}')
    assert violations == []


def test_importing_domains_does_not_load_technical_adapters():
    code = '''
import sys
import app.facts.domain.fact
import app.snapshots.domain.snapshot
import app.projects.domain.project
import app.scans.domain.scan
for name in sys.modules:
    assert name.split('.')[0] not in {'fastapi', 'sqlalchemy', 'psycopg', 'subprocess', 'jsonschema'}
    assert not name.startswith('app.') or '.infrastructure' not in name
'''
    subprocess.run([sys.executable, '-c', code], cwd=APP.parent, check=True, capture_output=True)


class MemoryContent:
    def read_many(self, paths):
        contents = {'package.json': b'{"dependencies":{"react":"19"}}'}
        for path in paths:
            yield path, contents[path]


def test_inventory_only_needs_a_snapshot():
    snapshot = Snapshot('project-key', 'a' * 40, COMMIT,
                        (SnapshotFile('package.json', 31), SnapshotFile('App.tsx', 1)),
                        content=MemoryContent())
    result = evaluate(snapshot)
    assert result['snapshot'] == {'repository': 'project-key', 'commit': 'a' * 40, 'mode': COMMIT}
    assert {fact['technology'] for fact in result['facts']} == {'React', 'Node.js ecosystem', 'TypeScript'}


def test_failed_snapshot_never_reaches_inventory_or_persistence():
    class Projects:
        def get(self, project_id):
            return Project(project_id, 'demo', 'logical-location')

    class Paths:
        def resolve(self, value):
            return value

    class Reader:
        def open(self, *args):
            raise SnapshotError(GIT_READ_ERROR, 'unavailable')

    class Scans:
        def add(self, scan):
            pytest.fail('An unsuccessful scan must never be persisted')

    def inventory(snapshot):
        pytest.fail('Inventory must never run without a readable snapshot')

    run = RunScan(Projects(), Scans(), Paths(), Reader(), inventory)
    with pytest.raises(ScanError, match='GIT_READ_ERROR : unavailable'):
        run('project-key')
