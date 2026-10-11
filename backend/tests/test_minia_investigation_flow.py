"""L'enquete navigable de bout en bout, sur le depot de reference du recit TAXO-MINIA-ENQUETE-01 (§ 5) : un modele
scenarise conduit l'enquete, Taxo cartographie, Minia tient le carnet. Lot C : orchestration, etat compact,
declaration finale, memoire vive, renouvellement et reprise."""
import json
import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.main import create_app
from app.minia.domain.investigation.budget import BudgetLimits
from app.minia.domain.investigation.conversation import STEP_SCHEMA, SYSTEM
from app.minia.domain.errors import INVESTIGATION_EXPIRED, UNAVAILABLE, MiniaError
from app.minia.domain.investigation.identity import Status

import school_sources as school
from test_minia_general import Scripted

QUESTION = 'Comment fonctionne l’inscription à un cours ?'
CONFIRMED = 'Comment fonctionne l’inscription ?'
EMPTY = {'operation': '', 'arguments': '', 'note_id': '', 'text': '', 'nodes': [], 'branches': [], 'justification': '',
         'answer': '', 'used_mip_items': [], 'remaining_unknowns': []}


def step(action, **fields):
    return json.dumps({**EMPTY, 'action': action, **fields})


def call(operation, **arguments):
    return step('call', operation=operation, arguments=json.dumps(arguments))


def neighborhood(root):
    return lambda sent: call('get_neighborhood', analysis=sent['state']['snapshot']['analysis'], root=root,
                             steps=[{'relation': 'CALLS', 'direction': 'OUTGOING'}], depth=1)


def find(name):
    return lambda sent: call('find_references', analysis=sent['state']['snapshot']['analysis'], prefix=name,
                             match='NAME')


def delivery_of(sent, operation, reference=None):
    return next(item['delivery_id'] for item in sent['slice'] if item['operation'] == operation
                and (reference is None or item['response'].get('reference', item['response'].get('anchor', {})
                                                               .get('reference')) == reference))


def final(answer='Le contrôleur délègue au service, qui cherche l’étudiant et le cours.', items=(), unknowns=()):
    return step('answer', answer=answer, used_mip_items=list(items), remaining_unknowns=list(unknowns))


class Session:
    def __init__(self, make_repo, tmp_path, model, source_reading=None, limits=None):
        self.root = make_repo(school.files())
        self.app = create_app(f'sqlite:///{tmp_path / "school.db"}', [self.root], minia=model,
                              source_reading=source_reading, investigations_path=tmp_path / 'investigations.sqlite3')
        Base.metadata.create_all(self.app.state.engine)
        investigations = self.app.state.minia.investigations
        if limits is not None:
            investigations.settings = replace(investigations.settings, limits=limits)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.project = self.client.post('/api/projects', json={'name': 'École', 'path': str(self.root)}).json()['id']
        self.client.post(f'/api/projects/{self.project}/scans')

    def investigate(self, **body):
        stream = self.client.post(f'/api/projects/{self.project}/investigations/stream', json=body)
        return [(block.split('\n')[0][len('event: '):], json.loads(block.split('\n')[1][len('data: '):]))
                for block in stream.text.strip().split('\n\n') if not block.startswith(':')]

    def close(self):
        self.client.__exit__(None, None, None)


@pytest.fixture
def session(make_repo, tmp_path):
    opened = []

    def start(model, **options):
        opened.append(Session(make_repo, tmp_path, model, **options))
        return opened[-1]
    yield start
    for item in opened:
        item.close()


def completed(events):
    return next(data for kind, data in events if kind == 'minia.completed')


def sent(model, turn):
    return json.loads(model.calls[turn][1])


def reference_scenario():
    """Le parcours du § 5 : point d'entree, service, deux des trois branches, une note, puis la reponse."""
    def answer(message):
        tile = delivery_of(message, 'get_neighborhood', school.FIND_COURSE)
        return final(items=[{'mip_reference': school.FIND_COURSE, 'delivery_id': tile, 'kind': 'TILE'},
                            {'mip_reference': school.SAVE, 'delivery_id': 'D-99', 'kind': 'SOURCE'}],
                     unknowns=['EnrollmentRepository.save non exploré'])
    return Scripted(
        find('EnrollmentController.enroll'),
        neighborhood(school.CONTROLLER),
        neighborhood(school.SERVICE),
        step('note', note_id='n1', text='Le service chercherait l’étudiant puis le cours avant d’enregistrer.',
             nodes=[school.SERVICE, school.FIND_STUDENT]),
        neighborhood(school.FIND_STUDENT),
        neighborhood(school.FIND_COURSE),
        answer)


