"""Compatibility facade for the v1 Python contract and canonical JSON identity."""
import hashlib
import rfc8785
from .domain.errors import FactValidationError
from .domain.fact import RELATIONS
from .domain.identity import canonical_identity, _IDENTITY_DOMAIN
from .domain.evidence import content_hash
from .application.validate_fact import validate_fact as validate
from .infrastructure.contract.json_schema_validator import JsonSchemaValidator, SCHEMA, SCHEMA_PATH

_validator = JsonSchemaValidator()

def validate_fact(fact, *, submission=True):
    return validate(fact, _validator, submission=submission)

def identity_fields(fact):
    validate_fact(fact, submission=False)
    return canonical_identity(fact)

def fact_identity(fact):
    return 'sha256:' + hashlib.sha256(_IDENTITY_DOMAIN + rfc8785.dumps(identity_fields(fact))).hexdigest()
