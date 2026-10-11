"""L'identite d'une enquete de Minia : a qui elle appartient, sur quel instantane, dans quel etat
(recit TAXO-MINIA-ENQUETE-01, § 6.1).

Une enquete est liee a une analyse **et** a une generation de ses faits : deux generations sur le meme commit ne
sont pas interchangeables (INV-05). Elle n'est reprenable que si l'utilisateur a confirme une version minimisee de
sa question, et seule cette version est conservee : Minia ne juge jamais qu'une reformulation garde le sens de la
question d'origine (INV-04, AC-20).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Callable

from ..errors import (INVESTIGATION_EXPIRED, INVESTIGATION_INVALID, INVESTIGATION_NOT_FOUND,
                      INVESTIGATION_NOT_RESUMABLE, INVESTIGATION_STALE, MiniaError)
from .values import changed

# Une question minimisee est courte : elle sert a reprendre, pas a archiver un echange.
MAX_QUESTION_CHARS = 500

# Le controle de confidentialite d'un texte avant persistance : rend le texte a conserver, ou leve
# MiniaError(CONFIDENTIALITY_REFUSED). Fourni par l'application (la protection existante de Minia).
TextGuard = Callable[[str], str]


class Status(StrEnum):
    ACTIVE = 'ACTIVE'
    PAUSED = 'PAUSED'
    COMPLETE = 'COMPLETE'
    EXPIRED = 'EXPIRED'
    STALE = 'STALE'


# Les changements d'etat permis. EXPIRED est definitif ; STALE ne garde qu'une lecture historique.
_TRANSITIONS = {
    Status.ACTIVE: {Status.PAUSED, Status.COMPLETE, Status.EXPIRED, Status.STALE},
    Status.PAUSED: {Status.ACTIVE, Status.COMPLETE, Status.EXPIRED, Status.STALE},
    Status.COMPLETE: {Status.EXPIRED, Status.STALE},
    Status.STALE: {Status.EXPIRED},
    Status.EXPIRED: set(),
}
# Une enquete dans ces etats ne recoit plus d'operation, de note ni de budget.
WRITABLE = frozenset({Status.ACTIVE})


@dataclass(frozen=True)
class Snapshot:
    """L'instantane interroge : l'analyse, la generation de ses faits et, s'il existe, le commit."""
    analysis_id: str
    generation_id: int
    commit_id: str | None = None

    def __post_init__(self):
        if not self.analysis_id or not isinstance(self.generation_id, int) or self.generation_id < 0:
            raise MiniaError(INVESTIGATION_INVALID, 'Une enquête exige une analyse et une génération de ses faits.')


@dataclass(frozen=True)
class OwnerScope:
    """Le perimetre d'acces deja autorise : un proprietaire et un projet. Aucune lecture hors de ce perimetre."""
    owner: str
    project_id: str

    def __post_init__(self):
        if not self.owner or not self.project_id:
            raise MiniaError(INVESTIGATION_INVALID, 'Une enquête exige un propriétaire et un projet.')


@dataclass(frozen=True)
class ExpiryPolicy:
    """Duree d'inactivite apres laquelle une enquete persistee n'est plus restituee. Configurable, jamais figee
    par le recit ; aucune duree propre a la memoire vive, qui ne survit pas a la session."""
    inactivity: timedelta

    def __post_init__(self):
        if self.inactivity <= timedelta(0):
            raise MiniaError(INVESTIGATION_INVALID, 'La durée d’inactivité d’une enquête doit être positive.')
        if self.inactivity.microseconds:
            # Conservee en secondes entieres : une fraction serait perdue a la relecture.
            raise MiniaError(INVESTIGATION_INVALID, 'La durée d’inactivité d’une enquête se compte en secondes '
                             'entières.')

    def expires_at(self, last_activity: datetime) -> datetime:
        return last_activity + self.inactivity


