from pathlib import PurePosixPath

EXTENSIONS = {'.java': 'Java', '.py': 'Python', '.ts': 'TypeScript', '.tsx': 'TypeScript', '.js': 'JavaScript', '.jsx': 'JavaScript', '.sql': 'SQL'}

def _technologies_by_name(path):
    filename = path.rsplit('/', 1)[-1]
    suffix = PurePosixPath(filename).suffix
    if suffix in EXTENSIONS:
        yield EXTENSIONS[suffix]
    if filename == 'Dockerfile' or filename.startswith('Dockerfile.'):
        yield 'Docker'
    if path.startswith('.github/workflows/') and suffix in {'.yml', '.yaml'}:
        yield 'GitHub Actions'
