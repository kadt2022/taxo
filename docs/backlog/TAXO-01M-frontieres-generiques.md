# TAXO-01M — Contrat générique des frontières de connaissance et de périmètre

Statut : **proposé, corrigé après audit**. Il attend la validation avant toute implémentation.
Date : 2026-10-08.
Source de vérité : `ARCHITECTURE.md` § 5.5, § 9.3 et § 14 ; [TAXO-01J](TAXO-01J-navigation-multiniveau-et-explorateur.md) § 5 et § 8.
Dépend de : TAXO-01K (diagnostic des sites, livré). TAXO-01L (#99, non fusionné) n'est nécessaire qu'à la PR D.
Ne dépend ni de Minia, ni d'un LLM, ni de MIP.

## Problème

Un site d'appel que `taxo.java-calls` ne résout pas est décrit dans le `diagnostic` d'une couverture
`NOT_INTERPRETED`, avec une raison fermée (`TARGET_TYPE_OUTSIDE_SNAPSHOT`, `RECEIVER_TYPE_UNKNOWN`…).
Ces raisons sont utiles, mais elles sont propres à Java. Elles sont aussi figées dans le schéma **commun**
(`contract-v1.schema.json`, `$defs.site.reason`). Un producteur Python devrait donc modifier le contrat commun
pour ajouter ses codes. Et aucune catégorie générique ne dit à un lecteur ce que vaut une frontière, quel que
soit le langage.

Doctrine : **un analyseur possède ses diagnostics ; Taxo possède les frontières.**

## Constats de l'audit (2026-10-08, `main` à `19d7a76`)

| N° | Question | Constat vérifié | Décision |
| --- | --- | --- | --- |
| 1 | Où sont les frontières ? | Tuile : `neighborhood/domain/frontier.py` (sélection), `neighborhood/application/knowledge_frontier.py` (connaissance, contexte), assemblées dans `protocol/application/neighborhood_view.py`. Source : couverture `NOT_INTERPRETED` et son `diagnostic.sites[]`. | RÉUTILISER |
| 2 | Quels champs ? | Entrée de Tuile : `nature`, `scope`, `node`, `subject`, `reason`, `producer`, `causes`, `count`, `continuation`. Site : lignes, colonnes, `reason`, `method`, `receiver`, `receiver_type`, `external_supertypes`, `candidates`. Fait : `produced_by`, `snapshot`. | RÉUTILISER |
| 3 | Les 4 catégories sont-elles représentables ? | Non. `OUT_OF_SCOPE` (type de couverture « rien à lire », code d'erreur), `UNSUPPORTED` (statut d'évaluation) et `UNKNOWN` (décompte) existent déjà avec un autre sens. | AJOUTER un champ distinct |
| 4 | Versionnement ? | `producer_version` et `catalog_version` sur chaque fait ; règles nommées `…/1` dans les dérivations. Pas de version de classification. | RÉUTILISER la convention de règle nommée |
| 5 | Sites et occurrences ? | Un site est situé à l'octet près, hors identité du fait ; une couverture par propriétaire ; la Tuile réduit les sites à leurs raisons distinctes (`causes`). | ADAPTER : clé de site déterministe |
| 6 | Budget des frontières ? | Pas de `max_frontiers`. Bornes existantes : `max_bytes`, `MAX_LOCAL_REFERENCES`, `not_sent {what: local_coverage, count, reason: BUDGET}`, `sites_seen` contre `sites`. | RÉUTILISER |
| 7 | Diagnostic et catégorie distincts ? | Le code existe (`site.reason`), la catégorie non ; les codes Java sont fermés dans le schéma commun. | ADAPTER |

Correction de l'audit : les sites ne sont pas invisibles par le protocole. `find_facts` (`nature: COVERAGE`,
`subject`) et `get_coverage` rendent la couverture avec son `diagnostic`, sans ses preuves. Les sites sont
donc déjà « conservés et consultables séparément ». Ce récit réutilise ces opérations et n'en ajoute aucune.

## Décisions du 2026-10-08 (prises par le propriétaire du projet)

