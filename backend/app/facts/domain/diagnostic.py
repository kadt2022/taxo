"""Les sites d'un diagnostic : leurs catégories génériques et leur identité locale (TAXO-01M).

Un analyseur possède ses diagnostics, Taxo possède les frontières. Le code d'un site (`reason`) appartient à son
producteur, qui le déclare dans son catalogue. La catégorie appartient au contrat commun : quatre valeurs fermées,
qu'aucun langage n'étend.
"""
from collections import Counter

from .identity import canonical_identity

UNKNOWN, AMBIGUOUS, UNSUPPORTED, OUT_OF_SCOPE = 'UNKNOWN', 'AMBIGUOUS', 'UNSUPPORTED', 'OUT_OF_SCOPE'
# Ordre fixe : celui dans lequel une Tuile énumère les catégories.
CATEGORIES = (UNKNOWN, AMBIGUOUS, UNSUPPORTED, OUT_OF_SCOPE)
_POSITION = ('reason', 'line_start', 'column_start', 'line_end', 'column_end')


def sites(coverage):
    """Les sites décrits par le diagnostic d'une couverture, dans leur ordre ; aucun sans diagnostic."""
    return (coverage.get('diagnostic') or {}).get('sites', [])


def category_counts(coverage):
    """Le décompte des sites listés par catégorie, dans l'ordre fixe ; None pour un diagnostic non classé.

    Liste complète (`sites_seen` égal au nombre de sites listés) : chaque décompte est exact, et une catégorie
    absente vaut zéro. Liste tronquée : un site omis peut appartenir à n'importe quelle catégorie, donc les
    quatre catégories sont données, chacune « au moins » le nombre de sites listés, zéro compris. Un décompte
    n'est jamais inventé.
    """
    diagnostic = coverage.get('diagnostic') or {}
    if not diagnostic.get('classification'):
        return None
    listed = diagnostic.get('sites', [])
    counted = Counter(site['category'] for site in listed)
    if diagnostic.get('sites_seen', len(listed)) > len(listed):
        return [{'category': name, 'count': {'kind': 'AT_LEAST', 'value': counted[name]}} for name in CATEGORIES]
    return [{'category': name, 'count': {'kind': 'EXACT', 'value': counted[name]}}
            for name in CATEGORIES if counted[name]]


def site_keys(coverage):
    """La clé de chaque site d'une couverture validée, dans l'ordre de ses sites.

    Identité **locale** à ce diagnostic, jamais une identité de site dans le graphe : l'identité de la
    couverture, le code et la position du site, puis son rang parmi les sites de mêmes valeurs. Deux sites
    d'une même ligne diffèrent par leurs colonnes ; deux constats identiques gardent chacun leur rang et ne sont
    jamais fusionnés. Le rang ne porte aucun sens au-delà de cette analyse.
    """
    container = _frozen(canonical_identity(coverage))
    seen = {}
    keys = []
    for site in sites(coverage):
        position = tuple(site.get(name) for name in _POSITION)
        rank = seen.get(position, 0)
        seen[position] = rank + 1
        keys.append((container, *position, rank))
    return keys


def _frozen(value):
    """Une valeur d'identité canonique, rendue hachable et ordonnée sans perdre sa structure."""
    if isinstance(value, dict):
        return tuple((key, _frozen(value[key])) for key in sorted(value))
    if isinstance(value, list):
        return tuple(_frozen(item) for item in value)
    return value
