"""TAXO-01M, PR B : la categorie generique de chaque site Java non interprete.

La table attendue est ecrite ici a la main, pas relue dans le producteur : elle est la regle
`java.calls.frontier-classification/1` telle que le recit l'a validee.
"""
from pathlib import Path

import pytest

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.java_calls import classification
from app.evaluators.java_calls.catalog import CATALOG
from app.evaluators.java_calls.evaluator import JavaCallsEvaluator
from app.evaluators.java_calls.facts import site_order
from app.facts.domain.diagnostic import site_keys
from java_sources import snapshot

FIXTURE = Path(__file__).parent / 'fixtures' / 'java-calls-demo'
RULE = 'java.calls.frontier-classification/1'
EXPECTED = {
    'RECEIVER_TYPE_UNKNOWN': 'UNKNOWN',
    'RECEIVER_TYPE_AMBIGUOUS': 'AMBIGUOUS',
    'OVERLOAD_AMBIGUOUS': 'AMBIGUOUS',
    'NO_MATCHING_DECLARATION': 'UNKNOWN',
    'TARGET_DECLARATION_OUTSIDE_SNAPSHOT': 'UNKNOWN',
    'TARGET_TYPE_OUTSIDE_SNAPSHOT': 'UNKNOWN',
    'SUPER_TYPE_UNRESOLVED': 'UNKNOWN',
    'UNSUPPORTED_CALL_FORM': 'UNSUPPORTED',
    'RECEIVER_KIND_DEFERRED': 'UNSUPPORTED',
    'LAMBDA_OR_LOCAL_CONTEXT': 'UNSUPPORTED',
    'PARSE_ERROR': 'UNKNOWN',
}


def fixture_files():
    return {path.relative_to(FIXTURE).as_posix(): path.read_bytes()
            for path in sorted(FIXTURE.rglob('*')) if path.is_file()}


def run(files):
    execution = RunEvaluator()(JavaCallsEvaluator(), snapshot(files))
    assert execution.status is EvaluationStatus.SUCCESS
    return execution


@pytest.fixture(scope='module', name='execution')
def execution_fixture():
    return run(fixture_files())


def unread(execution):
    return [fact for fact in execution.coverage if fact['coverage_type'] == 'NOT_INTERPRETED']


def written(facts):
    """Ce qu'une execution ecrit, sans son identifiant d'execution."""
    return [{key: value for key, value in fact.items() if key != 'produced_by'} for fact in facts]


@pytest.mark.parametrize('code', sorted(EXPECTED))
def test_each_code_has_its_category(code):
    assert classification.category(code) == EXPECTED[code]


def test_the_rule_classifies_exactly_the_codes_of_the_catalog():
    assert classification.codes() == CATALOG.diagnostic_codes == tuple(sorted(EXPECTED))
    assert classification.RULE == RULE


def test_version_1_never_writes_out_of_scope():
    assert 'OUT_OF_SCOPE' not in {classification.category(code) for code in classification.codes()}


def test_a_code_without_category_is_refused_never_guessed():
    with pytest.raises(ValueError, match='MAY_CALL'):
        classification.category('MAY_CALL')


def test_the_producer_version_says_the_diagnostic_changed():
    assert JavaCallsEvaluator.producer_version == '1.2.0'
    assert CATALOG.catalog_version == '1'


def test_every_listed_site_is_classified_by_the_named_rule(execution):
    for fact in unread(execution):
        assert fact['diagnostic']['classification'] == RULE
        assert all(item['category'] == EXPECTED[item['reason']] for item in fact['diagnostic']['sites'])


def test_an_ambiguous_site_never_becomes_a_call(execution):
    calls = {(fact['subject'], fact['object']) for fact in execution.facts if fact['relation'] == 'CALLS'}
    ambiguous = [(fact['subject'], item) for fact in unread(execution) for item in fact['diagnostic']['sites']
                 if item['category'] == 'AMBIGUOUS']
    assert ambiguous, 'la fixture doit porter au moins un site ambigu'
    for owner, item in ambiguous:
        assert item.get('candidates'), 'un site ambigu nomme ses candidats'
        assert not {(owner, candidate) for candidate in item['candidates']} & calls


def test_sites_are_listed_by_position_and_two_sites_of_one_line_by_column(execution):
    same_line = 0
    for fact in unread(execution):
        listed = fact['diagnostic']['sites']
        assert listed == sorted(listed, key=site_order)
        lines = [item['line_start'] for item in listed]
        same_line += len(lines) - len(set(lines))
        keys = site_keys(fact)
        assert len(set(keys)) == len(keys)
    assert same_line, 'la fixture doit porter deux sites sur une même ligne'


def test_site_order_breaks_ties_by_end_then_code():
    def at(start, end, reason):
        return {'line_start': 4, 'line_end': 4, 'column_start': start, 'column_end': end, 'reason': reason}
    given = [at(8, 30, 'UNSUPPORTED_CALL_FORM'), at(8, 20, 'RECEIVER_KIND_DEFERRED'), at(2, 40, 'PARSE_ERROR'),
             at(8, 20, 'OVERLOAD_AMBIGUOUS')]
    assert sorted(given, key=site_order) == [given[2], given[3], given[1], given[0]]


def test_two_runs_write_the_same_diagnostics_and_the_same_facts(execution):
    again = run(fixture_files())
    assert written(unread(again)) == written(unread(execution))
    assert written(again.facts) == written(execution.facts)


def test_classifying_adds_no_fact_and_no_coverage(execution):
    assert {fact['relation'] for fact in execution.facts} <= set(CATALOG.relations)
    owners = {fact['subject'] for fact in unread(execution)}
    assert len(owners) == len(unread(execution))
    assert sum(len(fact['diagnostic']['sites']) for fact in unread(execution)) == \
        sum(execution.legacy['not_interpreted'].values())