def test_three_branches_two_explored_the_third_stays_in_the_frontier(session):
    """AC-01 et scenario du § 5 : les trois appels du service sont des branches distinctes ; deux sont explorees,
    l'enregistrement reste decouvert, non explore. Les repositories restent en frontiere."""
    model = reference_scenario()
    result = completed(session(model).investigate(question=QUESTION, resume_question=CONFIRMED))

    assert (result['mode'], result['status']) == ('investigation', 'ANSWERED')
    assert result['outside']['open_branches'] == [school.SAVE, school.STUDENT_BY_ID, school.COURSE_BY_ID]
    assert result['investigation']['status'] == 'COMPLETE' and result['investigation']['resumable']
    assert [entry['operation'] for entry in result['trajectory']] == [
        'find_references', 'get_neighborhood', 'get_neighborhood', 'get_neighborhood', 'get_neighborhood']
    third = sent(model, 3)['state']
    assert third['open_branches'] == [school.SAVE, school.FIND_COURSE, school.FIND_STUDENT], 'ordre d’arrivée'
    assert third['expanded'] == [school.CONTROLLER, school.SERVICE]


def test_no_verdict_is_given_on_the_model_conclusion(session):
    """INV-01 : `verify_claim` n'est pas propose ; la restitution a trois zones et aucun verdict."""
    model = reference_scenario()
    result = completed(session(model).investigate(question=QUESTION))

    offered = [item['operation'] for item in sent(model, 0)['operations']]
    assert 'verify_claim' not in offered and 'get_neighborhood' in offered and 'get_tile' in offered
    assert set(result) >= {'transmitted', 'exploration', 'outside'}
    text = json.dumps(result)
    assert 'CONFIRMED' not in text and 'REFUTED' not in text and 'verdict' not in text
    assert model.calls[0][0] == SYSTEM and model.calls[0][2] == STEP_SCHEMA


def test_the_final_declaration_is_confronted_by_identifiers(session):
    """AC-12 : une livraison reellement faite est attestee ; une reference jamais livree est une discordance."""
    result = completed(session(reference_scenario()).investigate(question=QUESTION))

    declared = result['exploration']['declared']
    assert [(item['mip_reference'], item['trace']) for item in declared] == [
        (school.FIND_COURSE, 'DELIVERED'), (school.SAVE, 'UNKNOWN_DELIVERY')]
    assert result['outside']['remaining_unknowns'] == ['EnrollmentRepository.save non exploré']
    assert {item['delivery_id'] for item in result['transmitted']} == {'D-1', 'D-2', 'D-3', 'D-4', 'D-5'}


def test_a_malformed_declaration_is_signalled_without_attestation(session):
    model = Scripted(step('answer', **{**EMPTY, 'answer': 'Réponse.', 'used_mip_items': 'oui'}))
    result = completed(session(model).investigate(question=QUESTION))

    assert result['exploration']['declaration_malformed'] is True
    assert result['exploration']['declared'] == []


def test_the_note_is_a_hypothesis_kept_apart_from_facts(session):
    """AC-09 : la note du modele est une HYPOTHESIS_LLM, liee a des noeuds du carnet, jamais un fait."""
    result = completed(session(reference_scenario()).investigate(question=QUESTION))

    [note] = result['exploration']['notes']
    assert (note['kind'], note['status'], note['nodes']) == ('HYPOTHESIS_LLM', 'OPEN',
                                                             [school.SERVICE, school.FIND_STUDENT])


def test_a_note_on_an_unknown_node_is_refused_and_said_to_the_model(session):
    model = Scripted(step('note', note_id='n1', text='Hypothèse', nodes=['symbol:java:x.Invented#run()']),
                     final())
    result = completed(session(model).investigate(question=QUESTION))

    assert result['exploration']['notes'] == []
    assert sent(model, 1)['notices'][0]['notice'] == 'NOTE_REFUSED'


