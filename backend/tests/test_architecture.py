"""Executable dependency boundaries for ADR 0004."""
import ast
from importlib.util import resolve_name
from pathlib import Path
import subprocess
import sys

import pytest

from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.projects.application.commands import add_project
from app.projects.domain.project import Project, ProjectError
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


def test_evaluation_engine_has_no_concrete_evaluator_dependency():
    for path in (APP / 'evaluations').rglob('*.py'):
        source = path.read_text(encoding='utf-8')
        assert 'app.evaluators' not in source


ANALYSED_PROJECT_NAMES = ('orgboundaryfilter', 'policybasedauthorizationmanager',
                          'portail-math', 'takibo', 'takibu')


def supplies_vector_values(relative):
    """Un vecteur de conformite porte des valeurs de test ; son manifeste est structurel."""
    return 'conformance' in relative.parts and relative.name != 'manifest.json'


def test_the_engine_never_names_an_analysed_project():
    """Un projet analyse fournit des donnees, jamais du vocabulaire au moteur.

    Un nom de projet ne peut apparaitre que dans les valeurs d'un vecteur de
    conformite. Tout le reste de `app/` est structurel — nom de fichier, code,
    documentation, schema du contrat et manifeste de la suite compris.
    """
    violations = []
    for path in APP.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        relative = path.relative_to(APP)
        location = str(relative).lower()
        violations += [f"{relative} est nomme d'apres {name}"
                       for name in ANALYSED_PROJECT_NAMES if name in location]
        if supplies_vector_values(relative):
            continue
        content = path.read_text(encoding='utf-8', errors='ignore').lower()
        violations += [f'{relative} nomme {name}'
                       for name in ANALYSED_PROJECT_NAMES if name in content]
    assert violations == []


def test_the_engine_never_imports_the_throwaway_poc():
    """Le POC a le droit d'importer le moteur ; le moteur ne doit pas le connaitre."""
    violations = [f'{path.relative_to(APP)} importe {name}'
                  for path in APP.rglob('*.py')
                  for name in imports(path) if name.split('.')[0] == 'poc']
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
        contents = {'package.json': b'{"dependencies":{"react":"19"}}',
                    'App.tsx': b'x'}
        for path in paths:
            yield path, contents[path]


class Projects:
    def get(self, project_id):
        return Project(project_id, 'demo', 'logical-location')


class Paths:
    def resolve(self, value):
        return value


class UnreadableReader:
    def open(self, *args):
        raise SnapshotError(GIT_READ_ERROR, 'unavailable')


class Scans:
    def add(self, scan):
        pytest.fail('An unsuccessful scan must never be persisted')


def forbidden_inventory(snapshot):
    pytest.fail('Inventory must never run when a scan cannot proceed')


def test_inventory_only_needs_a_snapshot():
    snapshot = Snapshot('project-key', 'a' * 40, COMMIT,
                        (SnapshotFile('package.json', 31), SnapshotFile('App.tsx', 1)),
                        content=MemoryContent())
    result = RunEvaluator()(InventoryEvaluator(), snapshot).legacy
    assert result['snapshot'] == {'repository': 'project-key', 'commit': 'a' * 40, 'mode': COMMIT}
    assert {fact['technology'] for fact in result['facts']} == {'React', 'Node.js ecosystem', 'TypeScript'}


def test_a_snapshot_is_never_built_without_its_content():
    """A snapshot that cannot be read is an invalid state, not a buildable one."""
    with pytest.raises(TypeError):
        Snapshot('project-key', 'a' * 40, COMMIT, (SnapshotFile('package.json', 31),))


def test_failed_snapshot_never_reaches_inventory_or_persistence():
    projects = Projects()
    scans = Scans()
    paths = Paths()
    reader = UnreadableReader()
    with pytest.raises(TypeError):
        RunScan(projects, scans, paths, reader, forbidden_inventory)
    run = RunScan(projects, scans, paths, reader, forbidden_inventory, RunEvaluator())
    with pytest.raises(ScanError, match='GIT_READ_ERROR : unavailable'):
        run('project-key')


def test_scan_mode_is_validated_by_the_use_case_not_by_its_adapter():
    class ForbiddenReader:
        def open(self, *args):
            pytest.fail('An unknown mode must be refused before a snapshot is opened')

    run = RunScan(Projects(), Scans(), Paths(), ForbiddenReader(), forbidden_inventory, RunEvaluator())
    with pytest.raises(ScanError, match='Mode de scan inconnu'):
        run('project-key', 'nimporte-quoi')


def test_scan_persists_only_legacy_and_bounded_execution_summary():
    legacy = {'files_count': 1, 'facts': [{'technology': 'Python'}]}
    summary = {'fact_count': 2000, 'coverage_count': 2}

    class Reader:
        def open(self, *args):
            return Snapshot('project-key', 'a' * 40, COMMIT, (), content=MemoryContent())

    class Runner:
        def __call__(self, evaluator, snapshot):
            class Execution:
                status = EvaluationStatus.SUCCESS
                evaluator_id, facts, coverage = 'fake', ({'kind': 'ASSERTION'},) * 2000, ()

                def result(self):
                    pytest.fail('The full execution must not be stored in scans.result')

                def summary(self):
                    return summary

            execution = Execution()
            execution.legacy = legacy
            return execution

    class SavedScans:
        def add(self, scan):
            self.scan = scan
            return scan

    scans = SavedScans()
    run = RunScan(Projects(), scans, Paths(), Reader(), object(), Runner())
    expected = {**legacy, 'evaluation_summary': summary, 'evaluations': [summary]}
    assert run('project-key').result == expected
    assert scans.scan.result == expected, 'les faits vont au magasin des faits, jamais dans scans.result'


def test_registering_a_project_takes_primitives_not_an_http_schema():
    class Repository:
        def __init__(self):
            self.projects = []

        def find_path(self, path):
            return next((project for project in self.projects if project.path == path), None)

        def add(self, project):
            self.projects.append(project)
            return project

    repository, paths = Repository(), Paths()
    project = add_project('  Demo  ', 'logical-location', repository, paths)
    assert (project.name, project.path) == ('Demo', 'logical-location')
    with pytest.raises(ProjectError, match='Le nom est obligatoire'):
        add_project('   ', 'other-location', repository, paths)
    with pytest.raises(ProjectError, match='déjà enregistré'):
        add_project('Demo again', 'logical-location', repository, paths)


def test_minia_explains_but_never_writes_facts_and_stays_apart_from_clochette():
    """Minia lit l'impact de Taxo ; elle ne connait ni le contrat du fait ni Clochette (ADR 0004, ADR 0006)."""
    violations = []
    for path in APP.rglob('*.py'):
        parts = path.relative_to(APP).parts
        for name in imports(path):
            if parts[0] == 'minia' and name.startswith(('app.facts', 'app.hypotheses', 'app.evaluations')):
                violations.append(f'{path.relative_to(APP)} importe {name}')
            if parts[0] not in {'minia', 'bootstrap', 'platform'} and name.startswith('app.minia'):
                violations.append(f'{path.relative_to(APP)} importe {name}')
    assert violations == []
