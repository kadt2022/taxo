# TAXO-01D — Exécution d'évaluateur et couverture

Statut : implémenté sur `feat/taxo-01d-evaluator-execution-coverage`, PR #8 en revue. À déplacer dans `Terminé` après validation et merge.

Source de vérité : [T4 de l'EPIC TAXO-01](EPIC-TAXO-01-fondation-memoire-verifiable.md). En cas de divergence avec un récit antérieur, T4 prévaut.

## Objectif

Exécuter un évaluateur versionné sur un snapshot déterminé et rendre une `EvaluatorExecution` non persistée contenant identifiant, producteur, catalogue, snapshot, `started_at`, `finished_at`, statut, périmètre structuré `{include, exclude}`, Facts et au moins une `COVERAGE`. `RUNNING`, `SUCCESS`, `PARTIAL`, `FAILED` et `UNSUPPORTED` sont les statuts techniques.

`SUCCESS` signifie que l'exécution technique s'est achevée. Un manifeste invalide, un fichier non UTF-8 ou une limite volontaire de compréhension conserve `SUCCESS` et déclare `NOT_INTERPRETED`. Une erreur réelle de lecture donne `PARTIAL` avec `READ_ERROR`. Un échec global donne `FAILED` et déclare aussi sa couverture.

## Périmètre

- `evaluations` définit le contrat générique, le catalogue, le registre explicite et `RunEvaluator`. Le moteur ne connaît aucun évaluateur concret.
- Inventory v0 produit les relations `CONTAINS`, `WRITTEN_IN`, `USES_TECHNOLOGY` et `DECLARED_BY`, avec preuve, provenance et identité canonique du contrat v1.
- Le catalogue Inventory annonce uniquement ses relations et couvertures effectivement produites : `ANALYSED`, `NOT_INTERPRETED`, `READ_ERROR`.
- `RunScan` ouvre le snapshot et passe exclusivement par `RunEvaluator`. Le JSON historique de l'API dérive de l'`EvaluatorExecution` et de l'`EvaluationOutput` jusqu'à 01E.

## Acceptation

- Chaque exécution contient les métadonnées T4 et une couverture conforme au contrat v1, y compris en cas d'échec.
- Les limitations de compréhension et les erreurs de lecture produisent des statuts et couvertures distincts.
- Le registre refuse les doublons et expose un ordre stable.
- Inventory est testable avec un snapshot mémoire ; ses faits, couvertures et identités sont reproductibles pour un même commit et une même version.
- L'API existante fonctionne ; la suite de conformité TAXO-01A et la suite backend passent.
- PostgreSQL, Docker Smoke et Sonar Quality Gate passent sur la PR avant merge.

## Hors périmètre

Aucune table de mémoire, comparaison entre commits, API de consultation des faits, analyse Gradle/Java/Spring, file de travail ou production de faits par LLM. La persistance appartient à TAXO-01E.