def test_deliveries_are_recorded_only_once_sent(session):
    """INV-07 et AC-13 : la reponse obtenue au dernier tour n'est livree qu'une fois le message parti."""
    model = Scripted(find('EnrollmentController.enroll'), final())
    started = session(model)
    result = completed(started.investigate(question=QUESTION))

    assert [item['delivery_id'] for item in result['transmitted']] == ['D-1']
    assert (sent(model, 1)['slice'][0]['delivery_id'], sent(model, 1)['slice'][0]['kind']) == ('D-1', 'FACT')
    view = started.client.get(f'/api/projects/{started.project}/investigations/{result["investigation"]["id"]}').json()
    assert view['deliveries'] == [{'delivery_id': 'D-1', 'mip_reference': 'EnrollmentController.enroll',
                                   'kind': 'FACT', 'replay_of': None}]


def test_the_same_tile_in_the_same_session_is_replayed_from_memory(session):
    """AC-18 : la meme Tuile redemandee dans la meme demande est rejouee sans nouvel appel a Taxo, avec une
    livraison distincte liee a l'origine ; la repetition est signalee avec les branches ouvertes."""
    model = Scripted(neighborhood(school.SERVICE), neighborhood(school.SERVICE), final())
    result = completed(session(model).investigate(question=QUESTION))

    first, again = result['trajectory']
    assert first['outcome'] == 'OK' and again == {**again, 'outcome': 'REPLAYED', 'replay_of': first['delivery_id']}
    notice = sent(model, 2)['notices'][0]
    assert notice['notice'] == 'REPEATED' and school.SAVE in notice['open_branches']
    assert result['budget']['operations'] == 1, 'un rejeu n’est pas une opération de Taxo'


def test_source_is_read_only_under_this_request_consent_and_never_replayed(session):
    """AC-04, AC-19 : avec le reglage et l'accord, le code est lu et seul un recu est garde ; redemande, il repasse
    par Taxo ; sans accord, l'operation n'est pas proposee."""
    model = Scripted(neighborhood(school.CONTROLLER), call('get_source', reference=school.CONTROLLER),
                     call('get_source', reference=school.CONTROLLER), final())
    started = session(model, source_reading='symbol')
    result = completed(started.investigate(question=QUESTION, source=True))

    assert [entry['outcome'] for entry in result['trajectory']] == ['OK', 'OK', 'OK']
    assert result['source_reading'] == {'status': 'ON_DEMAND'}
    store = started.app.state.minia.investigations.store
    state = store.load(result['investigation']['id'], started.app.state.minia.investigations.scope(started.project))
    assert [receipt.reference for receipt in state.logbook.receipts] == [school.CONTROLLER, school.CONTROLLER]
    assert 'return service.enroll' not in json.dumps(started.client.get(
        f'/api/projects/{started.project}/investigations/{result["investigation"]["id"]}').json())

    refused = Scripted(call('get_source', reference=school.CONTROLLER), final())
    started = session(refused, source_reading='symbol')
    result = completed(started.investigate(question=QUESTION))
    assert result['trajectory'] == []
    assert sent(refused, 1)['notices'][0] == {'notice': 'REFUSED', 'reason': 'NOT_OFFERED', 'operation': 'get_source'}


def test_a_note_never_copies_the_code_it_was_shown(session):
    """INV-10 et § 11 : une note qui reprend une ligne du code lu est refusee ; citer le symbole suffit."""
    def copying(message):
        piece = next(item for item in message['slice'] if item['operation'] == 'get_source')['response']['items'][0]
        line = next(line for line in piece['text'].splitlines() if len(line.strip()) >= 20)
        return step('note', note_id='n1', text=f'Le contrôleur fait : {line}', nodes=[school.CONTROLLER])
    model = Scripted(neighborhood(school.CONTROLLER), call('get_source', reference=school.CONTROLLER), copying,
                     step('note', note_id='n2', text='Le contrôleur délègue au service.', nodes=[school.CONTROLLER]),
                     final())
    started = session(model, source_reading='symbol')
    result = completed(started.investigate(question=QUESTION, source=True))

    assert sent(model, 3)['notices'][-1]['notice'] == 'NOTE_REFUSED'
    assert [note['note_id'] for note in result['exploration']['notes']] == ['n2']


