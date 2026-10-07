"""TAXO-01K : la regle `java.calls.declared-receiver-unique-target/1`, cas par cas, sur des sources ecrites ici.

Chaque test dit une forme d'appel et ce que la regle en fait : un `CALLS` vers la seule declaration possible, ou le
site non interprete avec sa raison fermee. Jamais une cible devinee.
"""
import pytest

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.java_calls import arguments
from app.evaluators.java_calls.evaluator import JavaCallsEvaluator
from java_sources import snapshot

PACKAGE = 'p'


def java(name, body, imports=''):
    """Un fichier `p/<name>.java` qui contient `body`."""
    return f'p/{name}.java', f'package {PACKAGE};\n{imports}\n{body}\n'


def run(*sources):
    return RunEvaluator()(JavaCallsEvaluator(), snapshot(dict(sources)))


def short(reference):
    return reference.removeprefix(f'symbol:java:{PACKAGE}.')


def calls(execution):
    return {(short(fact['subject']), short(fact['object'])) for fact in execution.facts if fact['relation'] == 'CALLS'}


def declared(execution, relation):
    return {(short(fact['subject']), short(fact['object'])) for fact in execution.facts
            if fact['relation'] == relation}


def sites(execution):
    """Les sites non interpretes, par (proprietaire, methode appelee) : leur diagnostic."""
    return {(short(fact['subject']), site.get('method')): site for fact in execution.coverage
            if fact['coverage_type'] == 'NOT_INTERPRETED' for site in fact.get('diagnostic', {}).get('sites', [])}


def reason(execution, owner, method):
    return sites(execution)[owner, method]['reason']


def the_call(execution, subject, target):
    return next(fact for fact in execution.facts if fact['relation'] == 'CALLS'
                and short(fact['subject']) == subject and short(fact['object']) == target)


# Ce que la regle etablit.

def test_a_call_on_the_current_type_targets_its_own_declaration():
    execution = run(java('A', 'class A { void f() {} void g() { f(); this.f(); } }'))
    assert calls(execution) == {('A#g()', 'A#f()')}
    call = the_call(execution, 'A#g()', 'A#f()')
    assert len(call['evidence']) == 2, 'deux sites, une seule assertion'
    assert call['derivation']['premises'] == ['CONTAINS : symbol:java:p.A -> symbol:java:p.A#f()']


@pytest.mark.parametrize('receiver', ['b', 'this.b'])
def test_a_call_on_a_field_follows_its_declared_type(receiver):
    execution = run(java('A', f'class A {{ private B b; void g() {{ {receiver}.f(1); }} }}'),
                    java('B', 'class B { void f(int x) {} }'))
    assert calls(execution) == {('A#g()', 'B#f(int)')}
    assert the_call(execution, 'A#g()', 'B#f(int)')['derivation']['premises'] == [
        'TYPED_AS : symbol:java:p.A#b -> symbol:java:p.B', 'CONTAINS : symbol:java:p.B -> symbol:java:p.B#f(int)']
    assert ('A#b', 'B') in declared(execution, 'TYPED_AS')


def test_an_inherited_declaration_is_reached_through_its_supertypes():
    execution = run(java('A', 'class A { private C c; void g() { c.f(); } }'),
                    java('B', 'class B { void f() {} }'), java('C', 'class C extends B {}'))
    assert calls(execution) == {('A#g()', 'B#f()')}
    assert 'EXTENDS : symbol:java:p.C -> symbol:java:p.B' in the_call(execution, 'A#g()', 'B#f()')['derivation'][
        'premises']


def test_the_nearest_declaration_of_a_hierarchy_is_the_target():
    execution = run(java('A', 'class A { private C c; void g() { c.f(); } }'),
                    java('B', 'class B { void f() {} }'), java('C', 'class C extends B { void f() {} }'))
    assert calls(execution) == {('A#g()', 'C#f()')}


def test_a_call_on_an_interface_targets_the_interface_declaration():
    execution = run(java('A', 'class A { private J j; void g() { j.f(); } }'),
                    java('I', 'interface I { void f(); }'), java('J', 'interface J extends I {}'),
                    java('K', 'class K implements J { public void f() {} }'))
    assert calls(execution) == {('A#g()', 'I#f()')}, 'jamais une implementation'
    assert declared(execution, 'EXTENDS') == {('J', 'I')} and declared(execution, 'IMPLEMENTS') == {('K', 'J')}


