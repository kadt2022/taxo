import json
import os
import subprocess
import sys
import unicodedata

from fastapi.testclient import TestClient
import pytest

from app.snapshots.infrastructure.git import reader as snapshots
from app.main import create_app
from app.bootstrap.database import Base
from app.evaluators.inventory.evaluator import evaluate
from app.snapshots.infrastructure.git.reader import (COMMIT, GIT_READ_ERROR, NOT_A_GIT_REPOSITORY, UNKNOWN_COMMIT, UNSUPPORTED_GIT_ENTRY,
                           WORKING_TREE, WORKING_TREE_READ_ERROR, SnapshotError, open_snapshot)

FILES = {'.gitignore': 'cache/\nignored.txt\n', 'package.json': json.dumps({'dependencies': {'react': '19'}}),
         'App.tsx': 'export const App = () => null\n', 'src/main.py': 'print(1)\n'}


def inspect_repository(root, repository, mode=COMMIT, commit=None):
    return evaluate(open_snapshot(root, repository, mode, commit))


@pytest.fixture
def repo(make_repo):
    return make_repo(FILES, 'demo')


def paths(snapshot):
    return [f.path for f in snapshot.iter_files()]


def contents(snapshot):
    return dict(snapshot.read_many(paths(snapshot)))


def fingerprint(repo):
    return open_snapshot(repo, 'demo', WORKING_TREE).content_fingerprint


def error_code(call):
    with pytest.raises(SnapshotError) as caught:
        call()
    return caught.value.code


# COMMIT

def test_commit_lists_committed_files_and_reads_git_objects(repo):
    (repo / 'cache').mkdir()
    (repo / 'cache' / 'big.bin').write_bytes(b'x')
    (repo / 'ignored.txt').write_text('ignored')
    (repo / 'untracked.py').write_text('')
    (repo / 'package.json').write_text('{"local": true}')
    (repo / 'App.tsx').unlink()
    snapshot = open_snapshot(repo, 'demo')
    assert paths(snapshot) == ['.gitignore', 'App.tsx', 'package.json', 'src/main.py']
    data = contents(snapshot)
    assert data['package.json'] == FILES['package.json'].encode()
    assert data['App.tsx'] == FILES['App.tsx'].encode()
    assert snapshot.dirty is None
    assert 'content_fingerprint' not in snapshot.reference()


def test_commit_does_not_depend_on_the_working_tree(repo):
    before = open_snapshot(repo, 'demo')
    expected = (paths(before), contents(before))
    for path in expected[0]:
        (repo / path).unlink()
    after = open_snapshot(repo, 'demo')
    actual = (paths(after), contents(after))
    assert actual == expected
    assert after.commit == before.commit


def test_old_commit_can_be_read_after_head_moves(repo, git):
    first = git(repo, 'rev-parse', 'HEAD')
    (repo / 'App.tsx').write_bytes(b'changed\n')
    git(repo, 'commit', '-qam', 'second')
    old = open_snapshot(repo, 'demo', commit=first)
    assert old.commit == first
    assert old.read_bytes('App.tsx') == FILES['App.tsx'].encode()
    assert open_snapshot(repo, 'demo').read_bytes('App.tsx') == b'changed\n'


def test_sha_is_frozen_when_head_moves_during_analysis(repo, git):
    snapshot = open_snapshot(repo, 'demo')
    frozen = snapshot.commit
    (repo / 'App.tsx').write_bytes(b'newer\n')
    (repo / 'added.py').write_text('')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'during')
    assert snapshot.commit == frozen
    assert 'added.py' not in paths(snapshot)
    assert snapshot.read_bytes('App.tsx') == FILES['App.tsx'].encode()


def test_no_checkout_reset_or_index_write(repo):
    (repo / 'App.tsx').write_bytes(b'local\n')
    (repo / 'untracked.py').write_text('')
    index = repo / '.git' / 'index'
    def state():
        return (index.read_bytes(), index.stat().st_mtime_ns, (repo / '.git' / 'HEAD').read_bytes(),
                (repo / 'App.tsx').read_bytes(), sorted(p.name for p in repo.iterdir()))
    before = state()
    for mode in (COMMIT, WORKING_TREE):
        contents(open_snapshot(repo, 'demo', mode))
    assert state() == before


def test_symlinks_and_submodules_are_not_followed(repo, git):
    link = git(repo, 'hash-object', '-w', '--stdin', stdin=b'../outside')
    git(repo, 'update-index', '--add', '--cacheinfo', f'120000,{link},link.py')
    git(repo, 'update-index', '--add', '--cacheinfo', f'160000,{git(repo, "rev-parse", "HEAD")},vendor')
    git(repo, 'commit', '-qm', 'special entries')
    snapshot = open_snapshot(repo, 'demo')
    assert 'link.py' not in paths(snapshot)
    assert 'vendor' not in paths(snapshot)
    assert set(snapshot.skipped) == {('link.py', 'symlink'), ('vendor', 'submodule')}


