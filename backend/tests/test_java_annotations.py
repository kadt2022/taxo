"""Annotations observées sans interprétation (récit TAXO-MIP-ADT-01, PR A2 ; § 14 du récit).

La vérité est écrite à la main dans les sources ci-dessous. `@Toto` est une annotation fictive, inconnue de toute
bibliothèque : Taxo la relève comme `@Service`, sans rien en dire de plus.
"""
import pytest

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluators.java_calls.evaluator import JavaCallsEvaluator
from app.facts.contract import validate_fact
from java_sources import snapshot

ROOT = 'src/main/java/com/acme/'
SOURCES = {
    f'{ROOT}Toto.java': 'package com.acme;\n\npublic @interface Toto {\n    String role();\n}\n',
    f'{ROOT}Roles.java': 'package com.acme;\n\npublic final class Roles {\n'
                         '    public static final String ADMIN = "ADMIN";\n}\n',
    f'{ROOT}StudentService.java': '\n'.join([
        'package com.acme;',
        '',
        'import org.springframework.stereotype.Component;',
        'import org.example.flags.*;',
        '',
        '@Component',
        'public class StudentService {',
        '    @Toto(role = Roles.ADMIN)',
        '    public String get(Long id) { return null; }',
        '',
        '    @Toto(role = "ADMIN") @Flag(level = Levels.MAX)',
        '    public String get(String name) { return null; }',
        '',
        '    @Tag("a") @Tag("b")',
        '    public void tagged() { }',
        '',
        '    @Toto(role = "X")',
        '    public void twice(int a) { }',
        '    @Toto(role = "Y")',
        '    public void twice(int b) { }',
        '}',
        '']),
}
SERVICE = 'symbol:java:com.acme.StudentService'


@pytest.fixture(scope='module', name='annotated')
def annotated_fixture():
    execution = RunEvaluator()(JavaCallsEvaluator(), snapshot(SOURCES))
    assert all(validate_fact(fact) is None for fact in execution.facts)
    found = {}
    for fact in execution.facts:
        if fact['relation'] == 'ANNOTATED_WITH':
            found.setdefault(fact['subject'], []).append(fact)
    return found


def test_the_class_annotation_is_observed_as_written_and_nothing_else(annotated):
    fact, = annotated[SERVICE]
    assert (fact['object'], fact['status']) == ('annotation:org.springframework.stereotype.Component', 'OBSERVED')
    assert fact['qualifiers'] == {'written_name': 'Component', 'resolution': 'IMPORTED'}
    assert fact['evidence'][0]['line_start'] == 6
    assert not any(item['object'] == 'annotation:org.springframework.stereotype.Service'
                   for facts in annotated.values() for item in facts), 'jamais une annotation qui n’est pas écrite'


def test_an_unknown_annotation_is_kept_with_its_written_and_resolved_values(annotated):
    """B3 : `@Toto` est relevée sans interprétation ; une constante des sources est résolue, et le dit."""
    fact, = annotated[f'{SERVICE}#get(Long)']
    assert fact['object'] == 'annotation:com.acme.Toto'
    assert fact['qualifiers'] == {'written_name': 'Toto', 'resolution': 'SOURCE_TYPE', 'arguments': {
        'role': [{'written': 'Roles.ADMIN', 'resolved': True, 'value': 'ADMIN'}]}}


def test_an_overload_carries_only_its_own_annotations_and_an_unread_value_stays_written(annotated):
    """B1 : chaque surcharge a les siennes ; une valeur que le code n'écrit pas reste dans sa forme écrite."""
    facts = {fact['object']: fact for fact in annotated[f'{SERVICE}#get(String)']}
    assert set(facts) == {'annotation:com.acme.Toto', 'annotation:Flag'}
    assert facts['annotation:Flag']['qualifiers'] == {'written_name': 'Flag', 'resolution': 'AS_WRITTEN', 'arguments': {
        'level': [{'written': 'Levels.MAX', 'resolved': False}]}}


def test_a_repeated_annotation_with_other_arguments_is_another_fact(annotated):
    values = sorted(fact['qualifiers']['arguments']['value'][0]['value'] for fact in annotated[f'{SERVICE}#tagged()'])
    assert values == ['a', 'b']


def test_a_method_with_an_ambiguous_identity_is_not_annotated(annotated):
    assert f'{SERVICE}#twice(int)' not in annotated


def test_the_annotations_are_the_same_on_every_run():
    first = RunEvaluator()(JavaCallsEvaluator(), snapshot(SOURCES))
    second = RunEvaluator()(JavaCallsEvaluator(), snapshot(SOURCES))
    def pick(execution):
        return [(fact['subject'], fact['object'], fact['qualifiers'], fact['evidence'][0]['line_start'])
                for fact in execution.facts if fact['relation'] == 'ANNOTATED_WITH']
    assert pick(first) == pick(second) and pick(first)
