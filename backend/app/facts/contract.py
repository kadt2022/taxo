"""Structural and semantic validation of individual fact occurrences (ADR 0002)."""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

from jsonschema import Draft202012Validator, FormatChecker
import rfc8785


SCHEMA_PATH = Path(__file__).with_name('contract-v1.schema.json')
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
_VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
# Reserved type:key syntax of entity references; never read as a literal expression.
_REFERENCE_SYNTAX = re.compile(r'[a-z][a-z0-9-]*:')

# Source/target types and permitted statuses are the v1 relation vocabulary.
RELATIONS = {
    'CONTAINS': ({'repository', 'module'}, {'module', 'file'}, {'OBSERVED'}),
    'WRITTEN_IN': ({'file'}, {'language'}, {'OBSERVED'}),
    'USES_TECHNOLOGY': ({'repository', 'module'}, {'technology'}, {'OBSERVED'}),
    'DECLARED_BY': ({'technology'}, {'file'}, {'OBSERVED'}),
    'ANNOTATED_WITH': ({'symbol'}, {'annotation'}, {'OBSERVED'}),
    'CALLS': ({'symbol'}, {'symbol'}, {'OBSERVED'}),
    'IMPLEMENTS': ({'symbol'}, {'symbol'}, {'OBSERVED'}),
    'DISPATCHES_TO': ({'symbol'}, {'symbol'}, {'INFERRED'}),
    'HANDLED_BY': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'ACCEPTS': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'RETURNS': ({'endpoint'}, {'symbol'}, {'OBSERVED'}),
    'PERMITS_ALL': ({'route-pattern'}, set(), {'OBSERVED'}),
    'AUTHORIZED_BY': ({'route-pattern'}, {'symbol'}, {'OBSERVED'}),
    'MATCHED_BY': ({'endpoint'}, {'route-pattern'}, {'INFERRED'}),
    'PROTECTED_BY': ({'endpoint'}, {'symbol', 'policy-rule'}, {'INFERRED', 'HUMAN_VALIDATED'}),
}
_STATUS_PRODUCERS = {
    'OBSERVED': {'EVALUATOR'},
    'INFERRED': {'EVALUATOR', 'PROJECTION'},
    'HUMAN_VALIDATED': {'HUMAN'},
}
_IDENTITY_FIELDS = {
    'ASSERTION': ('kind', 'subject', 'relation', 'object', 'qualifiers'),
    'ABSENCE': ('kind', 'pattern', 'scope', 'method'),
    'COVERAGE': ('kind', 'subject', 'coverage_type', 'scope'),
}
_IDENTITY_DOMAIN = b'taxo-fact-identity/v1\n'
_MAX_SAFE_INTEGER = 2**53 - 1


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


class FactValidationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__('; '.join(f'{i.path}: {i.message}' for i in self.issues))


def _pointer(parts):
    return '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in parts)


def _schema_message(error):
    if error.validator == 'required':
        missing = [key for key in error.validator_value if key not in error.instance]
        return 'Required fields missing: ' + ', '.join(missing) + '.'
    if error.validator == 'additionalProperties':
        return 'Unknown fields are not allowed.'
    if error.validator == 'minItems':
        return f'At least {error.validator_value} item(s) required.'
    if error.validator in ('enum', 'const'):
        return 'Value is not permitted by the contract.'
    if error.validator is None:
        return 'Field is forbidden in this context.'
    return f'Contract constraint failed: {error.validator}.'


def _json_issue(value, path=()):
    # Reject Python-only values before jsonschema can treat tuples or NaN as JSON.
    if value is None or type(value) in (str, bool, int):
        return None
    if type(value) is float and math.isfinite(value):
        return None
    if type(value) is list:
        children = enumerate(value)
    elif type(value) is dict and all(type(k) is str for k in value):
        children = value.items()
    else:
        return ValidationIssue('JSON_VALUE', _pointer(path), 'Expected a finite JSON value.')
    for key, child in children:
        issue = _json_issue(child, (*path, key))
        if issue:
            return issue
    return None


