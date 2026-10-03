"""TAXO-01J : `find_references`, chercher une référence d'une analyse par le début de sa clé.

La vérité est écrite à la main : quelles références commencent par quel préfixe, dans quel ordre. Les deux
stockages rendent la même liste ; la mémoire versionnée par une lecture indexée bornée.
"""
import os
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text

from app.facts import is_reference
from app.neighborhood.domain.references import fold
from test_neighborhood_conformance import STORAGES, Twin, edge

LONG = 'module:' + 'p' * 300
REFERENCES = ['module:Orders', 'module:orders-api', 'module:ordinal', 'module:Straße', 'module:strasse-x',
              'file:orders/Order.java', LONG + 'a', LONG + 'b', 'module:o\u0301rders',
              *(f'module:queue-{index:02}' for index in range(20))]


@pytest.fixture
def twin(tmp_path):
    found = Twin(tmp_path)
    found.add([edge(target, 'CONTAINS' if target.startswith('file:') else 'DEPENDS_ON', subject='module:root')
               for target in REFERENCES])
    return found


def search(twin, name, **arguments):
    exchange = twin.exchange(name)
    return exchange.call({'operation': 'find_references', 'max_bytes': arguments.pop('max_bytes', 20_000),
                          'arguments': {'analysis': 'analysis-1', **arguments}})


def found(result):
    return [item['reference'] for item in result['items']]


def all_pages(twin, name, **arguments):
    pages, after = [], None
    while True:
        result = search(twin, name, **arguments, **({'after': after} if after else {}))
        assert result['outcome'] == 'OK', result
        pages.append(found(result))
        after = result['next']
        if after is None:
            return pages
        assert len(pages) < 20


@pytest.mark.parametrize('name', STORAGES)
def test_a_prefix_finds_every_reference_whose_key_starts_with_it_in_key_order(twin, name):
    # Ordre des clés repliées : « orders », « orders-api », « orders/order.java » (« - » avant « / »), « ordinal ».
    assert found(search(twin, name, prefix='ord')) == ['module:Orders', 'module:orders-api', 'file:orders/Order.java',
                                                       'module:ordinal'], 'la casse ne compte pas'
    assert found(search(twin, name, prefix='ORDERS')) == ['module:Orders', 'module:orders-api',
                                                          'file:orders/Order.java']
    assert found(search(twin, name, prefix='ord', type='module')) == ['module:Orders', 'module:orders-api',
                                                                      'module:ordinal']
    assert found(search(twin, name, prefix='strasse')) == ['module:Straße', 'module:strasse-x'], 'ß se replie en ss'
    assert found(search(twin, name, prefix='ór')) == ['module:órders'], 'NFD et NFC se comparent pareil'
    assert found(search(twin, name, prefix='zzz')) == []
    assert search(twin, name, prefix='root')['items'] == [{'reference': 'module:root', 'type': 'module'}]


@pytest.mark.parametrize('name', STORAGES)
def test_references_that_differ_after_the_index_key_are_both_found(twin, name):
    assert sorted(found(search(twin, name, prefix='p' * 200))) == [LONG + 'a', LONG + 'b']


@pytest.mark.parametrize('name', STORAGES)
def test_paging_reaches_every_match_once_in_order(twin, name):
    pages = all_pages(twin, name, prefix='o', limit=2)
    flat = [reference for page in pages for reference in page]
    assert flat == found(search(twin, name, prefix='o', limit=50))
    assert len(flat) == len(set(flat)) == 4, 'ó (o et l’accent combinant, en NFC) ne commence pas par o'
    assert [len(page) for page in pages] == [2, 2]


