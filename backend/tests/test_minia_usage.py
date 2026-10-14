"""Récit TAXO-RECIT-REDUCTION-PAYLOAD-MINIA, R0 : ce que coûte une demande, mesuré sans rien changer.

Chaque appel au modèle est relevé (octets envoyés après protection, compteurs rapportés par le fournisseur) ; la réponse
finale porte le relevé en diagnostic. Un compteur que le fournisseur ne rapporte pas reste « non rapporté », jamais zéro.
Relever les jetons qu'un fournisseur met en cache de lui-même n'active aucun cache : la requête envoyée est inchangée."""
import io
import json
from types import SimpleNamespace

import httpx

from app.minia.application import trace
from app.minia.application.protected_model import ProtectedModel
from app.minia.domain import usage
from app.minia.domain.confidentiality import Disclosure
from test_minia_claude import FakeMessages, FakeStream, claude, text_message
from test_minia_explore import ScriptedModel, answer, call, completed, repo_fixture, run, statement  # noqa: F401
from test_minia_gemini import ANSWER, gemini, reply

CLAUDE_USAGE = SimpleNamespace(input_tokens=1200, output_tokens=80, cache_read_input_tokens=0,
                               cache_creation_input_tokens=0)
GEMINI_USAGE = {'promptTokenCount': 900, 'cachedContentTokenCount': 300, 'candidatesTokenCount': 40,
                'thoughtsTokenCount': 25}


# --- Les compteurs, dans les catégories du fournisseur ----------------------------------------------------------

def test_claude_counters_are_read_as_reported_and_reasoning_is_not_invented():
    assert usage.claude(CLAUDE_USAGE) == {'input': 1200, 'cache_read': 0, 'cache_write': 0, 'output': 80,
                                          'reasoning': None}
    assert usage.claude(None) == dict.fromkeys(usage.KEYS), 'sans usage, rien n est rapporté'


def test_gemini_counters_are_read_as_reported_and_cache_write_is_not_invented():
    assert usage.gemini(GEMINI_USAGE) == {'input': 900, 'cache_read': 300, 'cache_write': None, 'output': 40,
                                          'reasoning': 25}
    assert usage.gemini({'promptTokenCount': -1, 'candidatesTokenCount': True})['input'] is None, \
        'une valeur invalide n est jamais prise pour un compte'


def test_a_total_is_given_only_when_every_call_reported_it():
    ledger = usage.Ledger()
    model = SimpleNamespace(provider='claude', model_name='claude-test')
    ledger.record(model, 'consignes', 'message', usage.counters(input=10, output=2))
    ledger.record(model, 'consignes', 'un autre message', usage.counters(input=5))
    report = ledger.report()
    assert report['tokens']['input'] == 15
    assert report['tokens']['output'] is None and report['unreported']['output'] == 1, \
        'un compteur manquant sur un appel : non rapporté, jamais additionné comme zéro'
    assert report['sent_bytes'] == len('consignes') * 2 + len('message') + len('un autre message')
    assert report['input_excludes_cache'] == {'claude': True}


def test_taxo_bytes_separate_the_exploration_from_the_verifications_minia_runs_after_the_answer():
    trajectory = [{'operation': 'describe', 'bytes': 100}, {'operation': 'get_tile', 'bytes': 50},
                  {'operation': 'find_claim', 'bytes': 30}, {'operation': 'find_claim', 'bytes': 20}]
    report = usage.Ledger().report(trajectory, verification_from=2)
    assert report['taxo_bytes'] == {'exploration': 150, 'verification': 50}
    assert report['calls'] == 0 and report['tokens'] == dict.fromkeys(usage.KEYS)


# --- Les adaptateurs rapportent sans rien changer à la requête -------------------------------------------------

def test_claude_reports_the_usage_of_a_call_and_sends_the_same_request():
    messages = FakeMessages(reply=ANSWER)
    messages.create = lambda **request: (messages.calls.append(request),
                                          SimpleNamespace(**vars(text_message(ANSWER)), usage=CLAUDE_USAGE))[1]
    reported = {}
    claude(messages).complete('consignes', 'faits', usage=reported.update)
    assert reported == usage.claude(CLAUDE_USAGE)
    assert 'cache_control' not in json.dumps(messages.calls[0], default=str), 'R0 ne demande aucun cache'