def test_justified_renewal_opens_a_new_slice_under_the_total_cap(session):
    """AC-10 : tranche epuisee, renouvellement justifie sur des branches ouvertes, puis nouvelle tranche ; les
    reponses de la tranche precedente ne sont pas rejouees."""
    limits = BudgetLimits(slice_operations=2, slice_bytes=64_000, total_operations=3, total_bytes=160_000,
                          max_renewals=1)
    model = Scripted(neighborhood(school.CONTROLLER), neighborhood(school.SERVICE),
                     step('renew', branches=[school.SAVE], justification='Lire l’enregistrement.'),
                     neighborhood(school.SAVE),
                     step('renew', branches=[school.FIND_STUDENT], justification='Encore.'),
                     final())
    result = completed(session(model, limits=limits).investigate(question=QUESTION))

    assert sent(model, 2)['calls_left'] == 0
    assert sent(model, 3)['slice'] == [] and sent(model, 3)['calls_left'] == 1
    refusal = sent(model, 5)['notices'][0]
    assert (refusal['notice'], refusal['reason']) == ('RENEWAL_REFUSED', 'TOTAL_EXHAUSTED')
    assert school.FIND_STUDENT in refusal['open_branches']
    assert result['budget'] == {'operations': 3, 'max_operations': 3, 'renewals': 1,
                                'bytes': result['budget']['bytes']}


def test_a_call_beyond_the_slice_is_refused_and_said(session):
    limits = BudgetLimits(slice_operations=1, slice_bytes=64_000, total_operations=1, total_bytes=160_000,
                          max_renewals=0)
    model = Scripted(neighborhood(school.CONTROLLER), neighborhood(school.SERVICE), final())
    result = completed(session(model, limits=limits).investigate(question=QUESTION))

    assert len(result['trajectory']) == 1
    assert sent(model, 2)['notices'][0]['reason'] == 'NO_CALL_LEFT'


def test_responses_never_exceed_the_bytes_left_to_the_investigation(session):
    """Chaque reponse demandee tient dans les octets qui restent ; sans la place d'un refus, plus d'appel."""
    limits = BudgetLimits(slice_operations=6, slice_bytes=6_000, total_operations=6, total_bytes=30_000,
                          max_renewals=0)
    model = Scripted(*(neighborhood(node) for node in (school.CONTROLLER, school.SERVICE, school.FIND_STUDENT,
                                                       school.FIND_COURSE, school.SAVE)), final())
    result = completed(session(model, limits=limits).investigate(question=QUESTION))

    assert 0 < result['budget']['bytes'] <= 6_000
    assert any(sent(model, turn)['calls_left'] == 0 for turn in range(len(model.calls)))


def test_interrupt_then_resume_restores_the_confirmed_question_and_frontier(session):
    """AC-05 : la demande s'arrete sans reponse ; l'enquete reprend avec la question confirmee, la meme frontiere,
    les memes notes et le meme budget, sans aucun code restitue. Le modele redemande ce qu'il lui faut."""
    first = Scripted(neighborhood(school.CONTROLLER), neighborhood(school.SERVICE), 'pas du JSON')
    started = session(first)
    events = started.investigate(question=QUESTION, resume_question=CONFIRMED)
    failed = next(data for kind, data in events if kind == 'minia.failed')
    assert failed['code'] == 'MINIA_INVALID_ANSWER'
    opened = next(data for kind, data in events if kind == 'minia.investigation')
    assert opened['resumable'] is True
    investigation_id = opened['id']

    paused = started.client.get(f'/api/projects/{started.project}/investigations/{investigation_id}').json()
    assert (paused['status'], paused['question']) == ('PAUSED', CONFIRMED)

    resumed_model = Scripted(neighborhood(school.SAVE), final())
    started.app.state.minia.models = {'scripted': resumed_model}
    result = completed(started.investigate(investigation_id=investigation_id))

    assert result['question'] == CONFIRMED
    state = sent(resumed_model, 0)['state']
    assert state['open_branches'] == paused['state']['open_branches'] == [
        school.SAVE, school.FIND_COURSE, school.FIND_STUDENT]
    assert state['budget']['total_calls_left'] == paused['state']['budget']['total_calls_left']
    assert sent(resumed_model, 0)['slice'] == []
    assert result['investigation']['status'] == 'COMPLETE'


def test_an_unconfirmed_investigation_cannot_be_resumed(session):
    """AC-20 : sans question confirmee, rien de la question n'est garde et la reprise est refusee."""
    started = session(Scripted(final()))
    result = completed(started.investigate(question=QUESTION))
    assert result['investigation']['resumable'] is False and result['investigation']['not_resumable']

    started.app.state.minia.models = {'scripted': Scripted(final())}
    response = started.client.post(f'/api/projects/{started.project}/investigations/stream',
                                   json={'investigation_id': result['investigation']['id']})
    assert response.status_code == 409


