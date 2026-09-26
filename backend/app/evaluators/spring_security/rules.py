"""Les regles d'autorisation d'URL de Spring Security, lues dans les chaines d'appels de l'analyseur Java.

Une configuration est une methode qui appelle `authorizeHttpRequests` (ou `authorizeRequests`, Spring
Security 5) : ses regles dans l'ordre (`requestMatchers(...)` puis une action), et son perimetre
(`securityMatcher(...)`). Une regle ou un perimetre que ce module ne sait pas lire est marque non lu, avec
sa raison : il ne devine jamais un motif, un verbe ou une action.

La correspondance d'une route a un motif a trois issues : toutes les requetes de la route correspondent
(ALL), aucune (NONE), ou certaines seulement, ou on ne sait pas (SOME). Seul ALL permet de conclure.
"""
import re
from dataclasses import dataclass, replace

AUTHORIZE = ('authorizeHttpRequests', 'authorizeRequests')
# Regles d'une configuration : un matcher, puis une action.
PATH_MATCHERS = {'requestMatchers', 'antMatchers', 'mvcMatchers'}
ANY_REQUEST = 'anyRequest'
DISPATCHER = 'dispatcherTypeMatchers'
MATCHERS = {*PATH_MATCHERS, ANY_REQUEST, DISPATCHER, 'regexMatchers'}
PERMIT = 'permitAll'
# Actions qui exigent une autorisation : la route est protegee, par la regle ecrite.
PROTECTING = {'authenticated', 'fullyAuthenticated', 'rememberMe', 'denyAll', 'hasRole', 'hasAnyRole',
              'hasAuthority', 'hasAnyAuthority', 'hasIpAddress', 'access'}
