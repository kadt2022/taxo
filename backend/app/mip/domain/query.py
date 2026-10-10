"""Lire une requête MIP 0.1 (ARCHITECTURE § 12.0, récit TAXO-01N / MIP-01 § 4.1).

Une requête nomme une expression, une référence déjà résolue, les relations à suivre et leur sens. Elle est lue
en entier avant d'être servie, jamais interprétée : un champ inconnu, un type faux ou une expression non servie
est une erreur de protocole, pas une frontière de connaissance. Seule la forme est lue ici : le vocabulaire des
relations, les références et les budgets sont validés par l'opération `taxo-query/1` servie, une seule fois. Les
bornes demandées sont plafonnées par celles du serveur, jamais l'inverse ; c'est l'affaire du service, qui connaît
les plafonds du moteur.

Une requête nomme soit ses relations et leur sens, soit un profil déclaré (récit TAXO-MIP-ADT-01) : jamais les deux.
Un profil inconnu, ou une ancre d'un type qu'il n'accepte pas, est refusé ; aucun profil n'est improvisé.
"""
from dataclasses import dataclass

from app.mip.domain.profiles import PROFILES, Profile
from app.protocol.domain.envelope import INVALID_ARGUMENT, NOT_AVAILABLE

VERSION = 'mip/0.1'
EXPAND, PROJECT = 'EXPAND', 'PROJECT'
EXPRESSIONS = frozenset({EXPAND, PROJECT})
SERVED = frozenset({EXPAND})
DIRECTIONS = frozenset({'INCOMING', 'OUTGOING', 'BOTH'})
BOUNDS = ('depth', 'max_nodes', 'max_facts', 'max_bytes')
EXPRESSION, ANALYSIS, DIRECTION, CONTINUATION = 'expression', 'analysis', 'direction', 'continuation'
RELATIONS, PROFILE = 'relations', 'profile'
_FIELDS = frozenset({'mip', EXPRESSION, 'target', ANALYSIS, RELATIONS, DIRECTION, PROFILE, 'bounds', CONTINUATION})
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
    """Une requête lue : ce qui est demandé, sans encore rien de la Maille. Avec un profil, `relations` et
    `direction` sont vides : ses pas les remplacent."""
    expression: str
    reference: str
    relations: tuple
    direction: str | None
    bounds: dict
    analysis: str | None = None
    continuation: str | None = None
    profile: Profile | None = None


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


def _profile(value, reference):
    profile = PROFILES.get(value) if isinstance(value, str) else None
    if profile is None:
        _invalid(f'profile : un profil déclaré parmi {", ".join(sorted(PROFILES))}.')
    if not profile.accepts(reference):
        _invalid(f'{profile.identifier} accepte une ancre de type {" ou ".join(sorted(profile.anchors))}.')
    return profile


def read_query(payload) -> MipQuery:
    """La requête lue en entier, ou le refus qui dit quoi corriger."""
    if not isinstance(payload, dict):
        _invalid('La requête MIP est un objet JSON.')
    unknown = set(payload) - _FIELDS
    if unknown:
        _invalid(f'Champ inconnu : {sorted(unknown)[0][:100]}.')
    if payload.get('mip', VERSION) != VERSION:
        _invalid(f'Version attendue : {VERSION}.')
    expression = _choice(payload.get(EXPRESSION), EXPRESSION, EXPRESSIONS)
    if expression not in SERVED:
        raise MipError(NOT_AVAILABLE, f'{expression} n’est pas servie en {VERSION} : aucune règle de projection '
                                      'n’est encore écrite.')
    reference = _target(payload.get('target'))
    bounds = _bounds(payload.get('bounds'))
    analysis = _text(payload.get(ANALYSIS), ANALYSIS, required=False)
    continuation = _text(payload.get(CONTINUATION), CONTINUATION, required=False, longest=MAX_CONTINUATION)
    if PROFILE in payload:
        if {RELATIONS, DIRECTION} & set(payload):
            _invalid('profile exclut relations et direction : ses pas les déclarent.')
        return MipQuery(expression, reference, (), None, bounds, analysis, continuation,
                        _profile(payload[PROFILE], reference))
    direction = _choice(payload.get(DIRECTION), DIRECTION, DIRECTIONS)
    return MipQuery(expression, reference, _relations(payload.get(RELATIONS)), direction, bounds, analysis,
                    continuation)
