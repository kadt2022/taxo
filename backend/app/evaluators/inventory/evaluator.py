"""Inventory v0: deterministic observations over an already opened Snapshot."""
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.status import EvaluationStatus
from app.facts import content_hash
from app.snapshots.domain.mode import COMMIT, WORKING_TREE
from app.snapshots.domain.errors import SnapshotError
from .catalog import CATALOG
from .detectors.filenames import _technologies_by_name
from .detectors.manifests import MANIFEST_READERS

IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '__pycache__', '.python-packages'}
MANIFESTS = {'package.json', 'pom.xml', 'requirements.txt'}
MAX_FILES = 50000
MAX_MANIFEST_BYTES = 1024 * 1024


class InventoryEvaluator:
    evaluator_id = 'taxo.inventory'
    producer_version = '0.1.0'
    catalog = CATALOG

    def evaluate(self, snapshot):
        files = tuple(f for f in snapshot.iter_files()
                      if not IGNORED.intersection(f.path.split('/')[:-1]))
        if len(files) > MAX_FILES:
            raise ValueError('Projet trop volumineux : limite de 50 000 fichiers.')
        warnings = []
        observed = {(name, f.path, 'filename') for f in files
                    for name in _technologies_by_name(f.path)}
        for file in files:
            if file.size > MAX_MANIFEST_BYTES:
                kind = 'Manifeste' if PurePosixPath(file.path).name in MANIFESTS else 'Fichier'
                warnings.append(f'{kind} trop volumineux : {file.path}')
        readable = tuple(f for f in files if f.size <= MAX_MANIFEST_BYTES)
        by_path, read_error_subject = self._read_contents(snapshot, readable, observed, warnings)
        repository = f'repository:{snapshot.repository}'
        facts = self._facts(files, by_path, observed, repository)
        file_paths = {f.path for f in files}
        coverage = [self._coverage(repository, 'ANALYSED', repository)]
        for warning in warnings:
            path = warning.rsplit(': ', 1)[-1]
            if path in file_paths:
                coverage.append(self._coverage(f'file:{path}', 'NOT_INTERPRETED', f'file:{path}'))
        if read_error_subject:
            coverage.append(self._coverage(read_error_subject, 'READ_ERROR', read_error_subject))
        status = EvaluationStatus.PARTIAL if read_error_subject else EvaluationStatus.SUCCESS
        legacy = self._legacy(snapshot, files, observed, warnings)
        return EvaluationOutput(facts, tuple(coverage), status, tuple(warnings), legacy)

    def _read_contents(self, snapshot, readable, observed, warnings):
        by_path = {}
        read_error_subject = None
        next_file = 0
        try:
            for next_file, (path, data) in enumerate(snapshot.read_many(f.path for f in readable), 1):
                try:
                    by_path[path] = self._evidence(snapshot, path, data, 'inventory.file')
                except UnicodeDecodeError:
                    warnings.append(f'Fichier non UTF-8 non interprété : {path}')
                    continue
                filename = PurePosixPath(path).name
                if filename not in MANIFESTS:
                    continue
                try:
                    def add(name, path=path):
                        observed.add((name, path, 'manifest'))
                    MANIFEST_READERS[filename](data.decode('utf-8-sig'), add)
                except (ValueError, TypeError, AttributeError, ET.ParseError, UnicodeDecodeError):
                    warnings.append(f'Manifeste illisible ou invalide : {path}')
        except SnapshotError as exc:
            read_error_subject = (f'file:{readable[next_file].path}' if next_file < len(readable)
                                  else f'repository:{snapshot.repository}')
            warnings.append(f'Erreur de lecture : {read_error_subject} : {exc}')
        return by_path, read_error_subject

    def _facts(self, files, by_path, observed, repository):
        facts = []
        for file in files:
            if file.path not in by_path:
                continue
            evidence = by_path[file.path]
            facts.append(self._assertion(repository, 'CONTAINS', f'file:{file.path}', evidence))
            for language in self._languages(file.path):
                facts.append(self._assertion(f'file:{file.path}', 'WRITTEN_IN',
                                             f'language:{language}', evidence))
        for technology, path, method in sorted(observed):
            if path not in by_path:
                continue
            evidence = {**by_path[path], 'method': f'inventory.{method}'}
            key = self._technology_key(technology)
            facts.append(self._assertion(repository, 'USES_TECHNOLOGY', f'technology:{key}', evidence))
            facts.append(self._assertion(f'technology:{key}', 'DECLARED_BY', f'file:{path}', evidence))
        return tuple({fact['subject'] + '|' + fact['relation'] + '|' + fact.get('object', ''): fact
                      for fact in facts}.values())

    @staticmethod
    def _languages(path):
        suffix = PurePosixPath(path).suffix
        language = {'java': 'Java', 'py': 'Python', 'ts': 'TypeScript', 'tsx': 'TypeScript',
                    'js': 'JavaScript', 'jsx': 'JavaScript', 'sql': 'SQL'}.get(suffix.lstrip('.'))
        return (language,) if language else ()

    @staticmethod
    def _technology_key(name):
        return name.replace(' ', '-').replace('.', '').replace('/', '-')

    @staticmethod
    def _assertion(subject, relation, object_, evidence):
        return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
                'subject': subject, 'relation': relation, 'object': object_, 'qualifiers': {},
                'evidence': [evidence]}

    @staticmethod
    def _coverage(subject, coverage_type, scope):
        return {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                'subject': subject, 'coverage_type': coverage_type,
                'scope': {'include': [scope]}}

    @staticmethod
    def _evidence(snapshot, path, data, method):
        return {'repository': snapshot.repository, 'commit': snapshot.commit, 'path': path,
                'method': method, 'content_hash': content_hash(data)}

    @staticmethod
    def _legacy(snapshot, files, observed, warnings):
        reference = snapshot.reference()
        if snapshot.mode == WORKING_TREE:
            reference['dirty'] = snapshot.dirty
        return {'files_count': len(files), 'commit': snapshot.commit,
                'source': 'commit' if snapshot.mode == COMMIT else 'working-tree',
                'snapshot': reference,
                'facts': [{'technology': name, 'file': path, 'status': 'OBSERVED', 'method': method}
                          for name, path, method in sorted(observed)],
                'warnings': list(warnings)}
