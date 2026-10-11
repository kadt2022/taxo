"""L'etat d'une enquete ecrit en document versionne, et relu a l'identique (recit TAXO-MINIA-ENQUETE-01, INV-04).

Le document ne porte que des valeurs simples, sans aucun contenu source. Sa version de schema est verifiee a la
lecture : un document d'une autre version est refuse, jamais lu au hasard. Un champ manquant ou d'un mauvais type
est une erreur explicite, jamais une valeur par defaut silencieuse.
"""
from datetime import datetime, timedelta

from ..errors import INVESTIGATION_INVALID, MiniaError
from .budget import Budget, BudgetLimits
from .identity import ExpiryPolicy, Investigation, OwnerScope, Snapshot, Status
from .logbook import (Action, Delivery, DeliveryKind, Edge, FrontierEntry, FrontierKind, InFlight, Logbook,
                      OperationOutcome, OperationRecord, ReceiptStatus, SourceReceipt)
from .notes import Hypothesis, NoteStatus
from .state import Event, InvestigationState
from .values import plain, simple

SCHEMA_VERSION = 1


def to_document(state: InvestigationState) -> dict:
    """L'etat ecrit, sans les evenements en attente : ils vont au journal."""
    budget = state.budget
    return {
        'schema_version': SCHEMA_VERSION,
        'investigation': plain(state.investigation),
        'inactivity_seconds': int(state.policy.inactivity.total_seconds()),
        'budget': {**plain(budget.limits), 'used': {
            'slice_operations': budget.slice_operations, 'slice_bytes': budget.slice_bytes,
            'total_operations': budget.total_operations, 'total_bytes': budget.total_bytes,
            'granted_operations': budget.granted_operations, 'renewals': budget.renewals,
            'refusals': budget.refusals, 'last_renewal': simple(budget.last_renewal)}},
        'logbook': {
            'visited': {node: [str(action) for action in actions] for node, actions in state.logbook.visited.items()},
            'edges': [plain(edge) for edge in state.logbook.edges],
            'frontier': [plain(entry) for entry in state.logbook.frontier],
            'receipts': [plain(receipt) for receipt in state.logbook.receipts],
            'operations': [plain(record) for record in state.logbook.operations],
            'deliveries': [plain(delivery) for delivery in state.logbook.deliveries],
        },
        'notes': [plain(note) for note in state.notes],
        'in_flight': [{'record': plain(item.record), 'response_bytes': item.response_bytes}
                      for item in state.in_flight],
    }


def from_document(document: dict) -> InvestigationState:
    try:
        version = document['schema_version']
        if version != SCHEMA_VERSION:
            raise MiniaError(INVESTIGATION_INVALID, f'Version de carnet inconnue ({version}) : il n’est pas relu.')
        return InvestigationState(_investigation(document['investigation']),
                                  ExpiryPolicy(timedelta(seconds=document['inactivity_seconds'])),
                                  _budget(document['budget']), _logbook(document['logbook']),
                                  tuple(_note(item) for item in document['notes']),
                                  tuple(InFlight(_operation(item['record']), int(item['response_bytes']))
                                        for item in document['in_flight']))
    except MiniaError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise MiniaError(INVESTIGATION_INVALID, 'Le carnet enregistré est illisible : il n’est pas restitué.') from exc


def event_to_document(event: Event) -> dict:
    return {'kind': event.kind, 'at': event.at.isoformat(), 'data': simple(event.data)}


def event_from_document(document: dict) -> Event:
    return Event(document['kind'], _at(document['at']), document['data'])


def _at(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError('date sans fuseau')
    return moment


def _investigation(data):
    return Investigation(data['investigation_id'], OwnerScope(**data['scope']), Snapshot(**data['snapshot']),
                         Status(data['status']), int(data['revision']), _at(data['created_at']),
                         _at(data['last_activity_at']), _at(data['expires_at']), data['confirmed_question'])


def _budget(data):
    used = data['used']
    limits = BudgetLimits(*(data[name] for name in ('slice_operations', 'slice_bytes', 'total_operations',
                                                     'total_bytes', 'max_renewals')))
    last = used['last_renewal']
    return Budget(limits, used['slice_operations'], used['slice_bytes'], used['total_operations'],
                  used['total_bytes'], used['granted_operations'], used['renewals'], used['refusals'],
                  None if last is None else (tuple(last[0]), last[1]))


def _logbook(data):
    return Logbook(
        visited={node: tuple(Action(action) for action in actions) for node, actions in data['visited'].items()},
        edges=tuple(Edge(**item) for item in data['edges']),
        frontier=tuple(FrontierEntry(item['node'], FrontierKind(item['kind']), item['reason'], item['continuation'])
                       for item in data['frontier']),
        receipts=tuple(SourceReceipt(item['reference'], item['transmission_id'], ReceiptStatus(item['status']),
                                     item['classification'], item['fingerprint'], item['reason'])
                       for item in data['receipts']),
        operations=tuple(_operation(item) for item in data['operations']),
        deliveries=tuple(Delivery(item['delivery_id'], item['mip_reference'], DeliveryKind(item['kind']),
                                  _at(item['at']), item['replay_of'])
                         for item in data['deliveries']),
    )


def _operation(item):
    return OperationRecord(item['name'], item['arguments'], OperationOutcome(item['outcome']), _at(item['at']),
                           item['response_fingerprint'], tuple(item['delivery_ids']), tuple(item['not_sent']),
                           item['progress'])


def _note(item):
    return Hypothesis(item['note_id'], item['version'], item['text'], tuple(item['nodes']), item['generation_id'],
                      item['author'], NoteStatus(item['status']), _at(item['at']), item['kind'])
