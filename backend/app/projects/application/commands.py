from uuid import uuid4
from app.projects.domain.project import Project, ProjectError
from .ports import ProjectRepository, ProjectPathResolver

def add_project(name: str, path: str, repository: ProjectRepository, paths: ProjectPathResolver):
    """Register a project from primitives: the application never receives an HTTP schema."""
    resolved = paths.resolve(path)
    trimmed = name.strip()
    if not trimmed:
        raise ProjectError('NAME_REQUIRED', 'Le nom est obligatoire.')
    if repository.find_path(resolved):
        raise ProjectError('DUPLICATE_PATH', 'Ce dossier est déjà enregistré.')
    return repository.add(Project(str(uuid4()), trimmed, resolved))
