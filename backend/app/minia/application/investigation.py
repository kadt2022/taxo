"""L'enquete navigable de Minia : le modele enquete par Tuiles successives, Minia tient le carnet
(recit TAXO-MINIA-ENQUETE-01, lot C ; ARCHITECTURE § 12.7).

Taxo est le cartographe, Minia la commissionnaire, le modele l'enqueteur. Une demande ouvre une enquete, ou reprend
une enquete reprenable, et en joue une ou plusieurs tranches :

1. Minia ouvre un echange du protocole sur l'analyse de l'enquete et verifie la generation de ses faits ;
2. a chaque tour, le modele recoit la question, les operations proposees, l'etat compact du carnet et les reponses
   de la tranche, et choisit : une operation, une note, une nouvelle tranche, ou sa reponse ;
3. Minia transmet l'operation a Taxo par les chemins existants (echange, Tuile MIP, code d'un symbole), inscrit ce
   que Taxo a rendu, et n'inscrit une **livraison** qu'une fois le message reellement parti vers le modele ;
4. l'etat et ses evenements sont enregistres a chaque tour : une interruption laisse un carnet coherent.

`verify_claim` n'est pas propose dans ce parcours : Taxo n'y donne aucun verdict sur les conclusions du modele
(INV-01). La reponse finale est une declaration structuree, confrontee par identifiants au journal des livraisons.
Une Tuile ou une reference deja rendue dans la meme demande peut etre rejouee depuis la memoire vive, jamais le code
ni un diff ; la memoire vive disparait avec la demande.
"""
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.minia.application import trace
from app.minia.domain.cancellation import check
from app.minia.domain.errors import (CONFIDENTIALITY_REFUSED, INVESTIGATION_EXPIRED, INVESTIGATION_STALE, NOTE_REFUSED,
                                     MiniaError)
from app.minia.domain.exploration import Call
from app.minia.domain.investigation import conversation
from app.minia.domain.investigation import declaration as declared
from app.minia.domain.investigation import responses
from app.minia.domain.investigation.budget import BudgetLimits
from app.minia.domain.investigation.identity import (ExpiryPolicy, OwnerScope, Snapshot, Status,
                                                     ensure_resumable)
from app.minia.domain.investigation.logbook import (Action, Delivery, InFlight, OperationOutcome, OperationRecord,
                                                    request_key)
from app.minia.domain.investigation.state import InvestigationState
from app.protocol.domain.envelope import MAX_ERROR_BYTES

# Taxo n'authentifie pas encore ses utilisateurs : le perimetre d'une enquete est le projet, pour ce poste.
LOCAL_OWNER = 'local'
# Budgets de depart (§ 8.1), a calibrer par mesure : une tranche vaut les 8 operations de l'exploration actuelle ;
# l'echange du protocole en sert au plus 20, dont `describe`.
DEFAULT_LIMITS = BudgetLimits(slice_operations=8, slice_bytes=64_000, total_operations=18, total_bytes=160_000,
                              max_renewals=2)
DEFAULT_INACTIVITY = timedelta(days=7)
# Tours du modele sans operation (notes, renouvellement, refus) permis en plus des operations : une enquete finit.
EXTRA_TURNS = 8
TURN_MARGIN = 512
ROOM_TO_CONTINUE = 1024
MAX_EXCHANGE_BYTES = 200_000
# Une reponse de Taxo ne prend jamais plus, quelle que soit la place : celle d'une Tuile servie a Minia.
MAX_OPERATION_BYTES = 16_000
_NOT_OFFERED = 'NOT_OFFERED'
_NO_CALL_LEFT = 'NO_CALL_LEFT'
ANSWERED, STOPPED = 'ANSWERED', 'STOPPED'
MODE = 'investigation'
_LOGGER = logging.getLogger(__name__)


def utc_now():
    return datetime.now(timezone.utc)


def new_identifier():
    return uuid.uuid4().hex


@dataclass(frozen=True)
class InvestigationSettings:
    limits: BudgetLimits = DEFAULT_LIMITS
    policy: ExpiryPolicy = field(default_factory=lambda: ExpiryPolicy(DEFAULT_INACTIVITY))
    owner: str = LOCAL_OWNER


