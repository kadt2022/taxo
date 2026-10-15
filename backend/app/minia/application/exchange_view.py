"""La vue de `describe` et de `get_neighborhood` pour le modèle (récit TAXO-RECIT-REDUCTION-PAYLOAD-MINIA, R4 ;
projection `vue-minia/2`).

Même principe que la vue des Tuiles (`tile_view`, R2) : Taxo sert la réponse entière, Minia la garde entière (garde de
conclusion, références reçues, vérification, preuves), et seul le message envoyé au modèle reçoit cette vue, construite
avant la protection de la demande (SEC-01). Liste blanche (SEC-02) : un champ ou un genre d'élément inconnu n'est jamais
transmis, son nom est signalé dans `projection.withheld` (SEC-08) ; un test de contrat échoue sur tout champ que Taxo rend
sans classement.

Trois étapes, séparées et testables :

- **B** — `describe` sans ses éléments `operation` : Minia envoie déjà au modèle la liste des opérations proposées
  (`operations`), tirée de ces mêmes éléments ; seules celles que Minia retient volontairement (`verify_claim`) n'y sont
  pas, et ne doivent pas l'être.
- **C** — le reste de `describe` en forme courte, de même sens : familles (type et nombre), relations (nom, nombre,
  types de sujet et d'objet), analyseurs (statut, relations, langages, restitution si mesurée), langages. La couverture,
  le consentement, l'instantané et `not_sent` sont transmis tels quels (SEC-05).
- **D** — `get_neighborhood` projeté comme une Tuile : chaque fait par la vue de `tile_view` (triplet, qualificatifs,
  statut, dérivation d'un fait déduit, preuves en une ligne) ; ancre, nœuds, nœuds non développés ou inconnus, frontière,
  raison d'arrêt, suite de page (`continuation`, argument accepté par `get_neighborhood`), couverture et `not_sent`
  transmis. Gardés par Minia : protocole, moteur, paramètres (redits par les arguments de l'étape), révision, bornes,
  consommation, identités et occurrences des faits, provenance.
"""
from app.minia.application import tile_view

VERSION = tile_view.STRICT_VERSION
SENT, CONDENSED, RETAINED = tile_view.SENT, tile_view.CONDENSED, tile_view.RETAINED

DESCRIBE_FIELDS = {
    'protocol': RETAINED, 'operation': RETAINED, 'outcome': SENT, 'snapshot': SENT, 'consent': SENT,
    'items': CONDENSED, 'evidence': SENT, 'coverage': SENT, 'not_sent': SENT, 'bytes': RETAINED, 'error': SENT,
}
# Les éléments de `describe`, par genre, et les champs connus de chacun.
DESCRIBE_ITEMS = {
    'operation': {'kind', 'operation', 'arguments', 'note'},
    'family': {'kind', 'type', 'count', 'source'},
    'relation': {'kind', 'relation', 'count', 'subject_types', 'object_types'},
    'analyzer': {'kind', 'analyzer', 'status', 'relations', 'languages', 'restitution'},
    'languages': {'kind', 'present', 'complete'},
}
NEIGHBORHOOD_FIELDS = {
    'protocol': RETAINED, 'operation': RETAINED, 'outcome': SENT, 'snapshot': SENT, 'engine_version': RETAINED,
    'parameters': RETAINED, 'facts_revision': RETAINED, 'bounds': RETAINED, 'consumed': RETAINED, 'anchor': SENT,
    'nodes': SENT, 'node_details': CONDENSED, 'frontier': SENT, 'stop_reason': SENT, 'continuation': SENT,
    'items': CONDENSED, 'evidence': SENT, 'coverage': SENT, 'not_sent': SENT, 'bytes': RETAINED, 'error': SENT,
}


def _marked(shown, withheld):
    shown['projection'] = {'version': VERSION, **({'withheld': sorted(set(withheld))} if withheld else {})}
    return shown


def _whitelisted(response, fields):
    withheld = [name for name in response if name not in fields]
    return {name: value for name, value in response.items() if fields.get(name) == SENT}, withheld


# --- B ---------------------------------------------------------------------------------------------------------

