"""Le parcours d'une Tuile : en largeur, borné, déterministe (ARCHITECTURE § 9.4, TAXO-01J).

Niveau par niveau, chaque nœud est développé pas après pas, chaque pas dans l'ordre stable de son adjacence.
Un nœud n'apparaît qu'une fois ; un élément vers un nœud déjà présent est rendu et marqué, jamais redéveloppé.
Chaque occurrence est un élément à part entière : deux occurrences d'une même identité restent deux éléments ;
une même occurrence atteinte par deux pas n'est rendue qu'une fois.

Quand un budget global refuse un élément, le parcours s'arrête là : il ne saute jamais un élément pour en
accepter un suivant. Le parcours ne lit que par le port `Adjacency`, ne connaît la taille d'une réponse que
par une jauge, et ne sait d'une extrémité qu'elle est un nœud que par le contrat des faits qu'on lui donne
(`is_node`) : il ne sait rien du stockage, du format d'échange ni de la validation des faits.
"""
from collections import deque
from dataclasses import dataclass
from typing import Callable, Protocol

from app.neighborhood.domain.budget import Budget
from app.neighborhood.domain.frontier import BYTES, DEPTH, FANOUT, NOT_REACHED, WORK, Cut, Position
from app.neighborhood.domain.request import Step, TileRequest


# Le nœud en cours est coupé par son éventail : le parcours passe au suivant.
_NEXT_NODE = object()


class EnvelopeTooLarge(Exception):
    """L'enveloppe minimale de la Tuile ne tient pas dans le budget d'octets."""


@dataclass(frozen=True)
class Adjacent:
    """Une occurrence lue dans l'adjacence d'un nœud. `key` : son rang dans cette adjacence ; `occurrence` et
    `identity` : ses clés stables dans l'analyse."""
    key: str
    occurrence: str
    identity: str
    fact: dict


class Adjacency(Protocol):
    def read(self, anchor: str, step: Step, after: str, limit: int) -> list[Adjacent]:
        """Au plus `limit` occurrences de l'adjacence de `anchor` pour ce pas, strictement après `after`."""


@dataclass(frozen=True)
class Element:
    """Une occurrence rendue : par quel pas, depuis quel nœud, à quel niveau, et si elle rejoint un nœud déjà
    présent."""
    adjacent: Adjacent
    step: int
    origin: str
    level: int
    revisit: bool


@dataclass(frozen=True)
class NodeView:
    reference: str
    level: int
    discovered_by: int | None
    parents: int
    expanded: bool


@dataclass(frozen=True)
class Tile:
    """Une Tuile, ou l'état provisoire qu'une jauge mesure. `stop` : la coupure qui a arrêté tout le parcours ;
    `cuts` : les coupures d'éventail, après lesquelles le parcours a continué."""
    request: TileRequest
    known: bool
    nodes: tuple = ()
    elements: tuple = ()
    work: int = 0
    stop: Cut | None = None
    cuts: tuple = ()

    def unexpanded(self):
        """Les nœuds ni développés ni coupés, et pourquoi : la profondeur, ou un arrêt avant eux."""
        cut = {item.position.node for item in self.cuts}
        if self.stop is not None:
            cut.add(self.stop.position.node)
        return [(node, DEPTH if node.level >= self.request.depth else NOT_REACHED)
                for node in self.nodes if not node.expanded and node.reference not in cut]


@dataclass
class _Node:
    reference: str
    level: int
    discovered_by: int | None
    parents: int = 0
    expanded: bool = False


@dataclass
class _Expansion:
    """Le développement en cours d'un nœud : où il en est, et combien d'éléments il a rendus."""
    node: _Node
    step: int = 0
    after: str = ''
    rendered: int = 0

    def position(self, after=None):
        return Position(self.node.reference, self.step, self.after if after is None else after)


