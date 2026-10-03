"""Le dépôt du parcours de bout en bout de l'explorateur (TAXO-01J) : le dépôt Spring scénarisé des tests du
backend, écrit dans un dossier et commité. Usage : python e2e/repository.py <dossier>."""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / 'backend'
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests')]
from test_spring_boot import repository  # noqa: E402


def write(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    for path, text in repository().items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    git = ['git', '-C', str(root), '-c', 'user.name=Taxo', '-c', 'user.email=taxo@example.invalid']
    subprocess.run([*git, 'init', '-q'], check=True)
    subprocess.run([*git, 'add', '-A'], check=True)
    subprocess.run([*git, 'commit', '-q', '-m', 'Boutique et administration'], check=True)


if __name__ == '__main__':
    write(Path(sys.argv[1]))
