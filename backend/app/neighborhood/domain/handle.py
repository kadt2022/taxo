"""Désigner une occurrence d'une analyse hors de l'échange qui l'a rendue (TAXO-01J, § 7).

Une poignée nomme une analyse, une génération de faits et une occurrence : rien d'autre. Elle n'est jamais une
autorisation : l'échange ne sert que son analyse, et refuse toute poignée d'ailleurs sans dire ce qui existe.
"""
import base64
import json

VERSION = 'occurrence/1'
MAX_HANDLE = 2000
REFUSED = 'Poignée d’occurrence inconnue de cette analyse, ou d’une autre génération de ses faits.'


class HandleError(ValueError):
    pass


def encode(analysis, revision, occurrence):
    raw = json.dumps([VERSION, analysis, revision, occurrence], separators=(',', ':')).encode()
    return 'o' + base64.urlsafe_b64encode(raw).decode().rstrip('=')


def decode(handle, analysis, revision):
    """La clé de l'occurrence, si la poignée désigne cette analyse à cette génération ; sinon un refus, le même
    quelle que soit la raison."""
    if not isinstance(handle, str) or not handle.startswith('o') or len(handle) > MAX_HANDLE:
        raise HandleError(REFUSED)
    body = handle[1:]
    try:
        values = json.loads(base64.b64decode(body + '=' * (-len(body) % 4), altchars=b'-_', validate=True))
    except ValueError as exc:
        raise HandleError(REFUSED) from exc
    if (not isinstance(values, list) or len(values) != 4 or values[0] != VERSION or values[1] != analysis
            or values[2] != revision or not isinstance(values[3], str)):
        raise HandleError(REFUSED)
    return values[3]
