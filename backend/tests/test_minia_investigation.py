"""Le domaine de la memoire de parcours (recit TAXO-MINIA-ENQUETE-01, lot A) : carnet, frontieres, notes,
budget, reprise et serialisation, sans stockage ni modele."""
from datetime import timedelta

import pytest

from app.minia.domain.errors import (BUDGET_EXHAUSTED, CONFIDENTIALITY_REFUSED, INVESTIGATION_EXPIRED,
                                     INVESTIGATION_INVALID, INVESTIGATION_NOT_FOUND, INVESTIGATION_NOT_RESUMABLE,
                                     INVESTIGATION_STALE, NOTE_REFUSED, MiniaError)
from app.minia.domain.investigation.budget import BudgetLimits, Refusal, RenewalRequest
from app.minia.domain.investigation.codec import (SCHEMA_VERSION, event_from_document, event_to_document,
                                                  from_document, to_document)
from app.minia.domain.investigation.identity import ExpiryPolicy, OwnerScope, Snapshot, Status, ensure_resumable
from app.minia.domain.investigation.logbook import (Action, Delivery, DeliveryKind, Edge, FrontierEntry,
                                                    FrontierKind, OperationOutcome, OperationRecord, ReceiptStatus,
                                                    SourceReceipt, request_key)
from app.minia.domain.investigation.notes import KIND, MAX_NOTE_CHARS, MAX_NOTE_NODES, NoteStatus, open_notes
from app.minia.domain.investigation.state import EventKind, InvestigationState

from investigation_scenarios import (ALICE, BOB, CONTROLLER, COURSE_BY_ID, FIND_COURSE, FIND_STUDENT, LIMITS,
                                     OTHER_GENERATION, SAVE, SERVICE, SNAPSHOT, STUDENT_BY_ID, T0, allow, at, calls,
                                     explored_two_of_three, opened, without_pending)


def refuse(_text):
    raise MiniaError(CONFIDENTIALITY_REFUSED, 'Une donnée confidentielle subsiste.')


def operation(name='get_tile', minutes=5, fingerprint='h1', deliveries=(), outcome=OperationOutcome.OK, **arguments):
    return OperationRecord(name, arguments or {'reference': SERVICE, 'profile': 'calls/1'}, outcome, at(minutes),
                           fingerprint, tuple(deliveries))


# Carnet : branches, profondeur, cycles -------------------------------------------------------------------------

def test_three_calls_two_explored_keep_the_third_in_the_frontier():
    """AC-01 : les trois branches du service restent identifiees ; la troisieme est decouverte, non explorée."""
    logbook = explored_two_of_three().logbook

    assert {edge.target for edge in logbook.edges if edge.source == SERVICE} == {FIND_STUDENT, FIND_COURSE, SAVE}
    assert logbook.expanded(FIND_STUDENT) and logbook.expanded(FIND_COURSE)
    assert not logbook.expanded(SAVE)
    assert logbook.open_branches() == (SAVE, STUDENT_BY_ID, COURSE_BY_ID)
    assert all(entry.kind is FrontierKind.DISCOVERED for entry in logbook.frontier)


def test_branch_order_is_arrival_order_never_a_ranking():
    """INV-02 : Minia n'impose aucun ordre de visite ; la frontiere suit l'ordre d'arrivee."""
    state = opened().record_tile(SNAPSHOT, SERVICE, calls(SERVICE, SAVE, FIND_COURSE, FIND_STUDENT), at=at(1))

    assert state.logbook.open_branches() == (SAVE, FIND_COURSE, FIND_STUDENT)


def test_a_tile_cut_by_depth_continues_from_its_frontier_node():
    """AC-02 : une Tuile arretee a quatre niveaux laisse une frontiere de selection ; une nouvelle Tuile depuis ce
    noeud poursuit le chemin, sans limite globale de profondeur."""
    chain = [f'method:com.example.deep.N{level}#run()' for level in range(9)]
    first = tuple(edge for source, target in zip(chain[:4], chain[1:5]) for edge in calls(source, target))
    cut = FrontierEntry(chain[4], FrontierKind.SELECTION, 'DEPTH', 'cursor-g7-n4')
    state = opened().record_tile(SNAPSHOT, chain[0], first, (cut,), at=at(1))
    assert chain[4] in state.logbook.open_branches()

    second = tuple(edge for source, target in zip(chain[4:8], chain[5:9]) for edge in calls(source, target))
    state = state.record_tile(SNAPSHOT, chain[4], second, at=at(2))

    assert state.logbook.expanded(chain[4])
    assert not any(entry.node == chain[4] for entry in state.logbook.frontier)
    assert len(state.logbook.edges) == 8
    assert state.logbook.open_branches()[-1] == chain[8]


