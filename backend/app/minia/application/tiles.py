"""Les Tuiles adaptatives demandées par Minia en exploration (récit TAXO-MIP-ADT-01, PR C).

Minia nomme une référence déjà reçue de Taxo dans l'échange (sinon refus) et un profil déclaré (§ 9.5) ; Taxo sert
la Tuile par le service MIP (`EXPAND`), sur l'analyse de l'échange : jamais une autre version du dépôt. Minia ne
compose aucun parcours : le profil le fixe, et sa Tuile porte ses règles, ses chemins, sa provenance et sa
classification. La Tuile est comptée dans le budget de l'échange comme toute opération. Un refus (référence non
reçue, profil inconnu, ancre d'un autre type, budget) est rendu tel quel, sans repli silencieux.

Aucun code n'est transmis : une Tuile ne contient que des faits de la Maille, et `get_source` n'est jamais proposée
à Minia (elle attend son propre consentement, et la clôture de TAXO-MINIA-SEC-01).
"""
import json

from app.mip.domain.profiles import PROFILES
from app.mip.domain.tile import failure
from app.protocol.domain.envelope import size

OPERATION = 'get_tile'
EXPAND = 'EXPAND'
# Une Tuile ne prend jamais plus que ce budget, quelle que soit la place du modèle (celui du repli des ancres).
MAX_TILE_BYTES = 16_000
_ARGUMENTS = ('reference', 'profile')
# La place du champ `bytes` ajouté à la Tuile : la réponse reste dans la borne demandée.
_SIZE_FIELD = 32
_INVALID = 'INVALID_ARGUMENT'
# Ce que Minia doit savoir d'une Tuile, avec l'opération plutôt que dans ses consignes : la fenêtre d'un petit modèle
# ne paie ce texte que lorsque l'opération est proposée.
_NOTE = ('Le profil fixe les relations suivies. Chaque fait porte "selection" (règle et chemin) ; "frontier" et '
         '"profile.limits" disent ce qui n’a pas été parcouru ou rendu, jamais une absence. Aucun code source.')


def offered():
    """L'opération telle que Minia la voit, avec les profils déclarés et l'ancre que chacun accepte."""
    profiles = '; '.join(f'{identifier} (ancre {" ou ".join(sorted(profile.anchors))})'
                         for identifier, profile in sorted(PROFILES.items()))
    return {'kind': 'operation', 'operation': OPERATION,
            'arguments': {'reference': 'référence reçue de Taxo (find_references, get_neighborhood)',
                          'profile': profiles},
            'note': _NOTE}


def request(mip, exchange, arguments, space, exchanged):
    """La Tuile du profil demandé sur l'analyse de l'échange, comptée dans son budget comme toute opération, avec sa
    taille (`bytes`). `exchanged` : les réponses déjà reçues, d'où la référence doit venir."""
    requested = MAX_TILE_BYTES if space is None else max(min(space, MAX_TILE_BYTES), 1)
    return exchange.accounted(lambda max_bytes: _sized(_tile(mip, exchange, arguments, max_bytes, exchanged)),
                              requested)


def _tile(mip, exchange, arguments, max_bytes, exchanged):
    unknown = sorted(set(arguments) - set(_ARGUMENTS))
    if unknown:
        return failure(_INVALID, f'Argument inconnu : {unknown[0][:100]}.', exchange.snapshot, EXPAND)
    reference = arguments.get('reference')
    if not _received(reference, exchanged):
        # Une référence devinée pourrait désigner un élément réel sans rapport avec la question.
        return failure(_INVALID, 'reference : une référence reçue de Taxo dans cet échange (find_references, '
                                 'get_neighborhood ou une Tuile).', exchange.snapshot, EXPAND)
    query = {'expression': EXPAND, 'target': {'reference': reference}, 'profile': arguments.get('profile'),
             'analysis': exchange.snapshot['analysis'], 'bounds': {'max_bytes': max(max_bytes - _SIZE_FIELD, 1)}}
    # Servie dans l'échange de Minia : les références courtes de la Tuile (`F…`) sont les siennes.
    return mip.query(exchange.project_id, query, exchange)


def _received(reference, exchanged):
    """Vrai si `reference` figure, comme valeur, dans une réponse déjà reçue de Taxo."""
    if not isinstance(reference, str) or not reference:
        return False
    responses = json.dumps([item['response'] for item in exchanged], ensure_ascii=False)
    return json.dumps(reference, ensure_ascii=False) in responses


def _sized(tile):
    """La Tuile avec sa taille sérialisée, champ `bytes` compris (point fixe, comme l'enveloppe du protocole)."""
    sized = {**tile, 'bytes': 0}
    while sized['bytes'] != size(sized):
        sized['bytes'] = size(sized)
    return sized
