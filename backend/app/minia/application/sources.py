"""Le code d'un symbole lu par Minia en exploration (récit TAXO-MIP-ADT-01, PR C2 ; ARCHITECTURE § 12.6).

`get_source` reste une opération du protocole, distincte de la Tuile : Taxo ne la propose à Minia que si le réglage
du serveur et l'accord de la demande l'autorisent, et sert la pièce sous ses propres refus, sa classification et sa
provenance. Minia ajoute deux garde-fous à ce que le protocole contrôle déjà :

- la référence doit avoir été reçue de Taxo dans l'échange (une recherche, un voisinage, une Tuile ou une pièce) :
  un symbole deviné n'est jamais lu ;
- l'opération porte une consigne : le code n'est pas un fait de la Maille, son commit est celui de l'analyse.

Le texte du code passe, comme tout message, par la protection de la demande (secrets et identités masqués) avant
le fournisseur.
"""
import re

from app.minia.domain.exploration import UNKNOWN
from app.protocol.domain.envelope import error
from app.protocol.domain.source import nature

OPERATION = 'get_source'
_INVALID = 'INVALID_ARGUMENT'
# Ce que le modèle doit savoir de la pièce, avec l'opération plutôt que dans ses consignes : la fenêtre d'un petit
# modèle ne paie ce texte que lorsque la lecture est permise.
NOTE = ('Le code exact d’un symbole déclaré, lu au commit de l’analyse ("commit") : ce n’est pas forcément le dernier '
        'commit qui l’a modifié. Une pièce de code n’est pas un fait de Taxo : une affirmation se vérifie sur les faits '
        '(claim). Ne déduis ni cadre ni base de données d’un nom ou d’un appel ; lis plutôt le code de la méthode '
        'appelée, avec une référence reçue de Taxo : celles de "uses" (appels, types des champs) le sont.')


# Une indication courte pour `find_references` : comment lister une famille entière. Elle ne dit que ce que le protocole
# accepte déjà (un type sans préfixe) ; elle ne nomme aucune famille ni aucune référence du projet.
FIND_NOTE = 'Pour lister les références d’une famille, donne type sans prefix.'
FIND = 'find_references'


def noted(item):
    """L'opération telle que Minia la voit : `get_source` et `find_references` portent leur indication, les autres sont
    inchangées."""
    if item.get('operation') == OPERATION:
        return {**item, 'note': NOTE}
    if item.get('operation') == FIND:
        return {**item, 'note': FIND_NOTE}
    return item


# Les champs où Taxo rend une référence (recherche, voisinage, faits et preuves d'une Tuile, pièce source). Jamais
# un texte libre : le code d'une pièce ou un message de commit peut écrire n'importe quel symbole.
_REFERENCE_FIELDS = frozenset({'reference', 'subject', 'object', 'symbol', 'premises', 'from', 'node', 'root',
                               'subjects', 'known_objects'})


def _references(value, field=None):
    """Les valeurs des champs de référence d'une réponse, parcourue champ par champ."""
    if isinstance(value, dict):
        for name, item in value.items():
            yield from _references(item, name)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item, field)
    elif isinstance(value, str) and field in _REFERENCE_FIELDS:
        yield value


# La chaîne de filtres d'une règle de sécurité est une référence que Taxo rend hors d'un champ de référence :
# l'évaluateur Spring Security l'écrit dans `qualifiers.filter_chain` de ses faits. Elle n'est reçue qu'après une
# validation déterministe de son origine (producteur, relation, statut, validité, même commit que la réponse qui la
# porte, dans les faits rendus par Taxo) et de son type (une méthode Java). Aucun autre qualificatif n'ouvre la lecture.
_CHAIN_FIELD = 'filter_chain'
_CHAIN_PRODUCER = 'taxo.spring-security'
# PROTECTED_BY n'est plus produit (D5) mais reste lu dans les analyses anciennes qui le portent.
_CHAIN_RELATIONS = frozenset({'MATCHED_BY', 'PROTECTED_BY', 'AUTHORIZED_BY'})
_CHAIN_STATUSES = frozenset({'OBSERVED', 'INFERRED'})
_CHAIN_FACT_LISTS = ('facts', 'items')
MAX_CHAIN = 400
_JAVA_METHOD = re.compile(
    r'symbol:java:[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*#[A-Za-z_$][\w$]*\([\w$.<>\[\],?]*\)')


