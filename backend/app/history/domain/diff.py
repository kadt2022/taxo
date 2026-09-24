"""Diff cote a cote d'un fichier : le parent a gauche, le commit a droite (TAXO-HIST-02).

Ce que Git montre, sans interpretation : l'impact compris par Taxo reste une autre fonction. Un contenu
n'est renvoye que s'il est affichable des deux cotes ; sinon, seule la raison est donnee.
"""
import difflib
from dataclasses import dataclass

MAX_DIFF_BYTES = 1024 * 1024
CONTEXT_LINES = 3

CONFIDENTIAL = 'CONFIDENTIAL'
BINARY = 'BINARY'
TOO_LARGE = 'TOO_LARGE'
NOT_A_REGULAR_FILE = 'NOT_A_REGULAR_FILE'


@dataclass(frozen=True)
class Blob:
    """Une version d'un fichier dans Git : identifiant, mode et taille, lus avant tout contenu."""

    oid: str
    mode: str
    size: int


def refusal(blobs):
    """Raison de ne pas lire les contenus, decidee sur les metadonnees seules ; None si lisibles."""
    present = [blob for blob in blobs if blob is not None]
    if any(blob.mode not in {'100644', '100755'} for blob in present):
        return NOT_A_REGULAR_FILE
    if any(blob.size > MAX_DIFF_BYTES for blob in present):
        return TOO_LARGE
    return None


def as_text(content):
    """Texte UTF-8, ou None pour un contenu binaire : un octet nul ou un decodage impossible."""
    if b'\x00' in content[:8192]:
        return None
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        return None


def _row(kind, before=None, after=None):
    return {'kind': kind, 'before': before, 'after': after}


def _line(number, text):
    return {'number': number, 'text': text}


def side_by_side(before, after, context=CONTEXT_LINES):
    """Blocs de lignes alignees ; chaque rangee porte la ligne de gauche, celle de droite, ou les deux."""
    left, right = before.splitlines(), after.splitlines()
    hunks = []
    for group in difflib.SequenceMatcher(None, left, right, autojunk=False).get_grouped_opcodes(context):
        rows = []
        for tag, i1, i2, j1, j2 in group:
            if tag == 'equal':
                rows += [_row('equal', _line(i + 1, left[i]), _line(j + 1, right[j]))
                         for i, j in zip(range(i1, i2), range(j1, j2))]
                continue
            removed = [_line(i + 1, left[i]) for i in range(i1, i2)]
            added = [_line(j + 1, right[j]) for j in range(j1, j2)]
            for index in range(max(len(removed), len(added))):
                old = removed[index] if index < len(removed) else None
                new = added[index] if index < len(added) else None
                rows.append(_row('changed' if old and new else 'removed' if old else 'added', old, new))
        first = group[0]
        hunks.append({'before_start': first[1] + 1, 'after_start': first[3] + 1, 'rows': rows})
    return hunks
