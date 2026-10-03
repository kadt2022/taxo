"""Le cas d'usage `find_references` (TAXO-01J) : les références d'une analyse qui commencent par un préfixe.

Le préfixe suit la règle de comparaison du domaine ; la lecture est celle, bornée et indexée, du port.
"""
from typing import Protocol

from app.neighborhood.domain.references import fold


class ReferenceSearch(Protocol):
    def references(self, scan_id: str, prefix: str, kind: str | None, after: tuple | None,
                   limit: int) -> tuple[list[tuple], bool]:
        """Au plus `limit` (clé, empreinte, référence, type) après `after`, et s'il en reste."""


def find_references(search: ReferenceSearch, scan_id, prefix, kind, after, limit):
    """Une page de références, dans l'ordre de leur clé ; et s'il en reste."""
    return search.references(scan_id, fold(prefix), kind, after, limit)
