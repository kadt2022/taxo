"""TAXO-01K : l'evaluateur des appels Java compare a la verite ecrite a la main (tests/fixtures/java-calls-demo).

Le producteur doit retrouver exactement l'oracle : ni un appel de plus, ni un de moins, chaque site a son octet,
chaque site non interprete avec sa raison fermee. Une seule execution sert tous les tests du module.
"""
import json
from pathlib import Path

import pytest

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.java_calls.evaluator import JavaCallsEvaluator
from app.evaluators.spring_api.evaluator import SpringApiEvaluator
from app.facts.contract import validate_fact
from java_sources import snapshot

FIXTURE = Path(__file__).parent / 'fixtures' / 'java-calls-demo'
ORACLE = json.loads((FIXTURE / 'expected.json').read_text(encoding='utf-8'))
DIAGNOSTIC_FIELDS = ('method', 'receiver', 'receiver_type', 'external_supertypes', 'candidates')


def fixture_files():
    return {path.relative_to(FIXTURE).as_posix(): path.read_bytes()
            for path in sorted(FIXTURE.rglob('*')) if path.is_file()}


@pytest.fixture(scope='module', name='execution')
def execution_fixture():
    return RunEvaluator()(JavaCallsEvaluator(), snapshot(fixture_files()))


def of(execution, relation):
    return [fact for fact in execution.facts if fact['relation'] == relation]


def premise(relation, subject, target):
    return f'{relation} : {subject} -> {target}'


def test_the_fixture_is_read_entirely(execution):
    assert execution.status is EvaluationStatus.SUCCESS and execution.warnings == ()
    assert {fact['subject'] for fact in execution.coverage if fact['coverage_type'] == 'ANALYSED'} >= {
        'repository:depot', *(f"file:{item['file']}" for item in ORACLE['declarations'])}
    assert all(validate_fact(fact) is None for fact in execution.facts + execution.coverage)


def test_the_declarations_are_exactly_those_of_the_oracle(execution):
    expected = {('CONTAINS', f"file:{item['file']}", item['type']) for item in ORACLE['declarations']}
    expected |= {('CONTAINS', item['type'], member) for item in ORACLE['declarations'] for member in item['members']}
    expected |= {('TYPED_AS', item['field'], item['type']) for item in ORACLE['typed_as']}
    expected |= {('EXTENDS', item['subject'], item['object']) for item in ORACLE['extends']}
    expected |= {('IMPLEMENTS', item['subject'], item['object']) for item in ORACLE['implements']
                 if item['status'] == 'OBSERVED'}
    found = {(fact['relation'], fact['subject'], fact['object']) for fact in execution.facts
             if fact['status'] == 'OBSERVED'}
    assert found == expected
    assert {fact['relation'] for fact in execution.facts if fact['status'] == 'INFERRED'} == {'CALLS', 'IMPLEMENTS'}


def test_a_declared_field_type_is_proven_by_its_line(execution):
    lines = {(item['field'], item['type']): (item['path'], item['line']) for item in ORACLE['typed_as']}
    for fact in of(execution, 'TYPED_AS'):
        [evidence] = fact['evidence']
        assert (evidence['path'], evidence['line_start']) == lines[fact['subject'], fact['object']]
        assert evidence['symbol'] == fact['subject'] and evidence['method'] == 'java.declaration'


def test_the_calls_are_exactly_those_of_the_oracle_with_every_site(execution):
    expected = {(item['subject'], item['object']): item for item in ORACLE['calls']}
    found = {(fact['subject'], fact['object']): fact for fact in of(execution, 'CALLS')}
    assert found.keys() == expected.keys()
    for key, fact in found.items():
        oracle = expected[key]
        assert fact['status'] == 'INFERRED' and fact['derivation']['rule'] == oracle['rule']
        assert fact['derivation']['premises'] == [premise(*item) for item in oracle['premises']]
        sites = [(item['path'], item['line_start'], item['column_start'], item['column_end'], item['role'])
                 for item in fact['evidence']]
        assert sites == [(site['path'], site['line'], site['column_start'], site['column_end'], 'call-site')
                         for site in oracle['sites']]
        assert all(item['symbol'] == fact['subject'] for item in fact['evidence'])


