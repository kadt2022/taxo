"""Analyseur Java (TAXO-03, ARCHITECTURE § 7.3) : les primitives Java d'un fichier source, lues par sa syntaxe.

Il donne le paquetage, les imports, les types (classes, interfaces, enums, records, types imbriques), leurs
annotations et leurs methodes annotees, et les constantes chaines (`static final String`). Une valeur
d'annotation est resolue quand elle est ecrite dans le code : une chaine, une concatenation de chaines, une
constante du meme type, d'un type du meme fichier ou d'un type connu (`constants`). Sinon, elle est rendue telle qu'ecrite, marquee non resolue : l'analyseur ne devine
jamais.

Il donne toutes les declarations d'un type, annotees ou non (methodes, constructeurs, champs), avec leurs lignes et
leurs modificateurs, et resout un nom de type ecrit vers un type des sources (TAXO-01K).

Il donne aussi, a la demande, les chaines d'appels fluentes (`a.b(x).c(y)`) : chaque appel, ses arguments
(valeur resolue, corps d'une lambda, type declare d'une variable), la methode et le type qui les portent.

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
# Schema des references de methode (TAXO-ID-01) : signature syntaxique normalisee, types non resolus.
IDENTITY_SCHEMA = 'java-symbol-syntactic/1'
_SIMPLE_TYPES = {'type_identifier', 'integral_type', 'floating_point_type', 'boolean_type', 'void_type'}


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
    # Types des parametres, normalises (TAXO-ID-01) : identite syntaxique, jamais des types resolus.
    parameters: tuple = ()
    constructor: bool = False
    # Vrai si la declaration a un parametre variable (`T...`).
    varargs: bool = False
    # Ligne du nom : la preuve d'une declaration ne bouge pas quand son corps change.
    name_line: int = 0

    @property
    def signature(self):
        """`nom(Type,Type)`, ou `<init>(...)` pour un constructeur (schema `java-symbol-syntactic/1`)."""
        return f'{"<init>" if self.constructor else self.name}({",".join(self.parameters)})'


@dataclass(frozen=True)
class Supertype:
    """Un type ecrit dans une clause `extends` (`superclass`, `extends_interfaces`) ou `implements` (`interfaces`) :
    son nom ecrit, son nom qualifie s'il est un type des sources (sinon None), et sa ligne."""
    written: str
    qualified: str | None
    line: int
    clause: str


@dataclass(frozen=True)
class Field:
    """Un champ : son nom, son type ecrit (sans arguments de type) et, s'il est un type des sources, son nom
    qualifie ; `None` sinon (type externe, variable de type, primitif)."""
    name: str
    written_type: str
    qualified_type: str | None
    line: int
    # Vrai si le type ecrit est une variable de type (`T`) du type ou d'un type englobant.
    type_variable: bool = False


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
    # Signatures de toutes les methodes et constructeurs du type, annotes ou non : deux egales sont ambigues.
    signatures: tuple = ()
    # Toutes les declarations (TAXO-01K) : methodes et constructeurs annotes ou non, champs, supertypes avec leur
    # clause et leur ligne, ligne du nom.
    declarations: tuple = ()
    fields: tuple = ()
    clauses: tuple = ()
    name_line: int = 0

    def ambiguous(self, signature):
        """Vrai si plusieurs declarations du type partagent cette signature syntaxique normalisee."""
        return self.signatures.count(signature) > 1


@dataclass(frozen=True)
class Lambda:
    """Une lambda : ses parametres, et les chaines d'appels de son corps. `complete` est faux si son corps
    contient autre chose que des chaines d'appels (une condition, une boucle...)."""
    parameters: tuple
    chains: tuple
    complete: bool


@dataclass(frozen=True)
class Argument:
    """Un argument d'appel : sa valeur (resolue si elle est ecrite), la lambda qu'il est, ou, s'il nomme une
    variable, le type declare de celle-ci : (type ecrit, nom qualifie ou None)."""
    value: Value
    function: Lambda | None = None
    declared: tuple | None = None


@dataclass(frozen=True)
class Call:
    name: str
    line_start: int
    line_end: int
    arguments: tuple = ()


@dataclass(frozen=True)
class Chain:
    """Une chaine d'appels fluente, du receveur vers l'exterieur : `http.a().b()` donne `http`, puis a, b.
    `owner` est le type qualifie qui la porte, `method` la signature de sa methode (None hors d'une methode)."""
    owner: str
    method: str | None
    receiver: str
    calls: tuple
    # Type declare du receveur s'il est une variable : (type ecrit, nom qualifie ou None) ; None sinon.
    declared: tuple | None = None

    @property
    def names(self):
        return tuple(call.name for call in self.calls)


