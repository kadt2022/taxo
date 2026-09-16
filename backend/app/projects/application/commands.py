from uuid import uuid4
from app.projects.domain.project import Project, ProjectError
from .ports import ProjectRepository, ProjectPathResolver

def add_project(data, repository: ProjectRepository, paths: ProjectPathResolver):
    path = paths.resolve(data.path)
    name = data.name.strip()
    if not name:
        raise ProjectError('NAME_REQUIRED', 'Le nom est obligatoire.')
    if repository.find_path(path):
        raise ProjectError('DUPLICATE_PATH', 'Ce dossier est déjà enregistré.')
    return repository.add(Project(str(uuid4()), name, path))
