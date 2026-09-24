"""Relier un diff a l'impact : quels faits changes par un commit ont leur preuve dans ce fichier (TAXO-HIST-03).

Le lien passe uniquement par les preuves des faits, jamais par une lecture du texte : un fait est relie a
un fichier si l'une de ses preuves avant porte sur l'ancien chemin, ou l'une de ses preuves apres sur le
nouveau. Le lien est dit LINE quand la plage de lignes d'une preuve recouvre une ligne modifiee du diff,
FILE sinon (preuve sans lignes, ou lignes de preuve restees identiques).
"""
LINE = 'LINE'
FILE = 'FILE'


def _modified(hunks, side):
    return {row[side]['number'] for hunk in hunks for row in hunk['rows']
            if row['kind'] != 'equal' and row[side] is not None}


def _anchored(evidence, path, modified):
    """Lignes modifiees couvertes par les preuves de ce fichier ; None si aucune preuve n'y porte."""
    spans = [item for item in evidence if item.get('path') == path]
    if not spans:
        return None
    return sorted({number for item in spans if 'line_start' in item
                   for number in modified if item['line_start'] <= number <= item['line_end']})


def link(changes, before_path, after_path, hunks):
    """Faits changes dont une preuve porte sur ce fichier, avec les lignes modifiees qu'ils recouvrent."""
    modified = {'before': _modified(hunks, 'before'), 'after': _modified(hunks, 'after')}
    linked = []
    for change in changes:
        lines = {
            'before': _anchored(change['evidence_before'], before_path, modified['before']) if before_path else None,
            'after': _anchored(change['evidence_after'], after_path, modified['after']) if after_path else None,
        }
        if lines['before'] is None and lines['after'] is None:
            continue
        lines = {side: numbers or [] for side, numbers in lines.items()}
        precision = LINE if lines['before'] or lines['after'] else FILE
        linked.append({**change, 'precision': precision, 'lines': lines})
    linked.sort(key=lambda item: item['precision'] != LINE)
    return linked
