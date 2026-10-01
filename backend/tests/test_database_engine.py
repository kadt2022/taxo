"""SQLite readers and the analysis writer must not block each other (« database is locked »)."""
import sqlite3
import time

from sqlalchemy import text

from app.platform.database.engine import SQLITE_WAIT_SECONDS, database_engine


def test_sqlite_uses_the_write_ahead_log(tmp_path):
    engine = database_engine(f'sqlite:///{tmp_path / "taxo.db"}')
    with engine.connect() as connection:
        assert connection.scalar(text('PRAGMA journal_mode')) == 'wal'
        assert connection.scalar(text('PRAGMA busy_timeout')) == SQLITE_WAIT_SECONDS * 1000
    engine.dispose()


def test_a_writer_commits_while_a_reader_keeps_its_transaction_open(tmp_path):
    path = tmp_path / 'taxo.db'
    engine = database_engine(f'sqlite:///{path}')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE facts (id INTEGER PRIMARY KEY)'))
        connection.execute(text('INSERT INTO facts VALUES (1)'))
    # A long portal read: an explicit read transaction, as SQLite holds it during a large query.
    reader = sqlite3.connect(path, timeout=0.2, isolation_level=None)
    reader.execute('BEGIN')
    assert reader.execute('SELECT count(*) FROM facts').fetchone() == (1,)
    started = time.monotonic()
    with engine.begin() as writer:
        writer.execute(text('INSERT INTO facts VALUES (2)'))  # without WAL: waits on the reader, then fails
    assert time.monotonic() - started < 1
    assert reader.execute('SELECT count(*) FROM facts').fetchone() == (1,)  # the reader keeps its snapshot
    reader.execute('COMMIT')
    assert reader.execute('SELECT count(*) FROM facts').fetchone() == (2,)
    reader.close()
    engine.dispose()


def test_other_databases_are_left_as_they_are():
    engine = database_engine('postgresql+psycopg://taxo@localhost/taxo')
    assert engine.dialect.name == 'postgresql'