def test_a_multilevel_tile_marks_every_node_it_expanded():
    """Une Tuile de plusieurs niveaux developpe ses noeuds internes : ils quittent la frontiere, ses feuilles y
    restent."""
    edges = calls(CONTROLLER, SERVICE) + calls(SERVICE, FIND_STUDENT, SAVE)
    state = opened().record_tile(SNAPSHOT, CONTROLLER, edges, at=at(1), expanded=(SERVICE,))

    assert state.logbook.expanded(SERVICE)
    assert state.logbook.open_branches() == (FIND_STUDENT, SAVE)


def test_convergence_and_cycle_keep_every_edge_without_reexpanding():
    """AC-03 : deux aretes vers un meme noeud et l'arete qui ferme un cycle sont conservees ; un noeud developpe
    ne revient jamais en frontiere."""
    a, b, c = 'method:x.A#a()', 'method:x.B#b()', 'method:x.C#c()'
    state = opened().record_tile(SNAPSHOT, a, calls(a, b, c), at=at(1))
    state = state.record_tile(SNAPSHOT, b, calls(b, a) + calls(b, c), at=at(2))
    state = state.record_tile(SNAPSHOT, c, (), at=at(3))

    assert {(edge.source, edge.target) for edge in state.logbook.edges} == {(a, b), (a, c), (b, a), (b, c)}
    assert state.logbook.open_branches() == ()
    revisited = state.record_tile(SNAPSHOT, a, calls(a, b, c), at=at(4))
    assert len(revisited.logbook.edges) == 4
    assert revisited.logbook.open_branches() == ()


def test_edges_without_occurrence_keep_distinct_relations():
    state = opened().record_tile(SNAPSHOT, CONTROLLER, (Edge(CONTROLLER, 'CALLS', SERVICE),
                                                        Edge(CONTROLLER, 'HANDLED_BY', SERVICE)), at=at(1))

    assert len(state.logbook.edges) == 2


def test_knowledge_and_context_frontiers_stay_distinct_and_survive_expansion():
    """Les frontieres de selection, de connaissance et de contexte ne sont jamais confondues ; une nouvelle Tuile
    ne leve que la selection."""
    frontier = (FrontierEntry(SERVICE, FrontierKind.KNOWLEDGE, 'NOT_INTERPRETED'),
                FrontierEntry(SERVICE, FrontierKind.CONTEXT, 'NO_CAPABILITY'),
                FrontierEntry(SERVICE, FrontierKind.SELECTION, 'FANOUT', 'cursor'))
    state = opened().record_tile(SNAPSHOT, CONTROLLER, calls(CONTROLLER, SERVICE), frontier, at=at(1))
    assert {entry.kind for entry in state.logbook.frontier if entry.node == SERVICE} == set(FrontierKind)

    state = state.record_tile(SNAPSHOT, SERVICE, (), at=at(2))

    assert {entry.kind for entry in state.logbook.frontier if entry.node == SERVICE} == {
        FrontierKind.KNOWLEDGE, FrontierKind.CONTEXT}
    assert SERVICE not in state.logbook.open_branches()


def test_tile_without_anchor_is_refused():
    with pytest.raises(MiniaError) as error:
        opened().record_tile(SNAPSHOT, '', (), at=at(1))
    assert error.value.code == INVESTIGATION_INVALID


# Code lu, livraisons, operations ------------------------------------------------------------------------------

def test_tile_explored_and_source_read_are_independent():
    state = opened().record_tile(SNAPSHOT, CONTROLLER, calls(CONTROLLER, SERVICE), at=at(1))
    state = state.record_receipt(SNAPSHOT, SourceReceipt(SERVICE, 'tx-1', ReceiptStatus.DELIVERED, 'CODE_SOURCE',
                                                         'sha256:ab'), at=at(2))

    assert state.logbook.expanded(CONTROLLER) and not state.logbook.source_read(CONTROLLER)
    assert state.logbook.source_read(SERVICE) and not state.logbook.expanded(SERVICE)


