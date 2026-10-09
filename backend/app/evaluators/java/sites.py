"""Les sites d'appel d'un fichier Java (TAXO-01K, ARCHITECTURE § 14) : ce qui est ecrit, jamais ce qui s'execute.

Chaque appel de methode, creation d'objet (`new T(...)`) et appel de constructeur (`this(...)`, `super(...)`) est un
site, y compris dans l'argument d'un autre appel. Un site dit ou il est ecrit (lignes, colonnes en octets UTF-8
de la ligne, a partir de 0, fin exclue), la methode ou le constructeur dont il est ecrit directement dans le corps,
et ce que le code ecrit de son receveur. Un receveur nomme designe le parametre ou la variable locale visible au site
(TAXO-01L) : declare dans un bloc qui englobe le site, avant lui ; sinon un champ ou un type. Un site d'une lambda,
d'une classe anonyme ou locale n'est pas attribue a la methode englobante : il est marque imbrique. Rien n'est resolu
ici : le lecteur ne connait aucun framework et ne choisit aucune cible.
"""
from collections import Counter
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
# Une variable de motif (`o instanceof B b`) : sa portee suit le flot du code ; elle n'est pas suivie.
PATTERN = 'PATTERN'

_INVOCATIONS = {'method_invocation': METHOD, 'object_creation_expression': CREATION,
                'explicit_constructor_invocation': CONSTRUCTOR}
# Un corps de classe sans nom : classe anonyme, ou corps propre d'une constante d'enum.
_ANONYMOUS = ('object_creation_expression', 'enum_constant')
_BODIES = ('class_body', 'interface_body', 'enum_body', 'enum_body_declarations', 'annotation_type_body')
# Ce qui, dans un corps, appartient a un autre proprietaire : lambda, classe anonyme ou locale.
_ELSEWHERE = ('lambda_expression', 'class_body', *syntax.TYPE_DECLARATIONS)
_PATTERNS = ('type_pattern', 'record_pattern_component')
# Les noeuds dont `_declarators` donne les variables, chacune une seule fois.
_DECLARING = ('local_variable_declaration', 'enhanced_for_statement', 'catch_clause', 'resource_specification')
_LITERALS = {'string_literal': 'String', 'text_block': 'String', 'true': 'boolean', 'false': 'boolean',
             'character_literal': 'char', 'null_literal': 'null'}
_INTEGERS = ('decimal_integer_literal', 'hex_integer_literal', 'octal_integer_literal', 'binary_integer_literal')
_FLOATS = ('decimal_floating_point_literal', 'hex_floating_point_literal')


@dataclass(frozen=True)
class Variable:
    """Un parametre ou une variable locale. `name` est son nom dans un symbole : suivi de son rang de declaration dans
    le corps (`b#2`, ordre du fichier) quand le corps declare ce nom plusieurs fois, pour ne pas dependre des lignes.
    `written` est son type ecrit (sans arguments de type) ; `named` est faux quand ce type ne nomme aucun type :
    `var`, variable de type, type local au corps, union d'un `catch`. `line` est la ligne de son nom."""
    kind: str
    name: str
    written: str
    named: bool
    line: int


@dataclass(frozen=True)
class Site:
    """Un site d'appel. `owner` est le type qualifie, de premier niveau ou membre, qui le porte ; `member` la
    signature de la methode ou du constructeur dont le corps le contient (None dans un initialiseur). `written` est le
    receveur ecrit quand il est un nom (`x`, `this.x`, `this`, `super`), `variable` ce que ce nom designe s'il est
    declare dans ce corps et visible au site, `declaration` ce parametre ou cette variable. `arguments` donne, pour
    chaque argument, le type de son litteral, ou None."""
    owner: str
    member: str | None
    context: str
    form: str
    name: str | None
    receiver: str | None
    written: str | None
    variable: str | None
    declaration: object
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
        self._bodies = {}

    def site(self, node):
        owner, member, context = self._place(node)
        form = _INVOCATIONS[node.type]
        name = receiver = written = variable = declaration = None
        if form == METHOD:
            name = _text(node.child_by_field_name('name'))
            receiver, written = _receiver(node.child_by_field_name('object'))
            if receiver == NAME and context == BODY:
                variable, declaration = self._body(member).designated(node, written)
        arguments = tuple(_literal(item) for item in _named(node.child_by_field_name('arguments')))
        return Site(owner, syntax.signature(member) if member is not None else None, context, form, name, receiver,
                    written, variable, declaration, arguments, node.start_point[0] + 1, node.end_point[0] + 1,
                    node.start_point[1], node.end_point[1])

    def _place(self, node):
        """(type qualifie, noeud de la methode ou du constructeur, contexte) qui portent le site `node`."""
        member, nested, parent = None, False, node.parent
        while parent is not None:
            if parent.type == 'lambda_expression' or (parent.type == 'class_body'
                                                      and parent.parent.type in _ANONYMOUS):
                nested = True
            elif parent.type in syntax.CALLABLES:
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

    def _body(self, member):
        if member.id not in self._bodies:
            self._bodies[member.id] = _Body(member)
        return self._bodies[member.id]


