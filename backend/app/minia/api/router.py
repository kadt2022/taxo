import json

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.minia.application.ask import HEARTBEAT
from app.minia.domain.errors import MiniaError

_ERRORS = {
    404: {'description': 'Projet, commit ou parent introuvable.'},
    422: {'description': 'Question vide ou trop longue, ou fournisseur non configuré.'},
    502: {'description': 'Réponse de Minia illisible.'},
    503: {'description': 'Minia non configurée, ou modèle injoignable.'},
}


class Question(BaseModel):
    question: str
    parent: str | None = None
    # Accord de la demande pour joindre le diff du commit ; sans effet si MINIA_SOURCE_CONTEXT vaut off.
    source_context: bool = False
    # Fournisseur choisi pour cette demande (ollama, claude...) ; celui par defaut sinon.
    provider: str | None = None


class ProjectQuestion(BaseModel):
    question: str
    provider: str | None = None


def _stream(events):
    """Etapes de Minia en Server-Sent Events ; une panne du modele devient un dernier evenement."""
    def body():
        try:
            for event_type, data in events:
                if event_type == HEARTBEAT:
                    # Commentaire SSE : ignore par le portail, il garde la connexion ouverte pendant l'attente.
                    yield ': Minia attend le modèle\n\n'
                    continue
                yield f'event: {event_type}\ndata: {json.dumps(jsonable_encoder(data), ensure_ascii=False)}\n\n'
        except MiniaError as exc:
            failure = json.dumps({'code': exc.code, 'message': str(exc)}, ensure_ascii=False)
            yield f'event: minia.failed\ndata: {failure}\n\n'
    return StreamingResponse(body(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def create_router(minia):
    router = APIRouter()

    @router.get('/api/minia/status')
    def status():
        return minia.status()

    @router.post('/api/projects/{project_id}/history/commits/{sha}/ask', responses=_ERRORS)
    def ask(project_id: str, sha: str, body: Question):
        return minia.about_commit(project_id, sha, body.question, body.parent, body.source_context, body.provider)

    @router.post('/api/projects/{project_id}/history/commits/{sha}/ask/stream', responses=_ERRORS)
    def ask_stream(project_id: str, sha: str, body: Question):
        return _stream(minia.about_commit_events(project_id, sha, body.question, body.parent, body.source_context,
                                                body.provider))

    @router.post('/api/projects/{project_id}/ask/stream', responses={
        **_ERRORS, 409: {'description': 'Aucune analyse globale pour ce projet.'}})
    def ask_project_stream(project_id: str, body: ProjectQuestion):
        return _stream(minia.about_project_events(project_id, body.question, body.provider))

    @router.post('/api/projects/{project_id}/ask', responses={
        **_ERRORS, 409: {'description': 'Aucune analyse globale pour ce projet.'}})
    def ask_project(project_id: str, body: ProjectQuestion):
        return minia.about_project(project_id, body.question, body.provider)

    return router
