from datetime import datetime, timezone
from uuid import uuid4
from app.projects.application.queries import require_project
from app.projects.application.ports import ProjectRepository, ProjectPathResolver
from app.snapshots.application.ports import SnapshotReader
from app.snapshots.domain.mode import COMMIT, WORKING_TREE
from app.snapshots.domain.errors import SnapshotError
from app.scans.domain.scan import Scan, ScanError
from .ports import ScanRepository, Inventory

# Requested modes, whatever the adapter: the use case owns this invariant, not FastAPI.
MODES = {'commit': COMMIT, 'working-tree': WORKING_TREE}

class RunScan:
    def __init__(self, projects: ProjectRepository, scans: ScanRepository,
                 paths: ProjectPathResolver, snapshots: SnapshotReader, inventory: Inventory,
                 evaluator_runner=None):
        self.projects, self.scans, self.paths = projects, scans, paths
        self.snapshots, self.inventory = snapshots, inventory
        self.evaluator_runner = evaluator_runner

    def __call__(self, project_id, mode='commit', commit=None):
        if mode not in MODES:
            raise ScanError('Mode de scan inconnu : « commit » ou « working-tree » attendu.')
        project = require_project(self.projects, project_id)
        path = self.paths.resolve(project.path)
        try:
            snapshot = self.snapshots.open(path, project.id, MODES[mode], commit)
            if self.evaluator_runner is None:
                result = self.inventory(snapshot)
            else:
                execution = self.evaluator_runner(self.inventory, snapshot)
                result = {**(execution.legacy or {}), 'evaluation': execution.result()}
        except SnapshotError as exc:
            raise ScanError(f'{exc.code} : {exc}') from exc
        except (ValueError, OSError) as exc:
            raise ScanError(str(exc)) from exc
        scan = Scan(str(uuid4()), project_id, datetime.now(timezone.utc), result)
        return self.scans.add(scan)
