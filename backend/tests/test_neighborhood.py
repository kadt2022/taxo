"""Bounded work and replay on generic persisted graphs; no source repository is read."""
from types import SimpleNamespace
import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, event, text
from app.bootstrap.database import Base
from app.protocol.application.exchange import Exchange
from app.protocol.domain.envelope import size
from app.scans.infrastructure.sqlalchemy.fact_store import SqlAlchemyAnalysisFacts
from test_protocol import taxo_fixture, repo_fixture

ROOT = 'module:root'


def fact(target='module:child', relation='DEPENDS_ON', **extra):
    return {'kind': 'ASSERTION', 'subject': ROOT, 'relation': relation, 'object': target,
            'qualifiers': {}, 'status': 'OBSERVED', 'validity': 'VALID',
            'evidence': [{'path': 'build.gradle', 'line_start': 1, 'method': 'fixture'}],
            'produced_by': {'producer_id': 'fixture', 'catalog_id': 'fixture', 'catalog_version': '1'}, **extra}


@pytest.fixture
def graph(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "graph.db"}')
    Base.metadata.create_all(engine)
    store = SqlAlchemyAnalysisFacts(engine)
    evaluation = {'evaluator_id': 'fixture', 'status': 'SUCCESS',
                  'snapshot': {'repository': 'project', 'commit': 'a' * 40},
                  'coverage': [{'coverage_type': 'ANALYSED', 'count': 1, 'subjects': ['repository:project']}]}
    service = SimpleNamespace(facts=store, source_context='off',
                              catalogs={'fixture': frozenset({'CONTAINS', 'DEPENDS_ON'})})
    scan = SimpleNamespace(id='analysis-1', result={'evaluations': [evaluation]})
    def opened():
        return Exchange(service, 'project', scan, False, 200_000)
    yield store, opened, evaluation, engine
    engine.dispose()


def ask(exchange, **arguments):
    budget = arguments.pop('max_bytes', 20_000)
    result = exchange.call({'operation': 'get_neighborhood', 'max_bytes': budget, 'arguments': {
        'analysis': 'analysis-1', 'root': ROOT, 'follow': ['DEPENDS_ON'], 'direction': 'OUTGOING', **arguments}})
    assert result['bytes'] == size(result)
    if result['outcome'] == 'OK':
        assert result['bytes'] <= budget
    return result


def test_priority_orientation_cycles_replay_and_proof_access(graph):
    store, opened, _, _ = graph
    store.add('analysis-1', 'fixture', [fact('module:z'), fact(ROOT), fact('module:a'), fact('module:b', 'CONTAINS')])
    exchange = opened()
    args = {'follow': ['CONTAINS', 'DEPENDS_ON'], 'priority': ['DEPENDS_ON', 'CONTAINS']}
    result = ask(exchange, **args)
    assert [x['fact']['object'] for x in result['items']] == ['module:a', ROOT, 'module:z', 'module:b']
    assert result['nodes'].count(ROOT) == 1
    assert result['stop_reason'] == 'ADJACENCY_COMPLETE' and result['continuation'] is None
    assert ask(opened(), **args) == result
    inverse = ask(opened(), root='module:a', direction='INCOMING')
    assert [(x['fact']['subject'], x['fact']['object']) for x in inverse['items']] == [(ROOT, 'module:a')]
    proof = exchange.call({'operation': 'get_evidence', 'arguments': {'fact': result['items'][0]['ref']}})
    assert proof['evidence'][0]['location']['path'] == 'build.gradle'


def test_high_degree_reprise_never_loads_the_adjacency(graph):
    store, opened, _, engine = graph
    store.add('analysis-1', 'fixture', [fact(f'module:{i:04}') for i in reversed(range(1000))])
    statements = []
    event.listen(engine, 'before_cursor_execute', lambda conn, cur, sql, params, ctx, many: statements.append(sql))
    result = ask(opened(), max_edges=2, max_work=2)
    assert result['consumed']['work'] == 2
    assert [x['fact']['object'] for x in result['items']] == ['module:0000', 'module:0001']
    following = ask(opened(), continuation=result['continuation'], max_edges=2, max_work=2)
    assert [x['fact']['object'] for x in following['items']] == ['module:0002', 'module:0003']
    assert all('LIMIT' in sql for sql in statements if sql.lstrip().startswith('SELECT'))
    assert ask(opened(), root='module:0000', continuation=result['continuation'])['error']['code'] == 'INVALID_ARGUMENT'


