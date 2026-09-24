from dataclasses import asdict

from fastapi import APIRouter, Query

_ERRORS = {
    404: {'description': 'Projet ou commit introuvable.'},
    422: {'description': 'Historique illisible, par exemple « NOT_A_GIT_REPOSITORY : … ».'},
}


def _commit(commit):
    return asdict(commit)


def create_router(history):
    router = APIRouter()

    @router.get('/api/projects/{project_id}/history/commits', responses=_ERRORS)
    def commits(project_id: str, limit: int = Query(10, ge=1, le=100)):
        return [_commit(commit) for commit in history.commits(project_id, limit)]

    @router.get('/api/projects/{project_id}/history/commits/{sha}', responses=_ERRORS)
    def commit(project_id: str, sha: str, parent: str | None = None):
        found, base, files = history.detail(project_id, sha, parent)
        return {'commit': _commit(found), 'parent': base, 'files': [asdict(item) for item in files]}

    @router.get('/api/projects/{project_id}/history/commits/{sha}/impact', responses=_ERRORS)
    def impact(project_id: str, sha: str, parent: str | None = None):
        found, base, evaluations = history.impact(project_id, sha, parent)
        return {'commit': _commit(found), 'parent': base, 'evaluations': evaluations}

    return router
