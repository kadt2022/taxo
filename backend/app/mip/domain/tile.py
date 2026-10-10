"""La Tuile MIP 0.1 : une Tuile `neighborhood/2` rendue sous le contrat MIP (récit TAXO-01N / MIP-01 § 4.2).

Une présentation, jamais une seconde construction : chaque fait, nœud, preuve résumée, couverture et frontière
vient tel quel de la réponse du moteur. Ce qui s'ajoute ne dit que ce que cette réponse établit déjà : les bornes
demandées et appliquées, et si la Tuile a été coupée par un budget. Rien n'est renommé dans le domaine de la Maille.
"""
from app.mip.domain.query import CONTINUATION, EXPRESSION, VERSION
from app.protocol.domain.envelope import BUDGET_EXHAUSTED, size

WIRE_OPERATION = 'get_neighborhood'
# Les arrêts dus à un budget : ce que la Tuile ne dit pas faute de place, jamais une absence dans la Maille.
# `DEPTH` (profondeur demandée atteinte) et `ROOT_UNKNOWN` (rien dans l'analyse) n'en sont pas.
BUDGET_STOPS = frozenset({'NODES', 'EDGES', 'WORK', 'BYTES', 'FANOUT'})
SNAPSHOT, BOUNDS, NODES, MAX_BYTES = 'snapshot', 'bounds', 'nodes', 'max_bytes'


def failure(code, message, snapshot=None, expression=None):
    """Un refus : le code du registre existant et ce qu'il faut corriger, jamais un détail interne."""
    refused = {'mip': VERSION, EXPRESSION: expression, 'outcome': 'ERROR', 'error': {'code': code, 'message': message}}
    if snapshot is not None:
        refused[SNAPSHOT] = snapshot
    return refused


def _bounds(query, envelope):
    """Ce qui a été demandé, ce que le serveur a appliqué après plafonnement, et ce que la Tuile a consommé."""
    limits, consumed = envelope[BOUNDS], envelope['consumed']
    applied = {'depth': envelope['parameters']['depth'], 'max_nodes': limits['max_nodes'],
               'max_facts': limits['max_edges'], MAX_BYTES: limits[MAX_BYTES]}
    return {'requested': dict(query.bounds), 'applied': applied,
            'consumed': {NODES: consumed[NODES], 'facts': consumed['edges']}}


def tile(query, envelope):
    """La Tuile MIP d'une réponse `OK` de `get_neighborhood` ; un refus du moteur reste un refus."""
    if envelope['outcome'] != 'OK':
        error = envelope['error']
        return failure(error['code'], error['message'], envelope.get(SNAPSHOT), query.expression)
    stop, not_sent = envelope['stop_reason'], envelope['not_sent']
    rendered = {
        'mip': VERSION,
        EXPRESSION: query.expression,
        'outcome': 'OK',
        SNAPSHOT: envelope[SNAPSHOT],
        'root': envelope['anchor'],
        NODES: envelope['node_details'],
        'facts': envelope['items'],
        'coverage': envelope['coverage'],
        'frontier': envelope['frontier'],
        BOUNDS: _bounds(query, envelope),
        'stop_reason': stop,
        'truncated': stop in BUDGET_STOPS or bool(not_sent),
        'not_sent': not_sent,
        CONTINUATION: envelope[CONTINUATION],
        'wire': {'protocol': envelope['protocol'], 'operation': WIRE_OPERATION,
                 'engine': envelope['engine_version'], 'facts_revision': envelope['facts_revision']},
    }
    # Le budget d'octets vaut pour ce que le consommateur reçoit, pas seulement pour l'enveloppe du moteur.
    if size(rendered) > rendered[BOUNDS]['applied'][MAX_BYTES]:
        return failure(BUDGET_EXHAUSTED, 'La Tuile MIP dépasse le budget d’octets : augmenter max_bytes.',
                       envelope[SNAPSHOT], query.expression)
    return rendered
