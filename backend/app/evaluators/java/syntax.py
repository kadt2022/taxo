"""Analyseur Java (TAXO-03, ADR 0003) : les primitives Java d'un fichier source, lues par sa syntaxe.

Il donne le paquetage, les imports, les types (classes, interfaces, enums, records, types imbriques), leurs
annotations et leurs methodes annotees, et les constantes chaines (`static final String`). Une valeur
d'annotation est resolue quand elle est ecrite dans le code : une chaine, une concatenation de chaines, une
constante du meme type, d'un type du meme fichier ou d'un type connu (`constants`). Sinon, elle est rendue telle qu'ecrite, marquee non resolue : l'analyseur ne devine
jamais.

Il ne connait aucun framework : ni endpoint, ni controleur. Ce sont les evaluateurs de framework qui donnent
un sens a ces primitives. Aucun Gradle ni Maven n'est execute, aucun jar n'est lu : seules les sources comptent.
"""
from dataclasses import dataclass, field

import tree_sitter_java
from tree_sitter import Language, Parser

_LANGUAGE = Language(tree_sitter_java.language())
_TYPES = {'class_declaration': 'class', 'interface_declaration': 'interface', 'enum_declaration': 'enum',
          'record_declaration': 'record', 'annotation_type_declaration': 'annotation'}
# Au-dela, une concatenation n'est plus lue : une valeur d'annotation n'en a jamais autant.
MAX_PARTS = 64


@dataclass(frozen=True)
class Value:
    """Une valeur d'annotation : `text` si elle est resolue, sinon `written` (le code tel qu'ecrit)."""
    text: str | None
    written: str

    @property
    def resolved(self):
        return self.text is not None


@dataclass(frozen=True)
class Annotation:
    name: str
    line_start: int
    line_end: int
    # Arguments par nom ; l'argument sans nom est `value`. Chaque argument est une liste (tableau ou valeur seule).
    arguments: dict = field(default_factory=dict)

    @property
    def simple_name(self):
        return self.name.rsplit('.', 1)[-1]


@dataclass(frozen=True)
class Method:
    name: str
    line_start: int
    line_end: int
    annotations: tuple = ()


@dataclass(frozen=True)
class JavaType:
    name: str
    qualified_name: str
    kind: str
    line_start: int
    line_end: int
    annotations: tuple = ()
    methods: tuple = ()
    constants: dict = field(default_factory=dict)
    # Supertypes (classe etendue, interfaces), tels qu'ecrits, avec leur nom qualifie s'il est connu, sinon None.
    supertypes: tuple = ()


@dataclass(frozen=True)
class JavaFile:
    path: str
    package: str
    imports: tuple
    types: tuple
    # Vrai si l'arbre syntaxique contient des erreurs : le fichier n'est lu qu'en partie.
    has_errors: bool

    def constants(self):
        """Constantes chaines du fichier, par nom qualifie de leur type."""
        return {item.qualified_name: item.constants for item in self.types}


def parse(path, source: bytes, constants=None):
    """Primitives du fichier Java `path`. `constants` : les constantes deja connues d'autres fichiers, par
    nom qualifie de type ; elles servent a resoudre `Type.CONSTANTE`."""
    tree = Parser(_LANGUAGE).parse(source)
    root = tree.root_node
    package = ''
    imports = []
    for child in root.named_children:
        if child.type == 'package_declaration':
            package = _text(_first(child, ('scoped_identifier', 'identifier')))
        elif child.type == 'import_declaration':
            imports.append(_import(child))
    reader = _Reader(package, tuple(imports), constants or {})
    types = []
    for child in root.named_children:
        if child.type in _TYPES:
            reader.collect(child, package, types)
    # Les constantes d'abord (tous les types du fichier), puis les annotations qui peuvent les citer.
    types = [reader.complete(item) for item in types]
    return JavaFile(path, package, tuple(imports), tuple(types), root.has_error)


def _text(node):
    return node.text.decode('utf-8') if node is not None else ''


