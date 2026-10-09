"""Ce dont une Tuile a besoin, et rien d'autre : lire l'adjacence d'une analyse, et ce que son résumé dit d'elle."""
from typing import Protocol

from app.neighborhood.domain.traversal import Adjacent


class AdjacencyReading(Protocol):
    def revision(self, scan_id: str) -> int:
        """La génération des faits de l'analyse."""

    def has_reference(self, scan_id: str, root: str) -> bool:
        """Une assertion de l'analyse nomme-t-elle cette référence ?"""

    def neighbors(self, scan_id: str, root: str, relation: str, direction: str, after: str,
                  limit: int) -> list[Adjacent]:
        """Au plus `limit` occurrences adjacentes, dans l'ordre des rangs, strictement après `after` : une
        lecture indexée, jamais toute l'adjacence."""


class CoverageReading(Protocol):
    def unread(self, scan_id: str, references: list[str]) -> list[dict]:
        """Les couvertures non lues (NOT_INTERPRETED, READ_ERROR) dont le sujet est l'une de ces références :
        `subject`, `coverage_type`, `producer`, et `reasons`, les raisons fermees de son `diagnostic` (vide sans
        diagnostic), et `categories`, ses decomptes par categorie (None sans classification, TAXO-01M). Une
        lecture par l'ancre du sujet, jamais un parcours."""


class AnalysisSummary(Protocol):
    """Ce que le résumé d'une analyse dit de ses analyseurs, sans parcourir ses faits."""

    evaluations: list
    catalogs: dict
    languages: tuple
    result: dict

    def summary_analyzers(self):
        """Les analyseurs tels que le résumé les décrit (`app.knowledge`)."""
