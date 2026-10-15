"""Ce qu'une réponse de Taxo donne au modèle pour décider, entière ou dans sa vue (récit
TAXO-RECIT-REDUCTION-PAYLOAD-MINIA, R4 ; principe : la plus petite représentation **suffisante**).

Une vue ne vaut que si elle garde tout ce qui sert à explorer et à justifier : les références citables, chaque fait avec
son statut, ses qualificatifs, sa dérivation et ses preuves, la frontière, la couverture (exclusions comprises), ce qui
n'a pas été transmis, la troncature et la suite de page. `essentials(operation, réponse)` rend cet ensemble pour une
réponse entière ; `essentials(operation, vue, view=True)`, pour sa vue. Les deux doivent être égaux : sinon la vue a
perdu une information utile à la décision, quel que soit le gain en octets. Sert aux tests et au rejeu sans modèle ;
n'intervient pas dans l'échange.
"""
import json

from app.minia.application import exchange_view, tile_view


def _frozen(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _fact(item, view):
    fact = item.get('fact') or {}
    derivation = fact.get('derivation') or {}
    evidence = item.get('evidence') or ()
    proofs = tuple(proof if view else tile_view._proof(proof) for proof in evidence if proof)
    counter = (derivation.get('counter_examples') if view
               else len(derivation.get('counter_examples_checked') or ()) or None)
    return (item.get('ref'), fact.get('subject'), fact.get('relation'), fact.get('object'), fact.get('status'),
            _frozen(fact.get('qualifiers') or {}), derivation.get('rule'), tuple(derivation.get('premises') or ()),
            tuple(derivation.get('known_gaps') or ()), counter, proofs, _frozen(item.get('selection')),
            item.get('level'), item.get('evidence_count'))


def _graph(response, facts_key, anchor_key, view):
    """Une Tuile ou un voisinage : faits, références, frontière, couverture et limites."""
    if response.get('outcome') != 'OK':
        return {'outcome': response.get('outcome'), 'error': _frozen(response.get('error'))}
    facts = [_fact(item, view) for item in response.get(facts_key) or ()]
    anchor = (response.get(anchor_key) or {})
    nodes = response.get('nodes')
    if view:
        listed = (nodes.get('references') or []) if isinstance(nodes, dict) else (nodes or [])
        closed = (nodes.get('not_expanded') or []) if isinstance(nodes, dict) else (response.get('not_expanded') or [])
        unknown = response.get('not_known') or []
        known = anchor.get('known', True)
    else:
        details = nodes if facts_key == 'facts' else (response.get('node_details') or [])
        listed = [node.get('reference') if isinstance(node, dict) else node for node in (nodes or [])]
        closed = [node.get('reference') for node in details if isinstance(node, dict) and node.get('expanded') is False]
        unknown = [] if facts_key == 'facts' else [
            node.get('reference') for node in details if isinstance(node, dict) and node.get('known') is False]
        known = anchor.get('known', True)
    references = set(listed) | {fact[1] for fact in facts} | {fact[3] for fact in facts} | {anchor.get('reference')}
    profile = response.get('profile') or {}
    return {
        'facts': sorted(map(_frozen, facts)), 'references': sorted(filter(None, references)),
        'not_expanded': sorted(closed), 'not_known': sorted(unknown), 'anchor': anchor.get('reference'),
        'anchor_known': known, 'analysis': (response.get('snapshot') or {}).get('analysis'),
        'frontier': _frozen(response.get('frontier')), 'coverage': _frozen(response.get('coverage')),
        'not_sent': _frozen(response.get('not_sent')), 'truncated': response.get('truncated'),
        'stop_reason': response.get('stop_reason'), 'continuation': response.get('continuation'),
        'limits': _frozen(profile.get('limits')),
    }


def _describe(response, view):
    if response.get('outcome') != 'OK':
        return {'outcome': response.get('outcome'), 'error': _frozen(response.get('error'))}
    if view:
        families = response.get('families') or {}
        relations = sorted(response.get('relations') or [])
        analyzers = sorted(_frozen(item) for item in response.get('analyzers') or [])
        languages = sorted(_frozen(item) for item in response.get('languages') or [])
    else:
        items = response.get('items') or []
        families = {item['type']: item['count'] for item in items if item.get('kind') == 'family'}
        relations = sorted(f'{item["relation"]} ({item["count"]}) {"/".join(item.get("subject_types") or ())}'
                           f'→{"/".join(item.get("object_types") or ())}' for item in items if item.get('kind') == 'relation')
        analyzers = sorted(_frozen(exchange_view._analyzer(item)) for item in items if item.get('kind') == 'analyzer')
        languages = sorted(_frozen({name: item[name] for name in ('present', 'complete') if name in item})
                           for item in items if item.get('kind') == 'languages')
    return {'families': _frozen(families), 'relations': relations, 'analyzers': analyzers, 'languages': languages,
            'coverage': _frozen(response.get('coverage')), 'not_sent': _frozen(response.get('not_sent')),
            'consent': _frozen(response.get('consent')), 'snapshot': _frozen(response.get('snapshot'))}


def essentials(operation, response, view=False):
    """Ce que la réponse (ou sa vue) donne au modèle pour décider ; None si l'opération n'a pas de vue."""
    if not isinstance(response, dict):
        return None
    if operation == 'get_tile':
        return _graph(response, 'facts', 'root', view)
    if operation == 'get_neighborhood':
        return _graph(response, 'items', 'anchor', view)
    if operation == 'describe':
        return _describe(response, view)
    return None


def lost(operation, response, shown):
    """Les informations utiles que la vue a perdues : vide si la vue est suffisante."""
    full, kept = essentials(operation, response), essentials(operation, shown, view=True)
    if full is None or kept is None:
        return {}
    return {name: (full[name], kept.get(name)) for name in full if full[name] != kept.get(name)}
