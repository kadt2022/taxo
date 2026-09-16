import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from app.facts.domain.errors import FactValidationError, ValidationIssue, _pointer

SCHEMA_PATH = Path(__file__).with_name('contract-v1.schema.json')
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
_VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
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


def validate_structure(fact):
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


class JsonSchemaValidator:
    def validate(self, fact):
        validate_structure(fact)

    def is_reference(self, value):
        return _VALIDATOR.evolve(schema=SCHEMA['$defs']['reference']).is_valid(value)

    def is_path(self, value):
        return _VALIDATOR.evolve(schema=SCHEMA['$defs']['path']).is_valid(value)