@dataclass(frozen=True)
class JavaFile:
    path: str
    package: str
    imports: tuple
    types: tuple
    # Vrai si l'arbre syntaxique contient des erreurs : le fichier n'est lu qu'en partie.
    has_errors: bool
    _root: object = field(default=None, compare=False, repr=False)
    _reader: object = field(default=None, compare=False, repr=False)

    @property
    def root(self):
        """L'arbre syntaxique du fichier, pour les lecteurs du paquetage Java ; None si le fichier n'a pas ete lu."""
        return self._root

    def resolve(self, written, owner):
        """Nom qualifie du type ecrit `written`, vu depuis le type `owner`, s'il est un type des sources connu sans
        ambiguite ; None sinon. Rien n'est devine : un type externe ou une variable de type n'est pas resolu."""
        return self._reader.type_of(written, owner) if self._reader is not None else None

    def imported(self, simple):
        """Nom qualifie d'un import explicite (non statique) dont le nom simple est `simple`, ou None."""
        return next((name for name, static in self.imports if not static and name.rsplit('.', 1)[-1] == simple), None)

    def constants(self):
        """Constantes chaines du fichier, par nom qualifie de leur type."""
        return {item.qualified_name: item.constants for item in self.types}

    def chains(self, names):
        """Chaines d'appels du fichier dont un appel porte l'un des noms `names`, dans l'ordre du fichier."""
        if self._root is None:
            return ()
        wanted = set(names)
        found = []
        for node in _walk(self._root):
            if node.type == 'method_invocation' and not _inner(node):
                chain = self._reader.chain(node)
                if wanted.intersection(chain.names):
                    found.append(chain)
        return tuple(found)


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
    return JavaFile(path, package, tuple(imports), tuple(types), root.has_error, root, reader)


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
                        self._methods(node, qualified), self.known[qualified], self._supertypes(node, qualified),
                        _signatures(node), _declarations(node), self._fields(node, qualified),
                        self._clauses(node, qualified),
                        node.child_by_field_name('name').start_point[0] + 1)

    def type_of(self, written, owner):
        return self._type(written, owner)

    def chain(self, node):
        """La chaine d'appels dont `node` est l'appel le plus exterieur."""
        owner, method = self._enclosing(node)
        calls = []
        while node.type == 'method_invocation':
            arguments = node.child_by_field_name('arguments')
            name = node.child_by_field_name('name')
            # Les lignes d'un appel vont de son nom a sa parenthese fermante, receveur exclu.
            calls.append(Call(_text(name), name.start_point[0] + 1, node.end_point[0] + 1,
                              tuple(self._argument(item, owner) for item in _named(arguments))))
            receiver = node.child_by_field_name('object')
            if receiver is None:
                break
            node = receiver
        receiver = _text(node) if node.type != 'method_invocation' else ''
        declared = self._declared(node, owner) if node.type == 'identifier' else None
        return Chain(owner, method, receiver, tuple(reversed(calls)), declared)

    def _enclosing(self, node):
        """Type qualifie et methode qui portent `node`."""
        names, method = [], None
        parent = node.parent
        while parent is not None:
            if parent.type in ('method_declaration', 'constructor_declaration') and method is None and not names:
                method = Method(_text(parent.child_by_field_name('name')), 0, 0, (),
                                _parameters(parent.child_by_field_name('parameters')),
                                parent.type == 'constructor_declaration').signature
            elif parent.type in _TYPES:
                names.append(_text(parent.child_by_field_name('name')))
            parent = parent.parent
        qualified = '.'.join(reversed(names))
        return (f'{self.package}.{qualified}' if self.package and qualified else qualified or self.package), method

    def _argument(self, node, owner):
        value = self._value(node, owner)
        if node.type == 'lambda_expression':
            return Argument(value, function=self._lambda(node))
        if node.type == 'identifier':
            return Argument(value, declared=self._declared(node, owner))
        return Argument(value)

    def _lambda(self, node):
        parameters = node.child_by_field_name('parameters')
        names = (_text(parameters),) if parameters.type == 'identifier' else tuple(
            _text(item.child_by_field_name('name') or item) for item in _named(parameters))
        body = node.child_by_field_name('body')
        if body.type == 'method_invocation':
            return Lambda(names, (self.chain(body),), True)
        if body.type != 'block':
            return Lambda(names, (), False)
        chains, complete = [], True
        for statement in _named(body):
            expression = statement.named_children[0] if statement.type == 'expression_statement' else None
            if expression is not None and expression.type == 'method_invocation':
                chains.append(self.chain(expression))
            else:
                complete = False
        return Lambda(names, tuple(chains), complete)

    def _declared(self, node, owner):
        """Type declare de la variable nommee par `node` : parametre, variable locale ou champ ; None si
        c'est un parametre de lambda ou si la declaration n'est pas trouvee."""
        name = _text(node)
        child, parent = node, node.parent
        while parent is not None:
            if parent.type == 'lambda_expression' and name in self._lambda_parameters(parent):
                return None
            written = _declaration(parent, name, child)
            if written is not None:
                return written, self._type(written, owner)
            child, parent = parent, parent.parent
        return None

    @staticmethod
    def _lambda_parameters(node):
        parameters = node.child_by_field_name('parameters')
        if parameters.type == 'identifier':
            return {_text(parameters)}
        return {_text(item.child_by_field_name('name') or item) for item in _named(parameters)}

    def _methods(self, node, owner):
        """Methodes et constructeurs annotes du type."""
        methods = []
        for member in _members(node.child_by_field_name('body')):
            if member.type not in ('method_declaration', 'constructor_declaration'):
                continue
            annotations = self._annotations(member, owner)
            if annotations:
                methods.append(Method(_text(member.child_by_field_name('name')), *_lines(member), annotations,
                                      _parameters(member.child_by_field_name('parameters')),
                                      member.type == 'constructor_declaration'))
        return tuple(methods)

    def _supertypes(self, node, owner):
        """Supertypes tels qu'ecrits : (type ecrit, nom qualifie ou None)."""
        return tuple((item.written, item.qualified) for item in self._clauses(node, owner))

    def _clauses(self, node, owner):
        found = []
        for kind in ('superclass', 'interfaces', 'extends_interfaces'):
            clause = node.child_by_field_name(kind) or _first(node, (kind,))
            if clause is not None:
                found += [Supertype(_text(item), self._type(_text(item), owner), item.start_point[0] + 1, kind)
                          for item in _type_names(clause)]
        return tuple(found)

    def _fields(self, node, owner):
        """Champs du type. Un champ type par une variable de type (`T`, du type ou d'un type englobant) n'a pas de
        type qualifie, meme si un type des sources porte le meme nom : la variable le masque."""
        fields, variables = [], _type_variables(node)
        for member in _members(node.child_by_field_name('body')):
            if member.type in ('field_declaration', 'constant_declaration'):
                written = _type_name(member.child_by_field_name('type'))
                variable = written.partition('.')[0] in variables
                qualified = None if variable else self._type(written, owner)
                fields += [_field(declarator, written, qualified, variable) for declarator in member.named_children
                           if declarator.type == 'variable_declarator']
        return tuple(fields)

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


