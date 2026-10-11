"""Le scenario de reference du recit TAXO-MINIA-ENQUETE-01 (§ 5) et un stockage en memoire pour le contrat du port.

L'arbre suit l'inscription a un cours du depot de demonstration Java : un controleur, un service, trois appels,
deux repositories. Les references ont la forme des symboles de Taxo ; les echanges avec le modele sont simules.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.minia.domain.errors import INVESTIGATION_CONFLICT, INVESTIGATION_NOT_FOUND, MiniaError
from app.minia.domain.investigation.budget import BudgetLimits
from app.minia.domain.investigation.codec import event_to_document, from_document, to_document
from app.minia.domain.investigation.identity import ExpiryPolicy, OwnerScope, Snapshot, Status
from app.minia.domain.investigation.logbook import Edge
from app.minia.domain.investigation.state import InvestigationState

T0 = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
PACKAGE = 'com.example.school'


def method(owner, name):
    return f'method:{PACKAGE}.{owner}#{name}()'


CONTROLLER = method('controller.EnrollmentController', 'enroll')
SERVICE = method('service.EnrollmentService', 'enroll')
FIND_STUDENT = method('service.StudentService', 'findStudent')
FIND_COURSE = method('service.CourseService', 'findCourse')
SAVE = method('repository.EnrollmentRepository', 'save')
STUDENT_BY_ID = method('repository.StudentRepository', 'findById')
COURSE_BY_ID = method('repository.CourseRepository', 'findById')

SNAPSHOT = Snapshot('analysis-1', 7, 'c0ffee')
OTHER_GENERATION = Snapshot('analysis-1', 8, 'c0ffee')
ALICE = OwnerScope('alice', 'project-school')
BOB = OwnerScope('bob', 'project-other')
LIMITS = BudgetLimits(slice_operations=8, slice_bytes=64_000, total_operations=24, total_bytes=192_000,
                      max_renewals=2)
POLICY = ExpiryPolicy(timedelta(days=7))


def calls(source, *targets):
    return tuple(Edge(source, 'CALLS', target, f'occ:{source}->{target}') for target in targets)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def allow(text):
    return text


def opened(investigation_id='inv-1', scope=ALICE, snapshot=SNAPSHOT, limits=LIMITS):
    return InvestigationState.opened(investigation_id, scope, snapshot, limits, POLICY, T0)


def explored_two_of_three(state=None):
    """Le parcours du § 5 jusqu'a l'etape 5 : deux branches du service explorees, la troisieme laissee."""
    state = state or opened()
    state = state.record_tile(SNAPSHOT, CONTROLLER, calls(CONTROLLER, SERVICE), at=at(1))
    state = state.record_tile(SNAPSHOT, SERVICE, calls(SERVICE, FIND_STUDENT, FIND_COURSE, SAVE), at=at(2))
    state = state.record_tile(SNAPSHOT, FIND_STUDENT, calls(FIND_STUDENT, STUDENT_BY_ID), at=at(3))
    return state.record_tile(SNAPSHOT, FIND_COURSE, calls(FIND_COURSE, COURSE_BY_ID), at=at(4))


class InMemoryStore:
    """Un stockage de test qui suit le contrat du port : documents serialises, revision controlee, journal
    append-only. Il garde des documents, pas des objets, pour que la relecture passe par le codec."""

    def __init__(self):
        self.states, self.scopes, self.events = {}, {}, {}

    def create(self, state):
        if state.investigation_id in self.states:
            raise MiniaError(INVESTIGATION_CONFLICT, 'Cette enquête existe déjà.')
        return self._write(state, 1)

    def load(self, investigation_id, scope):
        if self.scopes.get(investigation_id) != scope:
            raise MiniaError(INVESTIGATION_NOT_FOUND, 'Enquête introuvable.')
        return from_document(self.states[investigation_id])

    def commit(self, investigation_id, expected_revision, new_state):
        if investigation_id != new_state.investigation_id or investigation_id not in self.states:
            raise MiniaError(INVESTIGATION_NOT_FOUND, 'Enquête introuvable.')
        if self.states[investigation_id]['investigation']['revision'] != expected_revision:
            raise MiniaError(INVESTIGATION_CONFLICT, 'Une autre écriture est passée : rechargez l’enquête.')
        return self._write(new_state, expected_revision + 1)

    def mark_status(self, investigation_id, scope, status, expected_revision, at):
        state = self.load(investigation_id, scope)
        return self.commit(investigation_id, expected_revision, state.move_to(status, at))

    def expire(self, now, limit):
        expired = 0
        for investigation_id, document in self.states.items():
            if expired >= limit:
                break
            state = from_document(document)
            if state.investigation.status is not Status.EXPIRED and state.investigation.expires_at <= now:
                self.commit(investigation_id, state.revision, state.move_to(Status.EXPIRED, now))
                expired += 1
        return expired

    def _write(self, state, revision):
        written = state.committed(revision)
        self.events.setdefault(state.investigation_id, []).extend(event_to_document(e) for e in state.pending)
        self.states[state.investigation_id] = to_document(written)
        self.scopes[state.investigation_id] = state.investigation.scope
        return written


def without_pending(state):
    return replace(state, pending=())
