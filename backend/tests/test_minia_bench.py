"""Le banc de reference de Minia (TAXO-MINIA-SEC-01, § 4) : ses mesures, et un rejeu complet sur un petit depot."""
import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import minia_bench as bench

NAME, EMAIL = 'Ada Lovelace', 'ada@example.org'
TRUTH = {'security_relations': ['PROTECTED_BY', 'AUTHORIZED_BY', 'PERMITS_ALL', 'CONFIGURES'],
         'security_annotations': ['org.springframework.security.'],
         'security_truth': [['endpoint:GET /api/students', 'PROTECTED_BY', "policy-rule:hasAnyRole('ADMIN')"],
                            ['route-pattern:/**', 'PERMITS_ALL', None]]}


def claim(subject, relation, object_=None, verdict='CONFIRMED', text=''):
    return {'type': 'claim', 'text': text, 'verdict': verdict,
            'claim': {'subject': subject, 'relation': relation, 'object': object_}}


def test_the_reference_bench_has_its_questions_with_their_expected_answers():
    reference = json.loads(bench.QUESTIONS.read_text(encoding='utf-8'))
    assert [item['id'] for item in reference['questions']] == list(range(1, 20))
    security = {item['id'] for item in reference['questions'] if item['theme'] == 'sécurité'}
    assert {9, 11, 18} <= security, 'les tests 9, 11 et 18 du récit portent sur la sécurité'
    assert all(item.get('must') or item.get('must_not') or item.get('direct') for item in reference['questions'])
    assert len(reference['commit']) == 40


def test_a_confirmation_outside_the_hand_established_truth_is_a_false_one():
    result = {'statements': [
        claim('endpoint:GET /api/students', 'PROTECTED_BY', "policy-rule:hasAnyRole('ADMIN')"),
        claim('endpoint:GET /api/students', 'PROTECTED_BY', 'policy-rule:permitAll()'),
        claim('route-pattern:/**', 'PERMITS_ALL'),
        claim('symbol:A', 'ANNOTATED_WITH', 'annotation:org.springframework.security.access.prepost.PreAuthorize'),
        claim('symbol:A', 'ANNOTATED_WITH', 'annotation:RestController'),
        claim('symbol:A', 'CALLS', 'symbol:B'),
        claim('endpoint:GET /api/students', 'PROTECTED_BY', 'policy-rule:permitAll()', verdict='NOT_PROVEN'),
        {'type': 'interpretation', 'text': 'La route est ouverte.'}]}
    assert bench.false_confirmations(result, TRUTH) == [
        ['endpoint:GET /api/students', 'PROTECTED_BY', 'policy-rule:permitAll()'],
        ['symbol:A', 'ANNOTATED_WITH', 'annotation:org.springframework.security.access.prepost.PreAuthorize']]
    assert bench.unjustified(result) == 1


def test_an_answer_is_exact_with_every_expected_mention_and_no_forbidden_wording():
    question = {'must': [['ADMIN'], ['non', 'refus']], 'must_not': ['seulement (une )?authentification']}
    good = {'answer': 'Non : il faut le rôle ADMIN.', 'unknown': ''}
    assert bench.exactness(question, good) == {'exact': True, 'missing': [], 'forbidden': []}
    vague = {'answer': 'La route exige seulement une authentification.', 'unknown': ''}
    assert bench.exactness(question, vague) == {
        'exact': False, 'missing': [['ADMIN'], ['non', 'refus']], 'forbidden': ['seulement (une )?authentification']}
    verified = {'statements': [claim('endpoint:GET /api/students', 'PROTECTED_BY', "hasAnyRole('ADMIN')",
                                     text='Refusé sans le rôle.')]}
    assert bench.exactness(question, verified)['exact'], 'le texte dit par Taxo compte aussi'


def test_a_payload_leaks_an_identity_an_address_or_a_clear_password_never_their_value():
    known = [NAME, EMAIL]
    assert bench.leaks('{"author":"personne-1","code":"password(\\"******\\")"}', known) == []
    found = bench.leaks(f'{NAME} <{EMAIL}> password("admin") bob@example.org', known)
    assert found == ['identité : Ad…', 'identité : ad…', 'courriel', 'courriel', 'secret en clair']
    assert bench.masked_password_kept(['.password(\\"******\\")'])
    assert not bench.masked_password_kept(['.password(\\"admin\\")'])


