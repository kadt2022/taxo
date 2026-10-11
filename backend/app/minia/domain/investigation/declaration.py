"""La declaration finale du modele, confrontee au journal des livraisons (recit TAXO-MINIA-ENQUETE-01, § 10).

Le modele declare les elements MIP qu'il dit avoir utilises : une reference exactement recue, l'identifiant de la
livraison qui la lui a apportee et sa nature. Minia compare des **identifiants**, jamais une phrase : une
correspondance atteste une livraison, pas une lecture ni une interpretation juste. Une discordance est une
discordance de tracabilite, jamais la refutation d'une idee. Aucun verdict sur le fond (INV-01, INV-07).
"""
from dataclasses import dataclass

from .logbook import DeliveryKind, Logbook

MAX_ITEMS = 50
MAX_UNKNOWNS = 20
MAX_TEXT = 4000


class Trace:
    """L'issue de la confrontation d'un element declare au journal B."""
    DELIVERED = 'DELIVERED'  # livre au modele, sous cette reference et cette nature
    UNKNOWN_DELIVERY = 'UNKNOWN_DELIVERY'  # aucune livraison de cet identifiant dans l'enquete
    REFERENCE_MISMATCH = 'REFERENCE_MISMATCH'  # la livraison portait une autre reference
    KIND_MISMATCH = 'KIND_MISMATCH'  # la livraison etait d'une autre nature
    MALFORMED = 'MALFORMED'  # element illisible : rien n'est atteste


@dataclass(frozen=True)
class Declaration:
    answer: str
    items: tuple  # dicts : mip_reference, delivery_id, kind (tels que declares)
    remaining_unknowns: tuple
    # Vrai si la sortie n'avait pas la forme exigee (liste absente, champ manquant) : signale, jamais corrige.
    malformed: bool = False


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ''


def parse(data: dict) -> Declaration:
    """La declaration telle que le modele l'a rendue, bornee. Une forme inattendue est marquee, pas devinee."""
    items, unknowns = data.get('used_mip_items'), data.get('remaining_unknowns')
    malformed = not isinstance(items, list) or not isinstance(unknowns, list)
    kept = []
    for item in (items if isinstance(items, list) else [])[:MAX_ITEMS]:
        entry = {name: _text(item.get(name), 500) if isinstance(item, dict) else ''
                 for name in ('mip_reference', 'delivery_id', 'kind')}
        kept.append(entry)
    values = unknowns[:MAX_UNKNOWNS] if isinstance(unknowns, list) else []
    remaining = tuple(text for text in (_text(value, 500) for value in values) if text)
    return Declaration(_text(data.get('answer'), MAX_TEXT), tuple(kept), remaining, malformed)


def confronted(declaration: Declaration, logbook: Logbook) -> list:
    """Chaque element declare et son issue face au journal des livraisons de cette enquete."""
    traced = []
    for item in declaration.items:
        traced.append({**item, 'trace': _trace(item, logbook)})
    return traced


def _trace(item, logbook):
    if not all(item.get(name) for name in ('mip_reference', 'delivery_id', 'kind')):
        return Trace.MALFORMED
    if item['kind'] not in {kind.value for kind in DeliveryKind}:
        return Trace.MALFORMED
    delivery = logbook.delivery(item['delivery_id'])
    if delivery is None:
        return Trace.UNKNOWN_DELIVERY
    if delivery.mip_reference != item['mip_reference']:
        return Trace.REFERENCE_MISMATCH
    if delivery.kind.value != item['kind']:
        return Trace.KIND_MISMATCH
    return Trace.DELIVERED
