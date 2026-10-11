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
from app.protocol.domain.envelope import error

OPERATION = 'get_source'
_INVALID = 'INVALID_ARGUMENT'
# Ce que le modèle doit savoir de la pièce, avec l'opération plutôt que dans ses consignes : la fenêtre d'un petit
# modèle ne paie ce texte que lorsque la lecture est permise.
NOTE = ('Le code exact d’un symbole déclaré, lu au commit de l’analyse ("commit") : ce n’est pas forcément le dernier '
        'commit qui l’a modifié. Une pièce de code n’est pas un fait de Taxo : une affirmation se vérifie sur les faits '
        '(claim). Ne déduis ni cadre ni base de données d’un nom ou d’un appel ; lis plutôt le code de la méthode '
        'appelée, avec une référence reçue de Taxo.')


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
    """Les références que Taxo atteste connaître dans une réponse : une ancre ou un nœud marqué connu, un résultat
    de recherche (lu dans l'index des noms de l'analyse)."""
    response = item['response']
    found = response.get('items', []) if item.get('operation') == 'find_references' else []
    return {*_known(response), *(row['reference'] for row in found if isinstance(row.get('reference'), str))}


def _known(value):
    if isinstance(value, dict):
        if value.get('known') is True and isinstance(value.get('reference'), str):
            yield value['reference']
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
    return {value for value in _references(item['response']) if value not in asked}


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
