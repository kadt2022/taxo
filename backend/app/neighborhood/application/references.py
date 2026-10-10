"""Le cas d'usage `find_references` (TAXO-01J) : les références d'une analyse qui commencent par un préfixe ;
ou, en mode `NAME` (TAXO-01N, PR A2), celles qui se retrouvent sous un nom.

Le préfixe et le nom suivent les règles du domaine (`prefix_key`, `name_key`, qui refusent ce qui dépasserait
l'index) ; la lecture est celle, bornée et indexée, du port.
"""
from typing import Protocol

from app.neighborhood.domain.reference_names import NAME, name_key
from app.neighborhood.domain.references import prefix_key


class ReferenceSearch(Protocol):
    def references(self, scan_id: str, prefix: str, kind: str | None, after: tuple | None,
                   limit: int) -> tuple[list[tuple], bool]:
        """Au plus `limit` (clé, empreinte, référence, type) après `after`, et s'il en reste."""

    def named(self, scan_id: str, name: str, kind: str | None, after: tuple | None,
              limit: int) -> tuple[list[tuple], bool] | None:
        """Au plus `limit` (nom, empreinte, référence, type) après `after`, et s'il en reste ; None si
        l'analyse n'a pas d'index des noms."""


def compared(prefix, match):
    """Le préfixe, ou le nom, tel qu'il se compare dans ce mode."""
    return name_key(prefix) if match == NAME else prefix_key(prefix)


def find_references(search: ReferenceSearch, scan_id, prefix, kind, after, limit, match=None):
    """Une page de références et s'il en reste : dans l'ordre de leur clé, ou de leur empreinte en mode `NAME`
    (None si l'analyse n'a pas d'index des noms)."""
    if match == NAME:
        return search.named(scan_id, name_key(prefix), kind, after, limit)
    return search.references(scan_id, prefix_key(prefix), kind, after, limit)
