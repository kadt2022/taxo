"""TAXO-HIST-02 : diff cote a cote d'un fichier, parent a gauche, commit a droite."""
import json

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.database import Base
from app.history.domain.diff import MAX_DIFF_BYTES, side_by_side
from app.main import create_app


def commit_all(git, repo, message):
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', message)
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture(name='client')
def client_fixture(tmp_path):
    clients = []

    def open_client(repo):
        app = create_app(f'sqlite:///{tmp_path / "diff.db"}', [repo])
        Base.metadata.create_all(app.state.engine)
        client = TestClient(app)
        clients.append(client)
        project = client.post('/api/projects', json={'name': 'Diff', 'path': str(repo)}).json()
        return client, f'/api/projects/{project["id"]}/history/commits'
    yield open_client
    for client in clients:
        client.close()


def diff(client, base, sha, path, **params):
    return client.get(f'{base}/{sha}/diff', params={'path': path, **params})


def rows(result):
    return [row for hunk in result['hunks'] for row in hunk['rows']]


@pytest.fixture(name='story')
def story_fixture(make_repo, git):
    repo = make_repo({'app.py': 'a = 1\nb = 2\nc = 3\n', 'old.txt': 'garde\n', 'gone.txt': 'adieu\n'}, 'story')
    root = git(repo, 'rev-parse', 'HEAD')
    (repo / 'app.py').write_text('a = 1\nb = 20\nc = 3\nd = 4\n')
    (repo / 'new.txt').write_text('bonjour\n')
    (repo / 'gone.txt').unlink()
    git(repo, 'mv', 'old.txt', 'renamed.txt')
    second = commit_all(git, repo, 'modifie, ajoute, supprime, renomme')
    return repo, root, second


def test_a_modified_file_puts_the_parent_left_and_the_commit_right(story, client):
    repo, root, second = story
    http, base = client(repo)
    result = diff(http, base, second, 'app.py').json()
    assert (result['status'], result['parent'], result['commit']) == ('MODIFIED', root, second)
    assert result['displayable'] is True and result['reason'] is None
    assert result['before'] == {'path': 'app.py', 'size': 18}
    changed = [row for row in rows(result) if row['kind'] != 'equal']
    assert changed == [
        {'kind': 'changed', 'before': {'number': 2, 'text': 'b = 2'}, 'after': {'number': 2, 'text': 'b = 20'}},
        {'kind': 'added', 'before': None, 'after': {'number': 4, 'text': 'd = 4'}},
    ]
    assert rows(result)[0] == {'kind': 'equal', 'before': {'number': 1, 'text': 'a = 1'},
                               'after': {'number': 1, 'text': 'a = 1'}}


def test_an_added_file_has_an_empty_left_side_and_a_deleted_one_an_empty_right_side(story, client):
    repo, _, second = story
    http, base = client(repo)
    added = diff(http, base, second, 'new.txt').json()
    assert added['before'] is None and [row['kind'] for row in rows(added)] == ['added']
    deleted = diff(http, base, second, 'gone.txt').json()
    assert deleted['after'] is None and rows(deleted) == [
        {'kind': 'removed', 'before': {'number': 1, 'text': 'adieu'}, 'after': None}]


def test_a_renamed_file_shows_the_old_path_left_and_the_new_path_right(story, client):
    repo, _, second = story
    http, base = client(repo)
    result = diff(http, base, second, 'renamed.txt').json()
    assert (result['status'], result['old_path']) == ('RENAMED', 'old.txt')
    assert (result['before']['path'], result['after']['path']) == ('old.txt', 'renamed.txt')
    assert result['hunks'] == [], 'un renommage sans changement de contenu ne montre aucune ligne'


def test_a_root_commit_compares_with_nothing(story, client):
    repo, root, _ = story
    http, base = client(repo)
    result = diff(http, base, root, 'app.py').json()
    assert result['parent'] is None and result['before'] is None
    assert {row['kind'] for row in rows(result)} == {'added'}


def test_a_merge_commit_diffs_against_the_chosen_parent(make_repo, git, client):
    repo = make_repo({'a.txt': 'a\n'}, 'merge')
    git(repo, 'checkout', '-qb', 'side')
    (repo / 'side.py').write_text('x = 1\n')
    side = commit_all(git, repo, 'side')
    git(repo, 'checkout', '-q', '-')
    (repo / 'main.java').write_text('class M {}\n')
    main = commit_all(git, repo, 'main')
    git(repo, 'merge', '-q', '--no-edit', 'side')
    merge = git(repo, 'rev-parse', 'HEAD')
    http, base = client(repo)
    first_parent = diff(http, base, merge, 'side.py').json()
    assert (first_parent['parent'], first_parent['status']) == (main, 'ADDED')
    assert diff(http, base, merge, 'main.java').status_code == 404, 'inchange par rapport au premier parent'
    against_side = diff(http, base, merge, 'main.java', parent=side).json()
    assert (against_side['parent'], against_side['status']) == (side, 'ADDED')