def test_node_and_byte_cuts_retain_the_refused_edge(graph):
    store, opened, _, _ = graph
    store.add('analysis-1', 'fixture', [fact('module:a'), fact('module:b')])
    limited = ask(opened(), max_nodes=1)
    assert limited['items'] == [] and limited['stop_reason'] == 'NODES'
    assert limited['frontier'][-1]['count'] == {'kind': 'AT_LEAST', 'value': 1}
    assert len(ask(opened(), continuation=limited['continuation'])['items']) == 2
    assert ask(opened(), max_bytes=100)['error']['code'] == 'BUDGET_EXHAUSTED'
    store.add('analysis-1', 'fixture', [fact('module:c', qualifiers={'label': 'x' * 6000})])
    exchange = opened()
    bounded = ask(exchange, max_bytes=4500)
    assert bounded['stop_reason'] == 'BYTES'
    assert len(bounded['items']) == len(exchange.refs.facts) == 2
    resumed = ask(opened(), continuation=bounded['continuation'])
    assert [x['fact']['object'] for x in resumed['items']] == ['module:c']


def test_work_empty_context_knowledge_and_analysis_boundaries(graph):
    store, opened, evaluation, _ = graph
    store.add('analysis-1', 'fixture', [fact()])
    store.add('analysis-2', 'fixture', [fact('module:foreign')])
    result = ask(opened(), follow=['CONTAINS', 'DEPENDS_ON'], max_work=1)
    assert result['items'] == [] and result['stop_reason'] == 'WORK'
    resumed = ask(opened(), follow=['CONTAINS', 'DEPENDS_ON'], continuation=result['continuation'])
    assert [x['fact']['object'] for x in resumed['items']] == ['module:child']
    assert ask(opened(), root='module:missing')['stop_reason'] == 'ROOT_UNKNOWN'
    empty = ask(opened(), follow=['CONTAINS'])
    assert empty['items'] == [] and empty['anchor']['known']
    assert not any(x['nature'] == 'CONTEXT' for x in empty['frontier'])
    assert ask(opened(), follow=['CALLS'])['frontier'][0]['nature'] == 'CONTEXT'
    evaluation['coverage'].append({'coverage_type': 'NOT_INTERPRETED', 'count': 10, 'subjects': ['file:x']})
    assert any(x['nature'] == 'KNOWLEDGE' for x in ask(opened())['frontier'])
    assert ask(opened(), root='repository:foreign')['error']['code'] == 'OUT_OF_SCOPE'
    assert ask(opened(), analysis='analysis-2')['error']['code'] == 'INVALID_ARGUMENT'


@pytest.mark.parametrize('args', [{'follow': []}, {'follow': ['NO_RELATION']}, {'follow': ['CALLS', 'CALLS']},
    {'priority': ['CONTAINS']}, {'priority': [{}]}, {'direction': 'BOTH'}, {'depth': 2}, {'depth': True},
    {'max_work': 0}, {'max_nodes': -1}, {'max_edges': 201}, {'continuation': 'invalid'}, {'extra': 1}])
def test_bad_arguments_are_refused(graph, args):
    assert ask(graph[1](), **args)['error']['code'] == 'INVALID_ARGUMENT'


def test_migration_backfill_and_downgrade_preserve_existing_facts(tmp_path):
    url = f'sqlite:///{tmp_path / "migrate.db"}'
    env = {**os.environ, 'DATABASE_URL': url}
    def migrate(action, target):
        subprocess.run([sys.executable, '-m', 'alembic', action, target], check=True, env=env, capture_output=True)
    migrate('upgrade', '002')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text('INSERT INTO analysis_facts (scan_id,evaluator_id,kind,subject,relation,object,fact) '
                        'VALUES (:scan,:eval,:kind,:subject,:relation,:object,:fact)'),
                   {'scan': 'analysis-1', 'eval': 'fixture', 'kind': 'ASSERTION', 'subject': ROOT,
                    'relation': 'DEPENDS_ON', 'object': 'module:child', 'fact': json.dumps(fact())})
    migrate('upgrade', 'head')
    assert SqlAlchemyAnalysisFacts(engine).neighbor('analysis-1', ROOT, 'DEPENDS_ON', 'OUTGOING')[1] == fact()
    migrate('downgrade', '002')
    with engine.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM analysis_facts')) == 1
    engine.dispose()


