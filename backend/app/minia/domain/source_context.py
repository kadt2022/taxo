"""Le diff d'un commit, donne a Minia comme matiere d'interpretation (TAXO-MINIA-02, ADR 0008).

Taxo etablit, Git montre ce qui a change, Minia lit les deux et explique. Le diff n'est jamais un fait :
c'est du contexte documentaire, et ce que Minia en deduit reste une interpretation non verifiee.

Seuls les blocs modifies sont transmis (avec les quelques lignes de contexte que montre deja le diff),
jamais les fichiers entiers ni le reste du depot. Le contenu est lu par `ProjectHistory` avec ses refus :
un fichier confidentiel, binaire, trop gros, un lien ou un sous-module n'est jamais lu. Au-dela des
limites, un fichier n'est pas transmis ; il est nomme, avec sa raison, pour que la reponse le dise.
"""
import re
from dataclasses import dataclass, field

# Limites et fichiers generes : la politique de transmission du diff, commune au protocole (ADR 0008).
from app.history.domain.disclosure import (GENERATED, LIMIT, MAX_DIFF_BYTES, MAX_DIFF_FILES,
                                           MAX_DIFF_LINES, generated)

OFF, DIFF = 'off', 'diff'
MODES = (OFF, DIFF)


# Un fichier de test explique moins le risque d'un commit que le code qu'il teste : il passe apres.
_TEST_DIRECTORIES = frozenset({'test', 'tests', '__tests__', 'spec', 'specs', 'testing'})
_TEST_NAME = re.compile(r'test_.*\.py|.*_test\.[^.]+|.*(Test|Tests|IT)\.(java|kt|scala|groovy)|.*\.(test|spec)\.[^.]+')


def is_test(path):
    *directories, name = path.split('/')
    in_test_directory = bool(_TEST_DIRECTORIES.intersection(part.lower() for part in directories))
    return in_test_directory or bool(_TEST_NAME.fullmatch(name))


@dataclass
class DiffContext:
    """Ce qui est transmis a Minia, et ce qui ne l'est pas, avec la raison."""

    files: list = field(default_factory=list)
    not_sent: list = field(default_factory=list)
    lines: int = 0
    size: int = 0
    # Poids (lignes, octets) de chaque fichier transmis, dans le meme ordre ; jamais envoye au modele.
    weights: list = field(default_factory=list, repr=False)

    def drop_last(self):
        """Retire le dernier fichier transmis, faute de place dans la fenetre du modele."""
        entry, (lines, size) = self.files.pop(), self.weights.pop()
        self.lines, self.size = self.lines - lines, self.size - size
        self.not_sent.append({'path': entry['path'], 'reason': LIMIT})

    def summary(self):
        return {'status': 'SENT', 'files_sent': [item['path'] for item in self.files],
                'files_not_sent': list(self.not_sent), 'lines_sent': self.lines, 'bytes_sent': self.size}


def _side(rows, side):
    return '\n'.join(row[side]['text'] for row in rows if row[side] is not None)


def _hunk(hunk):
    return {'before_start': hunk['before_start'], 'after_start': hunk['after_start'],
            'before': _side(hunk['rows'], 'before'), 'after': _side(hunk['rows'], 'after')}


def _entry(diff):
    entry = {'path': diff['path'], 'status': diff['status'], 'hunks': [_hunk(item) for item in diff['hunks']]}
    if diff['old_path']:
        entry['old_path'] = diff['old_path']
    return entry


def _weight(diff, entry):
    lines = sum(len(hunk['rows']) for hunk in diff['hunks'])
    size = sum(len(hunk[side].encode('utf-8')) for hunk in entry['hunks'] for side in ('before', 'after'))
    return lines, size


def build(files, read, max_files=MAX_DIFF_FILES, max_lines=MAX_DIFF_LINES, max_bytes=MAX_DIFF_BYTES):
    """Contexte de diff d'un commit : `files` sont ses fichiers, `read(fichier)` rend le diff de l'un d'eux.

    Le code passe avant les tests : quand la place manque, ce sont les tests qui ne sont pas transmis.
    Aucun contenu n'est lu pour un fichier genere, ni une fois le nombre de fichiers atteint.
    """
    context = DiffContext()
    for changed in sorted(files, key=lambda item: is_test(item.path)):
        if generated(changed.path):
            context.not_sent.append({'path': changed.path, 'reason': GENERATED})
            continue
        if len(context.files) >= max_files:
            context.not_sent.append({'path': changed.path, 'reason': LIMIT})
            continue
        diff = read(changed)
        if not diff['displayable']:
            context.not_sent.append({'path': changed.path, 'reason': diff['reason']})
            continue
        entry = _entry(diff)
        lines, size = _weight(diff, entry)
        if context.lines + lines > max_lines or context.size + size > max_bytes:
            context.not_sent.append({'path': changed.path, 'reason': LIMIT})
            continue
        context.files.append(entry)
        context.weights.append((lines, size))
        context.lines, context.size = context.lines + lines, context.size + size
    return context
