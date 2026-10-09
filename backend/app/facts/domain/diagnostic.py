"""Les sites d'un diagnostic : leurs catégories génériques et leur identité locale (TAXO-01M).

Un analyseur possède ses diagnostics, Taxo possède les frontières. Le code d'un site (`reason`) appartient à son
producteur, qui le déclare dans son catalogue. La catégorie appartient au contrat commun : quatre valeurs fermées,
qu'aucun langage n'étend.
"""
from .identity import canonical_identity

UNKNOWN, AMBIGUOUS, UNSUPPORTED, OUT_OF_SCOPE = 'UNKNOWN', 'AMBIGUOUS', 'UNSUPPORTED', 'OUT_OF_SCOPE'
# Ordre fixe : celui dans lequel une Tuile énumère les catégories.
CATEGORIES = (UNKNOWN, AMBIGUOUS, UNSUPPORTED, OUT_OF_SCOPE)
_POSITION = ('reason', 'line_start', 'column_start', 'line_end', 'column_end')


def sites(coverage):
    """Les sites décrits par le diagnostic d'une couverture, dans leur ordre ; aucun sans diagnostic."""
    return (coverage.get('diagnostic') or {}).get('sites', [])


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
