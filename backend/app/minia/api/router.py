from fastapi import APIRouter
from pydantic import BaseModel

_ERRORS = {
    404: {'description': 'Projet, commit ou parent introuvable.'},
    422: {'description': 'Question vide ou trop longue.'},
    502: {'description': 'Réponse de Minia illisible.'},
    503: {'description': 'Minia non configurée, ou modèle injoignable.'},
}


class Question(BaseModel):
    question: str
    parent: str | None = None


def create_router(minia):
    router = APIRouter()

    @router.get('/api/minia/status')
    def status():
        return minia.status()

    @router.post('/api/projects/{project_id}/history/commits/{sha}/ask', responses=_ERRORS)
    def ask(project_id: str, sha: str, body: Question):
        return minia.about_commit(project_id, sha, body.question, body.parent)

    return router
