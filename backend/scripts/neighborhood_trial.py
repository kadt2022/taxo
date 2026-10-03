"""Essai du voisinage sur un dépôt réel (TAXO-01J, tranche F) : reproductible, mesuré, jamais promis.

Analyse un dépôt Git à un commit donné, puis mesure, par l'API du protocole et dans le même processus :
- des Tuiles `neighborhood/2` depuis des ancres choisies sans rien nommer (la référence la plus connectée de
  chaque type présent, d'après les comptes de l'analyse), à profondeur 1 à 3, en forme complète et compacte ;
- `find_references` sur des préfixes courts.

Usage (depuis `backend`) :
    python scripts/neighborhood_trial.py <dépôt> <commit> [--database URL] [--repeat 5]

Sans `--database`, une base SQLite temporaire. Le résultat est un tableau Markdown sur la sortie standard.
"""
import argparse
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import create_app  # noqa: E402
from app.platform.database.base import Base  # noqa: E402

BUDGET = 32_000
STANDARD = {'max_nodes': 60, 'max_edges': 120, 'max_work': 300, 'max_fanout': 20}


class Trial:
    def __init__(self, client, project, scan, repeat):
        self.client, self.project, self.scan, self.repeat = client, project, scan, repeat

    def call(self, operation, **arguments):
        if operation in ('get_neighborhood', 'find_references'):
            arguments = {'analysis': self.scan, **arguments}
        response = self.client.post(f'/api/projects/{self.project}/taxo-query', json={
            'analysis': self.scan, 'requests': [{'operation': operation, 'max_bytes': BUDGET, 'arguments': arguments}]})
        response.raise_for_status()
        found, = response.json()['responses']
        return found

    def timed(self, operation, **arguments):
        """La réponse et le temps médian de `repeat` appels, en millisecondes."""
        durations, found = [], None
        for _ in range(self.repeat):
            start = time.perf_counter()
            found = self.call(operation, **arguments)
            durations.append((time.perf_counter() - start) * 1000)
        return found, statistics.median(durations)


def anchors(trial):
    """La référence la plus connectée de chaque type, comptée sur les assertions de l'analyse, lues par l'API : ni
    nom de type ni de relation écrit ici."""
    facts = trial.client.get(f'/api/projects/{trial.project}/scans/{trial.scan}/facts', params={'kind': 'ASSERTION'})
    facts.raise_for_status()
    degree = Counter()
    for fact in facts.json():
        for reference in (fact.get('subject'), fact.get('object')):
            if isinstance(reference, str) and ':' in reference:
                degree[reference] += 1
    best = {}
    for reference, count in degree.most_common():
        best.setdefault(reference.split(':', 1)[0], (reference, count))
    return sorted(best.values(), key=lambda item: -item[1])


def project_of(client, repository):
    """Le projet de ce dépôt : celui déjà enregistré pour ce chemin, sinon un nouveau."""
    known = [item['id'] for item in client.get('/api/projects').json() if item.get('path') == str(repository)]
    if known:
        return known[0]
    created = client.post('/api/projects', json={'name': repository.name, 'path': str(repository)})
    created.raise_for_status()
    return created.json()['id']


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('repository', type=Path)
    parser.add_argument('commit')
    parser.add_argument('--database')
    parser.add_argument('--repeat', type=int, default=5)
    options = parser.parse_args()
    repository = options.repository.resolve()
    database = options.database or f'sqlite:///{tempfile.mkdtemp(prefix="taxo-trial-")}/taxo.db'
    app = create_app(database, [repository], minia={})
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        project = project_of(client, repository)
        start = time.perf_counter()
        scanned = client.post(f'/api/projects/{project}/scans', params={'commit': options.commit})
        scanned.raise_for_status()
        analysis_seconds = time.perf_counter() - start
        trial = Trial(client, project, scanned.json()['id'], options.repeat)
        described = trial.call('describe')['items']
        relations = sorted(item['relation'] for item in described if item['kind'] == 'relation')
        facts = sum(item['count'] for item in described if item['kind'] == 'relation')
        print(f'# {repository.name} @ {options.commit[:7]} — {database.split(":", 1)[0]}\n')
        print(f'Analyse : {analysis_seconds:.1f} s, {facts} assertions, {len(relations)} relations.\n')
        report_tiles(trial, anchors(trial), relations)
        report_search(trial)


def report_tiles(trial, chosen, relations):
    print('| Ancre (degré) | Prof. | Forme | ms | Octets | Éléments | Nœuds | Arrêt | Non transmis |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for reference, count in chosen:
        for depth in (1, 2, 3):
            for form in ('FULL', 'COMPACT'):
                found, ms = trial.timed('get_neighborhood', engine='neighborhood/2', root=reference,
                                        follow=relations[:16], direction='BOTH', depth=depth, evidence='SUMMARY',
                                        form=form, **STANDARD)
                if found['outcome'] != 'OK':
                    print(f'| `{reference[:48]}` ({count}) | {depth} | {form} | {ms:.0f} | — | — | — | '
                          f'{found["error"]["code"]} | — |')
                    continue
                omitted = ', '.join(f'{entry["what"]} {entry.get("count", 1)}' for entry in found['not_sent']) or '—'
                print(f'| `{reference[:48]}` ({count}) | {depth} | {form} | {ms:.0f} | {found["bytes"]} | '
                      f'{len(found["items"])} | {len(found["nodes"])} | {found["stop_reason"]} | {omitted} |')


def report_search(trial):
    print('\n| Préfixe | ms | Références | Suite |')
    print('| --- | --- | --- | --- |')
    for prefix in ('a', 'src/', 'e', 'GET /'):
        found, ms = trial.timed('find_references', prefix=prefix, limit=50)
        print(f'| `{prefix}` | {ms:.1f} | {len(found.get("items", []))} | {"oui" if found.get("next") else "non"} |')


if __name__ == '__main__':
    main()
