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
    """Les valeurs rendues par Taxo comme références, en parcourant la réponse champ par champ."""
    if isinstance(value, dict):
        for name, item in value.items():
            yield from _references(item, name)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item, field)
    elif isinstance(value, str) and field in _REFERENCE_FIELDS:
        yield value


def received(reference, exchanged):
    """Vrai si `reference` a été rendue par Taxo comme une référence dans cet échange : égale à la valeur d'un champ
    de référence, jamais trouvée dans un texte (un symbole écrit dans le code lu n'est pas une référence reçue)."""
    if not isinstance(reference, str) or not reference:
        return False
    return any(reference == value for item in exchanged for value in _references(item['response']))


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
