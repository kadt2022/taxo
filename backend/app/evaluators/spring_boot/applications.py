"""Applications Spring Boot et ce qu'elles chargent (TAXO-E1, tranche 2 ; ADR 0012).

Une application est un type annote `@SpringBootApplication` dans les sources principales d'un module. Elle
charge une classe du depot si, et seulement si, les trois prémisses suivantes sont etablies statiquement :

1. le module de la classe est sur son classpath d'execution : son propre module, puis les dependances
   `module DEPENDS_ON module` d'execution (`implementation`, `api`, `runtimeOnly` ; `compile`, `runtime`),
   de proche en proche, telles que l'evaluateur de structure les lit ;
2. la classe est dans un paquetage balaye (`scanBasePackages`, `scanBasePackageClasses` litteraux, sinon le
   paquetage de l'application), ou importee par un `@Import` litteral d'une classe chargee ;
3. elle porte un stereotype Spring (`@Configuration`, `@RestController`...) et aucune condition
   (`@Profile`, `@Conditional...`).

Ce qui ne s'etablit pas ainsi est inconnu, jamais tranche par paquetage, proximite ou nom : configuration
de dependance inconnue, descripteur non lu, dependances communes (`subprojects`, `apply from`, `buildSrc`,
`<dependencies>` d'un pom parent), balayage supplementaire (`@ComponentScan`), import non litteral ou
selectif, auto-configuration declaree (ses conditions ne sont pas evaluees), annotation non resolue.
Une classe hors du classpath n'est jamais chargee : c'est la seule absence que l'application prouve sans
reserve. Une classe du classpath, hors du balayage et non importee, n'est pas chargee par les voies lues ;
les autres voies (XML, initialiseurs, `spring.main.sources`) sont une lacune connue, dite a chaque usage.
"""
import re
from dataclasses import dataclass, field

from app.evaluators.structure import evaluator as structure
from app.evaluators.structure import readers
from app.snapshots.domain.errors import SnapshotError

YES, NO, UNKNOWN = 'YES', 'NO', 'UNKNOWN'
BOOT = 'org.springframework.boot.autoconfigure'
CONTEXT = 'org.springframework.context.annotation'
STEREOTYPE = 'org.springframework.stereotype'
WEB = 'org.springframework.web.bind.annotation'
CONDITION = 'org.springframework.boot.autoconfigure.condition'
# Noms simples connus, par paquetage : un import `paquetage.*` les resout sans ambiguite.
KNOWN = {
    STEREOTYPE: {'Component', 'Service', 'Repository', 'Controller', 'Indexed'},
    CONTEXT: {'Configuration', 'Import', 'ComponentScan', 'ComponentScans', 'Profile', 'Conditional', 'Bean',
              'Primary', 'Lazy', 'DependsOn', 'Scope', 'PropertySource', 'ImportResource', 'Role', 'Description',
              'EnableAspectJAutoProxy'},
    WEB: {'RestController', 'RequestMapping', 'GetMapping', 'PostMapping', 'PutMapping', 'DeleteMapping',
          'PatchMapping', 'ControllerAdvice', 'RestControllerAdvice', 'CrossOrigin', 'ResponseStatus',
          'ExceptionHandler', 'ResponseBody'},
    BOOT: {'SpringBootApplication', 'EnableAutoConfiguration', 'AutoConfiguration', 'AutoConfigureAfter',
           'AutoConfigureBefore', 'AutoConfigureOrder'},
    'org.springframework.boot': {'SpringBootConfiguration'},
    'org.springframework.core.annotation': {'Order'},
    'org.springframework.validation.annotation': {'Validated'},
    'org.springframework.transaction.annotation': {'Transactional', 'EnableTransactionManagement'},
    'org.springframework.security.config.annotation.web.configuration': {'EnableWebSecurity'},
    'org.springframework.security.config.annotation.method.configuration': {'EnableMethodSecurity'},
    'lombok': {'Getter', 'Setter', 'Data', 'Builder', 'Value', 'ToString', 'EqualsAndHashCode',
               'RequiredArgsConstructor', 'AllArgsConstructor', 'NoArgsConstructor'},
    'lombok.extern.slf4j': {'Slf4j'},
}
JAVA_LANG = {'Deprecated', 'Override', 'SuppressWarnings', 'SafeVarargs', 'FunctionalInterface'}
STEREOTYPES = {f'{STEREOTYPE}.{name}' for name in ('Component', 'Service', 'Repository', 'Controller')} | {
    f'{CONTEXT}.Configuration', f'{WEB}.RestController', f'{WEB}.ControllerAdvice', f'{WEB}.RestControllerAdvice',
    f'{BOOT}.AutoConfiguration'}
