# TAXO-MINIA-01 — Demander à Minia ce que signifie un commit

Statut : livré dans la PR de la branche `feat/taxo-minia-01-ask-commit`.
Dépend de : TAXO-HIST-01 (impact d'un commit), ADR 0004 (règle 14 : le LLM ne produit pas de faits),
ADR 0006 (Clochette reste séparée).

## Objectif

Depuis la fiche d'un commit, poser une question en langage courant et recevoir une réponse qui sépare
toujours ce que Taxo a prouvé, ce que Minia en déduit, et ce qui reste inconnu.

## Règles

1. Minia ne reçoit que les faits changés par le commit, leurs preuves réduites à leur localisation
   (chemin, lignes, commit), les zones non interprétées, les évaluateurs en échec, les métadonnées du
   commit et la liste Git de ses fichiers (statut, chemin, ancien chemin d'un renommage). Jamais de code
   source, jamais le contenu d'une preuve ni d'un fichier.
2. Le modèle rend des références (F1, F2…) et du texte. Les faits affichés sont ceux de Taxo, retrouvés
   par référence ; une référence inconnue est écartée et signalée.
3. Une réponse de Minia n'est jamais un fait : elle n'est ni validée par le contrat, ni conservée.
4. Si Taxo n'a vu changer aucun fait et qu'aucun évaluateur n'a échoué, le modèle n'est pas appelé :
   Minia dit qu'elle ne sait pas. Une zone non interprétée seule ne suffit pas à l'appeler : elle peut
   exister dans tous les instantanés sans que le commit l'ait touchée (MINIA-01b).
4 bis. Ce que Git sait du commit (auteur, date, message, fichiers) est toujours affiché, tiré de Git et
   non du modèle, quelle que soit sa réponse (MINIA-01b).
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

## MINIA-01b — ancrage Git (premiers essais avec qwen2.5:3b)

Les premiers essais réels ont montré un modèle qui affirmait sans appui, recopiait le gabarit de la
consigne (« … »), ignorait l'auteur pourtant transmis, et lisait un déplacement de fichiers comme une
suppression. Corrections : règles 4 et 4 bis ci-dessus ; liste Git des fichiers transmise (renommages
compris) ; consigne sans valeurs d'exemple, but du commit toujours au conditionnel, message du commit
présenté comme une déclaration de son auteur ; texte fait seulement de points de suspension traité comme
vide ; type de changement et nom du projet affichés dans le portail.