@dataclass(frozen=True)
class Turn:
    """Ce dont une demande a besoin pour parler au modele et a Taxo, fourni par Minia."""
    ask: Callable  # ask(text) : generateur des signes d'attente, rend le texte brut du modele
    serve: Callable  # serve(exchange, step, bounded, space, exchanged) : la reponse de Taxo
    disclosure: object  # la protection de la demande : restaure ce que le modele rend
    capacity: int | None  # place du message dans la fenetre du modele, si le fournisseur la connait
    author: str = ''  # le modele qui enquete, pour attribuer ses notes


def _stage(stage, state, label, count=None):
    return 'minia.stage', {'stage': stage, 'state': state, 'label': label, 'count': count}


def guard_with(disclosure):
    """La protection existante appliquee a un texte avant conservation : secrets masques, identites
    pseudonymisees ; un texte qui fuirait encore est refuse (MiniaError)."""
    def guard(text):
        return json.loads(disclosure.protect(json.dumps({'text': text}, ensure_ascii=False)))['text']
    return guard


def _offered(describe, mip_offer):
    """Les operations proposees au modele : celles que l'echange sert, sans verdict ; la Tuile MIP si elle existe."""
    operations = [item for item in describe.get('items', [])
                  if item.get('kind') == 'operation' and item.get('operation') != 'verify_claim']
    return operations + ([mip_offer] if mip_offer else [])


class Investigations:
    """Les enquetes d'un serveur. Le stockage est ouvert a la premiere enquete (`store` ou `store_factory`) : un
    serveur ou personne n'enquete ne cree aucun fichier."""

    def __init__(self, store=None, settings: InvestigationSettings = InvestigationSettings(), clock=utc_now,
                 identifiers=new_identifier, store_factory=None):
        if (store is None) == (store_factory is None):
            raise ValueError('Un stockage des enquêtes, ou de quoi l’ouvrir, exactement.')
        self._store, self._store_factory, self._lock = store, store_factory, threading.Lock()
        self.settings, self.clock, self.identifiers = settings, clock, identifiers

    @property
    def store(self):
        with self._lock:
            if self._store is None:
                self._store = self._store_factory()
            return self._store

    def scope(self, project_id):
        return OwnerScope(self.settings.owner, project_id)

    # Ouvrir ou reprendre ----------------------------------------------------------------------------------

    def open(self, project_id, question, exchange, generation, guard, resume_question=None):
        """Une enquete nouvelle sur l'instantane de l'echange, enregistree avant tout appel au modele. Sans
        question confirmee, ou si la protection la refuse, elle n'est pas reprenable : rien de la question n'est
        conserve, et la raison est rendue."""
        now = self.clock()
        snapshot = Snapshot(exchange.snapshot['analysis'], generation, exchange.snapshot.get('commit'))
        state = InvestigationState.opened(self.identifiers(), self.scope(project_id), snapshot,
                                          self.settings.limits, self.settings.policy, now)
        not_resumable = None
        if resume_question:
            try:
                state = state.confirm_question(resume_question, True, guard, now)
            except MiniaError as exc:
                not_resumable = str(exc)
        else:
            not_resumable = 'Aucune version de la question n’a été confirmée : l’enquête ne sera pas reprenable.'
        return self.store.create(state), question, not_resumable

    def load(self, project_id, investigation_id):
        return self.store.load(investigation_id, self.scope(project_id))

    def resume(self, state, exchange, generation):
        """L'enquete enregistree, si elle se reprend sur cet instantane (`exchange` None : son analyse n'existe
        plus). Une generation changee la rend historique (STALE) : elle ne se poursuit jamais sur une autre Maille."""
        investigation_id = state.investigation_id
        if state.in_flight:
            # Un envoi annonce sans livraison inscrite : le processus s'est arrete pendant l'appel au modele.
            state = self.store.commit(investigation_id, state.revision, state.settle_in_flight())
        current = (None if exchange is None else
                   Snapshot(exchange.snapshot['analysis'], generation, exchange.snapshot.get('commit')))
        try:
            if current is None:
                raise MiniaError(INVESTIGATION_STALE, 'L’analyse de cette enquête n’existe plus : elle ne se poursuit '
                                 'pas sur une autre. Ouvrez une nouvelle enquête.')
            ensure_resumable(state.investigation, state.investigation.scope, current, self.clock())
        except MiniaError as exc:
            if exc.code == INVESTIGATION_STALE and state.investigation.status in (Status.ACTIVE, Status.PAUSED):
                self.store.commit(investigation_id, state.revision, state.move_to(Status.STALE, self.clock()))
            raise
        if state.investigation.status is Status.PAUSED:
            state = self.store.commit(investigation_id, state.revision, state.move_to(Status.ACTIVE, self.clock()))
        state.investigation.ensure_writable()
        return state, state.investigation.confirmed_question

    def view(self, project_id, investigation_id):
        """L'etat d'une enquete pour l'affichage : son carnet compact et ses livraisons, jamais un contenu."""
        state = self.store.load(investigation_id, self.scope(project_id))
        if state.investigation.expired(self.clock()):
            raise MiniaError(INVESTIGATION_EXPIRED, 'Cette enquête a expiré : elle n’est plus restituée.')
        return _summary(state)

    # Jouer ------------------------------------------------------------------------------------------------

    def run(self, state, question, exchange, mip_offer, turn: Turn, cancel=None, not_resumable=None,
            base_result=None):
        """Les tranches d'une enquete, jusqu'a la reponse du modele ou l'arret. Generateur d'evenements ; le
        dernier, `minia.completed`, porte la restitution en trois zones."""
        run = _Run(self, state, question, exchange, mip_offer, turn, cancel)
        return run.events(not_resumable, base_result or {})


