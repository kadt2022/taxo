"""Présenter une Tuile dans l'enveloppe du protocole (ARCHITECTURE § 9.2, TAXO-01J § 8).

Le format seul : le parcours est décidé ailleurs. `neighborhood/1` garde sa forme d'origine, à l'octet ;
`neighborhood/2` y ajoute les nœuds détaillés, le chemin de chaque élément et une frontière par nœud.
La même présentation sert de jauge : une Tuile provisoire est mesurée telle qu'elle serait rendue, avec les
références qu'elle aurait, sans en créer aucune.
"""
from app.neighborhood.domain.continuation import V1, V2
from app.neighborhood.domain.frontier import DEPTH, UNKNOWN
from app.protocol.domain.envelope import Response, size

COMPLETE, ROOT_UNKNOWN = 'ADJACENCY_COMPLETE', 'ROOT_UNKNOWN'


class TileView:
    """Ce qui est commun aux deux versions : l'enveloppe, les références, la mesure."""

    version = None

    def __init__(self, exchange, demand, frontier, cursor, revision, max_bytes):
        self.exchange, self.demand, self.analysis = exchange, demand, frontier
        self.cursor, self.revision, self.max_bytes = cursor, revision, max_bytes
        self._keys = {}

    def fits(self, tile):
        return size(self.render(tile).close()) <= self.max_bytes

    def register(self, tile):
        """Les références de la Tuile rendue sont créées, dans l'ordre de ses éléments."""
        for element in tile.elements:
            self.exchange.refs.fact(element.adjacent.fact)

    def render(self, tile):
        refs = self.exchange.refs.preview([self._key(element) for element in tile.elements])
        stop_reason, continuation = self._stop(tile)
        request = tile.request
        response = Response('get_neighborhood', self.exchange.snapshot, self.analysis.coverage, self.max_bytes,
                            engine_version=self.version, parameters=self.demand.parameters,
                            facts_revision=self.revision, bounds=self._bounds(request),
                            consumed={'nodes': len(tile.nodes), 'edges': len(tile.elements), 'work': tile.work},
                            anchor={'reference': request.root, 'known': tile.known},
                            nodes=[node.reference for node in tile.nodes], **self._nodes(tile),
                            frontier=[*self.analysis.frontier, *self._selection(tile)], stop_reason=stop_reason,
                            continuation=continuation)
        response.envelope['items'] = [self._item(element, ref, tile) for element, ref in zip(tile.elements, refs)]
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
        return {}

    def _selection(self, tile):
        raise NotImplementedError

    def _item(self, element, ref, tile):
        raise NotImplementedError


class AnchorView(TileView):
    """`neighborhood/1` : le voisinage de l'ancre, dans sa forme d'origine."""

    version = V1

    def _selection(self, tile):
        boundaries = [{'nature': 'SELECTION', 'node': node.reference, 'reason': DEPTH, 'count': UNKNOWN}
                      for node in tile.nodes[1:]]
        if tile.known and tile.stop is not None:
            position = tile.stop.position
            boundaries.append({'nature': 'SELECTION', 'node': tile.request.root,
                               'relation': tile.request.steps[position.step].relation, 'reason': tile.stop.reason,
                               'count': tile.stop.count, 'continuation': self.cursor.encode(position)})
        return boundaries

    def _item(self, element, ref, tile):
        return {'ref': ref, **self._fact(element)}


class LayeredView(TileView):
    """`neighborhood/2` : plusieurs niveaux, une frontière par nœud, le chemin de chaque élément."""

    version = V2

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
        waiting = dict((node.reference, reason) for node, reason in tile.unexpanded()) if tile.known else {}
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

    def _item(self, element, ref, tile):
        step = tile.request.steps[element.step]
        return {'ref': ref, **self._fact(element), 'identity': element.adjacent.identity,
                'via': {'from': element.origin, 'relation': step.relation, 'direction': step.direction},
                'level': element.level, 'revisit': element.revisit}
