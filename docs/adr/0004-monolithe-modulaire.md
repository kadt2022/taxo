# ADR 0004 — Monolithe modulaire par capacité

Statut : adopté pour TAXO-ARCH-01. L'identifiant 0003 reste réservé au spike Java Analyzer.

## Décision

Taxo organise son backend par capacité : `projects`, `snapshots`, `facts`, `scans`,
`evaluations` et `evaluators`. Dans chaque capacité, les frontières domaine,
application, infrastructure et API sont introduites lorsque du code existant les justifie.
`bootstrap` compose l'application ; `platform` accueille la base SQLAlchemy et les
adaptateurs HTTP communs. Aucun package `utils` généraliste.

Les dépendances suivent ces règles :

1. La capacité précède la couche ; aucune couche globale regroupant les fonctionnalités.
2. Le domaine ne dépend ni de FastAPI, SQLAlchemy, psycopg, subprocess, Git ou du système de fichiers.
3. L'application dépend du domaine et de ports ; elle ne construit pas les adaptateurs.
4. Les adaptateurs satisfont les Protocols du domaine/application par typage structurel.
5. L'API appelle les cas d'utilisation et ne manipule ni sessions ni modèles SQLAlchemy.
6. Les évaluateurs ne persistent pas leurs résultats.
7. Ils ne connaissent pas FastAPI.
8. Leur entrée est un snapshot ; aucun parcours direct du système de fichiers.
9. À partir de 01D, ils produisent Facts/Coverage ; le stockage est une autre responsabilité.
10. `evaluations` sera le moteur générique (exécutions, statuts, catalogue, registre),
    indépendant des langages et frameworks ; `evaluators` contient les implémentations.
11. Java Analyzer ne connaît pas Spring.
12. Spring API consomme les primitives Java.
13. Les projections lisent la mémoire et ne rescannent pas le dépôt.
14. Ask Taxo consomme projections/mémoire ; le LLM ne produit pas de faits.
15. Pas de package fourre-tout ni de classe/fichier sans responsabilité existante.

## Extraction réalisée dans ARCH-01

- `main.py` garde la factory publique utilisée par Uvicorn ; `bootstrap.application`
  câble les routes, repositories, résolution de chemins, lecteur Git et inventaire.
- `projects` possède l'enregistrement, les erreurs et la politique de chemins autorisés.
- `scans` orchestre la lecture du projet, l'ouverture du snapshot, l'inventaire et la persistance.
- `snapshots.domain.Snapshot` expose les métadonnées et délègue la lecture à
  `SnapshotContent`. `SnapshotReader` ouvre les snapshots ; `GitSnapshotReader`
  contient les opérations Git et disque de 01C. Les algorithmes et limites sont conservés.
- `evaluators/inventory` reçoit exclusivement un snapshot et conserve les détections
  existantes. Les détecteurs de noms de fichiers restent regroupés : leur taille ne
  justifie pas encore trois modules distincts.
- `facts.domain` contient règles sémantiques, normalisation d'identité et empreintes.
  `facts.application` orchestre validation structurelle puis sémantique via un port.
  Le schéma et sa suite de conformité sont dans `facts/infrastructure/contract`.
  `facts.contract` conserve la façade Python v1 et son câblage, y compris la
  sérialisation canonique RFC 8785 ; le domaine n'importe pas JSON Schema.
- Alembic charge les mappings via `bootstrap.database`, sans créer de serveur.

Les dictionnaires métier existants ne sont pas remplacés par un nouveau modèle
de classes Fact/Assertion/Absence/Coverage dans ce refactoring. Leur représentation
et la conformité v1 restent identiques. Les Protocols suffisent aux frontières ;
aucune hiérarchie de repositories abstraits n'est nécessaire.

## Portée et suites

ARCH-01 ne crée ni EvaluatorExecution, registre, catalogue exécutable, nouveau fait,
couverture ou table. `evaluations` sera créé dans 01D lorsque ces responsabilités
existeront. L'inventaire garde son JSON historique jusqu'à cette conversion.
01E remplacera ensuite `scans.result` comme mémoire de référence.
TAXO-02 enrichira Inventory, notamment avec Gradle.

Le contrat HTTP, la factory `app.main:create_app`, les migrations et la façade
`app.facts` restent stables. Les anciens imports internes `app.scanner`,
`app.snapshots.open_snapshot` et `app.main.Base` sont remplacés dans les tests et
outils internes. Les chemins du schéma et des fixtures changent, pas leurs octets.

## Vérification

Les 316 tests existants gardent leurs assertions ; seuls leurs imports et chemins
de ressources suivent les nouvelles frontières. Des tests supplémentaires protègent
les dépendances, l'inventaire en mémoire sans Git/disque et l'absence de persistance
après un échec de snapshot. La CLI de conformité, le contrat OpenAPI et les migrations
font également partie de la vérification du refactoring.
