"""TAXO-01F : comparer deux analyses depuis la memoire, sans relire le depot.

Banc Git scenarise. La verite de chaque transition est ecrite ici a la main, a partir de ce qui change
dans les fichiers, jamais a partir de ce que Taxo en dit :

  A  le depot de reference (deux applications, des routes protegees) ;
  B  A + une route GET /status, et OrderController decale de trois lignes ;
  C  B, la regle de la boutique devient hasRole("USER") et UserAdminController disparait.
"""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.bootstrap.database import Base
from app.evaluations.domain.evaluator import EvaluatorCatalog
from app.evaluators.spring_security.evaluator import SpringSecurityEvaluator
from app.main import create_app
from test_spring_boot import controller, repository, security

ORDERS = 'web/src/main/java/com/acme/web/OrderController.java'
STATUS = 'web/src/main/java/com/acme/web/StatusController.java'
SHOP_SECURITY = 'security/src/main/java/com/acme/security/ShopSecurity.java'
ADMIN_CONTROLLER = 'admin/src/main/java/com/acme/admin/UserAdminController.java'
CATEGORIES = ('ADDED', 'REMOVED', 'MODIFIED', 'EVIDENCE_CHANGED', 'STATUS_CHANGED', 'OCCURRENCE_COUNT_CHANGED',
              'OCCURRENCES_CHANGED')


class Bench:
    def __init__(self, client, base, engine, commits):
        self.client, self.base, self.engine, self.commits = client, base, engine, commits

    def analyse(self, commit):
        return self.client.post(f'{self.base}/scans', params={'commit': self.commits[commit]}).json()['id']

    def summary(self, before, after):
        response = self.client.get(f'{self.base}/comparisons', params={'before': before, 'after': after})
        assert response.status_code == 200, response.text
        return response.json()

    def changes(self, before, after, category):
        """Every item of a category, for every comparable evaluator, following the pages."""
        items = []
        for evaluator in self.summary(before, after)['evaluators']:
            if not evaluator['comparable']:
                continue
            cursor = None
            while True:
                params = {'before': before, 'after': after, 'evaluator': evaluator['evaluator_id'],
                          'category': category, 'limit': 3, **({'cursor': cursor} if cursor else {})}
                page = self.client.get(f'{self.base}/comparisons/changes', params=params).json()
                items += page['items']
                cursor = page['next']
                if cursor is None:
                    break
        return items


@pytest.fixture(scope='module')
def bench(tmp_path_factory):
    from conftest import run_git
    root = tmp_path_factory.mktemp('bench') / 'shop'
    root.mkdir()
    run_git(root, 'init', '-q')
    states = {
        'A': repository(),
        'B': repository(**{STATUS: controller('com.acme.web', 'StatusController', '/status'),
                           ORDERS: '\n\n\n' + controller('com.acme.web', 'OrderController', '/orders')}),
    }
    states['C'] = {**states['B'], SHOP_SECURITY: security('com.acme.security', 'ShopSecurity', 'hasRole("USER")')}
    del states['C'][ADMIN_CONTROLLER]
    commits = {}
    for name, files in states.items():
        for path in run_git(root, 'ls-files').splitlines():
            if path not in files:
                (root / path).unlink()
        for path, content in files.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(content)
        run_git(root, 'add', '-A')
        run_git(root, 'commit', '-qm', name)
        commits[name] = run_git(root, 'rev-parse', 'HEAD')
    app = create_app(f'sqlite:///{tmp_path_factory.mktemp("db") / "bench.db"}', [root])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Boutique', 'path': str(root)}).json()
        bench = Bench(client, f'/api/projects/{project["id"]}', app.state.engine, commits)
        bench.scans = {name: bench.analyse(name) for name in 'ABC'}
        yield bench


def concerns(fact, *needles):
    text_of_fact = ' '.join(str(fact.get(key, '')) for key in ('subject', 'object'))
    return any(needle in text_of_fact for needle in needles)


def paths(item):
    return {proof.get('path') for side in ('before', 'after') for fact in item[side] for proof in fact.get('evidence', [])}


def test_a_to_b_a_route_appears_and_a_controller_moves(bench):
    a, b = bench.scans['A'], bench.scans['B']
    totals = bench.summary(a, b)['totals']
    assert totals['REMOVED'] == totals['MODIFIED'] == totals['STATUS_CHANGED'] == 0
    added = [fact for item in bench.changes(a, b, 'ADDED') for fact in item['after']]
    assert any(fact['subject'] == 'endpoint:GET /status' and fact['relation'] == 'HANDLED_BY' for fact in added)
    # Ce qui est nouveau est la route /status, son fichier, ou le commit B lui-meme dans l'historique.
    assert all(concerns(fact, 'status', 'Status', bench.commits['B']) for fact in added), \
        [fact for fact in added if not concerns(fact, 'status', 'Status', bench.commits['B'])]
    moved = bench.changes(a, b, 'EVIDENCE_CHANGED')
    assert any(item['before'][0]['subject'] == 'endpoint:GET /orders' and item['before'][0]['relation'] == 'HANDLED_BY'
               for item in moved)
    # Une preuve ne peut bouger que dans un fichier modifie.
    assert all(ORDERS in paths(item) for item in moved), [paths(item) for item in moved]
    assert totals['EVIDENCE_CHANGED'] == len(moved)