def _chain(fact, commit):
    """La chaîne de filtres que ce fait porte légitimement, ou None : le fait vient du producteur de sécurité, dit une
    relation de sécurité, est valide, et date du commit de la réponse ; la valeur est une méthode Java."""
    if not isinstance(fact, dict) or commit is None:
        return None
    qualifiers, produced, snapshot = fact.get('qualifiers'), fact.get('produced_by'), fact.get('snapshot')
    chain = qualifiers.get(_CHAIN_FIELD) if isinstance(qualifiers, dict) else None
    if (not isinstance(chain, str) or len(chain) > MAX_CHAIN or not _JAVA_METHOD.fullmatch(chain)
            or fact.get('relation') not in _CHAIN_RELATIONS or fact.get('status') not in _CHAIN_STATUSES
            or fact.get('validity') != 'VALID' or not isinstance(produced, dict)
            or produced.get('producer_id') != _CHAIN_PRODUCER or not isinstance(snapshot, dict)
            or snapshot.get('commit') != commit):
        return None
    return chain


def _chains(item):
    """Les chaînes de filtres validées d'une réponse de Taxo, lues seulement dans les listes de faits qu'il rend ;
    jamais celles d'une pièce de code, ni d'un texte."""
    response = item['response']
    if item.get('operation') == OPERATION or not isinstance(response, dict):
        return
    snapshot = response.get('snapshot')
    commit = snapshot.get('commit') if isinstance(snapshot, dict) else None
    for name in _CHAIN_FACT_LISTS:
        for entry in response.get(name) or []:
            chain = _chain(entry.get('fact') if isinstance(entry, dict) else None, commit)
            if chain is not None:
                yield chain


def _strings(value):
    """Toutes les chaînes d'une demande : ce que le modèle a écrit, à quelque profondeur que ce soit."""
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def _confirmed(item):
    """Les références que Taxo atteste connaître dans une réponse : une ancre ou un nœud marqué connu, un fait de la
    Maille, un résultat de recherche (lu dans l'index des noms de l'analyse)."""
    response = item['response']
    found = response.get('items', []) if item.get('operation') == 'find_references' else []
    return {*_known(response), *(row['reference'] for row in found if isinstance(row.get('reference'), str))}


def _known(value):
    if isinstance(value, dict):
        if value.get('known') is True and isinstance(value.get('reference'), str):
            yield value['reference']
        if isinstance(value.get('fact'), dict):
            yield from _references(value['fact'])
        value = list(value.values())
    if isinstance(value, list):
        for item in value:
            yield from _known(item)


def _discovered(item):
    """Les références qu'une réponse apporte : celles de ses champs de référence, moins ce que la demande portait
    déjà sans que Taxo l'atteste. Une réponse peut répéter sa demande (l'affirmation de `verify_claim`, l'ancre d'un
    voisinage inconnue, la couverture) : un symbole deviné par le modèle n'en devient pas une découverte de Taxo ;
    un symbole demandé que Taxo reconnaît (ancre connue, résultat de recherche) l'est."""
    asked = set(_strings(item.get('arguments', {}))) - _confirmed(item)
    found = {value for value in _references(item['response']) if value not in asked}
    return found | {chain for chain in _chains(item) if chain not in asked}


def references_of(item):
    """Les références qu'une réponse de l'échange a apportées (celles qu'un résumé de la réponse garde)."""
    return sorted(_discovered(item))


def received(reference, exchanged):
    """Vrai si `reference` a été découverte par Taxo dans cet échange : égale à la valeur d'un champ de référence d'une
    réponse, jamais trouvée dans un texte (un symbole écrit dans le code lu n'est pas reçu) ni simplement répétée
    de la demande."""
    if not isinstance(reference, str) or not reference:
        return False
    return any(reference in _discovered(item) for item in exchanged)


# La garde de conclusion : une conclusion qui porte un « inconnu » et cite un symbole reçu de Taxo, lisible et jamais lu,
# revient une fois au modèle. La règle est fixe et ne juge rien : elle compare des noms à des références reçues ; le modèle lit
# le code ou garde son inconnu.
GUARD = 'conclusion'
RETURNED = 'RETURNED'
MAX_RETURNED = 3
GUARD_NOTE = ('Conclusion renvoyée une fois : elle porte un « unknown » et cite un symbole reçu de Taxo dont le code est '
              'lisible et n’a pas été lu ({}). Lis-le avec get_source avant de conclure, ou garde cet unknown.')


def _owner(reference):
    """La classe d'une référence de symbole : la référence elle-même, ou celle qui précède le membre (`#`)."""
    return reference.split('#', 1)[0]


def _simple(reference):
    """Le nom simple de la classe d'une référence de symbole (`symbol:java:a.b.Orders#list()` → `Orders`)."""
    return re.split(r'[.:]', _owner(reference))[-1]


