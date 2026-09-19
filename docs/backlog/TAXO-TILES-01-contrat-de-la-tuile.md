# TAXO-TILES-01 — Contrat de la Tuile

Statut : rédigé le 2026-09-17, **non ouvert**. L'épique TAXO-01 (01A à 01G) reste prioritaire.

Source de vérité : [ADR 0005](../adr/0005-vocabulaire-tuile-maille-contexte.md) pour le vocabulaire,
[ADR 0002](../adr/0002-contrat-du-fait.md) pour le contrat du fait,
[TAXO-POC-01](TAXO-POC-01-verite-de-reference-chaine-autorisation.md) comme étalon.

Dépend de : 01B (identité stable), 01D (couverture), 01E (persistance), TAXO-04 et TAXO-05 pour les
faits d'endpoint et d'autorisation.

## Objectif

Définir et produire la `KnowledgeTile` : une projection vérifiable et réutilisable d'un ensemble de
Facts portant sur une même frontière de connaissance, rendue à plusieurs résolutions, qui annonce son
coût en tokens, cite ses faits, déclare sa couverture et ses trous.

Une tuile n'est jamais la vérité. Elle se reconstruit depuis ses faits, et ses faits depuis leurs
preuves.

## Périmètre

- structure d'une tuile : `tile_key`, `revision`, instantané, portée, faits cités (identités de 01B),
  connaissance rendue, couverture, inconnus, dépendances **par portée**, coût annoncé par résolution ;
- **identité en trois plans**, jamais confondus :

  ```text
  tile_key   identité logique stable de la portée, ne change pas quand la connaissance evolue
  revision   empreinte de la connaissance projetée et de la version du projecteur
  snapshot   occurrence au commit
  ```

  Les empreintes de blobs ne participent à aucun des trois : elles ne servent qu'à décider d'un
  recalcul interne ;
- provenance `PROJECTION`, jamais `EVALUATOR` : une tuile ne produit aucun fait ;
- trois résolutions : L0 réponse, L1 travail, L2 diagnostic. La preuve (L3) n'est jamais incluse ;
  elle reste servie par l'API de lecture de 01G ;
- deux familles seulement : **Structure** (les endpoints d'un handler) et **Behavior** (une chaîne
  d'autorisation) ;
- rendu déterministe, sans aucune narration produite par un modèle.

## Acceptation

1. Sur TAKIBO `032788fb6d`, la tuile Behavior de `SecurityConfig` rend les règles **dans l'ordre réel
   de la chaîne**, avec leur méthode HTTP, et déclare les filtres qu'elle ne modélise pas.
2. Les cinq faits attendus de TAXO-POC-01 sont retrouvables depuis les faits cités par les tuiles
   Structure et Behavior de cette route, `MATCHED_BY` et les prémisses de `PROTECTED_BY` compris.
   Un verdict d'autorisation sans prémisse citée est un échec.
3. Un commit qui modifie des blobs sans changer aucun fait **pertinent pour la portée de la tuile** ne
   change ni sa `tile_key` ni sa `revision`. Banc : `b3490e6` (restriction des origines CORS) modifie
   16 blobs sous-jacents et zéro fait d'endpoint ou d'autorisation, les mécanismes CORS n'étant pas
   modélisés à ce jour. Mesure exploratoire du 2026-09-17, à rejouer par le banc versionné : invalider
   sur les blobs renvoyait 13 tuiles sur 16 pour rien.
4. Un changement réel de connaissance change la `revision` et **conserve** la `tile_key`.
5. Aucune tuile ne cite l'empreinte ni la révision d'une autre tuile ; les dépendances se réfèrent par
   portée.
6. Le coût est d'abord annoncé dans une unité reproductible — octets et caractères du rendu — puis
   estimé en tokens pour un **tokenizer déclaré, avec sa version**. La tolérance de 5 % ne vaut que
   pour ce tokenizer : Claude, OpenAI et les autres ne découpent pas identiquement.
7. Une tuile dont la portée a produit des couvertures `NOT_INTERPRETED` et qui ne déclare aucun trou
   est refusée.
8. Deux exécutions sur le même instantané produisent un rendu identique, octet pour octet.

## Hors périmètre

Sélection et invalidation (TAXO-TILES-02), protocole agent (TAXO-TILES-03), familles History et
Context, tuiles de module, MCP.
