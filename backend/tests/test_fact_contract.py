from copy import deepcopy
import hashlib
import json

from jsonschema import Draft202012Validator
import pytest

from app.facts import FactValidationError, content_hash, identity_fields, validate_fact
from app.facts.__main__ import main
from app.facts.contract import RELATIONS, SCHEMA, SCHEMA_PATH


ROOT = SCHEMA_PATH.parent / 'conformance' / 'v1'
CASES = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))['cases']


def read(name):
    return json.loads((ROOT / (name + '.json')).read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['file'])
def test_conformance(case):
    fact = json.loads((ROOT / case['file']).read_text(encoding='utf-8'))
    original = deepcopy(fact)
    if case['accepted']:
        assert validate_fact(fact, submission=case['submission']) is None
    else:
        with pytest.raises(FactValidationError) as caught:
            validate_fact(fact, submission=case['submission'])
        assert any(i.code == case['expected_error']['code'] and i.path == case['expected_error']['path']
                   for i in caught.value.issues), caught.value.issues
        assert all(i.message for i in caught.value.issues)
    assert fact == original


def test_suite_covers_all_t16_groups_and_all_files():
    assert {c['t16'] for c in CASES if 't16' in c} == set(range(1, 19))
    assert {c['file'] for c in CASES} == {p.name for p in ROOT.glob('*.json') if p.name not in ('manifest.json', 'hash-vectors.json')}
    assert len(CASES) == len({c['file'] for c in CASES})


def test_schema_and_vocabulary():
    Draft202012Validator.check_schema(SCHEMA)
    assert set(RELATIONS) == set(SCHEMA['properties']['relation']['enum'])


@pytest.mark.parametrize('case', json.loads((ROOT / 'hash-vectors.json').read_text(encoding='utf-8')), ids=lambda c: c['name'])
def test_portable_hash_vectors(case):
    assert content_hash(case['source_utf8'].encode('utf-8'), case.get('line_start'), case.get('line_end')) == case['expected']


@pytest.mark.parametrize('name,pointer', [
    ('observed', ('snapshot',)), ('observed', ('produced_by',)),
    ('observed', ('evidence', 0)), ('absence', ('scope',)), ('absence', ('pattern',)),
    ('inferred-evaluator', ('derivation',)), ('human', ('validation',)),
    ('human', ('validation', 'anchors', 0)),
])
def test_unknown_fields_are_refused_in_every_structure(name, pointer):
    fact = read('valid-' + name)
    target = fact
    for component in pointer:
        target = target[component]
    target['unexpected'] = 'not part of contract'
    with pytest.raises(FactValidationError, match='Unknown fields'):
        validate_fact(fact)


@pytest.mark.parametrize('coverage_type', ['ANALYSED', 'RECOGNIZED', 'NOT_INTERPRETED', 'OUT_OF_SCOPE', 'READ_ERROR'])
def test_all_coverage_types(coverage_type):
    fact = read('valid-coverage')
    fact['coverage_type'] = coverage_type
    validate_fact(fact)


@pytest.mark.parametrize('version', [True, '1', 2])
def test_contract_version_is_explicit(version):
    fact = read('valid-observed')
    fact['contract_version'] = version
    with pytest.raises(FactValidationError):
        validate_fact(fact)


def test_permits_all_forbids_object_and_inference_relations_forbid_observation():
    fact = read('valid-permits-all')
    fact['object'] = 'symbol:java:X'
    with pytest.raises(FactValidationError, match='no object'):
        validate_fact(fact)
    fact = read('valid-inferred-evaluator')
    fact['status'] = 'OBSERVED'
    fact.pop('derivation')
    fact['evidence'] = read('valid-observed')['evidence']
    with pytest.raises(FactValidationError, match='Status is not permitted'):
        validate_fact(fact)


@pytest.mark.parametrize('relation', RELATIONS)
def test_every_relation_has_valid_typed_example(relation):
    sources, targets, statuses = RELATIONS[relation]
    fact = read('valid-inferred-evaluator' if 'INFERRED' in statuses else 'valid-observed')
    fact.update(relation=relation, subject=sorted(sources)[0] + ':example')
    if targets:
        fact['object'] = sorted(targets)[0] + ':example'
    else:
        fact.pop('object')
    validate_fact(fact)
    fact['subject'] = 'role:R_ADMIN'
    with pytest.raises(FactValidationError, match='Subject type'):
        validate_fact(fact)


@pytest.mark.parametrize('value,accepted', [
    ('symbol:java:com.example.SecurityConfig', True),
    ("hasRole('ADMIN')", True),
    ("hasAuthority('SCOPE_read') and isAuthenticated()", True),
    ('role:R_ADMIN', False),
    ('file:SecurityConfig.java', False),
    ('policy-rule:POL_X', False),
    ('unknown-type:value', False),
])
def test_authorized_by_separates_references_from_literal_expressions(value, accepted):
    fact = read('valid-authorization-expression')
    fact['object'] = value
    if accepted:
        assert validate_fact(fact) is None
        return
    with pytest.raises(FactValidationError) as caught:
        validate_fact(fact)
    assert any(i.code == 'RELATION_OBJECT' and i.path == '/object' for i in caught.value.issues)


@pytest.mark.parametrize('kind', ['observed', 'absence', 'coverage'])
def test_identity_excludes_occurrence_and_is_detached(kind):
    fact = read('valid-' + kind)
    before = identity_fields(fact)
    fact['snapshot']['commit'] = 'b' * 40
    for evidence in fact.get('evidence', []):
        evidence['commit'] = 'b' * 40
    fact['produced_by'].update(producer_version='2', execution_id='second', catalog_version='2')
    assert identity_fields(fact) == before
    if kind == 'observed':
        fact['qualifiers']['version'] = '2'
    else:
        fact['scope']['include'].append('module:new')
    assert identity_fields(fact) != before


