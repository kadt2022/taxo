"""TAXO-COV-01 : une couverture bornee. Une absence de preuve n'est jamais une preuve d'absence.

La verite de chaque cas est ecrite ici a la main, a partir des fichiers du depot : un depot sans Java n'a
rien a lire pour un analyseur Java ; une route d'un fichier Python n'a pas ete cherchee par lui.
"""
import dataclasses
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.bootstrap.database import Base
from app.evaluations.domain.capability import Reads
from app.evaluations.domain.status import EvaluationStatus
from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.evaluators.spring_api.evaluator import SpringApiEvaluator
from app.main import create_app
from app.knowledge.domain.knowledge import AnalysisKnowledge, Analyzer
from app.protocol.domain.verdict import NOT_ANALYSED, NOT_FOUND_IN_ANALYSED_SCOPE, NOT_PROVEN, judge
from app.scans.infrastructure.sqlalchemy.scan_repository import ScanRow
from test_spring_boot import controller, repository

SPRING = ('taxo.spring-api', 'taxo.spring-boot', 'taxo.spring-security')
PYTHON = {'api/main.py': 'from fastapi import FastAPI\napp = FastAPI()\n\n@app.get("/api/health")\n'
                         'def health():\n    return {}\n',
          'README.md': 'Un service HTTP en Python.\n'}
HEALTH = {'subject': 'endpoint:GET /api/health', 'relation': 'HANDLED_BY', 'object': 'symbol:python:api.main#health'}


class Taxo:
    def __init__(self, client, base, engine):
        self.client, self.base, self.engine = client, base, engine

    def analyse(self, commit=None):
        response = self.client.post(f'{self.base}/scans', params={'commit': commit} if commit else {})
        assert response.status_code == 201, response.text
        return response.json()

    def ask(self, *requests, analysis=None):
        body = {'requests': [{'operation': name, 'arguments': arguments} for name, arguments in requests],
                **({'analysis': analysis} if analysis else {})}
        response = self.client.post(f'{self.base}/taxo-query', json=body)
        assert response.status_code == 200, response.text
        return response.json()['responses']

    def compare(self, before, after):
        response = self.client.get(f'{self.base}/comparisons', params={'before': before, 'after': after})
        assert response.status_code == 200, response.text
        return {item['evaluator_id']: item for item in response.json()['evaluators']}

    def forget_languages(self, scan_id):
        """Une analyse anterieure a TAXO-COV-01 : ses langages ne sont pas enregistres avec elle."""
        with Session(self.engine) as db:
            row = db.get(ScanRow, scan_id)
            row.result = {key: value for key, value in row.result.items() if key != 'languages'}
            db.commit()


@pytest.fixture(name='taxo_on')
def taxo_on_fixture(make_repo, tmp_path):
    clients = []

    def open_on(files):
        root = make_repo(files)
        app = create_app(f'sqlite:///{tmp_path / f"{root.name}.db"}', [root], minia={})
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        clients.append(client)
        project = client.post('/api/projects', json={'name': root.name, 'path': str(root)}).json()
        return Taxo(client, f'/api/projects/{project["id"]}', app.state.engine), root
    yield open_on
    for client in clients:
        client.close()


def legacy(monkeypatch):
    """Le moteur d'avant TAXO-COV-01 : chaque analyseur est execute, qu'il ait quelque chose a lire ou non."""
    monkeypatch.setattr('app.scans.application.run_scan.applicable', lambda languages, present: True)


def evaluations(scan):
    return {item['evaluator_id']: item for item in scan['evaluations']}


