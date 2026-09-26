"""Evaluateur Spring API (TAXO-04, ADR 0003) : les endpoints HTTP d'une application Spring MVC, en faits.

Il est proprietaire du concept d'endpoint ; il consomme les primitives de l'analyseur Java, qui n'en sait
rien. Pour chaque methode d'un controleur (`@RestController`, `@Controller`) portant une annotation de
mapping (`@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`,
`@RequestMapping`), il produit `endpoint:<VERBE> <chemin>` HANDLED_BY `symbol:java:<type>#<methode>`, avec
pour preuves le mapping du type et celui de la methode, a la ligne pres.

Il ne devine jamais. Un chemin ou un verbe qu'il ne sait pas resoudre (constante d'un type inconnu,
propriete `${...}`, expression), un mapping porte par une interface ou une classe qui n'est pas un
controleur, un controleur qui herite d'un type absent des sources (une interface generee au build depuis
une specification OpenAPI, par exemple) ou d'un type porteur de mappings, un fichier mal lu : autant de
couvertures NOT_INTERPRETED, jamais un endpoint invente ni une absence affirmee. Les sources de test (`src/test`) sont hors du perimetre, et le disent.
"""

from app.evaluations.domain.evaluator import EvaluationOutput
from app.evaluations.domain.progress import silent
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.java import syntax
from app.facts import content_hash, is_path
from app.snapshots.domain.errors import SnapshotError
from .catalog import CATALOG

METHOD = 'java.spring.request-mapping'
IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '__pycache__', '.gradle', 'out'}
TEST_SOURCES = ('src', 'test')
MAX_SOURCE_BYTES = 1024 * 1024
PROGRESS_EVERY = 250
CONTROLLERS = {'RestController', 'Controller'}
VERBS = {'GetMapping': 'GET', 'PostMapping': 'POST', 'PutMapping': 'PUT', 'DeleteMapping': 'DELETE',
         'PatchMapping': 'PATCH'}
