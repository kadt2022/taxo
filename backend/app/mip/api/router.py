"""Transport HTTP du MIP 0.1 : un premier adaptateur, pas le MIP lui-même (récit TAXO-01N / MIP-01 § 4.1).

Une requête par appel, adressée à un projet comme `taxo-query`. Un refus du contrat est une réponse `ERROR`, pas
une erreur HTTP ; seuls un projet inconnu (404) et l'absence d'analyse (409) le sont, comme pour `taxo-query`.
"""
from typing import Any

from fastapi import APIRouter, Body

_ERRORS = {404: {'description': 'Projet introuvable.'},
           409: {'description': 'Aucune analyse globale pour ce projet, ou analyse demandée inconnue.'}}


def create_router(mip):
    router = APIRouter()

    @router.post('/api/projects/{project_id}/mip/query', responses=_ERRORS)
    def query(project_id: str, body: Any = Body(...)):
        return mip.query(project_id, body)

    return router
