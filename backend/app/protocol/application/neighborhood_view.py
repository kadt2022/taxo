"""Présenter une Tuile dans l'enveloppe du protocole (ARCHITECTURE § 9.2, TAXO-01J § 8).

Le format seul : le parcours est décidé ailleurs. `neighborhood/1` garde sa forme d'origine, à l'octet ;
`neighborhood/2` y ajoute les nœuds détaillés, le chemin de chaque élément et une frontière par nœud.
La même présentation sert de jauge : une Tuile provisoire est mesurée telle qu'elle serait rendue, avec les
références qu'elle aurait, sans en créer aucune.
"""
from dataclasses import dataclass

from app.neighborhood.domain import handle
from app.neighborhood.domain.continuation import V1, V2
from app.neighborhood.domain.frontier import DEPTH, UNKNOWN
from app.protocol.application.neighborhood_request import SUMMARY
from app.protocol.domain.envelope import BUDGET, Response, size

COMPLETE, ROOT_UNKNOWN = 'ADJACENCY_COMPLETE', 'ROOT_UNKNOWN'
_SUMMARY_FIELDS = ('path', 'line_start', 'line_end', 'symbol', 'method')
# La place réservée pour compter des lacunes locales non transmises : un décompte à quatre chiffres.
_RESERVED = 9999


@dataclass(frozen=True)
class Enrichment:
    """Ce qui s'ajoute à une sélection déjà fixée, sans jamais la changer : les lacunes locales et les preuves
    résumées, chacune dans l'ordre, tant qu'elles tiennent. Ce qui n'a pas tenu est compté dans `not_sent`."""
    local: tuple = ()
    local_total: int = 0
    summaries: bool = False
    summarized: int = 0


def largest(count, fits):
    """Le plus grand préfixe (0 à `count`) qui tient, `fits` croissant avec la taille du préfixe."""
    low, high = 0, count
    while low < high:
        middle = (low + high + 1) // 2
        if fits(middle):
            low = middle
        else:
            high = middle - 1
    return low


class TileView:
    """Ce qui est commun aux deux versions : l'enveloppe, les références, la mesure."""

    version = None

    def __init__(self, exchange, demand, frontier, cursor, revision, max_bytes):
        self.exchange, self.demand, self.analysis = exchange, demand, frontier
        self.cursor, self.revision, self.max_bytes = cursor, revision, max_bytes
        self._keys = {}

    def baseline(self):
        """Ce que la jauge du parcours mesure : la Tuile sans rien d'ajouté, mais avec la place de dire ce qui
        n'aurait pas tenu. Une Tuile admise reste donc valable une fois enrichie de zéro ajout."""
        return Enrichment()

    def fits(self, tile, enrichment=None):
        return size(self.render(tile, enrichment or self.baseline()).close()) <= self.max_bytes

    def register(self, tile):
        """Les références de la Tuile rendue sont créées, dans l'ordre de ses éléments."""
        for element in tile.elements:
            self.exchange.refs.fact(element.adjacent.fact)

    def render(self, tile, enrichment=Enrichment()):
        refs = self.exchange.refs.preview([self._key(element) for element in tile.elements])
        stop_reason, continuation = self._stop(tile)
        request = tile.request
        response = Response('get_neighborhood', self.exchange.snapshot, self.analysis.coverage, self.max_bytes,
                            engine_version=self.version, parameters=self.demand.parameters,
                            facts_revision=self.revision, bounds=self._bounds(request),
                            consumed={'nodes': len(tile.nodes), 'edges': len(tile.elements), 'work': tile.work},
                            anchor={'reference': request.root, 'known': tile.known},
                            nodes=[node.reference for node in tile.nodes], **self._nodes(tile),
                            frontier=[*self.analysis.frontier, *self._selection(tile), *enrichment.local],
                            stop_reason=stop_reason, continuation=continuation)
        response.envelope['items'] = [self._item(element, ref, tile, enrichment, index)
                                      for index, (element, ref) in enumerate(zip(tile.elements, refs))]
        response.envelope['not_sent'] += _omitted(tile, enrichment)
        return response

    def _key(self, element):
        occurrence = element.adjacent.occurrence
        if occurrence not in self._keys:
            self._keys[occurrence] = self.exchange.refs.key(element.adjacent.fact)
        return self._keys[occurrence]

    def _bounds(self, request):
        limits = request.limits
        return {'max_nodes': limits.max_nodes, 'max_edges': limits.max_edges, 'max_work': limits.max_work,
                'max_bytes': self.max_bytes}

    def _stop(self, tile):
        if not tile.known:
            return ROOT_UNKNOWN, None
        if tile.stop is None:
            return COMPLETE, None
        return tile.stop.reason, self.cursor.encode(tile.stop.position)

    @staticmethod
    def _fact(element):
        fact = element.adjacent.fact
        return {'fact': {key: value for key, value in fact.items() if key != 'evidence'},
                'evidence_count': len(fact.get('evidence', []))}

    def _nodes(self, tile):
        raise NotImplementedError

    def _selection(self, tile):
        raise NotImplementedError

    def _item(self, element, ref, tile, enrichment, index):
        raise NotImplementedError


