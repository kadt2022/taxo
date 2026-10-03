"""Historique d'un projet : commits, fichiers touches, et ce que Taxo comprend de chaque commit."""
from typing import Protocol

from app.comparison.domain.comparison import CATALOG_CHANGED, FAILED_AFTER, FAILED_BEFORE
from app.evaluations.domain.status import EvaluationStatus
from app.facts import fact_identity
from app.history.application.recorded import MEMORY, REREAD, recorded, reread
from app.history.domain.commit import ChangedFile, Commit, is_confidential
from app.history.domain.diff import BINARY, CONFIDENTIAL, Blob, as_text, refusal, side_by_side
from app.history.domain.errors import INCOMPATIBLE_ANALYSES, UNKNOWN_PARENT, UNKNOWN_PATH, HistoryError
from app.history.domain.impact import compare, same_schema, unknowns
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
    def __init__(self, projects, paths, reader: HistoryReader, snapshots, evaluators, runner, recorded=None):
        self.projects, self.paths, self.reader = projects, paths, reader
        self.snapshots, self.evaluators, self.runner = snapshots, tuple(evaluators), runner
        # TAXO-01F, tranche E : l'impact depuis les analyses enregistrees, quand elles existent.
        self.recorded = recorded

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
        found = self.understand(project_id, sha, diff['parent'])
        base, evaluations = found['parent'], found['evaluations']
        before_path = None if base is None or diff['status'] == 'ADDED' else diff['old_path'] or diff['path']
        after_path = None if diff['status'] == 'DELETED' else diff['path']
        changes = [{**change, 'evaluator_id': evaluation['evaluator_id']}
                   for evaluation in evaluations for change in evaluation['changes']]
        return {'path': diff['path'], 'commit': diff['commit'], 'parent': base,
                'facts': link(changes, before_path, after_path, diff['hunks']),
                'not_comparable': [evaluation['evaluator_id'] for evaluation in evaluations
                                   if not evaluation['comparable']],
                'source': found['source'], 'analyses': found['analyses']}

    def impact(self, project_id, sha, parent=None):
        """Le commit, son parent et ce que chaque evaluateur de contenu y voit changer."""
        found = self.understand(project_id, sha, parent)
        return found['commit'], found['parent'], found['evaluations']

    def understand(self, project_id, sha, parent=None, before=None, after=None):
        """L'impact du commit, et d'ou il vient : `MEMORY` s'il est construit depuis les faits persistes des deux
        analyses nommees dans `analyses`, `REREAD` si le depot a ete relu, sans aucune analyse enregistree.

        `before` et `after` nomment explicitement les analyses du parent et du commit : une paire incompatible est
        refusee, jamais remplacee par une relecture. Seules les metadonnees du commit sont lues dans Git pour
        designer son parent ; depuis la memoire, aucun instantane n'est ouvert et aucun evaluateur n'est execute."""
        project, root = self._root(project_id)
        commit, base = self._commit_and_parent(root, sha, parent)
        if self.recorded is None and (before is not None or after is not None):
            raise HistoryError(INCOMPATIBLE_ANALYSES, 'Aucune analyse enregistrée ne peut être lue ici.')
        pair = self.recorded.pair(project.id, commit.sha, base, before, after) if self.recorded else None
        if pair is not None:
            return {'commit': commit, 'parent': base, 'source': MEMORY,
                    'analyses': {'before': recorded(pair[0]), 'after': recorded(pair[1])},
                    'evaluations': self.recorded.evaluations(*pair, self.evaluators)}
        return {'commit': commit, 'parent': base, 'source': REREAD,
                'analyses': {'before': reread(base) if base else None, 'after': reread(commit.sha)},
                'evaluations': self._reread(root, project, commit, base)}

    def _reread(self, root, project, commit, base):
        try:
            after = self.snapshots.open(root, project.id, COMMIT, commit.sha)
            before = self.snapshots.open(root, project.id, COMMIT, base) if base else None
        except SnapshotError as exc:
            raise HistoryError(exc.code, str(exc)) from exc
        return [self._evaluate(evaluator, before, after) for evaluator in self.evaluators]

    def _evaluate(self, evaluator, before, after):
        executed_after = self.runner(evaluator, after)
        executed_before = self.runner(evaluator, before) if before else None
        failed = [execution for execution in (executed_before, executed_after)
                  if execution is not None and execution.status is EvaluationStatus.FAILED]
        before_facts = executed_before.facts if executed_before else ()
        incompatible = not failed and not same_schema(before_facts, executed_after.facts)
        if failed or incompatible:
            # Une execution echouee n'a produit aucun fait, et deux schemas d'identite differents ne se
            # comparent pas : les comparer inventerait des changements.
            changes, unchanged = [], 0
        else:
            changes, unchanged = compare(before_facts, executed_after.facts, fact_identity)
        return {
            'evaluator_id': evaluator.evaluator_id,
            'producer_version': evaluator.producer_version,
            'status_before': executed_before.status.value if executed_before else None,
            'status_after': executed_after.status.value,
            'comparable': not (failed or incompatible),
            'reason': _reason(executed_before, executed_after, incompatible),
            'failures': [warning for execution in failed for warning in execution.warnings] + (
                ['Schéma d’identité différent entre les deux états : faits non comparés.'] if incompatible else []),
            'changes': changes,
            'unchanged_count': unchanged,
            'not_interpreted_before': unknowns(executed_before.coverage) if executed_before else [],
            'not_interpreted_after': unknowns(executed_after.coverage),
        }


def _reason(before, after, incompatible):
    """La raison, dans les termes de la comparaison (TAXO-01F), qui empeche de comparer ; None sinon."""
    if before is not None and before.status is EvaluationStatus.FAILED:
        return FAILED_BEFORE
    if after.status is EvaluationStatus.FAILED:
        return FAILED_AFTER
    return CATALOG_CHANGED if incompatible else None