def test_members_of_another_arity_are_the_counter_examples():
    execution = run(java('A', 'class A { void f() {} void f(int a, int b) {} void g() { f(); } }'))
    assert the_call(execution, 'A#g()', 'A#f()')['derivation']['counter_examples_checked'] == [
        'CONTAINS : symbol:java:p.A -> symbol:java:p.A#f(int,int)']


def test_a_literal_argument_chooses_nothing_but_can_rule_out():
    execution = run(java('A', 'class A { void f(int x) {} void g() { f("x"); } void h() { f(1); } }'))
    assert calls(execution) == {('A#h()', 'A#f(int)')}
    assert reason(execution, 'A#g()', 'f') == 'NO_MATCHING_DECLARATION'


def test_a_declared_object_method_is_a_call_like_any_other():
    execution = run(java('A', 'class A { public String toString() { return ""; } void g() { toString(); } }'))
    assert calls(execution) == {('A#g()', 'A#toString()')}


def test_extending_object_explicitly_adds_no_external_supertype():
    execution = run(java('A', 'class A extends Object { void f() {} void g() { f(); } }'))
    assert calls(execution) == {('A#g()', 'A#f()')}

# Ce que la regle laisse non interprete, avec sa raison.

def test_overloads_of_the_same_arity_are_ambiguous():
    execution = run(java('A', 'class A { void f(int x) {} void f(String x) {} void g(Object o) { f(o); } }'))
    site = sites(execution)['A#g(Object)', 'f']
    assert site['reason'] == 'OVERLOAD_AMBIGUOUS'
    assert site['candidates'] == ['symbol:java:p.A#f(int)', 'symbol:java:p.A#f(String)']


def test_a_varargs_declaration_is_ambiguous():
    execution = run(java('A', 'class A { void f(int... x) {} void g() { f(1); } }'))
    assert reason(execution, 'A#g()', 'f') == 'OVERLOAD_AMBIGUOUS'


def test_an_undeclared_object_method_is_ambiguous():
    execution = run(java('A', 'class A { void g() { hashCode(); } }'))
    assert reason(execution, 'A#g()', 'hashCode') == 'OVERLOAD_AMBIGUOUS'


def test_a_method_without_declaration_has_no_target():
    execution = run(java('A', 'class A { void g() { missing(); } }'))
    assert reason(execution, 'A#g()', 'missing') == 'NO_MATCHING_DECLARATION'


def test_a_field_of_an_external_type_names_it():
    execution = run(java('A', 'class A { private List<String> items; void g() { items.size(); } }',
                         'import java.util.List;'))
    site = sites(execution)['A#g()', 'size']
    assert (site['reason'], site['receiver'], site['receiver_type']) == (
        'TARGET_TYPE_OUTSIDE_SNAPSHOT', 'items', 'java.util.List')
    assert not declared(execution, 'TYPED_AS'), 'aucun symbole externe n est invente'


def test_an_external_supertype_hides_or_doubts_the_target():
    execution = run(java('A', 'class A { private R r; void g() { r.save(); r.mine(); } }'),
                    java('R', 'interface R extends Base { void mine(); }', 'import x.Base;'))
    save, mine = sites(execution)['A#g()', 'save'], sites(execution)['A#g()', 'mine']
    assert (save['reason'], save['external_supertypes']) == ('TARGET_DECLARATION_OUTSIDE_SNAPSHOT', ['x.Base'])
    assert (mine['reason'], mine['candidates']) == ('SUPER_TYPE_UNRESOLVED', ['symbol:java:p.R#mine()'])
    assert not calls(execution)


def test_a_supertype_declared_twice_makes_the_hierarchy_ambiguous():
    execution = run(java('A', 'class A { private C c; void g() { c.f(); } }'), java('C', 'class C extends B {}'),
                    java('B', 'class B { void f() {} }'), ('q/B.java', 'package p;\nclass B {}\n'))
    assert reason(execution, 'A#g()', 'f') == 'RECEIVER_TYPE_AMBIGUOUS'


def test_two_inherited_declarations_at_the_same_distance_are_ambiguous():
    execution = run(java('A', 'class A { private K k; void g() { k.f(); } }'), java('I', 'interface I { void f(); }'),
                    java('J', 'interface J { void f(); }'), java('K', 'interface K extends I, J {}'))
    site = sites(execution)['A#g()', 'f']
    assert site['reason'] == 'OVERLOAD_AMBIGUOUS'
    assert site['candidates'] == ['symbol:java:p.I#f()', 'symbol:java:p.J#f()']


