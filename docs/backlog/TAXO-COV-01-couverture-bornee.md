# TAXO-COV-01 — Une couverture bornée : une absence de preuve n'est jamais une preuve d'absence

Statut : rédigé le 2026-10-02, après l'exercice « Taxo analyse Taxo ». Passe avant la tranche E de
[TAXO-01F](TAXO-01F-comparaison-persistee.md), suspendue jusqu'à la livraison de la PR B.

Source de vérité : [ARCHITECTURE § 2, § 5.1, § 6, § 12.4](../ARCHITECTURE.md). En cas de divergence, le
document cible prévaut ; ce récit en corrige l'application, pas les principes.

## Constat

Taxo a été enregistré comme projet dans son propre portail et analysé au commit `33f0bd0`. Taxo expose
25 opérations HTTP, et aucun analyseur ne lit Python. Pourtant :

- les trois analyseurs Spring ont rendu `SUCCESS`, 0 fait, et une couverture `ANALYSED` sur **tout le
  dépôt** : rien ne bornait leur couverture aux sources qu'ils savent lire ;
- le portail a affiché « 0 route relevée », « Aucune limite signalée », « Non interprétées : 0 » ;
- le protocole de la Maille a rendu, pour `verify_claim(endpoint:GET /api/health, HANDLED_BY)` :
  `NOT_PROVEN`, raison **`NOT_FOUND_IN_ANALYSED_SCOPE`**. Taxo affirmait avoir cherché la route là où il
  l'aurait trouvée. La raison juste est `NOT_ANALYSED`.

Un test du protocole écrivait même ce défaut comme attendu : sur un dépôt sans Java, une protection de
route introuvable y était « non trouvée dans le périmètre analysé », au motif que « la sécurité est
analysée ».

Le contrat avait prévu le cas sans que rien ne l'emploie : le statut d'exécution `UNSUPPORTED`, le type
de couverture `OUT_OF_SCOPE` et la raison `NOT_ANALYSED` existent. ARCHITECTURE § 3 interdit au moteur de
« confondre réussite technique et couverture complète ». C'est cette règle qui était violée.

## Intention

En tant qu'utilisateur ou agent qui interroge Taxo, quand Taxo ne trouve rien, je sais si c'est parce
qu'il a lu et n'a rien trouvé, ou parce qu'il ne sait pas lire ce qu'il aurait fallu lire, ou parce que
son analyseur n'a pas tourné ou a échoué.

## Trois dimensions, jamais confondues

| Dimension | Source | Exemple sur Taxo |
| --- | --- | --- |
| **Langages présents** | les faits `WRITTEN_IN` de l'inventaire de l'analyse | Python, TypeScript |
| **Capacité déclarée** | le catalogue de l'analyseur : ses relations **et** les langages qu'il lit pour les produire | `spring-api` v2 : `HANDLED_BY` depuis Java |
| **Couverture effective** | les faits `COVERAGE` de l'exécution et son statut | `UNSUPPORTED` : aucun fichier Java |

- Une capacité est le produit d'une relation et d'un langage. Lire Java ne suffit pas : un analyseur qui
  lit Java sans produire `HANDLED_BY` ne couvre pas une recherche `HANDLED_BY`.
- Un catalogue qui ne déclare aucun langage est **indépendant du langage** (inventaire, Git, structure du
  dépôt) : il lit le dépôt ou son historique, pas des sources. Chaque catalogue le déclare explicitement.
- Le cœur (moteur, Maille, protocole, comparaison) interprète les capacités déclarées. Il ne connaît ni
  Spring, ni FastAPI, ni aucun langage par son nom.

## États d'une capacité, pour une analyse

| État | Établi par |
| --- | --- |
| **Analysé** | une exécution aboutie (`SUCCESS`, `PARTIAL`) dont le catalogue porte la relation, qui lit au moins un langage présent, et dont la couverture `ANALYSED` englobe le sujet |
| **Partiel** | une exécution `PARTIAL`, ou des zones `NOT_INTERPRETED` / `READ_ERROR` (inchangé) |
| **Non pris en charge** | un langage présent qu'aucune exécution aboutie capable de la relation ne lit ; ou une exécution `UNSUPPORTED` |
| **Non exécuté** | aucune exécution de l'analyseur dans l'analyse |
| **Échec** | une exécution `FAILED` (inchangé) |

**Jamais** un résultat vide ne devient une couverture complète : un analyseur lié à un langage dont aucun
langage n'est présent n'est pas exécuté. Le moteur enregistre son exécution `UNSUPPORTED`, avec pour
seule couverture `OUT_OF_SCOPE` sur le dépôt et sa raison. C'est le moteur qui la produit, comme il
produit déjà la couverture d'une exécution en échec ; l'analyseur n'est pas appelé.

## Règles

1. **Catalogue.** `EvaluatorCatalog.languages` : les langages lus pour produire les relations du
   catalogue, ou `None` (indépendant du langage). Les langages portent les noms de l'inventaire. Changer
   les langages d'un catalogue est un changement de catalogue : sa version monte.
