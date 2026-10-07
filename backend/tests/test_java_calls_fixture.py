"""The oracle of TAXO-01K (java-calls-demo) checked against its own sources and against the fact contract.

Taxo does not judge Taxo: nothing here reads the fixture with Taxo's Java reader. Each site of the oracle is found
again in the source by its line and byte columns, and each expected fact must be a valid v1 fact, built with the
evidence, premises and diagnostics a producer will have to give.
"""
import json
from pathlib import Path

import pytest

from app.facts.contract import SCHEMA, content_hash, validate_fact

FIXTURE = Path(__file__).parent / 'fixtures' / 'java-calls-demo'
ORACLE = json.loads((FIXTURE / 'expected.json').read_text(encoding='utf-8'))
SNAPSHOT = {'repository': 'java-calls-demo', 'commit': 'a' * 40, 'mode': 'COMMIT'}
PRODUCER = {'producer_type': 'EVALUATOR', 'producer_id': 'taxo.java-calls', 'producer_version': '1.0.0',
            'execution_id': 'oracle', 'catalog_id': 'java-calls', 'catalog_version': '1'}
REASONS = set(SCHEMA['$defs']['site']['properties']['reason']['enum'])
SITE_FIELDS = ('line_start', 'line_end', 'column_start', 'column_end')
DIAGNOSTIC_FIELDS = ('method', 'receiver', 'receiver_type', 'external_supertypes', 'candidates')


def source(path):
    return (FIXTURE / path).read_bytes()


def located(site):
    return {'line_start': site['line'], 'line_end': site['line'], 'column_start': site['column_start'],
            'column_end': site['column_end']}


def proof(path, line, **extra):
    return {'repository': SNAPSHOT['repository'], 'commit': SNAPSHOT['commit'], 'path': path, 'line_start': line,
            'line_end': line, 'content_hash': content_hash(source(path), line, line), **extra}


def assertion(subject, relation, target, status='OBSERVED', evidence=(), derivation=None):
    fact = {'contract_version': 1, 'kind': 'ASSERTION', 'status': status, 'validity': 'VALID', 'subject': subject,
            'relation': relation, 'object': target, 'qualifiers': {}, 'snapshot': dict(SNAPSHOT),
            'evidence': list(evidence), 'produced_by': dict(PRODUCER)}
    if derivation:
        fact['derivation'] = derivation
    validate_fact(fact)
    return fact


def declared():
    """The declarative facts the oracle states, as (relation, subject, object)."""
    facts = set()
    for item in ORACLE['declarations']:
        facts.add(('CONTAINS', f"file:{item['file']}", item['type']))
        facts |= {('CONTAINS', item['type'], member) for member in item['members']}
    facts |= {('TYPED_AS', item['field'], item['type']) for item in ORACLE['typed_as']}
    facts |= {('EXTENDS', item['subject'], item['object']) for item in ORACLE['extends']}
    facts |= {('IMPLEMENTS', item['subject'], item['object']) for item in ORACLE['implements']
              if item['status'] == 'OBSERVED'}
    return facts


def premises(items):
    """Premises are declarative facts of the same analysis, spelled `RELATION : sujet -> objet` like the others."""
    found = declared()
    for relation, subject, target in items:
        assert (relation, subject, target) in found, f'prémisse absente des faits déclaratifs : {relation} {subject}'
    return [f'{relation} : {subject} -> {target}' for relation, subject, target in items]


def all_sites():
    for call in ORACLE['calls']:
        yield from call['sites']
    yield from ORACLE['not_interpreted']


@pytest.mark.parametrize('site', list(all_sites()), ids=lambda site: f"{Path(site['path']).name}:{site['line']}")
def test_each_site_is_found_at_its_line_and_byte_columns(site):
    line = source(site['path']).split(b'\n')[site['line'] - 1]
    assert line[site['column_start']:site['column_end']].decode('utf-8') == site['text']
    assert site['text'].endswith(')')


