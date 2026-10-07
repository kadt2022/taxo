"""Essai des appels Java sur un dépôt réel (TAXO-01K, PR D) : reproductible, mesuré, jamais promis.

Analyse un dépôt Git à un commit donné par l'API, puis dit, depuis les faits de l'analyse :
- la durée de l'analyse et celle de `taxo.java-calls` ;
- les sites d'appel vus, résolus et non interprétés, et la distribution des raisons d'arrêt ;
- les faits produits par relation ;
- depuis chaque route, la Tuile qui suit `HANDLED_BY` puis `CALLS` : octets, éléments, arrêt.

Usage (depuis `backend`) :
    python scripts/java_calls_trial.py <dépôt> <commit> [--database URL]

Sans `--database`, une base SQLite temporaire. Le résultat est du Markdown sur la sortie standard.
"""
import argparse
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import create_app  # noqa: E402
from app.platform.database.base import Base  # noqa: E402

PRODUCER = 'taxo.java-calls'
BUDGET = 32_000


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('repository', type=Path)
    parser.add_argument('commit')
    parser.add_argument('--database')
    options = parser.parse_args()
    repository = options.repository.resolve()
    if options.database:
        run(options.database, repository, options.commit)
        return
    with tempfile.TemporaryDirectory(prefix='taxo-trial-') as folder:
        run(f'sqlite:///{folder}/taxo.db', repository, options.commit)


def run(database, repository, commit):
    app = create_app(database, [repository], minia={})
    Base.metadata.create_all(app.state.engine)
    try:
        with TestClient(app) as client:
            created = client.post('/api/projects', json={'name': repository.name, 'path': str(repository)})
            created.raise_for_status()
            base = f'/api/projects/{created.json()["id"]}'
            start = time.perf_counter()
            scanned = client.post(f'{base}/scans', params={'commit': commit})
            scanned.raise_for_status()
            seconds = time.perf_counter() - start
            analysis = scanned.json()
            print(f'# {repository.name} @ {commit[:7]} — {database.split(":", 1)[0]}\n')
            report_analysis(analysis, seconds)
            facts = client.get(f'{base}/scans/{analysis["id"]}/facts', params={'evaluator': PRODUCER}).json()
            report_sites(facts)
            report_tiles(client, base, analysis['id'])
    finally:
        app.state.engine.dispose()


def report_analysis(analysis, seconds):
    mine = next(item for item in analysis['evaluations'] if item['evaluator_id'] == PRODUCER)
    print(f'Analyse complète : {seconds:.1f} s. `{PRODUCER}` : {mine["status"]}, {mine["duration_seconds"]} s.\n')
    print('| Évaluateur | Durée (s) | Faits |')
    print('| --- | --- | --- |')
    for item in analysis['evaluations']:
        print(f'| `{item["evaluator_id"]}` | {item["duration_seconds"]} | {item["fact_count"]} |')
    print()


def report_sites(facts):
    relations = Counter((fact['relation'], fact['status']) for fact in facts if fact['kind'] == 'ASSERTION')
    calls = [fact for fact in facts if fact.get('relation') == 'CALLS']
    resolved = sum(len(fact['evidence']) for fact in calls)
    unread = [site for fact in facts if fact['kind'] == 'COVERAGE'
              for site in (fact.get('diagnostic') or {}).get('sites', [])]
    seen = resolved + len(unread)
    print(f'Sites d\'appel : {seen} vus, {resolved} résolus ({len(calls)} arêtes `CALLS`), '
          f'{len(unread)} non interprétés.\n')
    print('| Raison d\'arrêt | Sites |')
    print('| --- | --- |')
    for reason, count in Counter(site['reason'] for site in unread).most_common():
        print(f'| `{reason}` | {count} |')
    print('\n| Relation | Statut | Faits |')
    print('| --- | --- | --- |')
    for (relation, status), count in sorted(relations.items()):
        print(f'| `{relation}` | {status} | {count} |')
    print()


def report_tiles(client, base, scan):
    routes = client.get(f'{base}/scans/{scan}/facts', params={'relation': 'HANDLED_BY'}).json()
    print('| Route | ms | Octets | Éléments | `CALLS` | Arrêt | Causes en frontière |')
    print('| --- | --- | --- | --- | --- | --- | --- |')
    for root in sorted({fact['subject'] for fact in routes}):
        start = time.perf_counter()
        response = client.post(f'{base}/taxo-query', json={'analysis': scan, 'requests': [{
            'operation': 'get_neighborhood', 'max_bytes': BUDGET, 'arguments': {
                'analysis': scan, 'engine': 'neighborhood/2', 'root': root, 'follow': ['HANDLED_BY', 'CALLS'],
                'direction': 'OUTGOING', 'depth': 3}}]})
        ms = (time.perf_counter() - start) * 1000
        found, = response.json()['responses']
        if found['outcome'] != 'OK':
            print(f'| `{root}` | {ms:.0f} | — | — | — | {found["error"]["code"]} | — |')
            continue
        calls = sum(1 for item in found['items'] if item['fact']['relation'] == 'CALLS')
        causes = Counter(cause for entry in found['frontier'] for cause in entry.get('causes', []))
        said = ', '.join(f'{cause} {count}' for cause, count in sorted(causes.items())) or '—'
        print(f'| `{root}` | {ms:.0f} | {found["bytes"]} | {len(found["items"])} | {calls} | '
              f'{found["stop_reason"]} | {said} |')


if __name__ == '__main__':
    main()
