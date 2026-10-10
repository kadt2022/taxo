"""Le repli paquet hors Git (récit TAXO-01N / MIP-01 § 5.3) : une ancre explicite, puis sa Tuile MIP.

Sans modèle : Taxo cherche les ancres de la question (`anchors.candidates`) par `find_references`, page après page
jusqu'à l'épuisement ou la limite, et ne retient qu'une ancre unique. Sa Tuile est demandée au service MIP
(`EXPAND`, profondeur 1, dans les deux sens), sur les relations que l'analyse contient ; plus de 16 relations font
plusieurs Tuiles, jamais une Tuile élargie. Chaque opération est montrée dans la trajectoire.
"""
from dataclasses import dataclass

from app.minia.domain import anchors
from app.minia.domain.cancellation import check

MAX_PAGES = 3
PAGE = 20
MAX_RELATIONS = 16
TILE_BOUNDS = {'depth': 1, 'max_nodes': 30, 'max_facts': 60}
# Le paquet d'une ancre ne prend jamais plus que ce budget, quelle que soit la place du modèle.
MAX_TILE_BYTES = 16_000
OK, ERROR = 'OK', 'ERROR'


@dataclass(frozen=True)
class Anchored:
    """Ce que le repli a trouvé : la résolution des ancres, et les Tuiles de l'ancre unique."""
    resolution: anchors.Resolution
    tiles: tuple
    refused: str | None = None


def _step(operation, arguments, response):
    entry = {'operation': operation, 'arguments': arguments, 'outcome': response['outcome']}
    if response['outcome'] == OK:
        entry.update(items=len(response.get('items', response.get('facts', []))),
                     not_sent=response.get('not_sent', []))
    else:
        entry['error'] = response['error']
    return entry


def _search(exchange, candidate, trajectory, cancel):
    """Les références d'une ancre, page après page ; une référence complète n'est retenue qu'à l'identique."""
    found, after = [], {}
    for _ in range(MAX_PAGES):
        arguments = {'analysis': exchange.snapshot['analysis'], **candidate.search, 'limit': PAGE, **after}
        check(cancel)
        response = exchange.call({'operation': 'find_references', 'arguments': arguments})
        trajectory.append(_step('find_references', arguments, response))
        yield 'minia.operation', trajectory[-1]
        if response['outcome'] != OK:
            # Un argument refusé (un type inconnu) ne nomme rien ; tout autre refus (index des noms absent,
            # budget épuisé) laisse la recherche inachevée : rien n'est conclu.
            return anchors.Search(candidate, (), response['error']['code'] == 'INVALID_ARGUMENT')
        references = [item['reference'] for item in response['items']]
        if candidate.mode == anchors.KEY:
            if candidate.text in references:
                return anchors.Search(candidate, (candidate.text,), True)
        else:
            found.extend(references)
        if response['next'] is None and not response['not_sent']:
            return anchors.Search(candidate, tuple(found), True)
        after = {'after': response['next']} if response['next'] else {}
        if not after:
            break
    return anchors.Search(candidate, tuple(found), False)


def _relations(exchange):
    """Les relations que l'analyse contient, telles que `describe` les annonce."""
    described = exchange.call({'operation': 'describe'})
    if described['outcome'] != OK:
        return []
    return [item['relation'] for item in described['items'] if item.get('kind') == 'relation' and item.get('count')]


def drained(steps):
    """La valeur rendue par des étapes dont on ne montre pas les événements."""
    while True:
        try:
            next(steps)
        except StopIteration as end:
            return end.value


def locate(exchange, question, trajectory, cancel=None):
    """Les ancres explicites de la question, cherchées dans l'analyse de l'échange. Rend `anchors.Resolution`."""
    searches = []
    for candidate in anchors.candidates(question):
        searches.append((yield from _search(exchange, candidate, trajectory, cancel)))
    return anchors.resolve(searches)


def anchor(exchange, mip, project_id, question, trajectory, max_bytes, cancel=None):
    """Cherche l'ancre de la question ; si elle est unique, ses Tuiles MIP. Rend `Anchored`."""
    resolution = yield from locate(exchange, question, trajectory, cancel)
    if resolution.status != anchors.FOUND:
        return Anchored(resolution, ())
    relations = _relations(exchange)
    groups = [relations[start:start + MAX_RELATIONS] for start in range(0, len(relations), MAX_RELATIONS)]
    room = MAX_TILE_BYTES if max_bytes is None else min(max_bytes, MAX_TILE_BYTES)
    budget = max(room // max(len(groups), 1), 1)
    tiles = []
    for group in groups:
        query = {'expression': 'EXPAND', 'target': {'reference': resolution.anchor}, 'relations': group,
                 'direction': 'BOTH', 'analysis': exchange.snapshot['analysis'],
                 'bounds': {**TILE_BOUNDS, 'max_bytes': budget}}
        check(cancel)
        tile = mip.query(project_id, query)
        trajectory.append(_step('mip:EXPAND', {'reference': resolution.anchor, 'relations': group}, tile))
        yield 'minia.operation', trajectory[-1]
        if tile['outcome'] != OK:
            return Anchored(resolution, tuple(tiles), tile['error']['message'])
        tiles.append(tile)
    return Anchored(resolution, tuple(tiles))
