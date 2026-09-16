# TAXO-ARCH-01 — Modulariser le backend selon l'architecture DDD/hexagonale

Position : après 01A/01B/01C, avant 01D. Décision : [ADR 0004](../adr/0004-monolithe-modulaire.md).

## Objectif

Extraire les capacités du backend et leurs frontières techniques sans nouveau
comportement métier. Préparer l'arrivée de plusieurs évaluateurs et de la mémoire.

## Périmètre

- Extraire bootstrap, projets, scans et adaptateurs SQLAlchemy de `main.py`.
- Séparer le domaine snapshot des lectures Git/disque et introduire ses ports.
- Déplacer le scanner dans `evaluators/inventory`, avec entrée Snapshot.
- Séparer règles de faits, orchestration de validation et adaptateur JSON Schema.
- Mettre à jour imports, migrations, chemins de ressources et documentation.
- Ajouter des garde-fous de dépendances architecturales.

## Acceptation

- Les 316 tests de référence passent avec les mêmes assertions métier.
- Contrat HTTP/OpenAPI, persistance, snapshots et faits restent identiques.
- Schéma JSON et vecteurs de conformité sont déplacés sans modification.
- Les domaines n'importent aucune infrastructure ; l'API ne dépend pas de SQLAlchemy.
- L'inventaire fonctionne avec un snapshot en mémoire sans accès Git/disque.

## Hors périmètre

01D ajoutera `evaluations`, les exécutions, statuts, registre, catalogues et la
conversion de l'inventaire en Facts/Coverage. 01E ajoutera la mémoire persistante.
TAXO-02 reste consacré à l'enrichissement de l'inventaire (dont Gradle).

## Validation locale

Base de comparaison : commit `6f8b245` de TAXO-01C, 316 tests réussis avant refactoring.

- 320 tests réussis : les 316 existants et quatre garde-fous d'architecture.
- Comparaison des documents OpenAPI avant/après : identiques.
- Schéma et tous les vecteurs de conformité : identiques octet pour octet.
- CLI : 76 cas de contrat, 8 vecteurs d'empreinte, 19 identités positives et
  5 négatives ; aucun échec.
- SQLite : `alembic upgrade head`, `check`, `downgrade base`, `upgrade head`,
  `check` ; aucun écart entre modèles et migrations.
- Le contrôle CI de persistance de l'API passe sur cette base SQLite migrée,
  y compris après création d'une seconde instance de l'application.

Les validations PostgreSQL, Docker et Sonar restent celles du pipeline CI ; elles
n'ont pas été exécutées dans cette validation locale. Deux avertissements de
dépréciation Starlette/httpx/anyio étaient déjà présents avant refactoring.