def _first(node, kinds):
    return next((child for child in node.named_children if child.type in kinds), None)


def _import(node):
    static = any(child.type == 'static' for child in node.children)
    name = _text(_first(node, ('scoped_identifier', 'identifier')))
    wildcard = any(child.type == 'asterisk' for child in node.children)
    return (name + ('.*' if wildcard else ''), static)


def _lines(node):
    return node.start_point[0] + 1, node.end_point[0] + 1


class _Reader:
    def __init__(self, package, imports, known):
        self.package, self.imports, self.known = package, imports, dict(known)
        self._pending = {}

    def collect(self, node, outer, types):
        """Enregistre le type `node` et ses types imbriques ; leurs constantes sont lues avant toute annotation."""
        name = _text(node.child_by_field_name('name'))
        qualified = f'{outer}.{name}' if outer else name
        body = node.child_by_field_name('body')
        self._pending[qualified] = (node, name)
        self.known[qualified] = self._constants(body, qualified)
        types.append(qualified)
        for child in _members(body):
            if child.type in _TYPES:
                self.collect(child, qualified, types)

    def complete(self, qualified):
        node, name = self._pending[qualified]
        return JavaType(name, qualified, _TYPES[node.type], *_lines(node), self._annotations(node, qualified),
                        self._methods(node, qualified), self.known[qualified], self._supertypes(node, qualified))

    def _methods(self, node, owner):
        """Methodes et constructeurs annotes du type."""
        methods = []
        for member in _members(node.child_by_field_name('body')):
            if member.type not in ('method_declaration', 'constructor_declaration'):
                continue
            annotations = self._annotations(member, owner)
            if annotations:
                methods.append(Method(_text(member.child_by_field_name('name')), *_lines(member), annotations))
        return tuple(methods)

    def _supertypes(self, node, owner):
        supertypes = []
        for kind in ('superclass', 'interfaces', 'extends_interfaces'):
            clause = node.child_by_field_name(kind) or _first(node, (kind,))
            if clause is not None:
                supertypes += [(_text(item), self._type(_text(item), owner)) for item in _type_names(clause)]
        return tuple(supertypes)

    def _constants(self, body, qualified):
        """Constantes chaines `static final` du type, dans l'ordre : une constante peut citer les precedentes."""
        found = {}
        self.known[qualified] = found
        interface = body is not None and body.type == 'interface_body'
        for member in _members(body):
            if not _string_constant(member, interface):
                continue
            for name, value in _initialized(member):
                resolved = self._value(value, qualified)
                if resolved.resolved:
                    found[name] = resolved.text
        return found

    def _annotations(self, node, owner):
        modifiers = _first(node, ('modifiers',))
        children = modifiers.named_children if modifiers is not None else ()
        return tuple(Annotation(_text(child.child_by_field_name('name')), *_lines(child),
                                self._arguments(child.child_by_field_name('arguments'), owner))
                     for child in children if child.type in ('annotation', 'marker_annotation'))

    def _arguments(self, listing, owner):
        """Arguments d'une annotation par nom ; l'argument sans nom est `value`."""
        arguments = {}
        for argument in listing.named_children if listing is not None else ():
            if argument.type == 'element_value_pair':
                arguments[_text(argument.child_by_field_name('key'))] = self._values(
                    argument.child_by_field_name('value'), owner)
            elif argument.type != 'comment':
                arguments['value'] = self._values(argument, owner)
        return arguments

    def _values(self, node, owner):
        if node.type == 'element_value_array_initializer':
            return [self._value(item, owner) for item in node.named_children if item.type != 'comment']
        return [self._value(node, owner)]

    def _value(self, node, owner, depth=0):
        text = self._resolve(node, owner, depth + 1) if depth <= MAX_PARTS else None
        return Value(text, _text(node))

    def _resolve(self, node, owner, depth):
        """Texte de l'expression `node` si elle est ecrite dans le code (chaine, concatenation, constante)."""
        kind = node.type
        if kind == 'string_literal':
            literal = _literal(node)
            return literal.text if literal else None
        if kind == 'identifier':
            return self._constant(owner, _text(node))
        if kind == 'field_access':
            holder = self._type(_text(node.child_by_field_name('object')), owner)
            return self.known.get(holder, {}).get(_text(node.child_by_field_name('field')))
        if kind == 'parenthesized_expression' and node.named_children:
            return self._value(node.named_children[0], owner, depth).text
        if kind == 'binary_expression' and _text(node.child_by_field_name('operator')) == '+':
            left = self._value(node.child_by_field_name('left'), owner, depth)
            right = self._value(node.child_by_field_name('right'), owner, depth)
            return left.text + right.text if left.resolved and right.resolved else None
        return None

    def _scopes(self, owner):
        """Le type `owner`, puis ses types englobants, jusqu'au paquetage exclu."""
        scope = owner
        while scope:
            yield scope
            scope = scope.rpartition('.')[0] if scope != self.package else ''

    def _constant(self, owner, name):
        """Constante `name` vue depuis le type `owner` : le type et ses types englobants, puis les imports statiques."""
        for scope in self._scopes(owner):
            if name in self.known.get(scope, {}):
                return self.known[scope][name]
        for imported in (entry for entry, static in self.imports if static):
            holder, _, member = imported.rpartition('.')
            if member in (name, '*'):
                value = self.known.get(holder, {}).get(name)
                if value is not None or member == name:
                    return value
        return None

    def _type(self, written, owner):
        """Nom qualifie du type ecrit `written`, s'il est connu sans ambiguite ; sinon None."""
        if written in self.known:
            return written
        head, _, rest = written.partition('.')
        plain = [name for name, static in self.imports if not static]
        candidates = [f'{scope}.{head}' for scope in self._scopes(owner)]
        candidates += [name for name in plain if name.rsplit('.', 1)[-1] == head]
        candidates.append(f'{self.package}.{head}' if self.package else head)
        candidates += [f'{name[:-2]}.{head}' for name in plain if name.endswith('.*')]
        full = (f'{candidate}.{rest}' if rest else candidate for candidate in candidates)
        return next((name for name in full if name in self.known), None)