1. **Classification à la production, conservée dans chaque site.** L'historique est immuable. La règle est
   identifiable et versionnée.
2. **Codes de diagnostic ouverts par producteur ; quatre catégories fermées dans le contrat commun.** Ajouter
   Python ne demande pas d'ajouter ses codes au schéma commun.
3. **Décompte par catégorie dans la Tuile.** Les sites et leurs preuves restent consultables à part. Aucun site
   ne devient une frontière de Tuile. Le contrat `neighborhood/2` est préservé.
4. **`OUT_OF_SCOPE` sous condition.** La liste fermée JDK de TAXO-01L ne justifie `OUT_OF_SCOPE` que pour un type
   identifié avec certitude et explicitement exclu du périmètre d'analyse. L'appartenance à la liste ne suffit
   pas si le périmètre est inconnu : sinon `UNKNOWN`.

Exigences associées : réutiliser l'existant ; identité déterministe des sites, plusieurs sur une ligne
compris ; aucun `classified_at` ; aucune reclassification silencieuse ; aucune généralisation implicite à
toutes les bibliothèques ; aucun `max_frontiers` sans mesure ; aucune modification silencieuse de `neighborhood/2`.

## Comportement attendu

### 0. Responsabilités (normatives)

| Niveau | Responsabilité | Interdit |
| --- | --- | --- |
| Analyseur | Observer les sites, résoudre les cibles, produire diagnostics, preuves et catégories | Inventer une cible ; conclure sans preuve |
| Maille | Conserver faits, couvertures, sites individuels, provenance et règle de classification | Perdre un site dans une agrégation ; reclasser |
| Tuile | Présenter une portion bornée de la Maille | Faire passer une limite d'affichage pour une limite de connaissance |

Trois familles restent séparées et ne se convertissent jamais l'une en l'autre :

