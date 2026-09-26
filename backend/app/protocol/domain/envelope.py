"""Enveloppe commune des reponses du protocole Taxo (ADR 0009, section 4).

Toute reponse d'operation a la meme forme : une issue (`OK` ou `ERROR`, avec un code ferme), l'instantane
de l'echange, les resultats sous references courtes, la couverture (obligatoire), ce qui n'a pas ete
transmis et sa taille en octets. Rien n'est tronque au milieu : un element qui ne tient pas dans le budget
n'est pas transmis, il est compte dans `not_sent`.

Taille : octets UTF-8 du JSON compact, borne sure du nombre de tokens (ADR 0009, section 7).
"""
import json

PROTOCOL = 'taxo-query/1'
OK, ERROR = 'OK', 'ERROR'

INVALID_ARGUMENT = 'INVALID_ARGUMENT'
NO_CONSENT = 'NO_CONSENT'
NOT_AVAILABLE = 'NOT_AVAILABLE'
OUT_OF_SCOPE = 'OUT_OF_SCOPE'
BUDGET_EXHAUSTED = 'BUDGET_EXHAUSTED'
INTERNAL = 'INTERNAL'
ERROR_CODES = frozenset({INVALID_ARGUMENT, NO_CONSENT, NOT_AVAILABLE, OUT_OF_SCOPE, BUDGET_EXHAUSTED, INTERNAL})

BUDGET = 'BUDGET'
# Place gardee pour `not_sent` et pour la taille elle-meme, qui ne sont connues qu'a la fin.
_RESERVED = [{'what': 'evidence', 'count': 10 ** 7, 'reason': BUDGET},
             {'what': 'items', 'count': 10 ** 7, 'reason': BUDGET}]
_SIZE_PLACEHOLDER = 10 ** 9
# Taille maximale d'une reponse `ERROR` : l'echange garde toujours de quoi refuser les operations restantes.
MAX_ERROR_BYTES = 512


class OperationError(Exception):
    """Refus d'une operation, rendu comme resultat `ERROR`, jamais comme exception au transport."""

    def __init__(self, code, message):
        if code not in ERROR_CODES:
            raise ValueError(f'Code d’erreur hors protocole : {code}')
        super().__init__(message)
        self.code = code


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def _sized(envelope):
    envelope['bytes'] = 0
    while envelope['bytes'] != size(envelope):
        envelope['bytes'] = size(envelope)
    return envelope


def error(operation, snapshot, code, message):
    """Reponse `ERROR`, jamais plus grande que MAX_ERROR_BYTES : le message est raccourci s'il le faut."""
    while True:
        envelope = _sized({'protocol': PROTOCOL, 'operation': operation, 'outcome': ERROR, 'snapshot': snapshot,
                           'error': {'code': code, 'message': message}})
        if envelope['bytes'] <= MAX_ERROR_BYTES or not message:
            return envelope
        message = message[:len(message) * 3 // 4].rstrip() + '…' if len(message) > 1 else ''


class Response:
    """Reponse `OK` remplie dans la limite de `max_bytes` : chaque ajout est accepte ou refuse en entier.

    Des qu'un element d'une section ne tient pas, les suivants de cette section ne sont plus proposes :
    l'ordre de pertinence est conserve et le reste est compte dans `not_sent`.
    """

    def __init__(self, operation, snapshot, coverage, max_bytes, **fields):
        self.envelope = {'protocol': PROTOCOL, 'operation': operation, 'outcome': OK, 'snapshot': snapshot,
                         **fields, 'items': [], 'evidence': [], 'coverage': list(coverage), 'not_sent': []}
        self.max_bytes = max_bytes
        self.used = size({**self.envelope, 'not_sent': _RESERVED, 'bytes': _SIZE_PLACEHOLDER})
        self.full = set()
        self.skipped = {}

    @property
    def fits(self):
        """La couverture, obligatoire, et l'enveloppe tiennent-elles dans le budget ?"""
        return self.used <= self.max_bytes

    def add(self, section, entry):
        """Ajoute `entry` a `section` s'il tient ; sinon le compte comme non transmis et rend False."""
        cost = size(entry) + (1 if self.envelope[section] else 0)
        if section in self.full or self.used + cost > self.max_bytes:
            self.full.add(section)
            self.skip(section)
            return False
        self.envelope[section].append(entry)
        self.used += cost
        return True

    def skip(self, section, count=1):
        self.skipped[section] = self.skipped.get(section, 0) + count

    def not_sent(self, entry):
        """Element non transmis pour une autre raison que le budget (contenu refuse, par exemple). Sa mention
        compte dans le budget comme le reste ; si elle ne tient pas, la reponse ne peut pas etre servie."""
        cost = size(entry) + 1
        if self.used + cost > self.max_bytes:
            raise OperationError(BUDGET_EXHAUSTED, 'Plus assez de place pour dire ce qui n’est pas transmis.')
        self.envelope['not_sent'].append(entry)
        self.used += cost

    def close(self):
        budget = [{'what': section, 'count': count, 'reason': BUDGET}
                  for section, count in sorted(self.skipped.items()) if count]
        self.envelope['not_sent'] = budget + self.envelope['not_sent']
        return _sized(self.envelope)
