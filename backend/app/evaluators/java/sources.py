"""Les sources Java d'un instantane, choisies, lues et analysees une fois pour tous les evaluateurs Java.

Le perimetre exclut les sorties de build et les sources de test (`src/test`), et le dit. Un fichier trop gros ou
non UTF-8 n'est pas lu : c'est une erreur de lecture declaree, jamais un fichier ignore en silence.
"""
from app.evaluations.domain.progress import silent
from app.facts import is_path
from app.snapshots.domain.errors import SnapshotError
from . import syntax

IGNORED = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '__pycache__', '.gradle', 'out'}
TEST_SOURCES = ('src', 'test')
MAX_SOURCE_BYTES = 1024 * 1024
PROGRESS_EVERY = 250
# Au-dela, une chaine de constantes (A cite B qui cite C...) n'est plus suivie ; sa valeur reste non resolue.
MAX_CONSTANT_ROUNDS = 8


def select(snapshot):
    """Sources Java du perimetre, et les dossiers exclus (sorties de build, sources de test)."""
    sources, excluded = [], set()
    for file in snapshot.iter_files():
        if not file.path.endswith('.java') or not is_path(file.path):
            continue
        outside = _outside_scope(file.path.split('/'))
        if outside:
            excluded.add(f'directory:{outside}')
        else:
            sources.append(file)
    return sources, excluded


def _outside_scope(parts):
    """Le dossier qui met ce chemin hors du perimetre, ou None."""
    for index, part in enumerate(parts[:-1]):
        if part in IGNORED:
            return '/'.join(parts[:index + 1])
        if tuple(parts[index:index + 2]) == TEST_SOURCES and index + 2 < len(parts):
            return '/'.join(parts[:index + 2])
    return None


def read(snapshot, sources, warnings, read_errors, progress=silent):
    """Contenu des sources lisibles, par chemin ; les autres sont ajoutees a `read_errors` avec un avertissement."""
    readable = [file for file in sources if file.size <= MAX_SOURCE_BYTES]
    for file in sources:
        if file.size > MAX_SOURCE_BYTES:
            warnings.append(f'Fichier Java trop volumineux, non lu : {file.path}')
            read_errors.append(f'file:{file.path}')
    contents, count = {}, 0
    try:
        for count, (path, data) in enumerate(snapshot.read_many(file.path for file in readable), 1):
            if count % PROGRESS_EVERY == 0 or count == len(readable):
                progress('reading', 'Fichiers Java lus', count, len(readable))
            if _utf8(data):
                contents[path] = data
            else:
                warnings.append(f'Fichier Java non UTF-8, non lu : {path}')
                read_errors.append(f'file:{path}')
    except SnapshotError as exc:
        remaining = [f'file:{file.path}' for file in readable[count:]]
        read_errors += remaining
        warnings.append(f'Erreur de lecture : {remaining[0] if remaining else "dépôt"} : {exc}')
    return contents


def _utf8(data):
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return False
    return True


def parse_all(contents):
    """Chaque fichier, lu avec les constantes de tous les autres : une constante qui en cite une autre
    (`Routes.USERS = Api.ROOT + "/users"`) se resout de proche en proche, jusqu'a ce que rien ne change. Tous les
    types des sources sont alors connus de chaque fichier."""
    known, parsed = {}, []
    for _ in range(MAX_CONSTANT_ROUNDS):
        parsed = [syntax.parse(path, data, known) for path, data in contents.items()]
        found = {}
        for java_file in parsed:
            found.update(java_file.constants())
        if found == known:
            break
        known = found
    return parsed