@pytest.mark.parametrize('commit', ['HEAD', 'abc123', 'A' * 40, '0' * 39, '--output=' + '0' * 32, '0' * 40, 'f' * 64])
def test_unknown_or_malformed_commit_is_refused(repo, commit):
    assert error_code(lambda: open_snapshot(repo, 'demo', commit=commit)) == UNKNOWN_COMMIT


def test_two_reads_of_a_commit_are_identical(repo):
    first, second = open_snapshot(repo, 'demo'), open_snapshot(repo, 'demo')
    assert first.files == second.files
    assert contents(first) == contents(second)


def test_commit_content_is_read_through_one_batch_process(repo, monkeypatch):
    snapshot = open_snapshot(repo, 'demo')
    calls, real = [], subprocess.Popen
    def spy(args, *rest, **options):
        calls.append(args)
        return real(args, *rest, **options)
    monkeypatch.setattr(snapshots.subprocess, 'Popen', spy)
    assert len(contents(snapshot)) == 4
    assert sum('cat-file' in call for call in calls) == 1


def test_missing_git_object_is_a_read_error(repo):
    snapshot = open_snapshot(repo, 'demo')
    oid = snapshot.content.sources['App.tsx']
    obj = repo / '.git' / 'objects' / oid[:2] / oid[2:]
    os.chmod(obj, 0o644)
    obj.unlink()
    assert error_code(lambda: snapshot.read_bytes('App.tsx')) == GIT_READ_ERROR


def test_git_paths_must_be_utf8(repo, git):
    blob = git(repo, 'hash-object', '-w', '--stdin', stdin=b'x')
    git(repo, 'update-index', '--index-info', stdin=f'100644 blob {blob}\t'.encode() + b'bad\xff.txt\n')
    git(repo, 'commit', '-qm', 'non utf-8 path')
    assert error_code(lambda: open_snapshot(repo, 'demo')) == UNSUPPORTED_GIT_ENTRY


def test_git_paths_colliding_after_nfc_are_refused(repo, git):
    blob = git(repo, 'hash-object', '-w', '--stdin', stdin=b'x')
    entry = f'100644 blob {blob}\t'.encode()
    names = ('café.txt', unicodedata.normalize('NFD', 'café.txt'))
    git(repo, 'update-index', '--index-info', stdin=b''.join(entry + n.encode() + b'\n' for n in names))
    git(repo, 'commit', '-qm', 'nfc collision')
    assert error_code(lambda: open_snapshot(repo, 'demo')) == UNSUPPORTED_GIT_ENTRY


def test_env_files_are_never_exposed(make_repo):
    repo = make_repo({**FILES, '.env': 'SECRET=1', 'config/.env.local': 'TOKEN=2'}, 'demo')
    for mode in (COMMIT, WORKING_TREE):
        snapshot = open_snapshot(repo, 'demo', mode)
        assert not any(p.rsplit('/', 1)[-1].startswith('.env') for p in paths(snapshot))
        assert set(snapshot.skipped) >= {('.env', 'confidential'), ('config/.env.local', 'confidential')}
        with pytest.raises(KeyError):
            snapshot.read_bytes('.env')


def test_repository_configured_programs_are_never_executed(repo, git, tmp_path):
    marker = tmp_path / 'executed'
    command = f'"{sys.executable}" -c "open(r\'{marker}\', \'w\').close()"'
    for key in ('core.fsmonitor', 'filter.probe.clean', 'filter.probe.smudge'):
        git(repo, 'config', key, command)
    (repo / '.gitattributes').write_text('* filter=probe\n')
    (repo / 'App.tsx').write_text('changed\n')
    for mode in (COMMIT, WORKING_TREE):
        inspect_repository(repo, 'demo', mode)
    assert not marker.exists()


@pytest.mark.parametrize('mode', [COMMIT, WORKING_TREE])
def test_git_repository_root_is_required(make_repo, tmp_path, mode):
    plain = tmp_path / 'plain'
    plain.mkdir()
    (plain / 'Hello.java').write_text('class Hello {}')
    repo = make_repo(FILES, 'demo')
    (repo / 'sub').mkdir()
    for folder in (plain, repo / 'sub'):
        assert error_code(lambda: open_snapshot(folder, 'demo', mode)) == NOT_A_GIT_REPOSITORY