ENTRY = f'{BOOT}.SpringBootApplication'
PARTIAL_ENTRIES = {'org.springframework.boot.SpringBootConfiguration', f'{BOOT}.EnableAutoConfiguration'}
ENTRY_NAMES = {name.rsplit('.', 1)[-1] for name in (ENTRY, *PARTIAL_ENTRIES)}
IMPORT = f'{CONTEXT}.Import'
SCANS = {f'{CONTEXT}.ComponentScan', f'{CONTEXT}.ComponentScans'}
# Annotations qui n'enregistrent ni ne conditionnent rien : Java, persistance, documentation, generation de code.
# Toute autre annotation hors de Spring et du depot peut porter un stereotype ou une condition en meta-annotation.
INERT = ('java.', 'javax.', 'jakarta.', 'lombok.', 'io.swagger.', 'org.springdoc.', 'com.fasterxml.jackson.',
         'io.micrometer.', 'org.slf4j.')
SPRING = 'org.springframework.'
# Supertypes d'un import selectif : les classes enregistrees se decident a l'execution.
SELECTORS = {'ImportSelector', 'DeferredImportSelector', 'ImportBeanDefinitionRegistrar'}
RUNTIME = {'gradle': {'implementation', 'api', 'runtimeOnly', 'compile', 'runtime'}, 'maven': {'compile', 'runtime'}}
NOT_RUNTIME = {'gradle': {'compileOnly', 'compileOnlyApi', 'annotationProcessor', 'developmentOnly'},
               'maven': {'test'}}
AUTO_CONFIGURATION_FILES = ('META-INF/spring.factories',
                            'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports')
