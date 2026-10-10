"""TAXO-01N, PR A2 : `find_references` avec `match: NAME`, retrouver une référence par son nom.

La vérité est écrite à la main : quel nom trouve quelles références. Les deux stockages rendent la même liste ;
la mémoire versionnée par une lecture d'index bornée.
"""
import os
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text

from app.facts import is_reference
from app.neighborhood.domain.reference_names import name_keys
from test_find_references import found, search
from test_neighborhood_conformance import STORAGES, Twin, edge

JAVA = 'symbol:java:com.example.'
VET = JAVA + 'web.VetController'
SHOW = VET + '#show()'
FIND = JAVA + 'owner.OwnerRepository#findById(Long)'
FIND_LOCAL = FIND + '/value'
FIND_LEGACY = JAVA + 'legacy.OwnerRepository#findById(String)'
LIST, LIST_STRING = JAVA + 'Items#list()', JAVA + 'Items#list(String)'
LIST_FILE = 'file:Items.list(String)'
COURSE_METHOD, COURSE_FIELD = JAVA + 'Seat#course()', JAVA + 'Seat#course'
REPEATED = 'symbol:java:p.p.P#p()'
REFERENCES = [VET, SHOW, FIND, FIND_LOCAL, FIND_LEGACY, LIST, LIST_STRING, LIST_FILE, COURSE_METHOD, COURSE_FIELD,
              REPEATED]


@pytest.fixture
def twin(tmp_path):
    made = Twin(tmp_path)
    # Un fichier contient des symboles ; un module, des fichiers.
    made.add([edge(target, 'CONTAINS', subject='module:root' if target.startswith('file:') else 'file:App.java')
              for target in REFERENCES])
    return made


def by_name(twin, storage, name, **arguments):
    return search(twin, storage, prefix=name, match='NAME', **arguments)


def named(twin, storage, name, **arguments):
    result = by_name(twin, storage, name, **arguments)
    assert result['outcome'] == 'OK', result
    return sorted(found(result))


@pytest.mark.parametrize('storage', STORAGES)
def test_the_examples_of_the_story_each_find_their_reference_alone(twin, storage):
    assert named(twin, storage, 'VetController') == [VET], 'ni ses méthodes'
    assert named(twin, storage, 'web.VetController') == [VET]
    assert named(twin, storage, 'OwnerRepository.findById') == sorted([FIND, FIND_LEGACY]), \
        'deux homonymes de paquets différents, ni leurs paramètres ni leurs variables'
    assert named(twin, storage, 'owner.OwnerRepository#findById') == [FIND], 'qualifié, avec le séparateur canonique'
    assert named(twin, storage, 'findbyid') == sorted([FIND, FIND_LEGACY]), 'la casse ne compte pas'


@pytest.mark.parametrize('storage', STORAGES)
def test_a_signature_chooses_one_overload_and_is_only_read_on_callable_symbols(twin, storage):
    assert named(twin, storage, 'Items.list') == sorted([LIST, LIST_STRING]), 'toutes les surcharges'
    assert named(twin, storage, 'Items.list(String)') == sorted([LIST_STRING, LIST_FILE]), \
        'une seule surcharge ; le fichier se compare tel quel'
    assert named(twin, storage, 'Items.list()') == [LIST]
    assert LIST_FILE not in named(twin, storage, 'Items.list'), 'un fichier n’a pas de liste de paramètres'
    assert named(twin, storage, 'Seat.course()') == [COURSE_METHOD], 'la méthode, pas le champ'
    assert named(twin, storage, 'Seat.course') == sorted([COURSE_METHOD, COURSE_FIELD])
    assert named(twin, storage, 'Items.lis') == [], 'une égalité, pas un préfixe'
    assert named(twin, storage, 'example') == [], 'un segment isolé au milieu de la clé ne suffit pas'


@pytest.mark.parametrize('storage', STORAGES)
def test_a_reference_found_by_several_of_its_segments_is_returned_once(twin, storage):
    result = by_name(twin, storage, 'p')
    assert found(result) == [REPEATED]
    assert result['next'] is None


@pytest.mark.parametrize('storage', STORAGES)
def test_homonyms_spread_over_pages_are_all_reached_once(twin, storage):
    pages, after = [], None
    while True:
        result = by_name(twin, storage, 'findById', limit=1, **({'after': after} if after else {}))
        assert result['match'] == 'NAME'
        pages.append(found(result))
        after = result['next']
        if after is None:
            break
    assert [len(page) for page in pages] == [1, 1]
    assert sorted(reference for page in pages for reference in page) == sorted([FIND, FIND_LEGACY])
    first = by_name(twin, storage, 'findById', limit=1)
    assert first['next'] is not None, 'une page tronquée le dit : l’ancre n’est pas unique'


@pytest.mark.parametrize('storage', STORAGES)
def test_a_continuation_is_bound_to_the_mode(twin, storage):
    by_key = search(twin, storage, prefix='java', limit=1)['next']
    by_name_token = by_name(twin, storage, 'findById', limit=1)['next']
    assert search(twin, storage, prefix='java', match='NAME', after=by_key)['error']['code'] == 'INVALID_ARGUMENT'
    assert search(twin, storage, prefix='findById', after=by_name_token)['error']['code'] == 'INVALID_ARGUMENT'
    assert by_name(twin, storage, 'findById', after=by_name_token)['outcome'] == 'OK'