def test_refused_source_is_traced_without_marking_the_node_read():
    """AC-04 (domaine) : un refus est trace, sans texte ; le noeud n'est pas « lu »."""
    state = opened().record_receipt(SNAPSHOT, SourceReceipt(SERVICE, 'tx-2', ReceiptStatus.REFUSED,
                                                            reason='NOT_REQUESTED'), at=at(1))

    assert not state.logbook.source_read(SERVICE)
    assert state.logbook.receipts[0].reason == 'NOT_REQUESTED'
    assert 'text' not in to_document(state)['logbook']['receipts'][0]


def test_obtained_but_not_sent_is_not_a_delivery():
    """AC-13 : le journal distingue ce qui a ete obtenu, retenu et transmis."""
    delivery = Delivery('D-1', SERVICE, DeliveryKind.TILE, at(5))
    state = opened().record_delivery(SNAPSHOT, delivery)
    record = OperationRecord('get_tile', {'reference': SERVICE}, OperationOutcome.OK, at(5), 'h1', ('D-1',),
                             ({'what': 'facts', 'count': 3},))
    state, _ = state.record_operation(SNAPSHOT, record, 900)

    assert state.logbook.operations[0].delivery_ids == ('D-1',)
    assert state.logbook.operations[0].not_sent == ({'what': 'facts', 'count': 3},)
    assert [item.delivery_id for item in state.logbook.deliveries] == ['D-1']


def test_an_operation_cannot_cite_an_unrecorded_delivery():
    with pytest.raises(MiniaError) as error:
        opened().record_operation(SNAPSHOT, operation(deliveries=('D-9',)), 10)
    assert error.value.code == INVESTIGATION_INVALID


def test_an_interrupted_operation_delivers_nothing_but_counts():
    """AC-06 (domaine) : une operation interrompue ne peut citer aucune livraison ; elle compte dans le budget."""
    with pytest.raises(MiniaError):
        opened().record_delivery(SNAPSHOT, Delivery('D-1', SERVICE, DeliveryKind.TILE, at(1))).record_operation(
            SNAPSHOT, operation(deliveries=('D-1',), outcome=OperationOutcome.INTERRUPTED), 0)

    state, repetition = opened().record_operation(SNAPSHOT, operation(outcome=OperationOutcome.INTERRUPTED,
                                                                      fingerprint=None), 0)
    assert repetition is None
    assert state.budget.total_operations == 1
    assert state.logbook.deliveries == ()


def test_delivery_ids_are_unique_and_replays_cite_their_origin():
    state = opened().record_delivery(SNAPSHOT, Delivery('D-1', SERVICE, DeliveryKind.TILE, at(1)))
    with pytest.raises(MiniaError):
        state.record_delivery(SNAPSHOT, Delivery('D-1', SERVICE, DeliveryKind.TILE, at(2)))
    with pytest.raises(MiniaError):
        state.record_delivery(SNAPSHOT, Delivery('D-2', SERVICE, DeliveryKind.TILE, at(2), replay_of='D-0'))

    replayed = state.record_delivery(SNAPSHOT, Delivery('D-2', SERVICE, DeliveryKind.TILE, at(2), replay_of='D-1'))
    assert replayed.logbook.delivery('D-2').replay_of == 'D-1'


def test_repeated_request_without_progress_is_signalled_with_open_branches():
    """AC-11 : la meme demande qui rend la meme reponse est signalee, avec les branches encore ouvertes."""
    state = explored_two_of_three()
    state, first = state.record_operation(SNAPSHOT, operation(minutes=5), 100)
    state, second = state.record_operation(SNAPSHOT, operation(minutes=6), 100)
    state, third = state.record_operation(SNAPSHOT, operation(minutes=7), 100)

    assert first is None
    assert second.count == 2 and third.count == 3
    assert SAVE in third.open_branches
    assert [event.kind for event in state.pending].count(EventKind.REPETITION) == 2


def test_a_deliberate_revisit_with_other_parameters_is_not_a_repetition():
    state, _ = opened().record_operation(SNAPSHOT, operation(reference=SERVICE, profile='calls/1'), 100)
    state, other_profile = state.record_operation(SNAPSHOT, operation(reference=SERVICE, profile='security/1'), 100)
    state, other_answer = state.record_operation(SNAPSHOT, operation(reference=SERVICE, profile='calls/1',
                                                                     fingerprint='h2'), 100)

    assert other_profile is None and other_answer is None


def test_request_key_ignores_argument_order_but_not_generation():
    assert request_key('a', 7, 'get_tile', {'x': 1, 'y': 2}) == request_key('a', 7, 'get_tile', {'y': 2, 'x': 1})
    assert request_key('a', 7, 'get_tile', {'x': 1}) != request_key('a', 8, 'get_tile', {'x': 1})


