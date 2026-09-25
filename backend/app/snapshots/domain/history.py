"""L'historique Git atteignable depuis le commit d'un instantane (ADR 0007)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class HistoryChange:
    """Un fichier change par un commit, compare a son premier parent ; toute la racine pour un commit racine."""

    status: str
    path: str
    old_path: str | None = None


@dataclass(frozen=True)
class HistoryCommit:
    sha: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    authored_at: str
    subject: str
    changes: tuple[HistoryChange, ...]
