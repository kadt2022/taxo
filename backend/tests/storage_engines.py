"""Test databases: SQLite by default, PostgreSQL when TAXO_TEST_POSTGRES_URL names an empty test database."""
import os

from sqlalchemy import create_engine

from app.bootstrap.database import Base

POSTGRES = os.environ.get('TAXO_TEST_POSTGRES_URL')


def fresh_engine(tmp_path, name='taxo'):
    """A database holding every table and no row. On PostgreSQL the whole schema is dropped first."""
    if not POSTGRES:
        engine = create_engine(f'sqlite:///{tmp_path / f"{name}.db"}')
    else:
        engine = create_engine(POSTGRES)
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return engine