@pytest.mark.parametrize(('payload', 'nature'), [
    ('token = "ghp_abcdefghijklmnopqrstuvwxyz0123"', 'jeton'),
    ('-----BEGIN RSA PRIVATE KEY-----\nMIIE', 'clé privée'),
    ('jdbc postgres://app:s3cret@db:5432/app', 'identifiants dans une adresse'),
    ('spring.datasource.password=admin', 'secret en clair'),
    ('  password: admin', 'secret en clair'),
    ('{\\"api_key\\": \\"abc123\\"}', 'secret en clair'),
    ('String password = "admin";', 'secret en clair'),
])
def test_every_secret_form_the_protection_masks_is_a_leak_when_it_reaches_the_provider(payload, nature):
    assert nature in bench.leaks(payload, [])


@pytest.mark.parametrize('payload', [
    'password = "******"', 'password: ******', 'postgres://app:******@db/app', 'token: ${API_TOKEN}',
    'secret: null', 'password: |', '"withheld": {"secrets": 2}', 'Le mot de passe est écrit en dur.'])
def test_a_masked_or_absent_secret_is_not_a_leak(payload):
    assert bench.leaks(payload, []) == []


def test_an_answer_of_the_wrong_polarity_is_never_exact():
    questions = {item['id']: item for item in json.loads(bench.QUESTIONS.read_text(encoding='utf-8'))['questions']}
    wrong = {11: 'EnableMethodSecurity n’est pas activée dans ce projet.',
             12: 'Non, la protection CSRF n’est pas désactivée : elle reste active (pas de disable).',
             13: 'Non, ce commit n’introduit pas de mot de passe écrit en dur.',
             9: 'Oui : ADMIN et TEACHER, et STUDENT aussi, sans refus.',
             18: 'Oui, ADMIN ou TEACHER ne sont pas requis : non, rien de plus.'}
    for identifier, answer in wrong.items():
        assert not bench.exactness(questions[identifier], {'answer': answer})['exact'], identifier
    right = {11: 'Oui : @EnableMethodSecurity est posée sur SecurityConfig, la sécurité des méthodes est activée.',
             12: 'Non : csrf.disable() la désactive dans SecurityConfig.',
             13: 'Oui : trois mots de passe sont écrits en dur, valeurs masquées.',
             9: 'Non : GET /api/students exige ADMIN ou TEACHER ; STUDENT est refusé.',
             18: 'Non : il faut aussi le rôle ADMIN ou TEACHER.'}
    for identifier, answer in right.items():
        assert bench.exactness(questions[identifier], {'answer': answer})['exact'], identifier


def test_the_bench_replays_the_configured_provider_and_refuses_one_that_is_not(monkeypatch):
    monkeypatch.setenv('MINIA_OLLAMA_MODEL', 'qwen')
    monkeypatch.setenv('MINIA_CLAUDE_MODEL', 'claude-x')
    monkeypatch.setenv('MINIA_PROVIDER', 'claude')
    recorder = bench.Recorder()
    name, models = bench.recorded_models(recorder, None)
    assert name == 'claude' and set(models) == {'ollama', 'claude'}
    assert bench.recorded_models(recorder, 'ollama')[0] == 'ollama'
    monkeypatch.delenv('MINIA_CLAUDE_MODEL')
    with pytest.raises(SystemExit, match='claude'):
        bench.recorded_models(recorder, None)


def test_the_server_sent_events_give_the_result_or_the_failure():
    text = ('event: minia.started\ndata: {"request_id": "r"}\n\n: Minia attend le modèle\n\n'
            'event: minia.completed\ndata: {"status": "ANSWERED"}\n\n')
    assert bench.outcome(bench.events(text)) == ({'status': 'ANSWERED'}, None)
    failed = 'event: minia.failed\ndata: {"code": "MINIA_CONFIDENTIALITY_REFUSED", "message": "refusé"}\n\n'
    assert bench.outcome(bench.events(failed)) == (None, 'MINIA_CONFIDENTIALITY_REFUSED : refusé')
    assert bench.outcome([]) == (None, 'aucun résultat')


