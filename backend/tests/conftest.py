import subprocess

import pytest


def run_git(repo, *args, stdin=None):
    return subprocess.run(['git', '-c', 'user.name=Taxo', '-c', 'user.email=taxo@example.invalid',
                           '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false', '-C', str(repo), *args],
                          input=stdin, check=True, capture_output=True).stdout.decode('utf-8').strip()


@pytest.fixture
def git():
    return run_git


@pytest.fixture
def make_repo(tmp_path):
    """Create a Git repository whose first commit contains the given files."""
    names = iter(range(1000))
    def create(files, name=None):
        root = tmp_path / (name or f'repo{next(names)}')
        root.mkdir(parents=True)
        run_git(root, 'init', '-q')
        for path, content in files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        run_git(root, 'add', '-A')
        run_git(root, 'commit', '-q', '-m', 'initial')
        return root
    return create