def test_claude_reports_the_usage_of_a_streamed_call():
    class Measured(FakeStream):
        def get_final_message(self):
            return SimpleNamespace(**vars(super().get_final_message()), usage=CLAUDE_USAGE)

    messages = FakeMessages(chunks=[ANSWER])
    messages.stream = lambda **request: (messages.calls.append(request), Measured([ANSWER]))[1]
    reported = {}
    assert ''.join(claude(messages).stream('consignes', 'faits', usage=reported.update)) == ANSWER
    assert reported['input'] == 1200 and reported['reasoning'] is None


def test_gemini_reports_the_usage_carried_by_the_last_streamed_piece():
    lines = [f'data: {json.dumps(reply(ANSWER[:10], finish=None))}',
             f'data: {json.dumps(reply(ANSWER[10:], usageMetadata=GEMINI_USAGE))}']
    seen, reported = [], {}

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, text='\n\n'.join(lines) + '\n\n')

    assert ''.join(gemini(handler).stream('consignes', 'faits', usage=reported.update)) == ANSWER
    assert reported == usage.gemini(GEMINI_USAGE)
    assert 'cachedContent' not in json.dumps(seen[0]), 'R0 ne demande aucun cache Gemini'


def test_gemini_reports_the_usage_of_a_direct_call():
    reported = {}
    gemini(lambda request: httpx.Response(200, json=reply(ANSWER, usageMetadata=GEMINI_USAGE))).complete(
        'consignes', 'faits', usage=reported.update)
    assert reported['cache_read'] == 300


# --- Le passage protégé relève chaque appel, sans contenu --------------------------------------------------------

def test_the_protected_passage_records_each_call_with_the_protected_size_and_no_content():
    model = ScriptedModel('{"a": 1}', '{"b": 2}')
    protected = ProtectedModel(model, Disclosure(['Jean Dupont <secret.author@example.invalid>']))
    protected.complete('consignes', json.dumps({'question': 'Que fait secret.author@example.invalid ?'}))
    protected.complete('consignes', json.dumps({'question': 'suite'}))
    assert 'secret.author' not in model.calls[0][1], 'le message part protégé'
    report = protected.ledger.report()
    assert report['calls'] == 2
    first = report['per_call'][0]
    assert first['message_bytes'] == len(model.calls[0][1].encode('utf-8')), \
        'les octets comptés sont ceux du message protégé, réellement envoyé'
    assert report['tokens'] == dict.fromkeys(usage.KEYS) and report['unreported']['input'] == 2, \
        'un fournisseur qui ne rapporte rien : non rapporté'
    assert 'secret.author' not in json.dumps(report), 'le relevé ne garde aucun contenu'


def test_a_failed_call_is_still_recorded_because_it_was_sent():
    class Failing(ScriptedModel):
        def complete(self, system, user, schema=None):
            raise RuntimeError('panne')

    protected = ProtectedModel(Failing(), Disclosure([]))
    try:
        protected.complete('consignes', json.dumps({'question': 'message'}))
    except RuntimeError:
        pass
    assert protected.ledger.report()['per_call'][0]['failed'] is True


# --- La réponse finale porte le relevé ; le journal le dit sans contenu ----------------------------------------

def test_an_exploration_answer_carries_its_measurement(repo, tmp_path):
    repo, sha = repo
    model = ScriptedModel(call('get_commit', commit=sha[:10]),
                          answer(statement('claim', 'Le commit modifie src/app.txt.', f'commit:{sha}', 'CHANGES',
                                           'file:src/app.txt')))
    result = completed(run(repo, tmp_path, model))
    measured = result['usage']
    assert measured['calls'] == len(model.calls) == 2
    trajectory = result['trajectory']
    verifications = [step for step in trajectory if step['operation'] == 'find_claim']
    assert measured['taxo_bytes']['verification'] == sum(step['bytes'] for step in verifications)
    assert measured['taxo_bytes']['exploration'] == sum(step['bytes'] for step in trajectory) - \
        measured['taxo_bytes']['verification']
    assert measured['sent_bytes'] == sum(len(system.encode()) + len(user.encode()) for system, user, _ in model.calls)


def test_the_journal_says_the_counters_and_never_the_content():
    journal = io.StringIO()
    trace.configure(trace.SUMMARY, journal)
    try:
        model = SimpleNamespace(provider='claude', model_name='claude-test')
        trace.usage(model, {**usage.claude(CLAUDE_USAGE), 'system_bytes': 10, 'message_bytes': 20})
    finally:
        trace.configure(trace.OFF)
    line = journal.getvalue()
    assert 'entrée 1200' in line and 'raisonnement non rapporté' in line and 'envoyé 30 octets' in line
