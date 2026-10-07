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
    ('void g() { java.util.function.Consumer<B> c = b -> {}; b.f(); }', sites.LOCAL),
    ('void g() { java.util.function.BiConsumer<B, B> c = (a, b) -> {}; b.f(); }', sites.LOCAL),
    ('void g() { b.f(); }', None),
])
def test_a_name_declared_in_the_member_is_a_variable(body, variable):
    site = next(item for item in read(f'class A {{ B b; {body} }}') if item.name == 'f')
    assert site.variable == variable


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