class Scripted:
    """Un fournisseur sans diffusion : il rend une reponse de paquet ou d'exploration selon la consigne recue."""

    provider, model_name, explores = 'scripted', 'scripted-1', False

    def complete(self, system, user, schema=None):
        return json.dumps({'cited': [], 'unknown': '',
                           'answer': 'Non : ADMIN ou TEACHER. Un mot de passe est écrit en dur, valeur masquée.'})


class Streaming(Scripted):
    def stream(self, system, user, schema=None):
        yield self.complete(system, user, schema)
        return 'scripted-2'


def test_the_recording_keeps_what_the_provider_receives_and_its_interface():
    recorder = bench.Recorder()
    plain = bench.Recording(Scripted(), recorder)
    assert (plain.provider, plain.explores) == ('scripted', False)
    with pytest.raises(AttributeError):
        plain.stream  # noqa: B018 - un fournisseur sans diffusion le reste
    plain.complete('consignes', 'message 1')
    streamed = bench.Recording(Streaming(), recorder)
    pieces = streamed.stream('consignes', 'message 2')
    assert next(pieces).startswith('{')
    with pytest.raises(StopIteration) as end:
        next(pieces)
    assert end.value.value == 'scripted-2', 'le modèle qui a répondu reste dit'
    assert [call.payload for call in recorder.calls] == ['message 1', 'message 2']
    assert all(call.tokens is None for call in recorder.calls), 'aucun jeton imaginé'


SECURITY = '''package com.example;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public class SecurityConfig {
    @Bean
    InMemoryUserDetailsManager users() {
        return new InMemoryUserDetailsManager(User.withUsername("admin").password("admin123").roles("ADMIN").build());
    }
}
'''


def test_a_full_replay_measures_each_answer_and_finds_no_leak(make_repo, git, tmp_path):
    repository = make_repo({'README.md': 'démo\n'})
    (repository / 'src').mkdir()
    (repository / 'src' / 'SecurityConfig.java').write_text(SECURITY, encoding='utf-8')
    git(repository, 'add', '-A')
    git(repository, '-c', f'user.name={NAME}', '-c', f'user.email={EMAIL}', 'commit', '-qm',
        'feat: utilisateurs\n\nCo-authored-by: Bob Martin <bob@example.org>')
    sha = git(repository, 'rev-parse', 'HEAD')
    reference = {**TRUTH, 'commit': sha, 'questions': [
        {'id': 1, 'theme': 'confidentialité', 'question': 'Qui est l’auteur de ce commit ?', 'commit': sha[:7],
         'direct': True},
        {'id': 2, 'theme': 'confidentialité', 'question': 'Ce commit écrit-il un mot de passe en dur ?',
         'commit': sha[:7], 'source_context': True, 'masked_password': True,
         'must': [['mot de passe'], ['en dur']]},
        {'id': 3, 'theme': 'sécurité', 'question': 'Que changent les 2 derniers commits ?',
         'must': [['ADMIN']], 'must_not': ['seulement une authentification']}]}
    recorder = bench.Recorder()
    models = {'scripted': bench.Recording(Scripted(), recorder)}
    options = Namespace(runs=2, provider=None, payloads=tmp_path / 'charges.jsonl')
    measured = bench.run(f'sqlite:///{tmp_path / "banc.db"}', repository, options, reference, models, recorder)

    assert [(item['run'], item['id']) for item in measured] == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)]
    direct, password, project = measured[:3]
    assert (direct['mode'], direct['llm_calls'], direct['exact']) == ('taxo', 0, True)
    assert password['llm_calls'] == 1 and password['exact'] and password['masked_password_kept']
    assert project['exact'] and project['bytes_sent'] > 0
    assert all(item['leaks'] == [] and item['false_confirmations'] == [] for item in measured)
    assert all(item['tokens_sent'] is None for item in measured if item['llm_calls'])
    payloads = [json.loads(line) for line in options.payloads.read_text(encoding='utf-8').splitlines()]
    assert len(payloads) == sum(item['llm_calls'] for item in measured)
    for line in payloads:
        assert NAME not in line['payload'] and EMAIL not in line['payload'] and 'admin123' not in line['payload']
    report = bench.summary(measured, 'scripted')
    assert 'Réponses : 6 ; exactes : 6 (100%)' in report and 'Fuites dans les charges envoyées : 0' in report


