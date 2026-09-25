from fastapi import APIRouter, Query

_ERRORS = {404: {'description': 'Projet introuvable.'},
           409: {'description': 'Aucune analyse globale pour ce projet.'},
           422: {'description': 'Requête impossible (nombre nul, date invalide, période inversée).'}}


def create_router(query):
    router = APIRouter()

    @router.get('/api/projects/{project_id}/query', responses=_ERRORS)
    def project_query(project_id: str, q: str = Query(..., max_length=1000)):
        return query(project_id, q)

    return router