class Traversal:
    def __init__(self, request: TileRequest, adjacency: Adjacency, capable, gauge: Callable[[Tile], bool],
                 is_node: Callable[[object], bool], start: Position | None = None):
        self.request, self.adjacency, self.capable, self.gauge = request, adjacency, frozenset(capable), gauge
        self.is_node = is_node
        self.budget = Budget(request.limits)
        self.start = start or Position(request.root, 0)
        self.nodes = {request.root: _Node(request.root, 0, None)}
        self.elements, self.rendered, self.cuts = [], set(), []
        self.queue = deque([request.root])
        # La dernière Tuile provisoire que la jauge a admise : arrêtée par les octets juste après le dernier
        # élément rendu. Si la Tuile finale ne tenait pas, c'est la plus grande qui tient.
        self.admitted = None

    def run(self) -> Tile:
        if not self.gauge(self.tile(Cut(self.start, WORK, False))):
            raise EnvelopeTooLarge()
        self.admitted = self.tile(Cut(self.start, BYTES, False))
        resumed = _Expansion(self.nodes[self.request.root], self.start.step, self.start.after)
        while self.queue:
            node = self.nodes[self.queue.popleft()]
            expansion = resumed if node.reference == self.request.root else _Expansion(node)
            stop = self._expand(expansion)
            if stop is not None:
                return self.tile(stop)
        return self.tile(None)

    def tile(self, stop=None) -> Tile:
        nodes = tuple(NodeView(node.reference, node.level, node.discovered_by, node.parents, node.expanded)
                      for node in self.nodes.values())
        return Tile(self.request, True, nodes, tuple(self.elements), self.budget.work, stop, tuple(self.cuts))

    def _expand(self, expansion):
        """Développe un nœud ; rend la coupure qui arrête toute la Tuile, ou None."""
        steps = self.request.steps
        while expansion.step < len(steps):
            outcome = self._walk_step(expansion, steps[expansion.step])
            if outcome is _NEXT_NODE:
                return None
            if outcome is not None:
                return outcome
            expansion.step, expansion.after = expansion.step + 1, ''
        expansion.node.expanded = True
        return None

    def _walk_step(self, expansion, step):
        """Parcourt un pas d'un nœud : None quand son adjacence est épuisée, `_NEXT_NODE` quand l'éventail du
        nœud est plein (le parcours continue), sinon la coupure qui arrête la Tuile."""
        fanout = self.request.max_fanout
        while True:
            refusal = self.budget.before_read(len(self.elements))
            if refusal is not None:
                return Cut(expansion.position(), refusal, False)
            if step.relation not in self.capable:
                return None
            left = None if fanout is None else fanout - expansion.rendered
            if left == 0:
                self.cuts.append(Cut(expansion.position(), FANOUT, False))
                return _NEXT_NODE
            limit = self.budget.batch(len(self.elements), left, self.request.batched)
            self.budget.read()
            batch = self.adjacency.read(expansion.node.reference, step, expansion.after, limit)
            for adjacent in batch:
                outcome = self._offer(expansion, step, adjacent)
                if outcome is not None:
                    return outcome
            if len(batch) < limit:
                return None

    def _offer(self, expansion, step, adjacent):
        """Propose une occurrence lue : rendue, ignorée (déjà rendue), ou refusée par un budget."""
        if adjacent.occurrence in self.rendered:
            expansion.after = adjacent.key
            return None
        fanout = self.request.max_fanout
        if fanout is not None and expansion.rendered >= fanout:
            self.cuts.append(Cut(expansion.position(), FANOUT, True))
            return _NEXT_NODE
        far = step.far_end(adjacent.fact)
        reached = self.is_node(far)
        new = reached and far not in self.nodes
        refusal = self.budget.refusal(len(self.elements), len(self.nodes), new)
        if refusal is not None:
            return Cut(expansion.position(), refusal, True)
        node = expansion.node
        self._add(Element(adjacent, expansion.step, node.reference, node.level + 1, reached and not new),
                  far if reached else None, new)
        probe = self.tile(Cut(expansion.position(adjacent.key), BYTES, False))
        if not self.gauge(probe):
            self._remove_last(far if reached else None, new)
            return Cut(expansion.position(), BYTES, True)
        self.admitted = probe
        expansion.after, expansion.rendered = adjacent.key, expansion.rendered + 1
        return None

    def _add(self, element, far, new):
        self.elements.append(element)
        self.rendered.add(element.adjacent.occurrence)
        if new:
            self.nodes[far] = _Node(far, element.level, len(self.elements) - 1, 1)
            if element.level < self.request.depth:
                self.queue.append(far)
        elif far is not None:
            self.nodes[far].parents += 1

    def _remove_last(self, far, new):
        element = self.elements.pop()
        self.rendered.discard(element.adjacent.occurrence)
        if new:
            del self.nodes[far]
            if self.queue and self.queue[-1] == far:
                self.queue.pop()
        elif far is not None:
            self.nodes[far].parents -= 1


def unknown_root(request: TileRequest) -> Tile:
    """Une ancre que l'analyse ne nomme pas : aucune lecture, aucun nœud développé."""
    return Tile(request, False, (NodeView(request.root, 0, None, 0, False),))
