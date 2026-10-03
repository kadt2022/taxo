"""Où une Tuile s'arrête, et ce qu'elle sait de ce qu'elle ne montre pas (ARCHITECTURE § 9.3).

Une coupure de sélection se reprend ; un décompte n'est jamais inventé : « au moins un » seulement si une
occurrence non rendue a effectivement été lue, « inconnu » sinon.
"""
from dataclasses import dataclass

NODES, EDGES, WORK, BYTES, FANOUT = 'NODES', 'EDGES', 'WORK', 'BYTES', 'FANOUT'
DEPTH, NOT_REACHED = 'DEPTH', 'NOT_REACHED'
UNKNOWN = {'kind': 'UNKNOWN'}
AT_LEAST_ONE = {'kind': 'AT_LEAST', 'value': 1}


@dataclass(frozen=True)
class Position:
    """Où reprendre l'adjacence d'un nœud : l'indice du pas et la clé de la dernière occurrence examinée."""
    node: str
    step: int
    after: str = ''


@dataclass(frozen=True)
class Cut:
    """Une adjacence coupée par un budget, au milieu de ses occurrences ou avant elles."""
    position: Position
    reason: str
    found: bool

    @property
    def count(self):
        return AT_LEAST_ONE if self.found else UNKNOWN
