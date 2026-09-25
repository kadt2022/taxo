from typing import Literal
from fastapi import APIRouter
from app.scans.application.queries import analysis_facts, list_scans

def _response(scan):
    return {'id': scan.id, 'created_at': scan.created_at, **scan.result}

def create_router(projects, repository, run, facts=None):
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

    @router.get('/api/projects/{project_id}/scans/{scan_id}/facts',
                responses={404: {'description': 'Projet ou analyse introuvable.'}})
    def scan_facts(project_id: str, scan_id: str, evaluator: str | None = None, kind: str | None = None,
                   subject: str | None = None, relation: str | None = None, object: str | None = None):
        return analysis_facts(project_id, scan_id, projects, repository, facts, evaluator_id=evaluator, kind=kind,
                              subject=subject, relation=relation, object=object)

    return router
