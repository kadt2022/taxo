# TAXO-01E — Persistance de la mémoire vérifiable

Statut : rédigé le 2026-09-17, à ouvrir après la fusion de 01D.

Source de vérité : [T5 de l'EPIC TAXO-01](EPIC-TAXO-01-fondation-memoire-verifiable.md). En cas de
divergence avec un récit antérieur, T5 prévaut. Contrat du fait : [ADR 0002](../adr/0002-contrat-du-fait.md).

Dépend de : 01A (contrat), 01B (identité stable), 01C (instantané), 01D (exécution et couverture).

## Objectif

Conserver les faits indépendamment de la projection qui les utilisera. `scans.result` cesse d'être la
source de vérité : instantanés, exécutions, faits, occurrences, preuves, couvertures, dérivations et
validations humaines deviennent interrogeables séparément, et l'identité stable de 01B est calculée
puis indexée.

## Périmètre

- structures persistantes pour : instantanés, exécutions d'évaluateur, faits, **occurrences**,
  preuves, couvertures, **dérivations** (les prémisses d'un fait `INFERRED`) et validations humaines ;
- un fait existe une fois ; chaque exécution qui le produit ajoute une **occurrence** portant
  l'exécution, l'instantané et la provenance ;
- les dérivations sont persistées comme des liens fait vers prémisses : sans elles, un
  `PROTECTED_BY` ne peut pas être expliqué, ce qu'exigent l'ADR 0002 et TAXO-POC-01 ;
- l'identité stable est indexée, ainsi que sujet, objet, relation et instantané ;
- migrations Alembic, appliquées au démarrage comme aujourd'hui ;
- le JSON historique de l'API continue d'être servi, mais **dérivé** de la mémoire persistée.

Le choix physique du stockage reste une décision d'implémentation. **Aucun moteur de graphe n'est
requis par ce récit.**

## Acceptation

1. Réexécuter le même évaluateur sur le même instantané ne duplique aucun fait : une occurrence de
   plus, une identité stable inchangée.
2. Réexécuter avec une version de producteur différente conserve l'identité du fait et distingue les
   deux occurrences par leur producteur et sa version.
3. Les preuves d'un fait sont retrouvables depuis ce fait, et une `ABSENCE` n'en porte aucune.
4. Une exécution `FAILED` ou `PARTIAL` persiste malgré tout sa couverture.
5. Un fait `INFERRED` relu depuis la base restitue ses prémisses dans l'ordre.
6. Aller-retour sans perte : les faits relus depuis la base repassent la suite de conformité de 01A.
7. Migration vérifiée sur base vide et sur une base portant des scans existants.

## Hors périmètre

API de lecture et vue (01G), comparaison d'instantanés (01F), voisinage (01I), validité `STALE` et
`REVALIDATION_REQUIRED` (01H), moteur de graphe.