def test_a_qualified_external_supertype_keeps_its_written_name():
    execution = run(java('A', 'class A { private R r; void g() { r.save(); } }'),
                    java('R', 'class R extends x.Base {}'))
    assert sites(execution)['A#g()', 'save']['external_supertypes'] == ['x.Base']


@pytest.mark.parametrize('kind, declaration, implicit', [
    ('enum', 'enum E { X; void f() {} }', 'java.lang.Enum'),
    ('record', 'record E(int x) { void f() {} }', 'java.lang.Record'),
])
def test_an_enum_or_a_record_has_an_external_superclass(kind, declaration, implicit):
    execution = run(java('A', 'class A { private E e; void g() { e.f(); } }'), java('E', declaration))
    site = sites(execution)['A#g()', 'f']
    assert (site['reason'], site['external_supertypes']) == ('SUPER_TYPE_UNRESOLVED', [implicit]), kind


@pytest.mark.parametrize('body, method', [
    ('Runnable r = () -> f();', 'f'),
    ('new Thread() { public void run() { f(); } };', 'f'),
    ('class Local { void h() { f(); } }', 'f'),
])
def test_a_call_in_a_lambda_or_a_local_class_is_not_attributed(body, method):
    execution = run(java('A', f'class A {{ void f() {{}} void g() {{ {body} }} }}'))
    assert reason(execution, 'A#g()', method) == 'LAMBDA_OR_LOCAL_CONTEXT'
    assert not calls(execution)


@pytest.mark.parametrize('source, owner, method', [
    ('class A { int x = f(); int f() { return 1; } }', 'A', 'f'),
    ('class B { void f() {} } class A extends B { void f() { super.f(); } }', 'A#f()', 'f'),
    ('class B { void f() {} } class A { void g() { new B().f(); } }', 'A#g()', 'f'),
    ('class A { void g() { new A(); } }', 'A#g()', None),
    ('class A { A() { this(1); } A(int x) {} }', 'A#<init>()', None),
    ('class B { static void f() {} } class A { void g() { B.f(); } }', 'A#g()', 'f'),
])
def test_forms_outside_the_first_fragment_are_unsupported(source, owner, method):
    execution = run(java('A', source))
    assert reason(execution, owner, method) == 'UNSUPPORTED_CALL_FORM'


@pytest.mark.parametrize('body', ['void g(B b) { b.f(); }', 'void g() { B b = new B(); b.f(); }',
                                  'private B b; void g() { for (B b : java.util.List.<B>of()) {} b.f(); }'])
def test_a_parameter_or_a_local_variable_is_deferred(body):
    execution = run(java('A', f'class A {{ {body} }}'), java('B', 'class B { void f() {} }'))
    assert reason(execution, next(owner for owner, _ in sites(execution)), 'f') == 'RECEIVER_KIND_DEFERRED'
    assert not calls(execution)


def test_an_unknown_name_or_a_type_variable_has_no_known_type():
    execution = run(java('A', 'class A<T> { private T t; void g() { t.f(); unknown.f(); } }'))
    assert {site['reason'] for site in sites(execution).values()} == {'RECEIVER_TYPE_UNKNOWN'}
    assert len([fact for fact in execution.coverage if fact.get('diagnostic')][0]['diagnostic']['sites']) == 2


def test_a_type_declared_twice_is_ambiguous():
    execution = run(java('A', 'class A { private B b; void g() { b.f(); } }'),
                    java('B', 'class B { void f() {} }'), ('q/B.java', 'package p;\nclass B { void f() { f(); } }\n'))
    assert reason(execution, 'A#g()', 'f') == 'RECEIVER_TYPE_AMBIGUOUS'
    assert set(sites(execution)) == {('A#g()', 'f')}, 'un proprietaire sans identite unique ne porte aucun site'
    noted = [fact for fact in execution.coverage if fact['coverage_type'] == 'NOT_INTERPRETED'
             and fact['subject'] == 'symbol:java:p.B']
    assert noted and all('plusieurs fois' in fact['reason'] for fact in noted)
    assert not any(short(fact['subject']) == 'B' for fact in execution.facts if fact['relation'] == 'CONTAINS')


