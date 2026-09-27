"""Evaluateur de structure (TAXO-E1, ADR 0012) : modules, dependances entre modules, unites deployables.

Il lit les descripteurs de build (Gradle, Maven, npm, Python) et de deploiement (compose), sans rien
executer, et ne connait aucun framework. Il produit `repository CONTAINS module`, `module DEPENDS_ON module`
et `application BUILT_FROM module`, chaque fait avec la ligne qui le porte. Ce qu'il ne sait pas lire est
declare NOT_INTERPRETED sur son fichier : jamais un module ni une dependance devines.
"""
from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.progress import silent
from app.evaluations.domain.status import EvaluationStatus
from app.facts import content_hash, is_path
from app.snapshots.domain.errors import SnapshotError
from . import readers
from .catalog import CATALOG

IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '__pycache__', '.gradle', 'out',
           'coverage'}
MAX_BYTES = 1024 * 1024
DESCRIPTORS = {*readers.GRADLE_SETTINGS, *readers.GRADLE_BUILDS, 'pom.xml', 'package.json',
               *readers.PYTHON_DESCRIPTORS, *readers.COMPOSE_FILES}
METHODS = {'gradle': 'build.gradle.include', 'maven': 'build.maven.module', 'npm': 'build.npm.package',
           'python': 'build.python.descriptor'}


class StructureEvaluator:
    evaluator_id = 'taxo.structure'
    producer_version = '0.1.0'
    catalog = CATALOG

    def evaluate(self, snapshot, progress=silent):
        repository = f'repository:{snapshot.repository}'
        texts, read_errors, warnings = _read(snapshot)
        reading = _interpret(texts)
        progress('modules', 'Modules relevés', len({module.directory for module in reading.modules}))
        facts = _facts(snapshot, repository, texts, reading)
        coverage = [_coverage(repository, 'ANALYSED', repository)]
        coverage += [_coverage(f'file:{path}', 'NOT_INTERPRETED', f'file:{path}') for path in sorted(reading.gaps)]
        coverage += [_coverage(subject, 'READ_ERROR', subject) for subject in read_errors]
        warnings += [f'{path} : {" ; ".join(reasons)}' for path, reasons in sorted(reading.gaps.items())]
        status = EvaluationStatus.PARTIAL if reading.gaps or read_errors else EvaluationStatus.SUCCESS
        legacy = {'modules': len({module.directory for module in reading.modules}),
                  'dependencies': len(reading.dependencies), 'applications': len(reading.applications)}
        return EvaluationOutput(tuple(facts), tuple(coverage), status, tuple(warnings), legacy)


def _read(snapshot):
    wanted, read_errors, warnings = [], [], []
    for file in snapshot.iter_files():
        parts = file.path.split('/')
        if parts[-1] not in DESCRIPTORS or not is_path(file.path) or IGNORED.intersection(parts[:-1]):
            continue
        if file.size > MAX_BYTES:
            read_errors.append(f'file:{file.path}')
            warnings.append(f'Descripteur trop volumineux, non lu : {file.path}')
            continue
        wanted.append(file.path)
    texts = {}
    try:
        for path, data in snapshot.read_many(wanted):
            try:
                texts[path] = data.decode('utf-8')
            except UnicodeDecodeError:
                read_errors.append(f'file:{path}')
                warnings.append(f'Descripteur non UTF-8, non lu : {path}')
    except SnapshotError as exc:
        read_errors += [f'file:{path}' for path in wanted if path not in texts]
        warnings.append(f'Erreur de lecture des descripteurs : {exc}')
    return texts, read_errors, warnings


def _named(texts, names):
    return {path: text for path, text in texts.items() if path.rsplit('/', 1)[-1] in names}


def _interpret(texts):
    reading = readers.Reading()
    _gradle(_named(texts, readers.GRADLE_SETTINGS), _named(texts, readers.GRADLE_BUILDS), reading)
    _maven(_named(texts, ('pom.xml',)), reading)
    readers.npm_workspaces(readers.npm_packages(_named(texts, ('package.json',)), reading), reading)
    for path, text in sorted(_named(texts, readers.PYTHON_DESCRIPTORS).items()):
        readers.python_descriptor(path, text, reading)
    for path, text in sorted(_named(texts, readers.COMPOSE_FILES).items()):
        readers.compose_file(path, text, reading)
    known = {module.directory for module in reading.modules}
    for application in list(reading.applications):
        if application.module not in known:
            reading.applications.remove(application)
            reading.gap(application.path, f'contexte de build sans module reconnu : {application.key}')
    return reading