def test_b_to_c_a_rule_changes_and_a_route_disappears(bench):
    b, c = bench.scans['B'], bench.scans['C']
    removed = [fact for item in bench.changes(b, c, 'REMOVED') for fact in item['before']]
    assert any(fact['subject'] == 'endpoint:GET /admin/users' for fact in removed)
    assert all(concerns(fact, 'admin/users', 'UserAdminController') for fact in removed), \
        [fact for fact in removed if not concerns(fact, 'admin/users', 'UserAdminController')]
    modified = {(item['before'][0]['subject'], item['before'][0]['relation'], item['before'][0]['object'],
                 item['after'][0]['object']) for item in bench.changes(b, c, 'MODIFIED')}
    for route in ('endpoint:GET /orders', 'endpoint:GET /status'):
        assert (route, 'PROTECTED_BY', 'policy-rule:authenticated()', 'policy-rule:hasRole("USER")') in modified
    added = [fact for item in bench.changes(b, c, 'ADDED') for fact in item['after']]
    assert all(concerns(fact, bench.commits['C'], 'hasRole("USER")', 'ShopSecurity') for fact in added), \
        [fact for fact in added if not concerns(fact, bench.commits['C'], 'hasRole("USER")', 'ShopSecurity')]


def test_direction_swaps_added_and_removed_only(bench):
    a, b = bench.scans['A'], bench.scans['B']
    forward, backward = bench.summary(a, b)['totals'], bench.summary(b, a)['totals']
    assert (forward['ADDED'], forward['REMOVED']) == (backward['REMOVED'], backward['ADDED'])
    for name in ('MODIFIED', 'EVIDENCE_CHANGED', 'STATUS_CHANGED', 'UNCHANGED'):
        assert forward[name] == backward[name]


def test_a_to_c_combines_both_transitions(bench):
    a, c = bench.scans['A'], bench.scans['C']
    removed = {fact['subject'] for item in bench.changes(a, c, 'REMOVED') for fact in item['before']}
    added = {fact['subject'] for item in bench.changes(a, c, 'ADDED') for fact in item['after']}
    assert 'endpoint:GET /admin/users' in removed
    assert 'endpoint:GET /status' in added


def test_the_same_commit_analysed_twice_has_no_change(bench):
    again = bench.analyse('A')
    summary = bench.summary(bench.scans['A'], again)
    assert all(summary['totals'][name] == 0 for name in CATEGORIES)
    assert summary['totals']['UNCHANGED'] > 0


def test_a_new_catalog_is_not_comparable_and_nothing_else_moves(bench, monkeypatch):
    monkeypatch.setattr(SpringSecurityEvaluator, 'catalog', EvaluatorCatalog(
        SpringSecurityEvaluator.catalog.catalog_id, '999', SpringSecurityEvaluator.catalog.relations,
        SpringSecurityEvaluator.catalog.coverage_types))
    again = bench.analyse('A')
    summary = bench.summary(bench.scans['A'], again)
    security_entry = next(item for item in summary['evaluators'] if item['evaluator_id'] == 'taxo.spring-security')
    assert security_entry == {**security_entry, 'comparable': False, 'reason': 'CATALOG_CHANGED'}
    assert 'évolution du producteur' in security_entry['message']
    assert all(summary['totals'][name] == 0 for name in CATEGORIES)


def test_a_failed_execution_is_not_comparable(bench, monkeypatch):
    def broken(self, snapshot):
        raise RuntimeError('panne')
    monkeypatch.setattr(SpringSecurityEvaluator, 'evaluate', broken)
    again = bench.analyse('A')
    entry = next(item for item in bench.summary(bench.scans['A'], again)['evaluators']
                 if item['evaluator_id'] == 'taxo.spring-security')
    assert (entry['comparable'], entry['reason']) == (False, 'FAILED_AFTER')


def test_comparing_never_reads_the_repository(bench, monkeypatch):
    from app.evaluations.application.run_evaluator import RunEvaluator
    from app.snapshots.infrastructure.git.reader import GitSnapshotReader
    monkeypatch.setattr(GitSnapshotReader, 'open', lambda *a, **k: pytest.fail('dépôt relu'))
    monkeypatch.setattr(RunEvaluator, '__call__', lambda *a, **k: pytest.fail('évaluateur relancé'))
    assert bench.summary(bench.scans['A'], bench.scans['C'])['totals']['ADDED'] > 0
    assert bench.changes(bench.scans['A'], bench.scans['C'], 'MODIFIED')


def test_unknown_or_foreign_analyses_are_refused(bench):
    assert bench.client.get(f'{bench.base}/comparisons', params={'before': bench.scans['A'], 'after': 'x'}).status_code == 404
    response = bench.client.get(f'{bench.base}/comparisons/changes', params={
        'before': bench.scans['A'], 'after': bench.scans['B'], 'evaluator': 'taxo.inventory', 'category': 'NOPE'})
    assert response.status_code == 422


def test_reads_are_bound_to_the_two_analyses(bench):
    """A third analysis, whatever its size, is never walked: every read of the memory goes through an index
    bound to one of the two analyses (scan_id, id) or to an identity on the other side (identity_hash, scan_id)."""
    statements = []
    listen = lambda conn, cursor, sql, params, context, many: statements.append((sql, params))
    event.listen(bench.engine, 'before_cursor_execute', listen)
    try:
        a, c = bench.scans['A'], bench.scans['C']
        bench.summary(a, c)
        bench.changes(a, c, 'MODIFIED')
    finally:
        event.remove(bench.engine, 'before_cursor_execute', listen)
    walked = []
    with bench.engine.connect() as connection:
        for sql, params in statements:
            if not sql.lstrip().upper().startswith('SELECT') or 'fact_occurrences' not in sql:
                continue
            for row in connection.exec_driver_sql('EXPLAIN QUERY PLAN ' + sql, params).all():
                if re.match(r'SCAN (fact_occurrences|fact_identities|fact_evidence)', row[-1]):
                    walked.append((row[-1], sql))
    assert walked == []
