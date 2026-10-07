"""L'API ne demarre pas sur une base en retard sur le code : sinon chaque page qui lit une colonne recente
echoue en erreur 500 (la page Routes apres TAXO-01K, migration 009 non appliquee)."""
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine

from app.main import create_app
from app.platform.database.base import Base
from app.platform.database.schema import (SchemaOutOfDate, current_revisions, expected_revisions,
                                          require_current_schema)


def migrated(tmp_path, target):
    url = f'sqlite:///{tmp_path / "taxo.db"}'
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', target], check=True, capture_output=True,
                   env={**os.environ, 'DATABASE_URL': url})
    return url


def test_an_api_started_on_a_database_behind_the_code_refuses_with_what_to_do(tmp_path):
    url = migrated(tmp_path, '008')
    with pytest.raises(SchemaOutOfDate) as refused:
        create_app(url, [str(tmp_path)])
    message = str(refused.value)
    assert 'révision 008' in message and ', '.join(sorted(expected_revisions())) in message
    assert 'alembic upgrade head' in message


def test_an_api_started_on_a_migrated_database_serves(tmp_path):
    url = migrated(tmp_path, 'head')
    app = create_app(url, [str(tmp_path)])
    assert current_revisions(app.state.engine) == expected_revisions()


def test_a_database_not_managed_by_migrations_is_not_checked(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "mappings.db"}')
    Base.metadata.create_all(engine)
    assert current_revisions(engine) is None
    require_current_schema(engine)
    engine.dispose()


def test_a_database_ahead_of_the_code_is_refused_too(tmp_path):
    engine = create_engine(migrated(tmp_path, 'head'))
    with engine.begin() as db:
        db.exec_driver_sql("UPDATE alembic_version SET version_num = '999'")
    with pytest.raises(SchemaOutOfDate, match='révision 999'):
        require_current_schema(engine)
    engine.dispose()
