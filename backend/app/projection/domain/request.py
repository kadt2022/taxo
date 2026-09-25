"""Ce que demande l'utilisateur, lu dans sa phrase (TAXO-QUERY-01). La requete sait selectionner.

Trois selections de l'historique : un nombre explicite de derniers commits, un commit, une periode (dates
ISO : AAAA-MM-JJ ou AAAA-MM). Un nombre et une periode se combinent (« les 3 derniers commits depuis
2026-09-01 »). Aucune autre phrase ne devient une selection : « Analyse le projet » reste l'analyse
globale, jamais « les derniers commits », et aucun nombre n'est suppose quand la phrase n'en donne pas.
"""
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from .errors import INVALID_REQUEST, QueryError

GLOBAL, LATEST, COMMIT, PERIOD = 'GLOBAL', 'LATEST', 'COMMIT', 'PERIOD'

_WORDS = {'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5, 'six': 6, 'sept': 7,
          'huit': 8, 'neuf': 9, 'dix': 10}
_NUMBER = r'(\d+|' + '|'.join(_WORDS) + r')'
_LATEST = (re.compile(_NUMBER + r'\s+(?:derniers|dernieres|last)\b'),
           re.compile(r'\b(?:derniers|dernieres|last)\s+' + _NUMBER + r'\b'))
_LAST_ONE = re.compile(r'\b(?:le\s+)?dernier\s+commit\b|\blast\s+commit\b')
_SHA = re.compile(r'(?<![0-9a-z])(commit\s+)?([0-9a-f]{7,64})(?![0-9a-z])')
_DATE = re.compile(r"(?:(depuis|apres|a partir du|a partir de|since|avant|before|jusqu'au|jusqu'a|jusqu au|"
                   r"until|entre|du|au|et|le|en)\s+)?(\d{4})-(\d{2})(?:-(\d{2}))?(?![\d-])")
_SINCE, _UNTIL = {'depuis', 'apres', 'a partir du', 'a partir de', 'since', 'entre', 'du'}, \
    {"jusqu'au", "jusqu'a", 'jusqu au', 'until', 'au', 'et'}
_BEFORE = {'avant', 'before'}


@dataclass(frozen=True)
class Request:
    kind: str
    text: str
    count: int | None = None
    commit: str | None = None
    since: str | None = None
    until: str | None = None

    def as_dict(self):
        return asdict(self)


def _plain(text):
    decomposed = unicodedata.normalize('NFKD', text.lower().replace('’', "'"))
    return ''.join(char for char in decomposed if not unicodedata.combining(char))


def _count(text):
    for pattern in _LATEST:
        match = pattern.search(text)
        if match:
            value = match.group(1)
            count = _WORDS[value] if value in _WORDS else int(value)
            if count < 1:
                raise QueryError(INVALID_REQUEST, 'Le nombre de commits demandé doit être au moins 1.')
            return count
    return 1 if _LAST_ONE.search(text) else None


def _commit(text):
    for match in _SHA.finditer(text):
        keyword, value = match.groups()
        if keyword or re.search('[a-f]', value):
            return value
    return None


def _bounds(year, month, day):
    try:
        start = date(int(year), int(month), int(day or 1))
    except ValueError as exc:
        raise QueryError(INVALID_REQUEST, f'Date invalide : {year}-{month}{"-" + day if day else ""}.') from exc
    if day:
        return start, start
    following = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    return start, following - timedelta(days=1)


def _period(text):
    since = until = None
    matches = list(_DATE.finditer(text))
    for match in matches:
        keyword, year, month, day = match.groups()
        start, end = _bounds(year, month, day)
        if keyword in _SINCE:
            since = start
        elif keyword in _UNTIL:
            until = end
        elif keyword in _BEFORE:
            until = start - timedelta(days=1)
        elif len(matches) == 1:
            since, until = start, end
        else:
            since, until = (start, until) if since is None else (since, end)
    if since and until and since > until:
        raise QueryError(INVALID_REQUEST, 'La période demandée finit avant de commencer.')
    return (since.isoformat() if since else None), (until.isoformat() if until else None)


def parse(text):
    """Requete lue dans la phrase ; QueryError si elle demande quelque chose d'impossible."""
    text = (text or '').strip()
    plain = _plain(text)
    commit = _commit(plain)
    if commit:
        return Request(COMMIT, text, commit=commit)
    count = _count(plain)
    since, until = _period(plain)
    if count:
        return Request(LATEST, text, count=count, since=since, until=until)
    if since or until:
        return Request(PERIOD, text, since=since, until=until)
    return Request(GLOBAL, text)