@pytest.mark.parametrize('name', STORAGES)
def test_a_small_budget_sends_fewer_references_and_resumes_after_the_last_sent(twin, name):
    whole = search(twin, name, prefix='q', limit=50)
    complete, budget = found(whole), whole['bytes'] - 1
    assert len(complete) == 20
    pages, after = [], None
    while True:
        result = search(twin, name, prefix='q', limit=50, max_bytes=budget, **({'after': after} if after else {}))
        assert result['outcome'] == 'OK'
        assert result['bytes'] <= budget, 'la reprise est mesurée avec la page'
        pages.append(found(result))
        after = result['next']
        if after is None:
            break
    assert [reference for page in pages for reference in page] == complete
    assert len(pages) > 1
    one = search(twin, name, prefix='p', limit=1, max_bytes=search(twin, name, prefix='p', limit=1)['bytes'] - 1)
    assert one['error']['code'] == 'BUDGET_EXHAUSTED', 'pas une seule référence avec sa reprise : refusé, jamais vide'


@pytest.mark.parametrize('name', STORAGES)
def test_a_continuation_is_bound_to_its_analysis_generation_prefix_and_type(twin, name):
    token = search(twin, name, prefix='o', limit=1)['next']
    assert search(twin, name, prefix='o', after=token)['outcome'] == 'OK'
    for arguments in ({'prefix': 'or', 'after': token}, {'prefix': 'o', 'type': 'module', 'after': token},
                      {'prefix': 'o', 'after': 'invalid'}):
        assert search(twin, name, **arguments)['error']['code'] == 'INVALID_ARGUMENT'
    twin.add([edge('module:other', subject='module:root')])
    assert search(twin, name, prefix='o', after=token)['error']['code'] == 'INVALID_ARGUMENT'


@pytest.mark.parametrize('arguments', [{'prefix': ''}, {'prefix': 'x' * 201}, {'prefix': 3},
                                       {'prefix': 'a', 'limit': 0},
                                       {'prefix': 'a', 'limit': 51}, {'prefix': 'a', 'type': 'nope'},
                                       {'prefix': 'a', 'analysis': 'analysis-2'}, {'prefix': 'a', 'extra': 1}])
def test_bad_searches_are_refused(twin, arguments):
    assert search(twin, 'fact_memory', **arguments)['error']['code'] == 'INVALID_ARGUMENT'


def test_the_versioned_memory_reads_a_bounded_index_range_never_the_facts(twin):
    statements = []
    engine = twin.engines['fact_memory']
    event.listen(engine, 'before_cursor_execute', lambda conn, cur, sql, *rest: statements.append(sql))
    search(twin, 'fact_memory', prefix='ord', limit=2)
    reads = [sql for sql in statements if 'analysis_references' in sql]
    assert len(reads) == 1, 'une seule lecture pour la recherche'
    assert 'LIMIT' in reads[0], 'une plage bornée de l’index'
    assert 'fact_identities' not in reads[0], 'jamais les faits'


MIGRATION = Path(__file__).parents[1] / 'migrations/versions/008_analysis_references.py'


def frozen():
    spec = spec_from_file_location('migration008', MIGRATION)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_frozen_rules_of_the_migration_agree_with_the_application():
    migration = frozen()
    samples = ['module:a', 'file:src/A.java', 'endpoint:GET /orders', 'symbol:java:A#b()', 'policy-rule:x',
               'module: a', 'module:', 'nothing', 'Module:a', 'module:a\nb', 'module:a b', 'role:admin',
               'application:shop', 'commit:' + 'a' * 40, 'module:' + 'é' * 300]
    for value in samples:
        assert migration.is_reference(value) == is_reference(value), value
        if is_reference(value):
            assert migration.row('s', value)['search_key'] == fold(value.partition(':')[2])


