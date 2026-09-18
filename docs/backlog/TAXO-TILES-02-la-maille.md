# TAXO-TILES-02 — La Maille

Statut : rédigé le 2026-09-17, **non ouvert**. L'épique TAXO-01 (01A à 01G) reste prioritaire.

Source de vérité : [ADR 0005](../adr/0005-vocabulaire-tuile-maille-contexte.md).

Dépend de : TAXO-TILES-01, et de **01I Voisinage et projectabilité**, dont le parcours est réutilisé.
La maille n'invente pas un second mécanisme de voisinage.

## Objectif

Relier les tuiles, invalider de façon incrémentale, et sélectionner la connaissance nécessaire par
parcours depuis une ancre, sous un budget de tokens.

## Périmètre

- **les relations de maille se dérivent des faits**, elles ne sont jamais saisies à la main : une
  tuile dépend de celles dont ses faits `INFERRED` tirent leurs prémisses. Chaîne de référence :
  `PROTECTED_BY` dépend de `MATCHED_BY`, qui dépend de `AUTHORIZED_BY` ;
- invalidation : un fait change, les tuiles qui le citent se reconstruisent, la propagation suit les
  dépendances et s'arrête là. Le sous-graphe reconstruit est le plus petit possible ;
- sélection : une ancre (entité ou tuile), un parcours de voisinage, un budget, un ordre de priorité
  stable et un arrêt déterministe ;
- lorsque le budget ne suffit pas pour une tuile à la résolution demandée, la maille rend la
  résolution inférieure. **Elle ne tronque jamais une tuile** : une connaissance coupée est une
  connaissance fausse ;
- un banc reproductible mesure, à chaque exécution, le rapport entre les tokens des fichiers
  sous-jacents et les tokens remis.

## Acceptation

1. Un commit qui ne change aucun fait n'invalide aucune tuile et ne déclenche aucune reconstruction.
   Banc : `b3490e6` sur TAKIBO.
2. Un commit qui modifie une règle de la chaîne de sécurité invalide la tuile Behavior et **exactement**
   les tuiles Structure dont un verdict change ; les autres restent valides.
3. Ancre `symbol:SpaceController`, budget 600 tokens : la sélection contient la tuile Structure du
   contrôleur et la tuile Behavior de la chaîne, et **ne contient pas** le catalogue RBAC. Le
   prototype lexical du 2026-09-17 le retenait à tort : c'est le défaut que ce récit corrige.
4. Le budget n'est jamais dépassé, et le dépassement évité par abaissement de résolution est journalisé.
5. Deux sélections identiques sur le même instantané renvoient les mêmes tuiles dans le même ordre.
6. Aucun modèle de langage n'intervient dans la construction du graphe, l'invalidation ou la sélection.
7. Le banc publie le rapport d'amplification ; la mesure de référence du 2026-09-17 est de 8,0x à 9,9x
   sur TAKIBO.

## Hors périmètre

Protocole d'échange avec les agents et cache inter-session (TAXO-TILES-03), familles de tuiles
supplémentaires, MCP.
