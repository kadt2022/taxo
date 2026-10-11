"""Le carnet des enquetes de Minia dans un fichier SQLite en mode WAL (recit TAXO-MINIA-ENQUETE-01, lot B).

Seule realisation du port `ParcoursMemoryStore` : un fichier propre a Minia, distinct de la base des analyses, deux
tables (`minia_investigations`, l'etat courant compact et versionne ; `minia_investigation_events`, le journal
append-only). Chaque ecriture passe l'etat et ses evenements dans une seule transaction `BEGIN IMMEDIATE`, sous
controle de revision : une ecriture concurrente partie de la meme revision est refusee, rien n'est ecrit.

Le WAL laisse lire pendant qu'on ecrit, mais SQLite garde **un seul ecrivain a la fois** : une ecriture attend le
verrou au plus `busy_timeout`, puis echoue explicitement. Le schema a sa version (`PRAGMA user_version`) : un
fichier d'une version inconnue est refuse, jamais lu au hasard. L'etat porte son empreinte : un etat altere n'est
pas restitue.

Une suppression ou une expiration est logique : les anciennes pages du fichier, du WAL ou d'une sauvegarde ne
sont pas effacees physiquement a l'instant. Le carnet ne garde donc que des donnees minimisees (aucun code source,
aucun message complet du modele).
"""
import hashlib
import json
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime, timezone

from app.minia.domain.errors import (INVESTIGATION_CONFLICT, INVESTIGATION_INVALID, INVESTIGATION_NOT_FOUND,
                                     MiniaError)
from app.minia.domain.investigation.codec import event_to_document, from_document, to_document
from app.minia.domain.investigation.identity import Status

SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000
_NOT_FOUND = 'Enquête introuvable.'

# Chaque migration amene le fichier de la version d'indice a la suivante ; elles ne se modifient jamais apres
# publication, une nouvelle version en ajoute une.
_MIGRATIONS = (
    """
    CREATE TABLE minia_investigations (
        investigation_id TEXT PRIMARY KEY,
        owner TEXT NOT NULL,
        project_id TEXT NOT NULL,
        status TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision > 0),
        expires_at TEXT NOT NULL,
        state TEXT NOT NULL,
        state_sha256 TEXT NOT NULL
    );
    CREATE INDEX minia_investigations_expiry ON minia_investigations (status, expires_at);
    CREATE TABLE minia_investigation_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        investigation_id TEXT NOT NULL REFERENCES minia_investigations (investigation_id) ON DELETE CASCADE,
        revision INTEGER NOT NULL,
        kind TEXT NOT NULL,
        at TEXT NOT NULL,
        data TEXT NOT NULL
    );
    CREATE INDEX minia_investigation_events_by_investigation
        ON minia_investigation_events (investigation_id, event_id);
    """,
)


def _utc(moment: datetime) -> str:
    """Une date en UTC, toujours de meme forme : les echeances se comparent comme des chaines."""
    return moment.astimezone(timezone.utc).isoformat(timespec='microseconds')


