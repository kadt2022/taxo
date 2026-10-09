"""La Tuile MIP 0.1 : une Tuile `neighborhood/2` rendue sous le contrat MIP (récit TAXO-01N / MIP-01 § 4.2).

Une présentation, jamais une seconde construction : chaque fait, nœud, preuve résumée, couverture et frontière
vient tel quel de la réponse du moteur. Ce qui s'ajoute ne dit que ce que cette réponse établit déjà : les bornes
demandées et appliquées, et si la Tuile a été coupée par un budget. Rien n'est renommé dans le domaine de la Maille.
"""
from app.mip.domain.query import VERSION

WIRE_OPERATION = 'get_neighborhood'
# Les arrêts dus à un budget : ce que la Tuile ne dit pas faute de place, jamais une absence dans la Maille.
# `DEPTH` (profondeur demandée atteinte) et `ROOT_UNKNOWN` (rien dans l'analyse) n'en sont pas.
BUDGET_STOPS = frozenset({'NODES', 'EDGES', 'WORK', 'BYTES', 'FANOUT'})


def failure(code, message, snapshot=None, expression=None):
    """Un refus : le code du registre existant et ce qu'il faut corriger, jamais un détail interne."""
    refused = {'mip': VERSION, 'expression': expression, 'outcome': 'ERROR', 'error': {'code': code, 'message': message}}
    if snapshot is not None:
        refused['snapshot'] = snapshot
    return refused


def _applied(envelope):
    bounds = envelope['bounds']
    return {'depth': envelope['parameters']['depth'], 'max_nodes': bounds['max_nodes'],
            'max_facts': bounds['max_edges'], 'max_bytes': bounds['max_bytes']}


def tile(query, envelope):
    """La Tuile MIP d'une réponse `OK` de `get_neighborhood` ; un refus du moteur reste un refus."""
    if envelope['outcome'] != 'OK':
        error = envelope['error']
        return failure(error['code'], error['message'], envelope.get('snapshot'), query.expression)
    stop, not_sent = envelope['stop_reason'], envelope['not_sent']
    return {
        'mip': VERSION,
        'expression': query.expression,
        'outcome': 'OK',
        'snapshot': envelope['snapshot'],
        'root': envelope['anchor'],
        'nodes': envelope['node_details'],
        'facts': envelope['items'],
        'coverage': envelope['coverage'],
        'frontier': envelope['frontier'],
        'bounds': {'requested': dict(query.bounds), 'applied': _applied(envelope),
                   'consumed': {'nodes': envelope['consumed']['nodes'], 'facts': envelope['consumed']['edges']}},
        'stop_reason': stop,
        'truncated': stop in BUDGET_STOPS or bool(not_sent),
        'not_sent': not_sent,
        'continuation': envelope['continuation'],
        'wire': {'protocol': envelope['protocol'], 'operation': WIRE_OPERATION,
                 'engine': envelope['engine_version'], 'facts_revision': envelope['facts_revision']},
    }
