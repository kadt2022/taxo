"""Le budget d'une enquete : par tranche, renouvelable sur demande justifiee, sous un plafond total
(recit TAXO-MINIA-ENQUETE-01, § 8).

Les plafonds de chaque operation du MIP restent ceux de Taxo ; ce budget borne l'enquete. Le renouvellement est
une action interne a Minia, pas une operation de la Maille. Minia controle **mecaniquement** la demande : branches
deja decouvertes, justification presente, progres depuis le dernier renouvellement, plafonds. Elle n'evalue jamais
la qualite d'une justification (INV-08).
"""
from dataclasses import dataclass, replace

from ..errors import BUDGET_EXHAUSTED, INVESTIGATION_INVALID, MiniaError

MAX_JUSTIFICATION_CHARS = 500


class Refusal:
    """Les raisons stables d'un renouvellement refuse."""
    SLICE_NOT_EXHAUSTED = 'SLICE_NOT_EXHAUSTED'
    NO_JUSTIFICATION = 'NO_JUSTIFICATION'
    NO_BRANCH = 'NO_BRANCH'
    UNKNOWN_BRANCH = 'UNKNOWN_BRANCH'
    NO_PROGRESS = 'NO_PROGRESS'
    TOTAL_EXHAUSTED = 'TOTAL_EXHAUSTED'
    TOO_MANY_RENEWALS = 'TOO_MANY_RENEWALS'
    INVALID_SIZE = 'INVALID_SIZE'


@dataclass(frozen=True)
class BudgetLimits:
    """Plafonds d'une tranche et de toute l'enquete. Les valeurs sont a calibrer par mesure ; aucune n'est
    illimitee."""
    slice_operations: int
    slice_bytes: int
    total_operations: int
    total_bytes: int
    max_renewals: int

    def __post_init__(self):
        values = (self.slice_operations, self.slice_bytes, self.total_operations, self.total_bytes)
        if (any(not isinstance(value, int) or value <= 0 for value in values)
                or not isinstance(self.max_renewals, int) or self.max_renewals < 0):
            raise MiniaError(INVESTIGATION_INVALID, 'Les plafonds d’une enquête doivent être des entiers positifs.')
        if self.slice_operations > self.total_operations or self.slice_bytes > self.total_bytes:
            raise MiniaError(INVESTIGATION_INVALID, 'Une tranche ne peut pas dépasser le plafond de l’enquête.')


@dataclass(frozen=True)
class RenewalRequest:
    """Ce que le modele demande pour poursuivre : des branches deja decouvertes, pourquoi, et combien
    d'operations (0 : une tranche entiere)."""
    branches: tuple
    justification: str
    operations: int = 0


@dataclass(frozen=True)
class RenewalDecision:
    granted: bool
    operations: int = 0
    refusal: str | None = None


@dataclass(frozen=True)
class Budget:
    limits: BudgetLimits
    slice_operations: int = 0
    slice_bytes: int = 0
    total_operations: int = 0
    total_bytes: int = 0
    # Operations accordees a la tranche en cours ; None pour la premiere : le plafond de tranche.
    granted_operations: int | None = None
    renewals: int = 0
    refusals: int = 0
    # Le dernier renouvellement accorde : ses branches et le progres du carnet a cet instant.
    last_renewal: tuple | None = None

    @property
    def granted(self) -> int:
        return self.limits.slice_operations if self.granted_operations is None else self.granted_operations

    @property
    def remaining_operations(self) -> int:
        if self.slice_bytes >= self.limits.slice_bytes or self.total_bytes >= self.limits.total_bytes:
            return 0
        return max(0, min(self.granted - self.slice_operations,
                          self.limits.total_operations - self.total_operations))

    @property
    def remaining_bytes(self) -> int:
        """Les octets qu'une reponse peut encore porter : ce qui reste a la tranche et au total, le plus petit."""
        return max(0, min(self.limits.slice_bytes - self.slice_bytes, self.limits.total_bytes - self.total_bytes))

    @property
    def slice_exhausted(self) -> bool:
        return self.remaining_operations == 0

    @property
    def total_exhausted(self) -> bool:
        return (self.total_operations >= self.limits.total_operations
                or self.total_bytes >= self.limits.total_bytes)

    def spend(self, response_bytes: int) -> 'Budget':
        """Une operation de plus, et la taille de ce qu'elle a transmis. Refusee si la tranche est epuisee : une
        operation ne part jamais au-dela du budget."""
        if response_bytes < 0:
            raise MiniaError(INVESTIGATION_INVALID, 'Une taille transmise ne peut pas être négative.')
        if self.slice_exhausted:
            raise MiniaError(BUDGET_EXHAUSTED, 'Le budget de cette tranche est épuisé : demandez un renouvellement '
                             'justifié ou concluez.')
        if response_bytes > self.remaining_bytes:
            raise MiniaError(BUDGET_EXHAUSTED, 'Cette réponse dépasse les octets qui restent au budget : elle n’est '
                             'pas comptée comme transmise.')
        return replace(self, slice_operations=self.slice_operations + 1,
                       slice_bytes=self.slice_bytes + response_bytes,
                       total_operations=self.total_operations + 1, total_bytes=self.total_bytes + response_bytes)

    def renew(self, request: RenewalRequest, open_branches, progress: int,
              min_bytes: int = 0) -> tuple['Budget', RenewalDecision]:
        """Une nouvelle tranche, si la demande passe les controles mecaniques ; sinon le budget compte un refus et
        la decision dit pourquoi. Aucune extension au-dela des plafonds de l'enquete. `min_bytes` : la plus petite
        reponse utile ; une tranche qui n'en a plus la place est epuisee, une enquete aussi."""
        refusal = self._refusal(request, set(open_branches), progress, min_bytes)
        if refusal is not None:
            return replace(self, refusals=self.refusals + 1), RenewalDecision(False, refusal=refusal)
        wanted = request.operations if request.operations > 0 else self.limits.slice_operations
        granted = min(wanted, self.limits.slice_operations, self.limits.total_operations - self.total_operations)
        renewed = replace(self, slice_operations=0, slice_bytes=0, granted_operations=granted,
                          renewals=self.renewals + 1, last_renewal=(tuple(sorted(request.branches)), progress))
        return renewed, RenewalDecision(True, granted)

    def _refusal(self, request, open_branches, progress, min_bytes):
        branches = tuple(item for item in request.branches if isinstance(item, str) and item)
        justification = request.justification.strip() if isinstance(request.justification, str) else ''
        if type(request.operations) is not int or request.operations < 0:
            return Refusal.INVALID_SIZE
        if not self.slice_exhausted and self.remaining_bytes >= min_bytes:
            return Refusal.SLICE_NOT_EXHAUSTED
        if self.total_exhausted or self.limits.total_bytes - self.total_bytes < min_bytes:
            return Refusal.TOTAL_EXHAUSTED
        if self.renewals >= self.limits.max_renewals:
            return Refusal.TOO_MANY_RENEWALS
        if not justification or len(justification) > MAX_JUSTIFICATION_CHARS:
            return Refusal.NO_JUSTIFICATION
        if not branches:
            return Refusal.NO_BRANCH
        if any(branch not in open_branches for branch in branches):
            return Refusal.UNKNOWN_BRANCH
        # Le progres se juge sur le carnet seul : nommer une autre branche ne vaut pas progres.
        if self.last_renewal is not None and self.last_renewal[1] == progress:
            return Refusal.NO_PROGRESS
        return None
