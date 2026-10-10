"""Le repli paquet sans invention (récit TAXO-01N / MIP-01 § 5.3) : les ancres explicites d'une question.

Quand Minia ne peut pas explorer, Taxo cherche lui-même, sans modèle, de quoi la question parle : une référence
complète (`symbol:java:…#register(String)`), ou un nom qui a la forme d'un nom de code (`VetController`,
`OwnerRepository.findById`, ou tout texte entre accents graves), ou une route HTTP (`GET /api/students`,
`/api/admin/**`). Un mot ordinaire n'est jamais cherché : « service » trouverait un paquet par hasard. Aucune règle
propre à un langage : une route se reconnaît à sa forme HTTP (un chemin qui commence par `/`, peut-être précédé de
son verbe en majuscules), pas à un framework.

Une ancre n'est retenue que si elle est **unique** : une seule référence, trouvée par des recherches épuisées
(aucune reprise, rien de non transmis). Une page tronquée ne prouve rien ; plusieurs références restent des
candidates, et c'est l'utilisateur qui choisit, jamais Taxo.
"""
import re
import unicodedata
from dataclasses import dataclass

MAX_CANDIDATES = 4
MAX_NAME = 200
NAME, KEY = 'NAME', 'KEY'
FOUND, AMBIGUOUS, NONE = 'FOUND', 'AMBIGUOUS', 'NONE'

_QUOTED = re.compile(r'`([^`\n]{1,200})`')
# Un nom de code : des segments séparés par . # $ ou /, et peut-être une liste de paramètres.
_CODE = re.compile(r'[A-Za-z_][\w$.#/<>]*(?:\([\w$.<>\[\], ]*\))?')
_INNER_CAPITAL = re.compile(r'[a-z\d][A-Z]')
# Les méthodes de HTTP (RFC 9110), et `ANY`, la route servie pour toute méthode (`endpoint:ANY /…` du contrat).
_VERBS = 'GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|TRACE|ANY'
# Une référence complète : un type en minuscules, puis sa clé, jusqu'au prochain blanc ; une clé de route garde le
# blanc entre son verbe et son chemin (`endpoint:GET /api/students`).
# Jamais au milieu d'un chemin : `{id:[0-9]+}` est une variable de route, pas une référence.
_REFERENCE = re.compile(r'(?<![{/])\b[a-z][a-z-]*:(?:(?:' + _VERBS + r') /\S+|\S+)')
# Une route HTTP : un chemin qui commence par `/` hors d'un mot (jamais `et/ou` ni `2026/09`), suivi d'autre chose
# qu'une barre ou un blanc, et peut-être son verbe en majuscules juste avant. Le chemin va jusqu'au prochain blanc, tel qu'il est
# écrit (`/api/{id:[0-9]+}`), moins la ponctuation qui le suit dans la phrase.
_ROUTE_FORM = r'(?:(?:' + _VERBS + r')\s+)?/[^\s/]\S*'
_ROUTE = re.compile(r'(?<![\w/])' + _ROUTE_FORM)
_WHOLE_ROUTE = re.compile(_ROUTE_FORM)
_VERB_SET = frozenset(verb.casefold() for verb in _VERBS.split('|'))
_TRAILING = '?!.,;:"\'»”’'
_CLOSING = {')': '(', ']': '['}
_BLANKS = re.compile(r'\s+')


def _trimmed(text):
    """Le texte cité, sans la ponctuation ni les guillemets qui le suivent dans la phrase ; une parenthèse ou un
    crochet fermant n'est retiré que s'il ne ferme rien dans le texte (`(GET /api/x)`, pas `#c(String)`)."""
    while text:
        last = text[-1]
        if last in _TRAILING or (last in _CLOSING and text.count(_CLOSING[last]) < text.count(last)):
            text = text[:-1]
        else:
            return text
    return text


def _folded(text):
    return unicodedata.normalize('NFC', text).casefold()


