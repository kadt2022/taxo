"""Le carnet des enquetes sur SQLite en mode WAL (recit TAXO-MINIA-ENQUETE-01, lot B) : contrat du port, reprise
apres redemarrage, ecritures concurrentes, incident au milieu d'une ecriture, schema et integrite."""
import sqlite3
import subprocess
import sys
import textwrap
import threading
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from app.minia.domain.errors import (INVESTIGATION_CONFLICT, INVESTIGATION_EXPIRED, INVESTIGATION_INVALID,
                                     INVESTIGATION_NOT_FOUND, MiniaError)
from app.minia.domain.investigation import codec
from app.minia.domain.investigation.identity import Status, ensure_resumable
from app.minia.domain.investigation.logbook import (Delivery, DeliveryKind, OperationOutcome, OperationRecord,
                                                    ReceiptStatus, SourceReceipt)
from app.minia.infrastructure import investigation_store
from app.minia.infrastructure.investigation_store import SCHEMA_VERSION, SqliteParcoursMemoryStore

from investigation_scenarios import (ALICE, BOB, SAVE, SERVICE, SNAPSHOT, allow, at, explored_two_of_three,
                                     opened)
from investigation_store_contract import StoreContract

BACKEND = Path(__file__).parents[1]


class TestSqliteStore(StoreContract):
    @pytest.fixture
    def store(self, tmp_path):
        return SqliteParcoursMemoryStore(tmp_path / 'investigations.sqlite3')


@pytest.fixture
def path(tmp_path):
    return tmp_path / 'investigations.sqlite3'


def resumable_state():
    state = explored_two_of_three().confirm_question('Comment fonctionne l’inscription ?', True, allow, at(5))
    state = state.record_receipt(SNAPSHOT, SourceReceipt(SERVICE, 'tx-1', ReceiptStatus.DELIVERED, 'CODE_SOURCE',
                                                         'sha256:ab'), at=at(6))
    state = state.record_delivery(SNAPSHOT, Delivery('D-1', SERVICE, DeliveryKind.SOURCE, at(6)))
    state, _ = state.record_operation(SNAPSHOT, OperationRecord('get_source', {'reference': SERVICE},
                                                                OperationOutcome.OK, at(6), 'h', ('D-1',)), 3000)
    return state.write_note('n1', 'Le service cherche l’étudiant puis le cours.', [SERVICE], 'model-x', allow, at(7))


def test_the_file_is_in_wal_mode_with_its_schema_version(path):
    SqliteParcoursMemoryStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert connection.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {'minia_investigations', 'minia_investigation_events'} <= tables


def test_reopening_an_existing_file_keeps_its_content(path):
    SqliteParcoursMemoryStore(path).create(opened())
    assert SqliteParcoursMemoryStore(path).load('inv-1', ALICE).investigation.investigation_id == 'inv-1'


def test_save_interrupt_restore_is_exact_after_restart(path):
    """AC-05 : question confirmee, frontiere, visites, notes, statuts, recus et budget identiques apres un
    redemarrage ; aucun texte source n'est restitue."""
    written = SqliteParcoursMemoryStore(path).create(resumable_state())

    restored = SqliteParcoursMemoryStore(path).load('inv-1', ALICE)

    assert restored == written
    ensure_resumable(restored.investigation, ALICE, SNAPSHOT, at(8))
    assert restored.investigation.confirmed_question == 'Comment fonctionne l’inscription ?'
    assert restored.logbook.open_branches() == written.logbook.open_branches()
    assert restored.budget == written.budget
    assert (restored.notes[0].text, restored.notes[0].status) == (written.notes[0].text, written.notes[0].status)


def test_nothing_but_metadata_is_written(path):
    """INV-10 : ni code, ni question brute : seulement l'etat minimise et le journal."""
    SqliteParcoursMemoryStore(path).create(resumable_state())
    with sqlite3.connect(path) as connection:
        state = connection.execute('SELECT state FROM minia_investigations').fetchone()[0]
        events = ' '.join(row[0] for row in connection.execute('SELECT data FROM minia_investigation_events'))
    for written in (state, events):
        assert 'public Enrollment enroll' not in written
    assert 'Comment fonctionne' not in events


def test_state_and_events_are_written_together(path):
    store = SqliteParcoursMemoryStore(path)
    created = store.create(opened())
    store.commit('inv-1', 1, created.record_tile(SNAPSHOT, SERVICE, (), at=at(1)))

    events = store.events('inv-1', ALICE)

    assert [(event['revision'], event['kind']) for event in events] == [(1, 'OPENED'), (2, 'TILE')]
    with pytest.raises(MiniaError):
        store.events('inv-1', BOB)


def test_a_failure_in_the_middle_of_a_write_leaves_the_previous_state(path, monkeypatch):
    """AC-06 : une erreur apres l'ecriture de l'etat, avant celle du journal, annule toute la transaction."""
    store = SqliteParcoursMemoryStore(path)
    created = store.create(opened())

    def broken(_events):
        raise RuntimeError('incident simulé')
    monkeypatch.setattr(investigation_store, 'event_to_document', broken)
    with pytest.raises(RuntimeError):
        store.commit('inv-1', 1, created.record_tile(SNAPSHOT, SERVICE, (), at=at(1)))
    monkeypatch.undo()

    assert store.load('inv-1', ALICE) == created
    assert [event['kind'] for event in store.events('inv-1', ALICE)] == ['OPENED']