MAX_BYTES = 1024 * 1024
MAX_META = 4
UNRESOLVED = 'annotation non résolue'
OTHER_ROUTES = 'les enregistrements par XML, initialiseurs ou propriétés (spring.main.sources) ne sont pas lus'
_SHARED = re.compile(r'\b(?:subprojects|allprojects|configure)\b[^{]*\{')
_DEPENDENCIES = re.compile(r'\bdependencies\s*\{')
_APPLY_FROM = re.compile(r'\bapply[\s(]*from\b')
_GROUP = re.compile(r'''\bgroup\s*=\s*['"]([^'"\s]+)['"]''')
_CLASS_NAME = re.compile(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*')


@dataclass(frozen=True)
class Loading:
    """Ce qu'une application fait d'une classe : YES (premisses), NO ou UNKNOWN (raison)."""
    outcome: str
    premises: tuple = ()
    reason: str = ''


@dataclass
class Application:
    reference: str
    qualified: str
    path: str
    annotation: object
    module: str | None = None
    packages: tuple = ()
    # Modules du classpath, chacun avec le chemin de dependances qui l'y met (vide pour le module propre).
    classpath: dict = field(default_factory=dict)
    reason: str = ''
    loaded: dict = field(default_factory=dict)
    maybe: dict = field(default_factory=dict)
    open: list = field(default_factory=list)


class Deployment:
    """Les applications Spring Boot d'un depot, et ce que chacune charge. `analysis` est celle de l'evaluateur
    Spring API : les sources principales, deja lues."""

    def __init__(self, snapshot, analysis):
        self.analysis = analysis
        self.types = {}
        for java_file in analysis.parsed:
            for java_type in java_file.types:
                self.types[java_type.qualified_name] = (java_file, java_type)
        texts, self.reading, self.read_errors = structure.read(snapshot)
        self.texts = texts
        self.modules = sorted({module.directory for module in self.reading.modules}, key=len, reverse=True)
        self.edges = {}
        for dependency in self.reading.dependencies:
            self.edges.setdefault(dependency.source, []).append(dependency)
        self.shared = self._shared(snapshot)
        self.auto = _auto_configurations(snapshot, self)
        self.applications = [self._application(java_file, java_type, annotation)
                             for java_file in analysis.parsed for java_type in java_file.types
                             for annotation in java_type.annotations if annotation.simple_name in ENTRY_NAMES]
        # Une application n'est comptee qu'une fois, par son annotation d'entree la plus complete.
        unique = {}
        for application in self.applications:
            kept = unique.get(application.reference)
            if kept is None or (kept.reason and not application.reason):
                unique[application.reference] = application
        self.applications = sorted(unique.values(), key=lambda item: item.reference)
        for application in self.applications:
            if not application.reason:
                self._load(application)

    # --- Resolution des noms ------------------------------------------------------------------------

    def resolve(self, java_file, written):
        """Nom qualifie d'un type ou d'une annotation tel qu'ecrit dans `java_file`, ou None s'il n'est pas etabli."""
        written = written.removesuffix('.class').strip()
        if not _CLASS_NAME.fullmatch(written):
            return None
        head, _, rest = written.partition('.')
        if rest and head[:1].islower():
            return written
        plain = [name for name, static in java_file.imports if not static]
        explicit = [name for name in plain if name.rsplit('.', 1)[-1] == head]
        if explicit:
            return f'{explicit[0]}.{rest}' if rest else explicit[0]
        local = f'{java_file.package}.{head}' if java_file.package else head
        if local in self.types:
            return f'{local}.{rest}' if rest else local
        if not rest and head in JAVA_LANG:
            return f'java.lang.{head}'
        package = self._wildcard(plain, head)
        return f'{package}.{written}' if package else None

    def _wildcard(self, plain, head):
        """Le paquetage d'un import `paquetage.*` qui fournit `head`, s'il est seul a pouvoir le fournir."""
        wildcards = [name[:-2] for name in plain if name.endswith('.*')]
        found = [package for package in wildcards
                 if head in KNOWN.get(package, ()) or f'{package}.{head}' in self.types]
        if len(found) == 1:
            return found[0]
        return wildcards[0] if len(wildcards) == 1 and not found else None

    # --- Applications -------------------------------------------------------------------------------

    def _application(self, java_file, java_type, annotation):
        reference = f'application:{java_file.path}#{java_type.name}'
        application = Application(reference, java_type.qualified_name, java_file.path, annotation)
        resolved = self.resolve(java_file, annotation.name)
        if resolved in PARTIAL_ENTRIES:
            application.reason = f'point d’entrée @{annotation.simple_name} sans @SpringBootApplication : ' \
                                 'balayage non établi'
            return application
        if resolved != ENTRY:
            # Un nom d'entree qui ne se resout pas vers Spring Boot peut en etre un : l'application est vue, pas lue.
            application.reason = f'annotation @{annotation.simple_name} non résolue vers Spring Boot'
            return application
        application.module = self.module_of(java_file.path)
        if application.module is None:
            application.reason = 'application hors des sources principales (src/main) d’un module lu'
            return application
        condition, unsure = self._condition(java_file, java_type.annotations)
        if condition or unsure:
            what = f'condition @{condition}' if condition else UNRESOLVED
            application.reason = f'application elle-même conditionnelle ({what}) : chargement non établi'
            return application
        if any(self.resolve(java_file, item.name) in SCANS for item in java_type.annotations):
            application.reason = '@ComponentScan sur l’application : balayage non établi'
            return application
        packages, reason = self._packages(java_file, annotation)
        application.packages, application.reason = packages, reason
        if not reason:
            application.classpath, application.reason = self._classpath(application.module)
        return application

    def module_of(self, path):
        """Le module dont les sources principales portent `path`, ou None."""
        for module in self.modules:
            root = 'src/main/' if module == '.' else f'{module}/src/main/'
            if path.startswith(root):
                return module
        return None

    def _packages(self, java_file, annotation):
        packages = []
        for value in annotation.arguments.get('scanBasePackages', []):
            if not value.resolved or '${' in value.text:
                return (), f'paquetage balayé non littéral : {value.written}'
            packages.append(value.text)
        for value in annotation.arguments.get('scanBasePackageClasses', []):
            qualified = self.resolve(java_file, value.written)
            if qualified is None or qualified not in self.types:
                return (), f'classe de balayage non établie : {value.written}'
            packages.append(self.types[qualified][0].package)
        return tuple(sorted(set(packages or [java_file.package]))), ''

    def _classpath(self, module):
        """Modules du classpath d'execution, chacun avec son chemin ; ou la raison qui l'empeche d'etre etabli."""
        if self.shared:
            return {}, self.shared
        found, pending = {module: ()}, [module]
        while pending:
            source = pending.pop(0)
            unread = self._unread(source)
            if unread:
                return {}, f'descripteur non lu : {", ".join(unread)}'
            for dependency in self.edges.get(source, []):
                follow, reason = self._edge(dependency, found)
                if reason:
                    return {}, reason
                if follow:
                    found[dependency.target] = (*found[source], dependency)
                    pending.append(dependency.target)
        return found, ''

    def _edge(self, dependency, found):
        """(suivre la dependance, raison qui empeche d'etablir le classpath)."""
        kind = _kind(dependency)
        if kind == UNKNOWN:
            return False, (f'configuration « {dependency.configuration or "?"} » non interprétée '
                           f'({dependency.path} ligne {dependency.line})')
        if kind == NO or dependency.target in found:
            return False, ''
        if dependency.target not in self.modules:
            return False, f'dépendance vers un dossier qui n’est pas un module : {dependency.target}'
        return True, ''

    def _unread(self, module):
        """Descripteurs du module que la structure n'a pas lus entierement."""
        descriptors = [item.path for item in self.reading.modules if item.directory == module]
        descriptors += [path for path in self.texts if readers.directory_of(path) == module]
        errors = [path.removeprefix('file:') for path in self.read_errors]
        return sorted({path for path in descriptors if path in self.reading.gaps} |
                      {path for path in errors if readers.directory_of(path) == module})

    def _shared(self, snapshot):
        """Ce qui ajoute des dependances hors du descripteur de chaque module : le classpath n'est alors pas etabli."""
        if any(file.path.startswith('buildSrc/') for file in snapshot.iter_files()):
            return 'logique de build partagée (buildSrc) non lue'
        for path in sorted(self.reading.gaps):
            if path.rsplit('/', 1)[-1] in readers.GRADLE_SETTINGS:
                return f'modules non établis : {path}'
        groups = {match for text in self.texts.values() for match in _GROUP.findall(text)}
        for path, text in sorted(self.texts.items()):
            name = path.rsplit('/', 1)[-1]
            reason = ''
            if name in readers.GRADLE_BUILDS:
                reason = _gradle_shared(path, text, groups)
            elif name == 'pom.xml':
                reason = _maven_shared(path, text)
            if reason:
                return reason
        return ''

    # --- Chargement ---------------------------------------------------------------------------------

    def _load(self, application):
        """Point fixe : classes chargees (YES), peut-etre chargees (UNKNOWN), et ce qui ouvre le balayage."""
        java_file, java_type = self.types[application.qualified]
        # L'application est elle-meme une configuration : ses beans sont charges.
        application.loaded[application.qualified] = (f'@SpringBootApplication {application.qualified}',)
        self._imports(application, java_file, java_type, sure=True)
        changed = True
        while changed:
            before = (len(application.loaded), len(application.maybe), len(application.open))
            for qualified, (java_file, java_type) in self.types.items():
                if qualified == application.qualified or not self._on_classpath(application, java_file):
                    continue
                if qualified in self.auto:
                    application.maybe.setdefault(qualified, f'auto-configuration déclarée ({self.auto[qualified]}) : '
                                                            'conditions non évaluées')
                elif _scanned(application.packages, java_file.package):
                    self._component(application, qualified, java_file, java_type)
            for qualified in [*application.loaded, *application.maybe]:
                java_file, java_type = self.types[qualified]
                self._imports(application, java_file, java_type, sure=qualified in application.loaded)
                self._openers(application, qualified, java_file, java_type)
            changed = before != (len(application.loaded), len(application.maybe), len(application.open))

    def _on_classpath(self, application, java_file):
        return self.module_of(java_file.path) in application.classpath

    def _component(self, application, qualified, java_file, java_type):
        if qualified in application.loaded or qualified in application.maybe:
            return
        stereotype, unresolved = self._meta(java_file, java_type.annotations, STEREOTYPES)
        condition, unsure = self._condition(java_file, java_type.annotations)
        package = next(item for item in application.packages if _scanned((item,), java_file.package))
        if stereotype and not condition and not unsure:
            application.loaded[qualified] = (f'@{stereotype} {qualified} dans le paquetage balayé {package}',)
        elif stereotype or unresolved:
            reason = f'condition @{condition}' if condition else UNRESOLVED
            application.maybe[qualified] = f'{reason} : chargement non établi'

    def _imports(self, application, java_file, java_type, sure):
        for annotation in java_type.annotations:
            if self.resolve(java_file, annotation.name) == IMPORT:
                for value in annotation.arguments.get('value', []):
                    self._import(application, java_type, self.resolve(java_file, value.written), value.written, sure)

    def _import(self, application, java_type, target, written, sure):
        """Un `@Import(X.class)` porte par `java_type` : X est charge, peut-etre charge, ou ouvre le balayage."""
        if target is None:
            _open(application, f'@Import non résolu dans {java_type.qualified_name} : {written}')
            return
        if target not in self.types or target in application.loaded:
            return
        imported_file, imported = self.types[target]
        if {name.rsplit('.', 1)[-1] for name, _ in imported.supertypes} & SELECTORS:
            _open(application, f'import sélectif {target} : classes enregistrées à l’exécution')
            return
        condition, unsure = self._condition(imported_file, imported.annotations)
        if sure and not condition and not unsure:
            application.loaded[target] = (f'@Import({imported.name}.class) dans {java_type.qualified_name}',)
            application.maybe.pop(target, None)
        else:
            application.maybe.setdefault(target, f'importée par {java_type.qualified_name} sans chargement établi')

    def _openers(self, application, qualified, java_file, java_type):
        """Balayage supplementaire ou import par meta-annotation : l'absence hors balayage n'est plus etablie."""
        for annotation in java_type.annotations:
            name = self.resolve(java_file, annotation.name)
            if name in SCANS:
                _open(application, f'@ComponentScan dans {qualified}')
            elif name in self.types and name != qualified:
                meta_file, meta_type = self.types[name]
                meta, _ = self._meta(meta_file, meta_type.annotations, {IMPORT, *SCANS})
                if meta:
                    _open(application, f'@{annotation.simple_name} ({meta} en méta-annotation) dans {qualified}')

    def _unsure(self, name):
        """Vrai si l'annotation `name` peut porter, sans que Taxo le lise, un stereotype ou une condition."""
        return name is None or not (name.startswith((SPRING, *INERT)) or name in self.types)

    def _meta(self, java_file, annotations, wanted, depth=0):
        """Le nom de la premiere annotation de `wanted` portee, directement ou en meta-annotation par une
        annotation du depot ; et vrai si une annotation peut en porter une sans que Taxo le lise."""
        unresolved = False
        for annotation in annotations:
            name = self.resolve(java_file, annotation.name)
            if name in wanted:
                return annotation.simple_name, False
            if self._unsure(name) or (name in self.types and depth >= MAX_META):
                # Au-dela de la profondeur lue, une meta-annotation peut encore porter ce qu'on cherche.
                unresolved = True
            elif name in self.types:
                meta_file, meta_type = self.types[name]
                found, deeper = self._meta(meta_file, meta_type.annotations, wanted, depth + 1)
                if found:
                    return found, False
                unresolved = unresolved or deeper
        return None, unresolved

    def _condition(self, java_file, annotations, depth=0):
        """La condition portee (`Profile`, `Conditional...`), et vrai si une annotation n'est pas resolue."""
        unsure = False
        for annotation in annotations:
            name = self.resolve(java_file, annotation.name)
            if self._unsure(name) or (name in self.types and depth >= MAX_META):
                unsure = True
            elif name in (f'{CONTEXT}.Profile', f'{CONTEXT}.Conditional') or name.startswith(CONDITION + '.'):
                return annotation.simple_name, False
            elif name in self.types:
                meta_file, meta_type = self.types[name]
                found, deeper = self._condition(meta_file, meta_type.annotations, depth + 1)
                if found:
                    return found, False
                unsure = unsure or deeper
        return None, unsure

    def loads(self, application, qualified):
        """Ce que l'application fait de la classe `qualified` (des sources principales)."""
        if application.reason:
            return Loading(UNKNOWN, reason=application.reason)
        java_file, _ = self.types[qualified]
        module = self.module_of(java_file.path)
        if module is None:
            return Loading(UNKNOWN, reason=f'{qualified} hors des sources principales d’un module lu')
        if module not in application.classpath:
            return Loading(NO, reason=f'module:{module} hors du classpath de {application.reference}')
        if qualified in application.loaded:
            return Loading(YES, premises=(*self.path(application, module), *application.loaded[qualified]))
        if qualified in application.maybe:
            return Loading(UNKNOWN, reason=application.maybe[qualified])
        if application.open:
            return Loading(UNKNOWN, reason=' ; '.join(application.open))
        where = 'sans stéréotype Spring' if _scanned(application.packages, java_file.package) else \
            'hors des paquetages balayés'
        return Loading(NO, reason=f'{qualified} {where} et non importée ; {OTHER_ROUTES}')

    def loads_bean(self, application, qualified, signature):
        """Comme `loads`, pour le bean de methode `signature` du type : sa propre condition compte aussi."""
        if qualified not in self.types:
            return Loading(UNKNOWN, reason=f'{qualified} hors des sources principales lues')
        loading = self.loads(application, qualified)
        java_file, java_type = self.types[qualified]
        method = next((item for item in java_type.methods if item.signature == signature), None)
        if loading.outcome != YES or method is None:
            return loading
        condition, unsure = self._condition(java_file, method.annotations)
        if condition or unsure:
            what = f'condition @{condition}' if condition else UNRESOLVED
            return Loading(UNKNOWN, reason=f'bean {qualified}#{signature} : {what}')
        return loading

    def path(self, application, module):
        """Prémisses du classpath : le module de l'application, puis chaque dependance jusqu'a `module`."""
        premises = [f'BUILT_FROM : {application.reference} -> module:{application.module}']
        premises += [f'DEPENDS_ON : module:{item.source} -> module:{item.target} ({item.configuration})'
                     for item in application.classpath[module]]
        return premises


def _gradle_shared(path, text, groups):
    """Un build Gradle qui ajoute des dependances hors de son bloc propre, ou par coordonnees du depot."""
    local = next((group for group in sorted(groups) if f"'{group}:" in text or f'"{group}:' in text), None)
    if local:
        return f'dépendance par coordonnées vers le groupe du dépôt ({local}) : {path}'
    clean = readers.blank_comments(text)
    if _APPLY_FROM.search(clean):
        return f'script appliqué (apply from) non lu : {path}'
    if any(_DEPENDENCIES.search(_block(clean, match.end())) for match in _SHARED.finditer(clean)):
        return f'dépendances communes (subprojects, allprojects, configure) : {path}'
    return ''


def _maven_shared(path, text):
    """Un pom parent dont les `<dependencies>` sont heritees par ses modules."""
    if '<modules>' not in text:
        return ''
    body = re.sub(r'<dependencyManagement>.*?</dependencyManagement>', '', text, flags=re.S)
    return f'dépendances héritées d’un pom parent : {path}' if '<dependency>' in body else ''


def _kind(dependency):
    configuration, system = dependency.configuration, dependency.system
    if configuration in RUNTIME.get(system, ()):
        return YES
    if configuration in NOT_RUNTIME.get(system, ()) or (system == 'gradle' and configuration.startswith('test')):
        return NO
    return UNKNOWN


def _scanned(packages, package):
    return any(package == item or package.startswith(item + '.') for item in packages)


def _open(application, reason):
    if reason not in application.open:
        application.open.append(reason)


def _block(text, start):
    """Le corps d'un bloc `{...}` qui commence a `start` (apres l'accolade ouvrante)."""
    depth, index = 1, start
    while index < len(text) and depth:
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        index += 1
    return text[start:index]


def _auto_configurations(snapshot, deployment):
    """Classes declarees en auto-configuration dans les ressources d'un module : nom qualifie -> fichier."""
    wanted = [file.path for file in snapshot.iter_files()
              if file.size <= MAX_BYTES and any(file.path.endswith('src/main/resources/' + name)
                                                for name in AUTO_CONFIGURATION_FILES)]
    found = {}
    try:
        for path, data in snapshot.read_many(wanted):
            text = data.decode('utf-8', errors='replace').replace('\\\n', '')
            for name in re.findall(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+', text):
                if name in deployment.types:
                    found[name] = path
    except SnapshotError:
        # Un fichier d'auto-configuration illisible : toute classe du depot peut y figurer.
        for name in deployment.types:
            found.setdefault(name, 'fichier d’auto-configuration illisible')
    return found
