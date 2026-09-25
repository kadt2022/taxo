import json
from typing import Literal
from fastapi import APIRouter, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from app.scans.application.queries import analysis_facts, list_scans

def _response(scan):
    return {'id': scan.id, 'created_at': scan.created_at, **scan.result}

# Evenements serveur -> navigateur (Server-Sent Events) : un flux texte, sans tampon intermediaire.
SSE_HEADERS = {'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}


def sse(event):
    """Un evenement au format SSE ; None devient un commentaire qui garde la connexion ouverte."""
    if event is None:
        return ': en cours\n\n'
    data = json.dumps(jsonable_encoder(event['data']), ensure_ascii=False)
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {data}\n\n"


def _resume(value):
    return int(value) if value and value.isdigit() else 0


def create_router(projects, repository, run, facts=None, jobs=None):
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

    if jobs is not None:
        @router.post('/api/projects/{project_id}/analyses', status_code=202, responses={
            404: {'description': 'Projet introuvable.'}, 422: {'description': 'Mode inconnu.'}})
        def start_analysis(project_id: str, mode: Literal['commit', 'working-tree'] = 'commit', commit: str | None = None):
            job = jobs.start(project_id, mode, commit)
            return {'id': job.id, 'events': f'/api/projects/{project_id}/analyses/{job.id}/events'}

        @router.get('/api/projects/{project_id}/analyses/{job_id}/events',
                    responses={404: {'description': 'Analyse en cours introuvable.'}})
        def analysis_events(project_id: str, job_id: str, last_event_id: str | None = Header(None)):
            job = jobs.get(project_id, job_id)
            return StreamingResponse((sse(event) for event in job.follow(_resume(last_event_id))),
                                     media_type='text/event-stream', headers=SSE_HEADERS)

    return router