@pytest.mark.parametrize('storage', STORAGES)
def test_the_key_mode_is_unchanged(twin, storage):
    implicit = search(twin, storage, prefix='java:com.example.web')
    explicit = search(twin, storage, prefix='java:com.example.web', match='KEY')
    assert found(implicit) == found(explicit) == [VET, SHOW]
    assert 'match' not in implicit and 'match' not in explicit
    assert found(search(twin, storage, prefix='VetController')) == [], 'le préfixe de clé ne trouve pas le nom seul'


@pytest.mark.parametrize('arguments', [{'match': 'name'}, {'match': 3}, {'match': ['NAME']},
                                       {'match': 'NAME', 'prefix': 'ß' * 129}])
def test_bad_modes_are_refused(twin, arguments):
    assert search(twin, 'fact_memory', **{'prefix': 'a', **arguments})['error']['code'] == 'INVALID_ARGUMENT'


def test_an_analysis_without_the_name_index_says_so(twin):
    with twin.engines['fact_memory'].begin() as db:
        db.execute(text('DELETE FROM analysis_reference_names'))
    assert by_name(twin, 'fact_memory', 'VetController')['error']['code'] == 'NOT_AVAILABLE'
    assert found(search(twin, 'fact_memory', prefix='java:com.example.web')) == [VET, SHOW], 'KEY reste servi'


def test_an_analysis_without_references_is_an_empty_answer(tmp_path):
    result = by_name(Twin(tmp_path), 'fact_memory', 'x')
    assert result['outcome'] == 'OK' and result['items'] == [], 'rien à indexer : pas un index manquant'


def test_the_versioned_memory_reads_a_bounded_index_never_the_facts(twin):
    statements = []
    engine = twin.engines['fact_memory']
    event.listen(engine, 'before_cursor_execute', lambda conn, cur, sql, *rest: statements.append(sql))
    by_name(twin, 'fact_memory', 'findById', limit=1)
    reads = [sql for sql in statements if 'analysis_reference_names' in sql]
    assert len(reads) == 1, 'une seule lecture quand la page n’est pas vide'
    assert 'LIMIT' in reads[0], 'une plage bornée de l’index'
    assert 'fact_identities' not in reads[0] and 'fact_occurrences' not in reads[0], 'jamais les faits'


@pytest.mark.parametrize('storage', STORAGES)
def test_every_reference_found_by_name_is_accepted_as_an_anchor(twin, storage):
    for reference in named(twin, storage, 'findById') + named(twin, storage, 'VetController'):
        tile = twin.ask(twin.exchange(storage), root=reference, direction='INCOMING', follow=['CONTAINS'])
        assert tile['anchor']['known'], reference


def test_the_index_keeps_only_names_that_an_accepted_name_could_equal():
    long_reference = 'module:' + 'a' * 300 + '.tail'
    assert name_keys(long_reference) == ['tail'], 'une fin plus longue que la clé de l’index n’est pas gardée'
    assert name_keys('module:a..b') == ['.b', 'a..b', 'b'], 'des séparateurs répétés ne cassent rien'


MIGRATION = Path(__file__).parents[1] / 'migrations/versions/010_analysis_reference_names.py'


def frozen():
    spec = spec_from_file_location('migration010', MIGRATION)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_frozen_rules_of_the_migration_agree_with_the_application():
    migration = frozen()
    samples = [*REFERENCES, 'module:a', 'file:src/A.java', 'endpoint:GET /orders', 'symbol:java:A$B#c(int[])',
               'symbol:java:A#b(java.lang.String)', 'symbol:java:A#m(Long)/x#2', 'module:Straße.x', 'module:a..b',
               'symbol:java:A#b.c()', 'module:' + 'é' * 300]
    for value in samples:
        assert is_reference(value), value
        assert migration.name_keys(value) == name_keys(value), value


def test_migration_010_indexes_existing_analyses_and_downgrades(tmp_path):
    url = f'sqlite:///{tmp_path / "names.db"}'
    env = {**os.environ, 'DATABASE_URL': url}

    def migrate(action, target):
        return subprocess.run([sys.executable, '-m', 'alembic', action, target], check=True, env=env,
                              capture_output=True, text=True).stdout
    migrate('upgrade', '009')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO projects (id, name, path) VALUES ('p', 'p', '/p')"))
        db.execute(text("INSERT INTO scans (id, project_id, created_at, result) VALUES ('s', 'p', '2026-10-10', '{}')"))
        db.execute(text("INSERT INTO analysis_references (scan_id, reference_hash, search_key, type, reference) VALUES "
                        "('s', 'h1', 'java:a.b#c()', 'symbol', 'symbol:java:a.B#c()'), "
                        "('s', 'h2', 'x', 'module', 'module:x')"))
    assert '9 noms indexés pour 1 analyses' in migrate('upgrade', '010')
    with engine.connect() as db:
        rows = db.execute(text('SELECT name_key, reference_hash FROM analysis_reference_names '
                               'ORDER BY reference_hash, name_key')).all()
    assert [tuple(row) for row in rows] == [
        ('a.b.c', 'h1'), ('a.b.c()', 'h1'), ('b.c', 'h1'), ('b.c()', 'h1'), ('c', 'h1'), ('c()', 'h1'),
        ('java.a.b.c', 'h1'), ('java.a.b.c()', 'h1'), ('x', 'h2')]
    migrate('downgrade', '009')
    with engine.connect() as db:
        assert 'analysis_reference_names' not in {name for (name,) in db.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'"))}
    engine.dispose()