def _written(state) -> tuple[str, str]:
    text = json.dumps(to_document(state), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return text, hashlib.sha256(text.encode('utf-8')).hexdigest()


class SqliteParcoursMemoryStore:
    def __init__(self, path, busy_timeout_ms: int = BUSY_TIMEOUT_MS):
        self._path = str(path)
        self._busy_timeout_ms = busy_timeout_ms
        with self._connection() as connection:
            mode = connection.execute('PRAGMA journal_mode=WAL').fetchone()[0]
            if str(mode).lower() != 'wal':
                raise MiniaError(INVESTIGATION_INVALID, 'Le carnet des enquêtes exige le mode WAL de SQLite.')
            self._migrate(connection)

    # Port --------------------------------------------------------------------------------------------------

    def create(self, state):
        written = state.committed(1)
        text, digest = _written(written)
        investigation = written.investigation
        with self._transaction() as connection:
            try:
                connection.execute(
                    'INSERT INTO minia_investigations (investigation_id, owner, project_id, status, revision, '
                    'expires_at, state, state_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (investigation.investigation_id, investigation.scope.owner, investigation.scope.project_id,
                     str(investigation.status), 1, _utc(investigation.expires_at), text, digest))
            except sqlite3.IntegrityError as exc:
                raise MiniaError(INVESTIGATION_CONFLICT, 'Cette enquête existe déjà.') from exc
            self._append(connection, investigation.investigation_id, 1, state.pending)
        return written

    def load(self, investigation_id, scope):
        with self._connection() as connection:
            row = connection.execute(
                'SELECT state, state_sha256 FROM minia_investigations '
                'WHERE investigation_id = ? AND owner = ? AND project_id = ?',
                (investigation_id, scope.owner, scope.project_id)).fetchone()
        if row is None:
            raise MiniaError(INVESTIGATION_NOT_FOUND, _NOT_FOUND)
        return self._read(*row)

    def commit(self, investigation_id, expected_revision, new_state):
        if new_state.investigation_id != investigation_id:
            raise MiniaError(INVESTIGATION_INVALID, 'L’état écrit n’est pas celui de cette enquête.')
        revision = expected_revision + 1
        written = new_state.committed(revision)
        text, digest = _written(written)
        investigation = written.investigation
        with self._transaction() as connection:
            updated = connection.execute(
                'UPDATE minia_investigations SET status = ?, revision = ?, expires_at = ?, state = ?, '
                'state_sha256 = ? WHERE investigation_id = ? AND owner = ? AND project_id = ? AND revision = ?',
                (str(investigation.status), revision, _utc(investigation.expires_at), text, digest,
                 investigation_id, investigation.scope.owner, investigation.scope.project_id,
                 expected_revision)).rowcount
            if updated != 1:
                self._refuse(connection, investigation_id, investigation.scope)
            self._append(connection, investigation_id, revision, new_state.pending)
        return written

    def mark_status(self, investigation_id, scope, status, expected_revision, at):
        state = self.load(investigation_id, scope)
        return self.commit(investigation_id, expected_revision, state.move_to(status, at))

    def expire(self, now, limit):
        if limit <= 0:
            return 0
        with self._transaction() as connection:
            rows = connection.execute(
                'SELECT state, state_sha256 FROM minia_investigations WHERE status != ? AND expires_at <= ? '
                'ORDER BY expires_at, investigation_id LIMIT ?', (str(Status.EXPIRED), _utc(now), limit)).fetchall()
            for row in rows:
                state = self._read(*row)
                expired = state.move_to(Status.EXPIRED, now)
                revision = state.revision + 1
                written = expired.committed(revision)
                text, digest = _written(written)
                connection.execute(
                    'UPDATE minia_investigations SET status = ?, revision = ?, state = ?, state_sha256 = ? '
                    'WHERE investigation_id = ?',
                    (str(Status.EXPIRED), revision, text, digest, state.investigation_id))
                self._append(connection, state.investigation_id, revision, expired.pending)
        return len(rows)

    def events(self, investigation_id, scope):
        """Le journal d'une enquete, dans l'ordre d'ecriture : pour l'audit et les tests, jamais pour restaurer."""
        self.load(investigation_id, scope)
        with self._connection() as connection:
            rows = connection.execute(
                'SELECT revision, kind, at, data FROM minia_investigation_events WHERE investigation_id = ? '
                'ORDER BY event_id', (investigation_id,)).fetchall()
        return [{'revision': revision, 'kind': kind, 'at': at, 'data': json.loads(data)}
                for revision, kind, at, data in rows]

    # Interne -----------------------------------------------------------------------------------------------

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self._path, timeout=self._busy_timeout_ms / 1000, isolation_level=None)
        with closing(connection):
            connection.execute(f'PRAGMA busy_timeout = {int(self._busy_timeout_ms)}')
            connection.execute('PRAGMA foreign_keys = ON')
            yield connection

    @contextmanager
    def _transaction(self):
        """Une transaction d'ecriture : le verrou d'ecrivain est pris des le debut, tout est annule sur erreur."""
        with self._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as exc:
                raise MiniaError(INVESTIGATION_CONFLICT, 'Le carnet est occupé par une autre écriture : '
                                 'réessayez.') from exc
            try:
                yield connection
            except BaseException:
                connection.execute('ROLLBACK')
                raise
            connection.execute('COMMIT')

    def _migrate(self, connection):
        """Chaque etape sous le verrou d'ecrivain, la version relue une fois le verrou pris : deux processus qui
        ouvrent ensemble un carnet neuf n'appliquent jamais deux fois la meme migration."""
        while True:
            connection.execute('BEGIN IMMEDIATE')
            try:
                version = connection.execute('PRAGMA user_version').fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise MiniaError(INVESTIGATION_INVALID, f'Le carnet des enquêtes est au schéma {version}, plus '
                                     f'récent que celui de cette version de Taxo ({SCHEMA_VERSION}) : il n’est pas '
                                     'ouvert.')
                if version == SCHEMA_VERSION:
                    connection.execute('COMMIT')
                    return
                for statement in _MIGRATIONS[version].split(';'):
                    if statement.strip():
                        connection.execute(statement)
                connection.execute(f'PRAGMA user_version = {version + 1}')
            except BaseException:
                connection.execute('ROLLBACK')
                raise
            connection.execute('COMMIT')

    @staticmethod
    def _append(connection, investigation_id, revision, events):
        connection.executemany(
            'INSERT INTO minia_investigation_events (investigation_id, revision, kind, at, data) '
            'VALUES (?, ?, ?, ?, ?)',
            [(investigation_id, revision, document['kind'], document['at'],
              json.dumps(document['data'], ensure_ascii=False, sort_keys=True))
             for document in map(event_to_document, events)])

    @staticmethod
    def _refuse(connection, investigation_id, scope):
        """Pourquoi une ecriture n'a touche aucune ligne : une autre revision, ou une enquete absente de ce
        perimetre (dite introuvable, sans dire si elle existe ailleurs)."""
        found = connection.execute('SELECT 1 FROM minia_investigations WHERE investigation_id = ? AND owner = ? '
                                   'AND project_id = ?', (investigation_id, scope.owner, scope.project_id)).fetchone()
        if found is None:
            raise MiniaError(INVESTIGATION_NOT_FOUND, _NOT_FOUND)
        raise MiniaError(INVESTIGATION_CONFLICT, 'Une autre écriture est passée : rechargez l’enquête.')

    @staticmethod
    def _read(text, digest):
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != digest:
            raise MiniaError(INVESTIGATION_INVALID, 'Le carnet enregistré a été altéré : il n’est pas restitué.')
        try:
            document = json.loads(text)
        except ValueError as exc:
            raise MiniaError(INVESTIGATION_INVALID, 'Le carnet enregistré est illisible.') from exc
        return from_document(document)
