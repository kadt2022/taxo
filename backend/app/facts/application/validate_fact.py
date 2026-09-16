from app.facts.domain.fact import validate_semantics
from .ports import FactContractValidator

def validate_fact(fact, validator: FactContractValidator, *, submission=True):
    validator.validate(fact)
    validate_semantics(fact, validator, submission=submission)