def _string_constant(member, interface):
    """Un champ `static final String` (implicite dans une interface) ?"""
    if member.type not in ('field_declaration', 'constant_declaration'):
        return False
    words = _text(_first(member, ('modifiers',))).split()
    constant = member.type == 'constant_declaration' or interface or ('static' in words and 'final' in words)
    return constant and _text(member.child_by_field_name('type')) in ('String', 'java.lang.String')


def _initialized(member):
    """(nom, valeur) de chaque variable initialisee du champ."""
    for declarator in member.named_children:
        value = declarator.child_by_field_name('value') if declarator.type == 'variable_declarator' else None
        if value is not None:
            yield _text(declarator.child_by_field_name('name')), value


def _members(body):
    for child in body.named_children if body is not None else ():
        if child.type == 'enum_body_declarations':
            yield from child.named_children
        else:
            yield child


def _type_names(clause):
    for child in clause.named_children:
        if child.type in ('type_identifier', 'scoped_type_identifier', 'generic_type'):
            yield _base(child)
        elif child.type == 'type_list':
            yield from _type_names(child)


def _base(node):
    return _first(node, ('type_identifier', 'scoped_type_identifier')) if node.type == 'generic_type' else node


def _literal(node):
    parts = []
    for child in node.named_children:
        if child.type == 'string_fragment':
            parts.append(_text(child))
        elif child.type == 'escape_sequence':
            escaped = _ESCAPES.get(_text(child))
            if escaped is None:
                return None
            parts.append(escaped)
        else:
            return None
    return Value(''.join(parts), _text(node))


_ESCAPES = {'\\"': '"', "\\'": "'", '\\\\': '\\', '\\n': '\n', '\\t': '\t', '\\r': '\r', '\\/': '/'}
