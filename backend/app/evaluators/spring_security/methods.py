"""La securite de methode et la protection CSRF de Spring Security, lues dans les sources Java (TAXO-MINIA-SEC-01, E2).

Ce module lit ce qui est ecrit, sans rien deduire :

- l'activation de la securite de methode : `@EnableMethodSecurity`, ou `@EnableGlobalMethodSecurity` avec
  `prePostEnabled = true` ; un attribut `prePostEnabled` qui n'est pas un litteral laisse l'activation inconnue ;
- l'expression `@PreAuthorize` qui garde une methode : celle de la methode, sinon celle de son type ;
- la desactivation de CSRF sur une chaine `HttpSecurity` : `csrf().disable()`, `csrf(c -> c.disable())` ou
  `csrf(AbstractHttpConfigurer::disable)`. Toute autre configuration CSRF est vue, pas lue.

Une annotation compte si son nom se resout vers Spring par le code ecrit (nom qualifie ou import) : un homonyme
d'un autre paquetage ou un nom non resolu n'est jamais pris pour celle de Spring.
"""
from dataclasses import dataclass

from . import rules

PRE_AUTHORIZE = 'org.springframework.security.access.prepost.PreAuthorize'
_METHOD_CONFIGURATION = 'org.springframework.security.config.annotation.method.configuration'
ENABLE_METHOD_SECURITY = f'{_METHOD_CONFIGURATION}.EnableMethodSecurity'
ENABLE_GLOBAL_METHOD_SECURITY = f'{_METHOD_CONFIGURATION}.EnableGlobalMethodSecurity'
PRE_POST = 'prePostEnabled'
MODE, PROXY = 'mode', 'PROXY'
CSRF = 'csrf'
DISABLE = 'disable'
CSRF_DISABLED = 'csrf.disable()'
CONFIGURER = 'org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer'
# Annotations de securite de methode, par nom simple : une meta-annotation ou un supertype qui en porte une garde
# peut-etre la methode, sans que ce module le lise.
SECURITY_ANNOTATIONS = {'PreAuthorize', 'PostAuthorize', 'PreFilter', 'PostFilter', 'Secured', 'RolesAllowed',
                        'DenyAll', 'PermitAll'}
ENABLED, DISABLED, UNKNOWN = 'enabled', 'disabled', 'unknown'


@dataclass(frozen=True)
class Enabling:
    """Un type qui porte une annotation d'activation : son etat, et l'attribut `prePostEnabled` s'il est ecrit."""
    path: str
    owner: str
    annotation: object
    qualified: str
    state: str
    written: str | None = None
    # L'attribut qui laisse l'activation non etablie, tel qu'ecrit (`prePostEnabled = Flags.ON`, `mode = ASPECTJ`).
    unread: str | None = None

    @property
    def symbol(self):
        return f'symbol:java:{self.owner}'

    @property
    def reference(self):
        return f'annotation:{self.qualified}'


@dataclass(frozen=True)
class Guard:
    """L'expression `@PreAuthorize` qui garde une methode, et le symbole qui la porte (la methode ou son type)."""
    symbol: str
    annotation: object
    expression: str | None

    @property
    def restrictive(self):
        """Vrai si l'expression ne peut que restreindre : une lecture sure la conclut sans l'evaluer."""
        return self.expression is not None and rules.restrictive(self.expression)


@dataclass(frozen=True)
class Csrf:
    """Un appel `csrf` d'une chaine HttpSecurity : desactive, ou configure autrement (non lu)."""
    path: str
    symbol: str
    line_start: int
    line_end: int
    disabled: bool


def resolves(annotation, java_file, qualified, types=()):
    """Vrai si l'annotation designe `qualified` par le code ecrit : nom qualifie, import explicite ou import du paquetage.
    `types` : les noms qualifies des types des sources, pour qu'un type du meme paquetage l'emporte sur un import."""
    return _names(java_file, annotation.name, qualified, types)


def enablings(java_file, types=()):
    """Les types du fichier qui portent une annotation d'activation de la securite de methode."""
    found = []
    for java_type in java_file.types:
        for annotation in java_type.annotations:
            for qualified in (ENABLE_METHOD_SECURITY, ENABLE_GLOBAL_METHOD_SECURITY):
                if resolves(annotation, java_file, qualified, types):
                    state, written, unread = _state(annotation, qualified)
                    found.append(Enabling(java_file.path, java_type.qualified_name, annotation, qualified, state,
                                          written, unread))
    return found


def _state(annotation, qualified):
    """(etat, `prePostEnabled` ecrit, attribut non lu). `@EnableMethodSecurity` active `@PreAuthorize` par defaut ;
    `@EnableGlobalMethodSecurity` seulement avec `prePostEnabled = true`. Un attribut qui n'est pas un litteral
    booleen laisse l'etat inconnu, comme un `mode` autre que le proxy par defaut : le tissage AspectJ qu'il exige
    n'est pas lu."""
    values = annotation.arguments.get(PRE_POST)
    written = values[0].written.strip() if values and len(values) == 1 else None
    if values and written not in ('true', 'false'):
        return UNKNOWN, written, f'{PRE_POST} = {written}'
    modes = annotation.arguments.get(MODE)
    mode = modes[0].written.strip() if modes and len(modes) == 1 else None
    if modes and (mode is None or mode.rsplit('.', 1)[-1] != PROXY):
        return UNKNOWN, written, f'{MODE} = {mode}'
    if written is None:
        return (ENABLED if qualified == ENABLE_METHOD_SECURITY else DISABLED), None, None
    return (ENABLED if written == 'true' else DISABLED), written, None


