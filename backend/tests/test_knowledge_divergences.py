"""TAXO-ARCH-REF-01 : des divergences de la connaissance d'une analyse, trouvees par l'audit.

Exposees par la tranche A (seule l assertion divergente attendue en echec), corrigees par une PR dediee, jamais dans une restructuration :
ces tests sont desormais des garde-fous ordinaires. Une meme analyse dit la meme chose de ce qu'elle a lu, quelle
que soit l'operation qui le demande.
"""
import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.evaluations.domain.capability import CatalogContracts, Reads
from app.evaluations.domain.evaluator import EvaluatorCatalog
from app.protocol.domain.verdict import NOT_ANALYSED
from app.scans.infrastructure.sqlalchemy.fact_memory import ProducerExecutionRow
from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow
from test_coverage_bounds import HEALTH, PYTHON, legacy, taxo_on_fixture  # noqa: F401  (fixture partagee)
from test_spring_boot import repository


def retire_contract(taxo, producer):
    """Le catalogue enregistre avec ces executions n'est plus connu de ce Taxo (version retiree)."""
    with Session(taxo.engine) as db:
        db.execute(update(ProducerExecutionRow).where(ProducerExecutionRow.producer_id == producer)
                   .values(catalog_version='retiree'))
        db.commit()


def catalog(catalog_id, version, languages):
    return EvaluatorCatalog(catalog_id, version, languages=languages)


def forget_catalogs(taxo, scan_id):
    """Un resume anterieur a TAXO-COV-01 : ses executions n'y nomment pas leur catalogue."""
    with Session(taxo.engine) as db:
        row = db.get(ScanRow, scan_id)
        row.result = {**row.result, 'evaluations': [
            {key: value for key, value in item.items() if key not in ('catalog_id', 'catalog_version')}
            for item in row.result['evaluations']]}
        db.commit()


def test_an_unknown_contract_justifies_no_negative_conclusion_anywhere(taxo_on, git, monkeypatch):
    legacy(monkeypatch)
    taxo, root = taxo_on(PYTHON)
    before = taxo.analyse()['id']
    (root / 'api/admin.py').write_text('from api.main import app\n')
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'admin')
    after = taxo.analyse()['id']
    retire_contract(taxo, 'taxo.spring-api')
    verdict, = taxo.ask(('verify_claim', HEALTH), analysis=after)
    assert verdict['reason'] == NOT_ANALYSED, 'le verdict ne tire rien d un contrat inconnu'
    compared = taxo.compare(before, after)['taxo.spring-api']
    assert not compared['comparable'], 'la comparaison ne doit pas en tirer « aucun changement »'
    assert compared['reason'] == 'CONTRACT_UNKNOWN_BEFORE', 'le contrat est retire des deux cotes'
    assert compared['not_analysed'] == {'before': ['Python'], 'after': ['Python']}, 'un contrat inconnu ne lit rien'


