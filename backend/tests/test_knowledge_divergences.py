"""TAXO-ARCH-REF-01 : des divergences de la connaissance d'une analyse, trouvees par l'audit.

Exposees par la tranche A (seule l assertion divergente attendue en echec), corrigees par une PR dediee, jamais dans une restructuration :
ces tests sont desormais des garde-fous ordinaires. Une meme analyse dit la meme chose de ce qu'elle a lu, quelle
que soit l'operation qui le demande.
"""
from sqlalchemy import update
from sqlalchemy.orm import Session

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
    compare = CompareAnalyses(None, None, None, capabilities={('taxo.spring', '1'): frozenset({'Java'})})
    projection = ProducerExecution('PROJECTION', 'taxo.tree', '1', 'run')
    assert compare._read([projection]) == (True, None)
    evaluator = ProducerExecution('EVALUATOR', 'taxo.spring-api', '1', 'run', 'taxo.spring', 'retiree')
    assert compare._read([evaluator]) == (False, frozenset())


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
