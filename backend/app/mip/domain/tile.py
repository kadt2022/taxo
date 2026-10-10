"""La Tuile MIP 0.1 : une Tuile `neighborhood/2` rendue sous le contrat MIP (récit TAXO-01N / MIP-01 § 4.2).

Une présentation, jamais une seconde construction : chaque fait, nœud, preuve résumée, couverture et frontière
vient tel quel de la réponse du moteur. Ce qui s'ajoute ne dit que ce que cette réponse établit déjà : les bornes
demandées et appliquées, et si la Tuile a été coupée par un budget. Rien n'est renommé dans le domaine de la Maille.

Une Tuile servie par un profil (récit TAXO-MIP-ADT-01) rend en plus le manifeste appliqué et ses paramètres résolus,
et dit pour chaque fait la règle du profil qui l'a retenu et son chemin depuis l'ancre : les références des faits
parcourus, reconstruites depuis le fait qui a découvert chaque nœud. Rien n'est ajouté à la sélection du moteur.
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


def _bounds(query, envelope, budget):
    """Ce qui a été demandé, ce que le serveur a appliqué après plafonnement, et ce que la Tuile a consommé. Le budget
    d'octets appliqué est celui de la Tuile reçue, que l'adaptateur a pu répartir entre le moteur et le profil."""
    limits, consumed = envelope[BOUNDS], envelope['consumed']
    applied = {'depth': envelope['parameters']['depth'], 'max_nodes': limits['max_nodes'],
               'max_facts': limits['max_edges'], MAX_BYTES: budget}
    return {'requested': dict(query.bounds), 'applied': applied,
            'consumed': {NODES: consumed[NODES], 'facts': consumed['edges']}}


def _paths(envelope):
    """Le chemin de chaque nœud depuis l'ancre : les références des faits qui l'ont découvert, de proche en proche.
    Un nœud découvert par un fait non rendu (coupé par les octets) n'a pas de chemin connu : `None`."""
    items, paths = envelope['items'], {}
    for node in envelope['node_details']:
        found = node['discovered_by']
        if found is None:
            paths[node['reference']] = []
        elif found < len(items):
            origin = paths.get(items[found]['via']['from'])
            paths[node['reference']] = None if origin is None else [*origin, items[found]['ref']]
        else:
            paths[node['reference']] = None
    return paths


def _profiled(profile, envelope, facts):
    """Chaque fait avec sa règle et son chemin ; les nœuds sont rendus dans l'ordre de leur découverte, donc le
    chemin d'un nœud d'origine est toujours connu avant celui des faits qui en partent."""
    paths = _paths(envelope)
    rendered = []
    for item in facts:
        via, origin = item['via'], paths.get(item['via']['from'])
        rendered.append({**item, 'selection': {'rule': profile.rule(via['relation'], via['direction']),
                                               'path': None if origin is None else [*origin, item['ref']]}})
    return rendered


def render(query, envelope, budget):
    """La Tuile MIP d'une réponse `OK` du moteur, sans contrôle de taille."""
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
        BOUNDS: _bounds(query, envelope, budget),
        'stop_reason': stop,
        'truncated': stop in BUDGET_STOPS or bool(not_sent),
        'not_sent': not_sent,
        CONTINUATION: envelope[CONTINUATION],
        'wire': {'protocol': envelope['protocol'], 'operation': WIRE_OPERATION,
                 'engine': envelope['engine_version'], 'facts_revision': envelope['facts_revision']},
    }
    if query.profile is not None:
        rendered['facts'] = _profiled(query.profile, envelope, envelope['items'])
        rendered['profile'] = {**query.profile.manifest(), 'resolved': envelope['parameters']}
    return rendered


def engine_budget(envelope):
    """Le budget d'octets que le moteur a appliqué à son enveloppe."""
    return envelope[BOUNDS][MAX_BYTES]


def tile(query, envelope, budget=None):
    """La Tuile MIP d'une réponse de `get_neighborhood` ; un refus du moteur reste un refus. `budget` : le budget de
    la Tuile reçue, par défaut celui que le moteur a appliqué."""
    if envelope['outcome'] != 'OK':
        error = envelope['error']
        return failure(error['code'], error['message'], envelope.get(SNAPSHOT), query.expression)
    budget = engine_budget(envelope) if budget is None else budget
    rendered = render(query, envelope, budget)
    # Le budget d'octets vaut pour ce que le consommateur reçoit, pas seulement pour l'enveloppe du moteur.
    if size(rendered) > budget:
        return failure(BUDGET_EXHAUSTED, 'La Tuile MIP dépasse le budget d’octets : augmenter max_bytes.',
                       envelope[SNAPSHOT], query.expression)
    return rendered
