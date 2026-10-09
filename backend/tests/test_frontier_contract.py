"""TAXO-01M, PR A : le contrat générique des frontières.

Quatre catégories fermées dans le contrat commun ; des codes de diagnostic ouverts, que chaque producteur déclare
dans son catalogue ; une identité de site locale à son diagnostic. Le producteur « Python » de ce module est
synthétique : il prouve que le contrat ne dépend pas d'un langage, pas que Taxo sait analyser du Python.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.evaluator import EvaluationOutput, EvaluatorCatalog
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.java_calls import resolution
from app.evaluators.java_calls.catalog import CATALOG as JAVA_CALLS
from app.evaluators.java_calls.evaluator import JavaCallsEvaluator
from app.facts import identity_fields, validate_fact
from app.facts.contract import SCHEMA, SCHEMA_PATH
from app.facts.domain.diagnostic import CATEGORIES, site_keys
from app.snapshots.domain.mode import COMMIT
from app.snapshots.domain.snapshot import Snapshot

CONFORMANCE = SCHEMA_PATH.parent / 'conformance' / 'v1'
FIXTURE = Path(__file__).parent / 'fixtures' / 'java-calls-demo'
PYTHON_RULE = 'python.synthetic.frontier-classification/1'


def case(name):
    return json.loads((CONFORMANCE / f'{name}.json').read_text(encoding='utf-8'))


def site(line, start, end, reason='NAME_UNBOUND', **extra):
    return {'role': 'call-site', 'line_start': line, 'line_end': line, 'column_start': start, 'column_end': end,
            'reason': reason, **extra}


def snapshot():
    class EmptyContent:
        def read_many(self, paths):
            yield from ()
    return Snapshot('project-key', 'a' * 40, COMMIT, (), content=EmptyContent())


class SyntheticPythonEvaluator:
    """Un producteur d'un autre langage, réduit à ce que le contrat voit : ses codes, ses catégories."""
    evaluator_id = 'test.synthetic-python'
    producer_version = '0.0.1'
    catalog = EvaluatorCatalog('synthetic-python', '1', (), ('ANALYSED', 'NOT_INTERPRETED'), ('Python',),
                               diagnostic_codes=('DYNAMIC_ATTRIBUTE', 'NAME_UNBOUND'))

    def __init__(self, sites):
        self.sites = sites

    def evaluate(self, snapshot):
        repository = f'repository:{snapshot.repository}'
        analysed = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                    'subject': repository, 'coverage_type': 'ANALYSED', 'scope': {'include': [repository]}}
        unread = {'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                  'subject': 'symbol:python:app.service.OrderService.place', 'coverage_type': 'NOT_INTERPRETED',
                  'scope': {'include': ['file:app/service.py']},
                  'diagnostic': {'sites_seen': len(self.sites), 'classification': PYTHON_RULE, 'sites': self.sites}}
        return EvaluationOutput(coverage=(analysed, unread))


class MisdeclaredJavaEvaluator:
    """`taxo.java-calls` qui écrirait un code que son catalogue ne déclare pas."""
    evaluator_id = 'taxo.java-calls'
    producer_version = '1.0.0'
    catalog = JAVA_CALLS

    def evaluate(self, snapshot):
        fact = case('valid-coverage-diagnostic')
        fact['diagnostic']['sites'][0]['reason'] = 'MAY_CALL'
        del fact['snapshot'], fact['produced_by']
        return EvaluationOutput(coverage=(fact,))


def test_the_four_categories_are_those_of_the_common_contract():
    assert SCHEMA['$defs']['site']['properties']['category']['enum'] == list(CATEGORIES)
    assert CATEGORIES == ('UNKNOWN', 'AMBIGUOUS', 'UNSUPPORTED', 'OUT_OF_SCOPE')


def test_the_common_contract_names_no_language_code():
    assert 'enum' not in SCHEMA['$defs']['site']['properties']['reason']
    assert 'TARGET_TYPE_OUTSIDE_SNAPSHOT' not in json.dumps(SCHEMA)


def test_the_java_catalog_declares_exactly_the_codes_its_resolution_writes():
    written = {value for name, value in vars(resolution).items() if name.isupper() and value == name}
    assert set(JAVA_CALLS.diagnostic_codes) == written
    assert len(JAVA_CALLS.diagnostic_codes) == 11


