import json

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.minia.application.ask import HEARTBEAT
from app.minia.domain.cancellation import Cancellation
from app.minia.domain.errors import CANCELLED, MiniaError

_END = object()

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


def _event(event_type, data):
    return f'event: {event_type}\ndata: {json.dumps(jsonable_encoder(data), ensure_ascii=False)}\n\n'


def _stream(minia, events, cancel):
    """Etapes de Minia en Server-Sent Events. Le premier evenement donne l'identifiant de la demande, qui
    permet de l'arreter (TAXO-UX-03) ; une panne du modele ou un arret devient un dernier evenement. Si le
    client se deconnecte, la demande est arretee : le travail en cours ne continue pas pour personne."""
    request_id = minia.register(cancel)
    iterator = iter(events)

    def advance():
        return next(iterator, _END)

    async def body():
        finished = False
        try:
            yield _event('minia.started', {'request_id': request_id})
            while True:
                # Le thread qui attend le modele est abandonne a l'annulation : l'arret passe tout de suite.
                item = await anyio.to_thread.run_sync(advance, abandon_on_cancel=True)
                if item is _END:
                    break
                event_type, data = item
                if event_type == HEARTBEAT:
                    # Commentaire SSE : ignore par le portail, il garde la connexion ouverte pendant l'attente.
                    yield ': Minia attend le modèle\n\n'
                    continue
                yield _event(event_type, data)
            finished = True
        except MiniaError as exc:
            finished = True
            if exc.code == CANCELLED:
                yield _event('minia.cancelled', {'message': str(exc)})
            else:
                yield _event('minia.failed', {'code': exc.code, 'message': str(exc)})
        finally:
            if not finished:
                cancel.cancel()
            minia.release(request_id)
    return StreamingResponse(body(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def create_router(minia):
    router = APIRouter()

    @router.get('/api/minia/status')
    def status():
        return minia.status()

    @router.post('/api/minia/requests/{request_id}/cancel', status_code=202,
                 responses={404: {'description': 'Demande inconnue ou déjà terminée.'}})
    def cancel(request_id: str):
        """Arrete une demande en cours : plus aucun tour, l'appel au fournisseur est coupe, aucune reponse."""
        if not minia.stop(request_id):
            raise HTTPException(404, 'Demande inconnue ou déjà terminée.')
        return {'cancelled': True}

    @router.post('/api/projects/{project_id}/history/commits/{sha}/ask', responses=_ERRORS)
    def ask(project_id: str, sha: str, body: Question):
        return minia.about_commit(project_id, sha, body.question, body.parent, body.source_context, body.provider)

    @router.post('/api/projects/{project_id}/history/commits/{sha}/ask/stream', responses=_ERRORS)
    def ask_stream(project_id: str, sha: str, body: Question):
        cancel = Cancellation()
        return _stream(minia, minia.about_commit_events(project_id, sha, body.question, body.parent,
                                                        body.source_context, body.provider, cancel=cancel), cancel)

    @router.post('/api/projects/{project_id}/ask/stream', responses={
        **_ERRORS, 409: {'description': 'Aucune analyse globale pour ce projet.'}})
    def ask_project_stream(project_id: str, body: ProjectQuestion):
        cancel = Cancellation()
        return _stream(minia, minia.about_project_events(project_id, body.question, body.provider, cancel=cancel),
                       cancel)

    @router.post('/api/projects/{project_id}/ask', responses={
        **_ERRORS, 409: {'description': 'Aucune analyse globale pour ce projet.'}})
    def ask_project(project_id: str, body: ProjectQuestion):
        return minia.about_project(project_id, body.question, body.provider)

    return router
