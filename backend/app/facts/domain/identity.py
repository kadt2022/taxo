import unicodedata
from .errors import FactValidationError, ValidationIssue, _pointer

_IDENTITY_FIELDS = {
    'ASSERTION': ('kind', 'subject', 'relation', 'object', 'qualifiers'),
    'ABSENCE': ('kind', 'pattern', 'scope', 'method'),
    'COVERAGE': ('kind', 'subject', 'coverage_type', 'scope'),
}
_IDENTITY_DOMAIN = b'taxo-fact-identity/v1\n'
_MAX_SAFE_INTEGER = 2**53 - 1


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


def canonical_identity(fact):
    """Return detached canonical identity fields for an already validated occurrence."""
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
