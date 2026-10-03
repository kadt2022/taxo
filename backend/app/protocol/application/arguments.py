"""Les arguments d'une operation du protocole (ARCHITECTURE § 12) : ce qui est recevable, sinon un refus.

Une valeur qui prend la syntaxe reservee `type:cle` est toujours lue comme une reference du contrat
(ARCHITECTURE § 5). Aucune valeur de l'appelant n'est renvoyee telle quelle au-dela de ce que dit le refus.
"""
import re

from app.facts import is_reference
from app.facts.domain.fact import RELATIONS
from app.protocol.domain.envelope import INVALID_ARGUMENT, OperationError

MAX_ARGUMENT_LENGTH = 1000
_REFERENCE_SYNTAX = re.compile(r'[a-z][a-z0-9-]*:')


def text(arguments, name, required=False):
    value = arguments.get(name)
    if value is None:
        if required:
            raise OperationError(INVALID_ARGUMENT, f'Argument requis : {name}.')
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_ARGUMENT_LENGTH:
        raise OperationError(INVALID_ARGUMENT, f'Argument invalide : {name}.')
    return value


def reference(arguments, name, required=False):
    value = text(arguments, name, required)
    if value is not None and not is_reference(value):
        raise OperationError(INVALID_ARGUMENT, f'{name} doit être une référence du contrat (type:clé).')
    return value


def relation(arguments, required=False):
    value = text(arguments, 'relation', required)
    if value is not None and value not in RELATIONS:
        raise OperationError(INVALID_ARGUMENT, f'Relation hors du vocabulaire : {value}.')
    return value


def no_other(arguments, allowed):
    unknown = sorted(set(arguments) - set(allowed))
    if unknown:
        raise OperationError(INVALID_ARGUMENT, f'Argument inconnu : {", ".join(unknown)}.')


def claim_object(relation, target):
    """L'objet d'une affirmation doit etre du type que la relation admet (ARCHITECTURE § 5, vocabulaire v1)."""
    _, targets, _ = RELATIONS[relation]
    if bool(targets) != (target is not None):
        raise OperationError(INVALID_ARGUMENT, f'{relation} {"exige" if targets else "n’a pas"} d’objet.')
    if target is None or (relation == 'AUTHORIZED_BY' and not _REFERENCE_SYNTAX.match(target)):
        return
    if not is_reference(target) or target.split(':', 1)[0] not in targets:
        raise OperationError(INVALID_ARGUMENT, f'Objet attendu pour {relation} : {", ".join(sorted(targets))}.')
