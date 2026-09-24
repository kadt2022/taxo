"""TAXO-HIST-01 : l'historique Git d'un projet, et ce que Taxo comprend de chaque commit."""
import json

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.history.domain.errors import NOT_A_GIT_REPOSITORY, UNKNOWN_COMMIT, HistoryError
from app.history.domain.impact import INTRODUCED, MODIFIED, REMOVED, compare
from app.history.infrastructure.git_history import GitHistoryReader
from app.main import create_app

READER = GitHistoryReader()


def commit_all(git, repo, message):
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', message)
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture(name='history')
def history_fixture(make_repo, git):
    repo = make_repo({'App.java': 'class App {}\n', 'notes.txt': 'a\nb\n'}, 'history')
    first = git(repo, 'rev-parse', 'HEAD')
    (repo / 'package.json').write_text(json.dumps({'dependencies': {'react': '19'}}))
    (repo / 'notes.txt').write_text('a\nb\nc\n')
    (repo / '.env').write_text('PASSWORD=never-shown\n')
    second = commit_all(git, repo, 'ajoute react')
    git(repo, 'mv', 'App.java', 'Main.java')
    (repo / 'notes.txt').unlink()
    third = commit_all(git, repo, 'renomme et supprime')
    return repo, first, second, third


def test_the_latest_commits_come_newest_first(history):
    repo, first, second, third = history
    commits = READER.commits(repo, 10)
    assert [commit.sha for commit in commits] == [third, second, first]
    assert commits[0].subject == 'renomme et supprime'
    assert commits[0].parents == (second,)
    assert commits[-1].parents == ()
    assert [commit.sha for commit in READER.commits(repo, 2)] == [third, second]


def test_a_commit_lists_its_files_with_status_and_line_counts(history):
    repo, _, second, third = history
    files = {item.path: item for item in READER.files(repo, second, READER.commit(repo, second).parents[0])}
    assert files['package.json'].status == 'ADDED'
    assert (files['notes.txt'].status, files['notes.txt'].additions, files['notes.txt'].deletions) == ('MODIFIED', 1, 0)
    renamed = {item.path: item for item in READER.files(repo, third, second)}
    assert (renamed['Main.java'].status, renamed['Main.java'].old_path) == ('RENAMED', 'App.java')
    assert renamed['notes.txt'].status == 'DELETED'


def test_a_confidential_file_is_named_but_flagged(history):
    repo, first, second, _ = history
    files = {item.path: item for item in READER.files(repo, second, first)}
    assert files['.env'].confidential and not files['notes.txt'].confidential
    assert 'never-shown' not in json.dumps([vars(item) for item in files.values()])


def test_a_root_commit_has_no_parent_and_adds_everything(history):
    repo, first, _, _ = history
    assert READER.commit(repo, first).parents == ()
    assert {item.status for item in READER.files(repo, first, None)} == {'ADDED'}


@pytest.mark.parametrize('sha', ['HEAD', 'abc', 'f' * 40])
def test_an_unknown_or_symbolic_commit_is_refused(history, sha):
    with pytest.raises(HistoryError) as refused:
        READER.commit(history[0], sha)
    assert refused.value.code == UNKNOWN_COMMIT


def test_a_folder_that_is_not_a_repository_is_refused(tmp_path):
    with pytest.raises(HistoryError) as refused:
        READER.commits(tmp_path, 10)
    assert refused.value.code == NOT_A_GIT_REPOSITORY


def test_a_repository_without_commit_has_an_empty_history(tmp_path, git):
    git(tmp_path, 'init', '-q')
    assert READER.commits(tmp_path, 10) == []


def fact(subject, relation, object_, evidence_line=1):
    return {'kind': 'ASSERTION', 'status': 'OBSERVED', 'subject': subject, 'relation': relation,
            'object': object_, 'evidence': [{'path': 'A.java', 'line_start': evidence_line}]}


def identity(item):
    return (item['subject'], item['relation'], item['object'])


def test_comparison_finds_introduced_removed_and_modified_facts():
    before = [fact('endpoint:GET /a', 'MATCHED_BY', 'route-pattern:/a'), fact('endpoint:GET /b', 'HANDLED_BY', 'symbol:B'),
              fact('endpoint:GET /c', 'HANDLED_BY', 'symbol:C', 3)]
    after = [fact('endpoint:GET /a', 'MATCHED_BY', 'route-pattern:/**'), fact('endpoint:PUT /d', 'HANDLED_BY', 'symbol:D'),
             fact('endpoint:GET /c', 'HANDLED_BY', 'symbol:C', 9)]
    changes, unchanged = compare(before, after, identity)
    assert [(item['change'], item['subject']) for item in changes] == [
        (MODIFIED, 'endpoint:GET /a'), (INTRODUCED, 'endpoint:PUT /d'), (REMOVED, 'endpoint:GET /b')]
    assert (changes[0]['before'], changes[0]['after']) == ('route-pattern:/a', 'route-pattern:/**')
    assert unchanged == 1, 'une preuve deplacee ne change pas le fait'