@pytest.mark.parametrize('name', ['.env', 'config/.env.production'])
def test_a_confidential_file_is_named_but_its_content_never_leaves_git(make_repo, git, client, name):
    repo = make_repo({name: 'PASSWORD=ancien-secret\n'}, 'secret')
    (repo / name).write_text('PASSWORD=nouveau-secret\n')
    sha = commit_all(git, repo, 'change le secret')
    http, base = client(repo)
    response = diff(http, base, sha, name)
    result = response.json()
    assert (result['path'], result['displayable'], result['reason']) == (name, False, 'CONFIDENTIAL')
    assert result['hunks'] == [] and result['before'] is None and result['after'] is None
    assert 'secret' not in response.text


def test_a_binary_file_is_refused_on_either_side(make_repo, git, client):
    repo = make_repo({'logo.png': b'\x89PNG\x00\x01', 'data.txt': 'texte\n'}, 'binary')
    (repo / 'logo.png').write_bytes(b'\x89PNG\x00\x02')
    (repo / 'data.txt').write_bytes(b'\xff\xfe invalide')
    sha = commit_all(git, repo, 'binaires')
    http, base = client(repo)
    for path in ('logo.png', 'data.txt'):
        result = diff(http, base, sha, path).json()
        assert (result['displayable'], result['reason'], result['hunks']) == (False, 'BINARY', [])


def test_a_file_too_large_is_refused_without_being_read(make_repo, git, client, monkeypatch):
    from app.history.infrastructure.git_history import GitHistoryReader

    repo = make_repo({'big.log': 'petit\n'}, 'big')
    (repo / 'big.log').write_text('x' * (MAX_DIFF_BYTES + 1))
    sha = commit_all(git, repo, 'grossit')
    monkeypatch.setattr(GitHistoryReader, 'content', lambda *args: pytest.fail('aucun contenu ne doit etre lu'))
    http, base = client(repo)
    result = diff(http, base, sha, 'big.log').json()
    assert (result['displayable'], result['reason']) == (False, 'TOO_LARGE')
    assert result['after']['size'] == MAX_DIFF_BYTES + 1


def test_a_symlink_is_not_a_regular_file(make_repo, git, client):
    repo = make_repo({'a.txt': 'a\n'}, 'link')
    (repo / 'lien').symlink_to('/etc/passwd')
    sha = commit_all(git, repo, 'lien')
    http, base = client(repo)
    result = diff(http, base, sha, 'lien').json()
    assert (result['displayable'], result['reason']) == (False, 'NOT_A_REGULAR_FILE')
    assert 'root:' not in json.dumps(result)


@pytest.mark.parametrize('path', ['absent.txt', '../../etc/passwd', 'app.py/../app.py', ''])
def test_a_path_not_touched_by_the_commit_is_refused(story, client, path):
    repo, _, second = story
    http, base = client(repo)
    response = diff(http, base, second, path)
    assert response.status_code == 404
    assert 'UNKNOWN_PATH' in response.json()['detail']


def test_a_path_is_always_literal_never_a_pattern(make_repo, git, client):
    repo = make_repo({'abc.txt': 'autre\n', 'a*.txt': 'avant\n'}, 'glob')
    (repo / 'a*.txt').write_text('apres\n')
    sha = commit_all(git, repo, 'etoile')
    http, base = client(repo)
    result = diff(http, base, sha, 'a*.txt').json()
    assert [row['after']['text'] for row in rows(result) if row['after']] == ['apres']


def test_long_unchanged_stretches_are_folded_into_hunks():
    before = '\n'.join(f'ligne {n}' for n in range(1, 41))
    after = before.replace('ligne 5\n', 'ligne cinq\n').replace('ligne 35', 'ligne trente-cinq')
    hunks = side_by_side(before, after)
    assert [(hunk['before_start'], hunk['after_start']) for hunk in hunks] == [(2, 2), (32, 32)]
    assert all(len(hunk['rows']) == 7 for hunk in hunks), '3 lignes de contexte de chaque cote'
