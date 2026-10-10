"""TAXO-MINIA-SEC-01, E1 : un verdict vaut pour ce que Taxo a lu. Une confirmation porte les limites que Taxo
connait sur le sujet ou l'objet de l'affirmation, avec leur raison."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.protocol.application.exchange import Exchange
from tests.method_security_sources import FILES

ENDPOINT = 'endpoint:GET /api/items'


@pytest.fixture(name='taxo')
def taxo_fixture(make_repo, tmp_path):
    repo = make_repo(FILES, 'boutique')
    app = create_app(f'sqlite:///{tmp_path / "limites.db"}', [repo], minia={})
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Boutique', 'path': str(repo)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        yield client, f'/api/projects/{project["id"]}/taxo-query'


def verify(taxo, max_bytes=None, **claim):
    client, url = taxo
    request = {'operation': 'verify_claim', 'arguments': claim}
    if max_bytes is not None:
        request['max_bytes'] = max_bytes
    response = client.post(url, json={'requests': [request]})
    assert response.status_code == 200, response.text
    return response.json()['responses'][0]


def test_a_confirmed_url_rule_carries_the_method_security_that_taxo_did_not_read(taxo):
    response = verify(taxo, subject=ENDPOINT, relation='PROTECTED_BY', object='policy-rule:authenticated()')
    assert response['verdict'] == 'CONFIRMED', 'la règle d’URL est bien établie'
    [limit] = response['limits']
    assert limit['subject'] == ENDPOINT and limit['type'] == 'NOT_INTERPRETED'
    assert '@Secured' in limit['reason'], 'la confirmation dit ce qu’elle ne couvre pas'
    assert limit['producer'] == 'taxo.spring-security'


def test_a_claim_without_unread_zone_has_no_limit(taxo):
    response = verify(taxo, subject='route-pattern:/api/**', relation='AUTHORIZED_BY', object='authenticated()')
    assert response['verdict'] == 'CONFIRMED' and response['limits'] == []


def test_a_handled_by_confirmation_carries_only_the_limits_of_its_own_relation(taxo):
    response = verify(taxo, subject=ENDPOINT, relation='HANDLED_BY',
                      object='symbol:java:com.example.shop.web.ItemController#items()')
    assert response['verdict'] == 'CONFIRMED'
    assert response['limits'] == [], 'la sécurité n’est pas une limite de HANDLED_BY : chaque relation garde son sens'


def test_a_single_valued_confirmation_is_not_limited_by_the_security_left_unread(taxo):
    response = verify(taxo, subject=ENDPOINT, relation='MATCHED_BY', object='route-pattern:/api/**')
    assert response['verdict'] == 'CONFIRMED'
    assert response['limits'] == [], 'la sécurité de méthode ne change pas le motif qui capture la route'


def test_a_single_valued_confirmation_keeps_the_limits_of_an_ambiguous_target(make_repo, tmp_path):
    duplicated = {'src/main/java/demo/A.java': 'package demo;\n\npublic class A {\n    private B b;\n}\n',
                  'src/main/java/demo/B.java': 'package demo;\n\npublic class B {\n}\n',
                  'src/other/java/demo/B.java': 'package demo;\n\npublic class B {\n}\n'}
    repo = make_repo(duplicated, 'ambigu')
    app = create_app(f'sqlite:///{tmp_path / "ambigu.db"}', [repo], minia={})
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Ambigu', 'path': str(repo)}).json()
        client.post(f'/api/projects/{project["id"]}/scans')
        taxo = client, f'/api/projects/{project["id"]}/taxo-query'
        response = verify(taxo, subject='symbol:java:demo.A#b', relation='TYPED_AS', object='symbol:java:demo.B')
    assert response['verdict'] == 'CONFIRMED'
    assert {limit['subject'] for limit in response['limits']} == {'symbol:java:demo.B'}, \
        'la cible ambiguë accompagne la confirmation'


def test_a_claim_that_is_not_proven_still_says_why_and_what_was_not_read(taxo):
    response = verify(taxo, subject=ENDPOINT, relation='PROTECTED_BY', object="policy-rule:hasRole('ADMIN')")
    assert (response['verdict'], response['reason']) == ('NOT_PROVEN', 'NOT_INTERPRETED')
    assert '@Secured' in response['limits'][0]['reason']


# --- Minia : la limite accompagne le verdict, et un repli ne prétend pas que Taxo ne sait rien ---------------------

def test_minia_shows_the_limits_with_the_verdict_of_her_claim(make_repo, tmp_path):
    from test_minia_explore import answer, statement
    from test_minia_general import Scripted, ask
    repo = make_repo(FILES, 'boutique-minia')
    claim = statement('claim', 'GET /api/items exige seulement une authentification.', ENDPOINT, 'PROTECTED_BY',
                      'policy-rule:authenticated()')
    result, _, _ = ask(repo, tmp_path, Scripted(answer(claim)), 'Qui peut lire GET /api/items ?')
    [checked] = result['statements']
    assert checked['verdict'] == 'CONFIRMED'
    assert ['@Secured' in limit['reason'] for limit in checked['limits']] == [True], \
        'le « seulement » de Minia est contredit par la limite que Taxo affiche avec le verdict'


def test_facts_that_did_not_fit_are_never_said_unknown(tmp_path, make_repo, monkeypatch):
    from app.minia.domain import briefing
    from test_java_calls import fixture_files
    from test_minia_general import WHO_CALLS, Scripted, ask
    original = briefing.tile
    monkeypatch.setattr(briefing, 'tile', lambda *args: original(*args[:-1], 1))
    model = Scripted(explores=False)
    result, _, _ = ask(make_repo(fixture_files()), tmp_path, model, WHO_CALLS)
    assert model.calls == [] and result['facts_not_sent'] > 0
    assert 'aucun n\'a tenu dans la place du modèle' in result['unknown']
    assert 'ne connaît aucun fait' not in result['unknown']


def test_limits_that_do_not_fit_are_counted_never_cost_the_verdict(taxo):
    claim = {'subject': ENDPOINT, 'relation': 'PROTECTED_BY', 'object': 'policy-rule:authenticated()'}
    full = verify(taxo, **claim)
    # Le plus petit budget qui sert encore la reponse : les faits n'y tiennent plus, la limite non plus.
    served = [response for response in (verify(taxo, max_bytes=budget, **claim)
                                        for budget in range(full['bytes'], 0, -32)) if response['outcome'] == 'OK']
    tight = served[-1]
    assert tight['verdict'] == 'CONFIRMED', 'le verdict reste servi'
    assert tight['limits'] == []
    assert {'what': 'limits', 'count': 1, 'reason': 'BUDGET'} in tight['not_sent'], 'la limite tue est comptée'


@pytest.mark.parametrize('verdict, expected', [('CONFIRMED', []), ('REFUTED', []), ('NOT_PROVEN', ['commit:abc'])])
def test_a_decisive_verdict_on_a_single_valued_relation_ignores_what_was_not_read_on_its_subject(verdict, expected):
    gap = {'subject': 'commit:abc', 'coverage_type': 'NOT_INTERPRETED', 'reason': 'chemin non représentable',
           'produced_by': {'producer_id': 'taxo.git'}}
    git = SimpleNamespace(relations={'AUTHORED_BY'}, coverage=[gap])
    exchange = SimpleNamespace(analyzers=lambda: [git])
    limits = Exchange.limits(exchange, 'AUTHORED_BY', {'commit:abc', 'person:x@example.org'}, verdict, 'commit:abc')
    assert [limit['subject'] for limit in limits] == expected, 'l’auteur établi exclut tout autre'
