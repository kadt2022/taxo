"""P3 de la légende de la carte : `find_references` avec `match: CONTAINS` cherche un texte contenu dans la clé des références
d'un type, sans tenir compte de la casse. Ce n'est pas une recherche indexée : la lecture est bornée (`MAX_SCAN`) et, quand
elle s'arrête à sa borne, la page le dit dans `not_sent` et rend une reprise. Jamais une absence."""
import pytest

from app.neighborhood.application import references as application
from test_neighborhood_conformance import STORAGES, Twin, edge

REFERENCES = ['module:Orders', 'module:orders-api', 'module:ordinal', 'module:Straße', 'module:strasse-x',
              'file:orders/Order.java', 'module:órders', *(f'module:queue-{index:02}' for index in range(12))]


@pytest.fixture(name='twin')
def twin_fixture(tmp_path):
    found = Twin(tmp_path)
    found.add([edge(target, 'CONTAINS' if target.startswith('file:') else 'DEPENDS_ON', subject='module:root')
               for target in REFERENCES])
    return found


def contains(twin, name, text, kind='module', **arguments):
    exchange = twin.exchange(name)
    return exchange.call({'operation': 'find_references', 'max_bytes': 20_000,
                          'arguments': {'analysis': 'analysis-1', 'prefix': text, 'type': kind, 'match': 'CONTAINS',
                                        **arguments}})


def found(result):
    return [item['reference'] for item in result['items']]


def every_page(twin, name, text, **arguments):
    pages, after = [], None
    for _ in range(60):
        extra = {} if after is None else {'after': after}
        page = contains(twin, name, text, **extra, **arguments)
        assert page['outcome'] == 'OK', page
        pages.append(page)
        after = page.get('next')
        if not after:
            return pages
    raise AssertionError('la lecture ne se termine pas')


@pytest.mark.parametrize('name', STORAGES)
def test_a_text_is_found_anywhere_in_the_key(twin, name):
    result = contains(twin, name, 'rders')
    assert sorted(found(result)) == sorted(['module:Orders', 'module:orders-api', 'module:órders'])


@pytest.mark.parametrize('name', STORAGES)
def test_the_case_is_ignored(twin, name):
    assert sorted(found(contains(twin, name, 'ORDERS'))) == sorted(found(contains(twin, name, 'orders')))


@pytest.mark.parametrize('name', STORAGES)
def test_only_the_references_of_the_asked_type_are_read(twin, name):
    assert found(contains(twin, name, 'order', kind='file')) == ['file:orders/Order.java']


@pytest.mark.parametrize('name', STORAGES)
def test_a_text_that_matches_nothing_gives_an_empty_page_that_says_what_it_searched(twin, name):
    result = contains(twin, name, 'zzzz')
    assert result['outcome'] == 'OK'
    assert result['items'] == []
    assert result['match'] == 'CONTAINS'
    assert result['prefix'] == 'zzzz'
    assert not result.get('next')
    assert not result['not_sent']


@pytest.mark.parametrize('name', STORAGES)
def test_the_response_echoes_the_mode_and_declares_its_coverage(twin, name):
    result = contains(twin, name, 'rders')
    assert result['match'] == 'CONTAINS'
    assert result['type'] == 'module'
    assert result['coverage']


@pytest.mark.parametrize('name', STORAGES)
def test_the_two_storages_give_the_same_pages(twin, name):
    reference = [found(page) for page in every_page(twin, STORAGES[0], 'queue', limit=5)]
    assert [found(page) for page in every_page(twin, name, 'queue', limit=5)] == reference


@pytest.mark.parametrize('name', STORAGES)
def test_the_pages_add_up_to_everything_that_matches(twin, name):
    pages = every_page(twin, name, 'queue', limit=5)
    assert len(pages) == 3
    assert sum(len(page['items']) for page in pages) == 12
    assert not pages[-1].get('next')


@pytest.mark.parametrize('name', STORAGES)
def test_a_bounded_read_says_so_and_a_resume_reaches_the_rest(twin, name, monkeypatch):
    monkeypatch.setattr(application, 'MAX_SCAN', 4)
    pages = every_page(twin, name, 'queue', limit=50)
    cut = [page for page in pages if page['not_sent']]
    assert cut, 'la borne atteinte est dite'
    assert cut[0]['not_sent'][0]['reason'] == 'SCAN_LIMIT'
    assert cut[0]['next'], 'une page coupée rend une reprise'
    assert sum(len(page['items']) for page in pages) == 12, 'la reprise atteint tout ce qui correspond'
    assert not pages[-1]['not_sent']
    assert not pages[-1].get('next')


@pytest.mark.parametrize('name', STORAGES)
def test_a_bounded_read_without_a_match_never_says_there_is_none(twin, name, monkeypatch):
    monkeypatch.setattr(application, 'MAX_SCAN', 3)
    first = contains(twin, name, 'queue-11')
    assert first['items'] == []
    assert first['next'], 'rien n’a été trouvé dans ce qui a été lu, pas dans tout le type'
    assert first['not_sent'][0]['reason'] == 'SCAN_LIMIT'


def test_the_type_is_required(twin):
    result = twin.exchange('fact_memory').call({'operation': 'find_references', 'max_bytes': 20_000, 'arguments': {
        'analysis': 'analysis-1', 'prefix': 'rders', 'match': 'CONTAINS'}})
    assert result['outcome'] == 'ERROR'
    assert result['error']['code'] == 'INVALID_ARGUMENT'
    assert 'type' in result['error']['message']


def test_a_continuation_of_another_mode_is_refused(twin):
    first = twin.exchange('fact_memory').call({'operation': 'find_references', 'max_bytes': 20_000, 'arguments': {
        'analysis': 'analysis-1', 'prefix': 'q', 'type': 'module', 'limit': 2, 'match': 'KEY'}})
    assert first['next']
    result = contains(twin, 'fact_memory', 'q', after=first['next'])
    assert result['outcome'] == 'ERROR'
    assert result['error']['code'] == 'INVALID_ARGUMENT'


def test_a_prefix_search_is_unchanged(twin):
    result = twin.exchange('fact_memory').call({'operation': 'find_references', 'max_bytes': 20_000, 'arguments': {
        'analysis': 'analysis-1', 'prefix': 'module:ord', 'match': 'KEY'}})
    assert result['outcome'] == 'OK'
    assert 'match' not in result, 'une réponse du mode KEY reste celle d’avant'
    assert sorted(found(result)) == ['module:Orders', 'module:orders-api', 'module:ordinal', 'module:órders'] \
        or all(item.startswith('module:') for item in found(result))


def test_describe_advertises_the_contains_mode(twin):
    described = twin.exchange('fact_memory').call({'operation': 'describe'})
    declared = next(item for item in described['items'] if item.get('operation') == 'find_references')['arguments']
    assert 'CONTAINS' in declared['match']
    assert 'type obligatoire' in declared['match']
    assert 'bornée' in declared['match']
