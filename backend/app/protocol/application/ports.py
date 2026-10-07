"""Ce que le protocole lit des faits d'une analyse (TAXO-ARCH-REF-01, tranche B) : un port declare.

Le protocole, le voisinage et le chargeur de connaissance lisent les faits par ces seules methodes, toutes en
lecture et bornees par l'analyse. Aucune n'ecrit ; aucune ne relit le depot.
"""
from typing import Protocol

from app.facts.domain.provenance import ProducerExecution
from app.neighborhood.domain.traversal import Adjacent


class FactReading(Protocol):
    def query(self, scan_id: str, **filters) -> list[dict]:
        """Les faits de l'analyse qui repondent aux filtres (sujet, relation, objet, nature, evaluateur)."""

    def objects(self, scan_id: str, relation: str) -> list[str]:
        """Les objets distincts d'une relation, tries, sans reconstruire aucun fait."""

    def executions(self, scan_id: str) -> list[ProducerExecution]:
        """Les executions enregistrees de l'analyse : une ligne chacune, aucun fait."""

    def revision(self, scan_id: str) -> int:
        """La generation des faits de l'analyse : elle ne change plus une fois l'analyse complete."""

    def has_reference(self, scan_id: str, root: str) -> bool:
        """Une assertion de l'analyse nomme-t-elle cette reference ?"""

    def neighbors(self, scan_id: str, root: str, relation: str, direction: str, after: str,
                  limit: int) -> list[Adjacent]:
        """Au plus `limit` occurrences adjacentes de `root` pour une relation et un sens, apres `after`, dans
        l'ordre des rangs : une lecture indexee, jamais toute l'adjacence (TAXO-01J)."""

    def occurrence(self, scan_id: str, key: str) -> dict | None:
        """Le fait d'une occurrence de l'analyse, par sa cle stable (celle que rend `neighbors`) ; None si
        l'analyse n'en a pas de telle (TAXO-01J)."""

    def unread(self, scan_id: str, references: list[str]) -> list[dict]:
        """Les couvertures de l'analyse qui disent qu'une de ces references n'a pas ete lue (`subject`,
        `coverage_type`, `producer`, `reasons` de son `diagnostic`) : une lecture par l'ancre du sujet, jamais un
        parcours (TAXO-01J)."""
