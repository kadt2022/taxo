"""TAXO-01K : les sites d'appel tels que le lecteur Java les ecrit, sans rien resoudre."""
import pytest

from app.evaluators.java import sites, syntax


def read(body, package='p'):
    source = f'package {package};\n{body}\n'.encode('utf-8')
    return sites.of(syntax.parse('p/A.java', source))


def one(body):
    [site] = read(body)
    return site


def test_a_site_is_located_in_utf8_bytes_of_its_line():
    site = one('class A { void g() { String é = "é"; this.f(é); } void f(String s) {} }')
    line = 'class A { void g() { String é = "é"; this.f(é); } void f(String s) {} }'.encode('utf-8')
    assert line[site.column_start:site.column_end].decode('utf-8') == 'this.f(é)'
    assert (site.line_start, site.line_end) == (2, 2)


def test_a_site_spans_every_line_of_its_expression():
    site = one('class A { void g() {\n  f(\n    1);\n} void f(int x) {} }')
    assert (site.line_start, site.line_end, site.column_start, site.column_end) == (3, 4, 2, 6)


@pytest.mark.parametrize('call, receiver, written', [
    ('f()', sites.IMPLICIT, None), ('this.f()', sites.THIS, 'this'), ('super.f()', sites.SUPER, 'super'),
    ('b.f()', sites.NAME, 'b'), ('this.b.f()', sites.THIS_FIELD, 'this.b'), ('b.c.f()', sites.EXPRESSION, None),
    ('g().f()', sites.EXPRESSION, None), ('A.this.f()', sites.EXPRESSION, None),
])
def test_the_receiver_is_what_the_code_writes(call, receiver, written):
    site = next(item for item in read(f'class A {{ void m() {{ {call}; }} }}') if item.name == 'f')
    assert (site.form, site.receiver, site.written) == (sites.METHOD, receiver, written)


def test_creations_and_constructor_calls_are_sites_without_a_name():
    found = read('class A { A() { this(new A(1)); } A(A a) {} A(int x) {} }')
    assert [(site.form, site.name, site.member) for site in found] == [
        (sites.CONSTRUCTOR, None, '<init>()'), (sites.CREATION, None, '<init>()')]


def test_the_owner_is_the_member_type_and_the_member_its_signature():
    [site] = read('class A { static class In { void g(java.util.List<String> a, int... b) { f(); } } }')
    assert (site.owner, site.member, site.context) == ('p.A.In', 'g(java.util.List,int[])', sites.BODY)


@pytest.mark.parametrize('body, context, owner', [
    ('class A { int x = f(); }', sites.INITIALIZER, 'p.A'),
    ('class A { { f(); } }', sites.INITIALIZER, 'p.A'),
    ('class A { void g() { Runnable r = () -> f(); } }', sites.NESTED, 'p.A'),
    ('class A { void g() { new Object() { void h() { f(); } }; } }', sites.NESTED, 'p.A'),
    ('class A { void g() { class L { void h() { f(); } } } }', sites.NESTED, 'p.A'),
    ('enum A { X { void h() { f(); } }; void f() {} }', sites.NESTED, 'p.A'),
])
def test_a_site_outside_a_member_body_says_where_it_is(body, context, owner):
    site = next(item for item in read(body) if item.name == 'f')
    assert (site.context, site.owner) == (context, owner)


@pytest.mark.parametrize('body, variable', [
    ('void g(B b) { b.f(); }', sites.PARAMETER),
    ('void g(B... b) { b.f(); }', sites.PARAMETER),
    ('void g() { B b = null; b.f(); }', sites.LOCAL),
    ('void g() { try (B b = null) { b.f(); } }', sites.LOCAL),
    ('void g() { for (B b : l) { b.f(); } }', sites.LOCAL),
    ('void g() { for (B b = null; ; ) { b.f(); } }', sites.LOCAL),
    ('void g() { try { } catch (B b) { b.f(); } }', sites.LOCAL),
    ('void g(int k) { switch (k) { case 1: B b = null; break; default: b.f(); } }', sites.LOCAL),
    ('void g() { B b = ((b = null) != null ? b.f() : null); }', sites.LOCAL),
    ('void g() { B c = null, b = c != null ? b.f() : null; }', sites.LOCAL),
    ('void g(Object o) { if (o instanceof B b) { b.f(); } }', sites.PATTERN),
    ('void g() { b.f(); }', None),
])
def test_a_name_declared_in_the_member_and_visible_at_the_site_is_a_variable(body, variable):
    site = next(item for item in read(f'class A {{ B b; {body} }}') if item.name == 'f')
    assert site.variable == variable


@pytest.mark.parametrize('body', [
    'void g() { b.f(); B b = null; }',
    'void g() { { B b = null; } b.f(); }',
    'void g() { for (B b : l) { } b.f(); }',
    'void g() { try (B b = null) { } finally { b.f(); } }',
    'void g() { java.util.function.Consumer<B> c = b -> {}; b.f(); }',
    'void g() { java.util.function.BiConsumer<B, B> c = (a, b) -> {}; b.f(); }',
    'void g() { Runnable r = () -> { B b = null; }; b.f(); }',
    'void g() { new Object() { B b; }; b.f(); }',
])
def test_a_name_declared_elsewhere_in_the_body_still_names_the_field(body):
    """TAXO-01L : la portee reelle. Un nom declare apres le site, dans un autre bloc, dans une lambda ou une classe
    anonyme ne masque pas le champ au site."""
    site = next(item for item in read(f'class A {{ B b; {body} }}') if item.name == 'f')
    assert (site.variable, site.declaration) == (None, None)