- **Couverture** (ce que l'analyse a lu) : `ANALYSED`, `NOT_INTERPRETED`, `READ_ERROR`… par zone.
  `NOT_INTERPRETED` reste un type de couverture : la zone est identifiée, son contenu n'a pas été interprété.
- **Catégorie de site** (pourquoi une continuation précise n'est pas établie) : les quatre valeurs du § 1.
  Elle n'existe que sur un site, à l'intérieur d'une couverture `NOT_INTERPRETED` qui porte un `diagnostic`.
- **Frontière de sélection et de contexte** (ce que la Tuile n'a pas montré) : `DEPTH`, `FANOUT`, budgets,
  `NOT_REACHED`, `NO_ANALYZER`. Jamais de catégorie.

Distinction testable entre `NOT_INTERPRETED` et `UNSUPPORTED` : `UNSUPPORTED` qualifie **un site localisé**
dont l'analyseur a reconnu la forme et a tenté la résolution, en connaissant la raison de son échec.
`NOT_INTERPRETED` qualifie **une zone** ; elle peut n'avoir aucun site (par exemple un fichier en erreur de
syntaxe, ou une annotation détectée que l'analyseur ne lit pas, comme `@PreAuthorize` pour un analyseur
d'appels). Une couverture `NOT_INTERPRETED` sans `diagnostic` n'a **aucune** catégorie et ne vaut jamais
évaluation : rien n'en est déduit, ni « autorisé », ni « sans appel ».

### 1. Quatre catégories fermées (contrat commun)

| Catégorie | Sens |
| --- | --- |
| `UNKNOWN` | La continuation ne peut pas être déterminée avec les connaissances disponibles. |
| `AMBIGUOUS` | Plusieurs continuations sont possibles, sans preuve suffisante pour en choisir une. |
| `UNSUPPORTED` | La construction est reconnue, mais son interprétation n'est pas prise en charge. |
| `OUT_OF_SCOPE` | La continuation est établie comme extérieure au périmètre analysé. |

- Nouveau champ de site : `category`, énumération fermée de ces quatre valeurs. Il ne réutilise ni
  `coverage_type`, ni le statut d'évaluation, ni `count.kind` : même nom, autre champ, autre sens.
- Aucune catégorie propre à un langage, un framework ou une bibliothèque. Un langage de plus n'ajoute aucune
  catégorie.
- Une catégorie ne produit jamais de fait : aucune assertion, aucun `CALLS`, aucun symbole externe.
- **`AMBIGUOUS` n'est jamais converti en relation.** Les `candidates` d'un site restent des candidats : aucun
  `CALLS`, même `INFERRED`, n'est créé vers un candidat, ni par le producteur, ni par la Tuile, ni par
  l'Explorer, ni par une projection. Un seul candidat reste un candidat (§ 14).

### 2. Codes ouverts par producteur

- Schéma commun : `site.reason` passe de l'énumération Java à un code stable de forme `^[A-Z][A-Z0-9_]*$`.
  Les analyses existantes restent valides, puisque chaque ancien code respecte cette forme.
- La fermeture passe au catalogue du producteur : `EvaluatorCatalog` gagne `diagnostic_codes`, un tuple trié.
  Le catalogue `java-calls` y déclare ses 11 codes actuels. La conformité refuse tout site dont le code n'est
  pas déclaré par le catalogue de son producteur. L'invariant « raison fermée » de § 14 est donc conservé, au
  bon endroit.
- Le code reste le diagnostic. La catégorie n'entre jamais dans le code : reclasser ne renomme rien.
- Identifiant logique d'un diagnostic : `produced_by.producer_id` plus `site.reason`. Aucun champ nouveau.

### 3. Classification à la production, versionnée par une règle nommée

- Le `diagnostic` gagne `classification` : l'identifiant de la règle utilisée, selon la convention des règles
  nommées (`java.calls.frontier-classification/1`). C'est le seul champ de version ajouté. La version du
  producteur reste dans `produced_by`. Aucun horodatage.
- Quand `classification` est présent, chaque site porte `category` (exigé par le schéma). Quand il est absent,
  c'est une analyse antérieure : aucun site n'a de catégorie, et rien n'en est déduit.
- L'adaptateur Java est une fonction pure, dans `app/evaluators/java_calls/classification.py`. Elle prend le
  code et les preuves du site, plus ce que l'exécution sait du périmètre (§ 5), et rend une catégorie. Une
  table déclarative donne le cas général ; une seule fonction traite le cas contextuel. Aucune logique Java
  n'entre dans le cœur, la Tuile ou l'Explorer.
- Changer la table, c'est passer à `…/2` et monter `producer_version`. Une analyse ancienne garde ses
  catégories et sa règle : elle n'est jamais relue ni reclassée.

Table `java.calls.frontier-classification/1` :

| Code | Catégorie |
| --- | --- |
| `RECEIVER_TYPE_UNKNOWN` | `UNKNOWN` |
| `RECEIVER_TYPE_AMBIGUOUS` | `AMBIGUOUS` |
| `OVERLOAD_AMBIGUOUS` | `AMBIGUOUS` |
| `NO_MATCHING_DECLARATION` | `UNKNOWN` |
| `TARGET_DECLARATION_OUTSIDE_SNAPSHOT` | `UNKNOWN` |
| `SUPER_TYPE_UNRESOLVED` | `UNKNOWN` (des candidats, un supertype externe non lu : la cible n'est pas déterminée) |
| `UNSUPPORTED_CALL_FORM` | `UNSUPPORTED` |
| `RECEIVER_KIND_DEFERRED` | `UNSUPPORTED` |
| `LAMBDA_OR_LOCAL_CONTEXT` | `UNSUPPORTED` |
| `PARSE_ERROR` | `UNKNOWN` |
| `TARGET_TYPE_OUTSIDE_SNAPSHOT` | `UNKNOWN`, sauf les conditions du § 5 réunies : `OUT_OF_SCOPE` |

### 4. Identité locale des sites

- Le producteur émet les sites d'une couverture triés par `(line_start, column_start, line_end, column_end,
  reason)`. Aujourd'hui l'ordre vient du parcours de l'arbre ; il devient explicite et testé.
- Clé d'un site, dans une analyse : identité de sa couverture (sujet, type, périmètre, producteur, comme
  `canonical_identity` aujourd'hui), puis `reason`, `line_start`, `column_start`, `line_end`, `column_end`, puis
  le **rang** du site parmi ceux qui ont exactement les mêmes valeurs (0, 1…). Deux sites sur une même ligne
  diffèrent par leurs colonnes. Deux constats identiques gardent chacun leur rang : ils ne sont jamais fusionnés.
- La clé est calculée par une fonction pure du domaine commun (`site_key`). Elle n'est pas persistée et
  n'entre pas dans l'identité du fait : le `diagnostic` reste hors identité, comme le dit § 14.
- C'est une **identité locale de diagnostic**, pas une identité de site dans le graphe. Elle sert à compter et
  à désigner un site dans un `diagnostic` donné. Deux constats identiques ne se distinguent que par leur rang ;
  ce rang ne porte aucun sens : aucun consommateur ne peut rattacher une information à « le site de rang 1 »
  au-delà de cette analyse.
- Entre deux révisions, la clé n'est **pas** stable (les lignes bougent). Ce récit ne compare pas les sites
  d'une révision à l'autre (limite écrite). TAXO-01E et TAXO-01F ne changent pas.
- Deux producteurs sur un même symbole donnent deux couvertures, deux entrées de Tuile (la clé de
  `local_frontier` contient déjà le producteur). Aucune fusion ni priorité entre producteurs.

### 5. `OUT_OF_SCOPE` : quand, et seulement quand

Un site `TARGET_TYPE_OUTSIDE_SNAPSHOT` est `OUT_OF_SCOPE` **si et seulement si** les quatre conditions sont
établies. Sinon, il est `UNKNOWN`.

1. **Type identifié avec certitude.** Le nom qualifié du type du receveur est établi par le lecteur : import
   simple explicite, ou `java.lang` implicite. Aucun type de même nom simple n'est déclaré dans les sources, et
   le fichier n'a aucun import « à la demande » (`.*`) hors `java.lang` qui pourrait le fournir.
2. **Type dans la liste fermée JDK de TAXO-01L**, telle que livrée par ce récit, sans extension implicite.
   Aucune autre bibliothèque. Aucun préfixe (`java.*`) ne vaut liste.
3. **Périmètre connu.** L'exécution a lu toutes les sources Java sélectionnées : aucune `READ_ERROR`, aucun
   fichier en erreur de syntaxe, statut `SUCCESS`. Si l'exécution est `PARTIAL`, le type pourrait être déclaré
   dans un fichier non lu : `UNKNOWN`. C'est une **règle conservatrice de première version**, pas une définition
   universelle d'`OUT_OF_SCOPE` : un seul fichier illisible sans rapport avec la cible fait basculer ces sites
   en `UNKNOWN`. Une preuve de complétude locale (pertinente pour la résolution de ce type seulement)
   demanderait des métadonnées que Taxo ne produit pas aujourd'hui ; elle relève d'un futur récit.
4. **Exclusion explicite.** Le périmètre d'analyse, c'est la couverture `ANALYSED` du dépôt par le producteur
   (`scope.include` et `scope.exclude`) : il ne contient que les sources de l'instantané. Aucune source de
   l'instantané ne déclare le paquet du type. Une source qui le déclarerait l'inclurait, et le site serait
   résolu ou resterait `UNKNOWN`.

`receiver_type` et la règle nommée sont une **trace** de classification, pas à eux seuls une preuve du
périmètre. Chaque condition doit pouvoir être retrouvée dans l'analyse elle-même :

| Condition | Où elle se retrouve |
| --- | --- |
| 1. Type certain | Nouveau champ de site `qualification`, seulement sur un site `OUT_OF_SCOPE` : `{"kind": "IMPORT", "line_start": n}` (ligne de l'import simple) ou `{"kind": "IMPLICIT"}` (paquet implicite du langage). À valider : c'est un champ ajouté, de forme générique. |
| 2. Type dans la liste | La règle `classification` (`…/1`) désigne une version figée de la liste. |
| 3. Périmètre connu | Statut d'évaluation et couvertures `READ_ERROR` de la même analyse, déjà conservés. |
| 4. Exclusion explicite | Couverture `ANALYSED` du dépôt (`scope`) et faits `CONTAINS` des sources de la même analyse. |

Aucun `CALLS`, aucun `TYPED_AS`, aucun symbole externe n'est créé.

Conséquence assumée : la liste de TAXO-01L ne vise que des supertypes (`Serializable`, `Cloneable`, `Record`).
Un receveur `java.lang.String` reste donc `UNKNOWN` tant qu'aucun récit n'élargit la liste avec décision. La
PR D mesure combien de sites deviennent réellement `OUT_OF_SCOPE`.

### 6. Tuile : décompte par catégorie, `neighborhood/2` préservé

- Une entrée `KNOWLEDGE`, `scope: NODE`, dont la couverture a une `classification` gagne un champ **facultatif
  et additif** : `categories`, une liste triée selon l'ordre fixe `UNKNOWN`, `AMBIGUOUS`, `UNSUPPORTED`,
  `OUT_OF_SCOPE`. Exemple : `[{"category": "UNKNOWN", "count": {"kind": "EXACT", "value": 3}}]`.
- Les décomptes réutilisent la qualification de TAXO-01J. Quand `sites` est complet
  (`len(sites) == sites_seen`), chaque décompte est `EXACT` et une catégorie à zéro n'est pas listée : son
  absence veut dire zéro. Quand `sites` est tronqué (`sites_seen > len(sites)`), un site omis peut appartenir à
  n'importe quelle catégorie : les **quatre** catégories sont alors listées, chacune en `AT_LEAST` avec le
  nombre de sites retenus, **zéro compris** (`{"kind": "AT_LEAST", "value": 0}`). Une catégorie non observée
  n'est jamais confondue avec un zéro exact. Un décompte n'est jamais inventé.
- Aucun champ existant ne change : `reason`, `causes`, `count`, `producer` restent tels quels. Une entrée sans
  `classification` (analyse ancienne) n'a pas de `categories` ; l'Explorer dit « non classé ».
- `neighborhood/1` est inchangé à l'octet (il ne rend pas de lacunes locales ; l'instantané doré le prouve).
- Ce champ additif est **déclaré**, pas silencieux : ARCHITECTURE § 9.3 et TAXO-01J § 8 sont amendés dans la
  même PR, et `describe` ne change pas de version de moteur (voir « Point à valider »).
- Les frontières de **sélection** (`DEPTH`, `FANOUT`, `NODES`, `EDGES`, `BYTES`, `WORK`, `NOT_REACHED`) et de
  **contexte** ne portent jamais de catégorie. Un cycle reste une revisite (`revisit: true`), jamais `UNKNOWN`.
  Un budget épuisé reste une coupure de sélection, jamais `UNSUPPORTED`.
- Budget : aucun `max_frontiers`. Les lacunes locales restent bornées par `max_bytes` et
  `MAX_LOCAL_REFERENCES`, et l'omission reste dite par `not_sent`. La PR D mesure le coût en octets ; un
  `max_frontiers` ne serait proposé, dans un autre récit, que si la mesure le justifie.
- Détail d'un site : `find_facts` (`nature: COVERAGE`, `subject`) ou `get_coverage`, qui rendent déjà le
  `diagnostic`, catégories comprises, bornés par `max_bytes`.

### 7. Explorateur

- Il affiche les catégories de façon générique : quatre libellés français dans `vocabulary.ts`, par exemple
  « cible inconnue », « plusieurs cibles possibles », « forme non prise en charge », « hors du périmètre
  analysé ». Les codes restent affichés en détail, comme aujourd'hui (`CAUSES`).
- Aucune logique de langage : il lit `categories` et ne déduit rien des codes.
- Appels, Chaîne et Explorer gardent les frontières pertinentes : elles sont lues dans la même Tuile.

## Invariants

- § 5.5 n'est pas assoupli ; une frontière ne crée aucun fait et aucune relation.
- `OBSERVED`, `INFERRED`, `NOT_INTERPRETED` gardent leur sens ; l'absence de preuve n'est jamais une preuve
  d'absence.
- Même instantané, mêmes entrées, même configuration, mêmes versions : mêmes codes, mêmes catégories, même ordre.
- Aucune reclassification d'une analyse existante ; aucune migration de données ne réécrit un `diagnostic`.
- Les invariants de TAXO-01K et de TAXO-01L (#99) sont conservés : aucune cible inventée, aucun symbole de la
  JDK, aucune logique Java hors du producteur.
- Aucune modification de MIP, de `CALLS`, de `DISPATCHES_TO`.

## Critères d'acceptation

1. Le schéma commun déclare `category` à quatre valeurs fermées, documentées dans ARCHITECTURE.
2. Les 11 codes Java sont déclarés dans le catalogue `java-calls`, plus dans le schéma commun ; aucun code
   historique n'est renommé ; une analyse existante reste valide sans migration.
3. Un code non déclaré par le catalogue de son producteur est refusé par la conformité.
4. Chaque site d'une nouvelle analyse porte `category`, et son `diagnostic` porte `classification`.
4 bis. Un site `AMBIGUOUS` ne donne jamais de `CALLS` vers un de ses candidats, à aucun niveau.
4 ter. Une couverture `NOT_INTERPRETED` sans `diagnostic` n'a aucune catégorie ; `NOT_INTERPRETED` reste un type
   de couverture et n'est jamais remplacé par une catégorie.
5. `TARGET_TYPE_OUTSIDE_SNAPSHOT` donne `UNKNOWN` dès qu'une des quatre conditions du § 5 manque, et
   `OUT_OF_SCOPE` seulement quand les quatre sont réunies.
6. Les appels entre modules internes restent résolus, sans frontière.
7. Aucun `CALLS`, `TYPED_AS` ou symbole externe n'est créé par la classification.
8. Deux sites sur une même ligne, ou deux constats identiques, ont des clés distinctes et comptent chacun.
9. Deux producteurs sur un même symbole donnent deux entrées de Tuile distinctes.
10. Les frontières de sélection et de contexte n'ont jamais de catégorie.
11. Les décomptes par catégorie sont `EXACT` ou `AT_LEAST` selon `sites_seen` ; un diagnostic tronqué liste
    les quatre catégories en `AT_LEAST`, zéro compris ; la troncature reste dite par
    `not_sent`.
12. Deux exécutions identiques rendent des diagnostics identiques à l'octet.
13. Les tests Java tournent sur le vrai analyseur et la fixture `java-calls-demo`.
14. Les tests Python utilisent un producteur synthétique, présenté comme tel, jamais comme une capacité Python.
15. `neighborhood/1` est identique à l'octet ; `neighborhood/2` ne change que par le champ additif documenté ;
    budgets et monotonie de TAXO-01J sont inchangés.
16. L'Explorer affiche les catégories sans Minia ni LLM.
17. MIP n'est pas modifié.
18. Aucun nouveau stockage : la catégorie vit dans le `diagnostic` déjà persisté.

## Découpage proposé

Chaque PR est testable seule.

- **PR A — Contrat.** Schéma (`category`, `reason` ouvert, `classification`), `diagnostic_codes` au catalogue
  et conformité, `site_key`, ARCHITECTURE § 9.3 et § 14, tests de contrat Java et Python synthétique. Aucun
  producteur ne change.
- **PR B — Classification Java.** `classification.py`, sites triés, écriture de `category` et
  `classification`, `producer_version` 1.1.0. `OUT_OF_SCOPE` n'est pas encore produit : la liste de TAXO-01L
  n'existe pas ; tout `TARGET_TYPE_OUTSIDE_SNAPSHOT` est `UNKNOWN`. Oracle `expected.json` étendu à la main.
- **PR C — Tuile et Explorer.** `categories` dans les entrées `KNOWLEDGE`/`NODE` de `neighborhood/2`, libellés,
  état « non classé », non-régression `neighborhood/1`.
- **PR D — `OUT_OF_SCOPE` et mesure** (après la liste de TAXO-01L). Conditions du § 5 et champ
  `qualification`, puis mesure sur `student-analysis-java`, `bibliotheque` et `spring-petclinic` : sites par
  catégorie, sites restés `UNKNOWN`, sites `OUT_OF_SCOPE` vérifiés un par un, faux positifs constatés sur les
  fixtures, octets ajoutés aux Tuiles. Le récit est clos ensuite.

## Plan de tests

Toutes les valeurs (heure, ordre, environnement) sont fixées ; aucun test n'utilise le réseau.

**Contrat (PR A)**
- Un site avec chacune des 4 catégories est valide ; `category: "EXTERNAL"` est refusé.
- `classification` présent et un site sans `category` : refusé. `classification` absent et sites sans
  catégorie : valide (analyse ancienne).
- Un ancien `diagnostic` réel (instantané pris dans `java-calls-demo` avant PR B) est valide sans changement.
- `reason` : `TARGET_TYPE_OUTSIDE_SNAPSHOT` valide ; `""`, `"bad code"`, `"x"` refusés par la forme.
- Conformité : un site `java-calls` au code non déclaré est refusé, avec un message qui nomme le code et le
  producteur.
- Python synthétique : un producteur de test `test.synthetic-python` déclare `NAME_UNBOUND` et
  `DYNAMIC_ATTRIBUTE` dans son catalogue. Ses couvertures sont valides **sans toucher au schéma commun**.
- `site_key` : deux sites sur une ligne (colonnes différentes) donnent deux clés ; deux sites identiques donnent
  les rangs 0 et 1 ; la clé ne dépend pas de l'ordre d'arrivée une fois les sites triés.
- Une couverture `NOT_INTERPRETED` sans `diagnostic` (fichier en erreur de syntaxe) est valide sans catégorie ;
  une catégorie hors d'un site est refusée.

**Classification Java, unitaires purs (PR B)**
- Une ligne de table par code : les 11 codes donnent la catégorie attendue.
- `TARGET_TYPE_OUTSIDE_SNAPSHOT` : `UNKNOWN` quand le nom n'est pas qualifié avec certitude, quand un homonyme
  est déclaré dans les sources, quand le fichier a un import `.*` hors `java.lang`, quand l'exécution est
  `PARTIAL`, quand le type n'est pas dans la liste. Un test par condition manquante.
- Déterminisme : 100 classifications du même site rendent la même catégorie ; la fonction ne lit ni l'heure
  ni l'environnement.
- `AMBIGUOUS` : un site `OVERLOAD_AMBIGUOUS` à deux candidats, et un site à un seul candidat, ne produisent
  aucun `CALLS` ; les candidats restent dans le `diagnostic`.

**Classification Java sur le vrai analyseur (PR B)**
- `java-calls-demo` : chaque site de l'oracle a sa catégorie écrite à la main avant l'exécution ; l'évaluateur
  la retrouve exactement.
- Fixture à deux modules : un appel d'un module vers une classe d'un autre module des sources est un `CALLS`,
  pas une frontière.
- Deux appels non résolus sur une même ligne donnent deux sites, triés par colonne.
- Deux exécutions donnent des `diagnostic` identiques à l'octet.
- Aucun fait nouveau : le nombre d'assertions est identique avant et après PR B sur la fixture.

**Non-régression (rouge sans correctif, vert avec)**
- Un site sans catégorie dans une nouvelle analyse (PR B) ; un champ `categories` absent d'une entrée classée
  (PR C) ; un ancien schéma qui refuse un code Python synthétique (PR A).

**Tuile (PR C, SQLite et PostgreSQL)**
- `neighborhood/1` : instantané doré `neighborhood_v1_golden.json` identique.
- `neighborhood/2` : une entrée `KNOWLEDGE`/`NODE` porte `categories` dans l'ordre fixe, décomptes `EXACT`.
  Avec `sites_seen > len(sites)` : les quatre catégories listées en `AT_LEAST`, y compris une catégorie à
  `value: 0` ; aucune n'est absente. Exemple vérifié : 10 sites vus, 6 retenus (3 `UNKNOWN`, 2 `AMBIGUOUS`,
  1 `UNSUPPORTED`) donnent 3, 2, 1 et 0 en `AT_LEAST`, jamais un `OUT_OF_SCOPE` absent lu comme zéro.
- Analyse ancienne : aucune entrée n'a `categories`, et le reste de la réponse est identique à aujourd'hui.
- Deux producteurs (`taxo.java-calls` et le producteur Python synthétique) sur un même symbole : deux entrées.
- `DEPTH`, `FANOUT`, `NOT_REACHED`, `NO_ANALYZER`, une revisite : aucune catégorie.
- `max_bytes` serré : les lacunes locales omises sont comptées dans `not_sent`, sans erreur.
- Propriétés de TAXO-01J (préfixe, monotonie) rejouées à graine fixe : inchangées.
- `find_facts` (`nature: COVERAGE`) rend le `diagnostic` avec ses catégories.
- Forme compacte (`neighborhood_form.py`) : `categories` est transmis tel quel.
- `max_bytes` serré avec des entrées classées : la réponse tient dans le budget, et l'omission est dite.
- Client strict : une réponse `neighborhood/2` d'avant le champ et une d'après sont toutes deux lues par
  l'Explorer actuel (types `Boundary`), sans erreur.

**Explorateur (PR C, Vitest)**
- Les quatre libellés sont affichés ; « non classé » pour une entrée sans catégories ; le code reste visible
  en détail ; aucune branche du code ne teste un nom de langage.

**Mesure (PR D)**
- Les trois dépôts : sites par catégorie, avant et après ; sites restés `UNKNOWN` ; sites `OUT_OF_SCOPE`
  justifiés un par un ; faux positifs constatés sur les fixtures ; octets ajoutés par Tuile. Résultats écrits
  dans ce récit.

**CI de chaque PR** : backend `pytest -q`, frontend `npm ci && npm test && npm run build`, avec les nombres
exacts dans la description de la PR.

## Limites

- La clé de site n'est stable qu'à l'intérieur d'une analyse ; aucun suivi d'un site d'une révision à l'autre.
- `OUT_OF_SCOPE` ne couvre que les types de la liste de TAXO-01L. La plupart des receveurs JDK
  (`String`, `List`…) restent `UNKNOWN`.
- Les tests Python sont synthétiques : ils prouvent que le vocabulaire des catégories et l'ouverture des codes
  sont génériques, pas que tout le diagnostic de site est indépendant du langage, ni une analyse de code Python.
- La condition de périmètre d'`OUT_OF_SCOPE` est globale (exécution `SUCCESS`) : règle conservatrice de
  première version.
- Les champs de site autres que `reason` et `category` (`receiver`, `receiver_type`…) gardent leur forme
  actuelle, pensée pour Java. Un producteur Python pourra les laisser vides. Les ouvrir relève d'un futur récit.

## Hors périmètre

Analyseur Python ; résolution des appels dynamiques ; lecture des bibliothèques ou des JAR ; extension de la
liste JDK ; `max_frontiers` ; comparaison des sites entre révisions ; refonte de la Maille ; sens de `CALLS` ;
`DISPATCHES_TO` ; MIP ; Minia ou LLM ; fusion entre producteurs ; nouvelle opération du protocole.

## Point à valider avant la PR C

`neighborhood/2` reçoit un champ **additif** (`categories`), annoncé dans ARCHITECTURE et TAXO-01J, sans
changer de nom de moteur. Recommandation : garder `neighborhood/2`, mais **seulement si** ces quatre invariants
sont vérifiés au début de la PR C, avant la décision définitive :

1. Les champs existants gardent exactement leur sens.
2. Les consommateurs existants acceptent la propriété ajoutée. Inventaire au 2026-10-08 dans le dépôt :
   l'Explorer (types TypeScript `Boundary`, sans validation fermée à l'exécution) et la forme compacte
   (`neighborhood_form.py`) ; aucun schéma JSON fermé des réponses ; aucun code de Minia du dépôt ne lit `frontier`. À
   revérifier dans la PR C. ARCHITECTURE précisera qu'un client de `neighborhood/2` ignore les propriétés
   inconnues.
3. Le budget `max_bytes` reste respecté avec les catégories.
4. Les anciennes analyses restent lisibles sans reclassification.

Si un consommateur à schéma fermé est trouvé, la PR C s'arrête et propose `neighborhood/3`.
