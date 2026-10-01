from typing import Annotated

from fastapi import APIRouter, Query

from app.comparison.domain.comparison import CATEGORIES


def create_router(compare):
    router = APIRouter()
    missing = {404: {'description': 'Projet ou analyse introuvable, ou analyse interrompue.'}}

    @router.get('/api/projects/{project_id}/comparisons', responses=missing)
    def comparison(project_id: str, before: str, after: str):
        """Ce qui a changé entre deux analyses, compté par évaluateur, sans relire le dépôt (TAXO-01F)."""
        return compare.summary(project_id, before, after)

    @router.get('/api/projects/{project_id}/comparisons/changes',
                responses={**missing, 422: {'description': 'Catégorie inconnue ou évaluateur non comparable.'}})
    def changes(project_id: str, before: str, after: str, evaluator: str,
                category: Annotated[str, Query(description=', '.join(CATEGORIES))],
                cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50):
        """Les faits d'une catégorie, page par page ; `next` reprend la page suivante."""
        return compare.changes(project_id, before, after, category, evaluator, cursor, limit)

    return router
