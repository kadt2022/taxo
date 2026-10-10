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
CSRF = 'csrf'
DISABLE = 'disable'
CSRF_DISABLED = 'csrf.disable()'
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


def resolves(annotation, java_file, qualified):
    """Vrai si l'annotation designe `qualified` par le code ecrit : nom qualifie, import explicite ou import du paquetage."""
    if '.' in annotation.name:
        return annotation.name == qualified
    simple = qualified.rsplit('.', 1)[-1]
    if annotation.name != simple:
        return False
    imports = [name for name, static in java_file.imports if not static]
    explicit = [name for name in imports if name.rsplit('.', 1)[-1] == simple]
    if explicit:
        return explicit == [qualified]
    if any(item.name == simple for item in java_file.types):
        return False
    return f'{qualified.rpartition(".")[0]}.*' in imports


def enablings(java_file):
    """Les types du fichier qui portent une annotation d'activation de la securite de methode."""
    found = []
    for java_type in java_file.types:
        for annotation in java_type.annotations:
            for qualified in (ENABLE_METHOD_SECURITY, ENABLE_GLOBAL_METHOD_SECURITY):
                if resolves(annotation, java_file, qualified):
                    state, written = _state(annotation, qualified)
                    found.append(Enabling(java_file.path, java_type.qualified_name, annotation, qualified, state,
                                          written))
    return found


def _state(annotation, qualified):
    """`@EnableMethodSecurity` active `@PreAuthorize` par defaut ; `@EnableGlobalMethodSecurity` seulement avec
    `prePostEnabled = true`. Un attribut qui n'est pas un litteral booleen laisse l'etat inconnu."""
    values = annotation.arguments.get(PRE_POST)
    written = values[0].written.strip() if values and len(values) == 1 else None
    if values and written not in ('true', 'false'):
        return UNKNOWN, written
    if written is None:
        return (ENABLED if qualified == ENABLE_METHOD_SECURITY else DISABLED), None
    return (ENABLED if written == 'true' else DISABLED), written


def guard(java_file, java_type, method, handler):
    """L'expression `@PreAuthorize` de la methode, sinon celle du type ; None si aucune ne la garde."""
    for annotations, symbol in ((method.annotations, handler), (java_type.annotations,
                                                                f'symbol:java:{java_type.qualified_name}')):
        found = [item for item in annotations if resolves(item, java_file, PRE_AUTHORIZE)]
        if found:
            values = found[0].arguments.get('value') or []
            expression = values[0].text if len(values) == 1 and values[0].resolved else None
            return Guard(symbol, found[0], expression)
    return None


def csrf(java_file):
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
            disabled = _disables(call, following)
            end = following.line_end if disabled and not call.arguments else call.line_end
            found.append(Csrf(java_file.path, symbol, call.line_start, end, disabled))
    return found


def _disables(call, following):
    """Vrai pour `csrf().disable()`, `csrf(c -> c.disable())` et `csrf(AbstractHttpConfigurer::disable)`."""
    if not call.arguments:
        return following is not None and following.name == DISABLE and not following.arguments
    if len(call.arguments) != 1:
        return False
    argument = call.arguments[0]
    function = argument.function
    if function is None:
        return argument.value.written.replace(' ', '').endswith(f'::{DISABLE}')
    return (function.complete and len(function.parameters) == 1 and len(function.chains) == 1
            and function.chains[0].receiver == function.parameters[0] and function.chains[0].names == (DISABLE,))