def _mentions(name, texts):
    """Vrai si un des textes écrit `name` comme un nom entier (pas une partie d'un nom plus long)."""
    return any(re.search(rf'(?<![\w$]){re.escape(name)}(?![\w$])', text) for text in texts)


def _member(reference):
    """Le nom du membre d'une référence (`…#save(Long,Long)` → `save`), ou None pour une classe."""
    return reference.split('#', 1)[1].split('(', 1)[0] if '#' in reference else None


def _chosen(references, texts):
    """Ce que la garde propose pour une classe, parmi ses références reçues : celles qu'une affirmation cite, sinon la
    seule méthode nommée `Classe.méthode`, sinon la classe, sinon toutes les candidates (les surcharges nommées, ou
    les membres reçus) : une ambiguïté est montrée, jamais tranchée au hasard."""
    cited = sorted(reference for reference in references if reference in texts)
    if cited:
        return cited
    named = sorted(reference for reference in references if _member(reference) is not None
                   and _mentions(f'{_simple(reference)}.{_member(reference)}', texts))
    if len(named) == 1:
        return named
    classes = [reference for reference in references if _member(reference) is None]
    return classes or named or sorted(references)


def _cited(statement):
    """Ce qu'un énoncé écrit : son texte et, pour une affirmation, ses références."""
    yield statement['text']
    yield from (value for value in statement.get('claim', {}).values() if value)


def unread(statements, exchanged):
    """Pour une conclusion qui porte un « unknown » : les symboles reçus de Taxo dont la classe est citée par un de ses
    énoncés et dont aucun code n'a été lu dans l'échange (ni la classe, ni un de ses membres). Par classe, ce que
    retient `_chosen` ; seules des références reçues de Taxo, jamais une signature devinée. Deux classes de même nom
    simple sont rendues toutes deux, jamais l'une choisie pour l'autre ; au plus MAX_RETURNED en tout."""
    if not any(statement['type'] == UNKNOWN for statement in statements):
        return []
    texts = [text for statement in statements for text in _cited(statement)]
    read = {_owner(item['arguments'].get('reference', '')) for item in exchanged
            if item['operation'] == OPERATION and item['response'].get('outcome') == 'OK'}
    # Les tuiles du chemin (`get_path`, `read_tiles`) sont du code lu, comme une pièce `get_source`.
    read |= {_owner(tile['reference']) for item in exchanged if item['operation'] in ('get_path', 'read_tiles')
             for tile in item['response'].get('tiles') or () if isinstance(tile.get('reference'), str)}
    # Seuls une classe, une méthode ou un constructeur ont un code que `get_source` sert : jamais un champ.
    known = {reference for item in exchanged for reference in _discovered(item)
             if reference.startswith('symbol:') and nature(reference) != 'MEMBER'}
    by_owner = {}
    for reference in known:
        if _owner(reference) not in read and _mentions(_simple(reference), texts):
            by_owner.setdefault(_owner(reference), []).append(reference)
    return [reference for owner in sorted(by_owner) for reference in _chosen(by_owner[owner], texts)][:MAX_RETURNED]


def returned(references):
    """Ce que Minia voit de sa conclusion renvoyée : la règle et les références lisibles, jamais un verdict."""
    return {'operation': GUARD, 'arguments': {},
            'response': {'outcome': RETURNED, 'unread': references, 'note': GUARD_NOTE.format(', '.join(references))}}


def key(step, exchanged):
    """Ce qui rend une demande répétée : pour `get_source`, la même référence, refusée tant qu'elle n'avait pas été
    reçue de Taxo, peut être redemandée une fois reçue (le refus y invite) ; jamais deux fois dans le même état."""
    if step.operation != OPERATION:
        return step.key
    return f'{step.key}|{received(step.arguments.get("reference"), exchanged)}'


def request(exchange, arguments, max_bytes, exchanged):
    """La pièce source demandée par Minia, servie par l'échange (qui en contrôle le consentement, les refus et le
    budget) ; une référence jamais reçue de Taxo est refusée sans rien lire, comptée comme une opération. Sans
    consentement, c'est le refus du protocole (`NO_CONSENT`) qui est rendu."""
    if not exchange.source_consent or received(arguments.get('reference'), exchanged):
        return exchange.call({'operation': OPERATION, 'arguments': arguments,
                              **({} if max_bytes is None else {'max_bytes': max(max_bytes, 1)})})
    refusal = error(OPERATION, exchange.snapshot, _INVALID,
                    'reference : un symbole reçu de Taxo dans cet échange (find_references, get_neighborhood, une '
                    'Tuile ou une pièce source).')
    return exchange.accounted(lambda _: refusal)
