"""Historique d'un projet : commits, fichiers touches, et ce que Taxo comprend de chaque commit."""
from typing import Protocol

from app.evaluations.domain.status import EvaluationStatus
from app.facts import fact_identity
from app.history.domain.commit import ChangedFile, Commit, is_confidential
from app.history.domain.diff import BINARY, CONFIDENTIAL, Blob, as_text, refusal, side_by_side
from app.history.domain.errors import UNKNOWN_PARENT, UNKNOWN_PATH, HistoryError
from app.history.domain.impact import compare, unknowns
from app.history.domain.links import link
from app.projects.application.queries import require_project
from app.snapshots.domain.errors import SnapshotError
from app.snapshots.domain.mode import COMMIT


class HistoryReader(Protocol):
    def commits(self, root: str, limit: int) -> list[Commit]: ...

    def commit(self, root: str, sha: str) -> Commit: ...

    def files(self, root: str, sha: str, parent: str | None) -> list[ChangedFile]: ...

    def blob(self, root: str, revision: str, path: str) -> Blob | None: ...

    def content(self, root: str, oid: str) -> bytes: ...


class ProjectHistory:
    def __init__(self, projects, paths, reader: HistoryReader, snapshots, evaluators, runner):
        self.projects, self.paths, self.reader = projects, paths, reader
        self.snapshots, self.evaluators, self.runner = snapshots, tuple(evaluators), runner

    def _root(self, project_id):
        project = require_project(self.projects, project_id)
        return project, self.paths.resolve(project.path)

    def commits(self, project_id, limit):
        """Consultation explicite de l'historique : distincte de l'analyse globale du projet."""
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

    def diff(self, project_id, sha, path, parent=None):
        """Diff d'un fichier touche par le commit : parent a gauche, commit a droite.

        Seul un chemin de la liste des fichiers du commit est accepte. Aucun contenu n'est lu pour un
        fichier confidentiel, un lien, un sous-module ou un fichier trop gros, d'un cote comme de l'autre.
        """
        _, root = self._root(project_id)
        commit, base = self._commit_and_parent(root, sha, parent)
        changed = next((item for item in self.reader.files(root, commit.sha, base) if item.path == path), None)
        if changed is None:
            raise HistoryError(UNKNOWN_PATH, "Ce fichier n'est pas touché par ce commit.")
        return self._file_diff(root, commit, base, changed)

    def diffs(self, project_id, sha, parent=None):
        """Fichiers du commit et lecteur de leur diff : chaque contenu n'est lu qu'a la demande, avec les
        memes refus que `diff` (TAXO-MINIA-02)."""
        _, root = self._root(project_id)
        commit, base = self._commit_and_parent(root, sha, parent)
        return self.reader.files(root, commit.sha, base), lambda changed: self._file_diff(root, commit, base, changed)

    def _file_diff(self, root, commit, base, changed):
        before_path = changed.old_path or changed.path
        result = {'path': changed.path, 'old_path': changed.old_path, 'status': changed.status,
                  'commit': commit.sha, 'parent': base, 'before': None, 'after': None, 'hunks': []}
        if changed.confidential or is_confidential(before_path):
            return {**result, 'displayable': False, 'reason': CONFIDENTIAL}
        before = self.reader.blob(root, base, before_path) if base and changed.status != 'ADDED' else None
        after = self.reader.blob(root, commit.sha, changed.path) if changed.status != 'DELETED' else None
        sides = {'before': (before, before_path), 'after': (after, changed.path)}
        result.update({side: {'path': name, 'size': blob.size} if blob else None
                       for side, (blob, name) in sides.items()})
        reason = refusal([before, after])
        if reason:
            return {**result, 'displayable': False, 'reason': reason}
        texts = [as_text(self.reader.content(root, blob.oid)) if blob else '' for blob in (before, after)]
        if None in texts:
            return {**result, 'displayable': False, 'reason': BINARY}
        return {**result, 'displayable': True, 'reason': None, 'hunks': side_by_side(*texts)}

    def diff_facts(self, project_id, sha, path, parent=None):
        """Faits changes par le commit dont une preuve porte sur ce fichier, relies aux lignes du diff."""
        diff = self.diff(project_id, sha, path, parent)
        _, base, evaluations = self.impact(project_id, sha, diff['parent'])
        before_path = None if base is None or diff['status'] == 'ADDED' else diff['old_path'] or diff['path']
        after_path = None if diff['status'] == 'DELETED' else diff['path']
        changes = [{**change, 'evaluator_id': evaluation['evaluator_id']}
                   for evaluation in evaluations for change in evaluation['changes']]
        return {'path': diff['path'], 'commit': diff['commit'], 'parent': base,
                'facts': link(changes, before_path, after_path, diff['hunks']),
                'not_comparable': [evaluation['evaluator_id'] for evaluation in evaluations
                                   if not evaluation['comparable']]}

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
        failed = [execution for execution in (executed_before, executed_after)
                  if execution is not None and execution.status is EvaluationStatus.FAILED]
        if failed:
            # Une execution echouee n'a produit aucun fait : la comparer inventerait des changements.
            changes, unchanged = [], 0
        else:
            changes, unchanged = compare(executed_before.facts if executed_before else (),
                                         executed_after.facts, fact_identity)
        return {
            'evaluator_id': evaluator.evaluator_id,
            'producer_version': evaluator.producer_version,
            'status_before': executed_before.status.value if executed_before else None,
            'status_after': executed_after.status.value,
            'comparable': not failed,
            'failures': [warning for execution in failed for warning in execution.warnings],
            'changes': changes,
            'unchanged_count': unchanged,
            'not_interpreted_before': unknowns(executed_before.coverage) if executed_before else [],
            'not_interpreted_after': unknowns(executed_after.coverage),
        }
