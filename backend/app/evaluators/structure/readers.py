"""Lecture des descripteurs de build et de deploiement, par leur forme ecrite (ARCHITECTURE § 7.5).

Chaque lecteur rend ce qu'il a lu (modules, dependances entre modules, applications), chaque element avec
sa ligne, et ce qu'il n'a pas su lire (`gaps` : chemin -> raison). Il ne devine jamais : une inclusion
calculee, un `project(...)` non litteral, un contexte de build absent sont declares, pas completes.
"""
import json
import posixpath
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fnmatch import fnmatch

import yaml


@dataclass(frozen=True)
class Module:
    directory: str
    system: str
    path: str
    # Ligne qui declare le module ; None quand c'est le descripteur entier (un fichier vide compris).
    line: int | None


@dataclass(frozen=True)
class Dependency:
    source: str
    target: str
    system: str
    configuration: str
    path: str
    line: int


@dataclass(frozen=True)
class Application:
    key: str
    module: str
    path: str
    line_start: int
    line_end: int


@dataclass
class Reading:
    modules: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    applications: list = field(default_factory=list)
    gaps: dict = field(default_factory=dict)

    def gap(self, path, reason):
        self.gaps.setdefault(path, []).append(reason)


def _line(text, index):
    return text.count('\n', 0, index) + 1


def directory_of(path):
    parent = posixpath.dirname(path)
    return parent or '.'


def _join(base, relative):
    """Dossier relatif au depot, ou None s'il sort du depot."""
    joined = posixpath.normpath(posixpath.join('' if base == '.' else base, relative))
    return None if joined.startswith(('..', '/')) else joined


# --- Gradle ---------------------------------------------------------------------------------------

_COMMENT = re.compile(r'//[^\n]*|/\*.*?\*/', re.S)
_INCLUDE = re.compile(r'\binclude\b')
_LITERAL = re.compile(r'''(['"])([^'"\n]*)\1''')
_PROJECT = re.compile(r'''\bproject\s*\(([^)]*)\)''')
# Enveloppes d'une dependance de projet : la configuration est l'identifiant qui les precede.
_WRAPPERS = {'platform', 'enforcedPlatform', 'testFixtures'}
GRADLE_SETTINGS = ('settings.gradle', 'settings.gradle.kts')
GRADLE_BUILDS = ('build.gradle', 'build.gradle.kts')


def blank_comments(text):
    """Commentaires remplaces par des blancs : positions et lignes inchangees."""
    return _COMMENT.sub(lambda match: re.sub(r'[^\n]', ' ', match.group(0)), text)


def _include_arguments(text, start):
    """Texte des arguments d'un `include` : entre parentheses, ou jusqu'a la fin de la ligne (et des
    lignes suivantes tant qu'une virgule termine la precedente)."""
    rest = text[start:]
    stripped = rest.lstrip()
    if stripped.startswith('('):
        opening = start + len(rest) - len(stripped)
        depth = 0
        for index in range(opening, len(text)):
            depth += {'(': 1, ')': -1}.get(text[index], 0)
            if depth == 0:
                return text[opening + 1:index], opening + 1
        return text[opening + 1:], opening + 1
    end = start
    while True:
        newline = text.find('\n', end)
        newline = len(text) if newline < 0 else newline
        if not text[end:newline].rstrip().endswith(',') or newline == len(text):
            return text[start:newline], start
        end = newline + 1


def gradle_settings(path, text, reading):
    """Modules inclus par un fichier `settings.gradle(.kts)`."""
    text = blank_comments(text)
    base = directory_of(path)
    if re.search(r'\bprojectDir\b', text):
        reading.gap(path, 'dossier de projet redéfini (projectDir)')
        return
    if re.search(r'\bincludeBuild\b', text):
        reading.gap(path, 'build composite (includeBuild) non lu')
    for match in _INCLUDE.finditer(text):
        arguments, offset = _include_arguments(text, match.end())
        remainder = _LITERAL.sub('', arguments)
        if re.search(r'[^\s,()]', remainder):
            reading.gap(path, f'inclusion calculée ligne {_line(text, match.start())}')
            continue
        for literal in _LITERAL.finditer(arguments):
            name = literal.group(2).strip(':').replace(':', '/')
            directory = _join(base, name)
            if not name or directory is None:
                reading.gap(path, f'inclusion non lue : {literal.group(2)}')
                continue
            reading.modules.append(Module(directory, 'gradle', path, _line(text, offset + literal.start())))


