# TAXO-TILES-03 — Contexte et protocole agent

Statut : rédigé le 2026-09-17, **non ouvert**. L'épique TAXO-01 (01A à 01G) reste prioritaire.

Source de vérité : [ADR 0005](../adr/0005-vocabulaire-tuile-maille-contexte.md).

Dépend de : TAXO-TILES-01, TAXO-TILES-02, et de l'API de lecture de 01G pour les preuves.

## Objectif

Remettre à un agent le `ContextSelection` minimal pour sa tâche : les tuiles nécessaires, à la
résolution nécessaire, sous le budget disponible, sans jamais envoyer la mémoire entière ni le code.

## Périmètre

- opérations : `context(ancre, budget, known, zoom)`, `tile(identité, zoom)`, `evidence(fait)`,
  `delta(instantané_a, instantané_b, known)` ;
- toute réponse dit ce qu'elle **omet** et pourquoi : budget, résolution abaissée, portée non couverte ;
- **preuve paresseuse** : aucun extrait de code n'est transmis sans demande explicite ;
- **déduplication de session** : l'appelant annonce ce qu'il détient par couples `tile_key + revision`.
  Une `tile_key` connue dont la `revision` n'a pas bougé est confirmée valide sans rien renvoyer ; une
  `revision` différente renvoie la tuile à jour. L'identité seule ne suffit pas : elle dit de quoi on
  parle, pas si c'est encore vrai ;
- cache par empreinte (instantané, sélection, version du projecteur, versions des évaluateurs) ; tout
  changement de version invalide l'entrée ;
- catégorie `ZERO-LLM` : les réponses servies sans appel à un modèle sont comptées et affichées comme
  telles ;
- le banc publie, pour chaque tâche, les tokens remis, les tokens des fichiers sous-jacents et le
  rapport d'amplification.

## Acceptation

1. Banc de huit questions réelles sur TAKIBO et `portail-math` : chaque réponse est juste, ses
   inconnues sont déclarées, et le contexte ajouté reste **sous 2 000 tokens du tokenizer déclaré**,
   dont la référence et la version sont inscrites dans le banc.
2. Dépôt inchangé, session connue : aucune `revision` n'a changé, donc **zéro tuile renvoyée** et la
   réponse confirme « toujours valides » par `tile_key`.
3. Rapport d'amplification d'au moins 8x sur le banc TAKIBO, mesuré par le **banc versionné dans le
   dépôt**. Le 8,0x à 9,9x du 2026-09-17 vient d'un prototype jetable et ne fait pas référence.
4. Aucune preuve transmise sans demande ; un test vérifie qu'aucune réponse de `context` ne contient de
   code source.
5. Le budget demandé n'est jamais dépassé, y compris déduplication et mentions d'omission comprises.
6. Un deuxième appel identique est servi par le cache, sans recalcul ; changer la version d'un
   évaluateur invalide l'entrée et le prouve par un test.
7. Une affirmation fausse au banc est un échec bloquant du récit, même si les compteurs de tokens sont
   bons.

## Hors périmètre

Serveur MCP (LATER), Ask Taxo et toute narration, interface utilisateur, tuiles temporaires de tâche
persistées — une sélection se recalcule, elle ne se stocke pas comme vérité.
