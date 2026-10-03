"""La forme compacte d'une Tuile `neighborhood/2` (TAXO-01J, tranche F).

Une représentation de la même réponse, jamais une autre réponse : chaque valeur commune n'est écrite qu'une
fois, et chaque élément y renvoie par un indice. Rien n'est retiré ; la forme complète se reconstruit à
l'identique (vérifié par les tests, par l'inverse écrit à part).

- `shared.common` : ce que des faits ont en commun sans l'affirmer (nature, version du contrat, statut,
  validité, instantané, provenance), chaque combinaison une fois, dans l'ordre de sa première apparition ; un
  élément porte `common`, son indice, et son fait garde ce qu'il affirme (sujet, relation, objet,
  qualificatifs, dérivation) ;
- `via` : `from`, l'indice du nœud d'origine dans `nodes`, et `step`, l'indice du pas dans `parameters.steps` ;
- `node_details` : alignés sur `nodes`, sans répéter la référence.

La sélection ne change pas : la forme ne fait que changer la taille de ce qui est rendu, mesurée comme
toute réponse.
"""
import json

FULL, COMPACT = 'FULL', 'COMPACT'
FORMS = (FULL, COMPACT)
# Les champs d'un fait qui ne disent pas ce qu'il affirme : souvent les mêmes pour toute une Tuile.
_COMMON = ('kind', 'contract_version', 'status', 'validity', 'snapshot', 'produced_by')


class _Table:
    """Des valeurs distinctes, dans l'ordre de leur première apparition."""

    def __init__(self):
        self.values, self._index = [], {}

    def index(self, value):
        key = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if key not in self._index:
            self._index[key] = len(self.values)
            self.values.append(value)
        return self._index[key]


def compact(envelope):
    """L'enveloppe complète d'une Tuile, sous sa forme compacte ; l'enveloppe donnée n'est pas modifiée."""
    nodes = {reference: index for index, reference in enumerate(envelope['nodes'])}
    steps = {(step['relation'], step['direction']): index
             for index, step in enumerate(envelope['parameters']['steps'])}
    common = _Table()
    items = [_item(item, nodes, steps, common) for item in envelope['items']]
    details = [{key: value for key, value in node.items() if key != 'reference'}
               for node in envelope['node_details']]
    return {**envelope, 'node_details': details, 'items': items, 'shared': {'common': common.values}}


def _item(item, nodes, steps, common):
    fact = item['fact']
    shared = {field: fact[field] for field in _COMMON if field in fact}
    via = item['via']
    return {**item, 'fact': {field: value for field, value in fact.items() if field not in shared},
            'common': common.index(shared),
            'via': {'from': nodes[via['from']], 'step': steps[(via['relation'], via['direction'])]}}
