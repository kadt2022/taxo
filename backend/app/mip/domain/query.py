"""Lire une requête MIP 0.1 (ARCHITECTURE § 12.0, récit TAXO-01N / MIP-01 § 4.1).

Une requête nomme une expression, une référence déjà résolue, les relations à suivre et leur sens. Elle est lue
en entier avant d'être servie, jamais interprétée : un champ inconnu, un type faux ou une expression non servie
est une erreur de protocole, pas une frontière de connaissance. Seule la forme est lue ici : le vocabulaire des
relations, les références et les budgets sont validés par l'opération `taxo-query/1` servie, une seule fois. Les
bornes demandées sont plafonnées par celles du serveur, jamais l'inverse ; c'est l'affaire du service, qui connaît
les plafonds du moteur.
"""
from dataclasses import dataclass

from app.protocol.domain.envelope import INVALID_ARGUMENT, NOT_AVAILABLE

VERSION = 'mip/0.1'
EXPAND, PROJECT = 'EXPAND', 'PROJECT'
EXPRESSIONS = frozenset({EXPAND, PROJECT})
SERVED = frozenset({EXPAND})
DIRECTIONS = frozenset({'INCOMING', 'OUTGOING', 'BOTH'})
BOUNDS = ('depth', 'max_nodes', 'max_facts', 'max_bytes')
_FIELDS = frozenset({'mip', 'expression', 'target', 'analysis', 'relations', 'direction', 'bounds', 'continuation'})
MAX_TEXT = 1000
MAX_CONTINUATION = 4000
MAX_RELATIONS = 16
# Au-delà, une borne n'est plus une demande mais une donnée hors contrat ; en deçà, le serveur plafonne.
MAX_BOUND = 10 ** 6


class MipError(Exception):
    """Refus d'une requête, avec un code du registre existant du protocole (aucune catégorie nouvelle)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MipQuery:
    """Une requête lue : ce qui est demandé, sans encore rien de la Maille."""
    expression: str
    reference: str
    relations: tuple
    direction: str
    bounds: dict
    analysis: str | None = None
    continuation: str | None = None


def _invalid(message):
    raise MipError(INVALID_ARGUMENT, message)


def _choice(value, name, allowed):
    if not isinstance(value, str) or value not in allowed:
        _invalid(f'{name} : {" ou ".join(sorted(allowed))}.')
    return value


def _text(value, name, required=True, longest=MAX_TEXT):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > longest:
        _invalid(f'{name} : un texte non vide d’au plus {longest} caractères.')
    return value


def _target(value):
    if not isinstance(value, dict) or set(value) != {'reference'}:
        _invalid('target : {"reference": une référence résolue par Taxo}.')
    return _text(value['reference'], 'target.reference')


def _relations(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= MAX_RELATIONS
            or any(not isinstance(item, str) or not item for item in value) or len(set(value)) != len(value)):
        _invalid(f'relations : 1 à {MAX_RELATIONS} relations distinctes, annoncées par describe.')
    return tuple(value)


def _bounds(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - set(BOUNDS):
        _invalid(f'bounds : un objet dont les champs sont parmi {", ".join(BOUNDS)}.')
    for name, number in value.items():
        if type(number) is not int or not 1 <= number <= MAX_BOUND:
            _invalid(f'bounds.{name} : un entier entre 1 et {MAX_BOUND}.')
    return dict(value)


def read_query(payload) -> MipQuery:
    """La requête lue en entier, ou le refus qui dit quoi corriger."""
    if not isinstance(payload, dict):
        _invalid('La requête MIP est un objet JSON.')
    unknown = set(payload) - _FIELDS
    if unknown:
        _invalid(f'Champ inconnu : {sorted(unknown)[0][:100]}.')
    if payload.get('mip', VERSION) != VERSION:
        _invalid(f'Version attendue : {VERSION}.')
    expression = _choice(payload.get('expression'), 'expression', EXPRESSIONS)
    if expression not in SERVED:
        raise MipError(NOT_AVAILABLE, f'{expression} n’est pas servie en {VERSION} : aucune règle de projection '
                                      'n’est encore écrite.')
    direction = _choice(payload.get('direction'), 'direction', DIRECTIONS)
    return MipQuery(expression, _target(payload.get('target')), _relations(payload.get('relations')), direction,
                    _bounds(payload.get('bounds')), _text(payload.get('analysis'), 'analysis', required=False),
                    _text(payload.get('continuation'), 'continuation', required=False, longest=MAX_CONTINUATION))