# Instantane --------------------------------------------------------------------------------------------------

def test_a_result_from_another_generation_is_never_recorded():
    """INV-05 : un resultat de G2 ne s'inscrit pas dans une enquete de G1."""
    state = opened()
    for write in (lambda: state.record_tile(OTHER_GENERATION, CONTROLLER, (), at=at(1)),
                  lambda: state.record_operation(OTHER_GENERATION, operation(), 10),
                  lambda: state.record_receipt(OTHER_GENERATION, SourceReceipt(SERVICE, 't', ReceiptStatus.DELIVERED),
                                               at=at(1)),
                  lambda: state.record_delivery(OTHER_GENERATION, Delivery('D', SERVICE, DeliveryKind.TILE, at(1)))):
        with pytest.raises(MiniaError) as error:
            write()
        assert error.value.code == INVESTIGATION_STALE


def test_changed_generation_makes_the_investigation_stale_with_its_notes():
    """AC-08 : l'ancienne enquete devient historique ; ses notes aussi, et elle ne se reprend pas."""
    state = explored_two_of_three().confirm_question('Comment fonctionne l’inscription ?', True, allow, at(5))
    state = state.write_note('n1', 'Le service délègue la recherche.', [SERVICE], 'model-x', allow, at(6))
    stale = state.move_to(Status.STALE, at(7))

    assert stale.investigation.status is Status.STALE
    assert stale.notes[0].status is NoteStatus.STALE
    with pytest.raises(MiniaError) as error:
        ensure_resumable(stale.investigation, ALICE, SNAPSHOT, at(8))
    assert error.value.code == INVESTIGATION_STALE
    with pytest.raises(MiniaError) as error:
        ensure_resumable(state.investigation, ALICE, OTHER_GENERATION, at(8))
    assert error.value.code == INVESTIGATION_STALE
    with pytest.raises(MiniaError):
        stale.record_tile(SNAPSHOT, SAVE, (), at=at(9))


def test_status_transitions_are_closed():
    state = opened().move_to(Status.PAUSED, at(1)).move_to(Status.ACTIVE, at(2)).move_to(Status.EXPIRED, at(3))
    with pytest.raises(MiniaError):
        state.move_to(Status.ACTIVE, at(4))


# Question et reprise -----------------------------------------------------------------------------------------

def test_confirmed_question_makes_the_investigation_resumable():
    state = opened().confirm_question('  Comment fonctionne l’inscription ?  ', True, allow, at(1))

    assert state.investigation.resumable
    assert state.investigation.confirmed_question == 'Comment fonctionne l’inscription ?'
    assert state.pending[-1].kind == EventKind.QUESTION_CONFIRMED and state.pending[-1].data == {}
    ensure_resumable(state.investigation, ALICE, SNAPSHOT, at(2))


@pytest.mark.parametrize('confirmed, guard, text', [(False, allow, 'Une question'), (True, refuse, 'Une question'),
                                                    (True, allow, ''), (True, allow, 'x' * 501)])
def test_unconfirmed_or_refused_question_is_never_kept(confirmed, guard, text):
    """AC-20 : sans confirmation, ou si la protection refuse le texte, rien n'est conserve et l'enquete n'est pas
    reprenable ; une nouvelle question est exigee."""
    state = opened()
    with pytest.raises(MiniaError):
        state.confirm_question(text, confirmed, guard, at(1))

    assert not state.investigation.resumable
    assert to_document(state)['investigation']['confirmed_question'] is None
    with pytest.raises(MiniaError) as error:
        ensure_resumable(state.investigation, ALICE, SNAPSHOT, at(2))
    assert error.value.code == INVESTIGATION_NOT_RESUMABLE


def test_resume_is_refused_outside_scope_without_revealing_existence():
    """AC-07 et AC-16 : un autre perimetre recoit « introuvable » ; une enquete expiree n'est pas restituee."""
    state = opened().confirm_question('Une question', True, allow, at(1))

    with pytest.raises(MiniaError) as error:
        ensure_resumable(state.investigation, BOB, SNAPSHOT, at(2))
    assert error.value.code == INVESTIGATION_NOT_FOUND
    with pytest.raises(MiniaError) as error:
        ensure_resumable(state.investigation, ALICE, SNAPSHOT, at(1) + timedelta(days=7))
    assert error.value.code == INVESTIGATION_EXPIRED