def test_coverage_identity_contains_producer():
    fact = read('valid-coverage')
    before = identity_fields(fact)
    fact['produced_by']['producer_id'] = 'another-evaluator'
    assert identity_fields(fact) != before
    assert before['producer_id'] == 'inventory'


@pytest.mark.parametrize('source,expected', [
    (b'a\nb\n', b'a\nb'), (b'a\r\nb\r\n', b'a\nb'), (b'a\rb\n', b'ab'),
    (b'', b''), (b'\n', b''), (b'a\n\n', b'a\n'), (b'a\nb', b'a\nb'),
    ('caf\u00e9\n'.encode(), 'caf\u00e9'.encode()),
])
def test_hash_normalization(source, expected):
    assert content_hash(source) == 'sha256:' + hashlib.sha256(expected).hexdigest()


def test_hash_selects_inclusive_lines():
    expected = 'sha256:' + hashlib.sha256(b'alpha\nbeta').hexdigest()
    assert content_hash(b'header\nalpha\nbeta\nfooter\n', 2, 3) == expected
    assert content_hash(b'header\r\nalpha\r\nbeta\r\nfooter\r\n', 2, 3) == expected
    assert content_hash(b'a\n', 1, 1) == 'sha256:' + hashlib.sha256(b'a').hexdigest()


@pytest.mark.parametrize('start,end', [(0, 1), (2, 1), (1, 3), (1, None), (None, 1), (True, 1), (1.0, 1)])
def test_hash_rejects_invalid_bounds(start, end):
    with pytest.raises(ValueError):
        content_hash(b'a\nb\n', start, end)


def test_hash_rejects_non_utf8_and_empty_line_range():
    with pytest.raises(UnicodeDecodeError):
        content_hash(b'\xff')
    with pytest.raises(ValueError):
        content_hash(b'', 1, 1)


@pytest.mark.parametrize('field,value', [('line_start', 0), ('line_start', True), ('line_start', 2), ('line_end', 0)])
def test_evidence_line_boundaries(field, value):
    fact = read('valid-observed')
    fact['evidence'][0].update(line_start=1, line_end=1)
    fact['evidence'][0][field] = value
    with pytest.raises(FactValidationError):
        validate_fact(fact)


@pytest.mark.parametrize('path', ['/root/a', '../a', 'src/../a', './a', 'a/', 'a//b', 'C:/a', 'a\\b', 'a\n'])
def test_invalid_evidence_paths(path):
    fact = read('valid-observed')
    fact['evidence'][0]['path'] = path
    with pytest.raises(FactValidationError):
        validate_fact(fact)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), (1, 2), {1: 'x'}])
def test_python_values_must_be_json(value):
    fact = read('valid-observed')
    fact['qualifiers']['value'] = value
    with pytest.raises(FactValidationError, match='finite JSON'):
        validate_fact(fact)


def test_nested_confidence_is_refused_but_annotation_values_are_supported():
    fact = read('valid-observed')
    fact['qualifiers'] = {'annotation_values': {'paths': ['/api'], 'enabled': True, 'count': 2}}
    validate_fact(fact)
    fact['qualifiers']['annotation_values']['ConfidenceScore'] = 0.9
    with pytest.raises(FactValidationError):
        validate_fact(fact)


def test_cli_accepts_rejects_and_replays_suite(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    assert main(['--fact', 'valid-observed.json']) == 0
    assert json.loads(capsys.readouterr().out)['valid'] is True
    assert main(['--fact', str(ROOT / 't16-01-missing-evidence.json')]) == 1
    assert json.loads(capsys.readouterr().out)['errors']
    assert main(['--conformance']) == 0
    assert json.loads(capsys.readouterr().out)['failed'] == []


@pytest.mark.parametrize('document', ['{bad', '{"kind":"ASSERTION","kind":"ABSENCE"}', 'NaN'])
def test_cli_rejects_ambiguous_or_malformed_json(tmp_path, monkeypatch, capsys, document):
    (tmp_path / 'fact.json').write_text(document, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    assert main(['--fact', 'fact.json']) == 1
    assert json.loads(capsys.readouterr().out)['valid'] is False


@pytest.mark.parametrize('argument', ['../outside.json', '{outside}', 'fact.txt', 'missing-dir/../../outside.json'])
def test_cli_confines_fact_path_to_working_directory(tmp_path, monkeypatch, capsys, argument):
    work = tmp_path / 'work'
    work.mkdir()
    valid = (ROOT / 'valid-observed.json').read_text(encoding='utf-8')
    for target in (work / 'fact.json', work / 'fact.txt', tmp_path / 'outside.json'):
        target.write_text(valid, encoding='utf-8')
    monkeypatch.chdir(work)
    assert main(['--fact', 'fact.json']) == 0
    capsys.readouterr()
    assert main(['--fact', argument.format(outside=tmp_path / 'outside.json')]) == 1
    assert json.loads(capsys.readouterr().out)['valid'] is False


def test_errors_do_not_echo_source_values():
    fact = read('valid-observed')
    fact['evidence'][0]['source'] = 'secret-source-marker'
    with pytest.raises(FactValidationError) as caught:
        validate_fact(fact)
    assert 'secret-source-marker' not in str(caught.value)
