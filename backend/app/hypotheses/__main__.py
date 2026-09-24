"""Poids des modeles de la capacite hypotheses.

    python -m app.hypotheses status [modele]
    python -m app.hypotheses fetch [modele] [--record]

`fetch` installe le modele : il telecharge la revision epinglee une seule fois dans TAXO_MODELS_DIR,
verifie chaque empreinte SHA-256, retelecharge un fichier altere et echoue si une empreinte ne
correspond pas. Il ne charge pas le modele en memoire.

`--record` est une operation de maintenance reservee au developpement de Taxo : il epingle un modele
qui ne l'est pas encore, et le models.json modifie doit etre relu puis commite.
"""
import argparse
import sys

from app.hypotheses.infrastructure.model_store import ModelStore, ModelStoreError

DEFAULT_MODEL = 'smollm2-135m'


def main(argv=None):
    parser = argparse.ArgumentParser(prog='app.hypotheses', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('status', 'fetch'))
    parser.add_argument('model', nargs='?', default=DEFAULT_MODEL)
    parser.add_argument('--record', action='store_true', help='maintenance de Taxo : epingler un modele non epingle')
    arguments = parser.parse_args(argv)
    store = ModelStore()
    try:
        if arguments.command == 'status':
            for filename, state in store.status(arguments.model).items():
                print(f'{state:9} {filename}')
            return 0
        print(store.ensure(arguments.model, record=arguments.record))
        return 0
    except (ModelStoreError, OSError) as exc:
        print(f'[Taxo] {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
