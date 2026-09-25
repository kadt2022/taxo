"""Le modele de langage de Minia, vu par Taxo : un port, quel que soit le fournisseur (Ollama, Claude...)."""
from typing import Protocol


class MiniaModel(Protocol):
    provider: str
    model_name: str

    def complete(self, system: str, user: str) -> str:
        """Texte brut produit par le modele pour ces deux messages ; leve MiniaError(UNAVAILABLE) sinon."""
        ...
