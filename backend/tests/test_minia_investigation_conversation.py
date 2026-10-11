"""La conversation d'une enquete, ses lectures de reponses et sa declaration finale, sans serveur
(recit TAXO-MINIA-ENQUETE-01, lot C)."""
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.bootstrap import settings
from app.minia.application.investigation import InvestigationSettings, Investigations, guard_with
from app.minia.domain.confidentiality import Disclosure
from app.minia.domain.errors import INVALID_ANSWER, INVESTIGATION_EXPIRED, INVESTIGATION_STALE, MiniaError
from app.minia.domain.exploration import Call
from app.minia.domain.investigation import conversation, declaration, responses
from app.minia.domain.investigation.identity import Status
from app.minia.domain.investigation.logbook import Delivery, DeliveryKind, Edge, FrontierKind, ReceiptStatus

from investigation_scenarios import (ALICE, CONTROLLER, SAVE, SERVICE, SNAPSHOT, InMemoryStore, allow, at,
                                     explored_two_of_three, opened)

EMPTY = {'operation': '', 'arguments': '', 'note_id': '', 'text': '', 'nodes': [], 'branches': [], 'justification': '',
         'answer': '', 'used_mip_items': [], 'remaining_unknowns': []}


def raw(action, **fields):
    return json.dumps({**EMPTY, 'action': action, **fields})


# Tours du modele -------------------------------------------------------------------------------------------

def test_each_action_is_read():
    assert conversation.parse_step(raw('call', operation='get_tile', arguments='{"reference": "x"}')) == Call(
        'get_tile', {'reference': 'x'})
    assert conversation.parse_step(raw('note', note_id='n1', text=' t ', nodes=['a', '', 'b'])) == conversation.Note(
        'n1', 't', ('a', 'b'))
    assert conversation.parse_step(raw('close_note', note_id='n1')) == conversation.CloseNote('n1')
    renew = conversation.parse_step(raw('renew', branches=['a'], justification='pourquoi'))
    assert renew.request.branches == ('a',) and renew.request.justification == 'pourquoi'
    final = conversation.parse_step(raw('answer', answer='R', used_mip_items=[
        {'mip_reference': 'a', 'delivery_id': 'D-1', 'kind': 'TILE'}], remaining_unknowns=['x']))
    assert final.declaration == declaration.Declaration('R', ({'mip_reference': 'a', 'delivery_id': 'D-1',
                                                                'kind': 'TILE'},), ('x',), False)


@pytest.mark.parametrize('text', ['pas du JSON', '[]', json.dumps({'action': 'verify'}),
                                  raw('call', operation='')])
def test_an_unreadable_turn_is_refused(text):
    with pytest.raises(MiniaError) as error:
        conversation.parse_step(text)
    assert error.value.code == INVALID_ANSWER


def test_restoration_gives_back_original_values_but_keeps_note_text():
    disclosure = Disclosure(('Ada Lovelace <ada@example.invalid>',))
    disclosure.protect(json.dumps({'author': 'person:ada@example.invalid', 'name': 'Ada Lovelace'}))
    note = conversation.restored(conversation.Note('n1', 'personne-1 aurait écrit ceci', ('person:personne-1',)),
                                 disclosure)
    assert note.text == 'personne-1 aurait écrit ceci'
    assert note.nodes == ('person:ada@example.invalid',)
    renew = conversation.restored(conversation.parse_step(raw('renew', branches=['person:personne-1'],
                                                              justification='j')), disclosure)
    assert renew.request.branches == ('person:ada@example.invalid',)
    final = conversation.restored(conversation.parse_step(raw('answer', answer='Selon personne-1',
                                                              remaining_unknowns=['personne-1'])), disclosure)
    assert final.declaration.answer == 'Selon Ada Lovelace'


def test_the_compact_state_is_derived_and_bounded():
    state = explored_two_of_three()
    for index in range(conversation.MAX_LISTED + 5):
        state = state.record_tile(SNAPSHOT, SAVE, (Edge(SAVE, 'CALLS', f'method:x.N{index}#n()'),),
                                  at=at(10 + index))
    state = state.write_note('n1', 'x' * 900, [SERVICE], 'm', allow, at(60))
    compact = conversation.compact(state)

    assert compact['open_branches']['more'] == 7 and len(compact['open_branches']['items']) == conversation.MAX_LISTED
    assert len(compact['open_notes'][0]['text']) == conversation.MAX_NOTE_PREVIEW
    assert compact['budget'] == {'slice_calls_left': 8, 'total_calls_left': 24, 'renewals_left': 2}
    message = json.loads(conversation.message('Q', [], state, [], 3, ({'notice': 'X'},)))
    assert message['notices'] == [{'notice': 'X'}] and message['calls_left'] == 3


# Reponses de Taxo -------------------------------------------------------------------------------------------