@dataclass(frozen=True)
class Investigation:
    investigation_id: str
    scope: OwnerScope
    snapshot: Snapshot
    status: Status
    revision: int
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    # La seule question conservee : la version minimisee confirmee par l'utilisateur. None : non reprenable.
    confirmed_question: str | None = None

    @property
    def resumable(self) -> bool:
        return self.confirmed_question is not None

    def expired(self, now: datetime) -> bool:
        return self.status is Status.EXPIRED or self.expires_at <= now

    def touched(self, at: datetime, policy: ExpiryPolicy) -> 'Investigation':
        # Un resultat inscrit en retard ne ramene jamais l'activite en arriere : l'expiration suit la plus recente.
        latest = max(aware(at), self.last_activity_at)
        return changed(self, last_activity_at=latest, expires_at=policy.expires_at(latest))

    def moved_to(self, status: Status) -> 'Investigation':
        if status is not self.status and status not in _TRANSITIONS[self.status]:
            raise MiniaError(INVESTIGATION_INVALID, f'Une enquête {self.status} ne peut pas passer à {status}.')
        return changed(self, status=status)

    def ensure_writable(self):
        if self.status not in WRITABLE:
            raise MiniaError(INVESTIGATION_INVALID, f'Une enquête {self.status} ne reçoit plus d’opération.')


def aware(at: datetime) -> datetime:
    """Un instant avec son fuseau : sans fuseau, il serait ecrit puis illisible a la reprise."""
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise MiniaError(INVESTIGATION_INVALID, 'Un instant d’enquête porte son fuseau horaire.')
    return at


def open_investigation(investigation_id: str, scope: OwnerScope, snapshot: Snapshot, at: datetime,
                       policy: ExpiryPolicy) -> Investigation:
    if not investigation_id:
        raise MiniaError(INVESTIGATION_INVALID, 'Une enquête exige un identifiant.')
    aware(at)
    return Investigation(investigation_id, scope, snapshot, Status.ACTIVE, 0, at, at, policy.expires_at(at))


def confirm_question(investigation: Investigation, text: str, confirmed_by_user: bool,
                     guard: TextGuard) -> Investigation:
    """L'enquete devient reprenable avec la version minimisee que l'utilisateur a confirmee. Sans confirmation,
    ou si la protection refuse le texte, elle reste non reprenable : rien n'est conserve (AC-20). La confirmation
    ne vaut jamais consentement a lire le code."""
    if not confirmed_by_user:
        raise MiniaError(INVESTIGATION_NOT_RESUMABLE,
                         'Sans confirmation de l’utilisateur, la question n’est pas conservée.')
    text = text.strip() if isinstance(text, str) else ''
    if not text or len(text) > MAX_QUESTION_CHARS:
        raise MiniaError(INVESTIGATION_NOT_RESUMABLE,
                         f'La question à conserver doit faire de 1 à {MAX_QUESTION_CHARS} caractères.')
    return changed(investigation, confirmed_question=guard(text))


def ensure_resumable(investigation: Investigation, scope: OwnerScope, current: Snapshot, now: datetime):
    """Les controles avant toute reprise, dans l'ordre du recit (§ 7, « Apres interruption »). Une enquete d'un
    autre perimetre est dite introuvable : sa presence ne fuit pas (AC-07, AC-16)."""
    if investigation.scope != scope:
        raise MiniaError(INVESTIGATION_NOT_FOUND, 'Enquête introuvable.')
    if investigation.expired(now):
        raise MiniaError(INVESTIGATION_EXPIRED, 'Cette enquête a expiré : elle n’est plus restituée.')
    if investigation.status is Status.STALE or investigation.snapshot != current:
        raise MiniaError(INVESTIGATION_STALE, 'La Maille a changé depuis cette enquête : elle ne se poursuit pas '
                         'sur une autre génération. Ouvrez une nouvelle enquête.')
    if investigation.status is Status.COMPLETE:
        raise MiniaError(INVESTIGATION_NOT_RESUMABLE, 'Cette enquête est terminée : posez une nouvelle question.')
    if not investigation.resumable:
        raise MiniaError(INVESTIGATION_NOT_RESUMABLE,
                         'Cette enquête n’a pas de question confirmée : posez une nouvelle question.')
