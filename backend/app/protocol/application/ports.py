"""Ce que le protocole lit des faits d'une analyse (TAXO-ARCH-REF-01, tranche B) : un port declare.

Le protocole, le voisinage et le chargeur de connaissance lisent les faits par ces seules methodes, toutes en
lecture et bornees par l'analyse. Aucune n'ecrit ; aucune ne relit le depot.
"""
from typing import Protocol

from app.facts.domain.provenance import ProducerExecution


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

    def neighbor(self, scan_id: str, root: str, relation: str, direction: str,
                 after: str = '') -> tuple[str, dict] | None:
        """Le fait adjacent suivant de `root` pour une relation et une direction, apres `after`."""