2. **Langages présents.** L'analyse enregistre les langages de son inventaire (`languages` dans son
   résultat). Une analyse antérieure qui ne les porte pas les relit dans ses faits `WRITTEN_IN`.
3. **Exécution.** Après l'inventaire, le moteur n'exécute pas un analyseur lié à des langages dont aucun
   n'est présent : `UNSUPPORTED`, couverture `OUT_OF_SCOPE`, aucun fait. **Seulement si l'inventaire a tout
   lu** (`SUCCESS`, sans zone `NOT_INTERPRETED` ni `READ_ERROR`) : sinon des fichiers non lus ont des
   langages inconnus, et chaque analyseur est exécuté pour dire lui-même ce qu'il a lu.
4. **Verdict négatif** (`verify_claim`, ARCHITECTURE § 12.4). Sans fait qui confirme ou réfute :
   - aucun analyseur capable de la relation : `NOT_ANALYSED` (inchangé) ;
   - un analyseur capable en échec, ou une zone illisible sur le sujet ou l'objet : `NOT_INTERPRETED`
     (inchangé) ;
   - les **langages concernés** sont ceux du fichier si le sujet est un fichier, sinon **tous les langages
     présents** : le sujet interrogé (`endpoint:GET /api/health`) n'a pas à exister dans le graphe pour
     que Taxo sache où il aurait dû le chercher ;
   - `NOT_FOUND_IN_ANALYSED_SCOPE` seulement si chaque langage concerné est lu par une exécution aboutie
     capable de la relation et dont la couverture `ANALYSED` englobe le sujet, ou par une exécution
     indépendante du langage qui l'englobe. Sinon `NOT_ANALYSED` ;
   - inventaire incomplet et sujet hors d'un fichier : les langages des fichiers non lus sont inconnus.
     Seule une exécution capable indépendante du langage peut alors justifier un « non trouvé » ; sinon
     `NOT_ANALYSED`, et l'enveloppe le dit (`subject: null`, `type: NOT_ANALYSED`, avec sa raison).
     `describe` dit si les langages sont complets ; le voisinage en fait une frontière `LANGUAGES_UNKNOWN`.
