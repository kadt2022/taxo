"""Exercise the API against an already migrated, disposable CI database."""

import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def git(root, *args):
    subprocess.run(['git', '-c', 'user.name=Taxo CI', '-c', 'user.email=ci@example.invalid',
                    '-c', 'commit.gpgsign=false', '-C', str(root), *args], check=True, capture_output=True)


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