def test_a_completed_or_foreign_investigation_is_not_resumed(session):
    started = session(Scripted(final()))
    result = completed(started.investigate(question=QUESTION, resume_question=CONFIRMED))

    again = started.client.post(f'/api/projects/{started.project}/investigations/stream',
                                json={'investigation_id': result['investigation']['id']})
    missing = started.client.post(f'/api/projects/{started.project}/investigations/stream',
                                  json={'investigation_id': 'inconnue'})
    both = started.client.post(f'/api/projects/{started.project}/investigations/stream',
                               json={'investigation_id': result['investigation']['id'], 'question': 'Autre ?'})
    assert (again.status_code, missing.status_code, both.status_code) == (409, 404, 422)


def test_the_compact_state_stays_bounded(session):
    """AC-14 : l'etat compact ne rejoue ni l'historique ni le code ; ses listes sont bornees."""
    model = reference_scenario()
    completed(session(model).investigate(question=QUESTION))

    last = sent(model, len(model.calls) - 1)
    assert set(last['state']) == {'snapshot', 'expanded', 'open_branches', 'knowledge_or_context_gaps',
                                  'sources_read', 'open_notes', 'budget', 'details_available_on_request'}
    assert len(model.calls[-1][1]) < 40_000


def test_a_model_that_does_not_explore_is_refused(session):
    started = session(Scripted(final(), explores=False))
    response = started.client.post(f'/api/projects/{started.project}/investigations/stream',
                                   json={'question': QUESTION})
    assert response.status_code == 503


def test_the_store_records_every_turn(session):
    """AC-06 : le carnet est enregistre a chaque tour ; ce qui a ete obtenu et transmis y est."""
    started = session(reference_scenario())
    result = completed(started.investigate(question=QUESTION, resume_question=CONFIRMED))
    investigations = started.app.state.minia.investigations
    state = investigations.store.load(result['investigation']['id'], investigations.scope(started.project))

    assert state.investigation.status is Status.COMPLETE
    assert len(state.logbook.operations) == 5 and len(state.logbook.deliveries) == 5
    assert state.revision >= 7


def test_notes_are_revised_and_closed_and_evidence_is_traced(session):
    def evidence(message):
        tile = message['slice'][0]['response']
        return call('get_evidence', fact=tile['items'][0]['ref'])
    model = Scripted(neighborhood(school.CONTROLLER),
                     step('note', note_id='n1', text='Le contrôleur délègue.', nodes=[school.CONTROLLER]),
                     step('note', note_id='n1', text='Le contrôleur délègue au service.',
                          nodes=[school.CONTROLLER, school.SERVICE]),
                     step('close_note', note_id='n1'), step('close_note', note_id='n9'),
                     evidence, final())
    events = session(model).investigate(question=QUESTION)
    result = completed(events)

    notes = [data for kind, data in events if kind == 'minia.note']
    assert [(item.get('version'), item['status']) for item in notes] == [(1, 'OPEN'), (2, 'REVISED'), (None, 'CLOSED')]
    assert result['exploration']['notes'][0]['status'] == 'CLOSED'
    assert sent(model, 5)['notices'][0]['notice'] == 'NOTE_REFUSED'
    assert result['trajectory'][-1]['operation'] == 'get_evidence' and result['trajectory'][-1]['outcome'] == 'OK'
    assert result['transmitted'][-1]['kind'] == 'EVIDENCE'


def test_an_interrupted_request_keeps_what_was_obtained_but_never_sent(session):
    """AC-06 et AC-13 : le modele tombe apres une reponse de Taxo ; l'operation est inscrite sans livraison, et
    l'enquete passe en pause."""
    def unavailable(_message):
        raise MiniaError(UNAVAILABLE, 'Modèle injoignable.')
    started = session(Scripted(neighborhood(school.CONTROLLER), unavailable))
    events = started.investigate(question=QUESTION, resume_question=CONFIRMED)
    assert next(data for kind, data in events if kind == 'minia.failed')['code'] == UNAVAILABLE
    investigation_id = next(data for kind, data in events if kind == 'minia.investigation')['id']

    investigations = started.app.state.minia.investigations
    state = investigations.store.load(investigation_id, investigations.scope(started.project))
    assert state.investigation.status is Status.PAUSED
    [operation] = state.logbook.operations
    assert operation.outcome.value == 'OK' and operation.delivery_ids == ()
    assert {'what': 'response', 'reason': 'TRANSMISSION_UNCERTAIN'} in operation.not_sent, \
        'coupee pendant l’appel au modele, la reponse a pu partir : le carnet le dit'
    assert state.logbook.deliveries == ()
    assert state.logbook.expanded(school.CONTROLLER), 'ce que Taxo a rendu reste au carnet'


