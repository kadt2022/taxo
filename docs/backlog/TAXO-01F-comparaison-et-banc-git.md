# TAXO-01F — Comparaison de deux instantanés et banc Git

Statut : rédigé le 2026-09-17, à ouvrir après 01E.

Source de vérité : [T8 et T11 de l'EPIC TAXO-01](EPIC-TAXO-01-fondation-memoire-verifiable.md).

Dépend de : 01B (identité stable), 01C (instantané), 01D (exécution, catalogue et versions), 01E
(persistance).

## Objectif

Comparer deux instantanés sur l'identité stable des faits, et **distinguer une évolution du logiciel
d'une évolution du producteur**. C'est la première démonstration technique de Taxo : dire ce qui a
changé, et le prouver.

## Périmètre

- comparaison produisant `INTRODUCED`, `REMOVED`, `MODIFIED`, `UNCHANGED`, calculée sur les
  occurrences et leur identité stable ;
- lorsque les versions d'un producteur ou de son catalogue diffèrent entre les deux instantanés, le
  résultat porte « cause possible : évolution du producteur ». Un mécanisme interprété par la version
  1.1 et pas par la 1.0 n'est **jamais** présenté comme une modification du logiciel ;
- un fait dont la connaissance est identique et dont **seule la preuve se déplace reste `UNCHANGED`** :
  la ligne a bougé, le fait non. Le déplacement est signalé séparément par `EVIDENCE_CHANGED`, avec les
  deux preuves citées, et n'entre jamais dans le décompte des modifications ;
- banc Git scénarisé dans les tests : commit A (un fichier Java), commit B (ajout d'un fichier et d'un
  manifeste), commit C (suppression d'un fichier et modification d'un manifeste) ;
- le banc couvre aussi le changement de version d'évaluateur sur un même commit ;
- la comparaison est une capacité interne ; son exposition publique appartient à 01G.

## Acceptation

1. La chronologie reconstruite sur le banc A, B, C correspond exactement aux changements scénarisés,
   faits introduits, retirés, modifiés et inchangés compris.
2. Même commit, deux versions d'évaluateur : aucun changement n'est attribué au logiciel ; la cause
   possible « évolution du producteur » est portée par le résultat.
3. **Un commit qui ne change aucun fait produit zéro `INTRODUCED`, zéro `REMOVED`, zéro `MODIFIED`**,
   même si des fichiers ont changé, et même si des preuves se sont déplacées. Cas réel à ajouter au
   banc : la restriction des origines CORS de TAKIBO (`b3490e6`) ne modifie aucun fait **parmi ceux que
   les capacités en place savent produire** — endpoints et autorisations. Le jour où Taxo modélisera
   CORS, ce commit changera des faits CORS, et le banc devra le refléter.
4. Un déplacement de preuve sans changement de connaissance produit `UNCHANGED` **et**
   `EVIDENCE_CHANGED`, avec les deux preuves restituées. Les preuves des deux côtés d'un `MODIFIED` le
   sont également.
5. La comparaison ne relit jamais le dépôt : elle travaille sur la mémoire persistée.
6. Comparer un instantané avec lui-même produit uniquement des `UNCHANGED`.

## Hors périmètre

Projection PR (TAXO-PROJ-PR-01), API publique de comparaison (01G), tuiles et maille (TAXO-TILES-01
et 02), qui réutiliseront ce résultat comme critère d'invalidation.