def test_migration_008_indexes_existing_analyses_and_downgrades(tmp_path):
    url = f'sqlite:///{tmp_path / "references.db"}'
    env = {**os.environ, 'DATABASE_URL': url}

    def migrate(action, target):
        return subprocess.run([sys.executable, '-m', 'alembic', action, target], check=True, env=env,
                              capture_output=True, text=True).stdout
    migrate('upgrade', '007')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO projects (id, name, path) VALUES ('p', 'p', '/p')"))
        db.execute(text("INSERT INTO scans (id, project_id, created_at, result) VALUES ('s', 'p', '2026-10-03', '{}')"))
        db.execute(text("INSERT INTO fact_identities (identity_hash, kind, subject, relation, object, identity) VALUES "
                        "('a', 'ASSERTION', 'module:Root', 'DEPENDS_ON', 'module:b', '{}'), "
                        "('l', 'ASSERTION', 'endpoint:GET /x', 'AUTHORIZED_BY', 'hasRole(\"A\")', '{}'), "
                        "('c', 'COVERAGE', 'file:c.java', NULL, NULL, '{}')"))
        db.execute(text("INSERT INTO fact_occurrences (scan_id, identity_hash, status, validity, has_evidence) VALUES "
                        "('s', 'a', 'OBSERVED', 'VALID', 0), ('s', 'l', 'OBSERVED', 'VALID', 0), "
                        "('s', 'c', 'OBSERVED', 'VALID', 0)"))
    assert '3 références indexées pour 1 analyses' in migrate('upgrade', '008')
    with engine.connect() as db:
        rows = db.execute(text('SELECT reference, type, search_key FROM analysis_references ORDER BY reference')).all()
    assert [tuple(row) for row in rows] == [
        ('endpoint:GET /x', 'endpoint', 'get /x'), ('module:Root', 'module', 'root'), ('module:b', 'module', 'b')], \
        'une valeur littérale n’est pas une référence'
    migrate('downgrade', '007')
    with engine.connect() as db:
        assert 'analysis_references' not in {name for (name,) in db.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
    engine.dispose()


def test_describe_offers_the_search(twin):
    described = twin.exchange('fact_memory').call({'operation': 'describe'})
    assert 'find_references' in [item['operation'] for item in described['items'] if item['kind'] == 'operation']


@pytest.mark.parametrize('name', STORAGES)
def test_every_reference_found_is_accepted_as_an_anchor(twin, name):
    """Ce que la recherche propose, le parcours l'accepte : orthographe soumise comprise (NFD ici)."""
    assert found(search(twin, name, prefix='\u00f3r')) == ['module:o\u0301rders'], \
        'comparée en NFC, rendue telle quelle'
    for reference in found(search(twin, name, prefix='o', limit=50)) + found(search(twin, name, prefix='st')):
        tile = twin.ask(twin.exchange(name), root=reference, direction='INCOMING',
                        follow=['CONTAINS' if reference.startswith('file:') else 'DEPENDS_ON'])
        assert tile['anchor']['known'], reference
        assert [item['fact']['subject'] for item in tile['items']] == ['module:root']


@pytest.mark.parametrize('name', STORAGES)
def test_a_prefix_range_follows_code_points_whatever_the_database_language(tmp_path, name):
    """Dans une collation de langue, « é » se range entre « e » et « f » : la plage du préfixe « e » y prendrait
    « éclair ». L'index compare dans l'ordre des octets, partout : « e » ne trouve pas « é »."""
    twin = Twin(tmp_path)
    twin.add([edge(target, subject='module:root') for target in ('module:eclair', 'module:éclair', 'module:fable')])
    assert found(search(twin, name, prefix='e')) == ['module:eclair']
    assert found(search(twin, name, prefix='é')) == ['module:éclair']
    assert found(search(twin, name, prefix='ecl')) == ['module:eclair']


@pytest.mark.parametrize('name', STORAGES)
def test_a_prefix_that_folds_beyond_the_index_key_never_matches_wrongly(tmp_path, name):
    """129 « ß » se replient en 258 « s » : tronqué à la clé de l'index, le préfixe trouverait une référence qui
    ne commence pas par lui. Un tel préfixe est refusé ; à la longueur de la clé, il reste exact."""
    twin = Twin(tmp_path)
    twin.add([edge('module:' + 'ß' * 128 + 'x', subject='module:root')])
    assert search(twin, name, prefix='ß' * 129)['error']['code'] == 'INVALID_ARGUMENT'
    assert found(search(twin, name, prefix='ß' * 128)) == ['module:' + 'ß' * 128 + 'x']
