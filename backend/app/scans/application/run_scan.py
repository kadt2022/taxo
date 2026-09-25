"""Analyse globale d'un projet (TAXO-EVAL-01, TAXO-EVAL-02).

Chaque evaluateur enregistre observe le meme instantane et produit ses faits ; l'analyse les conserve
pour qu'ils soient interroges ensuite. Aucun ne decide de ce qui sera montre. L'inventaire du code
reste l'evaluateur principal : s'il echoue, l'analyse echoue. Un autre evaluateur en echec est
signale dans le resultat sans empecher l'analyse du code.
"""
from datetime import datetime, timezone
from uuid import uuid4
from app.projects.application.queries import require_project
from app.projects.application.ports import ProjectRepository, ProjectPathResolver
from app.snapshots.application.ports import SnapshotReader
from app.snapshots.domain.mode import COMMIT, WORKING_TREE
from app.snapshots.domain.errors import SnapshotError
from app.scans.domain.scan import Scan, ScanError
from .ports import AnalysisFacts, ScanRepository, EvaluationRunner
from app.evaluations.domain.evaluator import Evaluator
from app.evaluations.domain.status import EvaluationStatus

# Requested modes, whatever the adapter: the use case owns this invariant, not FastAPI.
MODES = {'commit': COMMIT, 'working-tree': WORKING_TREE}


class _NoFactStore:
    def add(self, scan_id, evaluator_id, facts):
        """Sans magasin, les faits ne sont pas conserves ; l'analyse reste possible."""


class RunScan:
    def __init__(self, projects: ProjectRepository, scans: ScanRepository,
                 paths: ProjectPathResolver, snapshots: SnapshotReader, evaluator: Evaluator,
                 evaluator_runner: EvaluationRunner, others: tuple[Evaluator, ...] = (),
                 facts: AnalysisFacts | None = None):
        self.projects, self.scans, self.paths = projects, scans, paths
        self.snapshots, self.evaluator, self.others = snapshots, evaluator, tuple(others)
        self.evaluator_runner = evaluator_runner
        self.facts = facts or _NoFactStore()

    def __call__(self, project_id, mode='commit', commit=None):
        if mode not in MODES:
            raise ScanError('Mode de scan inconnu : « commit » ou « working-tree » attendu.')
        project = require_project(self.projects, project_id)
        path = self.paths.resolve(project.path)
        try:
            snapshot = self.snapshots.open(path, project.id, MODES[mode], commit)
            execution = self.evaluator_runner(self.evaluator, snapshot)
            if execution.status is EvaluationStatus.FAILED:
                detail = execution.warnings[0] if execution.warnings else "L'évaluation a échoué."
                _, separator, message = detail.partition(': ')
                raise ScanError(message if separator else detail)
            executions = [execution, *(self.evaluator_runner(other, snapshot) for other in self.others)]
            result = {**(execution.legacy or {}), 'evaluation_summary': execution.summary(),
                      'evaluations': [item.summary() for item in executions]}
        except SnapshotError as exc:
            raise ScanError(f'{exc.code} : {exc}') from exc
        except (ValueError, OSError) as exc:
            raise ScanError(str(exc)) from exc
        scan = self.scans.add(Scan(str(uuid4()), project_id, datetime.now(timezone.utc), result))
        for item in executions:
            self.facts.add(scan.id, item.evaluator_id, [*item.facts, *item.coverage])
        return scan
