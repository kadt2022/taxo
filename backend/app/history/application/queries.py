"""Historique d'un projet : commits, fichiers touches, et ce que Taxo comprend de chaque commit."""
from typing import Protocol

from app.facts import fact_identity
from app.history.domain.commit import ChangedFile, Commit
from app.history.domain.errors import UNKNOWN_PARENT, HistoryError
from app.history.domain.impact import compare, unknowns
from app.projects.application.queries import require_project
from app.snapshots.domain.errors import SnapshotError
from app.snapshots.domain.mode import COMMIT


class HistoryReader(Protocol):
    def commits(self, root: str, limit: int) -> list[Commit]: ...

    def commit(self, root: str, sha: str) -> Commit: ...

    def files(self, root: str, sha: str, parent: str | None) -> list[ChangedFile]: ...


class ProjectHistory:
    def __init__(self, projects, paths, reader: HistoryReader, snapshots, evaluators, runner):
        self.projects, self.paths, self.reader = projects, paths, reader
        self.snapshots, self.evaluators, self.runner = snapshots, tuple(evaluators), runner

    def _root(self, project_id):
        project = require_project(self.projects, project_id)
        return project, self.paths.resolve(project.path)

    def commits(self, project_id, limit=10):
        _, root = self._root(project_id)
        return self.reader.commits(root, limit)

    def _commit_and_parent(self, root, sha, parent):
        commit = self.reader.commit(root, sha)
        if parent is None:
            return commit, commit.parents[0] if commit.parents else None
        if parent not in commit.parents:
            raise HistoryError(UNKNOWN_PARENT, "Ce commit n'a pas ce parent : choisir l'un de ses parents.")
        return commit, parent

    def detail(self, project_id, sha, parent=None):
        _, root = self._root(project_id)
        commit, base = self._commit_and_parent(root, sha, parent)
        return commit, base, self.reader.files(root, commit.sha, base)

    def impact(self, project_id, sha, parent=None):
        """Chaque evaluateur enregistre analyse le parent puis le commit ; les faits sont compares."""
        project, root = self._root(project_id)
        commit, base = self._commit_and_parent(root, sha, parent)
        try:
            after = self.snapshots.open(root, project.id, COMMIT, commit.sha)
            before = self.snapshots.open(root, project.id, COMMIT, base) if base else None
        except SnapshotError as exc:
            raise HistoryError(exc.code, str(exc)) from exc
        return commit, base, [self._evaluate(evaluator, before, after) for evaluator in self.evaluators]

    def _evaluate(self, evaluator, before, after):
        executed_after = self.runner(evaluator, after)
        executed_before = self.runner(evaluator, before) if before else None
        changes, unchanged = compare(executed_before.facts if executed_before else (),
                                     executed_after.facts, fact_identity)
        return {
            'evaluator_id': evaluator.evaluator_id,
            'producer_version': evaluator.producer_version,
            'status_before': executed_before.status.value if executed_before else None,
            'status_after': executed_after.status.value,
            'changes': changes,
            'unchanged_count': unchanged,
            'not_interpreted_before': unknowns(executed_before.coverage) if executed_before else [],
            'not_interpreted_after': unknowns(executed_after.coverage),
        }
