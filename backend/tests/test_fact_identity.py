from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unicodedata

import pytest
import rfc8785

from app.facts import FactValidationError, fact_identity, identity_fields, validate_fact
from app.facts import contract


ROOT = contract.SCHEMA_PATH.parent / 'conformance'
VECTORS = json.loads((ROOT / 'identity/identity-vectors-v1.json').read_text(encoding='utf-8'))
REFERENCE = Path(__file__).parent / 'fixtures/jcs-reference'


def read(name='observed'):
    return json.loads((ROOT / 'v1' / f'valid-{name}.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', VECTORS['cases'], ids=lambda case: case['name'])
def test_portable_identity_vectors(case):
    original = deepcopy(case['input'])
    assert identity_fields(case['input']) == case['canonical_identity']
    assert rfc8785.dumps(identity_fields(case['input'])) == case['canonical_json'].encode('utf-8')
    assert fact_identity(case['input']) == case['expected']
    assert case['input'] == original


@pytest.mark.parametrize('case', VECTORS['negative'], ids=lambda case: case['name'])
@pytest.mark.parametrize('operation', [validate_fact, identity_fields, fact_identity])
def test_portable_negative_vectors(case, operation):
    with pytest.raises(FactValidationError) as caught:
        operation(case['input'])
    assert any(i.code == case['expected_error']['code'] and i.path == case['expected_error']['path']
               for i in caught.value.issues)


@pytest.mark.parametrize('name', ['arrays', 'french', 'structures', 'unicode', 'values', 'weird'])
def test_upstream_jcs_documents(name):
    # JCS numbers are binary64, including lexically integral values beyond 2^53.
    value = json.loads((REFERENCE / 'input' / f'{name}.json').read_text(encoding='utf-8'), parse_int=float)
    expected = bytes.fromhex((REFERENCE / 'outhex' / f'{name}.txt').read_text())
    assert rfc8785.dumps(value) == expected


@pytest.mark.parametrize('name', ['observed', 'absence', 'coverage', 'human', 'inferred-evaluator'])
@pytest.mark.parametrize('change', ['commit', 'evidence', 'execution_id', 'producer_version', 'catalog_version',
                                    'validity', 'validation', 'derivation'])
def test_occurrence_fields_do_not_affect_identity(name, change):
    fact = read(name)
    before = fact_identity(fact)
    if change == 'commit':
        fact['snapshot']['commit'] = 'b' * 40
        for evidence in fact.get('evidence', []):
            evidence['commit'] = 'b' * 40
    elif change == 'evidence':
        for evidence in fact.get('evidence', []):
            evidence.update(path='other.txt', content_hash='sha256:' + 'b' * 64, method='new-method')
    elif change == 'validity':
        fact['validity'] = 'STALE'
    elif change == 'validation':
        if 'validation' in fact:
            fact['validation']['validated_at'] = '2030-01-01T00:00:00Z'
    elif change == 'derivation':
        if 'derivation' in fact:
            fact['derivation']['premises'] = ['another-premise']
    elif change in fact['produced_by']:
        fact['produced_by'][change] = 'second'
    assert fact_identity(fact) == before


def test_status_does_not_affect_identity():
    inferred = read('inferred-evaluator')
    human = read('human')
    # PROTECTED_BY supports both INFERRED and HUMAN_VALIDATED.
    for key in ('subject', 'relation', 'object', 'qualifiers'):
        inferred[key] = deepcopy(human[key])
    assert fact_identity(inferred) == fact_identity(human)


@pytest.mark.parametrize('key,value', [('subject', 'module:other'), ('object', 'technology:Flask'),
                                      ('qualifiers', {'version': '2'})])
def test_assertion_changes_are_distinct(key, value):
    fact = read()
    before = fact_identity(fact)
    fact[key] = value
    assert fact_identity(fact) != before


def test_relation_changes_are_distinct():
    fact = read()
    fact.update(subject='symbol:java:A', object='symbol:java:B', relation='CALLS')
    before = fact_identity(fact)
    fact['relation'] = 'IMPLEMENTS'
    assert fact_identity(fact) != before


@pytest.mark.parametrize('name,key,value', [('absence', 'method', 'other'),
    ('absence', 'pattern', {'type': 'literal', 'value': 'other'}),
    ('coverage', 'coverage_type', 'ANALYSED'), ('coverage', 'subject', 'module:other')])
def test_other_identity_changes_are_distinct(name, key, value):
    fact = read(name)
    before = fact_identity(fact)
    fact[key] = value
    assert fact_identity(fact) != before


@pytest.mark.parametrize('name', ['absence', 'coverage'])
def test_scope_normalization_and_separation(name):
    fact = read(name)
    fact['scope'] = {'include': ['module:Ａ', 'module:𝒜', 'module:cafe\u0301', 'module:café'],
                     'exclude': ['file:Ａ', 'file:𝒜', 'file:𝒜']}
    expected = {'include': ['module:café', 'module:𝒜', 'module:Ａ'], 'exclude': ['file:𝒜', 'file:Ａ']}
    result = identity_fields(fact)
    assert result['scope'] == expected
    before = fact_identity(fact)
    fact['scope'] = {'include': expected['exclude'], 'exclude': expected['include']}
    assert fact_identity(fact) != before
    result['scope']['include'].append('module:detached')
    assert 'module:detached' not in fact['scope']['exclude']


@pytest.mark.parametrize('path', ['src\\main.py', '/src/a', 'C:/a', './a', '../a', 'a/../b', 'a//b', 'a/'])
def test_invalid_references_are_never_repaired(path):
    fact = read('absence')
    fact['scope']['include'] = ['file:' + path]
    with pytest.raises(FactValidationError):
        fact_identity(fact)


@pytest.mark.parametrize('reference', ['endpoint:GET /api/{orgId}', 'endpoint:get /api/{orgId}',
    'endpoint:GET /api/{id}', 'endpoint:GET /api/{orgId}/'])
def test_no_endpoint_semantic_rewriting(reference):
    fact = read()
    fact.update(subject=reference, relation='HANDLED_BY', object='symbol:java:Controller#handle')
    assert identity_fields(fact)['subject'] == reference
    assert len({fact_identity({**fact, 'subject': item}) for item in [
        'endpoint:GET /api/{orgId}', 'endpoint:get /api/{orgId}',
        'endpoint:GET /api/{id}', 'endpoint:GET /api/{orgId}/']}) == 4


def test_all_identity_strings_are_nfc_and_arrays_keep_order():
    fact = read('absence')
    fact.update(pattern={'type': 'é', 'value': 'café'}, method='méthode')
    fact['scope'] = {'include': ['file:café']}
    nfd = json.loads(unicodedata.normalize('NFD', json.dumps(fact, ensure_ascii=False)))
    assert identity_fields(fact) == identity_fields(nfd)
    fact = read()
    fact['qualifiers'] = {'é': [{'é': 'café'}, 'second']}
    nfd = json.loads(unicodedata.normalize('NFD', json.dumps(fact, ensure_ascii=False)))
    assert fact_identity(fact) == fact_identity(nfd)
    before = fact_identity(fact)
    fact['qualifiers']['é'].reverse()
    assert fact_identity(fact) != before


@pytest.mark.parametrize('value', [1, 1.0])
@pytest.mark.parametrize('zero', [0, -0.0])
def test_numeric_equivalence(value, zero):
    fact = read()
    fact['qualifiers'] = {'one': value, 'zero': zero}
    expected = next(c['expected'] for c in VECTORS['cases'] if c['name'] == 'integer-one')
    assert fact_identity(fact) == expected


def test_fact_identity_uses_only_public_identity_boundary(monkeypatch):
    marker = {'nested': {'é': 1.0}}
    sentinel = object()
    def selected(value):
        assert value is sentinel
        return marker
    monkeypatch.setattr(contract, 'identity_fields', selected)
    canonical = rfc8785.dumps(marker)
    assert fact_identity(sentinel) == 'sha256:' + hashlib.sha256(b'taxo-fact-identity/v1\n' + canonical).hexdigest()
    assert fact_identity(sentinel) != 'sha256:' + hashlib.sha256(canonical).hexdigest()


def test_identity_survives_new_process_and_hash_seed():
    code = ('import json; from pathlib import Path; from app.facts import fact_identity; '
            'fact = json.loads(Path("app/facts/infrastructure/contract/conformance/v1/valid-observed.json").read_text()); '
            'print(fact_identity(fact))')
    for seed in ['1', '7919']:
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).parents[1],
                                env={**os.environ, 'PYTHONHASHSEED': seed}, capture_output=True, text=True, check=True)
        assert result.stdout.strip() == fact_identity(read())
