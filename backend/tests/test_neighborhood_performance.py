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

from test_neighborhood_conformance import Twin, edge

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
    return [sql for sql in statements if 'outgoing_rank' in sql and sql.lstrip().upper().startswith('SELECT')]


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