class _Body:
    """Les parametres et les variables locales d'une methode ou d'un constructeur, dans l'ordre du fichier, sans
    ceux de ses lambdas et de ses classes anonymes ou locales : ils appartiennent a un autre proprietaire."""

    def __init__(self, member):
        self.member = member
        self.parameters = _parameters(member)
        locals_, self.patterns = _scan(member.child_by_field_name('body'))
        self.variables = _variables(member, self.parameters, locals_)

    def designated(self, node, name):
        """(PARAMETER, LOCAL ou PATTERN, la declaration) que le nom `name` designe au noeud `node`, ou (None, None)
        s'il n'y designe ni parametre ni variable locale : un champ ou un type. Java interdit qu'une variable locale
        en masque une autre : la declaration visible est unique."""
        found = next((item for item in self._visible(node) if _text(item.child_by_field_name('name')) == name), None)
        if found is not None:
            variable = self.variables[found.id]
            return variable.kind, variable
        return (PATTERN, None) if name in self.patterns else (None, None)

    def _visible(self, node):
        """Les declarations visibles au noeud `node`, des blocs qui l'englobent jusqu'aux parametres."""
        child = node
        while child.id != self.member.id:
            parent = child.parent
            yield from _before(parent, child)
            child = parent
        yield from self.parameters


def _scan(body):
    """(variables locales, noms de variables de motif) du corps, dans l'ordre du fichier."""
    locals_, patterns = [], set()
    for node in _own(body):
        if node.type in _DECLARING:
            locals_ += _declarators(node)
        elif node.type in _PATTERNS:
            patterns.update(_text(item) for item in node.named_children if item.type == 'identifier')
        elif node.type == 'instanceof_expression' and node.child_by_field_name('name') is not None:
            patterns.add(_text(node.child_by_field_name('name')))
    return locals_, patterns


def _variables(member, parameters, locals_):
    """Chaque declaration, par l'identifiant de son noeud : son nom de symbole, rang compris si le nom est declare
    plusieurs fois, et son type ecrit ; un type dont le nom est cache la ou la variable est declaree (variable de
    type, type local visible) ne nomme aucun type des sources."""
    variables = syntax.type_variables(member)
    declaring = parameters + locals_
    counts, seen, found = Counter(_text(item.child_by_field_name('name')) for item in declaring), Counter(), {}
    for kind, items in ((PARAMETER, parameters), (LOCAL, locals_)):
        for item in items:
            name = _text(item.child_by_field_name('name'))
            seen[name] += 1
            written = _declared_type(item)
            head = written.partition('.')[0].partition('[')[0]
            hidden = variables | _local_types(item, member)
            found[item.id] = Variable(kind, f'{name}#{seen[name]}' if counts[name] > 1 else name, written,
                                      written != 'var' and '|' not in written and head not in hidden,
                                      item.child_by_field_name('name').start_point[0] + 1)
    return found


def _local_types(node, member):
    """Les noms des types locaux visibles au noeud `node` : declares avant lui dans un bloc qui l'englobe (JLS 6.3).
    Le composant d'un record, parametre de son constructeur compact, est hors du corps : aucun ne l'est."""
    names, child = set(), node
    while child.id != member.id and child.parent is not None:
        parent = child.parent
        if parent.type in ('block', 'switch_block_statement_group'):
            names.update(_text(item.child_by_field_name('name')) for item in parent.named_children
                         if item.type in syntax.TYPE_DECLARATIONS and item.start_byte < child.start_byte)
        child = parent
    return names


