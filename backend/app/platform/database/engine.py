"""The application's database engine.

SQLite in its default journal mode lets a reader block a writer's commit, and a writer block every
reader: a portal page read during an analysis failed with « database is locked », and so did the
analysis. In WAL mode readers and the writer no longer block each other; two writers still take
turns, waiting up to 30 seconds instead of 5.
"""
from sqlalchemy import create_engine, event

SQLITE_WAIT_SECONDS = 30


def database_engine(url):
    if not url.startswith('sqlite'):
        return create_engine(url)
    engine = create_engine(url, connect_args={'timeout': SQLITE_WAIT_SECONDS})

    @event.listens_for(engine, 'connect')
    def _write_ahead_log(connection, _):
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.close()

    return engine
