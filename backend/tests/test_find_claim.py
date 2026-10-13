"""`find_claim` (décision « Taxo témoin », D3) : Taxo dit ce qui lui a été demandé et ce qu'il a trouvé pour ce sujet
et cette relation, avec les preuves. Jamais de verdict ni de motif : `found` n'est qu'une comparaison littérale, et ne
pas trouver n'est pas une absence (la couverture et les limites disent ce qu'il a lu)."""
from test_verify_claim_symbol_scope import ENROLL, taxo_fixture  # noqa: F401


def find(taxo, subject, relation, target=None):
    client, url = taxo
    arguments = {'subject': subject, 'relation': relation, **({'object': target} if target else {})}
    body = {'requests': [{'operation': 'find_claim', 'arguments': arguments}]}
    return client.post(url, json=body).json()['responses'][0]


def objects(response):
    return [item['fact']['object'] for item in response['items']]


def test_what_was_asked_and_what_was_found_without_a_verdict(taxo):
    response = find(taxo, ENROLL, 'ANNOTATED_WITH', 'annotation:PostMapping')
    assert response['asked'] == {'subject': ENROLL, 'relation': 'ANNOTATED_WITH', 'object': 'annotation:PostMapping'}
    assert response['found'] is True and objects(response)[0] == 'annotation:PostMapping'
    assert 'verdict' not in response and 'reason' not in response
    assert response['evidence'], 'chaque fait vient avec sa preuve'


def test_another_form_is_not_found_and_taxo_shows_what_it_has(taxo):
    response = find(taxo, ENROLL, 'ANNOTATED_WITH', 'annotation:org.springframework.web.bind.annotation.PostMapping')
    assert response['found'] is False
    assert objects(response) == ['annotation:PostMapping'], 'ce que Taxo a trouvé, tel quel'
    assert 'verdict' not in response


def test_nothing_found_is_never_an_absence(taxo):
    response = find(taxo, ENROLL, 'CALLS', 'symbol:java:com.acme.web.Orders#absent()')
    assert response['found'] is False and response['items'] == []
    assert response['coverage'], 'la couverture dit où Taxo a lu'
    assert 'verdict' not in response and 'reason' not in response


def test_a_relation_that_needs_an_object_is_refused_without_one(taxo):
    response = find(taxo, ENROLL, 'ANNOTATED_WITH')
    assert response['outcome'] == 'ERROR' and response['error']['code'] == 'INVALID_ARGUMENT'


def test_a_malformed_claim_is_refused_as_before(taxo):
    response = find(taxo, ENROLL, 'CONTAINS', 'Set<Item>')
    assert response['outcome'] == 'ERROR' and response['error']['code'] == 'INVALID_ARGUMENT'
