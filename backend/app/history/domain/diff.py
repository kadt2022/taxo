"""Diff cote a cote d'un fichier : le parent a gauche, le commit a droite (TAXO-HIST-02).

Ce que Git montre, sans interpretation : l'impact compris par Taxo reste une autre fonction. Un contenu
n'est renvoye que s'il est affichable des deux cotes ; sinon, seule la raison est donnee.
"""
import difflib
from dataclasses import dataclass

MAX_DIFF_BYTES = 1024 * 1024
CONTEXT_LINES = 3
# Au-dela, la comparaison exacte deviendrait quadratique : l'heuristique de difflib prend le relais. Son
# resultat reste un diff exact (il transforme bien l'avant en apres), seulement moins compact.
MAX_EXACT_COMPARISONS = 2_000_000

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


def lines(text):
    """Lignes au sens de Git, fin de ligne comprise : un passage de LF a CRLF, ou la perte du saut de
    ligne final, reste un changement visible."""
    parts = text.split('\n')
    found = [part + '\n' for part in parts[:-1]]
    if parts[-1]:
        found.append(parts[-1])
    return found


def _eol(raw):
    if raw.endswith('\r\n'):
        return 'CRLF'
    return 'LF' if raw.endswith('\n') else 'NONE'


def _line(number, raw):
    return {'number': number, 'text': raw.rstrip('\n').removesuffix('\r'), 'eol': _eol(raw)}


def _row(kind, before=None, after=None):
    return {'kind': kind, 'before': before, 'after': after}


def _opcodes(left, right):
    """Operations de diff, lignes communes du debut et de la fin mises a part avant toute comparaison."""
    prefix = 0
    while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < min(len(left), len(right)) - prefix
           and left[len(left) - 1 - suffix] == right[len(right) - 1 - suffix]):
        suffix += 1
    middle_left, middle_right = left[prefix:len(left) - suffix], right[prefix:len(right) - suffix]
    exact = len(middle_left) * len(middle_right) <= MAX_EXACT_COMPARISONS
    matcher = difflib.SequenceMatcher(None, middle_left, middle_right, autojunk=not exact)
    codes = [('equal', 0, prefix, 0, prefix)] if prefix else []
    codes += [(tag, i1 + prefix, i2 + prefix, j1 + prefix, j2 + prefix)
              for tag, i1, i2, j1, j2 in matcher.get_opcodes()]
    if suffix:
        codes.append(('equal', len(left) - suffix, len(left), len(right) - suffix, len(right)))
    return codes


def _groups(codes, context):
    """Blocs de changements avec `context` lignes autour, comme difflib.get_grouped_opcodes."""
    codes = [code for code in codes if code[1] != code[2] or code[3] != code[4]]
    if not codes:
        return []
    if codes[0][0] == 'equal':
        tag, i1, i2, j1, j2 = codes[0]
        codes[0] = tag, max(i1, i2 - context), i2, max(j1, j2 - context), j2
    if codes[-1][0] == 'equal':
        tag, i1, i2, j1, j2 = codes[-1]
        codes[-1] = tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)
    groups, group = [], []
    for tag, i1, i2, j1, j2 in codes:
        if tag == 'equal' and i2 - i1 > 2 * context:
            group.append((tag, i1, min(i2, i1 + context), j1, min(j2, j1 + context)))
            groups.append(group)
            group = []
            i1, j1 = max(i1, i2 - context), max(j1, j2 - context)
        group.append((tag, i1, i2, j1, j2))
    if group and not (len(group) == 1 and group[0][0] == 'equal'):
        groups.append(group)
    return groups


def side_by_side(before, after, context=CONTEXT_LINES):
    """Blocs de lignes alignees ; chaque rangee porte la ligne de gauche, celle de droite, ou les deux."""
    left, right = lines(before), lines(after)
    hunks = []
    for group in _groups(_opcodes(left, right), context):
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
