"""L'etat d'une enquete et ses changements (recit TAXO-MINIA-ENQUETE-01, § 6 et § 7).

L'etat reunit l'identite, le carnet, les notes et le budget. Chaque changement rend un nouvel etat et ajoute les
evenements qui le decrivent a `pending` : le port de stockage ecrit l'etat et ces evenements dans la meme
transaction, sous controle de revision, puis rend un etat sans evenement en attente. Rien ici ne lit Taxo ni ne
juge un resultat : l'application inscrit ce que Taxo a rendu et ce qui a ete transmis.
"""
from dataclasses import dataclass, field, replace
from datetime import datetime

from ..errors import INVESTIGATION_INVALID, INVESTIGATION_STALE, MiniaError
from . import notes as hypotheses
from .budget import Budget, BudgetLimits, RenewalDecision, RenewalRequest
from .identity import (WRITABLE, ExpiryPolicy, Investigation, OwnerScope, Snapshot, Status, TextGuard, aware,
                       confirm_question, open_investigation)
from .logbook import (Action, Delivery, InFlight, Logbook, OperationOutcome, OperationRecord, Repetition, SourceReceipt,
                      uncertain)
from .values import plain as _plain

DIRECT_ACTIONS = frozenset({Action.EVIDENCE, Action.REFERENCES})


class EventKind:
    OPENED = 'OPENED'
    QUESTION_CONFIRMED = 'QUESTION_CONFIRMED'
    TILE = 'TILE'
    ACTION = 'ACTION'
    RECEIPT = 'RECEIPT'
    DELIVERY = 'DELIVERY'
    OPERATION = 'OPERATION'
    IN_FLIGHT = 'IN_FLIGHT'
    REPETITION = 'REPETITION'
    NOTE = 'NOTE'
    RENEWAL = 'RENEWAL'
    STATUS = 'STATUS'


@dataclass(frozen=True)
class Event:
    """Une ligne du journal append-only : ce qui a change, quand, avec des metadonnees seulement."""
    kind: str
    at: datetime
    data: dict