def _omitted(tile, enrichment):
    omitted = []
    if enrichment.local_total > len(enrichment.local):
        omitted.append({'what': 'local_coverage', 'count': enrichment.local_total - len(enrichment.local),
                        'reason': BUDGET})
    if enrichment.summaries and len(tile.elements) > enrichment.summarized:
        omitted.append({'what': 'evidence_summary', 'count': len(tile.elements) - enrichment.summarized,
                        'reason': BUDGET})
    return omitted


def summary(fact):
    """Les preuves d'un fait, résumées en localisations : jamais de contenu."""
    return [{name: proof[name] for name in _SUMMARY_FIELDS if name in proof} for proof in fact.get('evidence', [])]


class AnchorView(TileView):
    """`neighborhood/1` : le voisinage de l'ancre, dans sa forme d'origine."""

    version = V1

    def _nodes(self, tile):
        return {}

    def _selection(self, tile):
        boundaries = [{'nature': 'SELECTION', 'node': node.reference, 'reason': DEPTH, 'count': UNKNOWN}
                      for node in tile.nodes[1:]]
        if tile.known and tile.stop is not None:
            position = tile.stop.position
            boundaries.append({'nature': 'SELECTION', 'node': tile.request.root,
                               'relation': tile.request.steps[position.step].relation, 'reason': tile.stop.reason,
                               'count': tile.stop.count, 'continuation': self.cursor.encode(position)})
        return boundaries

    def _item(self, element, ref, tile, enrichment, index):
        return {'ref': ref, **self._fact(element)}


class LayeredView(TileView):
    """`neighborhood/2` : plusieurs niveaux, une frontière par nœud, le chemin de chaque élément."""

    version = V2

    def baseline(self):
        return Enrichment(local_total=_RESERVED, summaries=self.demand.evidence == SUMMARY)

    def _bounds(self, request):
        return {**super()._bounds(request), 'max_fanout': request.max_fanout}

    def _stop(self, tile):
        reason, continuation = super()._stop(tile)
        if reason != COMPLETE:
            return reason, continuation
        if tile.cuts:
            return tile.cuts[0].reason, None
        return (DEPTH, None) if tile.unexpanded() else (COMPLETE, None)

    def _nodes(self, tile):
        return {'node_details': [{'reference': node.reference, 'level': node.level, 'known': tile.known or index > 0,
                                  'expanded': node.expanded, 'parents': node.parents,
                                  'discovered_by': node.discovered_by}
                                 for index, node in enumerate(tile.nodes)]}

    def _selection(self, tile):
        depth, levels = tile.request.depth, {node.reference: node.level for node in tile.nodes}
        cuts = {cut.position.node: cut for cut in tile.cuts}
        if tile.known and tile.stop is not None:
            cuts[tile.stop.position.node] = tile.stop
        waiting = {node.reference: reason for node, reason in tile.unexpanded()} if tile.known else {}
        boundaries = []
        for node in tile.nodes:
            if node.reference in cuts:
                cut = cuts[node.reference]
                step = tile.request.steps[cut.position.step]
                boundaries.append({'nature': 'SELECTION', 'node': node.reference, 'relation': step.relation,
                                   'direction': step.direction, 'reason': cut.reason, 'count': cut.count,
                                   'remaining_depth': depth - levels[node.reference],
                                   'continuation': self.cursor.encode(cut.position)})
            elif node.reference in waiting:
                boundaries.append({'nature': 'SELECTION', 'node': node.reference, 'reason': waiting[node.reference],
                                   'count': UNKNOWN, 'remaining_depth': depth - node.level})
        return boundaries

    def _item(self, element, ref, tile, enrichment, index):
        step = tile.request.steps[element.step]
        item = {'ref': ref, **self._fact(element), 'identity': element.adjacent.identity,
                'occurrence': handle.encode(self.exchange.scan.id, self.revision, element.adjacent.occurrence),
                'via': {'from': element.origin, 'relation': step.relation, 'direction': step.direction},
                'level': element.level, 'revisit': element.revisit}
        if enrichment.summaries:
            item['evidence'] = summary(element.adjacent.fact) if index < enrichment.summarized else None
        return item