def test_every_java_file_is_declared_once_and_every_symbol_is_a_declaration():
    files = {path.relative_to(FIXTURE).as_posix() for path in FIXTURE.rglob('*.java')}
    assert sorted(item['file'] for item in ORACLE['declarations']) == sorted(files)
    members = {member for item in ORACLE['declarations'] for member in [item['type'], *item['members']]}
    named = {call[side] for call in ORACLE['calls'] for side in ('subject', 'object')}
    named |= {item[side] for item in ORACLE['implements'] for side in ('subject', 'object')}
    named |= {item['owner'] for item in ORACLE['not_interpreted']}
    named |= {candidate for item in ORACLE['not_interpreted'] for candidate in item.get('candidates', [])}
    assert named <= members, named - members


def test_an_edge_is_stated_once_and_keeps_every_site():
    edges = [(call['subject'], call['object']) for call in ORACLE['calls']]
    assert len(edges) == len(set(edges))
    refresh = next(call for call in ORACLE['calls'] if call['object'].endswith('CourseCatalog#refresh()'))
    assert [site['line'] for site in refresh['sites']] == [26, 27]


def test_what_must_never_be_produced_is_absent_from_the_truth():
    edges = {(call['subject'], call['object']) for call in ORACLE['calls']}
    assert not edges & {(item['subject'], item['object']) for item in ORACLE['never']['calls']}
    assert ORACLE['never']['relations'] == ['DISPATCHES_TO']
    assert {item['reason'] for item in ORACLE['not_interpreted']} <= REASONS


@pytest.mark.parametrize('call', ORACLE['calls'], ids=lambda call: call['subject'].split('#')[1] + ' → '
                         + call['object'].rsplit('.', 1)[1])
def test_each_expected_call_is_a_valid_inferred_fact_proven_by_its_sites(call):
    evidence = [proof(site['path'], site['line'], column_start=site['column_start'], column_end=site['column_end'],
                      symbol=call['subject'], method='java.call-site', role='call-site') for site in call['sites']]
    fact = assertion(call['subject'], 'CALLS', call['object'], 'INFERRED', evidence, {
        'premises': premises(call['premises']), 'rule': call['rule'], 'counter_examples_checked': [],
        'known_gaps': ['applicabilité des arguments non vérifiée ; suppose un code qui compile']})
    assert len(fact['evidence']) == len(call['sites'])


@pytest.mark.parametrize('item', ORACLE['implements'], ids=lambda item: item['subject'].rsplit('.', 1)[1])
def test_each_expected_implementation_is_a_valid_fact(item):
    if item['status'] == 'OBSERVED':
        assertion(item['subject'], 'IMPLEMENTS', item['object'],
                  evidence=[proof(item['path'], item['line'], method='java.implements-clause')])
    else:
        assertion(item['subject'], 'IMPLEMENTS', item['object'], 'INFERRED', derivation={
            'premises': premises(item['premises']), 'rule': item['rule'], 'counter_examples_checked': [],
            'known_gaps': []})


def test_each_declared_field_type_is_a_valid_fact():
    for item in ORACLE['typed_as']:
        assertion(item['field'], 'TYPED_AS', item['type'], evidence=[proof(item['path'], item['line'],
                                                                          method='java.field-type')])
    declared_types = {item['type'] for item in ORACLE['declarations']}
    assert {item['type'] for item in ORACLE['typed_as']} <= declared_types, 'aucun type externe inventé'


def test_uninterpreted_sites_are_one_valid_coverage_per_owner():
    owners = {}
    for item in ORACLE['not_interpreted']:
        owners.setdefault((item['owner'], item['path']), []).append(item)
    for (owner, path), sites in owners.items():
        diagnostic = {'sites_seen': len(sites), 'sites': [
            {'role': 'call-site', **located(site), 'reason': site['reason'],
             **{key: site[key] for key in DIAGNOSTIC_FIELDS if key in site}} for site in sites]}
        validate_fact({'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                       'subject': owner, 'coverage_type': 'NOT_INTERPRETED', 'scope': {'include': [f'file:{path}']},
                       'reason': 'appels non résolus', 'diagnostic': diagnostic, 'snapshot': dict(SNAPSHOT),
                       'produced_by': dict(PRODUCER)})
    assert len(owners) == len({owner for owner, _ in owners}), 'un propriétaire, un fichier : une seule identité'


def test_the_route_reaches_the_calls_of_its_handler():
    route = ORACLE['route']
    targets = [call['object'] for call in ORACLE['calls'] if call['subject'] == route['handled_by']]
    assert targets == route['then']
