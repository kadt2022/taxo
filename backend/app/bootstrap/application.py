from fastapi import FastAPI
from sqlalchemy import create_engine
from app.projects.infrastructure.sqlalchemy.project_repository import SqlAlchemyProjectRepository
from app.projects.infrastructure.paths import LocalProjectPaths
from app.projects.api.router import create_router as projects_router
from app.scans.infrastructure.sqlalchemy.scan_repository import SqlAlchemyScanRepository
from app.scans.application.run_scan import RunScan
from app.scans.api.router import create_router as scans_router
from app.snapshots.infrastructure.git.reader import GitSnapshotReader
from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.evaluations.application.registry import EvaluatorRegistry
from app.evaluations.application.run_evaluator import RunEvaluator
from app.platform.api.health import router as health_router
from app.platform.api.errors import register_errors
from . import settings

def create_app(database_url=None, allowed_roots=None):
    engine = create_engine(settings.database_url(database_url))
    paths = LocalProjectPaths(settings.allowed_roots(allowed_roots))
    projects = SqlAlchemyProjectRepository(engine)
    scans = SqlAlchemyScanRepository(engine)
    registry = EvaluatorRegistry([InventoryEvaluator()])
    inventory = registry.get('taxo.inventory')
    run = RunScan(projects, scans, paths, GitSnapshotReader(), inventory, RunEvaluator())
    api = FastAPI(title='Taxo', version='0.1.0')
    api.state.engine = engine
    register_errors(api)
    api.include_router(health_router)
    api.include_router(projects_router(projects, paths))
    api.include_router(scans_router(projects, scans, run))
    return api