def test_repository_key_comes_from_the_caller(make_repo):
    first = make_repo(FILES, 'A/backend')
    second = make_repo(FILES, 'B/backend')
    assert open_snapshot(first, 'project-a').repository == 'project-a'
    assert open_snapshot(second, 'project-b').repository == 'project-b'
    with pytest.raises(ValueError):
        open_snapshot(first, '')


# WORKING_TREE

def test_working_tree_is_marked_with_head_and_fingerprint(repo, git):
    snapshot = open_snapshot(repo, 'demo', WORKING_TREE)
    assert snapshot.mode == WORKING_TREE
    assert snapshot.commit == git(repo, 'rev-parse', 'HEAD')
    assert snapshot.reference()['content_fingerprint'].startswith('sha256:')
    assert len(snapshot.content_fingerprint) == 71
    assert snapshot.dirty is False
    with pytest.raises(ValueError):
        open_snapshot(repo, 'demo', WORKING_TREE, commit=snapshot.commit)


def test_working_tree_fingerprint_follows_included_content_only(repo):
    base = fingerprint(repo)
    (repo / 'App.tsx').write_bytes(b'modified\n')
    assert fingerprint(repo) != base
    assert open_snapshot(repo, 'demo', WORKING_TREE).dirty is True
    (repo / 'App.tsx').write_bytes(FILES['App.tsx'].encode())
    assert fingerprint(repo) == base
    (repo / 'new.py').write_text('')
    added = fingerprint(repo)
    assert added != base
    (repo / 'new.py').unlink()
    (repo / 'src' / 'main.py').unlink()
    assert fingerprint(repo) not in (base, added)
    (repo / 'src' / 'main.py').write_bytes(FILES['src/main.py'].encode())
    (repo / 'ignored.txt').write_text('a')
    (repo / 'cache').mkdir()
    (repo / 'cache' / 'x').write_text('')
    assert fingerprint(repo) == base
    (repo / 'ignored.txt').write_text('b')
    assert fingerprint(repo) == base


def test_working_tree_fingerprint_ignores_timestamps_and_line_endings(repo):
    base = fingerprint(repo)
    os.utime(repo / 'App.tsx', (1, 1))
    (repo / 'src' / 'main.py').write_bytes(b'print(1)\r\n')
    snapshot = open_snapshot(repo, 'demo', WORKING_TREE)
    assert snapshot.content_fingerprint == base
    assert snapshot.dirty is False


def test_identical_working_trees_share_fingerprint_across_unicode_forms(make_repo):
    nfc = make_repo({'café.txt': 'x'}, 'nfc')
    nfd = make_repo({unicodedata.normalize('NFD', 'café.txt'): 'x'}, 'nfd')
    assert fingerprint(nfc) == fingerprint(nfd)
    assert paths(open_snapshot(nfd, 'demo', WORKING_TREE)) == ['café.txt']


def test_working_tree_read_error_fails_the_snapshot(repo, monkeypatch):
    def broken(_file):
        raise OSError('denied')
    monkeypatch.setattr(snapshots, '_file_digest', broken)
    assert error_code(lambda: open_snapshot(repo, 'demo', WORKING_TREE)) == WORKING_TREE_READ_ERROR


# API

def test_api_modes_explicit_commit_and_structured_errors(make_repo, git, tmp_path):
    repo = make_repo(FILES, 'demo')
    first = git(repo, 'rev-parse', 'HEAD')
    (repo / 'App.tsx').write_bytes(b'second\n')
    git(repo, 'commit', '-qam', 'second')
    plain = tmp_path / 'plain'
    plain.mkdir()
    url = f'sqlite:///{tmp_path / "api.db"}'
    app = create_app(url, [tmp_path])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Demo', 'path': str(repo)}).json()
        scans = f'/api/projects/{project["id"]}/scans'
        head = client.post(scans).json()
        assert head['source'] == 'commit'
        assert head['snapshot']['repository'] == project['id']
        assert 'dirty' not in head['snapshot']
        assert client.post(scans, params={'commit': first}).json()['commit'] == first
        working = client.post(scans, params={'mode': 'working-tree'}).json()
        assert working['source'] == 'working-tree'
        assert working['snapshot']['dirty'] is False
        refused = client.post(scans, params={'commit': 'HEAD'})
        assert refused.status_code == 422
        assert refused.json()['detail'].startswith(UNKNOWN_COMMIT)
        assert client.post(scans, params={'mode': 'other'}).status_code == 422
        assert client.post(scans, params={'mode': 'working-tree', 'commit': first}).status_code == 422
        other = client.post('/api/projects', json={'name': 'Plain', 'path': str(plain)}).json()
        response = client.post(f'/api/projects/{other["id"]}/scans')
        assert response.status_code == 422
        assert response.json()['detail'].startswith(NOT_A_GIT_REPOSITORY)