def test_an_analyzer_with_nothing_to_read_is_not_run_and_never_claims_coverage(taxo_on, monkeypatch):
    monkeypatch.setattr(SpringApiEvaluator, 'evaluate', lambda *args, **kwargs: pytest.fail('analyseur appelé'))
    taxo, _ = taxo_on(PYTHON)
    scan = taxo.analyse()
    assert scan['languages'] == ['Python']
    found = evaluations(scan)
    for name in SPRING:
        assert found[name]['status'] == 'UNSUPPORTED', name
        assert found[name]['fact_count'] == 0, name
        assert [item['coverage_type'] for item in found[name]['coverage']] == ['OUT_OF_SCOPE'], name
    assert found['taxo.inventory']['status'] == found['taxo.git']['status'] == 'SUCCESS'
    spring = [entry for entry in taxo.ask(('find_facts', {'relation': 'HANDLED_BY'}))[0]['coverage']
              if entry['producer'] == 'taxo.spring-api']
    assert [(entry['type'], entry['languages']) for entry in spring] == [('OUT_OF_SCOPE', ['Java'])]
    reasons = taxo.ask(('find_facts', {'nature': 'COVERAGE'}))[0]['items']
    said = [item['fact'] for item in reasons if item['fact']['produced_by']['producer_id'] == 'taxo.spring-api']
    assert said[0]['reason'].startswith('Aucun fichier en Java'), 'la raison dit pourquoi rien n a ete lu'


def test_a_python_route_is_not_analysed_never_not_found(taxo_on):
    taxo, _ = taxo_on(PYTHON)
    taxo.analyse()
    verdict, found, described = taxo.ask(('verify_claim', HEALTH), ('find_facts', {'relation': 'HANDLED_BY'}),
                                         ('describe', {}))
    assert (verdict['verdict'], verdict['reason']) == (NOT_PROVEN, NOT_ANALYSED)
    named = {'subject': 'language:Python', 'type': 'NOT_ANALYSED', 'scope': None, 'producer': None,
             'relation': 'HANDLED_BY'}
    assert named in verdict['coverage']
    assert named in found['coverage']
    items = described['items']
    assert {'kind': 'languages', 'present': ['Python'], 'complete': True} in items
    analyzers = {item['analyzer']: item for item in items if item['kind'] == 'analyzer'}
    assert (analyzers['taxo.spring-api']['status'], analyzers['taxo.spring-api']['languages']) == ('UNSUPPORTED', ['Java'])
    assert analyzers['taxo.git']['languages'] is None, 'un analyseur independant du langage le dit'


def test_on_java_and_python_only_java_was_read(taxo_on):
    taxo, _ = taxo_on({**repository(), **PYTHON})
    scan = taxo.analyse()
    assert scan['languages'] == ['Java', 'Python']
    assert evaluations(scan)['taxo.spring-api']['status'] == 'SUCCESS'
    missing = {'subject': 'endpoint:GET /missing', 'relation': 'HANDLED_BY', 'object': 'symbol:java:com.acme.Missing#get()'}
    verdict, = taxo.ask(('verify_claim', missing))
    assert (verdict['verdict'], verdict['reason']) == (NOT_PROVEN, NOT_ANALYSED), 'Python n a pas ete lu'
    assert [entry['subject'] for entry in verdict['coverage'] if entry['type'] == 'NOT_ANALYSED'] == ['language:Python']
    spring = [entry for entry in verdict['coverage'] if entry['producer'] == 'taxo.spring-api']
    assert spring
    assert all(entry['languages'] == ['Java'] for entry in spring), 'sa couverture ne vaut que pour Java'


def test_on_java_alone_an_absent_route_is_still_not_found_in_the_analysed_scope(taxo_on):
    taxo, _ = taxo_on(repository())
    taxo.analyse()
    verdict, = taxo.ask(('verify_claim', {'subject': 'endpoint:GET /missing', 'relation': 'HANDLED_BY',
                                         'object': 'symbol:java:com.acme.Missing#get()'}))
    assert (verdict['verdict'], verdict['reason']) == (NOT_PROVEN, NOT_FOUND_IN_ANALYSED_SCOPE)
    assert not [entry for entry in verdict['coverage'] if entry['type'] == 'NOT_ANALYSED']


