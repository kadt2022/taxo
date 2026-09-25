from dataclasses import dataclass

# Plafond de protection d'une consultation de l'historique ; jamais une valeur par defaut.
MAX_COMMITS = 100


@dataclass(frozen=True)
class Commit:
    sha: str
    parents: tuple[str, ...]
    author: str
    authored_at: str
    subject: str


@dataclass(frozen=True)
class ChangedFile:
    """Un fichier touche par un commit. Taxo ne renvoie jamais le contenu d'un fichier confidentiel."""

    path: str
    status: str
    old_path: str | None
    additions: int | None
    deletions: int | None
    confidential: bool


def is_confidential(path):
    """Meme regle que la lecture des instantanes : un .env n'est jamais expose."""
    name = path.rsplit('/', 1)[-1]
    return name == '.env' or name.startswith('.env.')