def _gradle(settings, builds, reading):
    """Un build Gradle par `settings.gradle(.kts)` ; un `build.gradle` hors de tout build est un projet seul."""
    roots = {}
    for path, text in sorted(settings.items()):
        root = readers.directory_of(path)
        before = len(reading.modules)
        readers.gradle_settings(path, text, reading)
        included = [module.directory for module in reading.modules[before:]]
        projects = {readers.gradle_path(directory, root): directory for directory in included}
        projects[':'] = root
        roots[root] = projects
    for path, text in sorted(builds.items()):
        directory = readers.directory_of(path)
        root = next((candidate for candidate in sorted(roots, key=len, reverse=True)
                     if candidate == '.' or directory == candidate or directory.startswith(candidate + '/')), None)
        if root is None:
            reading.modules.append(readers.Module(directory, 'gradle', path, 1))
            projects = {':': directory}
        else:
            projects = roots[root]
            if directory not in projects.values():
                # Un build.gradle qu'aucun settings n'inclut n'est pas un projet du build : non lu.
                reading.gap(path, 'build.gradle hors des projets inclus')
                continue
        readers.gradle_dependencies(path, text, reading, projects)


def _maven(poms, reading):
    parsed = {}
    for path, text in sorted(poms.items()):
        readers.maven_pom(path, text, reading, parsed)
    listed = {module.directory for module in reading.modules if module.system == 'maven'}
    for path in sorted(poms):
        directory = readers.directory_of(path)
        aggregator = '<modules>' in poms[path]
        if directory in parsed and directory not in listed and not aggregator:
            reading.modules.append(readers.Module(directory, 'maven', path, 1))
    readers.maven_dependencies(reading, parsed, poms)


def _facts(snapshot, repository, texts, reading):
    facts = {}
    by_directory = {}
    for module in reading.modules:
        by_directory.setdefault(module.directory, []).append(module)
    for directory, modules in sorted(by_directory.items()):
        systems = sorted({module.system for module in modules})
        evidence = [_evidence(snapshot, texts, module.path, module.line, module.line, METHODS[module.system])
                    for module in {(module.path, module.line): module for module in modules}.values()]
        fact = _assertion(repository, 'CONTAINS', f'module:{directory}', {'build_systems': systems}, evidence)
        facts[(repository, 'CONTAINS', directory)] = fact
    for dependency in reading.dependencies:
        if dependency.source not in by_directory or dependency.target not in by_directory:
            reading.gap(dependency.path, f'dépendance vers un dossier qui n’est pas un module : {dependency.target}')
            continue
        qualifiers = {'build_system': dependency.system, 'configuration': dependency.configuration}
        evidence = [_evidence(snapshot, texts, dependency.path, dependency.line, dependency.line,
                              f'build.{dependency.system}.dependency')]
        key = (dependency.source, dependency.target, dependency.system, dependency.configuration)
        facts.setdefault(key, _assertion(f'module:{dependency.source}', 'DEPENDS_ON', f'module:{dependency.target}',
                                         qualifiers, evidence))
    for application in reading.applications:
        evidence = [_evidence(snapshot, texts, application.path, application.line_start, application.line_end,
                              'deploy.compose.build')]
        facts[(application.key,)] = _assertion(f'application:{application.key}', 'BUILT_FROM',
                                               f'module:{application.module}', {}, evidence)
    return list(facts.values())


def _evidence(snapshot, texts, path, line_start, line_end, method):
    return {'repository': snapshot.repository, 'commit': snapshot.commit, 'path': path,
            'line_start': line_start, 'line_end': line_end, 'method': method,
            'content_hash': content_hash(texts[path].encode('utf-8'), line_start, line_end)}


def _assertion(subject, relation, target, qualifiers, evidence):
    return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'relation': relation, 'object': target, 'qualifiers': qualifiers,
            'evidence': evidence}


def _coverage(subject, coverage_type, scope):
    return {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'coverage_type': coverage_type, 'scope': {'include': [scope]}}

