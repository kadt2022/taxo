import json
from fastapi.testclient import TestClient
from app.main import Base, create_app
from app.scanner import inspect_repository


def test_inventory_and_exclusions(tmp_path):
    (tmp_path / 'package.json').write_text(json.dumps({'dependencies': {'react': '19'}}))
    (tmp_path / 'App.tsx').write_text('export const App = () => null')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'hidden.py').write_text('')
    (tmp_path / '.env').write_text('PASSWORD=never-index-this')
    result = inspect_repository(tmp_path)
    assert {f['technology'] for f in result['facts']} == {'React', 'TypeScript', 'Node.js ecosystem'}
    assert 'never-index-this' not in json.dumps(result)


def test_api_persistence_and_boundaries(tmp_path):
    source = tmp_path / 'repo'
    source.mkdir()
    (source / 'Hello.java').write_text('class Hello {}')
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
        (source / 'Hello.java').unlink()
        assert client.post(f'/api/projects/{p["id"]}/scans').json()['facts'] == []
    with TestClient(create_app(url, [source])) as client:
        assert len(client.get(f'/api/projects/{p["id"]}/scans').json()) == 2


def test_malformed_manifest(tmp_path):
    (tmp_path / 'package.json').write_text('{broken')
    assert inspect_repository(tmp_path)['warnings']


def test_python_requirements_and_maven(tmp_path):
    (tmp_path / 'requirements.txt').write_text('fastapi>=0.115\npsycopg[binary]>=3.2\n# flask is not installed\n')
    (tmp_path / 'pom.xml').write_text('<project xmlns="http://maven.apache.org/POM/4.0.0"><parent><groupId>org.springframework.boot</groupId></parent></project>')
    names = {fact['technology'] for fact in inspect_repository(tmp_path)['facts']}
    assert names == {'FastAPI', 'PostgreSQL client', 'Maven', 'Spring Boot'}
