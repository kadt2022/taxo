"""Les sites d'appel d'un fichier Java (TAXO-01K, ARCHITECTURE § 14) : ce qui est ecrit, jamais ce qui s'execute.

Chaque appel de methode, creation d'objet (`new T(...)`) et appel de constructeur (`this(...)`, `super(...)`) est un
site, y compris dans l'argument d'un autre appel. Un site dit ou il est ecrit (lignes, colonnes en octets UTF-8
de la ligne, a partir de 0, fin exclue), la methode ou le constructeur dont il est ecrit directement dans le corps,
et ce que le code ecrit de son receveur. Un site d'une lambda, d'une classe anonyme ou locale n'est pas attribue a
la methode englobante : il est marque imbrique. Rien n'est resolu ici : le lecteur ne connait aucun framework et ne
choisit aucune cible.
"""
from dataclasses import dataclass

from . import syntax

# La forme d'un site.
METHOD = 'METHOD'
CREATION = 'CREATION'
CONSTRUCTOR = 'CONSTRUCTOR'
# Ou il est ecrit : directement dans le corps d'une methode ou d'un constructeur, dans une lambda ou une classe
# anonyme ou locale de ce corps, ou hors de tout corps (initialiseur de champ, bloc d'initialisation).
BODY = 'BODY'
NESTED = 'NESTED'
INITIALIZER = 'INITIALIZER'
# Ce que le code ecrit du receveur d'un appel de methode.
IMPLICIT = 'IMPLICIT'          # f()
THIS = 'THIS'                  # this.f()
SUPER = 'SUPER'                # super.f()
NAME = 'NAME'                  # x.f() : une variable, un champ ou un nom de type
THIS_FIELD = 'THIS_FIELD'      # this.x.f()
EXPRESSION = 'EXPRESSION'      # tout le reste : a.b.f(), g().f(), (x).f(), Outer.this.f()...
# Ce que designe un nom de receveur declare dans le corps qui porte le site.
PARAMETER = 'PARAMETER'
LOCAL = 'LOCAL'

_INVOCATIONS = {'method_invocation': METHOD, 'object_creation_expression': CREATION,
                'explicit_constructor_invocation': CONSTRUCTOR}
_MEMBERS = ('method_declaration', 'constructor_declaration')
# Un corps de classe sans nom : classe anonyme, ou corps propre d'une constante d'enum.
_ANONYMOUS = ('object_creation_expression', 'enum_constant')
_BODIES = ('class_body', 'interface_body', 'enum_body', 'enum_body_declarations', 'annotation_type_body')
# Les noeuds qui declarent une variable par leur champ `name`.
_DECLARING = ('variable_declarator', 'formal_parameter', 'catch_formal_parameter', 'enhanced_for_statement',
              'resource', 'instanceof_expression', 'type_pattern', 'record_pattern_component')
_LITERALS = {'string_literal': 'String', 'text_block': 'String', 'true': 'boolean', 'false': 'boolean',
             'character_literal': 'char', 'null_literal': 'null'}
_INTEGERS = ('decimal_integer_literal', 'hex_integer_literal', 'octal_integer_literal', 'binary_integer_literal')
_FLOATS = ('decimal_floating_point_literal', 'hex_floating_point_literal')


@dataclass(frozen=True)
class Site:
    """Un site d'appel. `owner` est le type qualifie, de premier niveau ou membre, qui le porte ; `member` la
    signature de la methode ou du constructeur dont le corps le contient (None dans un initialiseur). `written` est le
    receveur ecrit quand il est un nom (`x`, `this.x`, `this`, `super`), `variable` ce que ce nom designe s'il est
    declare dans ce corps. `arguments` donne, pour chaque argument, le type de son litteral, ou None."""
    owner: str
    member: str | None
    context: str
    form: str
    name: str | None
    receiver: str | None
    written: str | None
    variable: str | None
    arguments: tuple
    line_start: int
    line_end: int
    column_start: int
    column_end: int


def of(java_file):
    """Les sites du fichier, dans l'ordre du fichier."""
    if java_file.root is None:
        return ()
    reader = _Reader(java_file.package)
    return tuple(reader.site(node) for node in _walk(java_file.root) if node.type in _INVOCATIONS)