def test_an_identity_shared_by_two_declarations_is_noted_and_never_targeted():
    execution = run(java('A', 'class A { void f(java.util.List<String> a) {} void f(java.util.List<Integer> a) {'
                              ' f(null); } void g() { f(null); } }'))
    assert reason(execution, 'A#g()', 'f') == 'OVERLOAD_AMBIGUOUS'
    assert set(sites(execution)) == {('A#g()', 'f')}
    assert not any('#f(' in fact['object'] for fact in execution.facts if fact['relation'] == 'CONTAINS')
    assert any('ambiguë' in fact.get('reason', '') for fact in execution.coverage)


def test_an_implicit_call_in_a_deeply_nested_type_targets_that_type():
    execution = run(java('A', 'class A { class In { class Deep { void f() {} void g() { f(); } } } }'))
    assert calls(execution) == {('A.In.Deep#g()', 'A.In.Deep#f()')}


@pytest.mark.parametrize('source, imports', [
    ('class A { void f() {} class In { void g() { f(); } } }', ''),
    ('class A { void f() {} class In { class Deep { void g() { f(); } } } }', ''),
    ('class A { void g() { f(); } }', 'import static q.Util.f;'),
    ('class A { void g() { f(); } }', 'import static q.Util.*;'),
])
def test_another_provider_of_an_implicit_call_makes_it_ambiguous(source, imports):
    execution = run(java('A', source, imports))
    assert {site['reason'] for site in sites(execution).values()} == {'OVERLOAD_AMBIGUOUS'}
    assert not calls(execution)


def test_a_file_read_in_part_stops_its_calls_and_the_run_says_so():
    execution = run(java('A', 'class A { private B b; void g() { b.f(); } }'),
                    java('B', 'class B { void f() {} void broken( }'))
    assert execution.status is EvaluationStatus.PARTIAL
    assert reason(execution, 'A#g()', 'f') == 'PARSE_ERROR'
    assert any('erreur de syntaxe' in warning for warning in execution.warnings)
    broken = [fact for fact in execution.coverage if fact['subject'] == 'file:p/B.java']
    assert [fact['coverage_type'] for fact in broken] == ['NOT_INTERPRETED']


def test_an_unreadable_file_is_a_read_error():
    execution = run(java('A', 'class A {}'), ('p/B.java', b'class B { String s = "\xff"; }'))
    assert execution.status is EvaluationStatus.PARTIAL
    assert [fact['coverage_type'] for fact in execution.coverage if fact['subject'] == 'file:p/B.java'] == [
        'READ_ERROR']


# Ce qui est declare.

def test_member_types_are_contained_by_their_outer_type():
    execution = run(java('A', 'class A { static class In { int x; void f() {} } }'))
    assert declared(execution, 'CONTAINS') == {('A', 'A.In'), ('A.In', 'A.In#x'), ('A.In', 'A.In#f()'),
                                               ('file:p/A.java', 'A')}


def test_test_sources_and_build_outputs_are_outside_the_scope():
    execution = run(java('A', 'class A {}'), ('src/test/java/p/T.java', 'package p; class T {}'),
                    ('target/p/G.java', 'package p; class G {}'))
    assert declared(execution, 'CONTAINS') == {('file:p/A.java', 'A')}
    [repository] = [fact for fact in execution.coverage if fact['subject'] == 'repository:depot']
    assert repository['scope']['exclude'] == ['directory:src/test', 'directory:target']


@pytest.mark.parametrize('field', ['B[] items;', 'B items[];'])
def test_an_array_field_is_not_typed_as_its_element(field):
    execution = run(java('A', f'class A {{ {field} void g() {{ items.clone(); }} }}'), java('B', 'class B {}'))
    assert not declared(execution, 'TYPED_AS')
    site = sites(execution)['A#g()', 'clone']
    assert (site['reason'], site['receiver_type']) == ('TARGET_TYPE_OUTSIDE_SNAPSHOT', 'B[]')


# Les implementations de methodes.

def implemented(execution):
    return {(short(fact['subject']), short(fact['object'])) for fact in execution.facts
            if fact['relation'] == 'IMPLEMENTS' and fact['status'] == 'INFERRED'}


