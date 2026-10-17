from datetime import timedelta

from fastapi import FastAPI
from app.platform.database.engine import database_engine
from app.platform.database.schema import require_current_schema
from app.projects.infrastructure.sqlalchemy.project_repository import SqlAlchemyProjectRepository
from app.projects.infrastructure.paths import LocalProjectPaths
from app.projects.api.router import create_router as projects_router
from app.scans.infrastructure.sqlalchemy.scan_repository import SqlAlchemyScanRepository
from app.scans.application.run_scan import RunScan
from app.scans.application.analysis_jobs import AnalysisJobs
from app.scans.api.router import create_router as scans_router
from app.snapshots.infrastructure.git.reader import GitSnapshotReader
from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.evaluators.java_calls.evaluator import JavaCallsEvaluator
from app.evaluators.git.evaluator import GitEvaluator
from app.evaluators.spring_api.evaluator import SpringApiEvaluator
from app.evaluators.spring_boot.evaluator import SpringBootEvaluator
from app.evaluators.spring_security.evaluator import SpringSecurityEvaluator
from app.evaluators.structure.evaluator import StructureEvaluator
from app.scans.infrastructure.sqlalchemy.fact_memory import SqlAlchemyFactMemory
from app.scans.infrastructure.sqlalchemy.fact_comparison import SqlAlchemyComparisonStore
from app.comparison.application.choices import AnalysisChoices
from app.comparison.application.compare import CompareAnalyses
from app.comparison.api.router import create_router as comparison_router
from app.evaluations.application.registry import EvaluatorRegistry
from app.evaluations.domain.capability import CatalogContracts
from app.evaluations.application.run_evaluator import RunEvaluator
from app.platform.api.health import router as health_router
from app.platform.api.errors import register_errors
from app.platform.api.access_log import redact_access_log
from app.hypotheses.infrastructure.model_store import ModelStore
from app.history.application.queries import ProjectHistory
from app.history.application.recorded import RecordedImpact
from app.history.infrastructure.git_history import GitHistoryReader
from app.history.api.router import create_router as history_router
from app.minia.application import trace
from app.minia.application.ask import AskMinia, Views
from app.minia.application.investigation import Investigations, InvestigationSettings
from app.minia.domain.investigation.identity import ExpiryPolicy
from app.minia.infrastructure.investigation_store import SqliteParcoursMemoryStore
from app.projection.application.query import ProjectQuery
from app.projection.api.router import create_router as query_router
from app.protocol.application.exchange import TaxoQuery
from app.protocol.api.router import create_router as protocol_router
from app.mip.application.service import MipService
from app.mip.api.router import create_router as mip_router
from app.minia.infrastructure.claude import ClaudeModel, ClaudeSonnetModel
from app.minia.infrastructure.gemini import GeminiLiteModel, GeminiModel
from app.minia.infrastructure.mistral import MistralModel
from app.minia.infrastructure.ollama import OllamaModel
from app.minia.api.router import create_router as minia_router
from . import settings

_FROM_SETTINGS = object()


PROVIDERS = ('ollama', 'claude', 'claude-sonnet', 'gemini', 'gemini-lite', 'mistral')


def minia_investigations(path=None):
    options = settings.minia_investigations(path)

    def opened():
        options['path'].parent.mkdir(parents=True, exist_ok=True)
        return SqliteParcoursMemoryStore(options['path'])
    return Investigations(settings=InvestigationSettings(policy=ExpiryPolicy(timedelta(days=options['days']))),
                          store_factory=opened)


def minia_models(options):
    """Modeles de Minia par fournisseur configure ; vide si aucun."""
    if options['provider'] not in PROVIDERS:
        raise ValueError(f"MINIA_PROVIDER inconnu : {options['provider']} (ollama, claude, claude-sonnet, gemini, "
                         "gemini-lite ou mistral).")
    models = {}
    if options['model']:
        models['ollama'] = OllamaModel(options['model'], options['url'], num_ctx=options.get('num_ctx', 16384),
                                       timeout=options.get('timeout', 900.0))
    if options.get('claude_model'):
        models['claude'] = ClaudeModel(options['claude_model'])
    if options.get('claude_sonnet_model'):
        models['claude-sonnet'] = ClaudeSonnetModel(options['claude_sonnet_model'])
    if options.get('gemini_model'):
        models['gemini'] = GeminiModel(options['gemini_model'], options.get('gemini_tier', 'free'))
    if options.get('gemini_lite_model'):
        models['gemini-lite'] = GeminiLiteModel(options['gemini_lite_model'], options.get('gemini_lite_tier', 'free'))
    if options.get('mistral_model'):
        models['mistral'] = MistralModel(options['mistral_model'], options.get('mistral_tier', 'free'),
                                         num_ctx=options.get('mistral_num_ctx', 32768))
    return models


def minia_model(options):
    """Modele de Minia par defaut ; None si aucun modele n'est configure."""
    models = minia_models(options)
    return models.get(options['provider']) or next(iter(models.values()), None)


