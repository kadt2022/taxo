# TAXO-MINIA-01 — Demander à Minia ce que signifie un commit

Statut : livré dans la PR de la branche `feat/taxo-minia-01-ask-commit`.
Dépend de : TAXO-HIST-01 (impact d'un commit), ADR 0004 (règle 14 : le LLM ne produit pas de faits),
ADR 0006 (Clochette reste séparée).

## Objectif

Depuis la fiche d'un commit, poser une question en langage courant et recevoir une réponse qui sépare
toujours ce que Taxo a prouvé, ce que Minia en déduit, et ce qui reste inconnu.

## Règles

1. Minia ne reçoit que les faits changés par le commit, leurs preuves réduites à leur localisation
   (chemin, lignes, commit), les zones non interprétées, les évaluateurs en échec et les métadonnées du
   commit. Jamais de code source, jamais le contenu d'une preuve.
2. Le modèle rend des références (F1, F2…) et du texte. Les faits affichés sont ceux de Taxo, retrouvés
   par référence ; une référence inconnue est écartée et signalée.
3. Une réponse de Minia n'est jamais un fait : elle n'est ni validée par le contrat, ni conservée.
4. Si Taxo n'a vu changer aucun fait, et ne signale ni zone non interprétée ni échec, le modèle n'est
   pas appelé : Minia dit qu'elle ne sait pas.
5. Le modèle est derrière le port `MiniaModel`. MINIA-01 livre l'adaptateur Ollama (gratuit) ;
   Claude pourra s'ajouter plus tard sans changer le domaine.
6. Pas de mémoire conversationnelle : chaque question est indépendante.
7. Minia n'importe ni `app.facts`, ni `app.hypotheses` (Clochette), ni `app.evaluations` ; un test
   d'architecture le vérifie.

## Configuration

`MINIA_PROVIDER=ollama` (par défaut), `MINIA_OLLAMA_URL=http://127.0.0.1:11434` (par défaut),
`MINIA_OLLAMA_MODEL=<modèle>` (par exemple `qwen2.5:3b`). Sans modèle, Minia est désactivée.

`MINIA_OLLAMA_URL` peut viser un Ollama local ou distant ; l'adresse n'est pas restreinte. Seule la
projection de la règle 1 est transmise, jamais le code source brut ; mais si Ollama est distant, ces
données quittent le processus et la machine de Taxo.

## Hors périmètre

Adaptateur Claude ; questions sur une route ou un fichier plutôt qu'un commit ; mémoire de conversation ;
évaluation de la qualité des réponses (à mesurer avec le benchmark du PLAN).