def _named(node):
    return [child for child in node.named_children if child.type not in ('comment', 'line_comment',
                                                                        'block_comment')] if node is not None else []


def _walk(node):
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.named_children))


def _inner(node):
    """Vrai si l'appel `node` est le receveur d'un autre appel : il appartient a une chaine plus longue."""
    parent = node.parent
    return parent is not None and parent.type == 'method_invocation' and parent.child_by_field_name('object') == node


def _declaration(scope, name, before):
    """Type ecrit de la variable `name` declaree dans `scope` (avant `before` pour un bloc), ou None."""
    if scope.type in ('method_declaration', 'constructor_declaration'):
        for parameter in _named(scope.child_by_field_name('parameters')):
            if _text(parameter.child_by_field_name('name')) == name:
                return _type_text(parameter.child_by_field_name('type'))
        return None
    if scope.type == 'block':
        declarations = [item for item in scope.named_children
                        if item.type == 'local_variable_declaration' and item.start_byte < before.start_byte]
    elif scope.type in ('class_body', 'enum_body', 'interface_body', 'record_declaration'):
        declarations = [item for item in _members(scope) if item.type == 'field_declaration']
    else:
        return None
    for declaration in reversed(declarations):
        names = [_text(item.child_by_field_name('name')) for item in declaration.named_children
                 if item.type == 'variable_declarator']
        if name in names:
            return _type_text(declaration.child_by_field_name('type'))
    return None


def _type_text(node):
    return _text(_base(node)) if node is not None else None