# --- Mesure D de l'Adaptive Tile (TAXO-MIP-ADT-01) : l'apport des Tuiles et du code, et les séries comparées ---

def test_the_contribution_counts_the_tiles_and_the_code_served_or_refused():
    trajectory = [{'operation': 'describe', 'outcome': 'OK', 'bytes': 900},
                  {'operation': 'get_tile', 'outcome': 'OK', 'bytes': 1200},
                  {'operation': 'get_source', 'outcome': 'OK', 'bytes': 400, 'items': 1},
                  {'operation': 'get_source', 'outcome': 'OK', 'bytes': 250, 'items': 0, 'not_sent': ['CONFIDENTIAL']},
                  {'operation': 'get_source', 'outcome': 'ERROR', 'bytes': 300}]
    # Une réponse OK sans aucune pièce n'est pas du code : elle compte comme refusée, sans ses octets.
    assert bench.contribution(trajectory) == {'tiles': {'served': 1, 'refused': 0, 'bytes': 1200},
                                              'sources': {'served': 1, 'refused': 2, 'bytes': 400}}
    assert bench.contribution([]) == {'tiles': {'served': 0, 'refused': 0, 'bytes': 0},
                                      'sources': {'served': 0, 'refused': 0, 'bytes': 0}}


def answer_row(exact, tiles=0, sources=0, tokens=None):
    return {'exact': exact, 'false_confirmations': [], 'unjustified': 0, 'leaks': [], 'taxo_operations': 3,
            'llm_calls': 2, 'bytes_sent': 1000, 'tokens_sent': tokens, 'seconds': 1.5,
            'tiles': {'served': tiles, 'refused': 0, 'bytes': 800 * tiles},
            'sources': {'served': sources, 'refused': 0, 'bytes': 300 * sources}}


def test_the_series_are_compared_side_by_side_without_imagined_tokens():
    reports = [{'series': 'ancienne', 'model': 'm', 'taxo': 'a' * 40, 'answers': [answer_row(False), answer_row(True)]},
               {'series': 'faits', 'model': 'm', 'taxo': 'b' * 40, 'answers': [answer_row(True, tiles=1)]},
               {'series': 'faits+code', 'model': 'm', 'answers': [answer_row(True, 1, 2, tokens=40)]}]
    table = bench.compared(reports).splitlines()
    assert table[2] == '| Mesure | ancienne | faits | faits+code |'
    assert '| Taxo | aaaaaaa | bbbbbbb | ? |' in table
    assert '| Réponses exactes | 1/2 | 1/1 | 1/1 |' in table
    assert '| Jetons envoyés | non rendus | non rendus | 40 |' in table
    assert '| Pièces sources servies (refusées) | 0 (0) | 0 (0) | 2 (0) |' in table
    assert '| Exactes avec du code | — | — | 1/1 |' in table
    assert '| Exactes sans Tuile ni code | 1/2 | — | — |' in table


def test_the_series_with_code_reads_the_method_and_the_series_without_never_does(make_repo, tmp_path):
    """Le banc rejoue la question de la démonstration : avec `--source`, la Tuile puis le code ; sans, le même
    parcours, et `get_source` refusée sans rien lire."""
    from test_minia_explore import answer, call, statement
    from test_minia_general import Scripted as Exploring
    from test_minia_general import analysis_of
    from test_minia_source_reading import BODY, FILES, FIND

    repository = make_repo(FILES)
    reference = {**TRUTH, 'commit': bench.full_sha(repository, 'HEAD'), 'questions': [
        {'id': 5, 'theme': 'appels', 'question': 'Que fait StudentService.findStudents ?',
         'must': [['findStudents']]}]}
    for source, served, refused in ((True, 1, 0), (False, 0, 1)):
        model = Exploring(
            lambda sent: call('find_references', analysis=analysis_of(sent), prefix='StudentService.findStudents',
                              match='NAME'),
            call('get_tile', reference=FIND, profile='method-context/1'), call('get_source', reference=FIND),
            answer(statement('interpretation', 'findStudents rendrait tous les étudiants.')))
        recorder = bench.Recorder()
        options = Namespace(runs=1, provider=None, payloads=None, source=source)
        (tmp_path / str(source)).mkdir()
        measured, = bench.run(f'sqlite:///{tmp_path / str(source) / "banc.db"}', repository, options, reference,
                              {'scripted': bench.Recording(model, recorder)}, recorder)
        assert measured['exact'] and measured['tiles']['served'] == 1
        assert (measured['sources']['served'], measured['sources']['refused']) == (served, refused)
        assert (BODY.split('\n')[1].strip() in json.dumps([item.payload for item in recorder.calls])) == source