# Options de la configuration sans effet sur la correspondance d'une requete ordinaire.
NEUTRAL = {'shouldFilterAllDispatcherTypes', 'filterSecurityInterceptorOncePerRequest'}
# Perimetre d'une chaine de filtres (Spring Security 6, puis 5).
SCOPE = {'securityMatcher', 'securityMatchers', 'requestMatcher', 'antMatcher', 'mvcMatcher', 'regexMatcher'}
IGNORING = 'ignoring'
# Types de dispatch qui ne sont jamais celui d'une requete ordinaire vers un endpoint.
OTHER_DISPATCHES = {'FORWARD', 'ERROR', 'INCLUDE'}
HTTP_METHODS = {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE'}
_VARIABLE = re.compile(r'\{[A-Za-z_]\w*}')
_ENDPOINT_VARIABLE = re.compile(r'\{[A-Za-z_]\w*(?::.*)?}')
# Emplacements de `PathRequest.toStaticResources().atCommonLocations()` (Spring Boot, StaticResourceLocation).
STATIC_RESOURCES = ('/css/**', '/js/**', '/images/**', '/webjars/**', '/favicon.*', '/*/icon-*')
_STATIC_WRITTEN = re.compile(r'(?:org\.springframework\.boot\.autoconfigure\.security\.servlet\.)?'
                             r'PathRequest\.toStaticResources\(\)\s*\.\s*atCommonLocations\(\)')

NONE, SOME, ALL = 0, 1, 2
HTTP_SECURITY = 'org.springframework.security.config.annotation.web.builders.HttpSecurity'
HTTP, OTHER, UNKNOWN = 'http', 'other', 'unknown'
# Expression SpEL qu'une lecture sure admet : une seule restriction, ou plusieurs jointes par `and`. Tout le
# reste (`or`, `true`, `permitAll`, une methode d'un bean...) peut tout permettre : la regle n'est pas lue.
_SPEL_ATOM = (r"(?:hasRole|hasAnyRole|hasAuthority|hasAnyAuthority|hasIpAddress)\(\s*'[^'()]+'"
              r"(?:\s*,\s*'[^'()]+')*\s*\)|isAuthenticated\(\)|isFullyAuthenticated\(\)|denyAll")
_RESTRICTIVE_SPEL = re.compile(rf'\s*(?:{_SPEL_ATOM})(?:\s+and\s+(?:{_SPEL_ATOM}))*\s*')
# `access(...)` avec un gestionnaire de Spring qui ne peut que restreindre.
_MANAGER = re.compile(r"(?:AuthorityAuthorizationManager\.)?(?:hasRole|hasAnyRole|hasAuthority|hasAnyAuthority)"
                      r'\(\s*"[^"()]+"(?:\s*,\s*"[^"()]+")*\s*\)|AuthenticatedAuthorizationManager\.'
                      r'(?:authenticated|fullyAuthenticated)\(\)')


@dataclass(frozen=True)
class Rule:
    """Une regle : ses motifs (vides si non lue), son verbe, son action telle qu'ecrite."""
    line_start: int
    line_end: int
    patterns: tuple = ()
    verb: str | None = None
    action: str = ''
    expression: str = ''
    readable: bool = True
    reason: str = ''
    # Le type qui decide, pour `access(variable)` dont le type est dans les sources.
    target: str | None = None
    # Lacune connue de la lecture de cette regle (antMatchers, par exemple).
    note: str = ''
    # Vrai pour une regle qui ne vise jamais une requete ordinaire (`dispatcherTypeMatchers(ERROR)`).
    never: bool = False

    @property
    def permits(self):
        return self.action == PERMIT

    def describe(self):
        if not self.readable:
            return f'ligne {self.line_start} : règle non lue ({self.reason})'
        prefix = f'{self.verb} ' if self.verb else ''
        scope = 'dispatch hors requête' if self.never else ' '.join(self.patterns)
        return f'ligne {self.line_start} : {prefix}{scope} -> {self.expression}'

    def references(self):
        """Une reference `route-pattern:` par motif ; le verbe, s'il y en a un, en fait partie."""
        prefix = f'{self.verb} ' if self.verb else ''
        return [f'route-pattern:{prefix}{pattern}' for pattern in self.patterns]

    def match(self, verb, route):
        """Issue de la regle pour la route : ALL, SOME ou NONE."""
        if self.never:
            return NONE
        if not self.readable:
            return SOME
        return min(_verb_match(self.verb, verb), max(match(pattern, route) for pattern in self.patterns))


@dataclass(frozen=True)
class Configuration:
    """Une chaine de filtres : ses regles, son perimetre (None s'il n'est pas lu, () s'il est global)."""
    path: str
    owner: str
    method: str | None
    rules: tuple
    scope: tuple | None
    line_start: int
    line_end: int
    reason: str = ''

    @property
    def symbol(self):
        return f'symbol:java:{self.owner}#{self.method}' if self.method else f'symbol:java:{self.owner}'

    @property
    def readable(self):
        return not self.reason

    def applies(self, route):
        """Issue du perimetre de la chaine pour la route."""
        if self.scope is None:
            return SOME
        if not self.scope:
            return ALL
        return max(match(pattern, route) for pattern in self.scope)


def configurations(java_file):
    """Configurations d'autorisation du fichier, et les motifs exclus de la securite (`ignoring()`)."""
    chains = java_file.chains({*AUTHORIZE, *SCOPE, 'requestMatchers', IGNORING})
    groups, ignored = {}, []
    inner = set()
    for chain in chains:
        for call in chain.calls:
            for argument in call.arguments:
                if argument.function is not None:
                    inner.update(argument.function.chains)
    for chain in chains:
        if chain in inner and IGNORING not in chain.names:
            continue
        if IGNORING in chain.names:
            ignored.append(_ignoring(chain))
            continue
        receiver = _receiver(chain, java_file)
        if receiver != OTHER:
            groups.setdefault((chain.owner, chain.method), []).append((chain, receiver))
    found = []
    for (owner, method), group in groups.items():
        if not any(set(AUTHORIZE) & set(chain.names) for chain, _ in group):
            continue
        configuration = _configuration(java_file.path, owner, method, [chain for chain, _ in group])
        if configuration.readable and any(receiver == UNKNOWN for _, receiver in group):
            # Un receveur de type inconnu est peut-etre HttpSecurity : la configuration est vue, pas lue.
            configuration = replace(configuration, rules=(), reason='receveur dont le type n’est pas établi')
        found.append(configuration)
    return found, ignored


def _receiver(chain, java_file):
    """HTTP si le receveur de la chaine est une variable de type HttpSecurity (celui de Spring, par son nom
    qualifie ou son import), OTHER s'il est d'un autre type, UNKNOWN si son type n'est pas etabli."""
    if chain.declared is None:
        return UNKNOWN
    written, qualified = chain.declared
    if written == HTTP_SECURITY:
        return HTTP
    imports = {name for name, static in java_file.imports if not static}
    spring = HTTP_SECURITY in imports or f'{HTTP_SECURITY.rpartition(".")[0]}.*' in imports
    if written == 'HttpSecurity' and qualified is None and spring:
        return HTTP
    return OTHER


def _configuration(path, owner, method, chains):
    authorizing = [(chain, index) for chain in chains for index, name in enumerate(chain.names) if name in AUTHORIZE]
    lines = [call for chain in chains for call in chain.calls]
    start, end = min(call.line_start for call in lines), max(call.line_end for call in lines)
    scope = _scope(chains, authorizing)
    if len(authorizing) != 1:
        return Configuration(path, owner, method, (), scope, start, end,
                             f'{len(authorizing)} blocs d’autorisation dans la même méthode')
    chain, index = authorizing[0]
    calls, reason = _rule_calls(chain, index)
    if reason:
        return Configuration(path, owner, method, (), scope, start, end, reason)
    return Configuration(path, owner, method, tuple(_rules(calls)), scope, start, end)


def _scope(chains, authorizing):
    """Motifs du perimetre de la chaine de filtres ; () si elle n'en declare pas, None s'il n'est pas lu."""
    patterns = []
    for chain in chains:
        limit = next((index for item, index in authorizing if item is chain), len(chain.calls))
        for call in chain.calls[:limit]:
            if call.name == 'requestMatchers' or (call.name in SCOPE and call.name != 'securityMatcher'):
                # `securityMatchers(...)`, `requestMatchers()` de Spring Security 5, matchers d'objets : non lus.
                return None
            if call.name == 'securityMatcher':
                found = [patterns_of(argument) for argument in call.arguments]
                if not found or None in found:
                    return None
                patterns += [pattern for group in found for pattern in group]
    return tuple(patterns)


def _ignoring(chain):
    """Motifs exclus de toute securite par `web.ignoring().requestMatchers(...)` ; None s'ils ne sont pas lus."""
    index = chain.names.index(IGNORING)
    patterns = []
    for call in chain.calls[index + 1:]:
        if call.name not in PATH_MATCHERS:
            return None, chain.calls[index].line_start
        found = [patterns_of(argument) for argument in call.arguments]
        if None in found:
            return None, chain.calls[index].line_start
        patterns += [pattern for group in found for pattern in group]
    return tuple(patterns) or None, chain.calls[index].line_start


def _rule_calls(chain, index):
    """Appels qui portent les regles : le corps de la lambda de `authorizeHttpRequests(...)`, ou la suite de la
    chaine jusqu'a `and()` (Spring Security 5). Sinon, la raison pour laquelle ils ne sont pas lus."""
    call = chain.calls[index]
    if not call.arguments:
        following = chain.calls[index + 1:]
        end = next((position for position, item in enumerate(following) if item.name == 'and'), len(following))
        return following[:end], ''
    function = call.arguments[0].function if len(call.arguments) == 1 else None
    if function is None or not function.complete or len(function.parameters) != 1:
        return (), f'argument de {call.name} non interprété'
    parameter = function.parameters[0]
    calls = []
    for inner in function.chains:
        if inner.receiver != parameter:
            return (), f'appel sur {inner.receiver} dans {call.name}'
        calls += inner.calls
    return calls, ''


def _rules(calls):
    """Regles dans l'ordre de declaration. Un appel inattendu devient une regle non lue, a sa place."""
    rules, pending = [], None
    for call in calls:
        if call.name in NEUTRAL:
            continue
        if call.name in MATCHERS:
            if pending is not None:
                rules.append(_unread(pending, pending, f'{pending.name} sans action'))
            pending = call
        elif pending is not None and (call.name == PERMIT or call.name in PROTECTING):
            rules.append(_rule(pending, call))
            pending = None
        else:
            rules.append(_unread(call, call, f'appel {call.name} non interprété'))
            pending = None
    if pending is not None:
        rules.append(_unread(pending, pending, f'{pending.name} sans action'))
    return rules


def _unread(first, last, reason):
    return Rule(first.line_start, last.line_end, readable=False, reason=reason)


def _rule(matcher, action):
    matched = _matcher(matcher)
    if isinstance(matched, str):
        return _unread(matcher, action, matched)
    patterns, verb, never, note = matched
    expression, target = _action(action)
    if expression is None:
        return _unread(matcher, action, target)
    return Rule(matcher.line_start, action.line_end, patterns, verb, action.name, expression,
                target=target, note=note, never=never)


def _matcher(call):
    """(motifs, verbe, jamais, lacune) du matcher, ou la raison pour laquelle il n'est pas lu."""
    if call.name == ANY_REQUEST:
        return ('/**',), None, False, ''
    if call.name == DISPATCHER:
        kinds = [argument.value.written.rsplit('.', 1)[-1] for argument in call.arguments]
        if kinds and all(kind in OTHER_DISPATCHES for kind in kinds):
            return (), None, True, ''
        return f'dispatcherTypeMatchers({", ".join(kinds)})'
    if call.name not in PATH_MATCHERS:
        return f'{call.name} non interprété'
    arguments = list(call.arguments)
    verb = _http_method(arguments[0].value.written) if arguments else None
    if verb is not None:
        arguments = arguments[1:]
    patterns = []
    for argument in arguments:
        found = patterns_of(argument)
        if found is None:
            return f'motif {argument.value.written}'
        patterns += found
    if not patterns and verb is None:
        return f'{call.name} sans motif'
    note = ('antMatchers (Spring Security 5) : variantes d’URL (barre finale, suffixe) non modélisées'
            if call.name == 'antMatchers' else '')
    return tuple(patterns) or ('/**',), verb, False, note


def _http_method(written):
    verb = written.rsplit('.', 1)[-1]
    if verb in HTTP_METHODS and written in (f'HttpMethod.{verb}', f'org.springframework.http.HttpMethod.{verb}'):
        return verb
    return None


def _action(call):
    """(expression ecrite, type qui decide) de l'action ; (None, raison) si elle n'est pas lue."""
    written = ', '.join(argument.value.written for argument in call.arguments)
    expression = f'{call.name}({written})'
    if call.name != 'access':
        return expression, None
    if len(call.arguments) != 1:
        return None, 'access sans argument unique'
    argument = call.arguments[0]
    if argument.value.text is not None:
        # Expression SpEL (Spring Security 5) : non evaluee, elle n'est lue que si elle ne peut que restreindre.
        if not _RESTRICTIVE_SPEL.fullmatch(argument.value.text):
            return None, f'access({argument.value.written}) : expression non évaluée'
        return expression, None
    declared = argument.declared
    if declared is not None and declared[1] is not None:
        # Gestionnaire du depot : la regle lui delegue la decision, qui n'est pas lue (lacune connue).
        return expression, f'symbol:java:{declared[1]}'
    if _MANAGER.fullmatch(argument.value.written):
        return expression, None
    return None, f'access({argument.value.written}) : gestionnaire non interprété'


def patterns_of(argument):
    """Motifs designes par un argument de matcher, ou None s'il n'est pas lu."""
    if argument.value.text is not None:
        return (argument.value.text,) if readable_pattern(argument.value.text) else None
    return STATIC_RESOURCES if _STATIC_WRITTEN.fullmatch(argument.value.written) else None


def readable_pattern(pattern):
    """Motif que ce module sait comparer : segments litteraux, `**`, `{variable}`, jokers `*` et `?`."""
    if not pattern.startswith('/'):
        return False
    return all(segment == '**' or _VARIABLE.fullmatch(segment) or not re.search(r'[{}\[\]]|\*\*', segment)
               for segment in _segments(pattern))


def match(pattern, route):
    """Issue de la correspondance du motif Spring a la route d'un endpoint : ALL, SOME ou NONE."""
    return _match(_segments(pattern), _segments(route))


def _segments(value):
    return tuple(segment for segment in value.split('/') if segment)


def _match(pattern, route):
    if not pattern:
        return ALL if not route else NONE
    head = pattern[0]
    if head == '**':
        return max(_match(pattern[1:], route[index:]) for index in range(len(route) + 1))
    if not route:
        return NONE
    segment = route[0]
    if segment.startswith('{*'):
        # Variable qui capture plusieurs segments : selon la requete, le motif correspond ou non.
        return SOME
    rest = _match(pattern[1:], route[1:])
    if head == '*' or _VARIABLE.fullmatch(head):
        return rest
    if _ENDPOINT_VARIABLE.fullmatch(segment):
        # Un segment litteral du motif ne correspond qu'a certaines valeurs de la variable.
        return min(rest, SOME)
    return rest if _segment_regex(head).fullmatch(segment) else NONE


def _segment_regex(segment):
    """Un segment de motif, jokers `*` (plusieurs caracteres) et `?` (un caractere) compris."""
    return re.compile(''.join('[^/]*' if char == '*' else '[^/]' if char == '?' else re.escape(char)
                              for char in segment))


def _verb_match(rule_verb, verb):
    if rule_verb is None:
        return ALL
    if verb == 'ANY':
        return SOME
    return ALL if rule_verb == verb else NONE
