from pathlib import Path
from app.projects.domain.project import ProjectError

class LocalProjectPaths:
    def __init__(self, roots):
        self.roots = roots

    def resolve(self, value):
        path = Path(value).resolve()
        if not any(path.is_relative_to(root) for root in self.roots):
            raise ProjectError('OUTSIDE_ROOTS', 'Ce dossier est hors des racines autorisées.')
        if not path.is_dir():
            raise ProjectError('MISSING_DIRECTORY', 'Le dossier est introuvable.')
        return str(path)
