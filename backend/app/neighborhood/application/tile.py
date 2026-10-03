"""Construire une Tuile (TAXO-01J) : l'enchaînement, sans règle de parcours ni format d'échange.

L'ancre est vérifiée, le parcours tourne sur l'adjacence de l'analyse, et la Tuile est refusée si les faits
ont changé pendant qu'elle se construisait : elle ne mélange jamais deux générations.
"""
from dataclasses import dataclass

from app.facts import is_reference
from app.neighborhood.domain.traversal import Traversal, unknown_root


class FactsChanged(Exception):
    """Des faits ont été ajoutés à l'analyse pendant le parcours."""


@dataclass(frozen=True)
class Built:
    """La Tuile, et la dernière Tuile provisoire que la jauge a admise : une Tuile plus courte, arrêtée par les
    octets, si la Tuile complète ne tient pas."""
    tile: object
    admitted: object


class _Adjacency:
    def __init__(self, facts, scan_id):
        self.facts, self.scan_id = facts, scan_id

    def read(self, anchor, step, after, limit):
        return self.facts.neighbors(self.scan_id, anchor, step.relation, step.direction, after, limit)


def _is_node(value):
    """Une extrémité est un nœud si c'est une référence du contrat des faits ; une valeur littérale n'en est pas."""
    return isinstance(value, str) and is_reference(value)


class BuildTile:
    def __init__(self, facts):
        self.facts = facts

    def __call__(self, scan_id, request, capable, gauge, start, revision) -> Built:
        if not self.facts.has_reference(scan_id, request.root):
            tile = unknown_root(request)
            built = Built(tile, tile)
        else:
            traversal = Traversal(request, _Adjacency(self.facts, scan_id), capable, gauge, _is_node, start)
            built = Built(traversal.run(), traversal.admitted)
        if self.facts.revision(scan_id) != revision:
            raise FactsChanged()
        return built
