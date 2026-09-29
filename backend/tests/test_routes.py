"""TAXO-UI-02 : la page Routes lit les seuls faits de Taxo, et dit pourquoi une route n'est pas interpretee."""
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.scans.application.routes import project_routes
from test_spring_boot import ADMIN_REF, SHOP_REF, controller, repository, security

PUBLIC = controller('com.acme.web', 'StatusController', '/status')
DEBUG = controller('com.acme.web', 'DebugController', '/debug', '@Profile("dev")\n')
INHERITED = '''package com.acme.web;

import org.springframework.web.bind.annotation.RestController;

@RestController
public class GeneratedController implements OrdersApi {
}
'''
OPEN_STATUS = security('com.acme.security', 'ShopSecurity', 'authenticated()').replace(
    '.anyRequest().authenticated()', '.requestMatchers("/status").permitAll()\n                .anyRequest().authenticated()')


def analyse(make_repo, tmp_path):
    repo = make_repo(repository(**{
        'web/src/main/java/com/acme/web/StatusController.java': PUBLIC,
        'web/src/main/java/com/acme/web/DebugController.java': DEBUG,
        'web/src/main/java/com/acme/web/GeneratedController.java': INHERITED,
        'security/src/main/java/com/acme/security/ShopSecurity.java': OPEN_STATUS}))
    app = create_app(f'sqlite:///{tmp_path / "routes.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Boutique', 'path': str(repo)}).json()
        base = f'/api/projects/{project["id"]}'
        scan = client.post(f'{base}/scans').json()
        return client.get(f'{base}/scans/{scan["id"]}/routes').json(), client.get(f'{base}/scans/inconnue/routes')


def test_each_route_carries_its_handler_application_rule_and_protection(make_repo, tmp_path):
    result, missing = analyse(make_repo, tmp_path)
    assert missing.status_code == 404
    routes = {route['endpoint']: route for route in result['routes']}
    admin = routes['endpoint:GET /admin/users']
    assert admin['state'] == 'PROTECTED'
    assert [fact['object'] for fact in admin['applications']] == [ADMIN_REF]
    assert [fact['object'] for fact in admin['protections']] == ['policy-rule:hasRole("ADMIN")']
    assert [fact['relation'] for fact in admin['rules']] == ['AUTHORIZED_BY']
    assert admin['handlers'][0]['evidence'], 'chaque fait arrive avec ses preuves'
    assert admin['protections'][0]['derivation']['premises'], 'et une deduction avec ses premisses'
    status = routes['endpoint:GET /status']
    assert status['state'] == 'PERMITS_ALL'
    assert [fact['object'] for fact in status['applications']] == [SHOP_REF]
    assert not status['protections']


def test_a_route_not_interpreted_says_exactly_why(make_repo, tmp_path):
    result, _ = analyse(make_repo, tmp_path)
    debug = next(route for route in result['routes'] if route['endpoint'] == 'endpoint:GET /debug')
    assert debug['state'] == 'NOT_INTERPRETED'
    assert not debug['applications']
    reasons = {gap['evaluator']: gap['reason'] for gap in debug['gaps']}
    assert 'condition @Profile' in reasons['taxo.spring-boot']
    assert 'condition @Profile' in reasons['taxo.spring-security']
    unestablished = {item['subject']: item for item in result['unestablished']}
    assert 'Routes héritées' in unestablished['symbol:java:com.acme.web.GeneratedController']['reason'], \
        'des routes peuvent manquer : la page le dit'


def test_the_projection_deduces_nothing_a_fact_does_not_carry():
    handled = {'subject': 'endpoint:GET /x', 'relation': 'HANDLED_BY', 'object': 'symbol:java:X#x()', 'qualifiers': {}}
    other_chain = {'subject': 'route-pattern:/**', 'relation': 'PERMITS_ALL', 'qualifiers': {'filter_chain': 'B'}}
    matched = {'subject': 'endpoint:GET /x', 'relation': 'MATCHED_BY', 'object': 'route-pattern:/**',
               'qualifiers': {'filter_chain': 'A'}}
    result = project_routes({'HANDLED_BY': [handled], 'MATCHED_BY': [matched], 'PERMITS_ALL': [other_chain]}, [])
    route = result['routes'][0]
    assert route['state'] == 'NO_CONCLUSION', 'la regle permitAll d une autre chaine ne vaut pas pour cette route'
    assert route['rules'] == []
