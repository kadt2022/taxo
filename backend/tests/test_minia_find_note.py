"""L'indication de `find_references` : le modèle la reçoit avec l'opération, courte, sans nommer ni famille ni référence,
et ce qu'elle promet est ce que le protocole sert."""
import test_minia_source_reading as reading
from app.minia.application import sources
from test_minia_explore import answer, call, statement
from test_minia_general import Scripted, analysis_of


def test_the_model_receives_the_short_note_with_find_references_and_only_there(make_repo, tmp_path):
    model = Scripted(answer(statement('unknown', 'Rien à conclure.')))
    reading.ask(make_repo, tmp_path, model)
    offered = {item['operation']: item for item in reading.sent(model, 0)['operations']}
    assert offered['find_references']['note'] == sources.FIND_NOTE
    assert 'type sans prefix' in offered['find_references']['note']
    assert 'note' not in offered['find_facts']
    assert 'note' not in offered['describe']


def test_the_note_stays_short_and_names_nothing_of_the_project():
    assert len(sources.FIND_NOTE.encode('utf-8')) < 100
    for word in ('endpoint', 'symbol', 'student', 'Student', 'api'):
        assert word not in sources.FIND_NOTE


def test_the_get_source_note_is_unchanged():
    assert sources.noted({'operation': 'get_source'})['note'] == sources.NOTE
    assert sources.noted({'operation': 'find_facts'}) == {'operation': 'find_facts'}


def test_what_the_note_promises_the_protocol_serves(make_repo, tmp_path):
    listing = lambda message: call('find_references', analysis=analysis_of(message), type='symbol')
    model = Scripted(listing, answer(statement('unknown', 'Rien à conclure.')))
    result = reading.ask(make_repo, tmp_path, model)
    searches = [step for step in result['trajectory'] if step['operation'] == 'find_references']
    assert [step['outcome'] for step in searches] == ['OK']
    assert searches[0]['items'] > 0
