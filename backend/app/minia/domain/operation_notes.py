"""Ce que Minia doit savoir de chaque opération pour la choisir (récit TAXO-MINIA-OPS-01).

`describe` dit les arguments d'une opération, pas son usage : un petit modèle choisit alors mal (une Tuile de sécurité
sur une méthode, une méthode cherchée pour une question sur une route). Minia joint donc à chaque opération proposée
une note courte : à quoi elle sert, quelle référence elle attend, l'erreur fréquente à éviter.

Les notes sont du côté de Minia, comme celles de `get_source` et de `get_tile` : le protocole et `describe` ne
changent pas, et une note ne dit rien que Taxo ne publie déjà (types de sujet et d'objet des relations, ancres des
profils). Elles voyagent avec l'opération plutôt que dans les consignes : la fenêtre du modèle ne paie que celles des
opérations proposées. Elles sont renvoyées à chaque tour : chaque octet compte autant de fois qu'il y a de tours,
d'où la borne MAX_NOTES_BYTES, qu'un guide plus long ne peut pas franchir sans que les tests le disent.
"""

NOTE = 'note'
# La somme des notes ajoutées ici, en octets UTF-8. Un guide de 1,2 Ko sur les relations a dégradé le banc : les
# notes en restent à la moitié, et une note de plus se mesure avant d'être ajoutée.
MAX_NOTES_BYTES = 600

NOTES = {
    'describe': 'Déjà servie à l’ouverture : sa réponse est dans la trajectoire.',
    'find_references': 'Point de départ pour un élément nommé. type : endpoint pour une route HTTP, symbol pour une '
                       'classe ou une méthode.',
    'get_neighborhood': 'Relations autour d’une référence reçue. OUTGOING : ce qu’elle vise (route vers méthode : '
                        'HANDLED_BY) ; INCOMING : ce qui la vise.',
    'find_facts': 'Le sujet doit être d’un type admis par la relation (subject_types de describe). Vide ne prouve pas '
                  'une absence.',
    'verify_claim': 'Sujet et objet des types que describe annonce pour la relation. Tes claim finaux sont vérifiés '
                    'de toute façon.',
}


def noted(item):
    """L'opération telle que Minia la voit, avec sa note. Une note déjà portée (celle de `get_source`) est gardée ;
    une opération sans note connue est rendue inchangée."""
    note = NOTES.get(item.get('operation'))
    if note is None or NOTE in item:
        return item
    return {**item, NOTE: note}