def create_app(database_url=None, allowed_roots=None, hypotheses=None, model_store=None, minia=_FROM_SETTINGS,
               source_context=None, source_reading=None, investigations_path=None):
    engine = database_engine(settings.database_url(database_url))
    # Une base en retard sur le code ferait echouer chaque page qui lit une colonne recente : l'API ne demarre pas.
    require_current_schema(engine)
    paths = LocalProjectPaths(settings.allowed_roots(allowed_roots))
    projects = SqlAlchemyProjectRepository(engine)
    scans = SqlAlchemyScanRepository(engine)
    registry = EvaluatorRegistry([InventoryEvaluator(), GitEvaluator(), SpringApiEvaluator(), SpringBootEvaluator(),
                                  SpringSecurityEvaluator(), StructureEvaluator(), JavaCallsEvaluator()])
    inventory = registry.get('taxo.inventory')
    facts = SqlAlchemyFactMemory(engine)  # TAXO-01E ; analysis_facts reste en secours, plus alimentee
    # Analyse globale : chaque evaluateur observe l'instantane ; l'inventaire du code reste le principal.
    run = RunScan(projects, scans, paths, GitSnapshotReader(), inventory, RunEvaluator(),
                  others=tuple(item for item in registry.all() if item is not inventory), facts=facts,
                  provenance=facts)
    # Mode hypotheses : les poids sont prepares et verifies au demarrage ; aucune API ne les expose
    # tant que TAXO-LAB-01 n'a pas conclu (ARCHITECTURE § 13).
    store = model_store or ModelStore()
    for name in settings.hypotheses_models(hypotheses):
        store.ensure(name)
    api = FastAPI(title='Taxo', version='0.1.0')
    api.state.engine = engine
    # La question passe parfois dans l'adresse : le journal d'acces n'en garde jamais la valeur (TAXO-MINIA-SEC-01, E4).
    redact_access_log()
    register_errors(api)
    api.include_router(health_router)
    api.include_router(projects_router(projects, paths))
    # Analyse observable : lancee en tache de fond, ses evenements reels sont diffuses (TAXO-UX-02).
    # Ce que lit chaque contrat de catalogue (TAXO-COV-01) : une seule valeur pour la restitution, la comparaison
    # et le protocole (TAXO-ARCH-REF-01).
    contracts = CatalogContracts(item.catalog for item in registry.all())
    api.include_router(scans_router(projects, scans, run, facts, AnalysisJobs(run, projects), contracts))
    store = SqlAlchemyComparisonStore(engine)
    comparison = CompareAnalyses(projects, scans, store, contracts)
    # L'impact d'un commit compare le contenu de deux etats : l'historique Git n'y entre pas. Depuis les analyses
    # enregistrees du commit et de son parent s'il y en a, sinon en relisant le depot (TAXO-01F, tranche E).
    history = ProjectHistory(projects, paths, GitHistoryReader(), GitSnapshotReader(),
                             registry.content(), RunEvaluator(), RecordedImpact(scans, comparison))
    api.include_router(history_router(history))
    api.include_router(comparison_router(comparison, AnalysisChoices(projects, scans, store)))
    # La requete selectionne parmi les faits conserves ; elle ne relit jamais le depot (TAXO-QUERY-01).
    query = ProjectQuery(projects, scans, facts)
    api.include_router(query_router(query))
    # Protocole Taxo (ARCHITECTURE § 12) : operations en lecture seule sur la derniere analyse ; le diff reste soumis
    # au meme double consentement que pour Minia (ARCHITECTURE § 12.6) ; le code d'un symbole, au sien (TAXO_SOURCE_READING).
    source = settings.minia_source_context(source_context)
    java_calls = registry.get(JavaCallsEvaluator.evaluator_id)
    api.state.taxo_query = TaxoQuery(projects, scans, facts, history, registry.all(), source, contracts,
                                     settings.taxo_source_reading(source_reading),
                                     {java_calls.evaluator_id: java_calls.declaration_lines})
    api.include_router(protocol_router(api.state.taxo_query))
    # MIP 0.1 (ARCHITECTURE § 12.0) : un adaptateur sur ce même protocole, qui sert une Tuile sans modèle de langage.
    mip = MipService(api.state.taxo_query)
    api.include_router(mip_router(mip))
    # Minia explique a partir des faits de Taxo ; elle ne produit jamais de fait (ARCHITECTURE § 2, principe 5).
    # Plusieurs fournisseurs peuvent servir Minia (Ollama local, Claude distant) : chaque demande choisit.
    # Le journal de développement des échanges, dans la console (MINIA_TRACE, désactivé par défaut).
    trace.configure(settings.minia_trace())
    options = settings.minia()
    models = minia_models(options) if minia is _FROM_SETTINGS else minia
    default = options['provider'] if minia is _FROM_SETTINGS and options['provider'] in models else None
    # Le diff d'un commit ne lui est joint que si MINIA_SOURCE_CONTEXT=diff et que la demande l'autorise (ARCHITECTURE § 12.6).
    # Le carnet des enquêtes navigables (récit TAXO-MINIA-ENQUETE-01) : un fichier SQLite WAL ouvert à la première.
    api.state.minia = AskMinia(history, models, projects, query, source, default, taxo_query=api.state.taxo_query,
                               mip=mip, investigations=minia_investigations(investigations_path),
                               max_calls=settings.minia_max_calls(), exchange_bytes=settings.minia_exchange_bytes(),
                               compact_after=settings.minia_compact_after(),
                               views=Views(tile_projection=settings.minia_tile_projection(),
                                           path_mode=settings.minia_path_mode()))
    api.include_router(minia_router(api.state.minia))
    return api
