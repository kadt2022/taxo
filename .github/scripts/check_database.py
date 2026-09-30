"""Exercise the API against an already migrated, disposable CI database."""

import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.scans.infrastructure.sqlalchemy.fact_store import SqlAlchemyAnalysisFacts


def git(root, *args):
    subprocess.run(['git', '-c', 'user.name=Taxo CI', '-c', 'user.email=ci@example.invalid',
                    '-c', 'commit.gpgsign=false', '-C', str(root), *args], check=True, capture_output=True)


def check_long_reference_adjacency(engine, scan_id):
    """Regression for PostgreSQL B-tree entry limits, including a long anchor."""
    store = SqlAlchemyAnalysisFacts(engine)
    anchor = 'module:' + ''.join(chr(0x4e00 + i) for i in range(850))
    prefix = 'module:' + ''.join(chr(0x5000 + i) for i in range(850))
    targets = [prefix + suffix for suffix in ('z', '\U00010000', '\ue000', '')]
    facts = [{'kind': 'ASSERTION', 'subject': anchor, 'relation': 'DEPENDS_ON', 'object': target,
              'qualifiers': {}, 'status': 'OBSERVED', 'validity': 'VALID', 'evidence': [],
              'produced_by': {'producer_id': 'ci-fixture'}} for target in targets]
    store.add(scan_id, 'ci-fixture', facts)
    assert store.has_reference(scan_id, anchor)
    after = ''
    for target in sorted(targets, key=lambda value: value.encode('utf-16-be')):
        after, found = store.neighbor(scan_id, anchor, 'DEPENDS_ON', 'OUTGOING', after)
        assert found['object'] == target
        assert store.neighbor(scan_id, target, 'DEPENDS_ON', 'INCOMING')[1]['subject'] == anchor
    assert store.neighbor(scan_id, anchor, 'DEPENDS_ON', 'OUTGOING', after) is None


def main():
    database_url = os.environ['DATABASE_URL']
    with TemporaryDirectory(prefix='taxo-ci-') as directory:
        root = Path(directory)
        (root / 'Hello.java').write_text('class Hello {}\n', encoding='utf-8')
        # Scans analyse a Git snapshot (TAXO-01C): the fixture must be a committed repository.
        git(root, 'init', '-q')
        git(root, 'add', '-A')
        git(root, 'commit', '-q', '-m', 'fixture')
        app = create_app(database_url, [root])
        try:
            with TestClient(app) as client:
                response = client.post('/api/projects', json={'name': 'CI-' + uuid4().hex, 'path': str(root)})
                assert response.status_code == 201, response.text
                project_id = response.json()['id']
                response = client.post(f'/api/projects/{project_id}/scans')
                assert response.status_code == 201, response.text
                assert any(fact['technology'] == 'Java' for fact in response.json()['facts'])
                check_long_reference_adjacency(app.state.engine, response.json()['id'])
        finally:
            app.state.engine.dispose()

        restarted = create_app(database_url, [root])
        try:
            with TestClient(restarted) as client:
                response = client.get(f'/api/projects/{project_id}/scans')
                assert response.status_code == 200, response.text
                assert len(response.json()) == 1
                assert any(fact['technology'] == 'Java' for fact in response.json()[0]['facts'])
        finally:
            restarted.state.engine.dispose()
    print('Migrated database: API writes and persistence across application instances passed.')


if __name__ == '__main__':
    main()