def test_the_real_java_producer_writes_only_declared_codes():
    from java_sources import snapshot as java_snapshot
    files = {path.relative_to(FIXTURE).as_posix(): path.read_bytes()
             for path in sorted(FIXTURE.rglob('*')) if path.is_file()}
    execution = RunEvaluator()(JavaCallsEvaluator(), java_snapshot(files))
    assert execution.status is EvaluationStatus.SUCCESS
    written = {item['reason'] for fact in execution.coverage for item in (fact.get('diagnostic') or {}).get('sites', [])}
    assert written and written <= set(JAVA_CALLS.diagnostic_codes)


def test_a_code_the_catalog_does_not_declare_fails_the_execution_and_names_it():
    execution = RunEvaluator()(MisdeclaredJavaEvaluator(), snapshot())
    assert execution.status is EvaluationStatus.FAILED
    assert any('MAY_CALL' in warning and 'java-calls' in warning and 'taxo.java-calls' in warning
               for warning in execution.warnings)
    assert all(fact['coverage_type'] != 'NOT_INTERPRETED' or 'diagnostic' not in fact for fact in execution.coverage)


def test_a_synthetic_python_producer_needs_no_change_to_the_common_contract():
    sites = [site(12, 4, 22, 'NAME_UNBOUND', category='UNKNOWN'),
             site(12, 26, 40, 'DYNAMIC_ATTRIBUTE', category='UNSUPPORTED')]
    execution = RunEvaluator()(SyntheticPythonEvaluator(sites), snapshot())
    assert execution.status is EvaluationStatus.SUCCESS
    unread = next(fact for fact in execution.coverage if fact['coverage_type'] == 'NOT_INTERPRETED')
    assert [item['category'] for item in unread['diagnostic']['sites']] == ['UNKNOWN', 'UNSUPPORTED']
    assert unread['diagnostic']['classification'] == PYTHON_RULE


def test_a_synthetic_python_code_left_undeclared_is_refused():
    execution = RunEvaluator()(SyntheticPythonEvaluator([site(3, 0, 5, 'LATE_BINDING', category='UNKNOWN')]),
                               snapshot())
    assert execution.status is EvaluationStatus.FAILED
    assert any('LATE_BINDING' in warning for warning in execution.warnings)


def test_a_catalog_lists_its_codes_sorted_and_once():
    with pytest.raises(ValueError):
        EvaluatorCatalog('x', '1', diagnostic_codes=('B_CODE', 'A_CODE'))
    with pytest.raises(ValueError):
        EvaluatorCatalog('x', '1', diagnostic_codes=('A_CODE', 'A_CODE'))


def test_an_analysis_written_before_the_categories_stays_valid_and_unclassified():
    fact = case('valid-coverage-diagnostic')
    assert validate_fact(fact) is None
    assert 'classification' not in fact['diagnostic']
    assert all('category' not in item for item in fact['diagnostic']['sites'])


def test_a_coverage_without_diagnostic_carries_no_category():
    fact = case('valid-coverage-diagnostic')
    del fact['diagnostic']
    assert validate_fact(fact) is None


def test_classifying_a_diagnostic_never_changes_the_identity_of_its_coverage():
    assert identity_fields(case('valid-coverage-diagnostic')) == \
        identity_fields(case('valid-coverage-diagnostic-classified'))


def test_two_sites_on_one_line_have_two_keys():
    fact = case('valid-coverage-diagnostic-producer-code')
    first, second = site_keys(fact)
    assert first != second
    assert first[2] == second[2] == 12


def test_two_identical_findings_keep_their_own_rank_and_are_never_merged():
    fact = case('valid-coverage-diagnostic-producer-code')
    fact['diagnostic']['sites'] = [site(12, 4, 22, category='UNKNOWN'), site(12, 4, 22, category='UNKNOWN')]
    fact['diagnostic']['sites_seen'] = 2
    keys = site_keys(fact)
    assert [key[-1] for key in keys] == [0, 1]
    assert len(set(keys)) == 2


def test_a_site_key_is_deterministic_and_local_to_its_coverage():
    fact = case('valid-coverage-diagnostic-producer-code')
    assert site_keys(fact) == site_keys(deepcopy(fact))
    other = deepcopy(fact)
    other['subject'] = 'symbol:python:app.service.OrderService.cancel'
    assert set(site_keys(fact)).isdisjoint(site_keys(other))


def test_a_coverage_without_diagnostic_has_no_site_key():
    fact = case('valid-coverage-diagnostic')
    del fact['diagnostic']
    assert site_keys(fact) == []