def _summary(state):
    investigation = state.investigation
    return {'id': investigation.investigation_id, 'status': investigation.status.value,
            'revision': investigation.revision, 'resumable': investigation.resumable,
            'question': investigation.confirmed_question, 'expires_at': investigation.expires_at.isoformat(),
            'state': conversation.compact(state),
            'deliveries': [{'delivery_id': item.delivery_id, 'mip_reference': item.mip_reference,
                            'kind': item.kind.value, 'replay_of': item.replay_of}
                           for item in state.logbook.deliveries],
            # Ce qui est parti, ou partait, au modele sans livraison inscrite : la transmission n'est pas attestee.
            'in_flight': [{'operation': item.record.name, 'delivery_ids': list(item.record.delivery_ids)}
                          for item in state.in_flight]}


class _Run:
    """Une demande : ses tranches, sa memoire vive et ce qui attend d'etre inscrit."""

    def __init__(self, owner, state, question, exchange, mip_offer, turn, cancel):
        self.owner, self.state, self.question = owner, state, question
        self.exchange, self.mip_offer, self.turn, self.cancel = exchange, mip_offer, turn, cancel
        self.snapshot = state.investigation.snapshot
        self.operations, self.offered = [], set()
        self.shown, self.received, self.notices = [], [], []
        # Les reponses en attente d'envoi : (operation, livraison, octets). Inscrites une fois le message parti.
        self.waiting = []
        # Vrai pendant l'appel au modele : une coupure a ce moment laisse la transmission incertaine.
        self.asking = False
        # La memoire vive de la demande : reponse non source et livraison d'origine, par cle de demande.
        self.memory = {}
        self.trajectory, self.delivered = [], []
        # L'auteur d'une note : le modele qui l'a ecrite, tel que le fournisseur le nomme.
        self.author = turn.author or 'LLM'

    def events(self, not_resumable, base):
        label = 'Minia enquête dans la Maille'
        yield _stage('investigation', 'running', label, 0)
        # L'identifiant d'abord : une demande interrompue se reprend par lui, si l'enquete est reprenable.
        yield 'minia.investigation', {'id': self.state.investigation_id,
                                      'resumable': self.state.investigation.resumable}
        try:
            describe = self.exchange.call({'operation': 'describe', 'arguments': {}})
            trace.taxo('describe', {}, describe)
            self.operations = _offered(describe, self.mip_offer)
            self.offered = {item['operation'] for item in self.operations}
            final = yield from self._turns()
        except BaseException:
            self._interrupted()
            raise
        yield _stage('investigation', 'done', label, len(self.trajectory))
        yield 'minia.completed', self._result(final, not_resumable, base)

    def _turns(self):
        limits = self.state.budget.limits
        for _ in range(limits.total_operations + EXTRA_TURNS):
            calls_left = self._calls_left()
            space = self._room(calls_left)
            if space < min(ROOM_TO_CONTINUE, self._bytes_left()):
                calls_left = 0
                self.notices.append({'notice': 'CONTEXT_FULL', 'message': 'La fenêtre du modèle est presque pleine : '
                                     'réponds, ou demande une nouvelle tranche (renew).'})
            text = conversation.message(self.question, self.operations, self.state, self.shown, calls_left,
                                        self.notices)
            check(self.cancel)
            self._announce()
            self.asking = True
            raw = yield from self.turn.ask(text)
            self.asking = False
            self._sent()
            step = conversation.restored(conversation.parse_step(raw), self.turn.disclosure)
            if isinstance(step, conversation.Final) and not step.declaration.answer:
                # Une reponse vide ne clot pas l'enquete : elle ne serait plus reprenable, sans rien avoir dit.
                self.notices.append({'notice': 'EMPTY_ANSWER', 'message': 'Ta réponse est vide : réponds, ou '
                                     'poursuis l’enquête.'})
                continue
            if isinstance(step, conversation.Final):
                return step.declaration
            yield from self._act(step, calls_left, space)
            self._save()
        return None

    def _calls_left(self):
        """Les operations encore permises a la tranche, celles qui attendent d'etre inscrites comprises."""
        if self._bytes_left() < MAX_ERROR_BYTES:
            # Plus la place d'une reponse, fut-ce un refus : la tranche est epuisee en octets.
            return 0
        waiting = sum(1 for record, _, _ in self.waiting if record is not None)
        return max(0, self.state.budget.remaining_operations - waiting)

    def _bytes_left(self):
        """Les octets que la tranche et l'enquete peuvent encore recevoir, reponses en attente deduites."""
        return self.state.budget.remaining_bytes - sum(size for _, _, size in self.waiting)

    def _room(self, calls_left):
        """La place d'une reponse de Taxo : ce qui reste a la tranche, borne par operation et, si le fournisseur la
        connait, par la fenetre du modele au tour suivant."""
        room = min(MAX_OPERATION_BYTES, self._bytes_left())
        if self.turn.capacity is None:
            return room
        text = conversation.message(self.question, self.operations, self.state, self.shown, calls_left,
                                    self.notices)
        return min(room, self.turn.capacity - len(text.encode('utf-8')) - TURN_MARGIN)

    def _act(self, step, calls_left, space):
        if isinstance(step, Call):
            yield from self._call(step, calls_left, space)
        elif isinstance(step, conversation.Note):
            yield from self._note(step)
        elif isinstance(step, conversation.CloseNote):
            yield from self._close(step)
        elif isinstance(step, conversation.Renew):
            yield from self._renew(step)

    # Operations -------------------------------------------------------------------------------------------

    def _call(self, step, calls_left, space):
        if step.operation not in self.offered:
            self.notices.append({'notice': 'REFUSED', 'reason': _NOT_OFFERED, 'operation': step.operation})
            return
        if calls_left <= 0:
            self.notices.append({'notice': 'REFUSED', 'reason': _NO_CALL_LEFT,
                                 'open_branches': list(self.state.logbook.open_branches())})
            return
        key = request_key(self.snapshot.analysis_id, self.snapshot.generation_id, step.operation, step.arguments)
        remembered = self.memory.get(key)
        if remembered is not None:
            yield from self._replay(step, remembered)
            return

        def bounded(operation, arguments, room):
            request = {'operation': operation, 'arguments': arguments}
            return request if room is None else {**request, 'max_bytes': max(room, 1)}
        check(self.cancel)
        response = self.turn.serve(self.exchange, step, bounded, space, self.received)
        trace.taxo(step.operation, step.arguments, response)
        delivery = Delivery(self._delivery_id(), responses.mip_reference(step.operation, step.arguments, response),
                            responses.delivery_kind(step.operation), self.owner.clock())
        record = OperationRecord(step.operation, step.arguments,
                                 OperationOutcome.OK if response.get('outcome') == 'OK' else OperationOutcome.ERROR,
                                 delivery.at, responses.fingerprint(response), (delivery.delivery_id,),
                                 responses.not_sent(response))
        self.waiting.append((record, delivery, response.get('bytes', 0)))
        self._learn(step, response, delivery)
        self.received.append({'operation': step.operation, 'arguments': step.arguments, 'response': response})
        self.shown.append({'operation': step.operation, 'arguments': step.arguments,
                           'delivery_id': delivery.delivery_id, 'kind': delivery.kind.value, 'response': response})
        if step.operation in responses.REPLAYABLE and response.get('outcome') == 'OK':
            self.memory[key] = (response, delivery.delivery_id)
        entry = {'operation': step.operation, 'arguments': step.arguments, 'outcome': response.get('outcome'),
                 'bytes': response.get('bytes', 0), 'delivery_id': delivery.delivery_id,
                 'not_sent': list(record.not_sent), **({'error': response['error']} if 'error' in response else {})}
        self.trajectory.append(entry)
        yield 'minia.operation', entry

    def _replay(self, step, remembered):
        """La meme demande, deja servie dans cette demande : rendue depuis la memoire vive, sans nouvel appel a
        Taxo ; la nouvelle transmission est une livraison distincte, liee a l'origine (AC-18)."""
        response, origin = remembered
        delivery = Delivery(self._delivery_id(), responses.mip_reference(step.operation, step.arguments, response),
                            responses.delivery_kind(step.operation), self.owner.clock(), replay_of=origin)
        self.waiting.append((None, delivery, 0))
        self.shown.append({'operation': step.operation, 'arguments': step.arguments,
                           'delivery_id': delivery.delivery_id, 'kind': delivery.kind.value, 'replay_of': origin,
                           'response': response})
        self.notices.append({'notice': 'REPEATED', 'operation': step.operation, 'replay_of': origin,
                             'message': 'Même demande, même réponse : rejouée sans nouvel appel à Taxo.',
                             'open_branches': list(self.state.logbook.open_branches())})
        entry = {'operation': step.operation, 'arguments': step.arguments, 'outcome': 'REPLAYED',
                 'delivery_id': delivery.delivery_id, 'replay_of': origin}
        self.trajectory.append(entry)
        yield 'minia.operation', entry

    def _learn(self, step, response, delivery):
        """Ce que Taxo a rendu, inscrit au carnet (journal A) : une Tuile, un recu de code, une preuve lue."""
        at = delivery.at
        if step.operation in responses.TILE_OPERATIONS:
            parts = responses.tile_parts(response)
            if parts is not None:
                anchor, edges, frontier, expanded = parts
                self.state = self.state.record_tile(self.snapshot, anchor, edges, frontier, at=at, expanded=expanded)
        elif step.operation == responses.SOURCE_OPERATION:
            receipt = responses.source_receipt(step.arguments, response, delivery.delivery_id)
            if receipt is not None:
                self.state = self.state.record_receipt(self.snapshot, receipt, at=at)
        elif step.operation == responses.EVIDENCE_OPERATION and response.get('outcome') == 'OK':
            self.state = self.state.record_action(self.snapshot, delivery.mip_reference, Action.EVIDENCE, at=at)

    def _delivery_id(self):
        """Un identifiant jamais donne dans cette enquete : ni livre, ni porte par un recu ou une reponse en
        attente, meme apres une coupure qui a laisse un recu sans livraison."""
        logbook = self.state.logbook
        issued = ([delivery.delivery_id for delivery in logbook.deliveries]
                  + [receipt.transmission_id for receipt in logbook.receipts]
                  + [delivery.delivery_id for _, delivery, _ in self.waiting])
        numbers = [int(value[2:]) for value in issued if isinstance(value, str) and value[:2] == 'D-'
                   and value[2:].isdigit()]
        return f'D-{max(numbers, default=0) + 1}'

    def _sent(self):
        """Le message est parti et le modele a repondu : ce qu'il portait pour la premiere fois est transmis."""
        for record, delivery, size in self.waiting:
            self.state = self.state.record_delivery(self.snapshot, delivery)
            self.delivered.append(delivery)
            if record is not None:
                self.state, repetition = self.state.record_operation(self.snapshot, record, size)
                if repetition is not None:
                    self.notices.append({'notice': 'REPEATED', 'count': repetition.count,
                                         'open_branches': list(repetition.open_branches)})
        self.waiting = []
        self.state = self.state.landed()

    def _announce(self):
        """Les operations dont la reponse part avec ce message, inscrites avant l'envoi : un arret du processus
        pendant l'appel au modele laisse leur trace (INV-07, AC-06)."""
        items = [InFlight(record, size) for record, _, size in self.waiting if record is not None]
        replays = [delivery for record, delivery, _ in self.waiting if record is None]
        if items or replays:
            self.state = self.state.announce(self.snapshot, items, self.owner.clock(), replays)
            self._save()

    def _interrupted(self):
        """Une demande coupee : ce que Taxo a rendu sans etre transmis reste « obtenu, non transmis », et
        l'enquete passe en pause. L'enregistrement est tente ; s'il echoue, le dernier etat enregistre fait foi."""
        try:
            if self.asking:
                # Coupee pendant l'appel au modele : ce qui etait annonce a pu partir, sans que rien ne l'atteste.
                self.state = self.state.settle_in_flight()
            else:
                self.state = self.state.landed()
                for record, _, size in self.waiting:
                    if record is not None:
                        self.state, _ = self.state.record_operation(self.snapshot, _undelivered(record), size)
            self.waiting = []
            if self.state.investigation.status is Status.ACTIVE:
                self.state = self.state.move_to(Status.PAUSED, self.owner.clock())
            self._save()
        except MiniaError as exc:
            # L'erreur d'origine reste celle rendue : le carnet garde son dernier etat enregistre, coherent.
            _LOGGER.warning('Enquête %s non enregistrée après interruption : %s', self.state.investigation_id,
                            exc.code)

    def _save(self):
        if self.state.pending:
            self.state = self.owner.store.commit(self.state.investigation_id, self.state.revision, self.state)

    # Notes et budget --------------------------------------------------------------------------------------

    def _note(self, step):
        at, guard = self.owner.clock(), self._note_guard()
        note_id = step.note_id or f'N-{len(self.state.notes) + 1}'
        try:
            if any(note.note_id == note_id for note in self.state.notes):
                self.state = self.state.revise_note(note_id, step.text, step.nodes, guard, at, self.author)
            else:
                self.state = self.state.write_note(note_id, step.text, step.nodes, self.author, guard, at)
        except MiniaError as exc:
            if exc.code not in (NOTE_REFUSED, CONFIDENTIALITY_REFUSED):
                raise
            self.notices.append({'notice': 'NOTE_REFUSED', 'message': str(exc)})
            return
        note = next(item for item in self.state.notes if item.note_id == note_id)
        yield 'minia.note', {'note_id': note.note_id, 'version': note.version, 'status': note.status.value,
                             'nodes': list(note.nodes)}

    def _note_guard(self):
        """La protection d'une note : elle ne recopie aucune ligne du code lu dans cette demande (le code n'est jamais
        conserve, INV-10), puis la protection existante des textes."""
        disclosure, protect = self.turn.disclosure, guard_with(self.turn.disclosure)
        lines = tuple(line for item in self.received if item['operation'] == responses.SOURCE_OPERATION
                      for line in responses.source_lines(item['response']))

        def guard(text):
            if responses.copies_source(text, lines) or responses.copies_source(disclosure.restore(text), lines):
                raise MiniaError(NOTE_REFUSED, 'Une note ne recopie pas le code lu : citez le symbole.')
            return protect(text)
        return guard

    def _close(self, step):
        try:
            self.state = self.state.close_note(step.note_id, self.owner.clock())
        except MiniaError as exc:
            if exc.code != NOTE_REFUSED:
                raise
            self.notices.append({'notice': 'NOTE_REFUSED', 'message': str(exc)})
            return
        yield 'minia.note', {'note_id': step.note_id, 'status': 'CLOSED'}

    def _renew(self, step):
        # Une tranche sans la place d'un refus est epuisee : sinon le modele ne pourrait ni appeler ni continuer.
        self.state, decision = self.state.request_renewal(step.request, self.owner.clock(), MAX_ERROR_BYTES)
        data = {'granted': decision.granted, 'operations': decision.operations, 'refusal': decision.refusal,
                'branches': list(step.request.branches)}
        if decision.granted:
            # Nouvelle tranche : les reponses de la precedente ne sont pas rejouees, l'etat compact les resume.
            self.shown = []
        else:
            self.notices.append({'notice': 'RENEWAL_REFUSED', 'reason': decision.refusal,
                                 'open_branches': list(self.state.logbook.open_branches())})
        yield 'minia.renewal', data

    # Restitution ------------------------------------------------------------------------------------------

    def _result(self, final, not_resumable, base):
        """La restitution en trois zones, sans verdict : ce que Taxo a transmis, l'exploration et les notes du
        modele, ce qui reste hors perimetre ou non explore."""
        now = self.owner.clock()
        if final is not None:
            self.state = self.state.move_to(Status.COMPLETE, now)
        elif self.state.investigation.status is Status.ACTIVE:
            self.state = self.state.move_to(Status.PAUSED, now)
        self._save()
        logbook = self.state.logbook
        shown = [delivery.delivery_id for delivery in self.delivered]
        traced = declared.confronted(final, logbook, shown) if final is not None else []
        refusals = [entry for entry in self.trajectory if entry.get('outcome') not in ('OK', 'REPLAYED')]
        return {
            **base, 'mode': MODE, 'status': ANSWERED if final is not None else STOPPED,
            'question': self.question,
            'investigation': {**{key: value for key, value in _summary(self.state).items()
                                 if key in ('id', 'status', 'revision', 'resumable', 'expires_at')},
                              'not_resumable': not_resumable},
            'transmitted': [{'delivery_id': item.delivery_id, 'mip_reference': item.mip_reference,
                             'kind': item.kind.value, 'replay_of': item.replay_of} for item in self.delivered],
            'exploration': {
                'answer': final.answer if final is not None else '',
                'declared': traced,
                'declaration_malformed': bool(final is not None and final.malformed),
                'notes': [{'note_id': note.note_id, 'kind': note.kind, 'version': note.version,
                           'status': note.status.value, 'text': self.turn.disclosure.restore(note.text),
                           'nodes': list(note.nodes)} for note in self.state.notes]},
            'outside': {
                'open_branches': list(logbook.open_branches()),
                'gaps': conversation.compact(self.state)['knowledge_or_context_gaps'],
                'remaining_unknowns': list(final.remaining_unknowns) if final is not None else [],
                'refusals': refusals,
                'stopped': None if final is not None else 'Le modèle n’a pas répondu dans le nombre de tours permis.'},
            'budget': {'operations': self.state.budget.total_operations,
                       'max_operations': self.state.budget.limits.total_operations,
                       'renewals': self.state.budget.renewals, 'bytes': self.state.budget.total_bytes},
            'trajectory': self.trajectory,
        }


def _undelivered(record):
    """Une operation coupee avant l'envoi : sa reponse est obtenue, non transmise."""
    return OperationRecord(record.name, record.arguments, record.outcome, record.at, record.response_fingerprint,
                           (), record.not_sent)


def exchange_bytes(limits: BudgetLimits) -> int:
    """Le budget de l'echange du protocole : le plafond total de l'enquete, dans la limite du protocole."""
    return min(limits.total_bytes, MAX_EXCHANGE_BYTES)
