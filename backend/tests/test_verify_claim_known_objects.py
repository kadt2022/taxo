"""Une affirmation non prouvée dit ce que Taxo établit pour le même sujet et la même relation (`known_objects`) :
la forme qu'il connaît. Des faits de la Maille, jamais un verdict ; reçus par Minia comme des références."""
from app.minia.application import sources
from test_verify_claim_symbol_scope import ENROLL, taxo_fixture, verify  # noqa: F401


def test_a_claim_not_proven_shows_the_objects_taxo_establishes(taxo):
    response = verify(taxo, ENROLL, 'ANNOTATED_WITH', 'annotation:org.springframework.web.bind.annotation.PostMapping')
    assert response['verdict'] == 'NOT_PROVEN'
    assert response['known_objects'] == ['annotation:PostMapping']
    assert response['items'] == [], 'aucun fait ne confirme l’affirmation'


def test_a_confirmed_claim_carries_no_known_objects(taxo):
    assert 'known_objects' not in verify(taxo, ENROLL, 'ANNOTATED_WITH', 'annotation:PostMapping')


def test_a_subject_without_facts_for_the_relation_has_an_empty_list(taxo):
    response = verify(taxo, ENROLL, 'CALLS', 'symbol:java:com.acme.web.Orders#absent()')
    assert response['verdict'] == 'NOT_PROVEN' and response['known_objects'] == []


def test_minia_receives_the_known_objects_as_references():
    item = {'operation': 'verify_claim', 'arguments': {'subject': 's', 'relation': 'CALLS', 'object': 'x'},
            'response': {'outcome': 'OK', 'known_objects': ['symbol:java:a.B#c()']}}
    assert sources.received('symbol:java:a.B#c()', [item])
