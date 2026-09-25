"""Progression reelle d'un evaluateur (TAXO-UX-02).

Un evaluateur rapporte ce qu'il a vraiment fait (fichiers recenses, commits lus, regles determinees),
avec un total seulement quand il le connait. Jamais un pourcentage estime.
"""
from typing import Protocol


class Progress(Protocol):
    def __call__(self, stage: str, message: str, completed: int | None = None, total: int | None = None) -> None: ...


def silent(stage, message, completed=None, total=None):
    """Personne n'observe l'evaluation : la progression n'est pas transmise."""
