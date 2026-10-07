"""Migration 009 (TAXO-01K): evidence gains the span and role of a call site, existing proofs stay as they were."""
import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text

COLUMNS = {'column_start', 'column_end', 'role'}


def test_migration_009_adds_the_call_site_columns_and_downgrades(tmp_path):
    url = f'sqlite:///{tmp_path / "call_sites.db"}'
    env = {**os.environ, 'DATABASE_URL': url}

    def migrate(action, target):
        subprocess.run([sys.executable, '-m', 'alembic', action, target], check=True, env=env, capture_output=True)

    def columns():
        return {column['name'] for column in inspect(engine).get_columns('fact_evidence')}

    migrate('upgrade', '008')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO fact_evidence (occurrence, position, path, line_start, line_end, method) "
                        "VALUES (1, 0, 'A.java', 3, 3, 'fixture')"))
    assert not columns() & COLUMNS
    migrate('upgrade', '009')
    assert COLUMNS <= columns()
    with engine.connect() as db:
        kept = db.execute(text('SELECT path, line_start, column_start, column_end, role FROM fact_evidence')).one()
    assert tuple(kept) == ('A.java', 3, None, None, None), 'une preuve existante ne gagne ni colonne ni rôle'
    migrate('downgrade', '008')
    assert not columns() & COLUMNS
    with engine.connect() as db:
        assert db.execute(text('SELECT path FROM fact_evidence')).scalar_one() == 'A.java'
    engine.dispose()
