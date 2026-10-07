"""The database schema the code expects, checked before the application serves anything.

`taxo-console.bat` and the Docker image run `alembic upgrade head` before starting the API, but an API restarted
on its own after the code changed skips that step. The code then reads columns the database does not have yet, and
every page reading them fails with an error 500 (TAXO-01K added three evidence columns in migration 009). Refusing
to start says what to do instead.

Only a database managed by migrations is checked: one without an `alembic_version` table (created from the ORM
mappings, as the tests do) has no revision to compare.
"""
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

MIGRATIONS = Path(__file__).resolve().parents[3] / 'migrations'
VERSION_TABLE = 'alembic_version'


class SchemaOutOfDate(RuntimeError):
    """The database is not at the revision the code expects."""


def expected_revisions(migrations=MIGRATIONS):
    """The head revisions of the migration scripts shipped with the code."""
    return set(_scripts(migrations).get_heads())


def known_revisions(migrations=MIGRATIONS):
    """Every revision of the migration scripts shipped with the code."""
    return {script.revision for script in _scripts(migrations).walk_revisions()}


def current_revisions(engine):
    """The revisions recorded in the database, or None when it is not managed by migrations."""
    with engine.connect() as connection:
        if not inspect(connection).has_table(VERSION_TABLE):
            return None
        return set(MigrationContext.configure(connection).get_current_heads())


def require_current_schema(engine, migrations=MIGRATIONS):
    """Fails when a database managed by migrations is not at the revision of the code."""
    current = current_revisions(engine)
    if current is None:
        return
    expected = expected_revisions(migrations)
    if current == expected:
        return
    unknown = current - known_revisions(migrations)
    if unknown:
        # Une base migree par un code plus recent : `alembic upgrade head` ne connait pas sa revision.
        raise SchemaOutOfDate(
            f'La base de données est à la révision {_names(unknown)}, inconnue de ce code (qui attend '
            f'{_names(expected)}) : elle a été migrée par une version plus récente. Démarrez l’API avec cette '
            'version, ou restaurez une sauvegarde de la base compatible avec ce code.')
    raise SchemaOutOfDate(
        f'La base de données est à la révision {_names(current)}, le code attend {_names(expected)}. '
        'Appliquez les migrations avant de démarrer l’API : `alembic upgrade head` dans backend/, '
        'ou relancez taxo-console.bat, qui le fait au démarrage.')


def _scripts(migrations):
    config = Config()
    config.set_main_option('script_location', str(migrations))
    return ScriptDirectory.from_config(config)


def _names(revisions):
    return ', '.join(sorted(revisions)) or 'aucune'