def test_activity_pushes_back_expiry():
    state = opened().record_tile(SNAPSHOT, CONTROLLER, (), at=at(60))

    assert state.investigation.last_activity_at == at(60)
    assert state.investigation.expires_at == at(60) + timedelta(days=7)


@pytest.mark.parametrize('build', [lambda: Snapshot('', 1), lambda: Snapshot('a', -1), lambda: OwnerScope('', 'p'),
                                   lambda: ExpiryPolicy(timedelta(0))])
def test_identity_values_are_validated(build):
    with pytest.raises(MiniaError):
        build()


# Notes HYPOTHESIS_LLM ----------------------------------------------------------------------------------------

def test_a_note_is_a_hypothesis_linked_to_known_nodes_and_generation():
    """AC-09 : la note reste distincte des faits, liee a la bonne generation ; ses versions restent au journal."""
    state = explored_two_of_three()
    state = state.write_note('n1', 'Le service vérifierait l’étudiant avant le cours.', [SERVICE, FIND_STUDENT],
                             'model-x', allow, at(6))
    state = state.revise_note('n1', 'Le service cherche l’étudiant puis le cours.', [SERVICE], allow, at(7))
    state = state.close_note('n1', at(8))

    note = state.notes[0]
    assert (note.kind, note.version, note.status, note.generation_id) == (KIND, 3, NoteStatus.CLOSED, 7)
    versions = [event.data for event in state.pending if event.kind == EventKind.NOTE]
    assert [item['version'] for item in versions] == [1, 2, 3]
    assert versions[0]['text'] != versions[1]['text']
    with pytest.raises(MiniaError):
        state.revise_note('n1', 'encore', [SERVICE], allow, at(9))


def test_a_note_citing_an_unknown_node_is_refused():
    with pytest.raises(MiniaError) as error:
        explored_two_of_three().write_note('n1', 'Hypothèse', ['method:invented#x()'], 'm', allow, at(6))
    assert error.value.code == NOTE_REFUSED
    assert 'method:invented#x()' in str(error.value)


@pytest.mark.parametrize('text, guard', [('x' * (MAX_NOTE_CHARS + 1), allow), ('', allow),
                                         ('password = "hunter2"', refuse)])
def test_long_empty_or_confidential_notes_are_not_kept(text, guard):
    """AC-15 (domaine) : taille bornee et protection appliquee avant toute conservation."""
    state = explored_two_of_three()
    with pytest.raises(MiniaError):
        state.write_note('n1', text, [SERVICE], 'm', guard, at(6))
    assert state.notes == ()


def test_the_guard_decides_the_kept_text():
    state = explored_two_of_three().write_note('n1', 'jeton sk-abc', [SERVICE], 'm',
                                               lambda text: text.replace('sk-abc', '******'), at(6))
    assert state.notes[0].text == 'jeton ******'


def test_a_note_cites_a_bounded_number_of_nodes():
    state = explored_two_of_three()
    with pytest.raises(MiniaError) as error:
        state.write_note('n1', 'Hypothèse', [SERVICE] + [f'method:x.N{index}#n()' for index in range(MAX_NOTE_NODES)],
                         'm', allow, at(6))
    assert error.value.code == NOTE_REFUSED


def test_only_open_and_revised_notes_are_open():
    state = explored_two_of_three().write_note('n1', 'a', [SERVICE], 'm', allow, at(6))
    state = state.write_note('n2', 'b', [SAVE], 'm', allow, at(6)).revise_note('n2', 'b2', [SAVE], allow, at(7))
    state = state.write_note('n3', 'c', [], 'm', allow, at(7)).close_note('n3', at(8))

    assert [note.note_id for note in open_notes(state.notes)] == ['n1', 'n2']
    with pytest.raises(MiniaError) as error:
        state.close_note('n9', at(9))
    assert error.value.code == NOTE_REFUSED


def test_note_ids_are_unique():
    state = explored_two_of_three().write_note('n1', 'a', [SERVICE], 'm', allow, at(6))
    with pytest.raises(MiniaError):
        state.write_note('n1', 'b', [SERVICE], 'm', allow, at(7))


# Budget ------------------------------------------------------------------------------------------------------

SMALL = BudgetLimits(slice_operations=2, slice_bytes=10_000, total_operations=5, total_bytes=50_000, max_renewals=3)


def exhausted_slice():
    state = explored_two_of_three(opened(limits=SMALL))
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=5, fingerprint='a'), 100)
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=6, fingerprint='b'), 100)
    return state