def guard(java_file, java_type, method, handler, types=()):
    """L'expression `@PreAuthorize` de la methode, sinon celle du type ; None si aucune ne la garde."""
    for annotations, symbol in ((method.annotations, handler), (java_type.annotations,
                                                                f'symbol:java:{java_type.qualified_name}')):
        found = [item for item in annotations if resolves(item, java_file, PRE_AUTHORIZE, types)]
        if found:
            values = found[0].arguments.get('value') or []
            expression = values[0].text if len(values) == 1 and values[0].resolved else None
            return Guard(symbol, found[0], expression)
    return None


def csrf(java_file, types=()):
    """Les appels `csrf` des chaines HttpSecurity du fichier, desactivations reconnues ou configurations non lues."""
    found = []
    chains = java_file.chains({CSRF})
    inner = rules.lambda_chains(chains)
    for chain in chains:
        if chain in inner or rules.receiver(chain, java_file) != rules.HTTP:
            continue
        symbol = f'symbol:java:{chain.owner}#{chain.method}' if chain.method else f'symbol:java:{chain.owner}'
        for index, call in enumerate(chain.calls):
            if call.name != CSRF:
                continue
            following = chain.calls[index + 1] if index + 1 < len(chain.calls) else None
            disabled = _disables(java_file, call, following, types)
            end = following.line_end if disabled and not call.arguments else call.line_end
            found.append(Csrf(java_file.path, symbol, call.line_start, end, disabled))
    return found


def _disables(java_file, call, following, types=()):
    """Vrai pour `csrf().disable()`, `csrf(c -> c.disable())` et `csrf(AbstractHttpConfigurer::disable)`, ce dernier
    seulement si `AbstractHttpConfigurer` est celui de Spring : une methode `disable` d'un autre type peut ne rien
    desactiver."""
    if not call.arguments:
        return following is not None and following.name == DISABLE and not following.arguments
    if len(call.arguments) != 1:
        return False
    argument = call.arguments[0]
    function = argument.function
    if function is None:
        owner, _, name = argument.value.written.replace(' ', '').partition('::')
        return name == DISABLE and _names(java_file, owner, CONFIGURER, types)
    return (function.complete and len(function.parameters) == 1 and len(function.chains) == 1
            and function.chains[0].receiver == function.parameters[0] and function.chains[0].names == (DISABLE,))


def _names(java_file, written, qualified, types=()):
    """Vrai si le nom de type ecrit designe `qualified` par le code ecrit : nom qualifie ou import. Comme en Java
    (JLS 6.4.1), un import explicite l'emporte sur un type du meme paquetage, qui l'emporte sur un import `*`."""
    if '.' in written:
        return written == qualified
    simple = qualified.rsplit('.', 1)[-1]
    if written != simple or any(item.name == simple for item in java_file.types):
        return False
    imports = [name for name, static in java_file.imports if not static]
    explicit = [name for name in imports if name.rsplit('.', 1)[-1] == simple]
    if explicit:
        return explicit == [qualified]
    sibling = f'{java_file.package}.{simple}' if java_file.package else simple
    return sibling not in types and f'{qualified.rpartition(".")[0]}.*' in imports


def hidden(java_file, java_type, method, types):
    """Ce qui peut garder la methode sans etre lu ici : une meta-annotation de securite declaree dans les sources,
    une annotation de securite d'un supertype lu (sur le type ou la meme signature). Chaque raison est dite."""
    reasons = []
    for annotation in (*method.annotations, *java_type.annotations):
        declared = types.get(_qualified(java_file, annotation.name))
        if declared and any(item.simple_name in SECURITY_ANNOTATIONS for item in declared[1].annotations):
            reasons.append(f'méta-annotation @{annotation.simple_name}')
    seen, pending = set(), [qualified for _, qualified in java_type.supertypes if qualified]
    while pending:
        qualified = pending.pop()
        if qualified in seen or qualified not in types:
            continue
        seen.add(qualified)
        supertype = types[qualified][1]
        inherited = [*supertype.annotations, *(item for candidate in supertype.methods
                                               if candidate.signature == method.signature
                                               for item in candidate.annotations)]
        if any(item.simple_name in SECURITY_ANNOTATIONS for item in inherited):
            reasons.append(f'héritée de {supertype.name}')
        pending += [item for _, item in supertype.supertypes if item]
    return reasons


def _qualified(java_file, name):
    """Le nom qualifie qu'un nom de type ecrit designe dans le fichier : qualifie, importe, ou du meme paquetage."""
    if '.' in name:
        return name
    explicit = [item for item, static in java_file.imports if not static and item.rsplit('.', 1)[-1] == name]
    if explicit:
        return explicit[0]
    return f'{java_file.package}.{name}' if java_file.package else name