def test_an_earlier_analysis_is_read_by_the_contract_of_its_producer(taxo_on, monkeypatch):
    """Une couverture `ANALYSED` du depot ecrite par un catalogue qui lit Java ne justifie pas un « non trouve »
    sur un depot sans Java : elle reste consultable telle quelle, sans etre reecrite ni crue au-dela de son contrat."""
    legacy(monkeypatch)
    taxo, _ = taxo_on(PYTHON)
    scan = taxo.analyse()
    taxo.forget_languages(scan['id'])
    assert evaluations(scan)['taxo.spring-api']['status'] == 'SUCCESS'
    coverage, verdict = taxo.ask(('find_facts', {'relation': 'HANDLED_BY'}), ('verify_claim', HEALTH))
    spring = [entry for entry in coverage['coverage'] if entry['producer'] == 'taxo.spring-api']
    assert [(entry['type'], entry['languages']) for entry in spring] == [('ANALYSED', ['Java'])], \
        'la couverture enregistree reste visible, bornee par le contrat de son producteur'
    assert (verdict['verdict'], verdict['reason']) == (NOT_PROVEN, NOT_ANALYSED)
    assert {'subject': 'language:Python', 'type': 'NOT_ANALYSED', 'scope': None, 'producer': None,
            'relation': 'HANDLED_BY'} in verdict['coverage'], 'les langages relus dans ses faits WRITTEN_IN'


def coverage(kind='ANALYSED'):
    return {'subject': 'repository:r', 'coverage_type': kind, 'scope': {'include': ['repository:r'], 'exclude': []}}


def test_a_negative_verdict_needs_every_concerned_language_read_by_a_capable_execution():
    java = Analyzer('j', frozenset({'HANDLED_BY'}), coverage=(coverage(),), reads=Reads.declared(('Java',)))
    structure = Analyzer('s', frozenset({'CONTAINS'}), coverage=(coverage(),), reads=Reads.declared(('Java', 'Python')))
    unknown = Analyzer('u', frozenset({'HANDLED_BY'}), coverage=(coverage(),), reads=Reads.unknown())
    anywhere = Analyzer('a', frozenset({'HANDLED_BY'}), coverage=(coverage(),))
    unsupported = Analyzer('j', frozenset({'HANDLED_BY'}), coverage=(coverage('OUT_OF_SCOPE'),),
                           reads=Reads.declared(('Java',)), unsupported=True)
    claim = {'subject': 'endpoint:GET /x', 'relation': 'HANDLED_BY'}

    def reason(analyzers, present, needed=None):
        return judge(claim, [], AnalysisKnowledge(present, True, tuple(analyzers)), needed).reason
    assert reason([java], ('Java',)) == NOT_FOUND_IN_ANALYSED_SCOPE
    assert reason([java], ('Java', 'Python')) == NOT_ANALYSED
    assert reason([java, structure], ('Java', 'Python')) == NOT_ANALYSED, \
        'lire Python sans produire HANDLED_BY ne couvre pas une recherche HANDLED_BY'
    assert reason([java], ()) == NOT_ANALYSED, 'aucun langage lu : rien ne justifie un « non trouve »'
    assert reason([unknown], ('Java',)) == NOT_ANALYSED, 'un contrat inconnu ne justifie aucun « non trouve »'
    assert reason([unsupported], ('Python',)) == NOT_ANALYSED
    assert reason([anywhere], ('Java', 'Python')) == NOT_FOUND_IN_ANALYSED_SCOPE, 'independant du langage'
    assert reason([java], ('Java', 'Python'), needed=('Java',)) == NOT_FOUND_IN_ANALYSED_SCOPE, \
        'un sujet situe dans un fichier Java ne concerne que Java'


def test_two_unread_sides_are_never_compared_as_no_change(taxo_on, git, monkeypatch):
    legacy(monkeypatch)
    taxo, root = taxo_on(PYTHON)
    before = taxo.analyse()['id']
    (root / 'api/admin.py').write_text('from api.main import app\n\n@app.get("/api/admin")\ndef admin():\n    pass\n')
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'admin')
    after = taxo.analyse()['id']
    for scan in (before, after):
        taxo.forget_languages(scan)
    compared = taxo.compare(before, after)
    for name in SPRING:
        assert (compared[name]['comparable'], compared[name]['reason']) == (False, 'NOT_SUPPORTED_BEFORE'), name
        assert 'counts' not in compared[name], 'jamais « aucun changement »'
        assert compared[name]['not_analysed'] == {'before': ['Python'], 'after': ['Python']}
    assert compared['taxo.inventory']['comparable']
    assert compared['taxo.inventory']['counts']['ADDED'] > 0
    assert compared['taxo.inventory']['not_analysed'] == {'before': [], 'after': []}
    monkeypatch.undo()
    fresh = taxo.analyse()['id']
    for name, entry in taxo.compare(after, fresh).items():
        if name in SPRING:
            assert (entry['comparable'], entry['reason']) == (False, 'NOT_SUPPORTED_BEFORE'), name


