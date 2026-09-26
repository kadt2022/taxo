from fastapi import FastAPI
from sqlalchemy import create_engine
from app.projects.infrastructure.sqlalchemy.project_repository import SqlAlchemyProjectRepository
from app.projects.infrastructure.paths import LocalProjectPaths
from app.projects.api.router import create_router as projects_router
from app.scans.infrastructure.sqlalchemy.scan_repository import SqlAlchemyScanRepository
from app.scans.application.run_scan import RunScan
from app.scans.application.analysis_jobs import AnalysisJobs
from app.scans.api.router import create_router as scans_router
from app.snapshots.infrastructure.git.reader import GitSnapshotReader
from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.evaluators.git.evaluator import GitEvaluator
from app.evaluators.spring_api.evaluator import SpringApiEvaluator
from app.scans.infrastructure.sqlalchemy.fact_store import SqlAlchemyAnalysisFacts
from app.evaluations.application.registry import EvaluatorRegistry
from app.evaluations.application.run_evaluator import RunEvaluator
from app.platform.api.health import router as health_router
from app.platform.api.errors import register_errors
from app.hypotheses.infrastructure.model_store import ModelStore
from app.history.application.queries import ProjectHistory
from app.history.infrastructure.git_history import GitHistoryReader
from app.history.api.router import create_router as history_router
from app.minia.application.ask import AskMinia
from app.projection.application.query import ProjectQuery
from app.projection.api.router import create_router as query_router
from app.protocol.application.exchange import TaxoQuery
from app.protocol.api.router import create_router as protocol_router
from app.minia.infrastructure.claude import ClaudeModel
from app.minia.infrastructure.gemini import GeminiModel
from app.minia.infrastructure.mistral import MistralModel
from app.minia.infrastructure.ollama import OllamaModel
from app.minia.api.router import create_router as minia_router
from . import settings

_FROM_SETTINGS = object()


PROVIDERS = ('ollama', 'claude', 'gemini', 'mistral')


def minia_models(options):
    """Modeles de Minia par fournisseur configure ; vide si aucun."""
    if options['provider'] not in PROVIDERS:
        raise ValueError(f"MINIA_PROVIDER inconnu : {options['provider']} (ollama, claude, gemini ou mistral).")
    models = {}
    if options['model']:
        models['ollama'] = OllamaModel(options['model'], options['url'], num_ctx=options.get('num_ctx', 16384),
                                       timeout=options.get('timeout', 900.0))
    if options.get('claude_model'):
        models['claude'] = ClaudeModel(options['claude_model'])
    if options.get('gemini_model'):
        models['gemini'] = GeminiModel(options['gemini_model'], options.get('gemini_tier', 'free'))
    if options.get('mistral_model'):
        models['mistral'] = MistralModel(options['mistral_model'], options.get('mistral_tier', 'free'),
                                         num_ctx=options.get('mistral_num_ctx', 32768))
    return models


def minia_model(options):
    """Modele de Minia par defaut ; None si aucun modele n'est configure."""
    models = minia_models(options)
    return models.get(options['provider']) or next(iter(models.values()), None)


def create_app(database_url=None, allowed_roots=None, hypotheses=None, model_store=None, minia=_FROM_SETTINGS,
               source_context=None):
    engine = create_engine(settings.database_url(database_url))
    paths = LocalProjectPaths(settings.allowed_roots(allowed_roots))
    projects = SqlAlchemyProjectRepository(engine)
    scans = SqlAlchemyScanRepository(engine)
    registry = EvaluatorRegistry([InventoryEvaluator(), GitEvaluator(), SpringApiEvaluator()])
    inventory = registry.get('taxo.inventory')
    facts = SqlAlchemyAnalysisFacts(engine)
    # Analyse globale : chaque evaluateur observe l'instantane ; l'inventaire du code reste le principal.
    run = RunScan(projects, scans, paths, GitSnapshotReader(), inventory, RunEvaluator(),
                  others=tuple(item for item in registry.all() if item is not inventory), facts=facts)
    # L'impact d'un commit compare le contenu de deux instantanes : l'historique Git n'y entre pas.
    history = ProjectHistory(projects, paths, GitHistoryReader(), GitSnapshotReader(),
                             registry.content(), RunEvaluator())
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
    # Analyse observable : lancee en tache de fond, ses evenements reels sont diffuses (TAXO-UX-02).
    api.include_router(scans_router(projects, scans, run, facts, AnalysisJobs(run, projects)))
    api.include_router(history_router(history))
    # La requete selectionne parmi les faits conserves ; elle ne relit jamais le depot (TAXO-QUERY-01).
    query = ProjectQuery(projects, scans, facts)
    api.include_router(query_router(query))
    # Protocole Taxo (ADR 0009) : operations en lecture seule sur la derniere analyse ; le diff reste soumis
    # au meme double consentement que pour Minia (ADR 0008).
    source = settings.minia_source_context(source_context)
    api.state.taxo_query = TaxoQuery(projects, scans, facts, history, registry.all(), source)
    api.include_router(protocol_router(api.state.taxo_query))
    # Minia explique a partir des faits de Taxo ; elle ne produit jamais de fait (ADR 0004, regle 14).
    # Plusieurs fournisseurs peuvent servir Minia (Ollama local, Claude distant) : chaque demande choisit.
    options = settings.minia()
    models = minia_models(options) if minia is _FROM_SETTINGS else minia
    default = options['provider'] if minia is _FROM_SETTINGS and options['provider'] in models else None
    # Le diff d'un commit ne lui est joint que si MINIA_SOURCE_CONTEXT=diff et que la demande l'autorise (ADR 0008).
    api.state.minia = AskMinia(history, models, projects, query, source, default, taxo_query=api.state.taxo_query)
    api.include_router(minia_router(api.state.minia))
    return api
