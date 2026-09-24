"""Impact d'un commit sur les chaines d'autorisation, en JSON. Jetable, comme le POC.

    py -m poc.authchain.impact --root <depot> --commit <sha> [--parent <sha>]

Le POC analyse chaque route du parent puis du commit ; les faits sont compares par identite, avec la
meme comparaison que l'historique de Taxo. Le resultat est marque `provisional` : l'analyseur Spring
lit le Java par expressions regulieres.
"""
import argparse
import json
import sys

from app.evaluations.application.run_evaluator import RunEvaluator
from app.evaluations.domain.status import EvaluationStatus
from app.facts import fact_identity
from app.history.domain.errors import UNKNOWN_PARENT, HistoryError
from app.history.domain.impact import compare, unknowns
from app.history.infrastructure.git_history import GitHistoryReader
from app.snapshots.domain.mode import COMMIT
from app.snapshots.infrastructure.git.reader import open_snapshot

from .evaluator import AuthorizationChainPoc


def impact(root, commit, parent=None, repository='poc'):
    found = GitHistoryReader().commit(root, commit)
    base = parent or (found.parents[0] if found.parents else None)
    if base is not None and base not in found.parents:
        raise HistoryError(UNKNOWN_PARENT, "Ce commit n'a pas ce parent.")
    run = RunEvaluator()
    after = run(AuthorizationChainPoc(), open_snapshot(root, repository, COMMIT, found.sha))
    before = run(AuthorizationChainPoc(), open_snapshot(root, repository, COMMIT, base)) if base else None
    failed = [execution for execution in (before, after)
              if execution is not None and execution.status is EvaluationStatus.FAILED]
    changes, unchanged = ([], 0) if failed else compare(before.facts if before else (), after.facts,
                                                        fact_identity)
    return {'commit': found.sha, 'parent': base, 'provisional': True, 'comparable': not failed,
            'failures': [warning for execution in failed for warning in execution.warnings],
            'evaluator_id': AuthorizationChainPoc.evaluator_id,
            'producer_version': AuthorizationChainPoc.producer_version,
            'changes': changes, 'unchanged_count': unchanged,
            'not_interpreted_after': unknowns(after.coverage)}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='poc.authchain.impact', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', required=True, help='racine du depot Git a lire')
    parser.add_argument('--commit', required=True, help='commit etudie, 40 ou 64 hexadecimaux')
    parser.add_argument('--parent', help='parent de comparaison ; le premier par defaut')
    arguments = parser.parse_args(argv)
    try:
        result = impact(arguments.root, arguments.commit, arguments.parent)
    except HistoryError as exc:
        print(f'{exc.code} : {exc}', file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