def test_an_operation_beyond_the_slice_is_refused():
    with pytest.raises(MiniaError) as error:
        exhausted_slice().record_operation(SNAPSHOT, operation(minutes=7, fingerprint='c'), 100)
    assert error.value.code == BUDGET_EXHAUSTED


def test_slice_bytes_exhaust_the_slice():
    state, _ = opened(limits=SMALL).record_operation(SNAPSHOT, operation(), 10_000)
    assert state.budget.slice_exhausted


def test_justified_renewal_on_known_branches_opens_a_new_slice():
    """AC-10 : renouvellement accorde pour des branches deja decouvertes, sous le plafond total."""
    state, decision = exhausted_slice().request_renewal(RenewalRequest((SAVE,), 'Lire l’enregistrement.'), at(8))

    assert decision.granted and decision.operations == 2
    assert state.budget.remaining_operations == 2 and state.budget.renewals == 1
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=9, fingerprint='c'), 100)
    assert state.budget.total_operations == 3


@pytest.mark.parametrize('request_, refusal', [
    (RenewalRequest((SAVE,), ''), Refusal.NO_JUSTIFICATION),
    (RenewalRequest((SAVE,), 'x' * 501), Refusal.NO_JUSTIFICATION),
    (RenewalRequest((), 'Pourquoi'), Refusal.NO_BRANCH),
    (RenewalRequest(('method:invented#x()',), 'Pourquoi'), Refusal.UNKNOWN_BRANCH),
    (RenewalRequest((SERVICE,), 'Déjà développé'), Refusal.UNKNOWN_BRANCH),
])
def test_renewal_controls_are_mechanical(request_, refusal):
    state, decision = exhausted_slice().request_renewal(request_, at(8))

    assert not decision.granted and decision.refusal == refusal
    assert state.budget.refusals == 1 and state.budget.slice_exhausted


def test_renewal_is_refused_before_the_slice_is_spent():
    _, decision = explored_two_of_three(opened(limits=SMALL)).request_renewal(RenewalRequest((SAVE,), 'Pourquoi'),
                                                                               at(5))
    assert decision.refusal == Refusal.SLICE_NOT_EXHAUSTED


def test_renewal_without_progress_is_refused():
    state, _ = exhausted_slice().request_renewal(RenewalRequest((SAVE,), 'Lire save.'), at(8))
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=9, fingerprint='c'), 100)
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=10, fingerprint='d'), 100)

    _, decision = state.request_renewal(RenewalRequest((SAVE,), 'Lire save, encore.'), at(11))
    assert decision.refusal == Refusal.NO_PROGRESS

    progressed = state.record_tile(SNAPSHOT, SAVE, (), at=at(11))
    _, decision = progressed.request_renewal(RenewalRequest((STUDENT_BY_ID,), 'Lire le repository.'), at(12))
    assert decision.granted


def test_total_cap_bounds_every_renewal():
    limits = BudgetLimits(slice_operations=2, slice_bytes=10_000, total_operations=3, total_bytes=50_000,
                          max_renewals=5)
    state = explored_two_of_three(opened(limits=limits))
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=5, fingerprint='a'), 100)
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=6, fingerprint='b'), 100)
    state, decision = state.request_renewal(RenewalRequest((SAVE,), 'Pourquoi', operations=5), at(7))
    assert decision.operations == 1
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=8, fingerprint='c'), 100)

    state = state.record_tile(SNAPSHOT, SAVE, (), at=at(9))
    _, decision = state.request_renewal(RenewalRequest((STUDENT_BY_ID,), 'Pourquoi'), at(10))
    assert decision.refusal == Refusal.TOTAL_EXHAUSTED


def test_renewals_are_capped():
    limits = BudgetLimits(slice_operations=1, slice_bytes=10_000, total_operations=10, total_bytes=50_000,
                          max_renewals=0)
    state, _ = explored_two_of_three(opened(limits=limits)).record_operation(SNAPSHOT, operation(), 1)
    _, decision = state.request_renewal(RenewalRequest((SAVE,), 'Pourquoi'), at(8))
    assert decision.refusal == Refusal.TOO_MANY_RENEWALS


@pytest.mark.parametrize('values', [(0, 1, 1, 1, 0), (2, 1, 1, 1, 0), (1, 2, 1, 1, 0), (1, 1, 1, 1, -1)])
def test_budget_limits_are_validated(values):
    with pytest.raises(MiniaError):
        BudgetLimits(*values)


