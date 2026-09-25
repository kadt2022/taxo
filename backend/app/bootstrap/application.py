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
from app.hypotheses.infrastructure.model_store import ModelStore
from app.history.application.queries import ProjectHistory
from app.history.infrastructure.git_history import GitHistoryReader
from app.history.api.router import create_router as history_router
from app.minia.application.ask import AskMinia
from app.minia.infrastructure.ollama import OllamaModel
from app.minia.api.router import create_router as minia_router
from . import settings

_FROM_SETTINGS = object()


def minia_model(options):
    """Adaptateur du modele de Minia ; None si aucun modele n'est configure."""
    if options['provider'] != 'ollama':
        raise ValueError(f"MINIA_PROVIDER inconnu : {options['provider']} (seul « ollama » est disponible).")
    return OllamaModel(options['model'], options['url']) if options['model'] else None


def create_app(database_url=None, allowed_roots=None, hypotheses=None, model_store=None, minia=_FROM_SETTINGS):
    engine = create_engine(settings.database_url(database_url))
    paths = LocalProjectPaths(settings.allowed_roots(allowed_roots))
    projects = SqlAlchemyProjectRepository(engine)
    scans = SqlAlchemyScanRepository(engine)
    registry = EvaluatorRegistry([InventoryEvaluator()])
    inventory = registry.get('taxo.inventory')
    run = RunScan(projects, scans, paths, GitSnapshotReader(), inventory, RunEvaluator())
    history = ProjectHistory(projects, paths, GitHistoryReader(), GitSnapshotReader(),
                             registry.all(), RunEvaluator())
    # Mode hypotheses : les poids sont prepares et verifies au demarrage ; aucune API ne les expose
    # tant que TAXO-LAB-01 n'a pas conclu (ADR 0006).
    store = model_store or ModelStore()
    for name in settings.hypotheses_models(hypotheses):
        store.ensure(name)
    api = FastAPI(title='Taxo', version='0.1.0')
    api.state.engine = engine
    register_errors(api)
    api.include_router(health_router)
    api.include_router(projects_router(projects, paths))
    api.include_router(scans_router(projects, scans, run))
    api.include_router(history_router(history))
    # Minia explique a partir des faits de Taxo ; elle ne produit jamais de fait (ADR 0004, regle 14).
    model = minia_model(settings.minia()) if minia is _FROM_SETTINGS else minia
    api.include_router(minia_router(AskMinia(history, model)))
    return api