def test_http_analysis_pinning(taxo):
    client, url, _ = taxo
    described = client.post(url, json={'requests': [{'operation': 'describe'}]}).json()
    analysis = described['snapshot']['analysis']
    listed = client.post(url, json={'requests': [{'operation': 'find_facts',
                         'arguments': {'relation': 'CONTAINS'}}]}).json()
    root = listed['responses'][0]['items'][0]['fact']['subject']
    response = client.post(url, json={'analysis': analysis, 'requests': [{'operation': 'get_neighborhood',
        'arguments': {'analysis': analysis, 'root': root, 'follow': ['CONTAINS'], 'direction': 'OUTGOING'}}]})
    assert response.status_code == 200 and response.json()['responses'][0]['items']
    assert client.post(url, json={'analysis': 'foreign', 'requests': [{'operation': 'describe'}]}).status_code == 409


def test_long_unicode_references_keep_canonical_order_and_resume(graph):
    store, opened, _, _ = graph
    # Long and varied: compression must not be relied on to fit a database index.
    root = 'module:' + ''.join(chr(0x4e00 + i) for i in range(850))
    prefix = 'module:' + ''.join(chr(0x5000 + i) for i in range(850))
    targets = [prefix + suffix for suffix in ('z', '\U00010000', '\ue000', '')]
    store.add('analysis-1', 'fixture', [fact(target, subject=root) for target in targets])
    expected = sorted(targets, key=lambda value: value.encode('utf-16-be'))
    pages = [ask(opened(), root=root, max_edges=2, max_bytes=32_000)]
    while pages[-1]['continuation'] is not None:
        assert len(pages) <= len(targets)
        pages.append(ask(opened(), root=root, continuation=pages[-1]['continuation'], max_bytes=32_000))
    assert [item['fact']['object'] for page in pages for item in page['items']] == expected
    assert store.has_reference('analysis-1', root)
    assert store.neighbor('analysis-1', targets[0], 'DEPENDS_ON', 'INCOMING')[1]['subject'] == root


def test_fact_append_invalidates_continuation_and_reorders_new_selection(graph):
    store, opened, _, _ = graph
    store.add('analysis-1', 'fixture', [fact('module:b'), fact('module:c')])
    first = ask(opened(), max_edges=1)
    store.add('analysis-1', 'fixture', [fact('module:a')])
    refused = ask(opened(), continuation=first['continuation'])
    assert refused['error']['code'] == 'INVALID_ARGUMENT'
    fresh = ask(opened())
    assert fresh['facts_revision'] > first['facts_revision']
    assert [item['fact']['object'] for item in fresh['items']] == ['module:a', 'module:b', 'module:c']


def test_fact_append_during_selection_refuses_mixed_page(graph, monkeypatch):
    store, opened, _, _ = graph
    store.add('analysis-1', 'fixture', [fact()])
    neighbor = store.neighbor
    def mutate(*args, **kwargs):
        result = neighbor(*args, **kwargs)
        store.add('analysis-1', 'fixture', [fact('module:a')])
        return result
    monkeypatch.setattr(store, 'neighbor', mutate)
    exchange = opened()
    assert ask(exchange, max_edges=1)['error']['code'] == 'INVALID_ARGUMENT'
    assert not exchange.refs.facts


def test_reference_hash_collision_never_returns_another_anchor(graph, monkeypatch):
    from app.scans.infrastructure.sqlalchemy import fact_store
    monkeypatch.setattr(fact_store, '_reference_hash', lambda reference: '0' * 64)
    store, opened, _, _ = graph
    store.add('analysis-1', 'fixture', [fact('module:a', subject='module:other'), fact('module:b')])
    result = ask(opened())
    assert [item['fact']['object'] for item in result['items']] == ['module:b']
    assert not store.has_reference('analysis-1', 'module:missing')


def test_frozen_migration_order_matches_v1_without_application_imports():
    import ast
    import importlib.util
    from pathlib import Path
    from app.scans.domain.fact_order import adjacency_keys
    path = Path(__file__).parents[1] / 'migrations/versions/003_adjacency.py'
    tree = ast.parse(path.read_text())
    assert not any(isinstance(node, ast.ImportFrom) and (node.module or '').startswith('app.')
                   for node in ast.walk(tree))
    spec = importlib.util.spec_from_file_location('migration003', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    samples = [fact('module:e\u0301'),
               {'kind': 'ABSENCE', 'pattern': {'relation': 'CALLS'}, 'method': 'fixture',
                'scope': {'include': ['module:b', 'module:a', 'module:b'], 'exclude': []}},
               {'kind': 'COVERAGE', 'subject': ROOT, 'coverage_type': 'ANALYSED',
                'scope': {'include': ['module:\U00010000', 'module:\ue000']},
                'produced_by': {'producer_id': 'fixture'}}]
    for sample in samples:
        assert migration._keys(sample) == adjacency_keys(sample)
