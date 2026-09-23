"""Lecture ciblee de quelques constructions Spring, par expressions regulieres.

Jetable : un vrai analyseur Java (TAXO-03) remplacera ce fichier. Aucune de ces
expressions ne connait un projet : elles connaissent Spring MVC et Spring Security.
"""
import re
from dataclasses import dataclass

CLASS_MAPPING = re.compile(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?"([^"]*)"')
CLASS_DECLARATION = re.compile(r'\bclass\s+(\w+)')
METHOD_MAPPING = re.compile(r'@(Get|Post|Put|Delete|Patch)Mapping\b(?:\s*\(\s*(?:value\s*=\s*)?(?:"([^"]*)")?)?')
METHOD_DECLARATION = re.compile(r'^\s*(?:public|protected|private)\s+[^;={]*?\b(\w+)\s*\(')
INJECTED_FIELD = re.compile(r'^\s*(?:private|protected)\s+final\s+([A-Z]\w*)\s+(\w+)\s*;')
HTTP_METHOD = re.compile(r'HttpMethod\.(\w+)')
STRING_LITERAL = re.compile(r'"([^"]*)"')
ACTION = re.compile(r'\.\s*(\w+)\s*\(')

AUTHORIZE_BLOCK = '.authorizeHttpRequests('
MATCHERS = '.requestMatchers('
ANY_REQUEST = '.anyRequest('


@dataclass(frozen=True)
class Endpoint:
    verb: str
    path: str
    type_name: str
    handler: str
    class_mapping_line: int
    method_mapping_line: int
    declaration_line: int

    def reference(self):
        return f'endpoint:{self.verb} {self.path}'

    def handler_reference(self):
        return f'symbol:{self.type_name}#{self.handler}'


@dataclass(frozen=True)
class SecurityRule:
    patterns: tuple
    verb: str | None
    action: str
    argument: str
    line_start: int
    line_end: int
    readable: bool
    catch_all: bool = False

    def describe(self):
        scope = 'anyRequest()' if self.catch_all else ' '.join(self.patterns) or '(motif non lu)'
        prefix = f'{self.verb} ' if self.verb else ''
        return f'ligne {self.line_start} : {prefix}{scope} -> {self.action}'


def _line_of(text, index):
    return text.count('\n', 0, index) + 1


def _closing(text, opening):
    """Index of the parenthesis closing the one at `opening`, string literals skipped."""
    depth, index, quoted = 0, opening, False
    escape = chr(92)
    while index < len(text):
        char = text[index]
        if quoted:
            if char == escape:
                index += 2
                continue
            quoted = char != '"'
            index += 1
            continue
        if char == '"':
            quoted = True
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError('Parenthese non fermee.')


def _join(base, suffix):
    if not suffix:
        return base or '/'
    return f"{(base or '').rstrip('/')}/{suffix.lstrip('/')}"


def endpoints(text):
    """Endpoints declares par un controleur Spring MVC, dans l'ordre du fichier."""
    lines = text.split('\n')
    type_name = base = None
    base_line = 0
    pending = None
    found = []
    for number, line in enumerate(lines, start=1):
        if type_name is None:
            mapping = CLASS_MAPPING.search(line)
            if mapping:
                base, base_line = mapping.group(1), number
            declaration = CLASS_DECLARATION.search(line)
            if declaration:
                type_name = declaration.group(1)
            continue
        mapping = METHOD_MAPPING.search(line)
        if mapping:
            pending = (mapping.group(1).upper(), mapping.group(2) or '', number)
            continue
        declaration = METHOD_DECLARATION.match(line)
        if pending and declaration:
            verb, suffix, mapping_line = pending
            found.append(Endpoint(verb, _join(base, suffix), type_name, declaration.group(1),
                                  base_line, mapping_line, number))
            pending = None
    return tuple(found)


def _matcher_arguments(arguments):
    verb = HTTP_METHOD.search(arguments)
    patterns = tuple(STRING_LITERAL.findall(arguments))
    without_literals = STRING_LITERAL.sub('', arguments)
    if verb:
        without_literals = without_literals.replace(verb.group(0), '')
    readable = bool(patterns) and not re.search(r'\w', without_literals)
    return patterns, (verb.group(1) if verb else None), readable


def _action(text, closing, stop):
    """Action chainee apres la parenthese `closing` et avant `stop`, avec son argument."""
    action = ACTION.search(text, closing + 1, stop)
    if not action:
        return '', ''
    return action.group(1), text[action.end():_closing(text, action.end() - 1)].strip()


def security_rules(text):
    """Regles d'autorisation dans leur ordre de declaration, la premiere gagnante.

    `anyRequest()` ferme la liste : il capture toute route qu'aucune regle anterieure n'a prise.
    """
    start = text.find(AUTHORIZE_BLOCK)
    if start < 0:
        return ()
    block_end = _closing(text, text.index('(', start))
    rules, cursor = [], start
    while True:
        found = text.find(MATCHERS, cursor, block_end)
        if found < 0:
            break
        opening = text.index('(', found)
        closing = _closing(text, opening)
        patterns, verb, readable = _matcher_arguments(text[opening + 1:closing])
        following = text.find(MATCHERS, closing, block_end)
        stop = following if following > 0 else text.find(ANY_REQUEST, closing, block_end)
        action, argument = _action(text, closing, stop if stop > 0 else block_end)
        rules.append(SecurityRule(patterns, verb, action, argument,
                                  _line_of(text, found), _line_of(text, closing), readable))
        cursor = closing
    found = text.find(ANY_REQUEST, cursor, block_end)
    if found >= 0:
        closing = _closing(text, found + len(ANY_REQUEST) - 1)
        action, argument = _action(text, closing, block_end)
        rules.append(SecurityRule(('/**',), None, action, argument, _line_of(text, found),
                                  _line_of(text, closing), True, catch_all=True))
    return tuple(rules)


def matches(pattern, path):
    """Semantique simplifiee des motifs Spring : `**` en queue, `{variable}` et `*` sur un segment."""
    return _matches(_segments(pattern), _segments(path))


def _segments(value):
    return tuple(segment for segment in value.strip('/').split('/') if segment)


def _matches(pattern, path):
    if not pattern:
        return not path
    head = pattern[0]
    if head == '**':
        return len(pattern) == 1 or any(_matches(pattern[1:], path[index:])
                                        for index in range(len(path) + 1))
    if not path:
        return False
    if head == '*' or (head.startswith('{') and head.endswith('}')):
        return _matches(pattern[1:], path[1:])
    return head == path[0] and _matches(pattern[1:], path[1:])


def injected_fields(text):
    """Champs injectes : nom -> (type, ligne de declaration)."""
    fields = {}
    for number, line in enumerate(text.split('\n'), start=1):
        field = INJECTED_FIELD.match(line)
        if field:
            fields[field.group(2)] = (field.group(1), number)
    return fields


def invocations(text, field):
    """Lignes ou `field.quelqueChose(` est appele."""
    call = re.compile(rf'\b{re.escape(field)}\s*\.\s*\w+\s*\(')
    return tuple(number for number, line in enumerate(text.split('\n'), start=1)
                 if call.search(line))