def test_a_failed_answer_still_counts_the_tiles_and_code_already_streamed():
    """Une demande qui échoue après une Tuile et une pièce : leur apport est compté, rien n'est perdu."""
    streamed = [{'operation': 'get_tile', 'outcome': 'OK', 'bytes': 900, 'items': 3},
                {'operation': 'get_source', 'outcome': 'OK', 'bytes': 300, 'items': 1}]
    question = {'id': 5, 'theme': 'appels', 'question': 'Que fait X ?', 'must': [['X']]}
    entry = bench.score(question, None, 'MINIA_PROVIDER_ERROR : coupé', [], 1.0, TRUTH, [], streamed)
    assert not entry['exact'] and entry['taxo_operations'] == 2
    assert entry['tiles']['served'] == 1 and entry['sources'] == {'served': 1, 'refused': 0, 'bytes': 300}


def test_the_reading_question_lists_the_code_a_human_reads_to_answer():
    reference = json.loads(bench.QUESTIONS.read_text(encoding='utf-8'))
    reading = next(item for item in reference['questions'] if item['id'] == 19)
    assert reading['must_read'] == ['EnrollmentService', 'EnrollmentRepository', 'model.Enrollment']
    assert reading['must'] and reading['must_not'] and reading['truth']
    written = json.dumps(reading['must'])
    assert all(name in written for name in ('EnrollmentController', 'EnrollmentService', 'EnrollmentRepository',
                                            'exception')), 'le parcours demandé est noté, pas seulement la conclusion'


def test_a_reading_gesture_is_missed_until_the_code_is_read():
    question = {'must_read': ['EnrollmentRepository', 'model.Enrollment']}
    read = [{'operation': 'get_source', 'outcome': 'OK',
             'arguments': {'reference': 'symbol:java:com.x.repository.EnrollmentRepository#save(Long,Long)'}},
            {'operation': 'get_source', 'outcome': 'ERROR', 'arguments': {'reference': 'symbol:java:com.x.model.Enrollment'}}]
    read[0]['items'] = 1
    assert bench.reads(question, read) == ['model.Enrollment'], 'une lecture refusée n’est pas une lecture'
    read[0]['items'] = 0
    assert 'EnrollmentRepository' in bench.reads(question, read), 'une pièce non livrée n’est pas une lecture'
    assert bench.reads(question, []) == ['EnrollmentRepository', 'model.Enrollment']


def test_malformed_claims_and_chosen_operations_are_counted():
    result = {'statements': [{'type': 'claim', 'verdict': None, 'error': {'code': 'INVALID_ARGUMENT'}},
                             {'type': 'claim', 'verdict': None, 'error': {'code': 'NOT_VERIFIED'}},
                             {'type': 'claim', 'verdict': 'CONFIRMED'}]}
    assert bench.malformed(result) == 1
    steps = [{'operation': 'describe'}, {'operation': 'find_references'}, {'operation': 'get_source'},
             {'operation': 'verify_claim'}]
    assert bench.chosen(steps) == 2
    seeded = [{'operation': 'describe'}, {'operation': 'get_commit'}, {'operation': 'diff_facts'}]
    assert bench.chosen(seeded) == 1, 'le get_commit servi d’office n’est pas un choix du modèle'


def test_the_restitution_of_each_analyzer_is_said():
    described = {'items': [
        {'kind': 'analyzer', 'analyzer': 'taxo.java-calls',
         'restitution': {'sites_restituted': 29, 'sites_not_restituted': 72, 'subjects_not_read': 0}},
        {'kind': 'analyzer', 'analyzer': 'taxo.ancien'}, {'kind': 'relation', 'relation': 'CALLS'}]}
    assert bench.restitution_lines(described) == [
        'restitution taxo.java-calls : sites restitués 29, non restitués 72 (71.3 %), sujets non lus 0']