5. **Enveloppe du protocole.** Chaque entrée de couverture dit les langages de son producteur
   (`languages`, `null` s'il est indépendant du langage). Pour une opération portant sur une relation,
   chaque langage présent que rien ne couvre pour elle est rendu : `{"subject": "language:Python",
   "type": "NOT_ANALYSED", "relation": …}`. `describe` donne les langages présents et ceux de chaque
   analyseur.
6. **Voisinage.** Un analyseur `UNSUPPORTED` ne compte pas parmi les capacités ; un langage présent non
   couvert pour une relation suivie est une frontière de connaissance (`NOT_ANALYSED`). Le voisinage lit le
   résumé de l'analyse, sans parcourir ses faits : pour une analyse antérieure, qui n'enregistre pas ses
   langages, il ne les nomme pas ; ses verdicts, eux, restent bornés.
7. **Comparaison (TAXO-01F).** Un analyseur lié à des langages dont aucun n'est présent d'un côté (selon
   un inventaire complet), ou `UNSUPPORTED` d'un côté, n'est **pas comparable** de ce côté, avec sa raison. Comparer deux absences de
   lecture n'est jamais « aucun changement ». Pour un analyseur comparable, la réponse donne les langages
   présents qu'il ne lit pas, de chaque côté (`not_analysed`). Un catalogue dont Taxo ne connaît pas le
   contrat reste comparé comme avant : comparer des faits enregistrés ne suppose rien de ce qui n'a pas
   été lu.

## Analyses antérieures : compatibilité explicite

Les analyses enregistrées ne sont ni modifiées ni migrées. Leur couverture reste consultable telle
qu'elle a été écrite.

Sa **capacité à justifier un verdict négatif** est examinée selon le contrat du producteur qui l'a
écrite : le catalogue enregistré avec l'exécution (`catalog_id`, `catalog_version`). Une couverture
`ANALYSED` du dépôt par `spring-api` v2 vaut pour Java, parce que c'est ce que ce catalogue sait lire, et
non pour le dépôt entier qu'elle nomme. Un catalogue dont Taxo ne connaît plus le contrat ne justifie
aucun verdict négatif. La même règle vaut pour les analyses anciennes et nouvelles : une analyse ancienne
de Taxo répond désormais `NOT_ANALYSED` sur ses routes, sans réécriture.

La version de catalogue ne monte pas : les catalogues déclarent ce que leurs analyseurs ont toujours lu.
Les versions de producteur ne montent pas : aucun analyseur ne change ce qu'il produit quand il est
exécuté.

## Livraison

| PR | Périmètre |
| --- | --- |
| **A — Contrat et protocole** | catalogues, moteur (`UNSUPPORTED`, `OUT_OF_SCOPE`), langages de l'analyse, module générique des capacités, verdicts, enveloppe et `describe`, voisinage, comparabilité, ARCHITECTURE ; tests backend |
| **B — Restitution** | Overview (« fichiers inventoriés » et non « analysés »), Routes, Sécurité, limites, comparaisons ; validation sur le dépôt Taxo |

Hors périmètre : un analyseur FastAPI ou Python ; l'impact d'un commit (`/history/.../impact`), qui
relance les analyseurs sans inventaire préalable et sera remplacé par la tranche E de 01F.

## Critères d'acceptation

1. Sur un dépôt sans Java, les analyseurs Spring sont `UNSUPPORTED`, sans fait, avec pour couverture
   `OUT_OF_SCOPE` et sa raison ; aucun n'est exécuté.
2. `verify_claim(endpoint:GET /api/health, HANDLED_BY)` sur un dépôt Python rend `NOT_ANALYSED`, et
   l'enveloppe nomme Python comme non analysé pour `HANDLED_BY`.
3. Sur un dépôt Java et Python, la même question rend `NOT_ANALYSED` ; sur un dépôt Java seul, une route
   absente reste `NOT_FOUND_IN_ANALYSED_SCOPE`.
4. Une analyse antérieure, couverture `ANALYSED` du dépôt écrite par un catalogue lié à Java, ne justifie
   pas un verdict négatif sur un dépôt sans Java.
5. Un analyseur lié à un langage absent d'un côté d'une comparaison n'y est jamais compté « aucun
   changement » ; deux versions de producteur d'un même catalogue restent comparables quand leurs
   langages sont présents, avec leurs vrais changements.
6. Aucune condition sur un nom de langage ou d'analyseur dans le moteur, la Maille, le protocole ou la
   comparaison.

## Références expérimentales : « Taxo analyse Taxo »

Deux analyses du dépôt Taxo servent de témoins, avant et après correction. Elles ne sont pas conservées
dans une base : elles se reproduisent à l'identique.

**Procédure** (base vierge, migrations Alembic jusqu'à `006`) :

```bash
git clone https://github.com/kadt2022/taxo.git <racine>/taxo
cd backend
DATABASE_URL=sqlite:///<base>.db python -m alembic upgrade head
DATABASE_URL=sqlite:///<base>.db TAXO_ALLOWED_ROOTS=<racine> \
  python -m uvicorn app.main:create_app --factory --port 8000
curl -X POST localhost:8000/api/projects -H 'content-type: application/json' \
  -d '{"name": "Taxo", "path": "<racine>/taxo"}'
curl -X POST "localhost:8000/api/projects/<id>/scans?commit=33f0bd04b1521b9393279bdf6039a7f25ce5d099"
curl -X POST "localhost:8000/api/projects/<id>/scans?commit=cb8d90a1f1a136e4f31d3a4bc711bda67c1041d1"
```

**Vérité écrite à la main**, indépendante de Taxo (`git ls-files`, `git rev-list`, `git log --merges`,
`git diff --stat`, décorateurs `@router.*` du backend) :

| Assertion | `33f0bd0` | `cb8d90a` |
| --- | --- | --- |
| fichiers (`CONTAINS` de l'inventaire) | 422 | 420 |
| `WRITTEN_IN` Python / TypeScript | 227 / 53 | 227 / 51 |
| commits (`HAS_COMMIT`) / `CHILD_OF` | 151 / 167 | 150 / 166 |
| opérations HTTP réelles | 25 | 25 |
| fichiers Java | 0 | 0 |

Comparaison `cb8d90a` → `33f0bd0` (13 fichiers : 2 créés, 11 modifiés dont 8 de code) : fichiers 2
ajoutés et 11 preuves déplacées ; identifications de langage 2 ajoutées et 8 déplacées ; Git 1 commit,
1 lien de parenté, 13 modifications de fichier.

**Attendu avant correction** (code de `33f0bd0`, constaté) : `spring-api`, `spring-boot` et
`spring-security` en `SUCCESS`, 0 fait, `ANALYSED` sur le dépôt ; `verify_claim(endpoint:GET /api/health,
HANDLED_BY)` → `NOT_FOUND_IN_ANALYSED_SCOPE` ; la comparaison compte API et Sécurité « Aucun changement ».

**Attendu après correction**, sur les mêmes commits :

- nouvelles analyses : les trois analyseurs Spring `UNSUPPORTED`, couverture `OUT_OF_SCOPE`, 0 fait ;
  les comptes de l'inventaire et de Git inchangés ;
- `verify_claim(endpoint:GET /api/health, HANDLED_BY)` → `NOT_ANALYSED`, sur une nouvelle analyse **et**
  sur une analyse faite avec le code de `33f0bd0` (compatibilité) ; l'enveloppe nomme Python et
  TypeScript non analysés pour `HANDLED_BY` ;
- la comparaison `cb8d90a` → `33f0bd0` : les trois analyseurs Spring non comparables, avec leur raison ;
  inventaire et Git inchangés (mêmes comptes que ci-dessus) ;
- l'analyse de référence de `33f0bd0` comparée à sa nouvelle analyse : inventaire (1 004 faits) et Git
  (2 356) identiques, structure (4) identique, les trois analyseurs Spring non comparables.

Constaté le 2026-10-02 avec le code de la PR A : toutes ces assertions tiennent.
