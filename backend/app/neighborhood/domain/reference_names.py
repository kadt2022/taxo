"""Retrouver une référence par son nom (TAXO-01N, PR A2, `find_references` avec `match: NAME`).

Une clé Java commence par son paquet : le nom seul (`VetController`, `OwnerRepository.findById`) n'en est pas un
préfixe. Le nom se compare donc à une **fin** de la clé, prise à un début de segment et jusqu'au dernier segment :
`VetController` trouve `…web.VetController`, jamais `…VetController#show()`, dont il ne couvre pas le dernier
segment. Aucune règle propre à un langage : un jeu fixe de séparateurs, ramenés à un seul.

La liste de paramètres n'a de sens que pour un symbole appelable : une clé `symbol:` dont le dernier segment suit
un `#` et se termine par `(…)`. Un nom sans liste trouve toutes ses surcharges ; un nom avec liste ne trouve que
la sienne. Ailleurs (le fichier `file:Items.list(String)`), les parenthèses sont des caractères ordinaires.

Un nom qui commence par un séparateur (le chemin `/api/students`) se compare sans lui : une fin de clé commence
après un séparateur, jamais sur lui. `/api/students` trouve donc `endpoint:GET /api/students` comme le ferait
`api/students`.

Chaque fin de clé possible est une entrée de l'index ; une entrée plus longue que la clé de l'index ne peut être
égale à aucun nom accepté et n'est pas gardée. La comparaison est une égalité : jamais de troncature.
"""
import unicodedata

from app.neighborhood.domain.references import KEY_LENGTH, KEY_MATCH, ReferenceSearchError

KEY, NAME = KEY_MATCH, 'NAME'
MATCHES = (KEY, NAME)
SEPARATORS = frozenset('./#:$')
CANONICAL = '.'
CALLABLE_TYPE, MEMBER, OPENING, CLOSING = 'symbol', '#', '(', ')'


def _canonical(text):
    """Repliée en casse, chaque séparateur ramené au même : ce que l'on compare."""
    return ''.join(CANONICAL if character in SEPARATORS else character for character in text.casefold())


def _callable(kind, key):
    """(tête, liste de paramètres) d'un symbole appelable ; None pour toute autre référence."""
    member = key.rfind(MEMBER)
    if kind != CALLABLE_TYPE or member < 0 or not key.endswith(CLOSING):
        return None
    opening = key.find(OPENING, member)
    if opening < 0 or any(character in SEPARATORS for character in key[member + 1:opening]):
        return None
    return key[:opening], key[opening:]


def _endings(text):
    """Les fins de `text` qui commencent à un début de segment."""
    starts = [0, *(position + 1 for position, character in enumerate(text) if character in SEPARATORS)]
    return [text[start:] for start in starts if start < len(text)]


def name_keys(reference):
    """Les noms sous lesquels une référence se retrouve, chacun une fois (une clé aux segments répétés aussi)."""
    kind, _, key = reference.partition(':')
    key = unicodedata.normalize('NFC', key)
    split = _callable(kind, key)
    if split is None:
        found = {_canonical(ending) for ending in _endings(key)}
    else:
        head, parameters = split
        found = {_canonical(ending + listed) for ending in _endings(head) for listed in ('', parameters)}
    return sorted(name for name in found if len(name) <= KEY_LENGTH)


def name_key(name):
    """Le nom demandé tel qu'il se compare ; refusé s'il dépasse la clé de l'index une fois replié."""
    compared = _canonical(unicodedata.normalize('NFC', name)).lstrip(CANONICAL)
    if not compared:
        raise ReferenceSearchError('prefix : un nom ne peut pas être fait que de séparateurs.')
    if len(compared) > KEY_LENGTH:
        raise ReferenceSearchError(f'prefix : plus de {KEY_LENGTH} caractères une fois replié en casse.')
    return compared