def gradle_dependencies(path, text, reading, projects):
    """Dependances `project(':x')` d'un `build.gradle(.kts)` ; `projects` : chemin Gradle -> dossier."""
    text = blank_comments(text)
    source = directory_of(path)
    for match in _PROJECT.finditer(text):
        line = _line(text, match.start())
        argument = match.group(1).strip()
        if argument.startswith('path'):
            argument = argument[len('path'):].lstrip().lstrip(':=').strip()
        literal = _LITERAL.fullmatch(argument)
        if literal is None:
            reading.gap(path, f'project(...) non littéral ligne {line}')
            continue
        target = projects.get(literal.group(2))
        if target is None:
            reading.gap(path, f'module inconnu {literal.group(2)} ligne {line}')
            continue
        prefix = text[text.rfind('\n', 0, match.start()) + 1:match.start()]
        reading.dependencies.append(Dependency(source, target, 'gradle', _configuration(prefix), path, line))


def _configuration(prefix):
    """Configuration d'une dependance : l'identifiant qui precede `project(` sur sa ligne, au-dela des
    enveloppes (`implementation(platform(project(...)))` donne `implementation`)."""
    words = re.findall(r'\w+', prefix.replace('(', ' '))
    while words and words[-1] in _WRAPPERS:
        words.pop()
    return words[-1] if words and words[-1] != 'dependencies' else ''


def gradle_path(directory, root):
    """Chemin Gradle (`:a:b`) d'un dossier de module, relativement a la racine du build."""
    relative = directory if root == '.' else posixpath.relpath(directory, root)
    return ':' + relative.replace('/', ':')


# --- Maven ----------------------------------------------------------------------------------------

def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _children(element, name):
    return [child for child in element if _local(child.tag) == name]


def _text_of(element, name):
    found = _children(element, name)
    return (found[0].text or '').strip() if found else ''


def _line_of(text, needle, start=0):
    index = text.find(needle, start)
    return _line(text, index) if index >= 0 else 1


def maven_pom(path, text, reading, poms):
    """Un `pom.xml` : ses modules (`<modules>`) et ses coordonnees ; `poms` recoit dossier -> (groupId,
    artifactId, dependances)."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        reading.gap(path, f'pom.xml illisible ({exc})')
        return
    directory = directory_of(path)
    parent = _children(root, 'parent')
    group = _text_of(root, 'groupId') or (_text_of(parent[0], 'groupId') if parent else '')
    dependencies = []
    for block in _children(root, 'dependencies'):
        for dependency in _children(block, 'dependency'):
            dependencies.append((_text_of(dependency, 'groupId'), _text_of(dependency, 'artifactId'),
                                 _text_of(dependency, 'scope') or 'compile'))
    poms[directory] = (group, _text_of(root, 'artifactId'), dependencies)
    for block in _children(root, 'modules'):
        for module in _children(block, 'module'):
            name = (module.text or '').strip()
            target = _join(directory, name)
            if '${' in name or target is None:
                reading.gap(path, f'module Maven non lu : {name}')
                continue
            reading.modules.append(Module(target, 'maven', path, _line_of(text, f'>{name}<')))


def maven_dependencies(reading, poms, texts):
    """Dependances entre modules Maven du depot, par coordonnees completes. Un `groupId` calcule
    (`${...}`) ne se resout pas : la dependance est declaree, jamais rattachee par son seul `artifactId`."""
    known = {(group, artifact): directory for directory, (group, artifact, _) in poms.items()}
    local = {artifact for (_, artifact, _) in poms.values()}
    for directory, (_, _, dependencies) in poms.items():
        path = 'pom.xml' if directory == '.' else f'{directory}/pom.xml'
        for group, artifact, scope in dependencies:
            target = known.get((group, artifact))
            if target is None and '${' in group and artifact in local:
                reading.gap(path, f'groupId calculé pour {artifact} : dépendance non rattachée')
            elif target is not None and target != directory:
                line = _line_of(texts[path], f'>{artifact}<', texts[path].find('<dependencies>'))
                reading.dependencies.append(Dependency(directory, target, 'maven', scope, path, line))


# --- npm ------------------------------------------------------------------------------------------

_SECTIONS = ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies')


def npm_packages(texts, reading):
    """Chaque `package.json` est un module ; les dependances entre paquets du depot sont relevees."""
    packages = {}
    for path, text in sorted(texts.items()):
        content = _package(path, text, reading)
        if content is None:
            continue
        directory = directory_of(path)
        packages[directory] = (path, text, content)
        reading.modules.append(Module(directory, 'npm', path, _line_of(text, '"name"') if 'name' in content else None))
    names = {content.get('name'): directory for directory, (_, _, content) in packages.items()
             if isinstance(content.get('name'), str)}
    for directory, (path, text, content) in packages.items():
        _npm_dependencies(directory, path, text, content, names, reading)
    return packages


def _package(path, text, reading):
    """Contenu d'un `package.json`, ou None (et la raison declaree) s'il n'est pas lisible."""
    try:
        content = json.loads(text)
    except ValueError as exc:
        reading.gap(path, f'package.json illisible ({exc})')
        return None
    if not isinstance(content, dict):
        reading.gap(path, 'package.json sans objet racine')
        return None
    return content