def api(history_repo, tmp_path):
    app = create_app(f'sqlite:///{tmp_path / "history.db"}', [history_repo])
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def test_the_api_serves_history_detail_and_impact(history, tmp_path):
    repo, first, second, third = history
    with api(repo, tmp_path) as client:
        project = client.post('/api/projects', json={'name': 'Histoire', 'path': str(repo)}).json()
        base = f'/api/projects/{project["id"]}/history/commits'
        assert [item['sha'] for item in client.get(base, params={'limit': 2}).json()] == [third, second]
        assert client.get(base, params={'limit': 0}).status_code == 422
        detail = client.get(f'{base}/{second}').json()
        assert detail['parent'] == first
        assert {item['path'] for item in detail['files']} == {'package.json', 'notes.txt', '.env'}
        impact = client.get(f'{base}/{second}/impact').json()
        inventory = impact['evaluations'][0]
        assert inventory['evaluator_id'] == 'taxo.inventory'
        introduced = {(item['relation'], item['after']) for item in inventory['changes'] if item['change'] == INTRODUCED}
        assert ('USES_TECHNOLOGY', 'technology:React') in introduced
        assert ('CONTAINS', 'file:package.json') in introduced
        assert not any(item['subject'] == 'file:notes.txt' for item in inventory['changes']), \
            'un fichier modifie reste le meme fait'
        assert 'never-shown' not in json.dumps(impact)
        removed = client.get(f'{base}/{third}/impact').json()['evaluations'][0]['changes']
        assert ('REMOVED', 'file:notes.txt') in {(item['change'], item['after'] or item['before']) for item in removed}
        root = client.get(f'{base}/{first}/impact').json()
        assert root['parent'] is None
        assert {item['change'] for item in root['evaluations'][0]['changes']} == {INTRODUCED}
        assert client.get(f'{base}/{"f" * 40}').status_code == 404
        assert client.get(f'{base}/{second}/impact', params={'parent': third}).status_code == 404


def test_a_merge_commit_compares_with_the_chosen_parent(make_repo, git, tmp_path):
    repo = make_repo({'a.txt': 'a'}, 'merge')
    git(repo, 'checkout', '-qb', 'side')
    (repo / 'side.py').write_text('x = 1\n')
    side = commit_all(git, repo, 'side')
    git(repo, 'checkout', '-q', '-')
    (repo / 'main.java').write_text('class M {}\n')
    main = commit_all(git, repo, 'main')
    git(repo, 'merge', '-q', '--no-edit', 'side')
    merge = git(repo, 'rev-parse', 'HEAD')
    assert READER.commit(repo, merge).parents == (main, side)
    with api(repo, tmp_path) as client:
        project = client.post('/api/projects', json={'name': 'Fusion', 'path': str(repo)}).json()
        base = f'/api/projects/{project["id"]}/history/commits/{merge}'
        assert client.get(base).json()['parent'] == main
        against_side = client.get(base, params={'parent': side}).json()
        assert {item['path'] for item in against_side['files']} == {'main.java'}


def test_a_failed_evaluation_is_not_comparable_and_invents_no_change(history):
    from app.evaluations.application.run_evaluator import RunEvaluator
    from app.evaluators.inventory.evaluator import InventoryEvaluator
    from app.history.application.queries import ProjectHistory
    from app.projects.domain.project import Project
    from app.snapshots.infrastructure.git.reader import GitSnapshotReader

    repo, _, second, third = history

    class FailsOnCommit(InventoryEvaluator):
        def evaluate(self, snapshot):
            if snapshot.commit == third:
                raise ValueError('Projet trop volumineux : limite de 50 000 fichiers.')
            return super().evaluate(snapshot)

    class Projects:
        def get(self, project_id):
            return Project(project_id, 'demo', str(repo))

    class Paths:
        def resolve(self, value):
            return value

    history_of = ProjectHistory(Projects(), Paths(), READER, GitSnapshotReader(), [FailsOnCommit()], RunEvaluator())
    _, _, (failed,) = history_of.impact('demo', third)
    assert failed['comparable'] is False
    assert failed['changes'] == [] and failed['unchanged_count'] == 0, 'un echec ne devient jamais « tout est retire »'
    assert failed['status_after'] == 'FAILED'
    assert '50 000 fichiers' in failed['failures'][0]
    _, _, (healthy,) = history_of.impact('demo', second)
    assert healthy['comparable'] is True and healthy['changes']