def test_a_process_killed_before_commit_writes_nothing(path):
    """AC-06 : un processus tue au milieu d'une transaction ne laisse aucune trace de l'ecriture interrompue."""
    store = SqliteParcoursMemoryStore(path)
    created = store.create(opened())
    script = textwrap.dedent(f'''
        import os, sqlite3
        connection = sqlite3.connect({str(path)!r}, isolation_level=None)
        connection.execute('BEGIN IMMEDIATE')
        connection.execute("UPDATE minia_investigations SET revision = 99, status = 'COMPLETE'")
        connection.execute("INSERT INTO minia_investigation_events (investigation_id, revision, kind, at, data) "
                           "VALUES ('inv-1', 99, 'OPERATION', 'x', '{{}}')")
        os._exit(17)
    ''')
    killed = subprocess.run([sys.executable, '-c', script], cwd=BACKEND, check=False, timeout=60)
    assert killed.returncode == 17

    reopened = SqliteParcoursMemoryStore(path)
    assert reopened.load('inv-1', ALICE) == created
    assert [event['kind'] for event in reopened.events('inv-1', ALICE)] == ['OPENED']


def test_concurrent_writers_from_the_same_revision_only_one_wins(path):
    """Deux ecrivains partis de la meme revision : l'un passe, l'autre est refuse ; aucun etat melange."""
    created = SqliteParcoursMemoryStore(path).create(opened())
    outcomes, barrier = [], threading.Barrier(2)

    def write(node, minutes):
        store = SqliteParcoursMemoryStore(path)
        barrier.wait()
        try:
            store.commit('inv-1', 1, created.record_tile(SNAPSHOT, node, (), at=at(minutes)))
            outcomes.append(('ok', node))
        except MiniaError as error:
            outcomes.append((error.code, node))

    threads = [threading.Thread(target=write, args=(node, minutes)) for node, minutes in ((SERVICE, 1), (SAVE, 2))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(code for code, _ in outcomes) == [INVESTIGATION_CONFLICT, 'ok']
    winner = next(node for code, node in outcomes if code == 'ok')
    loaded = SqliteParcoursMemoryStore(path).load('inv-1', ALICE)
    assert set(loaded.logbook.visited) == {winner} and loaded.revision == 2


def test_a_writer_waiting_beyond_the_busy_timeout_fails_explicitly(path):
    store = SqliteParcoursMemoryStore(path, busy_timeout_ms=50)
    created = store.create(opened())
    holder = sqlite3.connect(path, isolation_level=None)
    holder.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(MiniaError) as error:
            store.commit('inv-1', 1, created.record_tile(SNAPSHOT, SERVICE, (), at=at(1)))
        assert error.value.code == INVESTIGATION_CONFLICT
        assert store.load('inv-1', ALICE) == created
    finally:
        holder.execute('ROLLBACK')
        holder.close()


def test_two_investigations_of_different_scopes_never_mix(path):
    """AC-07 : enquetes concurrentes de perimetres distincts, aucun melange de references ou de notes."""
    store = SqliteParcoursMemoryStore(path)
    alice = store.create(resumable_state())
    bob = store.create(opened('inv-2', BOB).record_tile(SNAPSHOT, SAVE, (), at=at(1)))

    assert store.load('inv-1', ALICE) == alice and store.load('inv-2', BOB) == bob
    for investigation_id, scope in (('inv-1', BOB), ('inv-2', ALICE)):
        with pytest.raises(MiniaError) as error:
            store.load(investigation_id, scope)
        assert error.value.code == INVESTIGATION_NOT_FOUND
    with pytest.raises(MiniaError) as error:
        store.commit('inv-1', 1, bob.record_tile(SNAPSHOT, SERVICE, (), at=at(2)))
    assert error.value.code == INVESTIGATION_INVALID
    changed = alice.record_tile(SNAPSHOT, SAVE, (), at=at(9))
    forged = replace(changed, investigation=replace(changed.investigation, investigation_id='inv-2'))
    with pytest.raises(MiniaError) as error:
        store.commit('inv-2', 1, forged)
    assert error.value.code == INVESTIGATION_NOT_FOUND
    assert store.load('inv-2', BOB) == bob


def test_expired_investigation_is_never_restored(path):
    """AC-16 : expiree, l'enquete est refusee a la reprise, avant comme apres le nettoyage."""
    store = SqliteParcoursMemoryStore(path)
    store.create(resumable_state())
    later = at(7) + timedelta(days=7)

    with pytest.raises(MiniaError) as error:
        ensure_resumable(store.load('inv-1', ALICE).investigation, ALICE, SNAPSHOT, later)
    assert error.value.code == INVESTIGATION_EXPIRED
    assert store.expire(later, limit=10) == 1
    assert store.load('inv-1', ALICE).investigation.status is Status.EXPIRED
    assert store.expire(later, limit=10) == 0
    assert store.expire(later, limit=0) == 0


def test_a_tampered_state_is_not_restored(path):
    store = SqliteParcoursMemoryStore(path)
    store.create(resumable_state())
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE minia_investigations SET state = replace(state, 'model-x', 'model-y')")

    with pytest.raises(MiniaError) as error:
        store.load('inv-1', ALICE)
    assert error.value.code == INVESTIGATION_INVALID


def test_a_document_of_another_version_is_not_restored(path, monkeypatch):
    store = SqliteParcoursMemoryStore(path)
    monkeypatch.setattr(codec, 'SCHEMA_VERSION', codec.SCHEMA_VERSION + 1)
    store.create(opened())
    monkeypatch.undo()

    with pytest.raises(MiniaError) as error:
        store.load('inv-1', ALICE)
    assert error.value.code == INVESTIGATION_INVALID


def test_a_file_from_a_newer_schema_is_refused(path):
    with sqlite3.connect(path) as connection:
        connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION + 1}')

    with pytest.raises(MiniaError) as error:
        SqliteParcoursMemoryStore(path)
    assert error.value.code == INVESTIGATION_INVALID