def _npm_dependencies(directory, path, text, content, names, reading):
    for section in _SECTIONS:
        declared = content.get(section)
        if not isinstance(declared, dict):
            continue
        for name, version in declared.items():
            target = _npm_target(directory, name, version, names)
            if target is not None and target != directory:
                line = _line_of(text, f'"{name}"', text.find(f'"{section}"'))
                reading.dependencies.append(Dependency(directory, target, 'npm', section, path, line))


def _npm_target(directory, name, version, names):
    if isinstance(version, str) and version.startswith(('file:', 'link:')):
        return _join(directory, version.split(':', 1)[1])
    return names.get(name)


def npm_workspaces(packages, reading):
    """Un `workspaces` qui designe des dossiers sans `package.json` lu est declare."""
    for directory, (path, _, content) in packages.items():
        workspaces = content.get('workspaces')
        if isinstance(workspaces, dict):
            workspaces = workspaces.get('packages')
        if workspaces is None:
            continue
        if not isinstance(workspaces, list) or not all(isinstance(item, str) for item in workspaces):
            reading.gap(path, 'workspaces non lus')
            continue
        for pattern in workspaces:
            full = _join(directory, pattern)
            if full is None or not any(fnmatch(other, full) for other in packages):
                reading.gap(path, f'workspace sans paquet lu : {pattern}')


# --- Python ---------------------------------------------------------------------------------------

PYTHON_DESCRIPTORS = ('pyproject.toml', 'setup.py', 'requirements.txt')
# Dependance par chemin : ligne editable (`-e ../lib`), ou reference `file:` / `path =`.
_EDITABLE = re.compile(r'^\s*-e\s', re.M)
_PATH_REFERENCE = re.compile(r'\bfile:|\bpath\s*=')


def python_descriptor(path, text, reading):
    reading.modules.append(Module(directory_of(path), 'python', path, None))
    found = [match.start() for match in (_EDITABLE.search(text), _PATH_REFERENCE.search(text)) if match]
    if found:
        reading.gap(path, f'dépendance Python par chemin non lue ligne {_line(text, min(found))}')


# --- compose --------------------------------------------------------------------------------------

COMPOSE_FILES = ('compose.yaml', 'compose.yml', 'docker-compose.yaml', 'docker-compose.yml')


def compose_file(path, text, reading):
    """Services compose construits depuis le depot : `application:<fichier>#<service>`."""
    try:
        document = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        reading.gap(path, f'compose illisible ({str(exc).splitlines()[0]})')
        return
    services = _mapping_value(document, 'services')
    if services is None:
        return
    if not isinstance(services, yaml.MappingNode):
        reading.gap(path, 'services non lus')
        return
    base = directory_of(path)
    for key, service in services.value:
        found = _build_context(_mapping_value(service, 'build'))
        if found is None:
            continue
        context_value, node = found
        module = None if context_value is None else _join(base, context_value)
        if context_value is None:
            reading.gap(path, f'contexte de build non lu : service {key.value}')
        elif module is None or '://' in context_value:
            reading.gap(path, f'contexte de build hors du dépôt : service {key.value}')
        else:
            reading.applications.append(Application(f'{path}#{key.value}', module, path,
                                                    key.start_mark.line + 1, node.end_mark.line + 1))


def _build_context(build):
    """(contexte ecrit, noeud) du `build` d'un service ; (None, noeud) s'il n'est pas litteral ; None sans build."""
    if build is None:
        return None
    if isinstance(build, yaml.ScalarNode):
        context = build
    elif isinstance(build, yaml.MappingNode):
        context = _mapping_value(build, 'context')
        if context is None:
            return '.', build
    else:
        return None, build
    if isinstance(context, yaml.ScalarNode) and '$' not in context.value:
        return context.value, context
    return None, build


def _mapping_value(node, name):
    if not isinstance(node, yaml.MappingNode):
        return None
    return next((value for key, value in node.value if isinstance(key, yaml.ScalarNode) and key.value == name), None)