def test_a_method_implements_the_same_signature_of_its_interface():
    execution = run(java('I', 'interface I { void f(int x); void g(); }'),
                    java('C', 'class C implements I { public void f(int x) {} public void g(String s) {} }'))
    assert implemented(execution) == {('C#f(int)', 'I#f(int)')}
    [fact] = [fact for fact in execution.facts if fact['relation'] == 'IMPLEMENTS' and fact['status'] == 'INFERRED']
    assert fact['derivation']['rule'] == 'java.implements.same-signature/1'
    assert fact['derivation']['premises'] == ['IMPLEMENTS : symbol:java:p.C -> symbol:java:p.I',
                                              'CONTAINS : symbol:java:p.C -> symbol:java:p.C#f(int)',
                                              'CONTAINS : symbol:java:p.I -> symbol:java:p.I#f(int)']


@pytest.mark.parametrize('kind', ['enum E implements I { X; public void f() {} }',
                                  'record E(int x) implements I { public void f() {} }'])
def test_an_enum_or_a_record_implements_too(kind):
    execution = run(java('I', 'interface I { void f(); }'), java('E', kind))
    assert implemented(execution) == {('E#f()', 'I#f()')}


@pytest.mark.parametrize('interface, implementation', [
    ('interface I { static void f() {} }', 'class C implements I { public void f() {} }'),
    ('interface I { private void f() {} }', 'class C implements I { public void f() {} }'),
    ('interface I { void f(); }', 'class C implements I { public static void f() {} }'),
    ('interface I { void f(); }', 'class C implements I { public C() {} }'),
    ('interface I { void f(int a); void f(int b); }', 'class C implements I { public void f(int a) {} }'),
    ('interface I { void f(); }', 'class C implements I { public void f() {} public void f() {} }'),
    ('interface I { void f(); }', 'interface C extends I { void f(); }'),
    ('interface I { void f(); }', 'class B implements I {} class C extends B { public void f() {} }'),
    ('interface J { void f(); } interface I extends J {}', 'class C implements I { public void f() {} }'),
    ('interface I { void f(); }', 'class C implements I, x.Other { public void g() {} }'),
])
def test_what_is_not_an_implementation_is_never_linked(interface, implementation):
    execution = run(java('I', interface), java('C', implementation))
    assert not implemented(execution)


def test_a_default_method_can_be_implemented():
    execution = run(java('I', 'interface I { default void f() {} }'),
                    java('C', 'class C implements I { public void f() {} }'))
    assert implemented(execution) == {('C#f()', 'I#f()')}


@pytest.mark.parametrize('broken', ['I', 'C'])
def test_a_type_read_in_part_or_declared_twice_has_no_implementation(broken):
    files = dict([java('I', 'interface I { void f(); }'), java('C', 'class C implements I { public void f() {} }')])
    files[f'p/{broken}.java'] = files[f'p/{broken}.java'].replace('}', '} oops(', 1)
    assert not implemented(run(*files.items()))
    twice = dict([java('I', 'interface I { void f(); }'), java('C', 'class C implements I { public void f() {} }'),
                  (f'q/{broken}.java', f'package p;\ninterface {broken} {{}}\n')])
    assert not implemented(run(*twice.items()))

# Les litteraux.

@pytest.mark.parametrize('literal, parameter, contradicted', [
    (None, 'int', False), ('int', 'long', False), ('long', 'int', True), ('String', 'int', True),
    ('String', 'java.lang.String', False), ('null', 'int', True), ('null', 'Integer', False),
    ('int', 'int[]', True), ('null', 'int[]', False), ('int', 'Course', False), ('char', 'int', False),
    ('double', 'Number', False), ('boolean', 'String', True),
])
def test_a_literal_contradicts_only_a_known_parameter_type(literal, parameter, contradicted):
    assert arguments.contradicts(literal, parameter) is contradicted


def test_applicability_compares_arguments_rank_by_rank():
    assert arguments.applicable(('int', None), ('long', 'String'))
    assert not arguments.applicable((None, 'int'), ('long', 'String'))


def test_a_compact_record_constructor_owns_its_call_sites():
    execution = run(java('R', 'record R(int x) { R { f(); } void f() {} }'))
    assert ('R', 'R#<init>(int)') in declared(execution, 'CONTAINS')
    assert reason(execution, 'R#<init>(int)', 'f') == 'SUPER_TYPE_UNRESOLVED', 'java.lang.Record reste externe'
