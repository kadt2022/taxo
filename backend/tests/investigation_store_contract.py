"""Le contrat du port `ParcoursMemoryStore` (recit TAXO-MINIA-ENQUETE-01, § 6.3), pour toute realisation.

Une classe de test herite de `StoreContract` et fournit la fixture `store`. Le lot A l'applique au stockage de
test en memoire ; l'adaptateur SQLite du lot B la reprend telle quelle.
"""
from datetime import timedelta

import pytest

from app.minia.domain.errors import INVESTIGATION_CONFLICT, INVESTIGATION_NOT_FOUND, MiniaError
from app.minia.domain.investigation.identity import Status

from investigation_scenarios import (ALICE, BOB, FIND_STUDENT, SAVE, SERVICE, SNAPSHOT, allow, at,
                                     explored_two_of_three, opened)


class StoreContract:
    def test_create_then_load_restores_the_exact_state(self, store):
        state = explored_two_of_three(opened()).confirm_question('Comment ?', True, allow, at(5))
        state = state.write_note('n1', 'Hypothèse', [SERVICE], 'm', allow, at(6))

        written = store.create(state)
        loaded = store.load(state.investigation_id, ALICE)

        assert written.revision == 1 and written.pending == ()
        assert loaded == written

    def test_create_refuses_an_existing_identifier(self, store):
        store.create(opened())
        with pytest.raises(MiniaError) as error:
            store.create(opened())
        assert error.value.code == INVESTIGATION_CONFLICT

    def test_commit_advances_the_revision(self, store):
        written = store.create(opened())
        changed = written.record_tile(SNAPSHOT, SERVICE, (), at=at(1))

        committed = store.commit(written.investigation_id, written.revision, changed)

        assert committed.revision == 2
        assert store.load(written.investigation_id, ALICE) == committed

    def test_a_stale_revision_is_refused_and_nothing_is_written(self, store):
        """Deux ecritures concurrentes : la seconde, partie de la meme revision, est refusee."""
        written = store.create(opened())
        first = store.commit(written.investigation_id, 1, written.record_tile(SNAPSHOT, SERVICE, (), at=at(1)))

        with pytest.raises(MiniaError) as error:
            store.commit(written.investigation_id, 1, written.record_tile(SNAPSHOT, SAVE, (), at=at(2)))

        assert error.value.code == INVESTIGATION_CONFLICT
        assert store.load(written.investigation_id, ALICE) == first

    def test_another_scope_cannot_load_and_learns_nothing(self, store):
        """AC-07 : deux enquetes de perimetres distincts ne se melangent pas ; l'acces croise est refuse sans dire
        si l'enquete existe."""
        store.create(opened('inv-a', ALICE))
        store.create(opened('inv-b', BOB).record_tile(SNAPSHOT, FIND_STUDENT, (), at=at(1)))

        with pytest.raises(MiniaError) as crossed:
            store.load('inv-a', BOB)
        with pytest.raises(MiniaError) as missing:
            store.load('inv-z', BOB)

        assert crossed.value.code == missing.value.code == INVESTIGATION_NOT_FOUND
        assert str(crossed.value) == str(missing.value)
        assert store.load('inv-a', ALICE).logbook.visited == {}
        assert FIND_STUDENT in store.load('inv-b', BOB).logbook.visited

    def test_mark_status_is_checked_by_revision(self, store):
        written = store.create(opened())

        paused = store.mark_status(written.investigation_id, ALICE, Status.PAUSED, 1, at(1))

        assert paused.investigation.status is Status.PAUSED and paused.revision == 2
        with pytest.raises(MiniaError):
            store.mark_status(written.investigation_id, ALICE, Status.ACTIVE, 1, at(2))

    def test_expire_marks_only_inactive_investigations_up_to_the_limit(self, store):
        for index in range(3):
            store.create(opened(f'old-{index}'))
        store.create(opened('recent').record_tile(SNAPSHOT, SERVICE, (), at=at(60 * 24 * 6)))
        now = at(0) + timedelta(days=8)

        assert store.expire(now, limit=2) == 2
        assert store.expire(now, limit=10) == 1
        statuses = {name: store.load(name, ALICE).investigation.status
                    for name in ('old-0', 'old-1', 'old-2', 'recent')}
        assert statuses == {'old-0': Status.EXPIRED, 'old-1': Status.EXPIRED, 'old-2': Status.EXPIRED,
                            'recent': Status.ACTIVE}
