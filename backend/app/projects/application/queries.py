from app.projects.domain.project import ProjectError
from .ports import ProjectRepository

def list_projects(repository: ProjectRepository):
    return repository.list()

def require_project(repository: ProjectRepository, project_id: str):
    project = repository.get(project_id)
    if project is None:
        raise ProjectError('NOT_FOUND', 'Projet introuvable.')
    return project