@dataclass(frozen=True)
class InvestigationState:
    investigation: Investigation
    policy: ExpiryPolicy
    budget: Budget
    logbook: Logbook = field(default_factory=Logbook)
    notes: tuple = ()
    # Les operations dont la reponse part au modele, inscrites avant l'envoi (journal B ecrit a l'avance).
    in_flight: tuple = ()
    pending: tuple = ()

    @classmethod
    def opened(cls, investigation_id: str, scope: OwnerScope, snapshot: Snapshot, limits: BudgetLimits,
               policy: ExpiryPolicy, at: datetime) -> 'InvestigationState':
        investigation = open_investigation(investigation_id, scope, snapshot, at, policy)
        event = Event(EventKind.OPENED, at, {'analysis_id': snapshot.analysis_id,
                                             'generation_id': snapshot.generation_id})
        return cls(investigation, policy, Budget(limits), pending=(event,))

    @property
    def investigation_id(self) -> str:
        return self.investigation.investigation_id

    @property
    def revision(self) -> int:
        return self.investigation.revision

    # Identite et question ------------------------------------------------------------------------------------

    def confirm_question(self, text: str, confirmed_by_user: bool, guard: TextGuard,
                         at: datetime) -> 'InvestigationState':
        self.investigation.ensure_writable()
        investigation = confirm_question(self.investigation, text, confirmed_by_user, guard)
        # Le journal dit qu'une question a ete confirmee, sans la recopier : l'etat seul la garde.
        return self._changed(Event(EventKind.QUESTION_CONFIRMED, at, {}), at, investigation=investigation)

    # Carnet -------------------------------------------------------------------------------------------------

    def record_tile(self, snapshot: Snapshot, anchor: str, edges=(), frontier=(), *, at: datetime,
                    expanded=()) -> 'InvestigationState':
        self._writable_on(snapshot)
        logbook = self.logbook.with_tile(anchor, edges, frontier, expanded)
        event = Event(EventKind.TILE, at, {'anchor': anchor, 'edges': len(logbook.edges) - len(self.logbook.edges),
                                           'frontier': len(logbook.frontier)})
        return self._changed(event, at, logbook=logbook)

    def record_action(self, snapshot: Snapshot, node: str, action: Action, *, at: datetime) -> 'InvestigationState':
        """Une visite sans trace propre (preuve, references). Une Tuile et une lecture de code s'inscrivent par
        `record_tile` et `record_receipt`, qui gardent ce qui les etablit."""
        if action not in DIRECT_ACTIONS:
            raise MiniaError(INVESTIGATION_INVALID, f'Une visite {action} s’inscrit avec ce qui l’établit.')
        self._writable_on(snapshot)
        logbook = self.logbook.with_action(node, action)
        return self._changed(Event(EventKind.ACTION, at, {'node': node, 'action': str(action)}), at, logbook=logbook)

    def record_receipt(self, snapshot: Snapshot, receipt: SourceReceipt, *, at: datetime) -> 'InvestigationState':
        self._writable_on(snapshot)
        logbook = self.logbook.with_receipt(receipt)
        return self._changed(Event(EventKind.RECEIPT, at, _plain(receipt)), at, logbook=logbook)

    def record_delivery(self, snapshot: Snapshot, delivery: Delivery) -> 'InvestigationState':
        """Un element reellement insere dans un message envoye au modele. A n'appeler qu'apres l'envoi : ce qui
        n'est pas parti n'est jamais dit transmis (INV-07)."""
        self._writable_on(snapshot)
        logbook = self.logbook.with_delivery(delivery)
        return self._changed(Event(EventKind.DELIVERY, delivery.at, _plain(delivery)), delivery.at, logbook=logbook)

    def record_operation(self, snapshot: Snapshot, record: OperationRecord,
                         response_bytes: int) -> tuple['InvestigationState', Repetition | None]:
        """Une operation demandee a Taxo, comptee dans le budget, et le signal de repetition s'il y a lieu. Une
        operation interrompue compte : elle est partie, meme si rien de son resultat n'est inscrit."""
        self._writable_on(snapshot)
        return self._operation(record, response_bytes)

    def announce(self, snapshot: Snapshot, items, at: datetime) -> 'InvestigationState':
        """Les operations dont la reponse va partir au modele, inscrites avant l'envoi. L'envoi et l'ecriture du
        carnet ne tiennent pas dans une meme transaction : si le processus s'arrete entre les deux, la reprise les
        inscrit comme peut-etre transmises (`settle_in_flight`), jamais comme absentes."""
        self._writable_on(snapshot)
        items = tuple(items)
        if self.in_flight:
            raise MiniaError(INVESTIGATION_INVALID, 'Un envoi précédent n’est pas encore inscrit.')
        if not all(isinstance(item, InFlight) for item in items):
            raise MiniaError(INVESTIGATION_INVALID, 'Seule une opération en partance s’annonce.')
        event = Event(EventKind.IN_FLIGHT, at, {'operations': [item.record.name for item in items],
                                                'delivery_ids': [delivery_id for item in items
                                                                 for delivery_id in item.record.delivery_ids]})
        return self._changed(event, at, in_flight=items)

    def landed(self) -> 'InvestigationState':
        """L'envoi est atteste et ses operations inscrites avec leurs livraisons : l'annonce est levee."""
        return replace(self, in_flight=())

    def settle_in_flight(self) -> 'InvestigationState':
        """Les operations annoncees dont l'envoi n'a jamais ete atteste : chacune s'inscrit peut-etre transmise.
        C'est un fait passe de l'enquete, inscrit meme si elle ne recoit plus d'operation (pause, expiration)."""
        state = self
        for item in self.in_flight:
            state, _ = state._operation(uncertain(item.record), item.response_bytes)
        return replace(state, in_flight=())

    def _operation(self, record: OperationRecord, response_bytes: int):
        if record.outcome is OperationOutcome.INTERRUPTED and record.delivery_ids:
            raise MiniaError(INVESTIGATION_INVALID, 'Une opération interrompue n’a rien transmis.')
        budget = self.budget.spend(response_bytes)
        snapshot = self.investigation.snapshot
        logbook, repetition = self.logbook.with_operation(record, snapshot.analysis_id, snapshot.generation_id)
        events = [Event(EventKind.OPERATION, record.at, {**_plain(record), 'bytes': response_bytes})]
        if repetition is not None:
            events.append(Event(EventKind.REPETITION, record.at, {'count': repetition.count,
                                                                    'open_branches': list(repetition.open_branches)}))
        state = replace(self, logbook=logbook, budget=budget, pending=self.pending + tuple(events))
        if self.investigation.status in WRITABLE:
            state = replace(state, investigation=self.investigation.touched(record.at, self.policy))
        return state, repetition

    # Notes ------------------------------------------------------------------------------------------------

    def write_note(self, note_id: str, text: str, nodes, author: str, guard: TextGuard,
                   at: datetime) -> 'InvestigationState':
        self.investigation.ensure_writable()
        notes, note = hypotheses.write_note(self.notes, note_id, text, nodes, self.logbook.known_nodes(),
                                            self.investigation.snapshot.generation_id, author, at, guard)
        return self._changed(Event(EventKind.NOTE, at, _plain(note)), at, notes=notes)

    def revise_note(self, note_id: str, text: str, nodes, guard: TextGuard, at: datetime) -> 'InvestigationState':
        self.investigation.ensure_writable()
        notes, note = hypotheses.revise_note(self.notes, note_id, text, nodes, self.logbook.known_nodes(), at, guard)
        return self._changed(Event(EventKind.NOTE, at, _plain(note)), at, notes=notes)

    def close_note(self, note_id: str, at: datetime) -> 'InvestigationState':
        self.investigation.ensure_writable()
        notes, note = hypotheses.close_note(self.notes, note_id, at)
        return self._changed(Event(EventKind.NOTE, at, _plain(note)), at, notes=notes)

    # Budget -----------------------------------------------------------------------------------------------

    def request_renewal(self, request: RenewalRequest,
                        at: datetime) -> tuple['InvestigationState', RenewalDecision]:
        self.investigation.ensure_writable()
        open_branches = self.logbook.open_branches()
        budget, decision = self.budget.renew(request, open_branches, self.logbook.progress)
        data = {'granted': decision.granted, 'operations': decision.operations, 'refusal': decision.refusal,
                'branches': list(request.branches)}
        return self._changed(Event(EventKind.RENEWAL, at, data), at, budget=budget), decision

    # Etat -------------------------------------------------------------------------------------------------

    def move_to(self, status: Status, at: datetime) -> 'InvestigationState':
        aware(at)
        investigation = self.investigation.moved_to(status)
        notes = hypotheses.stale_notes(self.notes) if status is Status.STALE else self.notes
        event = Event(EventKind.STATUS, at, {'from': str(self.investigation.status), 'to': str(status)})
        return replace(self, investigation=investigation, notes=notes, pending=self.pending + (event,))

    def committed(self, revision: int) -> 'InvestigationState':
        """L'etat tel que le stockage l'a ecrit : sa nouvelle revision, sans evenement en attente."""
        return replace(self, investigation=replace(self.investigation, revision=revision), pending=())

    def _writable_on(self, snapshot: Snapshot):
        self.investigation.ensure_writable()
        if snapshot != self.investigation.snapshot:
            # INV-05 : un resultat ou une reprise d'une generation ne s'applique jamais a une autre.
            raise MiniaError(INVESTIGATION_STALE, 'Ce résultat vient d’une autre génération de la Maille que '
                             'celle de l’enquête : il n’est pas inscrit.')

    def _changed(self, event: Event, at: datetime, **fields) -> 'InvestigationState':
        investigation = fields.pop('investigation', self.investigation).touched(at, self.policy)
        return replace(self, investigation=investigation, pending=self.pending + (event,), **fields)