def test_a_name_declared_twice_in_the_body_is_ranked_in_file_order():
    found = [item.declaration for item in read(
        'class A { void g() { for (B b : l) { b.f(); } { B b = null; b.f(); } B c = null; c.f(); } }')]
    assert [(item.kind, item.name, item.written, item.line) for item in found] == [
        (sites.LOCAL, 'b#1', 'B', 2), (sites.LOCAL, 'b#2', 'B', 2), (sites.LOCAL, 'c', 'B', 2)]


@pytest.mark.parametrize('declaration, written, named', [
    ('B b', 'B', True), ('p.B b', 'p.B', True), ('java.util.List<B> b', 'java.util.List', True),
    ('B[] b', 'B[]', True), ('B b[]', 'B[]', True), ('var b', 'var', False), ('T b', 'T', False),
    ('U b', 'U', False), ('L b', 'L', False),
])
def test_a_variable_says_its_written_type_and_whether_it_names_a_type(declaration, written, named):
    """Ne nomment aucun type : `var`, une variable de type de la classe (`T`) ou de la methode (`U`), un type local."""
    site = next(item for item in read(f'class A<T> {{ <U> void g() {{ class L {{}} {declaration} = null; b.f(); }} }}')
                if item.name == 'f')
    assert (site.declaration.written, site.declaration.named) == (written, named)


@pytest.mark.parametrize('body, named', [
    ('void g(L b) { b.f(); { class L {} } }', True),
    ('void g() { { class L {} } L b = null; b.f(); }', True),
    ('void g() { L b = null; b.f(); class L {} }', True),
    ('void g() { class L {} L b = null; b.f(); }', False),
    ('void g(int k) { switch (k) { case 1: class L {} break; default: L b = null; b.f(); } }', False),
])
def test_a_local_type_hides_a_source_type_only_where_it_is_visible(body, named):
    site = next(item for item in read(f'class A {{ {body} }}') if item.name == 'f')
    assert site.declaration.named == named


def test_a_catch_union_names_no_single_type_and_a_parameter_its_array():
    found = [item.declaration for item in read(
        'class A { void g(B... v) { v.f(); try { } catch (E1 | E2 e) { e.f(); } } }')]
    assert [(item.kind, item.written, item.named) for item in found] == [
        (sites.PARAMETER, 'B[]', True), (sites.LOCAL, 'E1|E2', False)]


def test_a_compact_record_constructor_has_the_components_for_parameters():
    [site] = read('record R(B b) { R { b.f(); } }')
    assert (site.variable, site.declaration.name, site.declaration.written) == (sites.PARAMETER, 'b', 'B')


def test_a_site_in_a_lambda_designates_no_variable_of_the_body():
    [site] = read('class A { void g(B b) { Runnable r = () -> b.f(); } }')
    assert (site.context, site.variable) == (sites.NESTED, None)


@pytest.mark.parametrize('argument, literal', [
    ('1', 'int'), ('1L', 'long'), ('0x1F', 'int'), ('1.5', 'double'), ('1.5f', 'float'), ('"s"', 'String'),
    ('"""\n  s"""', 'String'), ("'c'", 'char'), ('true', 'boolean'), ('false', 'boolean'), ('null', 'null'),
    ('x', None), ('1 + 2', None),
])
def test_an_argument_is_typed_only_when_it_is_a_literal(argument, literal):
    site = next(item for item in read(f'class A {{ void g(int x) {{ f({argument}); }} }}') if item.name == 'f')
    assert site.arguments == (literal,)


def test_a_file_without_tree_has_no_site():
    assert sites.of(syntax.JavaFile('p/A.java', 'p', (), (), False)) == ()


def test_a_compact_record_constructor_is_the_canonical_constructor():
    """JLS 8.10.4 : le constructeur compact prend les composants du record pour parametres."""
    [site] = read('record R(int x, String y) { R { f(); } void f() {} }')
    assert (site.owner, site.member, site.context) == ('p.R', '<init>(int,String)', sites.BODY)


def test_record_components_are_fields_and_only_unwritten_accessors_are_implicit():
    """TAXO-01L, JLS 8.10.3 : chaque composant est un champ ; son accesseur est implicite sans `x()` ecrit."""
    source = (b'package p;\nrecord R(boolean b, int n,\n T t, String... xs) {\n'
              b' int n() { return n; } int b(int i) { return i; } }\n')
    [record] = syntax.parse('p/R.java', source).types
    assert [(item.name, item.written_type, item.line, item.component) for item in record.fields] == [
        ('b', 'boolean', 2, True), ('n', 'int', 2, True), ('t', 'T', 3, True), ('xs', 'String[]', 3, True)]
    assert [item.name for item in record.implicit_accessors] == ['b', 't', 'xs']
