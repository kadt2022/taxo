# ADR 0005 : Fait, Tuile, Maille, Contexte

Date : 2026-09-17
Statut : Proposé

## Contexte

L'ADR 0001 pose Taxo comme mémoire logicielle vérifiable et l'ADR 0002 fixe le contrat du fait. Il
manquait le vocabulaire de ce que Taxo **remet à un agent**, et non de ce qu'il stocke.

Le 2026-09-17, un prototype jetable a été construit puis mesuré sur TAKIBO au commit
`032788fb6d` et sur `portail-math`. Il produit des faits du vocabulaire v1 (`HANDLED_BY`,
`PERMITS_ALL`, `AUTHORIZED_BY`), joint la chaîne de sécurité dans son ordre réel, puis rend des
unités compactes sous budget de tokens. Résultats retenus :

- une unité « chaîne de sécurité » coûte 21, 122 ou 357 tokens selon la résolution, contre environ
  4 000 tokens pour lire `SecurityConfig.java` ;
- une tâche réelle (« modifier l'autorisation de création d'un space ») est servie en 531 tokens
  au lieu de 4 266 à 13 661 tokens de fichiers, soit un facteur 8 à 10 ;
- le commit `b3490e6` (restriction des origines CORS) modifie 16 blobs sous-jacents mais **aucun
  fait** d'endpoint ni d'autorisation. Invalider sur les blobs aurait renvoyé 13 unités pour rien.

Une objection a été soulevée contre le mot « tuile » : une carte a une grille régulière, la mémoire
de Taxo est un graphe irrégulier, donc ses éléments seraient des « nœuds ». L'objection décrit la
topologie interne, pas l'unité livrée. Elle est technique et juste ; sa conclusion sur le
vocabulaire ne l'est pas.

## Décision

Le vocabulaire de Taxo est figé ainsi :

```text
FACT     atome de vérité
TUILE    unité de connaissance prête à être consommée
MAILLE   réseau de relations entre les tuiles
CONTEXTE ensemble minimal de tuiles envoyé à l'agent
```

> Les Facts sont les atomes de vérité de Taxo. Une Tuile est une unité de connaissance dérivée de
> ces Facts. La Maille relie les Tuiles et permet à Taxo de sélectionner, invalider et transmettre
> uniquement la connaissance nécessaire.

Définition opérationnelle de la tuile : **une projection vérifiable et réutilisable d'un ensemble de
Facts portant sur une même frontière de connaissance.** Une tuile n'a pas de coordonnées ; elle a une
portée, un snapshot, ses faits cités, sa couverture, ses trous déclarés et son coût en tokens.

Trois plans, trois mots :

| Plan | Objet | Nom |
| --- | --- | --- |
| Interne | graphe de dépendances et d'invalidation | Maille (`MemoryMesh`) |
| Unité | projection des faits sur une frontière | Tuile (`KnowledgeTile`) |
| Externe | sélection remise à l'agent | Contexte (`ContextSelection`) |

Identifiants retenus dans le code : `KnowledgeTile`, `MemoryMesh`, `TileRevision`,
`TileProjection`, `ContextSelection`.

Taxo réutilise les **mécanismes** des systèmes de construction incrémentale et des vues
matérialisées. Il ne reprend pas leur vocabulaire : « Taxo parcourt la maille et remet à l'agent
uniquement les tuiles dont il a besoin » doit rester compréhensible sans glossaire.

Le sens de dérivation est unique et ne s'inverse jamais :

```text
Code -> Facts -> Tuiles -> Contexte -> LLM
```

Un résumé produit par un modèle n'entre jamais dans la mémoire. Une tuile est toujours reconstructible
depuis ses faits, et un fait depuis sa preuve.

## Conséquences

1. **L'identité d'une tuile porte sur sa connaissance, pas sur ses blobs.** Les blobs restent un
   pré-filtre interne pour décider quoi recalculer ; ils ne décident jamais de ce qui est renvoyé.
   Mesure à l'appui : 13 unités renvoyées pour rien sur un seul commit.
2. **Une tuile ne cite jamais l'empreinte d'une autre tuile.** Les références se font par portée,
   sinon la moindre modification se propage en bruit vers les tuiles d'ensemble.
3. **La sélection parcourt la maille depuis une ancre**, elle ne compare pas des mots. Le prototype
   lexical a retenu le catalogue RBAC pour une tâche portant sur les spaces.
4. **Toute tuile déclare sa couverture et ses trous.** C'est ce qui distingue Taxo d'un index :
   « 2 filtres de chaîne non modélisés » indique à l'agent où il doit encore lire le code.
5. La documentation, l'interface et les récits emploient Fait, Tuile, Maille, Contexte. Le code
   emploie les identifiants ci-dessus.

## Portée et limites

Cet ADR fixe un vocabulaire et un sens de dérivation. Il ne décide ni du découpage des tuiles, ni de
leurs familles, ni du protocole d'échange avec les agents : ces choix appartiennent aux récits qui
les implémenteront, et devront être mesurés comme l'a été le prototype.

Le numéro 0003 n'est pas utilisé dans ce dépôt ; cet ADR prend le numéro 0005 pour ne pas réécrire la
numérotation existante.