def test_two_producer_versions_of_one_catalog_stay_comparable_with_their_real_changes(taxo_on, git, monkeypatch):
    taxo, root = taxo_on(repository())
    before = taxo.analyse()['id']
    status = root / 'web/src/main/java/com/acme/web/StatusController.java'
    status.write_text(controller('com.acme.web', 'StatusController', '/status'))
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'status')
    monkeypatch.setattr(SpringApiEvaluator, 'producer_version', '9.9.9')
    after = taxo.analyse()['id']
    api = taxo.compare(before, after)['taxo.spring-api']
    assert api['comparable']
    assert api['versions'] == {'before': ['0.2.0'], 'after': ['9.9.9']}
    assert api['relations']['HANDLED_BY']['ADDED'] == 1, 'la nouvelle route, pas « aucun changement »'
    assert api['not_analysed'] == {'before': [], 'after': []}


def test_a_followed_relation_names_the_languages_nobody_read(taxo_on):
    taxo, _ = taxo_on({**repository(), **PYTHON})
    scan = taxo.analyse()
    tile, = taxo.ask(('get_neighborhood', {'analysis': scan['id'], 'root': 'endpoint:GET /orders',
                                           'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}))
    assert {'nature': 'KNOWLEDGE', 'scope': 'ANALYSIS', 'relation': 'HANDLED_BY', 'reason': 'NOT_ANALYSED',
            'languages': ['Python'], 'count': {'kind': 'UNKNOWN'}} in tile['frontier']
    python, _ = taxo_on(PYTHON)
    alone, = python.ask(('get_neighborhood', {'analysis': python.analyse()['id'], 'root': 'endpoint:GET /api/health',
                                              'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}))
    assert any(item['reason'] == 'NO_ANALYZER' and item['relation'] == 'HANDLED_BY' for item in alone['frontier']), \
        'un analyseur qui n avait rien a lire n est pas une capacite'


def test_catalogs_declare_what_they_read():
    """Chaque catalogue declare explicitement les langages qu'il lit, ou qu'il est independant du langage."""
    from app.evaluators.git.catalog import CATALOG as GIT
    from app.evaluators.inventory.catalog import CATALOG as INVENTORY
    from app.evaluators.spring_api.catalog import CATALOG as API
    from app.evaluators.spring_boot.catalog import CATALOG as BOOT
    from app.evaluators.spring_security.catalog import CATALOG as SECURITY
    from app.evaluators.structure.catalog import CATALOG as STRUCTURE
    assert {item.catalog_id: item.languages for item in (GIT, INVENTORY, API, BOOT, SECURITY, STRUCTURE)} == {
        'git': None, 'inventory': None, 'structure': None,
        'spring-api': ('Java',), 'spring-boot': ('Java',), 'spring-security': ('Java',)}


CORE = ('app/evaluations/domain/capability.py', 'app/evaluations/application/run_evaluator.py',
        'app/scans/application/run_scan.py', 'app/protocol/domain/verdict.py', 'app/protocol/application/exchange.py',
        *(f'app/neighborhood/{name}.py' for name in (
            'domain/request', 'domain/budget', 'domain/frontier', 'domain/continuation', 'domain/traversal',
            'application/ports', 'application/tile', 'application/knowledge_frontier')),
        *(f'app/protocol/application/neighborhood_{name}.py' for name in ('operation', 'request', 'view')),
        'app/comparison/domain/comparison.py',
        'app/comparison/application/compare.py', 'app/knowledge/domain/knowledge.py',
        'app/knowledge/application/loader.py', 'app/protocol/application/commits.py',
        'app/protocol/application/arguments.py', 'app/protocol/application/ports.py',
        'app/comparison/application/choices.py', 'app/comparison/application/analyses.py')


def test_the_core_knows_no_language_and_no_analyzer_by_name():
    root = Path(__file__).resolve().parents[1]
    named = re.compile(r'\b(Java|Python|TypeScript|JavaScript|SQL)\b|spring|taxo\.[a-z]')
    found = [(path, line) for path in CORE for line in (root / path).read_text(encoding='utf-8').splitlines()
             if named.search(line)]
    assert found == []


def test_an_unknown_catalog_contract_reads_nothing_known_in_the_neighborhood_too():
    """`None` est reserve a un contrat connu independant du langage ; un contrat inconnu ne lit rien de connu."""
    from app.evaluators.git.evaluator import GitEvaluator
    from app.protocol.application.exchange import TaxoQuery
    query = TaxoQuery(None, None, None, None, [GitEvaluator(), SpringApiEvaluator()], 'off')
    assert query.reads_of({'catalog_id': 'removed', 'catalog_version': '1'}) == Reads.unknown()
    assert query.reads_of({'catalog_id': 'spring-api', 'catalog_version': '1'}) == Reads.unknown()
    # Un resume anterieur ne nomme pas son catalogue : le voisinage le relit dans ses couvertures, jamais dans le
    # catalogue actuel de son analyseur (TAXO-ARCH-REF-01, divergence 3).
    assert query.reads_of({}) == Reads.unknown()
    assert query.reads_of({'catalog_id': 'git', 'catalog_version': GitEvaluator().catalog.catalog_version}) == Reads.any()


def partial_inventory(monkeypatch):
    """Un inventaire qui n'a pas tout lu : ses fichiers Java sont des zones illisibles, sans `WRITTEN_IN`."""
    original = InventoryEvaluator.evaluate

    def evaluate(self, snapshot, *args, **kwargs):
        output = original(self, snapshot, *args, **kwargs)
        java = [fact['subject'] for fact in output.facts
                if fact.get('relation') == 'WRITTEN_IN' and fact['object'] == 'language:Java']
        facts = tuple(fact for fact in output.facts if fact.get('subject') not in java)
        unread = tuple({'contract_version': 1, 'kind': 'COVERAGE', 'status': 'OBSERVED', 'validity': 'VALID',
                        'subject': subject, 'coverage_type': 'READ_ERROR', 'scope': {'include': [subject]}}
                       for subject in java)
        return dataclasses.replace(output, facts=facts, coverage=output.coverage + unread,
                                   status=EvaluationStatus.PARTIAL)
    monkeypatch.setattr(InventoryEvaluator, 'evaluate', evaluate)


def test_a_partial_inventory_never_makes_an_analyzer_unsupported(taxo_on, monkeypatch):
    """Des fichiers que l'inventaire n'a pas lus ont des langages inconnus : leur absence ne se deduit pas."""
    partial_inventory(monkeypatch)
    taxo, _ = taxo_on(repository())
    scan = taxo.analyse()
    assert scan['languages'] == []
    assert evaluations(scan)['taxo.inventory']['status'] == 'PARTIAL'
    spring = evaluations(scan)['taxo.spring-api']
    assert spring['status'] == 'SUCCESS', 'l analyseur a lu ses sources lui-meme'
    assert spring['fact_count'] > 0
    missing = {'subject': 'endpoint:GET /missing', 'relation': 'HANDLED_BY',
               'object': 'symbol:java:com.acme.Missing#get()'}
    verdict, described = taxo.ask(('verify_claim', missing), ('describe', {}))
    assert (verdict['verdict'], verdict['reason']) == (NOT_PROVEN, NOT_ANALYSED), 'des fichiers n ont pas ete lus'
    assert any(entry['subject'] is None and entry['type'] == 'NOT_ANALYSED' and entry['reason']
               for entry in verdict['coverage'])
    assert {'kind': 'languages', 'present': [], 'complete': False} in described['items']
    tile, = taxo.ask(('get_neighborhood', {'analysis': scan['id'], 'root': 'endpoint:GET /orders',
                                           'follow': ['HANDLED_BY'], 'direction': 'OUTGOING'}))
    assert any(item['reason'] == 'LANGUAGES_UNKNOWN' for item in tile['frontier'])


def test_a_partial_inventory_is_never_a_reason_to_refuse_a_comparison(taxo_on, git, monkeypatch):
    partial_inventory(monkeypatch)
    taxo, root = taxo_on(repository())
    before = taxo.analyse()['id']
    (root / 'web/src/main/java/com/acme/web/StatusController.java').write_text(
        controller('com.acme.web', 'StatusController', '/status'))
    git(root, 'add', '-A')
    git(root, 'commit', '-qm', 'status')
    api = taxo.compare(before, taxo.analyse()['id'])['taxo.spring-api']
    assert api['comparable']
    assert api['relations']['HANDLED_BY']['ADDED'] == 1


def coverage_of(taxo, scan_id):
    response = taxo.client.get(f'{taxo.base}/scans/{scan_id}/coverage')
    assert response.status_code == 200, response.text
    found = response.json()
    return found, {item['evaluator_id']: item for item in found['evaluators']}


def test_the_portal_reads_what_each_analyzer_read(taxo_on):
    """Restitution (PR B) : les langages de l'analyse, et pour chaque analyseur ce qu'il lit et n'a pas lu."""
    taxo, _ = taxo_on({**repository(), **PYTHON})
    found, by = coverage_of(taxo, taxo.analyse()['id'])
    assert (found['languages'], found['complete']) == (['Java', 'Python'], True)
    assert by['taxo.spring-api'] == {'evaluator_id': 'taxo.spring-api', 'status': 'SUCCESS', 'contract': 'KNOWN',
                                     'reads': ['Java'], 'unread': ['Python']}
    assert (by['taxo.git']['reads'], by['taxo.git']['unread']) == (None, [])
    python, _ = taxo_on(PYTHON)
    _, alone = coverage_of(python, python.analyse()['id'])
    assert (alone['taxo.spring-security']['status'], alone['taxo.spring-security']['unread']) == ('UNSUPPORTED', ['Python'])


def test_an_earlier_analysis_is_restituted_by_its_recorded_contract(taxo_on, monkeypatch):
    legacy(monkeypatch)
    taxo, _ = taxo_on(PYTHON)
    scan = taxo.analyse()['id']
    taxo.forget_languages(scan)
    with Session(taxo.engine) as db:
        # Avant TAXO-COV-01, le resume d'une execution ne nommait pas son catalogue : il est relu dans ses couvertures.
        row = db.get(ScanRow, scan)
        row.result = {**row.result, 'evaluations': [
            {key: value for key, value in item.items() if key not in ('catalog_id', 'catalog_version')}
            for item in row.result['evaluations']]}
        db.commit()
    found, by = coverage_of(taxo, scan)
    assert found['languages'] == ['Python']
    assert (by['taxo.spring-api']['status'], by['taxo.spring-api']['reads'], by['taxo.spring-api']['unread']) == \
        ('SUCCESS', ['Java'], ['Python']), 'un SUCCESS sans rien a lire reste « Python non analyse »'


def test_an_unknown_contract_reads_nothing_known_in_the_restitution(taxo_on):
    taxo, _ = taxo_on(PYTHON)
    scan = taxo.analyse()['id']
    with Session(taxo.engine) as db:
        row = db.get(ScanRow, scan)
        row.result = {**row.result, 'evaluations': [
            {**item, 'catalog_version': 'retiree'} if item['evaluator_id'] == 'taxo.git' else item
            for item in row.result['evaluations']]}
        db.commit()
    _, by = coverage_of(taxo, scan)
    assert by['taxo.git'] == {'evaluator_id': 'taxo.git', 'status': 'SUCCESS', 'contract': 'UNKNOWN',
                              'reads': [], 'unread': ['Python']}
    assert taxo.client.get(f'{taxo.base}/scans/inconnue/coverage').status_code == 404
