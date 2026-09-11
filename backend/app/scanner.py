"""Bounded, read-only inventory. No repository code or build scripts are executed."""
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '__pycache__', '.python-packages'}
EXTENSIONS = {'.java': 'Java', '.py': 'Python', '.ts': 'TypeScript', '.tsx': 'TypeScript', '.js': 'JavaScript', '.jsx': 'JavaScript', '.sql': 'SQL'}


def inspect_repository(root: Path) -> dict:
    facts, warnings = set(), []
    count = 0
    def add(name, path):
        facts.add((name, path))
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED and not (Path(directory) / d).is_symlink() and not (Path(directory) / d).is_junction())
        for filename in sorted(files):
            file = Path(directory) / filename
            if file.is_symlink() or not file.resolve().is_relative_to(root):
                continue
            count += 1
            if count > 50000:
                raise ValueError('Projet trop volumineux : limite de 50 000 fichiers.')
            relative = file.relative_to(root).as_posix()
            if file.suffix in EXTENSIONS:
                add(EXTENSIONS[file.suffix], relative)
            if filename == 'Dockerfile' or filename.startswith('Dockerfile.'):
                add('Docker', relative)
            if relative.startswith('.github/workflows/') and file.suffix in {'.yml', '.yaml'}:
                add('GitHub Actions', relative)
            if filename not in {'package.json', 'pom.xml', 'requirements.txt'}:
                continue
            try:
                if file.stat().st_size > 1024 * 1024:
                    warnings.append(f'Manifeste trop volumineux : {relative}')
                    continue
                content = file.read_text(encoding='utf-8-sig')
                if filename == 'requirements.txt':
                    for line in content.splitlines():
                        match = re.match(r'^\s*([A-Za-z0-9_-]+)(?:\[|[<>=!~;\s]|$)', line)
                        if match:
                            dependency = match.group(1).lower().replace('_', '-')
                            name = {'fastapi': 'FastAPI', 'django': 'Django', 'flask': 'Flask', 'sqlalchemy': 'SQLAlchemy', 'psycopg': 'PostgreSQL client', 'alembic': 'Alembic'}.get(dependency)
                            if name:
                                add(name, relative)
                elif filename == 'package.json':
                    package = json.loads(content)
                    deps = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
                    for key, name in {'react': 'React', 'typescript': 'TypeScript', 'vite': 'Vite', 'next': 'Next.js', 'express': 'Express', '@nestjs/core': 'NestJS'}.items():
                        if key in deps:
                            add(name, relative)
                    add('Node.js ecosystem', relative)
                else:
                    tree = ET.fromstring(content)
                    add('Maven', relative)
                    for element in tree.iter():
                        if element.tag.split('}')[-1] == 'groupId' and element.text == 'org.springframework.boot':
                            add('Spring Boot', relative)
            except (OSError, ValueError, TypeError, AttributeError, ET.ParseError):
                warnings.append(f'Manifeste illisible ou invalide : {relative}')
    commit = None
    # Only report a commit when this directory itself is the repository root.
    if (root / '.git').exists():
        try:
            result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', 'HEAD'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                commit = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            warnings.append('Commit Git indisponible.')
    return {'files_count': count, 'commit': commit, 'source': 'working-tree',
            'facts': [{'technology': name, 'file': path, 'status': 'OBSERVED', 'method': 'manifest' if Path(path).name in {'package.json', 'pom.xml', 'requirements.txt'} else 'filename'} for name, path in sorted(facts)],
            'warnings': warnings}