REQUEST_MAPPING = 'RequestMapping'
MAPPINGS = {*VERBS, REQUEST_MAPPING}
HTTP_METHODS = {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE'}
# `@RequestMapping` sans `method` accepte tous les verbes : l'endpoint le dit, sans en choisir un.
ANY = 'ANY'


class _NotInterpreted(Exception):
    """Un mapping que l'evaluateur ne sait pas resoudre : il le declare au lieu de le deviner."""


class SpringApiEvaluator:
    evaluator_id = 'taxo.spring-api'
    producer_version = '0.1.0'
    catalog = CATALOG

    def evaluate(self, snapshot, progress=silent):
        repository = f'repository:{snapshot.repository}'
        sources, excluded = self._select(snapshot)
        warnings, gaps, read_errors = [], {}, []
        contents = self._read(snapshot, sources, warnings, read_errors, progress)
        # Premier passage : les constantes de chaque type, pour resoudre `Type.CONSTANTE` d'un fichier a l'autre.
        known = {}
        for path, data in contents.items():
            known.update(syntax.parse(path, data).constants())
        # Seuls les fichiers qui peuvent porter un controleur ou un mapping sont relus avec toutes les constantes.
        parsed = [syntax.parse(path, data, known) for path, data in contents.items()
                  if b'Mapping' in data or b'Controller' in data]
        # Types qui portent eux-memes des mappings : un controleur qui en herite recoit des routes non suivies.
        mapped = {item.qualified_name for java_file in parsed for item in java_file.types
                  if _mappings(item.annotations) or any(_mappings(method.annotations) for method in item.methods)}
        facts = {}
        for java_file in parsed:
            if java_file.has_errors:
                gaps[f'file:{java_file.path}'] = (java_file.path, f'Fichier Java lu en partie (erreur de syntaxe) : '
                                                                  f'{java_file.path}')
            for java_type in java_file.types:
                self._type_facts(snapshot, java_file.path, contents[java_file.path], java_type, mapped, facts, gaps)
        progress('endpoints', 'Endpoints relevés', len({fact['subject'] for fact in facts.values()}))
        # Une zone non interpretee a pour perimetre le fichier qui la porte.
        warnings += [message for _, message in gaps.values()]
        scope = {'include': [repository], 'exclude': sorted(excluded)}
        coverage = [{**_coverage(repository, 'ANALYSED', repository), 'scope': scope}]
        coverage += [_coverage(subject, 'NOT_INTERPRETED', f'file:{gaps[subject][0]}') for subject in sorted(gaps)]
        coverage += [_coverage(subject, 'READ_ERROR', subject) for subject in read_errors]
        status = EvaluationStatus.PARTIAL if gaps or read_errors else EvaluationStatus.SUCCESS
        legacy = {'java_files': len(contents), 'endpoints': len({fact['subject'] for fact in facts.values()})}
        return EvaluationOutput(tuple(facts.values()), tuple(coverage), status, tuple(warnings), legacy)

    @staticmethod
    def _select(snapshot):
        sources, excluded = [], set()
        for file in snapshot.iter_files():
            if not file.path.endswith('.java') or not is_path(file.path):
                continue
            parts = file.path.split('/')
            ignored_at = next((index for index, part in enumerate(parts[:-1]) if part in IGNORED), None)
            if ignored_at is not None:
                excluded.add(f"directory:{'/'.join(parts[:ignored_at + 1])}")
                continue
            tests_at = next((index for index in range(len(parts) - 2) if tuple(parts[index:index + 2]) == TEST_SOURCES), None)
            if tests_at is not None:
                excluded.add(f"directory:{'/'.join(parts[:tests_at + 2])}")
                continue
            sources.append(file)
        return sources, excluded

    @staticmethod
    def _read(snapshot, sources, warnings, read_errors, progress):
        readable = [file for file in sources if file.size <= MAX_SOURCE_BYTES]
        for file in sources:
            if file.size > MAX_SOURCE_BYTES:
                warnings.append(f'Fichier Java trop volumineux, non lu : {file.path}')
                read_errors.append(f'file:{file.path}')
        contents, count = {}, 0
        try:
            for count, (path, data) in enumerate(snapshot.read_many(file.path for file in readable), 1):
                if count % PROGRESS_EVERY == 0 or count == len(readable):
                    progress('reading', 'Fichiers Java lus', count, len(readable))
                try:
                    data.decode('utf-8')
                except UnicodeDecodeError:
                    warnings.append(f'Fichier Java non UTF-8, non lu : {path}')
                    read_errors.append(f'file:{path}')
                    continue
                contents[path] = data
        except SnapshotError as exc:
            remaining = [f'file:{file.path}' for file in readable[count:]]
            read_errors += remaining
            warnings.append(f'Erreur de lecture : {remaining[0] if remaining else "dépôt"} : {exc}')
        return contents

    def _type_facts(self, snapshot, path, data, java_type, mapped_types, facts, gaps):
        symbol = f'symbol:java:{java_type.qualified_name}'
        own = [method for method in java_type.methods if _mappings(method.annotations)]
        type_mapping = next(iter(_mappings(java_type.annotations)), None)
        controller = any(item.simple_name in CONTROLLERS for item in java_type.annotations)
        if not controller:
            if own or type_mapping is not None:
                # Interface, classe de base ou controleur declare autrement : ses routes existent peut-etre,
                # mais par un chemin (heritage, configuration) que cette version ne suit pas.
                gaps[symbol] = (path, f'Mappings hors d’un contrôleur non interprétés : {java_type.qualified_name}')
            return
        absent = [written for written, qualified in java_type.supertypes if qualified is None]
        carrying = [written for written, qualified in java_type.supertypes if qualified in mapped_types]
        if absent or carrying:
            # Ses propres mappings restent des faits ; ceux qu'il herite (d'une interface generee au build, absente
            # des sources, ou d'un type qui porte des mappings) ne sont pas suivis : ses routes sont incompletes.
            reasons = ([f'absent des sources : {", ".join(absent)}'] if absent else []) + (
                [f'porteur de mappings : {", ".join(carrying)}'] if carrying else [])
            gaps[symbol] = (path, f'Routes héritées non interprétées ({" ; ".join(reasons)}) : '
                                  f'{java_type.qualified_name}')
        try:
            base_paths = _paths(type_mapping) if type_mapping is not None else ['']
            base_verbs = _verbs(type_mapping) if type_mapping is not None else []
        except _NotInterpreted as exc:
            gaps[symbol] = (path, f'Mapping du contrôleur non résolu ({exc}) : {java_type.qualified_name}')
            return
        for method in own:
            handler = f'{symbol}#{method.name}'
            for annotation in _mappings(method.annotations):
                try:
                    verbs = ([VERBS[annotation.simple_name]] if annotation.simple_name in VERBS
                             else _verbs(annotation) or base_verbs or [ANY])
                    paths = _paths(annotation)
                except _NotInterpreted as exc:
                    gaps[handler] = (path, f'Mapping non résolu ({exc}) : {java_type.qualified_name}#{method.name}')
                    continue
                evidence = [_evidence(snapshot, path, data, item, handler)
                            for item in (type_mapping, annotation) if item is not None]
                for base in base_paths:
                    for own in paths:
                        for verb in verbs:
                            subject = f'endpoint:{verb} {_join(base, own)}'
                            facts.setdefault((subject, handler), _assertion(subject, handler, evidence))


def _mappings(annotations):
    return [item for item in annotations if item.simple_name in MAPPINGS]


def _paths(annotation):
    """Chemins d'un mapping (`value` ou `path`, alias l'un de l'autre) ; aucun chemin vaut le chemin vide."""
    values = annotation.arguments.get('path') or annotation.arguments.get('value') or []
    paths = []
    for value in values:
        if not value.resolved:
            raise _NotInterpreted(f'chemin {value.written}')
        if '${' in value.text:
            raise _NotInterpreted(f'propriété {value.text}')
        paths.append(value.text)
    return paths or ['']


def _verbs(annotation):
    """Verbes de `@RequestMapping(method = ...)` : `RequestMethod.GET` ou `GET` (import statique)."""
    verbs = []
    for value in annotation.arguments.get('method', []):
        verb = value.written.rsplit('.', 1)[-1]
        if verb not in HTTP_METHODS or value.written not in (verb, f'RequestMethod.{verb}',
                                                              f'org.springframework.web.bind.annotation.RequestMethod.{verb}'):
            raise _NotInterpreted(f'verbe {value.written}')
        verbs.append(verb)
    return verbs


def _join(base, own):
    """Chemin complet, comme Spring le combine : un seul `/` entre les parties, toujours un `/` en tete."""
    parts = [part.strip('/') for part in (base, own) if part.strip('/')]
    path = '/' + '/'.join(parts)
    last = own or base
    return path + '/' if last.endswith('/') and path != '/' else path


def _evidence(snapshot, path, data, annotation, handler):
    return {'repository': snapshot.repository, 'commit': snapshot.commit, 'path': path,
            'line_start': annotation.line_start, 'line_end': annotation.line_end, 'symbol': handler,
            'method': METHOD, 'content_hash': content_hash(data, annotation.line_start, annotation.line_end)}


def _assertion(subject, handler, evidence):
    return {'contract_version': 1, 'kind': 'ASSERTION', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'relation': 'HANDLED_BY', 'object': handler, 'qualifiers': {},
            'evidence': evidence}


def _coverage(subject, coverage_type, scope):
    return {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
            'subject': subject, 'coverage_type': coverage_type, 'scope': {'include': [scope]}}
