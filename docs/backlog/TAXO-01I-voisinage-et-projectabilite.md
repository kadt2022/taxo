# TAXO-01I — Voisinage et projectabilité

Statut : rédigé le 2026-09-17, à réaliser avec TAXO-PROJ-API-01.

Source de vérité : [T6 et T12 de l'EPIC TAXO-01](EPIC-TAXO-01-fondation-memoire-verifiable.md).

Dépend de : 01E (persistance), 01G (lecture). Étalon : [TAXO-POC-01](TAXO-POC-01-verite-de-reference-chaine-autorisation.md).

## Objectif

Rendre les relations entre faits navigables dans les deux sens, et prouver par un test **sans aucun
LLM** qu'un flux se reconstruit depuis les seuls faits, sans relire le dépôt.

## Périmètre

- interroger les faits dont une entité est **sujet**, et ceux dont elle est **objet** ;
- fournir le voisinage immédiat d'une entité, puis un parcours de profondeur bornée ;
- trois fins de parcours possibles, et seulement trois :
  1. **un fait connu** poursuit la chaîne. Un fait `ABSENCE`, correctement couvert, est un fait connu :
     il la termine sur une absence établie, et c'est le seul cas où Taxo affirme une absence ;
  2. **un mécanisme déclaré `NOT_INTERPRETED`** arrête la chaîne en nommant ce qui n'est pas interprété ;
  3. **`UNKNOWN`** : aucune capacité en place n'a couvert la question. **L'absence de fait ne vaut
     jamais absence du phénomène** ; répondre « il n'y en a pas » parce que la mémoire est muette est
     exactement l'erreur que Taxo existe pour empêcher.
- test fonctionnel de projectabilité : à partir des faits, reconstruire une chaîne complète sans
  interprétation ajoutée.

Ce mécanisme n'est pas un Knowledge Graph et n'introduit aucun moteur de graphe. Il fournit les
primitives de navigation, rien de plus.

## Acceptation

1. Depuis `endpoint:GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users`, le parcours restitue la
   chaîne de TAXO-POC-01 jusqu'à `symbol:PolicyEvaluator`, en passant par `MATCHED_BY` puis
   `AUTHORIZED_BY`, et **jamais** par `HANDLED_BY`.
2. Un fait `INFERRED` rencontré en chemin expose ses prémisses.
3. Tout parcours se termine par l'une des trois fins ; aucune chaîne ne se complète par déduction
   implicite ou par invention.
4. Une entité sur laquelle aucune capacité n'a travaillé donne `UNKNOWN`, jamais une absence. Un test
   distingue explicitement les trois cas : fait `ABSENCE` couvert, `NOT_INTERPRETED`, et `UNKNOWN`.
4. Le parcours est déterministe, borné en profondeur, et ne relit jamais le dépôt.
5. Le test de projectabilité s'exécute sans aucun appel à un modèle de langage.
6. Interroger par objet et par sujet donne des résultats cohérents entre eux.

## Hors périmètre

Diagramme (TAXO-PROJ-API-01), narration (TAXO-ASK-01), maille des tuiles (TAXO-TILES-02), qui
réutilisera ce voisinage au lieu d'en créer un second.
