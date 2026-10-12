"""La garde de conclusion : une conclusion qui porte un « unknown » et cite un symbole reçu de Taxo, dont le code est
lisible et n'a pas été lu, revient une fois au modèle. Il lit le code ou garde son inconnu : la règle compare des noms à des
références reçues, elle ne juge pas la réponse, n'appelle pas Taxo et ne compte pas dans la limite des opérations."""
from app.minia.application import sources
from test_minia_explore import answer, call, statement
from test_minia_general import Scripted
from test_minia_source_reading import BODY, FIND, ask, found, sent

UNREAD = statement('unknown', 'Le code de StudentService n’a pas été lu : impossible de dire ce que rend findStudents.')
KEPT = statement('unknown', 'Le code de StudentService reste à lire.')
READ = statement('interpretation', 'findStudents rendrait tous les étudiants du repository.')


def guards(message):
    return [item for item in message['trajectory'] if item['operation'] == sources.GUARD]


def test_an_unknown_on_a_readable_unread_symbol_is_returned_once_and_the_model_reads_it(make_repo, tmp_path):
    model = Scripted(found, answer(UNREAD), call('get_source', reference=FIND), answer(READ))
    result = ask(make_repo, tmp_path, model)
    returned = guards(sent(model, 2))
    assert [item['response']['unread'] for item in returned] == [[FIND]]
    assert returned[0]['response']['outcome'] == sources.RETURNED
    assert 'get_source' in returned[0]['response']['note']
    assert sent(model, 3)['trajectory'][-1]['response']['items'][0]['text'] == BODY, 'le code lu est le vrai'
    assert result['returned'] == [FIND]
    assert [item['type'] for item in result['statements']] == ['interpretation']


def test_the_return_is_not_an_operation_of_taxo_and_costs_no_call(make_repo, tmp_path):
    model = Scripted(found, answer(UNREAD), answer(KEPT))
    result = ask(make_repo, tmp_path, model)
    assert [step['operation'] for step in result['trajectory']] == ['describe', 'find_references']
    assert sent(model, 2)['calls_left'] == sent(model, 1)['calls_left']


def test_the_model_may_keep_its_unknown_and_is_never_returned_twice(make_repo, tmp_path):
    model = Scripted(found, answer(UNREAD), answer(KEPT))
    result = ask(make_repo, tmp_path, model)
    assert len(model.calls) == 3
    assert result['statements'][0]['text'] == KEPT['text'], 'l’inconnu gardé est rendu tel quel'
    assert result['returned'] == [FIND]


def test_a_symbol_already_read_is_not_returned(make_repo, tmp_path):
    model = Scripted(found, call('get_source', reference=FIND), answer(UNREAD))
    result = ask(make_repo, tmp_path, model)
    assert len(model.calls) == 3
    assert 'returned' not in result


def test_a_name_never_received_from_taxo_is_not_returned(make_repo, tmp_path):
    model = Scripted(found, answer(statement('unknown', 'Le code de EnrollmentRepository n’a pas été lu.')))
    result = ask(make_repo, tmp_path, model)
    assert len(model.calls) == 2
    assert 'returned' not in result


def test_a_part_of_a_longer_name_is_not_a_mention(make_repo, tmp_path):
    model = Scripted(found, answer(statement('unknown', 'Le code de StudentServiceImpl n’a pas été lu.')))
    assert 'returned' not in ask(make_repo, tmp_path, model)


def test_without_the_consent_to_read_code_nothing_is_returned(make_repo, tmp_path):
    model = Scripted(found, answer(UNREAD))
    result = ask(make_repo, tmp_path, model, source=False)
    assert len(model.calls) == 2
    assert 'returned' not in result


def test_a_conclusion_without_an_unknown_is_never_returned(make_repo, tmp_path):
    model = Scripted(found, answer(statement('interpretation', 'Le code de StudentService n’a pas été lu.')))
    assert 'returned' not in ask(make_repo, tmp_path, model)


def test_a_symbol_cited_by_a_claim_is_returned_when_the_conclusion_has_an_unknown(make_repo, tmp_path):
    claim = statement('claim', 'StudentService.findStudents existe.', FIND, 'DECLARED_IN', '')
    model = Scripted(found, answer(claim, statement('unknown', 'Impossible de dire ce que rend la méthode.')),
                     answer(KEPT))
    assert ask(make_repo, tmp_path, model)['returned'] == [FIND]


def test_a_field_is_never_returned_since_its_code_cannot_be_read():
    field = 'symbol:java:com.example.demo.service.StudentService#studentRepository'
    exchanged = [{'operation': 'get_neighborhood', 'arguments': {},
                  'response': {'outcome': 'OK', 'items': [{'reference': field}, {'reference': FIND}]}}]
    claim = {'type': 'claim', 'text': 'StudentService garde un repository.',
             'claim': {'subject': field, 'relation': 'HAS', 'object': ''}}
    unknown = {'type': 'unknown', 'text': 'Le code de StudentService n’a pas été lu.'}
    assert sources.unread([claim, unknown], exchanged) == [FIND]


def test_a_fallback_after_the_return_still_says_the_conclusion_was_returned(make_repo, tmp_path):
    model = Scripted(found, answer(UNREAD), 'pas du JSON', lambda sent: '{"cited": [], "answer": "", "unknown": "x"}')
    result = ask(make_repo, tmp_path, model)
    assert result['mode'] == 'paquet'
    assert result['returned'] == [FIND]