def validate_fact(fact, *, submission=True):
    """Return None or raise FactValidationError; never mutate the supplied fact.

    submission=False validates stored occurrences, including memory-owned validity.
    This does not verify source bytes, premise existence, or execution membership.
    """
    json_issue = _json_issue(fact)
    if json_issue:
        raise FactValidationError([json_issue])
    errors = sorted(_VALIDATOR.iter_errors(fact), key=lambda e: (_pointer(e.absolute_path), str(e.validator)))
    if errors:
        # Do not echo rejected values (which can contain source text or secrets).
        raise FactValidationError([
            ValidationIssue(f'SCHEMA_{e.validator}', _pointer(e.absolute_path), _schema_message(e))
            for e in errors
        ])

    issues = []

    def reject(code, path, message):
        issues.append(ValidationIssue(code, path, message))

    if submission and fact['validity'] != 'VALID':
        reject('SUBMISSION_VALIDITY', '/validity', 'Only the memory can set a validity other than VALID.')
    producer = fact['produced_by']['producer_type']
    if producer not in _STATUS_PRODUCERS[fact['status']]:
        reject('PRODUCER_STATUS', '/produced_by/producer_type', 'Producer is not authorized for this status.')

    def reference(value, path):
        if not _VALIDATOR.evolve(schema=SCHEMA['$defs']['reference']).is_valid(value):
            reject('REFERENCE', path, 'Expected a v1 entity reference.')
            return None
        entity_type, key = value.split(':', 1)
        if key != key.strip() or any(ord(c) < 32 or ord(c) == 127 for c in key):
            reject('REFERENCE', path, 'Reference keys must be nonblank and contain no control characters.')
        if entity_type in {'file', 'directory'} and not _VALIDATOR.evolve(schema=SCHEMA['$defs']['path']).is_valid(key):
            reject('REFERENCE_PATH', path, 'Expected a relative repository path with forward slashes.')
        return entity_type

    if 'subject' in fact:
        reference(fact['subject'], '/subject')
    if 'scope' in fact:
        for field in ('include', 'exclude'):
            for index, value in enumerate(fact['scope'].get(field, [])):
                reference(value, f'/scope/{field}/{index}')
    if fact['kind'] == 'ASSERTION':
        sources, targets, statuses = RELATIONS[fact['relation']]
        if fact['subject'].split(':', 1)[0] not in sources:
            reject('RELATION_SUBJECT', '/subject', 'Subject type is not permitted by this relation.')
        if fact['status'] not in statuses:
            reject('RELATION_STATUS', '/status', 'Status is not permitted by this relation.')
        if not targets:
            if 'object' in fact:
                reject('RELATION_OBJECT', '/object', 'This relation has no object.')
        elif 'object' not in fact:
            reject('RELATION_OBJECT', '/object', 'This relation requires an object.')
        elif fact['relation'] != 'AUTHORIZED_BY' or _REFERENCE_SYNTAX.match(fact['object']):
            # AUTHORIZED_BY also accepts an uninterpreted literal expression, but a value
            # using the reserved type:key syntax is always validated as a reference.
            if reference(fact['object'], '/object') not in targets:
                reject('RELATION_OBJECT', '/object', 'Object type is not permitted by this relation.')

    for index, evidence in enumerate(fact.get('evidence', [])):
        path = f'/evidence/{index}'
        if any(evidence[k] != fact['snapshot'][k] for k in ('repository', 'commit')):
            reject('EVIDENCE_SNAPSHOT', path, 'Evidence must belong to the same repository and commit as the fact.')
        if 'line_start' in evidence and evidence['line_end'] < evidence['line_start']:
            reject('EVIDENCE_LINES', path, 'End line must not precede start line.')
        if 'symbol' in evidence:
            reference(evidence['symbol'], path + '/symbol')
    for index, anchor in enumerate(fact.get('validation', {}).get('anchors', [])):
        reference(anchor['symbol'], f'/validation/anchors/{index}/symbol')
    if issues:
        raise FactValidationError(issues)

    # Identity constraints apply at ingestion, not only when requesting a hash.
    for key in _IDENTITY_FIELDS[fact['kind']]:
        if key in fact:
            _normalize_identity_value(fact[key], (key,))
    if fact['kind'] == 'COVERAGE':
        _normalize_identity_value(fact['produced_by']['producer_id'], ('produced_by', 'producer_id'))


def _normalize_identity_value(value, path):
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise FactValidationError([ValidationIssue(
                'IDENTITY_UNICODE', _pointer(path), 'Identity strings must contain Unicode scalar values.')])
        return unicodedata.normalize('NFC', value)
    if type(value) is int and not -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER:
        raise FactValidationError([ValidationIssue(
            'IDENTITY_INTEGER_RANGE', _pointer(path), 'Identity integers must be within +/- (2^53 - 1).')])
    if isinstance(value, list):
        return [_normalize_identity_value(child, (*path, index)) for index, child in enumerate(value)]
    if isinstance(value, dict):
        normalized = {}
        for key, child in value.items():
            canonical_key = _normalize_identity_value(key, path)
            if canonical_key in normalized:
                raise FactValidationError([ValidationIssue(
                    'IDENTITY_KEY_COLLISION', _pointer(path), 'Object keys collide after Unicode NFC normalization.')])
            normalized[canonical_key] = _normalize_identity_value(child, (*path, key))
        return normalized
    return value


def identity_fields(fact):
    """Return detached canonical identity fields after validating the occurrence."""
    validate_fact(fact, submission=False)
    identity = {key: fact[key] for key in _IDENTITY_FIELDS[fact['kind']] if key in fact}
    if fact['kind'] == 'COVERAGE':
        identity['producer_id'] = fact['produced_by']['producer_id']
    identity = _normalize_identity_value(identity, ())
    if 'scope' in identity:
        scope = identity['scope']
        for key in ('include', 'exclude'):
            if key in scope:
                scope[key] = sorted(set(scope[key]), key=lambda reference: reference.encode('utf-16-be'))
        if not scope.get('exclude'):
            scope.pop('exclude', None)
    return identity


def fact_identity(fact):
    """SHA-256 of the v1 domain and RFC 8785 serialization of identity_fields."""
    return 'sha256:' + hashlib.sha256(_IDENTITY_DOMAIN + rfc8785.dumps(identity_fields(fact))).hexdigest()


def content_hash(source: bytes, line_start=None, line_end=None):
    """SHA-256 of UTF-8 source lines, 1-based and inclusive; no source is retained."""
    if (line_start is None) != (line_end is None):
        raise ValueError('Both line bounds are required.')
    text = source.decode('utf-8').replace('\r', '')
    lines = text.split('\n')
    if text.endswith('\n'):
        lines.pop()
    if not text:
        lines = []
    if line_start is not None:
        if (type(line_start) is not int or type(line_end) is not int
                or not 1 <= line_start <= line_end <= len(lines)):
            raise ValueError('Line range is outside the source.')
        lines = lines[line_start - 1:line_end]
    return 'sha256:' + hashlib.sha256('\n'.join(lines).encode('utf-8')).hexdigest()
