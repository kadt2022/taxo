"""Ce que demande une Tuile (TAXO-01J) : une ancre, des pas, une profondeur, des budgets.

Deux familles de paramètres, qui n'ont pas la même propriété (récit TAXO-01J, § 4) :

- la **forme** (ancre, pas, profondeur, éventail) définit la séquence canonique des éléments ;
- les **budgets globaux** (nœuds, éléments, travail, octets) ne décident que de l'endroit où elle s'arrête.
"""
from dataclasses import dataclass

OUTGOING, INCOMING = 'OUTGOING', 'INCOMING'
DIRECTIONS = (OUTGOING, INCOMING)


@dataclass(frozen=True)
class Step:
    """Un pas du parcours : une relation suivie dans un sens. Le sens dit de quel côté du fait on part."""
    relation: str
    direction: str

    def __post_init__(self):
        if self.direction not in DIRECTIONS:
            raise ValueError(f'Sens inconnu : {self.direction}.')

    def far_end(self, fact):
        """L'extrémité atteinte : l'objet en sortant, le sujet en entrant. Le fait garde son orientation."""
        return fact.get('object') if self.direction == OUTGOING else fact.get('subject')


@dataclass(frozen=True)
class Limits:
    """Les budgets globaux d'une Tuile. Ils ne changent jamais la séquence canonique."""
    max_nodes: int
    max_edges: int
    max_work: int


@dataclass(frozen=True)
class TileRequest:
    """Une Tuile demandée. `batched` : l'adjacence se lit par lots (`neighborhood/2`) ou une occurrence à la
    fois (`neighborhood/1`, dont chaque lecture compte pour un travail)."""
    root: str
    steps: tuple
    depth: int
    limits: Limits
    max_fanout: int | None = None
    batched: bool = True

    def __post_init__(self):
        if not self.steps or len(set(self.steps)) != len(self.steps):
            raise ValueError('Des pas distincts, au moins un.')
        if self.depth < 1:
            raise ValueError('Une profondeur d’au moins 1.')
        if self.max_fanout is not None and self.max_fanout < 1:
            raise ValueError('Un éventail d’au moins 1.')

    @property
    def relations(self):
        """Les relations suivies, chacune une fois, dans l'ordre de priorité des pas."""
        return tuple(dict.fromkeys(step.relation for step in self.steps))