def _field(declarator, written, qualified, variable):
    """Un champ d'une declaration : un tableau (`int x[]`) n'a ni type des sources ni variable de type."""
    name = declarator.child_by_field_name('name')
    dimensions = _dimensions(declarator.child_by_field_name('dimensions'))
    if dimensions:
        return Field(_text(name), written + '[]' * dimensions, None, name.start_point[0] + 1)
    return Field(_text(name), written, qualified, name.start_point[0] + 1, variable)


def _declarations(node):
    """Toutes les methodes et tous les constructeurs du type, annotes ou non, dans l'ordre du fichier."""
    return tuple(Method(_text(member.child_by_field_name('name')), *_lines(member), (),
                        _parameters(member.child_by_field_name('parameters')),
                        member.type == 'constructor_declaration',
                        any(item.type == 'spread_parameter'
                            for item in _named(member.child_by_field_name('parameters'))),
                        member.child_by_field_name('name').start_point[0] + 1)
                 for member in _members(node.child_by_field_name('body'))
                 if member.type in ('method_declaration', 'constructor_declaration'))


def _type_variables(node):
    """Variables de type visibles dans le type `node` : les siennes et celles des types qui l'englobent."""
    names = set()
    while node is not None:
        if node.type in _TYPES:
            names.update(_type_parameters(node))
        node = node.parent
    return names


def _type_parameters(node):
    parameters = node.child_by_field_name('type_parameters') or _first(node, ('type_parameters',))
    return tuple(_text(_first(item, ('type_identifier', 'identifier'))) for item in _named(parameters)
                 if item.type == 'type_parameter')


def signature(declaration):
    """Signature normalisee (`java-symbol-syntactic/1`) d'un noeud de methode ou de constructeur."""
    return Method(_text(declaration.child_by_field_name('name')), 0, 0, (),
                  _parameters(declaration.child_by_field_name('parameters')),
                  declaration.type == 'constructor_declaration').signature


TYPE_DECLARATIONS = frozenset(_TYPES)


def _signatures(node):
    return tuple(Method(_text(member.child_by_field_name('name')), 0, 0, (),
                        _parameters(member.child_by_field_name('parameters')),
                        member.type == 'constructor_declaration').signature
                 for member in _members(node.child_by_field_name('body'))
                 if member.type in ('method_declaration', 'constructor_declaration'))


def _parameters(node):
    """Types des parametres, normalises : noms, modificateurs, annotations, arguments de type et espaces
    exclus ; dimensions du declarateur reportees sur le type ; parametre variable `T...` ecrit `T[]`
    (JLS 8.4.1). Le parametre recepteur (`Foo this`) n'appartient pas a la signature."""
    types = []
    for parameter in _named(node):
        if parameter.type == 'formal_parameter':
            if _text(parameter.child_by_field_name('name')).split('.')[-1] == 'this':
                continue
            types.append(_type_name(parameter.child_by_field_name('type'))
                         + '[]' * _dimensions(parameter.child_by_field_name('dimensions')))
        elif parameter.type == 'spread_parameter':
            written = next(item for item in parameter.named_children
                           if item.type not in ('modifiers', 'variable_declarator', 'marker_annotation', 'annotation'))
            types.append(_type_name(written) + '[]')
    return tuple(types)


def _type_name(node):
    """Un type ecrit, sans annotation ni argument de type ; un nom compose reste compose."""
    if node is None:
        return ''
    if node.type in _SIMPLE_TYPES or node.type == 'identifier':
        return _text(node)
    if node.type in ('scoped_type_identifier', 'scoped_identifier'):
        # Un prefixe de paquetage peut etre lu comme `scoped_identifier` : il fait partie du nom ecrit.
        return '.'.join(_type_name(item) for item in node.named_children
                        if item.type in ('type_identifier', 'scoped_type_identifier', 'generic_type',
                                         'identifier', 'scoped_identifier'))
    if node.type == 'generic_type':
        return _type_name(_first(node, ('type_identifier', 'scoped_type_identifier')))
    if node.type == 'array_type':
        return _type_name(node.child_by_field_name('element')) + '[]' * _dimensions(
            node.child_by_field_name('dimensions'))
    if node.type == 'annotated_type':
        return _type_name(next((item for item in node.named_children
                                if item.type not in ('marker_annotation', 'annotation')), None))
    return ''.join(_text(node).split())


def _dimensions(node):
    return sum(1 for child in node.children if child.type == '[') if node is not None else 0


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