def _before(parent, child):
    """Les declarations du noeud `parent` visibles dans son enfant `child` (JLS 6.3)."""
    if parent.type == 'local_variable_declaration':
        yield from (item for item in _declarators(parent) if item.start_byte < child.start_byte)
    elif parent.type in ('block', 'switch_block_statement_group'):
        for item in parent.named_children:
            if item.start_byte >= child.start_byte:
                break
            if item.type == 'local_variable_declaration':
                yield from _declarators(item)
    elif parent.type == 'switch_block':
        # Une variable declaree dans un groupe `case ...:` est visible dans la suite du bloc du switch.
        for group in parent.named_children:
            if group.start_byte >= child.start_byte:
                break
            if group.type == 'switch_block_statement_group':
                yield from (declarator for item in group.named_children
                            if item.type == 'local_variable_declaration' for declarator in _declarators(item))
    elif parent.type == 'for_statement':
        init = parent.child_by_field_name('init')
        if init is not None and init.id != child.id and init.type == 'local_variable_declaration':
            yield from _declarators(init)
    elif parent.type in ('enhanced_for_statement', 'catch_clause', 'try_with_resources_statement'):
        if _is(parent.child_by_field_name('body'), child):
            yield from _declarators(parent)
    elif parent.type == 'resource_specification':
        yield from (item for item in _declarators(parent) if item.start_byte < child.start_byte)


def _declarators(node):
    """Les noeuds qui declarent, par leur champ `name`, une variable du noeud `node`."""
    if node.type == 'local_variable_declaration':
        return [item for item in node.named_children if item.type == 'variable_declarator']
    if node.type == 'enhanced_for_statement':
        return [node]
    if node.type == 'catch_clause':
        return [item for item in node.named_children if item.type == 'catch_formal_parameter']
    if node.type == 'try_with_resources_statement':
        return _declarators(node.child_by_field_name('resources') or _first(node, 'resource_specification'))
    if node.type == 'resource_specification':
        return [item for item in node.named_children
                if item.type == 'resource' and item.child_by_field_name('name') is not None]
    return []


def _parameters(member):
    """Les parametres de la methode ou du constructeur ; ceux d'un constructeur compact sont les composants du
    record (JLS 8.10.4). Le parametre recepteur (`B this`) n'est pas une variable."""
    listing = member.child_by_field_name('parameters')
    if member.type == 'compact_constructor_declaration':
        listing = member.parent.parent.child_by_field_name('parameters')
    found = []
    for item in _named(listing):
        if item.type == 'formal_parameter' and _text(item.child_by_field_name('name')).split('.')[-1] != 'this':
            found.append(item)
        elif item.type == 'spread_parameter':
            found += [declarator for declarator in item.named_children if declarator.type == 'variable_declarator']
    return found


def _declared_type(declaring):
    """Le type ecrit d'un parametre ou d'une variable, ses dimensions reportees ; une union de `catch` est ecrite
    `A|B` ; un parametre variable (`B... b`) est un tableau."""
    parent = declaring.parent
    if declaring.type == 'catch_formal_parameter':
        return '|'.join(syntax.written_type(item) for item in _named(_first(declaring, 'catch_type')))
    if parent.type == 'spread_parameter':
        written = next(item for item in parent.named_children
                       if item.type not in ('modifiers', 'variable_declarator', 'marker_annotation', 'annotation'))
        return syntax.written_type(written) + '[]'
    holder = parent if declaring.type == 'variable_declarator' else declaring
    return syntax.written_type(holder.child_by_field_name('type'), declaring.child_by_field_name('dimensions'))


def _own(body):
    """Les noeuds du corps `body`, sans entrer dans ce qui appartient a un autre proprietaire (qui est rendu)."""
    pending = [body] if body is not None else []
    while pending:
        current = pending.pop()
        yield current
        if current.type not in _ELSEWHERE:
            pending.extend(reversed(current.named_children))


def _is(node, other):
    return node is not None and node.id == other.id


def _first(node, kind):
    return next((item for item in node.named_children if item.type == kind), None) if node is not None else None


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