TILE = {'outcome': 'OK', 'root': {'reference': CONTROLLER, 'known': True},
        'nodes': [{'reference': CONTROLLER, 'expanded': True}, {'reference': SERVICE, 'expanded': True},
                  {'reference': SAVE, 'expanded': False}],
        'facts': [{'fact': {'subject': CONTROLLER, 'relation': 'CALLS', 'object': SERVICE}, 'occurrence': 'o1'},
                  {'fact': {'subject': SERVICE, 'relation': 'CALLS', 'object': SAVE}, 'occurrence': 'o2'},
                  {'fact': {'subject': SERVICE, 'relation': 'CALLS'}}],
        'frontier': [{'nature': 'SELECTION', 'node': SAVE, 'reason': 'DEPTH', 'continuation': 'c'},
                     {'nature': 'KNOWLEDGE', 'scope': 'ANALYSIS', 'reason': 'ANALYSIS_INCOMPLETE'},
                     {'nature': 'OTHER', 'node': SAVE}]}


def test_a_mip_tile_gives_anchor_edges_frontier_and_expanded_nodes():
    anchor, edges, frontier, expanded = responses.tile_parts(TILE)

    assert anchor == CONTROLLER and expanded == (SERVICE,)
    assert [(edge.source, edge.target, edge.occurrence) for edge in edges] == [(CONTROLLER, SERVICE, 'o1'),
                                                                               (SERVICE, SAVE, 'o2')]
    assert [(entry.node, entry.kind, entry.continuation) for entry in frontier] == [
        (SAVE, FrontierKind.SELECTION, 'c')]


def test_a_protocol_neighborhood_is_read_the_same_way():
    neighborhood = {'outcome': 'OK', 'anchor': {'reference': CONTROLLER, 'known': True},
                    'nodes': [CONTROLLER, SERVICE], 'node_details': [{'reference': CONTROLLER, 'expanded': True}],
                    'items': [{'ref': 'F1', 'fact': {'subject': CONTROLLER, 'relation': 'CALLS', 'object': SERVICE},
                               'occurrence': 'o1'}], 'frontier': []}
    anchor, edges, _, expanded = responses.tile_parts(neighborhood)
    assert (anchor, len(edges), expanded) == (CONTROLLER, 1, ())
    assert responses.mip_reference('get_neighborhood', {'root': SERVICE}, neighborhood) == CONTROLLER


@pytest.mark.parametrize('response', [{'outcome': 'ERROR'}, {'outcome': 'OK', 'root': {'reference': 'x'}},
                                      {'outcome': 'OK'}, None])
def test_a_refused_or_unknown_tile_is_not_recorded(response):
    assert responses.tile_parts(response) is None


def test_source_receipts_never_keep_the_text():
    delivered = responses.source_receipt({'reference': SERVICE}, {
        'outcome': 'OK', 'classification': {'content': ['CODE_SOURCE']},
        'items': [{'text': 'public String enroll()', 'content_hash': 'sha256:1', 'truncated': True}]}, 'D-1')
    refused = responses.source_receipt({'reference': SERVICE}, {
        'outcome': 'OK', 'classification': {'content': []}, 'items': [], 'not_sent': [{'reason': 'CONFIDENTIAL'}]},
        'D-2')
    error = responses.source_receipt({'reference': SERVICE}, {'outcome': 'ERROR', 'error': {'code': 'NO_CONSENT'}},
                                     'D-3')

    assert (delivered.status, delivered.fingerprint, delivered.classification) == (
        ReceiptStatus.TRUNCATED, 'sha256:1', 'CODE_SOURCE')
    assert (refused.status, refused.reason) == (ReceiptStatus.REFUSED, 'CONFIDENTIAL')
    assert (error.status, error.reason) == (ReceiptStatus.REFUSED, 'NO_CONSENT')
    assert responses.source_receipt({}, {}, 'D-4') is None
    assert 'public' not in json.dumps(delivered.__dict__)


def test_delivery_kinds_references_and_fingerprints():
    assert [responses.delivery_kind(name) for name in ('get_tile', 'get_source', 'get_evidence', 'find_references')] \
        == [DeliveryKind.TILE, DeliveryKind.SOURCE, DeliveryKind.EVIDENCE, DeliveryKind.FACT]
    assert responses.mip_reference('get_evidence', {'fact': 'F1'}, {}) == 'F1'
    assert responses.mip_reference('describe', {}, {}) == 'operation:describe'
    assert responses.fingerprint({'a': 1, 'b': 2}) == responses.fingerprint({'b': 2, 'a': 1})
    assert responses.not_sent({'not_sent': [{'what': 'facts', 'reason': 'BUDGET', 'value': 'x'}, 'bad']}) == (
        {'what': 'facts', 'reason': 'BUDGET'},)
    assert responses.not_sent(None) == ()
    assert 'get_source' not in responses.REPLAYABLE and 'get_diff' not in responses.REPLAYABLE


# Declaration finale ------------------------------------------------------------------------------------------

