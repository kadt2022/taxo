"""Le modele de langage de Minia, vu par Taxo : un port, quel que soit le fournisseur (Ollama, Claude...)."""
from typing import Protocol


class MiniaModel(Protocol):
    provider: str
    model_name: str

    def complete(self, system: str, user: str) -> str:
        """Texte brut produit par le modele pour ces deux messages ; leve MiniaError(UNAVAILABLE) sinon."""
        ...

    # Facultatif : `stream(system, user)` rend les morceaux du meme texte au fur et a mesure (TAXO-UX-02).
    # Un fournisseur qui ne l'offre pas repond d'un bloc ; Minia annonce alors ses etapes sans texte provisoire.