def test_negative_response_size_is_refused():
    with pytest.raises(MiniaError):
        opened().record_operation(SNAPSHOT, operation(), -1)


# Serialisation -----------------------------------------------------------------------------------------------

def full_state():
    state = explored_two_of_three().confirm_question('Comment fonctionne l’inscription ?', True, allow, at(5))
    state = state.record_receipt(SNAPSHOT, SourceReceipt(SERVICE, 'tx-1', ReceiptStatus.TRUNCATED, 'CODE_SOURCE',
                                                         'sha256:ab'), at=at(6))
    state = state.record_receipt(SNAPSHOT, SourceReceipt(SAVE, 'tx-2', ReceiptStatus.REFUSED, reason='DISABLED'),
                                 at=at(6))
    state = state.record_delivery(SNAPSHOT, Delivery('D-1', SERVICE, DeliveryKind.SOURCE, at(6)))
    state, _ = state.record_operation(SNAPSHOT, OperationRecord('get_source', {'reference': SERVICE},
                                                                OperationOutcome.OK, at(6), 'h', ('D-1',),
                                                                ({'what': 'lines', 'reason': 'LIMIT'},)), 4000)
    state = state.record_action(SNAPSHOT, CONTROLLER, Action.EVIDENCE, at=at(7))
    state = state.write_note('n1', 'Hypothèse de travail', [SERVICE], 'model-x', allow, at(8))
    return state


def test_save_and_restore_is_exact():
    """AC-05 et INV-04 (domaine) : question confirmee, frontiere, visites, notes, recus et budget identiques."""
    state = without_pending(full_state())

    restored = from_document(to_document(state))

    assert restored == state
    assert to_document(restored) == to_document(state)


def test_the_document_never_carries_source_text():
    document = to_document(full_state())

    assert document['schema_version'] == SCHEMA_VERSION
    assert set(document['logbook']['receipts'][0]) == {'reference', 'transmission_id', 'status', 'classification',
                                                       'fingerprint', 'reason'}


def test_another_schema_version_or_a_broken_document_is_refused():
    document = to_document(full_state())
    with pytest.raises(MiniaError) as error:
        from_document({**document, 'schema_version': SCHEMA_VERSION + 1})
    assert error.value.code == INVESTIGATION_INVALID
    broken = {**document, 'investigation': {**document['investigation'], 'created_at': '2026-10-11T09:00:00'}}
    with pytest.raises(MiniaError) as error:
        from_document(broken)
    assert error.value.code == INVESTIGATION_INVALID
    with pytest.raises(MiniaError):
        from_document({key: value for key, value in document.items() if key != 'budget'})


def test_events_round_trip():
    for event in full_state().pending:
        assert event_from_document(event_to_document(event)) == event


def test_operation_arguments_are_kept_as_json_values():
    state, _ = opened().record_operation(SNAPSHOT, operation(steps=({'relation': 'CALLS'},)), 1)
    assert state.logbook.operations[0].arguments == {'steps': [{'relation': 'CALLS'}]}
    with pytest.raises(MiniaError):
        opened().record_operation(SNAPSHOT, operation(bad={1, 2}), 1)


def test_opened_investigation_starts_active_and_logs_its_snapshot():
    state = opened()

    assert state.investigation.status is Status.ACTIVE and state.revision == 0
    assert state.investigation.created_at == T0
    assert state.pending[0].data == {'analysis_id': 'analysis-1', 'generation_id': 7}
    assert state.budget.limits == LIMITS


# Revue du lot A : plafonds, provenance, reprise, repetition, fuseaux ---------------------------------------------

def test_a_response_beyond_the_remaining_bytes_is_refused():
    """Une reponse ne depasse jamais les octets qui restent a la tranche ni au total."""
    limits = BudgetLimits(slice_operations=4, slice_bytes=10, total_operations=8, total_bytes=50, max_renewals=1)
    state = opened(limits=limits)
    with pytest.raises(MiniaError) as error:
        state.record_operation(SNAPSHOT, operation(), 11)
    assert error.value.code == BUDGET_EXHAUSTED
    state, _ = state.record_operation(SNAPSHOT, operation(), 10)
    assert state.budget.slice_bytes == 10 and state.budget.remaining_bytes == 0


def test_the_total_bytes_bound_a_response_too():
    limits = BudgetLimits(slice_operations=4, slice_bytes=100, total_operations=8, total_bytes=100, max_renewals=1)
    state, _ = opened(limits=limits).record_operation(SNAPSHOT, operation(fingerprint='a'), 60)
    assert state.budget.remaining_bytes == 40
    with pytest.raises(MiniaError) as error:
        state.record_operation(SNAPSHOT, operation(fingerprint='b'), 41)
    assert error.value.code == BUDGET_EXHAUSTED


