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

from app.protocol.domain.envelope import error

OPERATION = 'get_source'
_INVALID = 'INVALID_ARGUMENT'
# Ce que le modèle doit savoir de la pièce, avec l'opération plutôt que dans ses consignes : la fenêtre d'un petit
# modèle ne paie ce texte que lorsque la lecture est permise.
NOTE = ('Le code exact d’un symbole déclaré, lu au commit de l’analyse ("commit") : ce n’est pas forcément le dernier '
        'commit qui l’a modifié. Une pièce de code n’est pas un fait de Taxo : une affirmation se vérifie sur les faits '
        '(claim). Ne déduis ni cadre ni base de données d’un nom ou d’un appel ; lis plutôt le code de la méthode '
        'appelée, avec une référence reçue de Taxo. Rapporte ce que tu lis dans le code en "interpretation" qui commence '
        'par "Code lu" et cite le symbole et les lignes : ce n’est pas une relation de Taxo, et tu ne dis jamais '
        'qu’une relation de Taxo le confirme quand Taxo ne l’a pas fait.')


def noted(item):
    """L'opération telle que Minia la voit : `get_source` porte sa consigne, les autres sont inchangées."""
    return {**item, 'note': NOTE} if item.get('operation') == OPERATION else item


# Les champs où Taxo rend une référence (recherche, voisinage, faits et preuves d'une Tuile, pièce source). Jamais
# un texte libre : le code d'une pièce ou un message de commit peut écrire n'importe quel symbole.
_REFERENCE_FIELDS = frozenset({'reference', 'subject', 'object', 'symbol', 'premises', 'from', 'node', 'root',
                               'subjects'})


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


def received(reference, exchanged):
    """Vrai si `reference` a été découverte par Taxo dans cet échange : égale à la valeur d'un champ de référence d'une
    réponse, jamais trouvée dans un texte (un symbole écrit dans le code lu n'est pas reçu) ni simplement répétée
    de la demande."""
    if not isinstance(reference, str) or not reference:
        return False
    return any(reference in _discovered(item) for item in exchanged)


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
