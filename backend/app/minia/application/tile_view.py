"""La vue d'une Tuile pour le modèle (récit TAXO-RECIT-REDUCTION-PAYLOAD-MINIA, R2 ; projection `vue-minia/1`).

Taxo sert la Tuile entière, et Minia la garde entière : la trajectoire, la garde de conclusion, la vérification des
affirmations (`find_claim`) et l'affichage des preuves lisent toujours la réponse complète. Seul le message envoyé au
modèle reçoit cette vue, déterministe et versionnée, construite **avant** la protection de la demande, qui contrôle
ensuite le message entier (SEC-01).

Liste blanche (SEC-02) : chaque champ de la Tuile et de ses faits est classé ; un champ que la table ne connaît pas
n'est jamais transmis (SEC-08), et son nom est signalé dans `projection.withheld`. Le test de contrat compare la table
aux champs que Taxo rend réellement, et échoue sur tout champ non classé.

| Classe | Effet |
|---|---|
| `SENT` | transmis tel quel |
| `CONDENSED` | transmis sous une forme courte, de même sens |
| `RETAINED` | gardé par Minia, jamais envoyé (audit, provenance, poignées internes) |

Ce qui ne change jamais de sens (SEC-05) : couverture, frontière, `not_sent`, troncature, raison d'arrêt et limites du
profil restent transmises ; un fait déduit reste « déduit », avec ses prémisses et ses limites connues (I-07). Les
références courtes `F…` sont celles de l'échange : elles désignent sans ambiguïté le fait servi (SEC-03), et Minia
résout tout fait par sa réponse complète, jamais par cette vue.
"""
VERSION = 'vue-minia/1'
# La vue stricte (R4, étape E) : en plus, les seuls doublons prouvés retirés — `via` (redit le fait), les nœuds déjà
# sujets ou objets d'un fait, `root.known` vrai, le commit (dit par `describe`), la note répétée. Jamais les preuves,
# la dérivation, les qualificatifs, la frontière, la couverture, ni le chemin de sélection.
STRICT_VERSION = 'vue-minia/2'
SENT, CONDENSED, RETAINED = 'SENT', 'CONDENSED', 'RETAINED'

# La Tuile. `mip`, `expression`, `wire`, `classification` : provenance et audit ; `bounds` : redit en `truncated`,
# `stop_reason` et `not_sent` ; `continuation` : sans usage pour le modèle (`get_tile` n'en accepte pas) ;
# `bytes` : la taille servie, que la trajectoire montre.
TILE_FIELDS = {
    'mip': RETAINED, 'expression': RETAINED, 'outcome': SENT, 'snapshot': SENT, 'root': SENT, 'nodes': CONDENSED,
    'facts': CONDENSED, 'coverage': SENT, 'frontier': SENT, 'bounds': RETAINED, 'stop_reason': SENT,
    'truncated': SENT, 'not_sent': SENT, 'continuation': RETAINED, 'wire': RETAINED, 'profile': CONDENSED,
    'classification': RETAINED, 'disclosure': CONDENSED, 'bytes': RETAINED, 'error': SENT,
    # Ajoutés par Minia à une Tuile redonnée (trajectoire compacte) : le renvoi vers le tour d'origine.
    'reused': SENT, 'note': SENT,
}
# Un fait de la Tuile. `identity` et `occurrence` : poignées internes, retrouvées par la réponse complète (SEC-04).
ITEM_FIELDS = {
    'ref': SENT, 'fact': CONDENSED, 'evidence_count': SENT, 'identity': RETAINED, 'occurrence': RETAINED,
    'via': CONDENSED, 'level': SENT, 'revisit': CONDENSED, 'evidence': CONDENSED, 'selection': SENT,
}
# Le fait lui-même. `snapshot` : celui de la Tuile ; `produced_by` : l'analyseur, gardé pour l'audit.
FACT_FIELDS = {
    'kind': CONDENSED, 'subject': SENT, 'relation': SENT, 'object': SENT, 'qualifiers': SENT, 'status': SENT,
    'validity': CONDENSED, 'contract_version': RETAINED, 'snapshot': RETAINED, 'produced_by': RETAINED,
    'derivation': CONDENSED, 'coverage_type': SENT, 'scope': SENT, 'reason': SENT,
}
_DERIVATION = ('rule', 'premises', 'known_gaps')
_PROFILE = ('id', 'limits')


def projectable(response):
    """Une réponse qui porte une Tuile (servie ou refusée) ; pas un résumé de trajectoire compacte ni un simple renvoi,
    qui ne contiennent que des références et une note de Minia."""
    if not isinstance(response, dict) or response.get('compacted'):
        return False
    return not (response.get('reused') and 'facts' not in response and 'error' not in response)


