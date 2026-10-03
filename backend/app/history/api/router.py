from dataclasses import asdict

from typing import Annotated

from fastapi import APIRouter, Query

from app.history.domain.commit import MAX_COMMITS

_ERRORS = {
    404: {'description': 'Projet, commit, parent, fichier ou analyse introuvable.'},
    422: {'description': ('Historique illisible, par exemple « NOT_A_GIT_REPOSITORY : … », ou paire '
                          "d'analyses incompatible (« INCOMPATIBLE_ANALYSES : … »).")},
}


def _commit(commit):
    return asdict(commit)


def create_router(history):
    router = APIRouter()

    @router.get('/api/projects/{project_id}/history/commits', responses=_ERRORS)
    def commits(project_id: str, limit: int = Query(..., ge=1, le=MAX_COMMITS,
                                                   description='Nombre de commits demandé ; aucun par défaut.')):
        return [_commit(commit) for commit in history.commits(project_id, limit)]

    @router.get('/api/projects/{project_id}/history/commits/{sha}', responses=_ERRORS)
    def commit(project_id: str, sha: str, parent: str | None = None):
        found, base, files = history.detail(project_id, sha, parent)
        return {'commit': _commit(found), 'parent': base, 'files': [asdict(item) for item in files]}

    @router.get('/api/projects/{project_id}/history/commits/{sha}/diff', responses=_ERRORS)
    def diff(project_id: str, sha: str, path: str, parent: str | None = None):
        return history.diff(project_id, sha, path, parent)

    @router.get('/api/projects/{project_id}/history/commits/{sha}/diff/facts', responses=_ERRORS)
    def diff_facts(project_id: str, sha: str, path: str, parent: str | None = None):
        return history.diff_facts(project_id, sha, path, parent)

    @router.get('/api/projects/{project_id}/history/commits/{sha}/impact', responses=_ERRORS)
    def impact(project_id: str, sha: str, parent: str | None = None,
               before: Annotated[str | None, Query(description="Analyse du parent ; à nommer avec `after`.")] = None,
               after: Annotated[str | None, Query(description='Analyse du commit ; à nommer avec `before`.')] = None):
        """Ce que chaque évaluateur de contenu voit changer : depuis les analyses enregistrées du parent et du
        commit (`source` MEMORY, `analyses` les nomme), sinon en relisant le dépôt (`source` REREAD)."""
        found = history.understand(project_id, sha, parent, before, after)
        return {**found, 'commit': _commit(found['commit'])}

    return router