def test_naming_another_branch_is_not_progress():
    state, _ = exhausted_slice().request_renewal(RenewalRequest((SAVE,), 'Lire save.'), at(8))
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=9, fingerprint='c'), 100)
    state, _ = state.record_operation(SNAPSHOT, operation(minutes=10, fingerprint='d'), 100)

    _, decision = state.request_renewal(RenewalRequest((STUDENT_BY_ID,), 'Une autre branche.'), at(11))
    assert decision.refusal == Refusal.NO_PROGRESS


@pytest.mark.parametrize('action', [Action.TILE, Action.SOURCE])
def test_a_tile_or_a_source_read_is_never_recorded_without_what_establishes_it(action):
    with pytest.raises(MiniaError) as error:
        opened().record_action(SNAPSHOT, SERVICE, action, at=at(1))
    assert error.value.code == INVESTIGATION_INVALID


def test_evidence_and_references_are_recorded_directly():
    state = opened().record_action(SNAPSHOT, SERVICE, Action.EVIDENCE, at=at(1))
    state = state.record_action(SNAPSHOT, SERVICE, Action.REFERENCES, at=at(2))
    assert not state.logbook.expanded(SERVICE) and not state.logbook.source_read(SERVICE)


def test_a_completed_investigation_is_not_resumable():
    state = opened().confirm_question('Une question', True, allow, at(1)).move_to(Status.COMPLETE, at(2))
    with pytest.raises(MiniaError) as error:
        ensure_resumable(state.investigation, ALICE, SNAPSHOT, at(3))
    assert error.value.code == INVESTIGATION_NOT_RESUMABLE


def test_responses_without_fingerprint_or_with_another_outcome_are_not_repetitions():
    state, _ = opened().record_operation(SNAPSHOT, operation(fingerprint=None), 100)
    state, without = state.record_operation(SNAPSHOT, operation(fingerprint=None), 100)
    state, _ = state.record_operation(SNAPSHOT, operation(fingerprint='e', outcome=OperationOutcome.ERROR), 100)
    state, other_outcome = state.record_operation(SNAPSHOT, operation(fingerprint='e',
                                                                      outcome=OperationOutcome.REFUSED), 100)

    assert without is None and other_outcome is None


def test_a_timezone_less_instant_is_refused_at_once():
    naive = T0.replace(tzinfo=None)
    with pytest.raises(MiniaError) as error:
        InvestigationState.opened('inv-naive', ALICE, SNAPSHOT, LIMITS, ExpiryPolicy(timedelta(days=7)), naive)
    assert error.value.code == INVESTIGATION_INVALID
    with pytest.raises(MiniaError):
        opened().record_tile(SNAPSHOT, CONTROLLER, (), at=naive)


# Revue du lot A, seconde passe -----------------------------------------------------------------------------------

def test_the_same_answer_after_progress_is_not_a_repetition():
    state, _ = opened().record_operation(SNAPSHOT, operation(minutes=1), 100)
    state = state.record_tile(SNAPSHOT, CONTROLLER, calls(CONTROLLER, SERVICE), at=at(2))
    state, after_progress = state.record_operation(SNAPSHOT, operation(minutes=3), 100)
    state, without_progress = state.record_operation(SNAPSHOT, operation(minutes=4), 100)

    assert after_progress is None and without_progress.count == 2
    restored = from_document(to_document(state))
    assert [record.progress for record in restored.logbook.operations] == [0, 2, 2]


@pytest.mark.parametrize('size', [-1, 1.5])
def test_a_renewal_of_a_malformed_size_is_refused(size):
    _, decision = exhausted_slice().request_renewal(RenewalRequest((SAVE,), 'Lire save.', size), at(8))
    assert decision.refusal == Refusal.INVALID_SIZE


def test_a_status_change_without_timezone_is_refused():
    with pytest.raises(MiniaError) as error:
        opened().move_to(Status.PAUSED, T0.replace(tzinfo=None))
    assert error.value.code == INVESTIGATION_INVALID


def test_an_inactivity_with_a_fraction_of_second_is_refused():
    with pytest.raises(MiniaError) as error:
        ExpiryPolicy(timedelta(seconds=1, milliseconds=500))
    assert error.value.code == INVESTIGATION_INVALID
