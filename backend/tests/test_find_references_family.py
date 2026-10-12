"""P2 de la légende de la carte : `find_references` liste une famille entière sans préfixe, par pages. Avec un `type`, en
mode KEY, un préfixe absent ou vide liste toutes les références de ce type ; sans type, ou en mode NAME, le préfixe reste
obligatoire. Un assouplissement : aucun appel qui réussissait ne change."""
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from tests.method_security_sources import FILES


@pytest.fixture(name='taxo')
def taxo_fixture(make_repo, tmp_path):
    repo = make_repo(FILES, 'boutique')
    app = create_app(f'sqlite:///{tmp_path / "famille.db"}', [repo], minia={})
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Boutique', 'path': str(repo)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        yield client, f'/api/projects/{project["id"]}/taxo-query'


def search(taxo, **arguments):
    """Une recherche dans un échange qui commence par `describe`, dont on reprend l'analyse."""
    client, url = taxo
    opening = client.post(url, json={'requests': [{'operation': 'describe', 'arguments': {}}]}).json()
    analysis = opening['responses'][0]['snapshot']['analysis']
    request = {'operation': 'find_references', 'arguments': {'analysis': analysis, **arguments}}
    response = client.post(url, json={'requests': [{'operation': 'describe', 'arguments': {}}, request]})
    assert response.status_code == 200, response.text
    return response.json()['responses'][1]


def references_of(response):
    return [item['reference'] for item in response['items']]


def whole_family(taxo, kind, **arguments):
    """Toutes les pages d'une famille, en suivant la reprise."""
    found, after = [], None
    for _ in range(50):
        extra = {} if after is None else {'after': after}
        page = search(taxo, type=kind, limit=2, **extra, **arguments)
        assert page['outcome'] == 'OK', page
        found.extend(references_of(page))
        after = page.get('next')
        if not after:
            return found
    raise AssertionError('la pagination ne se termine pas')


def test_a_family_is_listed_without_a_prefix(taxo):
    page = search(taxo, type='endpoint', limit=50)
    assert page['outcome'] == 'OK'
    listed = references_of(page)
    assert listed
    assert all(item.startswith('endpoint:') for item in listed)
    assert all(item['type'] == 'endpoint' for item in page['items'])


def test_the_listing_is_the_union_of_what_each_prefix_finds(taxo):
    listed = references_of(search(taxo, type='endpoint', limit=50))
    by_prefix = set()
    for method in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
        by_prefix |= set(references_of(search(taxo, type='endpoint', prefix=method, limit=50, match='KEY')))
    assert set(listed) == by_prefix


def test_a_larger_family_equals_what_its_common_prefix_finds(taxo):
    assert references_of(search(taxo, type='symbol', limit=50)) ==         references_of(search(taxo, type='symbol', prefix='java:', limit=50, match='KEY'))


def test_an_empty_prefix_is_the_same_as_no_prefix(taxo):
    assert references_of(search(taxo, type='endpoint', prefix='', limit=50)) == \
        references_of(search(taxo, type='endpoint', limit=50))


def test_the_pages_follow_one_another_and_add_up_to_the_whole_family(taxo):
    whole = references_of(search(taxo, type='symbol', limit=50))
    assert len(whole) > 2, 'la famille tient sur plusieurs pages de 2'
    assert whole_family(taxo, 'symbol') == whole


def test_the_listing_is_in_the_order_of_the_keys(taxo):
    listed = references_of(search(taxo, type='symbol', limit=50))
    assert listed == sorted(listed, key=lambda item: item.casefold())


def test_the_last_page_has_no_continuation(taxo):
    page = search(taxo, type='endpoint', limit=50)
    assert page.get('next') in (None, '')


def test_the_response_declares_its_coverage_and_its_type(taxo):
    page = search(taxo, type='endpoint', limit=50)
    assert page['type'] == 'endpoint'
    assert page['coverage'], 'la couverture est déclarée dans chaque réponse'


def test_without_a_type_the_prefix_stays_required(taxo):
    page = search(taxo, limit=50)
    assert page['outcome'] == 'ERROR'
    assert page['error']['code'] == 'INVALID_ARGUMENT'
    assert 'prefix' in page['error']['message']
    assert 'type' in page['error']['message']


def test_a_name_search_still_needs_its_name(taxo):
    page = search(taxo, type='endpoint', match='NAME')
    assert page['outcome'] == 'ERROR'
    assert page['error']['code'] == 'INVALID_ARGUMENT'


def test_an_unknown_type_is_still_refused(taxo):
    page = search(taxo, type='nimporte', limit=50)
    assert page['outcome'] == 'ERROR'
    assert page['error']['code'] == 'INVALID_ARGUMENT'


def test_a_search_with_a_prefix_is_unchanged(taxo):
    page = search(taxo, type='endpoint', prefix='GET', match='KEY', limit=50)
    assert page['outcome'] == 'OK'
    assert page['prefix'] == 'GET'
    assert all(item.startswith('endpoint:GET') for item in references_of(page))
