"""Chercher une référence d'une analyse par le début de sa clé (TAXO-01J, `find_references`).

La règle de comparaison est ici, une seule fois : la clé d'une référence (après son type), sous sa forme
canonique (NFC), repliée en casse. L'index la tronque à une longueur fixe ; un préfixe ne la dépasse jamais.
La reprise est liée à l'analyse, à la génération des faits, au préfixe et au type : refusée ailleurs.
"""
import base64
import json
import unicodedata

VERSION = 'references/1'
KEY_LENGTH = 256
MAX_PREFIX = 200
MAX_LIMIT, DEFAULT_LIMIT = 50, 20
REFUSED = 'Reprise de recherche incompatible avec l’analyse, sa génération, le préfixe ou le type.'


class ReferenceSearchError(ValueError):
    pass


def fold(text):
    """Ce que l'on compare : la forme canonique, repliée en casse, à la longueur de l'index."""
    return unicodedata.normalize('NFC', text).casefold()[:KEY_LENGTH]


def encode(analysis, revision, prefix, kind, last):
    raw = json.dumps([VERSION, analysis, revision, prefix, kind, *last], separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode(token, analysis, revision, prefix, kind):
    """(clé, empreinte) de la dernière référence rendue ; None sans reprise."""
    if token is None:
        return None
    if not isinstance(token, str) or len(token) > 4000:
        raise ReferenceSearchError(REFUSED)
    try:
        values = json.loads(base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True))
    except ValueError as exc:
        raise ReferenceSearchError(REFUSED) from exc
    if (not isinstance(values, list) or len(values) != 7 or values[:5] != [VERSION, analysis, revision, prefix, kind]
            or not all(isinstance(value, str) for value in values[5:])):
        raise ReferenceSearchError(REFUSED)
    return values[5], values[6]
