"""P1 de la légende de la carte : `describe` annonce les familles de références que l'index de l'analyse tient, avec leur
effectif. Un élément de plus (`kind: family`), additif : ni fait, ni verdict, ni prétention à l'exhaustivité."""
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.scans.infrastructure.sqlalchemy.fact_memory import SqlAlchemyFactMemory
from test_neighborhood_conformance import Twin, edge
from tests.method_security_sources import FILES

KEYS = {'kind', 'type', 'count', 'source'}


@pytest.fixture(name='taxo')
def taxo_fixture(make_repo, tmp_path):
    repo = make_repo(FILES, 'boutique')
    app = create_app(f'sqlite:///{tmp_path / "familles.db"}', [repo], minia={})
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Boutique', 'path': str(repo)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        yield client, f'/api/projects/{project["id"]}/taxo-query'


def call(taxo, *requests):
    client, url = taxo
    response = client.post(url, json={'requests': [{'operation': name, 'arguments': arguments, **extra}
                                                   for name, arguments, extra in requests]})
    assert response.status_code == 200, response.text
    return response.json()['responses']


def describe(taxo, max_bytes=None):
    return call(taxo, ('describe', {}, {} if max_bytes is None else {'max_bytes': max_bytes}))[0]


def families(response):
    return [item for item in response['items'] if item['kind'] == 'family']


def test_describe_announces_each_family_the_index_holds_with_its_count(taxo):
    found = families(describe(taxo))
    assert found, 'l’analyse a des références indexées'
    for item in found:
        assert set(item) == KEYS
        assert item['kind'] == 'family'
        assert isinstance(item['count'], int)
        assert item['count'] > 0


def test_the_count_is_what_the_index_holds_for_that_type(taxo):
    # Dans un même échange : la description donne l'analyse, les recherches la reprennent.
    analysis = describe(taxo)['snapshot']['analysis']
    searches = [('find_references', {'analysis': analysis, 'type': 'endpoint', 'prefix': method, 'limit': 50,
                                     'match': 'KEY'}, {}) for method in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH')]
    listed = call(taxo, ('describe', {}, {}), *searches)
    endpoints = sum(len(item.get('items', [])) for item in listed[1:])
    announced = {item['type']: item['count'] for item in families(listed[0])}
    assert announced['endpoint'] == endpoints


def test_families_are_ordered_by_count_then_by_name(taxo):
    found = families(describe(taxo))
    assert found == sorted(found, key=lambda item: (-item['count'], item['type']))


def test_the_legend_says_it_is_an_index_not_the_program(taxo):
    assert {item['source'] for item in families(describe(taxo))} == {'analysis-index'}


def test_a_family_carries_only_a_type_and_a_count_never_a_name_or_a_path(taxo):
    for item in families(describe(taxo)):
        assert ':' not in item['type']
        assert '/' not in item['type']
        assert item['type'].replace('-', '').isalpha()


def test_describe_is_deterministic_for_the_same_analysis(taxo):
    first = families(describe(taxo))
    second = families(describe(taxo))
    assert first
    assert first == second


def test_an_analysis_without_an_index_announces_no_family_and_describe_still_works(taxo, monkeypatch):
    monkeypatch.setattr(SqlAlchemyFactMemory, 'families', lambda self, scan_id: [])
    response = describe(taxo)
    assert response['outcome'] == 'OK'
    assert families(response) == []
    assert [item for item in response['items'] if item['kind'] == 'relation'], 'le reste de describe est inchangé'


def test_the_other_items_of_describe_are_untouched(taxo, monkeypatch):
    # Un budget large : ce test compare les éléments, pas la place que la légende prend sous la limite par défaut.
    with_families = describe(taxo, max_bytes=30_000)
    monkeypatch.setattr(SqlAlchemyFactMemory, 'families', lambda self, scan_id: [])
    without = describe(taxo, max_bytes=30_000)
    kept = [item for item in with_families['items'] if item['kind'] != 'family']
    assert kept == without['items']


def test_under_a_tight_budget_the_legend_is_kept_and_the_end_of_describe_is_counted(taxo):
    full = describe(taxo)
    tight = describe(taxo, max_bytes=full['bytes'] - 400)
    assert tight['outcome'] == 'OK'
    assert tight['bytes'] <= full['bytes'] - 400
    assert families(tight) == families(full), 'la légende précède les éléments longs : elle n’est pas coupée la première'
    assert len(tight['items']) < len(full['items'])
    assert tight['not_sent'], 'ce qui n’a pas tenu est compté, jamais tu'


def test_the_legend_comes_before_the_analyzers_and_the_relations(taxo):
    kinds = [item['kind'] for item in describe(taxo)['items']]
    last_family = max(index for index, kind in enumerate(kinds) if kind == 'family')
    assert last_family < kinds.index('analyzer')
    assert last_family < kinds.index('relation')


def test_the_legend_costs_well_under_two_kilobytes(taxo, monkeypatch):
    with_families = describe(taxo)['bytes']
    monkeypatch.setattr(SqlAlchemyFactMemory, 'families', lambda self, scan_id: [])
    without = describe(taxo)['bytes']
    assert 0 < with_families - without <= 2000


def test_both_storages_count_the_same_families_and_describe_announces_them(tmp_path):
    twin = Twin(tmp_path)
    twin.add([edge('module:A', 'CONTAINS', subject='module:root'), edge('file:x', 'CONTAINS', subject='module:root'),
              edge('module:B', 'DEPENDS_ON', subject='module:root')])
    expected = [('module', 3), ('file', 1)]
    for name, store in twin.stores.items():
        assert store.families('analysis-1') == expected, name
        described = twin.exchange(name).call({'operation': 'describe'})
        announced = [(item['type'], item['count']) for item in described['items'] if item['kind'] == 'family']
        assert announced == expected, name
    assert twin.stores['fact_memory'].families('analysis-2') == []
