"""Le port de memoire des enquetes : la seule facon de conserver un carnet (recit TAXO-MINIA-ENQUETE-01, § 6.3).

Une seule interface, un seul adaptateur initial (SQLite en mode WAL, lot B) : pas d'abstraction multi-stockage,
pas de seconde Maille. Le port garde un etat de navigation, jamais un resultat de Taxo (INV-09, INV-10).
"""
from datetime import datetime
from typing import Protocol

from .identity import OwnerScope, Status
from .state import InvestigationState


class ParcoursMemoryStore(Protocol):
    def create(self, state: InvestigationState) -> InvestigationState:
        """Enregistre une enquete nouvelle et ses evenements en attente ; rend l'etat a la revision 1.
        MiniaError(INVESTIGATION_CONFLICT) si l'identifiant existe deja."""

    def load(self, investigation_id: str, scope: OwnerScope) -> InvestigationState:
        """L'etat enregistre, si le perimetre est celui de l'enquete. MiniaError(INVESTIGATION_NOT_FOUND) sinon,
        sans dire si l'enquete existe dans un autre perimetre."""

    def commit(self, investigation_id: str, expected_revision: int,
               new_state: InvestigationState) -> InvestigationState:
        """Ecrit le nouvel etat et ses evenements en attente dans la meme transaction, si la revision enregistree
        est `expected_revision` ; rend l'etat a la revision suivante, sans evenement en attente.
        MiniaError(INVESTIGATION_CONFLICT) si une autre ecriture est passee entre-temps : rien n'est ecrit."""

    def mark_status(self, investigation_id: str, scope: OwnerScope, status: Status, expected_revision: int,
                    at: datetime) -> InvestigationState:
        """Change l'etat de l'enquete (pause, fin, generation remplacee), sous le meme controle de revision."""

    def expire(self, now: datetime, limit: int) -> int:
        """Marque expirees au plus `limit` enquetes dont l'echeance (`expires_at`) est passee a `now` ; rend leur
        nombre. Le volume est borne pour un nettoyage opportuniste ; une enquete echue est refusee a la reprise
        meme avant ce nettoyage."""
