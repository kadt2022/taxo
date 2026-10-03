"""TAXO-01J : un nœud à fort degré n'est jamais lu en entier, et le coût d'une Tuile ne dépend pas du degré.

Le garde-fou permanent compte les requêtes SQL : à budgets égaux, une Tuile autour d'un nœud de degré 200 et
autour d'un nœud de degré 2 000 en fait exactement autant, et chaque lecture d'adjacence est bornée.

La mesure lourde (100 000 occurrences, un nœud de degré 50 000) est lancée à la demande,
`TAXO_PERFORMANCE=1` : ses chiffres sont consignés dans le récit TAXO-01J. Ce sont des mesures, jamais des
promesses.
"""
import os
import time

import pytest
from sqlalchemy import event

from test_neighborhood_conformance import STORAGES, Twin, edge

HUB = 'module:hub'


def graph(degree):
    """Un nœud de fort degré, dont chaque voisin a deux voisins à son tour : trois niveaux à parcourir."""
    facts = [edge(f'module:n{index:06}', subject=HUB) for index in range(degree)]
    facts += [edge(f'module:m{index:06}-{side}', subject=f'module:n{index:06}') for index in range(20) for side in 'ab']
    return facts


def measured(twin, **arguments):
    statements = []
    engine = twin.engines['fact_memory']

    def count(conn, cursor, sql, *rest):
        statements.append(sql)
    event.listen(engine, 'before_cursor_execute', count)
    started = time.perf_counter()
    try:
        result = twin.ask(twin.exchange('fact_memory'), root=HUB, engine='neighborhood/2', **arguments)
    finally:
        event.remove(engine, 'before_cursor_execute', count)
    return result, statements, time.perf_counter() - started


def adjacency(statements):
    """Les lectures de page d'une adjacence : celles qui bornent le rang."""
    return [sql for sql in statements if 'outgoing_rank >' in sql and sql.lstrip().upper().startswith('SELECT')]


def test_the_cost_of_a_tile_does_not_depend_on_the_degree(tmp_path):
    found = {}
    for degree in (200, 2000):
        (tmp_path / str(degree)).mkdir()
        twin = Twin(tmp_path / str(degree))
        twin.add(graph(degree))
        result, statements, _ = measured(twin, depth=3, max_fanout=10, max_edges=60, max_work=40, max_bytes=32_000)
        reads = adjacency(statements)
        assert len(reads) == result['consumed']['work'], 'chaque lecture d’adjacence compte pour un travail'
        assert all('LIMIT' in sql for sql in reads), 'aucune lecture sans borne'
        found[degree] = (len(statements), result['consumed'], [item['fact']['object'] for item in result['items']])
    assert found[200] == found[2000]


def _sqlite_bounded(plan):
    """SQLite ne dit pas les lignes lues : le plan doit le prouver par sa forme. Aucune table parcourue en entier ;
    l'adjacence lue par son index d'ancre, rang compris ; aucun tri sous la lecture de l'adjacence (un tri de la
    page chargée, au plus sa borne, est permis)."""
    parents = {node: parent for node, parent, _, _ in plan}
    detail = {node: text for node, _, _, text in plan}

    def under(node, ancestor):
        while node in parents:
            if node == ancestor:
                return True
            node = parents[node]
        return False
    reads = [node for node, text in detail.items() if 'outgoing_rank>?' in text or 'incoming_rank>?' in text]
    assert reads, plan
    assert not any(text.startswith('SCAN') for text in detail.values()), plan
    for read in reads:
        assert 'INDEX ix_fact_occurrences_' in detail[read] or 'INDEX ix_analysis_facts' in detail[read], plan
        scope = parents[read]
        assert not any('TEMP B-TREE' in text and under(node, scope) and scope != 0
                       for node, text in detail.items()), plan
    return True


