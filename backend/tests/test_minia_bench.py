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


def test_the_reference_bench_has_eighteen_questions_with_their_expected_answers():
    reference = json.loads(bench.QUESTIONS.read_text(encoding='utf-8'))
    assert [item['id'] for item in reference['questions']] == list(range(1, 19))
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
    assert found == ['identité : Ad…', 'identité : ad…', 'courriel', 'courriel', 'mot de passe en clair']
    assert bench.masked_password_kept(['.password(\\"******\\")'])
    assert not bench.masked_password_kept(['.password(\\"admin\\")'])


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