def test_declared_items_are_traced_against_deliveries_only():
    state = opened().record_delivery(SNAPSHOT, Delivery('D-1', SERVICE, DeliveryKind.TILE, at(1)))
    declared = declaration.parse({'answer': 'R', 'used_mip_items': [
        {'mip_reference': SERVICE, 'delivery_id': 'D-1', 'kind': 'TILE'},
        {'mip_reference': SAVE, 'delivery_id': 'D-1', 'kind': 'TILE'},
        {'mip_reference': SERVICE, 'delivery_id': 'D-1', 'kind': 'SOURCE'},
        {'mip_reference': SERVICE, 'delivery_id': 'D-7', 'kind': 'TILE'},
        {'mip_reference': SERVICE, 'delivery_id': 'D-1', 'kind': 'GUESS'},
        {'mip_reference': '', 'delivery_id': 'D-1', 'kind': 'TILE'}, 'pas un objet'],
        'remaining_unknowns': ['  ', 'x']})

    traces = [item['trace'] for item in declaration.confronted(declared, state.logbook)]
    assert traces == ['DELIVERED', 'REFERENCE_MISMATCH', 'KIND_MISMATCH', 'UNKNOWN_DELIVERY', 'MALFORMED',
                      'MALFORMED', 'MALFORMED']
    assert declared.remaining_unknowns == ('x',) and not declared.malformed


def test_a_missing_declaration_is_marked_malformed():
    declared = declaration.parse({'answer': 'R', 'used_mip_items': None, 'remaining_unknowns': {}})
    assert declared.malformed and declared.items == () and declared.remaining_unknowns == ()


# Protection et reprise ---------------------------------------------------------------------------------------

def test_the_guard_masks_secrets_and_identities_before_keeping_a_text():
    """AC-15 : la protection existante s'applique avant conservation ; un secret reconnu n'est jamais garde."""
    guard = guard_with(Disclosure(('Ada Lovelace <ada@example.invalid>',)))
    kept = guard('Ada Lovelace écrit password = "hunter2" et ghp_' + 'a' * 30)

    assert 'hunter2' not in kept and 'Ada Lovelace' not in kept and 'ghp_' not in kept
    assert 'personne-1' in kept


def resume_with(store, state, generation, now):
    investigations = Investigations(store, InvestigationSettings(), clock=lambda: now)
    exchange = SimpleNamespace(snapshot={'analysis': state.investigation.snapshot.analysis_id,
                                         'commit': state.investigation.snapshot.commit_id})
    return investigations, investigations.resume(store.load(state.investigation_id, ALICE), exchange, generation)


def test_a_changed_generation_makes_the_stored_investigation_stale():
    """AC-08 : la generation a change : l'enquete devient historique et ne se poursuit pas."""
    store = InMemoryStore()
    state = store.create(explored_two_of_three().confirm_question('Q', True, allow, at(5)))

    with pytest.raises(MiniaError) as error:
        resume_with(store, state, SNAPSHOT.generation_id + 1, at(10))
    assert error.value.code == INVESTIGATION_STALE
    assert store.load(state.investigation_id, ALICE).investigation.status is Status.STALE


def test_a_vanished_analysis_makes_it_stale_too():
    store = InMemoryStore()
    state = store.create(opened().confirm_question('Q', True, allow, at(1)))
    investigations = Investigations(store, clock=lambda: at(2))
    with pytest.raises(MiniaError) as error:
        investigations.resume(state, None, None)
    assert error.value.code == INVESTIGATION_STALE


def test_a_paused_investigation_resumes_active_with_its_confirmed_question():
    store = InMemoryStore()
    state = store.create(opened().confirm_question('Q', True, allow, at(1)).move_to(Status.PAUSED, at(2)))
    _, (resumed, question) = resume_with(store, state, SNAPSHOT.generation_id, at(3))
    assert resumed.investigation.status is Status.ACTIVE and question == 'Q'


def test_an_expired_investigation_is_refused_at_resume():
    store = InMemoryStore()
    state = store.create(opened().confirm_question('Q', True, allow, at(1)))
    with pytest.raises(MiniaError) as error:
        resume_with(store, state, SNAPSHOT.generation_id, at(1) + timedelta(days=8))
    assert error.value.code == INVESTIGATION_EXPIRED


def test_the_store_is_opened_only_when_needed():
    opened_stores = []
    investigations = Investigations(store_factory=lambda: opened_stores.append(InMemoryStore()) or opened_stores[-1])
    assert opened_stores == []
    assert investigations.store is investigations.store and len(opened_stores) == 1
    with pytest.raises(ValueError):
        Investigations()


def test_settings_of_the_investigation_log(monkeypatch, tmp_path):
    monkeypatch.delenv('MINIA_INVESTIGATIONS_DB', raising=False)
    monkeypatch.delenv('MINIA_INVESTIGATION_DAYS', raising=False)
    assert settings.minia_investigations()['days'] == 7
    assert settings.minia_investigations()['path'].name == 'investigations.sqlite3'
    monkeypatch.setenv('MINIA_INVESTIGATIONS_DB', str(tmp_path / 'carnet.sqlite3'))
    monkeypatch.setenv('MINIA_INVESTIGATION_DAYS', '3')
    assert settings.minia_investigations() == {'path': tmp_path / 'carnet.sqlite3', 'days': 3}
    with pytest.raises(ValueError):
        settings.minia_investigations(days=0)
