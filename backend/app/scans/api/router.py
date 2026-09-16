from typing import Literal
from fastapi import APIRouter
from app.scans.application.queries import list_scans

def _response(scan):
    return {'id': scan.id, 'created_at': scan.created_at, **scan.result}

def create_router(projects, repository, run):
    router = APIRouter()

    @router.get('/api/projects/{project_id}/scans')
    def scans(project_id: str):
        return [_response(scan) for scan in list_scans(project_id, projects, repository)]

    @router.post('/api/projects/{project_id}/scans', status_code=201, responses={
        403: {'description': 'Dossier hors des racines autorisées.'},
        404: {'description': 'Projet introuvable.'},
        422: {'description': 'Analyse impossible, par exemple « NOT_A_GIT_REPOSITORY : … » ou « UNKNOWN_COMMIT : … ».'},
    })
    def run_scan(project_id: str, mode: Literal['commit', 'working-tree'] = 'commit', commit: str | None = None):
        return _response(run(project_id, mode, commit))

    return router
