"""Produit la chaine d'autorisation d'une route, en JSON, pour le banc du POC.

    py -m poc.authchain --repository <cle> --root <chemin> --commit <sha> --target "GET /chemin"
"""
import argparse
import json
import sys

from app.evaluations.application.run_evaluator import RunEvaluator
from app.snapshots.domain.mode import COMMIT
from app.snapshots.infrastructure.git.reader import open_snapshot

from .evaluator import AuthorizationChainPoc


def run(arguments):
    snapshot = open_snapshot(arguments.root, arguments.repository, COMMIT, arguments.commit)
    execution = RunEvaluator()(AuthorizationChainPoc(arguments.target), snapshot)
    return {'summary': execution.summary(),
            'facts': list(execution.facts),
            'coverage': list(execution.coverage),
            'warnings': list(execution.warnings)}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='poc.authchain', description=__doc__)
    parser.add_argument('--root', required=True, help='racine du depot Git a lire')
    parser.add_argument('--repository', required=True, help='cle du depot dans les faits')
    parser.add_argument('--commit', required=True, help='commit a lire, 40 ou 64 hexadecimaux')
    parser.add_argument('--target', required=True, help="route etudiee, par exemple 'GET /api/x'")
    arguments = parser.parse_args(argv)
    result = run(arguments)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write('\n')
    return 0 if result['summary']['status'] == 'SUCCESS' else 1


if __name__ == '__main__':
    sys.exit(main())