def project(response, strict=False):
    """La vue de la Tuile pour le modèle. Un refus passe par la même liste blanche : son issue, son erreur et
    l'instantané, jamais la provenance ni un champ inconnu. `strict` : la vue de l'étape E (R4)."""
    if not isinstance(response, dict):
        return response
    version = STRICT_VERSION if strict else VERSION
    withheld = sorted(name for name in response if name not in TILE_FIELDS)
    shown = {name: value for name, value in response.items() if TILE_FIELDS.get(name) == SENT}
    if response.get('outcome') != 'OK':
        return {**shown, **({'projection': {'version': version, 'withheld': withheld}} if withheld else {})}
    if 'nodes' in response:
        shown['nodes'] = _nodes(response['nodes'])
    if 'profile' in response:
        shown['profile'] = {name: response['profile'][name] for name in _PROFILE if name in response['profile']}
    restrictions = (response.get('disclosure') or {}).get('restrictions')
    if restrictions:
        shown['disclosure'] = {'restrictions': restrictions}
    facts = []
    for item in response.get('facts') or ():
        fact, unknown = item_view(item, strict=strict)
        facts.append(fact)
        withheld.extend(unknown)
    shown['facts'] = facts
    if strict:
        _slimmed(shown, 'root', facts)
    shown['projection'] = {'version': version}
    if not strict:
        shown['projection']['note'] = ('Vue condensée : identité, occurrence, provenance et preuves détaillées restent '
                                       'dans Taxo, retrouvées par la référence F….')
    if withheld:
        shown['projection']['withheld'] = sorted(set(withheld))
    return shown


def _slimmed(shown, anchor, facts):
    """Les doublons prouvés de la vue stricte : le commit (dit par `describe`), l'ancre connue, les nœuds déjà sujets
    ou objets d'un fait. Un nœud sans fait, un nœud non développé ou une ancre inconnue restent dits."""
    if isinstance(shown.get('snapshot'), dict):
        shown['snapshot'] = {name: value for name, value in shown['snapshot'].items() if name != 'commit'}
    if isinstance(shown.get(anchor), dict) and shown[anchor].get('known') is True:
        shown[anchor] = {name: value for name, value in shown[anchor].items() if name != 'known'}
    cited = {value for item in facts for value in (item['fact'].get('subject'), item['fact'].get('object'))}
    cited.add((shown.get(anchor) or {}).get('reference'))
    nodes = shown.get('nodes')
    if isinstance(nodes, dict):
        rest = [reference for reference in nodes.get('references') or () if reference not in cited]
        shown['nodes'] = {**({'references': rest} if rest else {}),
                          **({'not_expanded': nodes['not_expanded']} if nodes.get('not_expanded') else {})}
        if not shown['nodes']:
            del shown['nodes']
    elif isinstance(nodes, list):
        rest = [reference for reference in nodes if reference not in cited]
        if rest:
            shown['nodes'] = rest
        else:
            del shown['nodes']


def _nodes(nodes):
    """Les nœuds atteints, par leur référence ; ceux que la Tuile n'a pas développés sont dits."""
    seen = [node.get('reference') for node in nodes if isinstance(node, dict)]
    closed = [node.get('reference') for node in nodes if isinstance(node, dict) and node.get('expanded') is False]
    return {'references': seen, **({'not_expanded': closed} if closed else {})}


def item_view(item, prefix='facts', strict=False):
    """Un fait servi (Tuile, voisinage) et les noms des champs inconnus, jamais transmis. `strict` : sans `via`, qui
    redit le sujet, la relation et l'objet du fait."""
    unknown = [f'{prefix}.{name}' for name in item if name not in ITEM_FIELDS]
    shown = {name: item[name] for name in item if ITEM_FIELDS.get(name) == SENT}
    fact = item.get('fact') or {}
    unknown += [f'{prefix}.fact.{name}' for name in fact if name not in FACT_FIELDS]
    inner = {name: fact[name] for name in fact if FACT_FIELDS.get(name) == SENT and fact[name] not in ({}, None)}
    if fact.get('kind') not in (None, 'ASSERTION'):
        inner['kind'] = fact['kind']
    if fact.get('validity') not in (None, 'VALID'):
        inner['validity'] = fact['validity']
    derivation = fact.get('derivation')
    if isinstance(derivation, dict):
        inner['derivation'] = {name: derivation[name] for name in _DERIVATION if derivation.get(name)}
        if derivation.get('counter_examples_checked'):
            inner['derivation']['counter_examples'] = len(derivation['counter_examples_checked'])
    shown['fact'] = inner
    via = item.get('via')
    if isinstance(via, dict) and not strict:
        shown['via'] = f'{via.get("direction", "")} {via.get("relation", "")} depuis {via.get("from", "")}'.strip()
    if item.get('revisit'):
        shown['revisit'] = True
    if item.get('evidence'):
        shown['evidence'] = [_proof(proof) for proof in item['evidence'] if isinstance(proof, dict)]
    return shown, unknown


def _proof(proof):
    """Une preuve en une ligne : fichier, lignes et méthode de lecture."""
    path, start, end = proof.get('path', ''), proof.get('line_start'), proof.get('line_end')
    lines = ''
    if start is not None:
        lines = f':{start}' if end in (None, start) else f':{start}-{end}'
    method = f' ({proof["method"]})' if proof.get('method') else ''
    return f'{path}{lines}{method}'


def unclassified(response):
    """Les champs qu'une Tuile réelle porte et que la table ne classe pas (test de contrat)."""
    names = {name for name in response if name not in TILE_FIELDS}
    for item in response.get('facts') or ():
        names |= {f'facts.{name}' for name in item if name not in ITEM_FIELDS}
        names |= {f'facts.fact.{name}' for name in item.get('fact') or {} if name not in FACT_FIELDS}
    return sorted(names)
