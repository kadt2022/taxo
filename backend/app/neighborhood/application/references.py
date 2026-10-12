"""Le cas d'usage `find_references` (TAXO-01J) : les références d'une analyse qui commencent par un préfixe ;
ou, en mode `NAME` (TAXO-01N, PR A2), celles qui se retrouvent sous un nom.

Le préfixe et le nom suivent les règles du domaine (`prefix_key`, `name_key`, qui refusent ce qui dépasserait
l'index) ; la lecture est celle, bornée et indexée, du port.
"""
from typing import Protocol

from app.neighborhood.domain.reference_names import CONTAINS, NAME, name_key
from app.neighborhood.domain.references import MAX_SCAN, prefix_key


class ReferenceSearch(Protocol):
    def references(self, scan_id: str, prefix: str, kind: str | None, after: tuple | None,
                   limit: int) -> tuple[list[tuple], bool]:
        """Au plus `limit` (clé, empreinte, référence, type) après `after`, et s'il en reste."""

    def containing(self, scan_id: str, text: str, kind: str, after: tuple | None, limit: int,
                   max_scan: int) -> tuple[list[tuple], bool, tuple | None]:
        """Au plus `limit` (clé, empreinte, référence, type) du type dont la clé contient `text` (déjà replié), après
        `after`, en lisant au plus `max_scan` références ; s'il en reste ; et, si la lecture s'est arrêtée à la borne, la
        (clé, empreinte) où reprendre (None sinon)."""

    def families(self, scan_id: str) -> list[tuple[str, int]]:
        """(type, nombre de références indexées) pour l'analyse, le plus nombreux d'abord ; vide si l'analyse n'a
        pas d'index."""

    def named(self, scan_id: str, name: str, kind: str | None, after: tuple | None,
              limit: int) -> tuple[list[tuple], bool] | None:
        """Au plus `limit` (nom, empreinte, référence, type) après `after`, et s'il en reste ; None si
        l'analyse n'a pas d'index des noms."""


def compared(prefix, match):
    """Le préfixe, ou le nom, tel qu'il se compare dans ce mode."""
    return name_key(prefix) if match == NAME else prefix_key(prefix)  # CONTAINS se replie comme un préfixe


def find_references(search: ReferenceSearch, scan_id, prefix, kind, after, limit, match=None):
    """Une page de références et s'il en reste : dans l'ordre de leur clé, ou de leur empreinte en mode `NAME`
    (None si l'analyse n'a pas d'index des noms)."""
    if match == CONTAINS:
        return search.containing(scan_id, prefix_key(prefix), kind, after, limit, MAX_SCAN)
    if match == NAME:
        return search.named(scan_id, name_key(prefix), kind, after, limit)
    return search.references(scan_id, prefix_key(prefix), kind, after, limit)