class _Reader:
    def __init__(self, package):
        self.package = package
        self._declared = {}

    def site(self, node):
        owner, member, context = self._place(node)
        form = _INVOCATIONS[node.type]
        name = receiver = written = variable = None
        if form == METHOD:
            name = _text(node.child_by_field_name('name'))
            receiver, written = _receiver(node.child_by_field_name('object'))
            if receiver == NAME and member is not None:
                variable = self._variable(member, written)
        arguments = tuple(_literal(item) for item in _named(node.child_by_field_name('arguments')))
        return Site(owner, syntax.signature(member) if member is not None else None, context, form, name, receiver,
                    written, variable, arguments, node.start_point[0] + 1, node.end_point[0] + 1,
                    node.start_point[1], node.end_point[1])

    def _place(self, node):
        """(type qualifie, noeud de la methode ou du constructeur, contexte) qui portent le site `node`."""
        member, nested, parent = None, False, node.parent
        while parent is not None:
            if parent.type == 'lambda_expression' or (parent.type == 'class_body'
                                                      and parent.parent.type in _ANONYMOUS):
                nested = True
            elif parent.type in _MEMBERS:
                member = parent
            elif parent.type in syntax.TYPE_DECLARATIONS:
                if _member_level(parent):
                    break
                nested = True
            parent = parent.parent
        if member is None:
            return self._qualified(parent), None, INITIALIZER
        return self._qualified(parent), member, NESTED if nested else BODY

    def _qualified(self, declaration):
        names = []
        while declaration is not None:
            if declaration.type in syntax.TYPE_DECLARATIONS:
                names.append(_text(declaration.child_by_field_name('name')))
            declaration = declaration.parent
        return '.'.join(([self.package] if self.package else []) + list(reversed(names)))

    def _variable(self, member, name):
        """PARAMETER ou LOCAL si `name` est declare dans la methode `member`, ou n'importe ou dans son corps
        (lambda, boucle, ressource, motif, classe locale...) : un tel nom masque un champ, et sa portee exacte n'est
        pas suivie. None s'il n'y est pas declare."""
        key = member.id
        if key not in self._declared:
            parameters = {_text(item.child_by_field_name('name')) for item in
                          _named(member.child_by_field_name('parameters')) if item.type == 'formal_parameter'}
            parameters |= {_text(declarator.child_by_field_name('name')) for item in
                           _named(member.child_by_field_name('parameters')) if item.type == 'spread_parameter'
                           for declarator in item.named_children if declarator.type == 'variable_declarator'}
            body = member.child_by_field_name('body')
            self._declared[key] = (parameters, set(_declared_names(body)) if body is not None else set())
        parameters, locals_ = self._declared[key]
        if name in parameters:
            return PARAMETER
        return LOCAL if name in locals_ else None


def _receiver(node):
    """(forme du receveur, nom ecrit) d'un appel de methode."""
    if node is None:
        return IMPLICIT, None
    if node.type == 'this':
        return THIS, 'this'
    if node.type == 'super':
        return SUPER, 'super'
    if node.type == 'identifier':
        return NAME, _text(node)
    if node.type == 'field_access':
        holder, field = node.child_by_field_name('object'), node.child_by_field_name('field')
        if holder is not None and holder.type == 'this' and field is not None and field.type == 'identifier':
            return THIS_FIELD, f'this.{_text(field)}'
    return EXPRESSION, None


def _declared_names(body):
    for node in _walk(body):
        if node.type in _DECLARING:
            name = node.child_by_field_name('name')
            if name is not None and name.type == 'identifier':
                yield _text(name)
        elif node.type == 'lambda_expression':
            parameters = node.child_by_field_name('parameters')
            if parameters is not None and parameters.type == 'identifier':
                yield _text(parameters)
        elif node.type == 'inferred_parameters':
            yield from (_text(item) for item in node.named_children if item.type == 'identifier')


def _literal(node):
    """Le type d'un argument litteral (`int`, `long`, `float`, `double`, `char`, `boolean`, `String`, `null`), ou
    None pour toute autre expression : les expressions ne sont pas typees."""
    if node.type in _LITERALS:
        return _LITERALS[node.type]
    text = _text(node)
    if node.type in _INTEGERS:
        return 'long' if text[-1] in 'lL' else 'int'
    if node.type in _FLOATS:
        return 'float' if text[-1] in 'fF' else 'double'
    return None


def _member_level(declaration):
    """Vrai si le type n'est declare dans aucun corps de methode : de premier niveau ou membre d'un autre type."""
    parent = declaration.parent
    while parent is not None and parent.type != 'program':
        if parent.type not in _BODIES and parent.type not in syntax.TYPE_DECLARATIONS:
            return False
        parent = parent.parent
    return True


def _text(node):
    return node.text.decode('utf-8') if node is not None else ''


def _named(node):
    return [child for child in node.named_children if 'comment' not in child.type] if node is not None else []


def _walk(node):
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.named_children))
