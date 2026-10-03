"""Ce qu'une Tuile a consommé et ce qui lui reste. Un budget dit lequel refuse ; il ne choisit jamais."""
from app.neighborhood.domain.frontier import EDGES, NODES, WORK


class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.work = 0

    def before_read(self, elements):
        """Ce qui interdit une nouvelle lecture d'adjacence : le travail, puis les éléments."""
        if self.work >= self.limits.max_work:
            return WORK
        if elements >= self.limits.max_edges:
            return EDGES
        return None

    def refusal(self, elements, nodes, new_node):
        """Ce qui refuse un élément lu : les éléments, puis un nouveau nœud quand il n'y a plus de place."""
        if elements >= self.limits.max_edges:
            return EDGES
        if new_node and nodes >= self.limits.max_nodes:
            return NODES
        return None

    def read(self):
        self.work += 1

    def batch(self, elements, fanout_left, batched):
        """Combien d'occurrences lire d'un coup : une sans lots ; sinon ce qui peut encore être rendu, plus une
        pour savoir s'il en reste. Jamais toute l'adjacence d'un nœud à fort degré."""
        if not batched:
            return 1
        room = self.limits.max_edges - elements
        if fanout_left is not None:
            room = min(room, fanout_left)
        return room + 1
