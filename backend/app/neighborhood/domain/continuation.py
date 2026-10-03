"""Reprendre une adjacence coupée (ARCHITECTURE § 9 et TAXO-01J § 6).

Une reprise est un repère de sélection, jamais une autorisation. Elle est liée à la version du moteur, à
l'instantané, aux paramètres qui fixent l'ordre et à la génération des faits ; elle est refusée ailleurs.

- `neighborhood/1` : la reprise de l'adjacence de l'ancre, au format d'origine, inchangé ;
- `neighborhood/2` : la reprise de l'adjacence d'un nœud, marquée de sa version : elle n'est jamais prise
  pour une reprise de `neighborhood/1`, ni l'inverse.
"""
import base64
import hashlib
import json

from app.neighborhood.domain.frontier import Position

V1, V2 = 'neighborhood/1', 'neighborhood/2'
MAX_TOKEN = 16000
INVALID = 'Reprise invalide.'
INCOMPATIBLE = 'Reprise incompatible avec l’analyse, l’ancre, le sens ou la priorité.'


class ContinuationError(ValueError):
    pass


def binding(version, snapshot, parameters, revision):
    return hashlib.sha256(json.dumps([version, snapshot, parameters, revision], sort_keys=True).encode()).hexdigest()


def _encode(values):
    raw = json.dumps(values, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def _decode(token):
    if not isinstance(token, str) or len(token) > MAX_TOKEN:
        raise ContinuationError(INVALID)
    try:
        return json.loads(base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True))
    except ValueError as exc:
        raise ContinuationError(INCOMPATIBLE) from exc


def _rank(value):
    return isinstance(value, str) and (value == '' or (value.isascii() and value.isdigit() and len(value) <= 19))


def is_v2(token):
    """Une reprise émise par `neighborhood/2` ? Elle porte sa version en tête ; rien d'autre n'est cru."""
    try:
        values = _decode(token)
    except ContinuationError:
        return False
    return isinstance(values, list) and len(values) == 5 and values[0] == V2


class AnchorCursor:
    """`neighborhood/1` : la position dans l'adjacence de l'ancre, au format d'origine."""

    def __init__(self, bound, steps):
        self.bound, self.steps = bound, steps

    def encode(self, position):
        return _encode([self.bound, position.step, position.after])

    def decode(self, token, root):
        if token is None:
            return Position(root, 0)
        values = _decode(token)
        valid = (isinstance(values, list) and len(values) == 3 and values[0] == self.bound
                 and type(values[1]) is int and 0 <= values[1] < self.steps and _rank(values[2]))
        if not valid:
            raise ContinuationError(INCOMPATIBLE)
        return Position(root, values[1], values[2])


class NodeCursor:
    """`neighborhood/2` : la position dans l'adjacence d'un nœud. La Tuile qui reprend part de ce nœud."""

    def __init__(self, bound, steps):
        self.bound, self.steps = bound, steps

    def encode(self, position):
        return _encode([V2, self.bound, position.node, position.step, position.after])

    def decode(self, token, root):
        if token is None:
            return Position(root, 0)
        values = _decode(token)
        valid = (isinstance(values, list) and len(values) == 5 and values[0] == V2 and values[1] == self.bound
                 and values[2] == root and type(values[3]) is int and 0 <= values[3] < self.steps
                 and _rank(values[4]))
        if not valid:
            raise ContinuationError(INCOMPATIBLE)
        return Position(root, values[3], values[4])
