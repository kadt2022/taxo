import json
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from app.main import Base, create_app
from app.scanner import inspect_repository
from app.snapshots import COMMIT, WORKING_TREE, SnapshotError, open_snapshot


def git(repo, *args, stdin=None):
    return subprocess.run(['git', '-c', 'user.name=Taxo', '-c', 'user.email=taxo@example.invalid',
                           '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false', '-C', str(repo), *args],
                          input=stdin, check=True, capture_output=True).stdout.decode().strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'demo'
    root.mkdir()
    git(root, 'init', '-q')
    (root / '.gitignore').write_text('ignored/\n.env\n')
    (root / 'package.json').write_text(json.dumps({'dependencies': {'react': '19'}}))
    (root / 'App.tsx').write_bytes(b'export const App = () => null\n')
    git(root, 'add', '.')
    git(root, 'commit', '-q', '-m', 'initial')
    return root


def test_commit_snapshot_reads_only_committed_tracked_content(repo):
    (repo / 'ignored').mkdir()
    (repo / 'ignored' / 'hidden.py').write_text('')
    (repo / 'untracked.py').write_text('')
    (repo / 'package.json').write_text(json.dumps({'dependencies': {'react': '19', 'vite': '7'}}))
    (repo / 'App.tsx').unlink()
    result = inspect_repository(repo)
    assert {f['technology'] for f in result['facts']} == {'React', 'TypeScript', 'Node.js ecosystem'}
    assert result['files_count'] == 3 and result['source'] == 'commit'
    assert result['snapshot'] == {'repository': 'demo', 'commit': git(repo, 'rev-parse', 'HEAD'),
                                  'mode': 'COMMIT', 'dirty': True}


def test_working_tree_snapshot_is_marked_and_includes_uncommitted_files(repo):
    (repo / 'ignored').mkdir()
    (repo / 'ignored' / 'hidden.py').write_text('')
    (repo / 'untracked.py').write_text('')
    result = inspect_repository(repo, WORKING_TREE)
    assert ('Python', 'untracked.py') in {(f['technology'], f['file']) for f in result['facts']}
    assert all(not f['file'].startswith('ignored/') for f in result['facts'])
    snapshot = result['snapshot']
    assert snapshot['mode'] == 'WORKING_TREE' and snapshot['dirty'] is True and result['source'] == 'working-tree'
    assert snapshot['content_fingerprint'].startswith('sha256:') and len(snapshot['content_fingerprint']) == 71


def test_line_endings_alone_do_not_change_state_or_fingerprint(repo):
    lf = open_snapshot(repo, WORKING_TREE)
    assert lf.dirty is False
    (repo / 'App.tsx').write_bytes(b'export const App = () => null\r\n')
    crlf = open_snapshot(repo, WORKING_TREE)
    assert crlf.dirty is False and crlf.content_fingerprint == lf.content_fingerprint
    (repo / 'App.tsx').write_bytes(b'export const App = () => 1\n')
    assert open_snapshot(repo, WORKING_TREE).content_fingerprint != lf.content_fingerprint


def test_env_files_are_never_read(repo):
    (repo / '.env.local').write_text('TOKEN=never-read')
    snapshot = open_snapshot(repo, WORKING_TREE)
    assert snapshot.dirty is False
    assert '.env.local' in {entry.path for entry in snapshot.entries}


def test_repository_configured_programs_are_never_executed(repo, tmp_path):
    marker = tmp_path / 'executed'
    command = f'"{sys.executable}" -c "open(r\'{marker}\', \'w\').close()"'
    for key in ('core.fsmonitor', 'filter.probe.clean', 'filter.probe.smudge'):
        git(repo, 'config', key, command)
    (repo / '.gitattributes').write_text('* filter=probe\n')
    (repo / 'App.tsx').write_text('changed\n')
    for mode in (COMMIT, WORKING_TREE):
        inspect_repository(repo, mode)
    assert not marker.exists()


def test_symlinks_and_submodules_are_not_followed(repo):
    link = git(repo, 'hash-object', '-w', '--stdin', stdin=b'App.tsx')
    git(repo, 'update-index', '--add', '--cacheinfo', f'120000,{link},link.py')
    git(repo, 'update-index', '--add', '--cacheinfo', f'160000,{git(repo, "rev-parse", "HEAD")},vendor')
    git(repo, 'commit', '-q', '-m', 'link and submodule')
    result = inspect_repository(repo)
    assert result['files_count'] == 3
    assert all(f['file'] not in ('link.py', 'vendor') for f in result['facts'])


def test_folders_that_are_not_git_top_levels_are_scanned_without_snapshot(repo, tmp_path):
    plain = tmp_path / 'plain'
    plain.mkdir()
    (plain / 'Hello.java').write_text('class Hello {}')
    (repo / 'sub').mkdir()
    (repo / 'sub' / 'Tool.py').write_text('')
    for folder in (plain, repo / 'sub'):
        result = inspect_repository(folder)
        assert result['snapshot'] is None and result['commit'] is None
        assert result['source'] == 'unversioned' and result['warnings'] and result['facts']


def test_repository_without_commit_is_refused(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    git(empty, 'init', '-q')
    with pytest.raises(SnapshotError):
        open_snapshot(empty)


def test_api_scan_mode(repo, tmp_path):
    url = f'sqlite:///{tmp_path / "api.db"}'
    app = create_app(url, [tmp_path])
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Demo', 'path': str(repo)}).json()
        scans = f'/api/projects/{project["id"]}/scans'
        assert client.post(scans).json()['snapshot']['mode'] == 'COMMIT'
        assert client.post(scans + '?mode=working-tree').json()['snapshot']['mode'] == 'WORKING_TREE'
        assert client.post(scans + '?mode=other').status_code == 422