@dataclass(frozen=True)
class Candidate:
    """Ce que la question nomme : une référence complète (`KEY`), ou un nom à retrouver (`NAME`). Une route
    (`route`) se cherche par son nom, mais ne retient que les références dont la clé est cette route entière."""
    mode: str
    text: str
    route: bool = False

    def accepts(self, reference):
        """La recherche par nom compare une fin de clé : `/api/students` y trouverait aussi `GET /v1/api/students`.
        Une route ne retient que la clé égale à la route citée, avec son verbe s'il est cité, sinon avec ou sans
        verbe (`endpoint:POST /api/students`, `route-pattern:/api/students`)."""
        if not self.route:
            return True
        key, route = _folded(reference.partition(':')[2]), _folded(self.text)
        if not route.startswith('/'):
            return key == route
        verb, blank, path = key.partition(' ')
        return key == route or (bool(blank) and verb in _VERB_SET and path == route)

    @property
    def search(self):
        """Les arguments de `find_references` qui la cherchent."""
        if self.mode == NAME:
            return {'prefix': self.text, 'match': NAME}
        kind, _, key = self.text.partition(':')
        return {'prefix': key[:MAX_NAME], 'type': kind}


@dataclass(frozen=True)
class Search:
    """Ce qu'une recherche a rendu : ses références, et si elle est allée jusqu'au bout."""
    candidate: Candidate
    references: tuple
    exhausted: bool


@dataclass(frozen=True)
class Resolution:
    status: str
    anchor: str | None
    candidates: tuple


def _looks_like_code(token):
    """Un nom qui ne peut pas être un mot ordinaire : qualifié, appelé, ou en casse mixte (`findById`)."""
    return any(mark in token for mark in '.#$(') or bool(_INNER_CAPITAL.search(token))


def candidates(question):
    """Les ancres explicites de la question, dans leur ordre, chacune une fois, au plus MAX_CANDIDATES."""
    found, taken = [], set()

    def keep(candidate):
        if candidate.text and candidate not in taken and len(found) < MAX_CANDIDATES:
            taken.add(candidate)
            found.append(candidate)

    rest = question
    for match in _REFERENCE.finditer(question):
        keep(Candidate(KEY, _trimmed(match.group(0))))
        rest = rest.replace(match.group(0), ' ')
    for match in _QUOTED.finditer(rest):
        quoted = match.group(1).strip()
        # Une route entre accents graves garde le sens d'une route : la route entière, jamais une fin de clé.
        if _WHOLE_ROUTE.fullmatch(quoted):
            quoted = _BLANKS.sub(' ', quoted)
        keep(Candidate(NAME, quoted[:MAX_NAME], route=bool(_WHOLE_ROUTE.fullmatch(quoted))))
    rest = _QUOTED.sub(' ', rest)
    for match in _ROUTE.finditer(rest):
        # Un seul blanc entre le verbe et le chemin, comme dans la clé.
        route = _BLANKS.sub(' ', _trimmed(match.group(0)))[:MAX_NAME]
        if route.rstrip('/'):
            keep(Candidate(NAME, route, route=True))
    rest = _ROUTE.sub(' ', rest)
    for match in _CODE.finditer(rest):
        token = match.group(0).rstrip('.')
        if _looks_like_code(token):
            keep(Candidate(NAME, token[:MAX_NAME]))
    return found


def resolve(searches):
    """L'ancre unique, ou les candidates : une seule référence en tout, et toutes les recherches épuisées."""
    references = tuple(dict.fromkeys(reference for search in searches for reference in search.references))
    if not references:
        status = AMBIGUOUS if any(not search.exhausted for search in searches) else NONE
        return Resolution(status, None, ())
    if len(references) == 1 and all(search.exhausted for search in searches):
        return Resolution(FOUND, references[0], references)
    return Resolution(AMBIGUOUS, None, references)