def test_a_process_stopped_during_the_model_call_leaves_a_trace_of_what_may_have_left(session, tmp_path):
    """AC-06 et INV-07 : l'envoi au modele et l'ecriture du carnet ne tiennent pas dans une transaction. Le carnet
    tel qu'un arret du processus le laisse pendant l'appel annonce l'operation en partance ; la reprise l'inscrit
    peut-etre transmise, jamais absente."""
    path = tmp_path / 'investigations.sqlite3'
    left = sqlite3.connect(':memory:')

    def stopped(_message):
        with sqlite3.connect(path) as store:
            store.backup(left)
        raise MiniaError(UNAVAILABLE, 'Processus arrêté.')
    started = session(Scripted(neighborhood(school.CONTROLLER), stopped, final()))
    events = started.investigate(question=QUESTION, resume_question=CONFIRMED)
    investigation_id = next(data for kind, data in events if kind == 'minia.investigation')['id']
    with sqlite3.connect(path) as store:
        left.backup(store)

    url = f'/api/projects/{started.project}/investigations/{investigation_id}'
    shown = started.client.get(url).json()
    assert shown['in_flight'] == [{'operation': 'get_neighborhood', 'delivery_ids': ['D-1']}]
    assert shown['deliveries'] == []

    completed(started.investigate(investigation_id=investigation_id))
    investigations = started.app.state.minia.investigations
    state = investigations.store.load(investigation_id, investigations.scope(started.project))
    assert state.in_flight == ()
    operation = state.logbook.operations[0]
    assert operation.name == 'get_neighborhood' and operation.delivery_ids == ()
    assert {'what': 'response', 'reason': 'TRANSMISSION_UNCERTAIN'} in operation.not_sent
    assert started.client.get(url).json()['in_flight'] == []


def test_an_expired_investigation_is_no_longer_shown(session):
    """Passe son expiration, une enquete n'est plus restituee, meme avant le menage du stockage."""
    started = session(Scripted(final()))
    result = completed(started.investigate(question=QUESTION, resume_question=CONFIRMED))
    url = f'/api/projects/{started.project}/investigations/{result["investigation"]["id"]}'
    assert started.client.get(url).status_code == 200

    investigations = started.app.state.minia.investigations
    now = investigations.clock()
    investigations.clock = lambda: now + timedelta(days=8)
    response = started.client.get(url)
    assert response.status_code == 409 and response.json()['detail'].startswith(INVESTIGATION_EXPIRED)


def test_an_empty_answer_does_not_close_the_investigation(session):
    model = Scripted(final(answer=''), final())
    result = completed(session(model).investigate(question=QUESTION))

    assert sent(model, 1)['notices'][-1]['notice'] == 'EMPTY_ANSWER'
    assert result['exploration']['answer'].startswith('Le contrôleur')


def test_delivery_ids_are_never_reused_after_an_interrupted_source_read(session):
    """Un recu de code garde son identifiant de transmission ; la reprise n'attribue jamais ce meme identifiant
    a une autre reponse."""
    def unavailable(_message):
        raise MiniaError(UNAVAILABLE, 'Modèle injoignable.')
    started = session(Scripted(call('get_source', reference=school.CONTROLLER), unavailable),
                      source_reading='symbol')
    events = started.investigate(question=QUESTION, resume_question=CONFIRMED, source=True)
    investigation_id = next(data for kind, data in events if kind == 'minia.investigation')['id']

    resumed = Scripted(neighborhood(school.CONTROLLER), final())
    started.app.state.minia.models = {'scripted': resumed}
    completed(started.investigate(investigation_id=investigation_id))
    investigations = started.app.state.minia.investigations
    state = investigations.store.load(investigation_id, investigations.scope(started.project))
    [receipt] = state.logbook.receipts
    assert receipt.transmission_id == 'D-1'
    assert [delivery.delivery_id for delivery in state.logbook.deliveries] == ['D-2']
