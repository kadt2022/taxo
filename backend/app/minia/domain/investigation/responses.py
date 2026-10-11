"""Ce que le carnet retient d'une reponse de Taxo (recit TAXO-MINIA-ENQUETE-01, § 6.2 et § 10).

Lecture mecanique de la forme des reponses, jamais de leur sens : une Tuile (MIP `EXPAND` ou `get_neighborhood`)
donne son ancre, ses aretes, les noeuds qu'elle a developpes et sa frontiere localisee ; une piece source donne
un recu sans texte. Une frontiere de toute l'analyse (sans noeud) n'est pas une branche : elle reste dans la reponse
transmise, pas dans le carnet.
"""
import hashlib
import json

from .logbook import DeliveryKind, Edge, FrontierEntry, FrontierKind, ReceiptStatus, SourceReceipt

TILE_OPERATIONS = frozenset({'get_tile', 'get_neighborhood'})
SOURCE_OPERATION = 'get_source'
EVIDENCE_OPERATION = 'get_evidence'
# Les operations dont un resultat peut etre rejoue depuis la memoire vive de la session : jamais le code ni un diff.
REPLAYABLE = frozenset({'get_tile', 'get_neighborhood', 'find_references', 'get_evidence', 'describe'})
_NATURES = {kind.value: kind for kind in (FrontierKind.SELECTION, FrontierKind.KNOWLEDGE, FrontierKind.CONTEXT)}
OK = 'OK'
# Une ligne de code plus courte (accolade, `return x;`) est trop commune pour signer une recopie.
MIN_COPIED_CHARS = 20


def fingerprint(response) -> str:
    """L'empreinte d'une reponse, sans la conserver : deux reponses identiques ont la meme."""
    text = json.dumps(response, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str)
    return 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()


def delivery_kind(operation) -> DeliveryKind:
    if operation in TILE_OPERATIONS:
        return DeliveryKind.TILE
    if operation == SOURCE_OPERATION:
        return DeliveryKind.SOURCE
    if operation == EVIDENCE_OPERATION:
        return DeliveryKind.EVIDENCE
    return DeliveryKind.FACT


def mip_reference(operation, arguments, response) -> str:
    """La reference MIP d'une livraison : celle que la demande visait, telle que Taxo l'a rendue s'il l'a rendue."""
    root = _root(response) if isinstance(response, dict) else None
    if root is not None:
        return root['reference']
    for name in ('reference', 'root', 'fact', 'occurrence', 'commit', 'prefix'):
        value = arguments.get(name)
        if isinstance(value, str) and value:
            return value
        value = response.get(name) if isinstance(response, dict) else None
        if isinstance(value, str) and value:
            return value
    return f'operation:{operation}'


def tile_parts(response):
    """L'ancre, les aretes, la frontiere par noeud et les noeuds developpes d'une Tuile ; None si la reponse n'en
    est pas une utilisable (refus, ancre inconnue)."""
    if not isinstance(response, dict) or response.get('outcome') != OK:
        return None
    root = _root(response)
    if root is None or not root.get('known'):
        return None
    edges = []
    for item in response.get('facts', response.get('items', [])):
        fact = item.get('fact', item) if isinstance(item, dict) else {}
        source, relation, target = fact.get('subject'), fact.get('relation'), fact.get('object')
        if all(isinstance(value, str) and value for value in (source, relation, target)):
            edges.append(Edge(source, relation, target, item.get('occurrence')))
    frontier = []
    for entry in response.get('frontier', []):
        kind = _NATURES.get(entry.get('nature')) if isinstance(entry, dict) else None
        if kind is not None and isinstance(entry.get('node'), str):
            frontier.append(FrontierEntry(entry['node'], kind, str(entry.get('reason', '')),
                                          entry.get('continuation')))
    expanded = tuple(node['reference'] for node in _details(response)
                     if isinstance(node, dict) and node.get('expanded') and isinstance(node.get('reference'), str)
                     and node['reference'] != root['reference'])
    return root['reference'], tuple(edges), tuple(frontier), expanded


def _root(response):
    """L'ancre d'une Tuile : `root` d'une Tuile MIP, `anchor` d'un voisinage du protocole."""
    root = response.get('root', response.get('anchor'))
    return root if isinstance(root, dict) and isinstance(root.get('reference'), str) else None


def _details(response):
    """Les noeuds detailles d'une Tuile : `nodes` d'une Tuile MIP, `node_details` d'un voisinage du protocole."""
    nodes = response.get('node_details', response.get('nodes', []))
    return nodes if isinstance(nodes, list) else []


def source_receipt(arguments, response, transmission_id) -> SourceReceipt | None:
    """Le recu d'une lecture de code : livree, tronquee ou refusee, avec la raison ; jamais le texte."""
    reference = arguments.get('reference')
    if not isinstance(reference, str) or not reference:
        return None
    if not isinstance(response, dict) or response.get('outcome') != OK:
        code = (response or {}).get('error', {}).get('code', 'ERROR') if isinstance(response, dict) else 'ERROR'
        return SourceReceipt(reference, transmission_id, ReceiptStatus.REFUSED, reason=str(code))
    classification = ','.join(response.get('classification', {}).get('content', []))
    piece = next((item for item in response.get('items', []) if isinstance(item, dict)), None)
    if piece is None:
        reason = next((str(item.get('reason', '')) for item in response.get('not_sent', []) if isinstance(item, dict)),
                      '')
        return SourceReceipt(reference, transmission_id, ReceiptStatus.REFUSED, classification, reason=reason)
    status = ReceiptStatus.TRUNCATED if piece.get('truncated') else ReceiptStatus.DELIVERED
    return SourceReceipt(reference, transmission_id, status, classification, piece.get('content_hash'))


def not_sent(response) -> tuple:
    """Ce que Taxo a retenu de sa reponse, tel qu'il le dit : quoi et pourquoi, sans valeur."""
    if not isinstance(response, dict):
        return ()
    return tuple({key: item[key] for key in ('what', 'reason', 'count') if key in item}
                 for item in response.get('not_sent', []) if isinstance(item, dict))


def _flat(text):
    return ' '.join(text.split())


def source_lines(response) -> tuple:
    """Les lignes du code qu'une lecture a livre, espaces normalises, assez longues pour signer une recopie."""
    if not isinstance(response, dict) or response.get('outcome') != OK:
        return ()
    lines = (_flat(line) for item in response.get('items', []) if isinstance(item, dict)
             and isinstance(item.get('text'), str) for line in item['text'].splitlines())
    return tuple(line for line in lines if len(line) >= MIN_COPIED_CHARS)


def copies_source(text, lines) -> bool:
    """Le texte reprend-il une ligne du code livre ? Une note cite un symbole, elle ne recopie pas son code (§ 11)."""
    flat = _flat(text) if isinstance(text, str) else ''
    return any(line in flat for line in lines)
