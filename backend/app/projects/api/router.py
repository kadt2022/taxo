from dataclasses import asdict
from fastapi import APIRouter
from app.projects.application.commands import add_project as create_project
from app.projects.application.queries import list_projects
from .schemas import ProjectInput

def create_router(repository, paths):
    router = APIRouter()

    @router.get('/api/projects')
    def projects():
        return [asdict(project) for project in list_projects(repository)]

    @router.post('/api/projects', status_code=201)
    def add_project(data: ProjectInput):
        return asdict(create_project(name=data.name, path=data.path,
                                     repository=repository, paths=paths))

    return router
