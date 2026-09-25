"""TAXO-EVAL-01 : l'analyse globale du projet et la consultation de l'historique sont deux operations.

L'analyse globale produit les faits du projet ; elle ne consulte pas l'historique Git. La consultation
des commits ne se fait que sur demande, avec un nombre explicite : aucune fenetre n'est imposee.
"""
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.history.domain.commit import MAX_COMMITS
from app.history.infrastructure.git_history import GitHistoryReader
from app.main import create_app


@pytest.fixture(name='project')
def project_fixture(make_repo, git, tmp_path):
    repo = make_repo({'package.json': '{"dependencies": {"react": "19"}}', 'App.java': 'class App {}\n'}, 'global')
    for index in range(11):
        (repo / 'notes.txt').write_text(f'note {index}\n')
        git(repo, 'add', '-A')
        git(repo, 'commit', '-qm', f'note {index}')
    app = create_app(f'sqlite:///{tmp_path / "global.db"}', [repo])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Global', 'path': str(repo)}).json()
        yield client, f'/api/projects/{project["id"]}'


def test_the_global_analysis_never_reads_the_commit_history(project, monkeypatch):
    client, base = project

    def forbidden(*args, **kwargs):
        pytest.fail("l'analyse globale ne doit pas consulter les derniers commits")

    monkeypatch.setattr(GitHistoryReader, 'commits', forbidden)
    analysis = client.post(f'{base}/scans')
    assert analysis.status_code == 201
    summary = analysis.json()['evaluation_summary']
    assert summary['fact_count'] > 0, 'les faits du projet restent produits et accessibles'
    assert client.get(f'{base}/scans').json()[0]['id'] == analysis.json()['id']


def test_consulting_commits_requires_an_explicit_count(project):
    client, base = project
    assert client.get(f'{base}/history/commits').status_code == 422, 'aucun nombre de commits par defaut'
    three = client.get(f'{base}/history/commits', params={'limit': 3}).json()
    ten = client.get(f'{base}/history/commits', params={'limit': 10}).json()
    assert (len(three), len(ten)) == (3, 10), 'le nombre renvoye est celui demande'
    assert [item['subject'] for item in three] == ['note 10', 'note 9', 'note 8']
    assert client.get(f'{base}/history/commits', params={'limit': MAX_COMMITS + 1}).status_code == 422


def test_git_features_remain_available_without_the_default_list(project):
    client, base = project
    [latest] = client.get(f'{base}/history/commits', params={'limit': 1}).json()
    detail = client.get(f'{base}/history/commits/{latest["sha"]}').json()
    assert [item['path'] for item in detail['files']] == ['notes.txt']
    assert client.get(f'{base}/history/commits/{latest["sha"]}/diff', params={'path': 'notes.txt'}).status_code == 200
    assert client.get(f'{base}/history/commits/{latest["sha"]}/impact').status_code == 200


def test_the_reader_has_no_default_window(make_repo):
    repo = make_repo({'a.txt': 'a\n'}, 'window')
    with pytest.raises(TypeError):
        GitHistoryReader().commits(repo)
