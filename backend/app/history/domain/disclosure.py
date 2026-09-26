"""Ce que Taxo accepte de transmettre du diff d'un commit a un modele (ADR 0008).

Les memes limites valent pour le paquet de Minia et pour les lectures a la demande du protocole
(`get_diff`, ADR 0009) : des fichiers generes jamais lus, et un total borne en fichiers, lignes et octets.
Au-dela, un fichier n'est pas tronque : il n'est pas transmis.
"""
MAX_DIFF_FILES = 20
MAX_DIFF_LINES = 1500
# 32 Ko, environ 11 000 tokens : le diff tient avec les faits dans la fenetre par defaut de Minia (16 384).
MAX_DIFF_BYTES = 32 * 1024

LIMIT, GENERATED = 'LIMIT', 'GENERATED'
# Fichiers produits par un outil : volumineux, sans intention d'auteur a interpreter.
_GENERATED = frozenset({
    'package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb', 'poetry.lock',
    'pipfile.lock', 'uv.lock', 'cargo.lock', 'go.sum', 'composer.lock', 'gemfile.lock', 'gradle.lockfile'})
_GENERATED_SUFFIXES = ('.min.js', '.min.css', '.map', '.snap')


def generated(path):
    name = path.rsplit('/', 1)[-1].lower()
    return name in _GENERATED or name.endswith(_GENERATED_SUFFIXES)