def _plan_rows(node):
    """Les lignes que chaque nœud du plan PostgreSQL a réellement produites, boucles comprises, par table."""
    rows = []
    if 'Relation Name' in node:
        rows.append((node['Relation Name'], node['Actual Rows'] * node.get('Actual Loops', 1)))
    for child in node.get('Plans', []):
        rows += _plan_rows(child)
    return rows


@pytest.mark.parametrize('name', STORAGES)
def test_an_adjacency_read_touches_its_page_only_in_the_engine_plan(tmp_path, name):
    """Le garde-fou précédent vérifie que chaque lecture porte une borne ; celui-ci vérifie ce que le moteur de
    base de données lit vraiment. Sur PostgreSQL, un plan qui joint toutes les identités avant la borne lirait
    l'adjacence entière d'un nœud de fort degré (constaté sur un dépôt réel, TAXO-01J tranche F)."""
    twin = Twin(tmp_path)
    # Un nœud de degré 1 000 parmi 10 000 occurrences : les proportions d'un dépôt réel (spring-petclinic).
    twin.add(graph(1000) + [edge(f'module:x{index:05}', subject=f'module:y{index % 500:03}') for index in range(9000)])
    engine = twin.engines[name]
    reads = []

    def keep(conn, cursor, sql, parameters, context, many):
        if 'outgoing_rank >' in sql or 'incoming_rank >' in sql:
            reads.append((sql, parameters))
    event.listen(engine, 'before_cursor_execute', keep)
    try:
        twin.ask(twin.exchange(name), root=HUB, engine='neighborhood/2', depth=1, max_fanout=10)
    finally:
        event.remove(engine, 'before_cursor_execute', keep)
    assert reads
    with engine.connect() as connection:
        if engine.dialect.name == 'postgresql':
            # Les statistiques que l'autovacuum tient à jour en service : sans elles, le planificateur ne voit pas
            # qu'un sujet porte des milliers d'identités, et le plan d'une base neuve ne dit rien du réel.
            connection.exec_driver_sql('ANALYZE')
        for sql, parameters in reads:
            if engine.dialect.name == 'postgresql':
                (plan,), = connection.exec_driver_sql('EXPLAIN (ANALYZE, FORMAT JSON) ' + sql, parameters).all()
                touched = _plan_rows(plan[0]['Plan'])
                assert all(count <= 50 for _, count in touched), touched
            else:
                assert _sqlite_bounded([tuple(row) for row in
                                        connection.exec_driver_sql('EXPLAIN QUERY PLAN ' + sql, parameters)])


@pytest.mark.skipif(os.environ.get('TAXO_PERFORMANCE') != '1', reason='mesure lourde à la demande : TAXO_PERFORMANCE=1')
def test_a_tile_around_a_node_of_degree_fifty_thousand(tmp_path, capsys):
    twin = Twin(tmp_path)
    started = time.perf_counter()
    facts = graph(50_000) + [edge(f'module:x{index:06}', subject=f'module:y{index % 1000:04}')
                             for index in range(50_000)]
    twin.stores['fact_memory'].add('analysis-1', 'fixture', facts)
    ingestion = time.perf_counter() - started
    rows = []
    for arguments in ({'depth': 3, 'max_fanout': 20, 'max_nodes': 200, 'max_edges': 400, 'max_work': 2000},
                      {'depth': 1, 'max_nodes': 200, 'max_edges': 400, 'max_work': 2000},
                      {'depth': 3, 'max_fanout': 10, 'max_nodes': 200, 'max_edges': 60, 'max_work': 100,
                       'evidence': 'SUMMARY'}):
        result, statements, elapsed = measured(twin, **arguments, max_bytes=32_000)
        assert len(adjacency(statements)) == result['consumed']['work']
        rows.append((arguments, round(elapsed * 1000), len(statements), result['consumed'], result['bytes'],
                     result['stop_reason']))
    with capsys.disabled():
        print(f'\ningestion de {len(facts)} occurrences : {ingestion:.1f} s')
        for row in rows:
            print('  {} : {} ms, {} requêtes, consommé {}, {} octets, arrêt {}'.format(*row))