def test_an_earlier_analysis_names_the_same_unread_languages_in_every_operation(taxo_on, monkeypatch):
    legacy(monkeypatch)
    taxo, _ = taxo_on(PYTHON)
    scan = taxo.analyse()['id']
    taxo.forget_languages(scan)
    verdict, tile = taxo.ask(('verify_claim', HEALTH), ('get_neighborhood', {
        'analysis': scan, 'root': HEALTH['subject'], 'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}), analysis=scan)
    named = sorted(entry['subject'] for entry in verdict['coverage'] if entry['type'] == 'NOT_ANALYSED' and entry['subject'])
    assert named == ['language:Python']
    frontier = [item for item in tile['frontier'] if item.get('reason') == 'NOT_ANALYSED']
    assert [item['languages'] for item in frontier] == [['Python']], 'le voisinage dit la meme limite que le verdict'


def test_a_projection_is_bound_to_no_catalog_contract():
    """Une projection n'a pas de catalogue : elle n'est ni un contrat inconnu ni un contrat qui ne lit rien."""
    from app.comparison.application.compare import CompareAnalyses
    from app.facts.domain.provenance import ProducerExecution
    compare = CompareAnalyses(None, None, None, CatalogContracts([catalog('taxo.spring', '1', ('Java',))]))
    projection = ProducerExecution('PROJECTION', 'taxo.tree', '1', 'run')
    assert compare._read([projection]) == Reads.any()
    evaluator = ProducerExecution('EVALUATOR', 'taxo.spring-api', '1', 'run', 'taxo.spring', 'retiree')
    assert compare._read([evaluator]) == Reads.unknown()


def test_an_earlier_summary_is_read_by_the_contract_its_execution_recorded(taxo_on):
    """Divergence 3 : une couverture ancienne se juge selon le contrat de son producteur, jamais selon le
    catalogue actuel de son analyseur. Ce contrat n'est plus connu : il ne lit rien, Java compris."""
    taxo, _ = taxo_on({**repository(), **PYTHON})
    scan = taxo.analyse()['id']
    forget_catalogs(taxo, scan)
    retire_contract(taxo, 'taxo.spring-api')
    verdict, tile = taxo.ask(('verify_claim', {'subject': 'endpoint:GET /missing', 'relation': 'HANDLED_BY',
                                               'object': 'symbol:java:com.acme.Missing#get()'}),
                             ('get_neighborhood', {'analysis': scan, 'root': 'endpoint:GET /orders',
                                                   'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}), analysis=scan)
    named = sorted(entry['subject'] for entry in verdict['coverage'] if entry['type'] == 'NOT_ANALYSED' and entry['subject'])
    assert named == ['language:Java', 'language:Python']
    reading = taxo.client.get(f'{taxo.base}/scans/{scan}/coverage').json()
    api, = [item for item in reading['evaluators'] if item['evaluator_id'] == 'taxo.spring-api']
    assert (api['contract'], api['unread']) == ('UNKNOWN', ['Java', 'Python'])
    frontier = [item['languages'] for item in tile['frontier'] if item.get('reason') == 'NOT_ANALYSED']
    assert frontier == [['Java', 'Python']], 'le voisinage dit la meme limite que le verdict et la restitution'


def test_the_recorded_contract_is_read_without_reading_any_coverage(taxo_on, monkeypatch):
    """Le voisinage reste borne : le contrat d'un resume anterieur se lit dans ses executions, pas dans ses faits."""
    from app.scans.infrastructure.sqlalchemy.fact_memory import SqlAlchemyFactMemory
    taxo, _ = taxo_on({**repository(), **PYTHON})
    scan = taxo.analyse()['id']
    forget_catalogs(taxo, scan)
    read, query = [], SqlAlchemyFactMemory.query
    monkeypatch.setattr(SqlAlchemyFactMemory, 'query',
                        lambda self, scan_id, **filters: read.append(filters) or query(self, scan_id, **filters))
    tile, = taxo.ask(('get_neighborhood', {'analysis': scan, 'root': 'endpoint:GET /orders',
                                           'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}), analysis=scan)
    assert [item['languages'] for item in tile['frontier'] if item.get('reason') == 'NOT_ANALYSED'] == [['Python']]
    assert not [filters for filters in read if filters.get('kind') == 'COVERAGE']


def test_an_analysis_cannot_record_a_second_execution_of_a_producer(taxo_on):
    """L'invariant sur lequel s'appuient verdict, comparaison et voisinage : une execution d'evaluateur par
    producteur et par analyse. La base ne le porte pas (contrainte sur `(scan_id, execution_id)`) ; il tient par
    construction : chaque evaluateur enregistre n'est execute qu'une fois, et une analyse relancee sous le meme
    identifiant est refusee par la cle de `scans` avant qu'aucune execution ne soit enregistree."""
    from sqlalchemy.exc import IntegrityError
    from app.evaluations.application.run_evaluator import RunEvaluator
    from app.evaluators.git.evaluator import GitEvaluator
    from app.evaluators.inventory.evaluator import InventoryEvaluator
    from app.evaluators.spring_api.evaluator import SpringApiEvaluator
    from app.projects.infrastructure.paths import LocalProjectPaths
    from app.projects.infrastructure.sqlalchemy.project_repository import SqlAlchemyProjectRepository
    from app.scans.application.run_scan import RunScan
    from app.scans.infrastructure.sqlalchemy.fact_memory import SqlAlchemyFactMemory
    from app.scans.infrastructure.sqlalchemy.scan_repository import SqlAlchemyScanRepository
    from app.snapshots.infrastructure.git.reader import GitSnapshotReader
    taxo, root = taxo_on({**repository(), **PYTHON})
    memory = SqlAlchemyFactMemory(taxo.engine)
    run = RunScan(SqlAlchemyProjectRepository(taxo.engine), SqlAlchemyScanRepository(taxo.engine),
                  LocalProjectPaths([root]), GitSnapshotReader(), InventoryEvaluator(), RunEvaluator(),
                  others=(GitEvaluator(), SpringApiEvaluator()), facts=memory, provenance=memory)
    project = taxo.base.rsplit('/', 1)[1]
    run(project, scan_id='reprise')
    recorded = sorted(item.producer_id for item in memory.executions('reprise'))
    assert recorded == ['taxo.git', 'taxo.inventory', 'taxo.spring-api']
    with pytest.raises(IntegrityError):
        run(project, scan_id='reprise')
    assert sorted(item.producer_id for item in memory.executions('reprise')) == recorded, 'aucune seconde execution'


def test_executions_of_one_producer_naming_different_contracts_read_nothing_known():
    """Aucune execution n'est choisie a la place d'une autre : des contrats differents pour un meme producteur
    ne justifient aucune conclusion negative."""
    from types import SimpleNamespace
    from app.facts.domain.provenance import ProducerExecution
    from app.neighborhood.application.query import _recorded_contracts
    contracts = CatalogContracts([catalog('spring', '1', ('Java',)), catalog('spring', '2', ('Java', 'Kotlin'))])
    executions = [ProducerExecution('EVALUATOR', 'api', '1', 'a', 'spring', '1'),
                  ProducerExecution('EVALUATOR', 'api', '1', 'b', 'spring', '2'),
                  ProducerExecution('EVALUATOR', 'git', '1', 'c', 'spring', '1'),
                  ProducerExecution('EVALUATOR', 'git', '1', 'd', 'spring', '1')]
    service = SimpleNamespace(facts=SimpleNamespace(executions=lambda scan_id: executions),
                              reads_of=lambda item: contracts.reads(item['catalog_id'], item['catalog_version']))
    exchange = SimpleNamespace(service=service, scan=SimpleNamespace(id='scan'))
    assert _recorded_contracts(exchange) == {'api': Reads.unknown(), 'git': Reads.declared(('Java',))}