def test_the_method_implementations_are_exactly_those_of_the_oracle(execution):
    expected = {(item['subject'], item['object']): item for item in ORACLE['implements'] if item['status'] == 'INFERRED'}
    found = {(fact['subject'], fact['object']): fact for fact in of(execution, 'IMPLEMENTS')
             if fact['status'] == 'INFERRED'}
    assert found.keys() == expected.keys()
    for key, fact in found.items():
        assert fact['derivation']['rule'] == expected[key]['rule']
        assert fact['derivation']['premises'] == [premise(*item) for item in expected[key]['premises']]
        [evidence] = fact['evidence']
        assert (evidence['symbol'], evidence['method']) == (fact['subject'], 'java.declaration')


def test_each_uninterpreted_site_has_its_closed_reason_under_its_owner(execution):
    expected = {}
    for site in ORACLE['not_interpreted']:
        expected.setdefault(site['owner'], []).append(
            {'role': 'call-site', 'line_start': site['line'], 'line_end': site['line'],
             'column_start': site['column_start'], 'column_end': site['column_end'], 'reason': site['reason'],
             'category': site['category'], **{key: site[key] for key in DIAGNOSTIC_FIELDS if key in site}})
    found = {fact['subject']: fact for fact in execution.coverage if fact['coverage_type'] == 'NOT_INTERPRETED'}
    assert found.keys() == expected.keys()
    for owner, fact in found.items():
        assert fact['diagnostic'] == {'sites_seen': len(expected[owner]),
                                      'classification': 'java.calls.frontier-classification/1',
                                      'sites': expected[owner]}
        assert all(site['reason'] in fact['reason'] for site in expected[owner])


def test_what_must_never_be_produced_is_absent(execution):
    relations = {fact['relation'] for fact in execution.facts}
    assert not relations & set(ORACLE['never']['relations'])
    found = {(fact['subject'], fact['object']) for fact in of(execution, 'CALLS')}
    assert not found & {(item['subject'], item['object']) for item in ORACLE['never']['calls']}


def test_the_counts_say_what_was_read(execution):
    resolved = sum(len(item['sites']) for item in ORACLE['calls'])
    unread = len(ORACLE['not_interpreted'])
    assert execution.legacy['resolved_sites'] == resolved
    assert execution.legacy['call_sites'] == resolved + unread
    assert sum(execution.legacy['not_interpreted'].values()) == unread


def test_two_runs_give_the_same_facts():
    first, second = (JavaCallsEvaluator().evaluate(snapshot(fixture_files())) for _ in range(2))
    assert first.facts == second.facts and first.coverage == second.coverage


def test_the_route_handler_is_the_subject_of_its_calls(execution):
    """La route de Spring et les appels Java se rejoignent par la meme identite de symbole, sans lien specifique."""
    route = ORACLE['route']
    handled = RunEvaluator()(SpringApiEvaluator(), snapshot(fixture_files()))
    assert (route['endpoint'], route['handled_by']) in {
        (fact['subject'], fact['object']) for fact in handled.facts if fact['relation'] == 'HANDLED_BY'}
    reached = [fact['object'] for fact in of(execution, 'CALLS') if fact['subject'] == route['handled_by']]
    assert sorted(reached) == sorted(route['then'])


def test_a_repository_without_java_gives_no_fact():
    """Le moteur ne l'appelle pas sur un depot sans Java (`OUT_OF_SCOPE`, test_protocol) ; appele, il ne dit rien."""
    output = JavaCallsEvaluator().evaluate(snapshot({'README.md': '# rien\n'}))
    assert output.facts == () and output.status is EvaluationStatus.SUCCESS
    assert [fact['coverage_type'] for fact in output.coverage] == ['ANALYSED']
