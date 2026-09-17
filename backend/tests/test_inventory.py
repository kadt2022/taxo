import json
from fastapi.testclient import TestClient
from app.main import create_app
from app.bootstrap.database import Base
from app.evaluators.inventory.evaluator import InventoryEvaluator
from app.evaluations.application.run_evaluator import RunEvaluator
from app.snapshots.infrastructure.git.reader import open_snapshot


def inspect_repository(root, repository, mode='COMMIT', commit=None):
    return RunEvaluator()(InventoryEvaluator(), open_snapshot(root, repository, mode, commit)).legacy


def test_inventory_and_exclusions(make_repo):
    repo = make_repo({'package.json': json.dumps({'dependencies': {'react': '19'}}),
                      'App.tsx': 'export const App = () => null',
                      'node_modules/hidden.py': '', '.env': 'PASSWORD=never-index-this'})
    result = inspect_repository(repo, 'demo')
    assert {f['technology'] for f in result['facts']} == {'React', 'TypeScript', 'Node.js ecosystem'}
    assert 'never-index-this' not in json.dumps(result)


def test_api_persistence_and_boundaries(make_repo, git, tmp_path):
    source = make_repo({'Hello.java': 'class Hello {}'}, 'repo')
    url = f'sqlite:///{tmp_path / "test.db"}'
    app = create_app(url, [source])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        assert client.post('/api/projects', json={'name': 'Outside', 'path': str(tmp_path)}).status_code == 403
        p = client.post('/api/projects', json={'name': 'Example', 'path': str(source)}).json()
        assert client.post('/api/projects', json={'name': 'Duplicate', 'path': str(source)}).status_code == 409
        response = client.post(f'/api/projects/{p["id"]}/scans')
        assert response.status_code == 201
        assert response.json()['facts'][0]['technology'] == 'Java'
        assert 'evaluation' not in response.json()
        git(source, 'rm', '-q', 'Hello.java')
        git(source, 'commit', '-q', '-m', 'remove')
        assert client.post(f'/api/projects/{p["id"]}/scans').json()['facts'] == []
    with TestClient(create_app(url, [source])) as client:
        history = client.get(f'/api/projects/{p["id"]}/scans').json()
        assert len(history) == 2
        assert all('evaluation' not in scan for scan in history)


def test_malformed_manifest(make_repo):
    assert inspect_repository(make_repo({'package.json': '{broken'}), 'demo')['warnings']


def test_python_requirements_and_maven(make_repo):
    repo = make_repo({'requirements.txt': 'fastapi>=0.115\npsycopg[binary]>=3.2\n# flask is not installed\n',
                      'pom.xml': '<project xmlns="http://maven.apache.org/POM/4.0.0"><parent><groupId>org.springframework.boot</groupId></parent></project>'})
    names = {fact['technology'] for fact in inspect_repository(repo, 'demo')['facts']}
    assert names == {'FastAPI', 'PostgreSQL client', 'Maven', 'Spring Boot'}
