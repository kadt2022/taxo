"""TAXO-01J : la Tuile multiniveau sur de vraies analyses, par l'API du protocole.

La vérité est écrite à la main, à partir des fichiers du dépôt scénarisé (`test_spring_boot.repository`) :
- `OrderController#get` traite `GET /orders` ;
- la boutique (`ShopApplication`) balaie `com.acme` et a `web` sur son classpath : elle sert la route ;
- `ShopSecurity` protège tout (`/**`) par `authenticated()` ; `AdminSecurity` autorise `/**` à `hasRole("ADMIN")`.
"""
from test_coverage_bounds import PYTHON, taxo_on_fixture  # noqa: F401  (fixture partagée)
from test_java_calls import fixture_files
from test_spring_boot import SHOP_REF, repository

ORDERS = 'endpoint:GET /orders'
CONTROLLER = 'web/src/main/java/com/acme/web/OrderController.java'
SECURITY = ('HANDLED_BY', 'SERVED_BY', 'MATCHED_BY', 'AUTHORIZED_BY', 'PROTECTED_BY')


def tile(taxo, scan, **arguments):
    response = taxo.client.post(f'{taxo.base}/taxo-query', json={'analysis': scan, 'requests': [{
        'operation': 'get_neighborhood', 'max_bytes': 32_000,
        'arguments': {'analysis': scan, 'engine': 'neighborhood/2', **arguments}}]})
    assert response.status_code == 200, response.text
    found, = response.json()['responses']
    assert found['outcome'] == 'OK', found
    return found


def elements(found):
    return [(item['level'], item['fact']['subject'], item['fact']['relation'], item['fact']['object'])
            for item in found['items']]


def test_from_a_route_to_its_handler_application_and_authorizations(taxo_on):
    taxo, _ = taxo_on(repository())
    scan = taxo.analyse()['id']
    steps = [{'relation': relation, 'direction': 'OUTGOING'} for relation in SECURITY]
    found = tile(taxo, scan, root=ORDERS, steps=steps, depth=3)
    assert elements(found) == [
        (1, ORDERS, 'HANDLED_BY', 'symbol:java:com.acme.web.OrderController#get()'),
        (1, ORDERS, 'SERVED_BY', SHOP_REF),
        (1, ORDERS, 'MATCHED_BY', 'route-pattern:/**'),
        (1, ORDERS, 'PROTECTED_BY', 'policy-rule:authenticated()'),
        (2, 'route-pattern:/**', 'AUTHORIZED_BY', 'authenticated()'),
        (2, 'route-pattern:/**', 'AUTHORIZED_BY', 'hasRole("ADMIN")')]
    assert found['stop_reason'] == 'ADJACENCY_COMPLETE'
    assert [node['reference'] for node in found['node_details']][0] == ORDERS
    assert all(item['occurrence'] for item in found['items'])


def test_from_a_file_back_to_its_commits_and_their_repository(taxo_on, git):
    """En entrant : le commit qui a changé le fichier, puis le dépôt qui a ce commit. Aucun fait inversé."""
    taxo, root = taxo_on(repository())
    scan = taxo.analyse()['id']
    sha = git(root, 'rev-parse', 'HEAD')
    found = tile(taxo, scan, root=f'file:{CONTROLLER}', direction='INCOMING', follow=['CHANGES', 'HAS_COMMIT'],
                 depth=2)
    commit = f'commit:{sha}'
    assert [(level, subject, relation) for level, subject, relation, _ in elements(found)] == [
        (1, commit, 'CHANGES'), (2, f'repository:{taxo.base.rsplit("/", 1)[-1]}', 'HAS_COMMIT')]
    assert [item['fact']['object'] for item in found['items']] == [f'file:{CONTROLLER}', commit]
    assert [item['via']['direction'] for item in found['items']] == ['INCOMING', 'INCOMING']


def test_a_relation_no_capable_execution_produces_is_a_context_frontier_never_an_empty_answer(taxo_on):
    taxo, _ = taxo_on(PYTHON)
    scan = taxo.analyse()['id']
    found = tile(taxo, scan, root='repository:' + taxo.base.rsplit('/', 1)[-1], follow=['HANDLED_BY'],
                 direction='OUTGOING', depth=2)
    assert {(entry['nature'], entry['reason']) for entry in found['frontier']} >= {('CONTEXT', 'NO_ANALYZER')}


def test_a_route_found_by_search_opens_its_tile(taxo_on):
    """Le parcours de l'explorateur, côté protocole : chercher une route, puis ouvrir sa Tuile."""
    taxo, _ = taxo_on(repository())
    scan = taxo.analyse()['id']
    response = taxo.client.post(f'{taxo.base}/taxo-query', json={'analysis': scan, 'requests': [
        {'operation': 'find_references', 'arguments': {'analysis': scan, 'prefix': 'GET /ord', 'type': 'endpoint'}}]})
    searched, = response.json()['responses']
    assert [item['reference'] for item in searched['items']] == [ORDERS]
    assert tile(taxo, scan, root=searched['items'][0]['reference'], follow=['HANDLED_BY'],
                direction='OUTGOING')['anchor']['known']


def test_the_calls_of_a_route_handler_are_followed_and_their_unread_sites_say_why(taxo_on):
    """TAXO-01K : sans rien de propre à Java dans le moteur, la Tuile suit la route vers son traitement puis ses
    appels, et la zone non lue d'une méthode porte les raisons fermées de ses sites."""
    taxo, _ = taxo_on(fixture_files())
    scan = taxo.analyse()['id']
    controller = 'symbol:java:com.example.demo.controller.CourseController'
    found = tile(taxo, scan, root='endpoint:POST /api/courses', follow=['HANDLED_BY', 'CALLS'],
                 direction='OUTGOING', depth=2)
    assert elements(found) == [
        (1, 'endpoint:POST /api/courses', 'HANDLED_BY', f'{controller}#register(String)'),
        (2, f'{controller}#register(String)', 'CALLS', f'{controller}#audit()'),
        (2, f'{controller}#register(String)', 'CALLS',
         'symbol:java:com.example.demo.service.CourseService#register(String)')]
    unread = [entry for entry in found['frontier'] if entry.get('node') == f'{controller}#register(String)'
              and entry['producer'] == 'taxo.java-calls']
    assert [(entry['reason'], entry['causes']) for entry in unread] == [
        ('NOT_INTERPRETED', ['OVERLOAD_AMBIGUOUS', 'RECEIVER_KIND_DEFERRED'])]
    # TAXO-01M : les memes sites, comptes par categorie generique, sans rien de Java dans le moteur.
    assert unread[0]['categories'] == [{'category': 'AMBIGUOUS', 'count': {'kind': 'EXACT', 'value': 1}},
                                       {'category': 'UNSUPPORTED', 'count': {'kind': 'EXACT', 'value': 1}}]
