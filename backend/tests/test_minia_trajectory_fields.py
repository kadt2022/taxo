"""La trajectoire dit, pour la lecture d'une méthode, les champs dont la déclaration a été jointe (`field_context`) :
par leur référence seulement, jamais leur code."""
from app.minia.application.ask import _step

FIELD = 'symbol:java:a.Repo#items'


def test_the_joined_fields_are_named_in_the_step_never_their_code():
    response = {'outcome': 'OK', 'bytes': 300, 'items': [{'text': 'code'}], 'not_sent': [],
                'field_context': [{'field': FIELD, 'text': 'private final Set<String> items;'}]}
    step = _step('get_source', {'reference': 'symbol:java:a.Repo#add()'}, response)
    assert step['fields'] == [FIELD]
    assert 'Set<String>' not in str(step)


def test_a_step_without_field_context_is_unchanged():
    step = _step('get_source', {'reference': 'symbol:java:a.Repo'}, {'outcome': 'OK', 'bytes': 9, 'items': []})
    assert 'fields' not in step
