# TAXO-01G — API de lecture et vue de vérification

Statut : rédigé le 2026-09-17, à ouvrir après 01F.

Source de vérité : [T9 et T10 de l'EPIC TAXO-01](EPIC-TAXO-01-fondation-memoire-verifiable.md).

Dépend de : 01E (persistance), 01F (comparaison). Les capacités de validité dépendent de 01H.

## Objectif

Offrir le **contrat de lecture** que toutes les projections futures utiliseront — PR, diagrammes, Ask
Taxo, MCP, analyse d'impact — pour qu'aucune n'accède aux tables internes ni au scanner. Et donner à
l'équipe une vue permettant de vérifier la mémoire à l'œil, avant de construire des projections plus
riches.

## Périmètre

Capacités de lecture : faits d'un instantané ; fait par identité ; faits par sujet, par objet, par
relation ; voisinage d'une entité ; preuves d'un fait ; couverture d'une exécution ; évaluateurs
exécutés pour un instantané ; faits non interprétés ; faits `STALE` ; faits `REVALIDATION_REQUIRED` ;
comparaison de deux instantanés.

Vue minimale du portail, affichant pour chaque fait : identité, nature, statut, validité, sujet,
relation, objet, périmètre, instantané, type de producteur, producteur, version du producteur, preuve,
couverture et trous.

- les réponses sont déterministes et paginées ;
- **une preuve n'est jamais incluse dans une réponse de liste** : elle se demande fait par fait ;
- l'API ne relit jamais le dépôt ;
- tant que 01H n'est pas livré, les capacités `STALE` et `REVALIDATION_REQUIRED` répondent
  explicitement « non encore produites », jamais une liste vide silencieuse.

## Acceptation

1. Chaque capacité listée est couverte par un test, y compris les deux capacités de validité en
   attente de 01H.
2. Aucune projection, aucun test de projection, n'accède aux tables ou au scanner.
3. La vue permet de vérifier un fait de bout en bout : identité, preuve, couverture, producteur et
   version.
4. Deux appels identiques sur le même instantané renvoient le même résultat, dans le même ordre.
5. Une réponse de liste ne contient aucun extrait de code.
6. Aucun chatbot, aucun diagramme, aucune narration dans ce récit.

## Hors périmètre

Ask Taxo, MCP, diagrammes, tuiles et contexte (TAXO-TILES-03, qui consommera cette API pour les
preuves).