def describe_without_operations(response):
    """`describe` sans ses éléments `operation`, déjà envoyés au modèle dans `operations` (étape B seule)."""
    if not isinstance(response, dict) or response.get('outcome') != 'OK':
        return response
    return {**response, 'items': [item for item in response.get('items') or ()
                                  if not (isinstance(item, dict) and item.get('kind') == 'operation')]}


# --- C ---------------------------------------------------------------------------------------------------------

def describe_view(response):
    """La vue de `describe` (étapes B et C) : sans ses éléments `operation`, le reste en forme courte."""
    if not isinstance(response, dict):
        return response
    shown, withheld = _whitelisted(response, DESCRIBE_FIELDS)
    if response.get('outcome') != 'OK':
        return _marked(shown, withheld) if withheld else shown
    families, relations, analyzers, languages = {}, [], [], []
    for item in response.get('items') or ():
        kind = item.get('kind') if isinstance(item, dict) else None
        if kind not in DESCRIBE_ITEMS:
            withheld.append(f'items.{kind}')
            continue
        withheld += [f'items.{kind}.{name}' for name in item if name not in DESCRIBE_ITEMS[kind]]
        if kind == 'family':
            families[item.get('type')] = item.get('count')
        elif kind == 'relation':
            relations.append(f'{item.get("relation")} ({item.get("count")}) '
                             f'{"/".join(item.get("subject_types") or ())}→{"/".join(item.get("object_types") or ())}')
        elif kind == 'analyzer':
            analyzers.append(_analyzer(item))
        elif kind == 'languages':
            languages.append({name: item[name] for name in ('present', 'complete') if name in item})
    shown.update(families=families, relations=relations, analyzers=analyzers, languages=languages)
    return _marked(shown, withheld)


def _analyzer(item):
    """Un analyseur en forme courte ; sa restitution seulement si elle est mesurée (des sites ou des sujets comptés)."""
    restitution = item.get('restitution') or {}
    return {**{name: item[name] for name in ('analyzer', 'status', 'relations') if name in item},
            **({'languages': item['languages']} if item.get('languages') else {}),
            **({'restitution': restitution} if any(restitution.values()) else {})}


# --- D ---------------------------------------------------------------------------------------------------------

def neighborhood_view(response):
    """La vue d'un voisinage (étape D) : les faits comme dans une Tuile, les bornes et la provenance gardées."""
    if not isinstance(response, dict):
        return response
    shown, withheld = _whitelisted(response, NEIGHBORHOOD_FIELDS)
    if response.get('outcome') != 'OK':
        return _marked(shown, withheld) if withheld else shown
    details = [node for node in response.get('node_details') or () if isinstance(node, dict)]
    closed = [node.get('reference') for node in details if node.get('expanded') is False]
    unknown = [node.get('reference') for node in details if node.get('known') is False]
    if closed:
        shown['not_expanded'] = closed
    if unknown:
        shown['not_known'] = unknown
    items = []
    for item in response.get('items') or ():
        view, unclassified = tile_view.item_view(item, 'items', strict=True)
        items.append(view)
        withheld.extend(unclassified)
    shown['items'] = items
    tile_view._slimmed(shown, 'anchor', items)
    return _marked(shown, withheld)


# --- Contrat -----------------------------------------------------------------------------------------------------

def unclassified_describe(response):
    names = {name for name in response if name not in DESCRIBE_FIELDS}
    for item in response.get('items') or ():
        kind = item.get('kind')
        if kind not in DESCRIBE_ITEMS:
            names.add(f'items.{kind}')
            continue
        names |= {f'items.{kind}.{name}' for name in item if name not in DESCRIBE_ITEMS[kind]}
    return sorted(names)


def unclassified_neighborhood(response):
    names = {name for name in response if name not in NEIGHBORHOOD_FIELDS}
    for item in response.get('items') or ():
        names |= {f'items.{name}' for name in item if name not in tile_view.ITEM_FIELDS}
        names |= {f'items.fact.{name}' for name in item.get('fact') or {} if name not in tile_view.FACT_FIELDS}
    return sorted(names)
