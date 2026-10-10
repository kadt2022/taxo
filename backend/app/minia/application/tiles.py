"""Les Tuiles adaptatives demandées par Minia en exploration (récit TAXO-MIP-ADT-01, PR C).

Minia nomme une référence déjà reçue de Taxo et un profil déclaré (§ 9.5) ; Taxo sert la Tuile par le service MIP
(`EXPAND`), sur l'analyse de l'échange : jamais une autre version du dépôt. Minia ne compose aucun parcours : le
profil le fixe, et sa Tuile porte ses règles, ses chemins, sa provenance et sa classification. Un refus (profil
inconnu, ancre d'un autre type, budget) est rendu tel quel, sans repli silencieux.

Aucun code n'est transmis : une Tuile ne contient que des faits de la Maille, et `get_source` n'est jamais proposée
à Minia (elle attend son propre consentement, et la clôture de TAXO-MINIA-SEC-01).
"""
from app.mip.domain.profiles import PROFILES
from app.mip.domain.tile import failure
from app.protocol.domain.envelope import size

OPERATION = 'get_tile'
EXPAND = 'EXPAND'
# Une Tuile ne prend jamais plus que ce budget, quelle que soit la place du modèle (celui du repli des ancres).
MAX_TILE_BYTES = 16_000
_ARGUMENTS = ('reference', 'profile')
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


def request(mip, exchange, arguments, space):
    """La Tuile du profil demandé sur l'analyse de l'échange, avec sa taille (`bytes`) comme toute réponse."""
    unknown = sorted(set(arguments) - set(_ARGUMENTS))
    if unknown:
        tile = failure(_INVALID, f'Argument inconnu : {unknown[0][:100]}.', exchange.snapshot, EXPAND)
    else:
        bounds = {'max_bytes': MAX_TILE_BYTES if space is None else max(min(space, MAX_TILE_BYTES), 1)}
        query = {'expression': EXPAND, 'target': {'reference': arguments.get('reference')},
                 'profile': arguments.get('profile'), 'analysis': exchange.snapshot['analysis'], 'bounds': bounds}
        tile = mip.query(exchange.project_id, query)
    return {**tile, 'bytes': size(tile)}
