# TAXO-E1 — Structure et unités déployables

Statut : rédigé le 2026-09-27. Tranche 1 en cours.

Décision : [ADR 0012](../adr/0012-structure-et-unites-deployables.md). Défaut : D1 (`DEFAUTS-MESURES.md`).
Jalon E1 de la section « Élargissement » du plan.

## Pourquoi

Premier jalon utile à un projet **sans Spring** : de quoi le dépôt est fait, qui dépend de qui,
ce qui se déploie. Il est aussi le prérequis pour résoudre D1 : savoir quelle application sert une
route, et quelles règles de sécurité elle charge.

## Tranche 1 — structure générique (`taxo.structure`)

**Lit**, sans rien exécuter :

| Système | Modules | Dépendances entre modules |
| --- | --- | --- |
| Gradle (Groovy et Kotlin) | `include` littéraux de `settings.gradle(.kts)` ; projet unique à la racine sans `settings` | `project(':x')` littéral, avec sa configuration |
| Maven | `<modules>` du `pom.xml` racine, récursivement | `<dependency>` vers l'`artifactId` (et le `groupId`) d'un module du dépôt, avec son `scope` |
| npm | chaque `package.json` hors dossiers ignorés ; `workspaces` | dépendance vers le nom d'un paquet du dépôt, ou `file:` vers son dossier |
| Python | dossier portant `pyproject.toml`, `setup.py` ou `requirements.txt` | non lues ; une dépendance par chemin (`-e`, `path =`, `file:`) est déclarée non interprétée |
| compose | services avec `build` (chaîne ou `context`) | — ; produit `application BUILT_FROM module` |

**Produit** `repository CONTAINS module`, `module DEPENDS_ON module` et
`application BUILT_FROM module`, avec preuve à la ligne. Ce qui n'est pas lu est
`NOT_INTERPRETED` sur son fichier.

### Acceptation

1. Sur Taxo lui-même :
   - deux modules : `backend` (Python) et `frontend` (npm) ;
   - deux applications : `compose.yaml#api`, construite depuis `backend`, et
     `compose.yaml#portal`, construite depuis `frontend` ;
   - `db`, service à image externe, ne produit aucun fait et n'est pas une lacune.
2. Sur TAKIBO (`6d9b214`) :
   - les 18 modules de `settings.gradle` ;
   - les dépendances `project(...)` de chaque `build.gradle`, avec leur configuration.
3. Chaque construction non lue du tableau de l'ADR 0012 (§ 2) a son test et produit une couverture
   `NOT_INTERPRETED`, jamais un module ni une dépendance devinés.
4. Une dépendance vers un module inconnu est déclarée non interprétée.
5. L'impact d'un commit montre un module ajouté et une dépendance ajoutée.
6. Tous les faits passent le contrat. Le vocabulaire, le schéma et la conformité évoluent ensemble.

## Tranche 2 — applications Spring Boot et routes servies

**Critère d'acceptation explicite** : pour chaque route, établir l'application qui l'expose et les
chaînes de filtres que cette application charge. Sur TAKIBO :
- les routes de `takibo-identity-core` et `takibo-management-service` sont servies par
  `TakiboIamBootApplication` ;
- `GET /api/admin/users` est servie par `AdpTestApplication`, et protégée par `TestSecurityConfig`,
  non par `SecurityConfig`.

TAXO-05 lève alors sa garde « plusieurs applications » là où la tranche 2 conclut. Il la garde là
où elle ne conclut pas : scan calculé, dépendance non lue, classe hors de tout module.

## Hors périmètre

Dépendances externes et versions (E2), images externes, `depends_on`, Dockerfile seul, Kubernetes,
composite builds.
