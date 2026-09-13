# TAXO-01A — Contrat machine du fait

Statut : À FAIRE  
Parent : EPIC TAXO-01 — Fondation de la mémoire logicielle vérifiable (`EPIC-TAXO-01-fondation-memoire-verifiable.md`)  
Références : ADR 0001, ADR 0002

## Récit

En tant que Taxo,  
je veux disposer d'un contrat machine unique et versionné pour représenter un fait,  
afin que tous les producteurs émettent des connaissances ayant la même signification et que les
projections futures puissent les consommer sans connaître leur technologie d'origine.

## Pourquoi ce récit existe

Aujourd'hui, Taxo conserve essentiellement des résultats libres produits par son scanner.

Cela suffit pour dire :

```text
Spring Boot détecté dans pom.xml
```

mais cela ne suffit pas pour construire la mémoire logicielle cible.

Demain, Taxo devra représenter des relations telles que :

```text
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
HANDLED_BY
symbol:java:...OAuthClientController#register
```

ou :

```text
route-pattern:/api/v1/**
AUTHORIZED_BY
symbol:java:...PolicyBasedAuthorizationManager
```

ou encore une limite d'analyse :

```text
symbol:java:...PolicyEvaluator
coverage_type: NOT_INTERPRETED
```

Ces informations pourront provenir d'évaluateurs, de projections ou de personnes, et d'outils écrits
dans des langages différents.

Leur seule frontière commune doit être le contrat du fait Taxo.

---

# Loi du récit

```text
Un producteur n'émet pas du JSON libre.

Il émet un fait Taxo valide
ou son résultat est refusé, avec la raison.
```

---

# Hors périmètre

Ce récit ne réalise pas :

- la persistance des faits ;
- les migrations de la base ;
- la **création** des instantanés Git (TAXO-01C) — la **référence** à un instantané, elle, fait partie du contrat ;
- la normalisation des références et du périmètre, et le calcul de l'identité stable (TAXO-01B) ;
- la réévaluation de la validité (TAXO-01H) ;
- l'analyse Java ou Spring ;
- l'Inventory Evaluator ;
- les projections, les diagrammes, Ask Taxo, MCP, le Knowledge Graph ;
- un LLM.

Il définit et valide uniquement **la forme et les règles d'un fait Taxo**.

---

# T1 — Version et forme machine du contrat

Créer une première version explicite du contrat :

```text
Taxo Fact Contract
version: 1
```

La version appartient au contrat lui-même. Une évolution incompatible crée une nouvelle version.

Le contrat est matérialisé par trois éléments, indépendants de toute technologie d'analyse :

- un **JSON Schema** versionné pour la structure ;
- un **validateur sémantique** pour les règles qui croisent plusieurs champs ;
- une **suite de conformité** : des fichiers d'exemples valides et invalides, avec pour chacun le
  résultat attendu (accepté, ou refusé avec la raison).

## Résultat attendu

Taxo identifie sans ambiguïté la version du contrat utilisée par un fait, et un futur analyseur JVM
peut rejouer la même suite de conformité sans dépendre du code Python.

---

# T2 — Implémenter les trois natures de faits

| Nature | Structure | Preuve | Statut |
| --- | --- | --- | --- |
| `ASSERTION` | `subject`, `relation`, `object`, `qualifiers` | obligatoire si `OBSERVED` | `OBSERVED`, `INFERRED`, `HUMAN_VALIDATED` |
| `ABSENCE` | `pattern`, `scope`, `method` | **interdite** | `OBSERVED` uniquement |
| `COVERAGE` | `subject`, `coverage_type`, `scope` | facultative | `OBSERVED` uniquement |

### ASSERTION

Exprime une relation entre un sujet et un objet. C'est la seule nature qui porte une relation.

### ABSENCE

Exprime qu'un motif n'a pas été trouvé dans un périmètre donné, par une méthode donnée.

Une absence **n'a pas de preuve** : c'est sa définition.

### COVERAGE

Décrit ce qu'une exécution a analysé, reconnu, ou n'a pas su interpréter.

Types de couverture v1 :

```text
ANALYSED
RECOGNIZED
NOT_INTERPRETED
OUT_OF_SCOPE
READ_ERROR
```

## Résultat attendu

Une absence et une limitation d'analyse ne peuvent plus être confondues avec une assertion classique.

---

# T3 — Statuts de connaissance et producteurs autorisés

Le contrat doit supporter :

```text
OBSERVED          produit uniquement par un évaluateur
INFERRED          produit par un évaluateur ou par une projection
HUMAN_VALIDATED   produit uniquement par une personne
```

### OBSERVED

Extrait mécaniquement d'une source, par une règle de détection nommée.

### INFERRED

Construit depuis un ou plusieurs autres faits, par une règle de dérivation nommée.

### HUMAN_VALIDATED

Confirmé ou fourni explicitement par une personne identifiée.

## Règle

Le statut fait partie de la signification de l'occurrence.

Une projection ne doit jamais pouvoir traiter silencieusement un `INFERRED` comme un `OBSERVED`.

---

# T4 — Implémenter la validité

Le contrat supporte :

```text
VALID
STALE
REVALIDATION_REQUIRED
```

### VALID

Le fait peut être utilisé dans son contexte actuel.

### STALE

Une connaissance dérivée dépend d'informations qui ne sont plus valables.

### REVALIDATION_REQUIRED

Une connaissance humaine était ancrée sur du code qui a changé.

## Règle

La validité est **décidée par la mémoire**, pas par le producteur.

Un producteur ne soumet que des faits `VALID`. Les états `STALE` et `REVALIDATION_REQUIRED` sont
représentables, mais seule la mémoire les pose (TAXO-01H).

## Résultat attendu

La validité est distincte du statut.

```text
Status   : HUMAN_VALIDATED
Validity : REVALIDATION_REQUIRED
```

est un état valide du modèle, mais pas un fait qu'un producteur peut soumettre.

---

# T5 — Séparer identité et occurrence

La structure du fait distingue :

**L'identité** — ce que le fait affirme, stable d'un commit à l'autre :

| Nature | Champs d'identité |
| --- | --- |
| `ASSERTION` | nature, sujet, relation, objet, qualificatifs |
| `ABSENCE` | nature, motif, méthode, périmètre |
| `COVERAGE` | nature, sujet, type de couverture, périmètre, identifiant du producteur |

« `PolicyEvaluator` non interprété dans le module A » et « `PolicyEvaluator` non interprété dans tout
le dépôt » sont deux couvertures distinctes.

**L'occurrence** — où et comment le fait a été établi : statut, validité, instantané, preuves,
dérivation ou validation, producteur.

Le calcul effectif de l'identité appartient à TAXO-01B. Ce récit fixe seulement la séparation, pour
que 01B n'ait pas à remodeler le contrat.

---

# T6 — Références d'entités : syntaxe et types v1

Un sujet ou un objet est une référence `type:clé`.

La liste des types v1 est **fermée** :

```text
repository   module   directory   file   symbol   endpoint   route-pattern
technology   language   annotation   role   permission   policy-rule
```

Exemple d'assertion :

```text
subject:
endpoint:POST /api/v1/spaces

relation:
HANDLED_BY

object:
symbol:java:com.example.SpaceController#create

qualifiers:
{}
```

- `object` peut être absent lorsque la relation le permet explicitement (`PERMITS_ALL`).
- Une valeur littérale n'est admise que dans `object` lorsque la relation le prévoit, ou dans `qualifiers`.
- `directory` désigne un sous-arbre : chemin relatif, séparateurs `/`, sans `/` final.
- La normalisation et la stabilité des clés relèvent de TAXO-01B.

---

# T7 — Référence d'instantané

Chaque fait référence son instantané :

```text
repository
commit
mode                  COMMIT | WORKING_TREE
content_fingerprint   obligatoire en WORKING_TREE
```

Créer un instantané relève de TAXO-01C. Le référencer fait partie du contrat : sans cette référence,
la règle « la preuve appartient au même instantané » ne peut pas être vérifiée.

---

# T8 — Périmètre structuré

`scope` est une structure, jamais une phrase libre :

```text
scope:
  include[]   au moins une référence
  exclude[]   facultatif
```

Types admis : `repository`, `module`, `directory`, `file`.

| Périmètre | Représentation |
| --- | --- |
| tout le dépôt | `include: [repository:takibo-iam]` |
| un module | `include: [module:takibo-security-management]` |
| un ensemble de fichiers | `include: [file:a/B.java, file:a/C.java]` |
| un sous-arbre | `include: [directory:takibo-security-management/src/main/java]` |
| une exclusion | `exclude: [directory:takibo-security-management/src/test]` |

- Le périmètre dit **où**. Le **comment** est porté par la méthode (`ABSENCE`) ou par le catalogue du
  producteur (`COVERAGE`) : « catalogue Security v1 » n'est jamais un périmètre.
- Le commit n'en fait pas partie : il appartient à l'instantané.
- Le périmètre entre dans l'identité d'une `ABSENCE` et d'une `COVERAGE` (T5).

---

# T9 — Provenance : producteur générique

Chaque fait contient :

```text
produced_by:
  producer_type      EVALUATOR | PROJECTION | HUMAN
  producer_id
  producer_version   obligatoire pour EVALUATOR et PROJECTION ; absent pour HUMAN
  execution_id       obligatoire pour EVALUATOR et PROJECTION ; absent pour HUMAN
  catalog_id         obligatoire pour EVALUATOR ; absent sinon
  catalog_version    obligatoire pour EVALUATOR ; absent sinon
```

Matrice appliquée par le validateur :

| Producteur | `ASSERTION` | `ABSENCE` | `COVERAGE` |
| --- | --- | --- | --- |
| `EVALUATOR` | `OBSERVED`, `INFERRED` | `OBSERVED` | `OBSERVED` |
| `PROJECTION` | `INFERRED` | interdit | interdit |
| `HUMAN` | `HUMAN_VALIDATED` | interdit | interdit |

Exemples :

```text
producer_type:     EVALUATOR
producer_id:       spring-security
producer_version:  1.2.0
execution_id:      <exécution>
catalog_id:        spring-security-rules
catalog_version:   1
```

```text
producer_type:     PROJECTION
producer_id:       projection-pr
producer_version:  1.0.0
execution_id:      <exécution>
```

```text
producer_type:     HUMAN
producer_id:       <identifiant de la personne>
```

L'horodatage d'analyse appartient à l'exécution référencée par `execution_id`. Pour une personne, la
date est portée par la validation (T14).

## Pourquoi

- **Une projection ou une personne n'est jamais enregistrée comme évaluateur.** Ask Taxo, le bot de
  PR ou un architecte qui valide une règle doivent apparaître pour ce qu'ils sont.
- Deux analyses du même commit peuvent produire des résultats différents parce que le producteur a
  évolué. Taxo doit pouvoir distinguer « le logiciel a changé » de « Taxo analyse mieux le même
  logiciel ».

---

# T10 — Définir la preuve

Une `ASSERTION` `OBSERVED` contient au moins une preuve. Une `COVERAGE` peut en contenir. Une
`ABSENCE` n'en contient jamais.

```text
repository
commit
path
line_start
line_end
symbol
method
content_hash
```

- `repository` et `commit` sont ceux de l'instantané du fait.
- `path` est relatif à la racine du dépôt, avec des séparateurs `/`.
- Les lignes et le symbole sont facultatifs lorsque la source ne les permet pas.
- `method` est obligatoire. Exemple : `java.spring.request-mapping`.

## Calcul de `content_hash`

1. prendre les lignes citées (le fichier entier si aucune ligne n'est citée) ;
2. décoder en UTF-8 ;
3. retirer tout caractère `\r` ;
4. joindre les lignes par `\n`, sans `\n` final ;
5. appliquer SHA-256 et écrire `sha256:` suivi de l'empreinte en hexadécimal minuscule.

## Pourquoi la normalisation est obligatoire

Vérifié sur TAKIBO le 2026-09-13 : `OAuthClientController.java` contient 0 octet CR dans le commit
`80eb595` et 89 dans le dossier de travail Windows (`core.autocrlf=true`). Empreinte brute du fichier
sur disque : `d64ce8df…` ; même fichier sans les CR : `ce768de4…`, identique au contenu du commit.

Sans normalisation, le même code aurait deux empreintes, et Taxo annoncerait de fausses modifications.

## Règles

- La preuve ne stocke jamais de texte source brut : seulement chemin, lignes, symbole, méthode et
  empreinte.
- Le contrat ne comporte aucun champ destiné à conserver un extrait brut de code source. Les
  producteurs restent responsables de ne jamais émettre de secret ou de valeur sensible, y compris
  dans les champs textuels (qualificatifs, valeur d'un motif, énoncé d'une validation, valeurs
  littérales).

---

# T11 — Définir les règles d'ABSENCE

Un fait `ABSENCE` contient obligatoirement :

```text
pattern   type et valeur du motif cherché
scope     périmètre structuré (T8)
method    méthode de recherche
```

Il ne contient ni relation ni preuve. Il est toujours `OBSERVED` et produit par un évaluateur.

Exemple :

```text
Kind:     ABSENCE
Status:   OBSERVED

Pattern:
  type:   literal
  value:  "P_SPACE_USER_CREATE"

Scope:
  include: [repository:takibo-iam]

Method:   java.string-literal-search
```

## Interdit

```text
P_SPACE_USER_CREATE n'existe pas.
```

Une absence Taxo signifie uniquement :

> le mécanisme déclaré n'a pas trouvé le motif dans le périmètre déclaré.

---

# T12 — Définir les règles de COVERAGE

Un fait `COVERAGE` contient obligatoirement :

```text
subject
coverage_type
scope       périmètre structuré (T8)
```

Il peut contenir une preuve (par exemple, le fichier non interprété). Il est toujours `OBSERVED` et
produit par un évaluateur.

Exemple :

```text
Kind:           COVERAGE
Status:         OBSERVED
Subject:        symbol:java:...PolicyEvaluator
Coverage type:  NOT_INTERPRETED
Scope:
  include: [module:takibo-security-management]
Produced by:    EVALUATOR spring-security, catalogue spring-security-rules v1
```

---

# T13 — Définir les règles d'INFERRED

Un fait `INFERRED` contient :

```text
premises
derivation_rule
counter_examples_checked
known_gaps
```

Au moins une prémisse et une règle sont obligatoires. Le producteur est un évaluateur ou une
projection.

Exemple : pourquoi cet endpoint est-il protégé ?

```text
F1  OBSERVED   endpoint:X  HANDLED_BY     symbol:...OAuthClientController#register
F2  OBSERVED   route-pattern:/api/v1/**   AUTHORIZED_BY   symbol:...PolicyBasedAuthorizationManager

F3  INFERRED   endpoint:X  MATCHED_BY     route-pattern:/api/v1/**
    Premises:  F1, F2
    Rule:      spring-security.first-matching-pattern

F4  INFERRED   endpoint:X  PROTECTED_BY   symbol:...PolicyBasedAuthorizationManager
    Premises:  F2, F3
    Rule:      spring-security.route-authorization-applies
    Known gaps: PolicyEvaluator internal rules not interpreted
```

`PROTECTED_BY` ne se déduit jamais directement de `HANDLED_BY` : `HANDLED_BY` ne prouve pas que
`/api/v1/**` couvre l'endpoint. C'est le rôle de `MATCHED_BY`.

## Interdit

Aucun pourcentage de confiance. Tout champ de confiance est refusé.

---

# T14 — Définir HUMAN_VALIDATED

Une connaissance validée par une personne a pour producteur `HUMAN` et contient au minimum :

```text
validation:
  validated_at
  statement
  anchors
```

La personne est identifiée par `produced_by.producer_id` (T9).

Chaque ancrage désigne un symbole et son `content_hash`, calculé selon T10, pour détecter
ultérieurement que le code concerné a changé.

Exemple :

```text
Anchor:
symbol:java:...PolicyEvaluator#denyOAuthClientSurface

content_hash:
sha256:<empreinte des lignes de la méthode>
```

---

# T15 — Vocabulaire versionné

Le contrat utilise le vocabulaire v1 de l'ADR 0002 :

```text
CONTAINS
WRITTEN_IN
USES_TECHNOLOGY
DECLARED_BY

ANNOTATED_WITH
CALLS
IMPLEMENTS
DISPATCHES_TO

HANDLED_BY
ACCEPTS
RETURNS

PERMITS_ALL
AUTHORIZED_BY
MATCHED_BY
PROTECTED_BY
```

Une relation inconnue est refusée par défaut.

Ajouter une relation au vocabulaire est une évolution explicite.

`NOT_INTERPRETED` n'est pas une relation : c'est un type de couverture (T2).

---

# T16 — Implémenter les règles de cohérence

Le validateur doit refuser, avec la raison :

| # | Cas | Raison attendue |
| --- | --- | --- |
| 1 | `ASSERTION` `OBSERVED` sans preuve | une assertion observée exige une preuve |
| 2 | `ABSENCE` avec une preuve ou une relation | une absence n'a ni preuve ni relation |
| 3 | preuve d'un autre dépôt ou d'un autre commit que l'instantané | preuve hors instantané |
| 4 | `INFERRED` sans prémisse ou sans règle | INFERRED exige une dérivation |
| 5 | `HUMAN_VALIDATED` sans validation complète ou sans ancrage | validation incomplète |
| 6 | `ABSENCE` sans motif, périmètre ou méthode | absence non bornée |
| 7 | `COVERAGE` sans périmètre, sans type de couverture, ou avec un type inconnu | couverture invalide |
| 8 | `ABSENCE` ou `COVERAGE` avec un statut autre que `OBSERVED` | statut interdit pour cette nature |
| 9 | statut incompatible avec le producteur (`PROJECTION` `OBSERVED`, `HUMAN` hors `HUMAN_VALIDATED`, `EVALUATOR` `HUMAN_VALIDATED`, `ABSENCE` ou `COVERAGE` hors `EVALUATOR`) | producteur non autorisé pour ce statut |
| 10 | `EVALUATOR` sans catalogue ; `EVALUATOR` ou `PROJECTION` sans version ou sans exécution ; `HUMAN` avec catalogue, version ou exécution | provenance incohérente |
| 11 | périmètre sans inclusion, ou type de référence non admis dans un périmètre | périmètre invalide |
| 12 | `ASSERTION` sans relation, ou relation hors vocabulaire | relation invalide |
| 13 | référence mal formée, ou type d'entité hors liste | référence invalide |
| 14 | nature, statut, validité ou type de producteur inconnus | valeur inconnue |
| 15 | validité différente de `VALID` à la soumission | validité réservée à la mémoire |
| 16 | champ inconnu, dont tout champ de confiance | champ non prévu par le contrat |
| 17 | instantané `WORKING_TREE` sans empreinte de contenu | instantané non identifiable |
| 18 | `content_hash` au mauvais format | empreinte invalide |

---

# T17 — Tests positifs

Créer, sous forme de fichiers de la suite de conformité, des exemples valides pour au minimum :

### ASSERTION / OBSERVED / EVALUATOR

```text
repository:taxo
USES_TECHNOLOGY
technology:FastAPI
```

### ASSERTION / INFERRED / EVALUATOR

```text
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
MATCHED_BY
route-pattern:/api/v1/**
```

### ASSERTION / INFERRED / PROJECTION

```text
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
PROTECTED_BY
symbol:java:...PolicyBasedAuthorizationManager
```

### ASSERTION / HUMAN_VALIDATED / HUMAN

```text
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
PROTECTED_BY
policy-rule:POL_OAUTH_CLIENT_ADMIN_REQUIRED
```

### ABSENCE

```text
pattern: literal "P_SPACE_USER_CREATE"
scope:   include [repository:takibo-iam]
method:  java.string-literal-search
```

### COVERAGE, avec et sans preuve

```text
symbol:java:...PolicyEvaluator
coverage_type: NOT_INTERPRETED
scope: include [module:takibo-security-management]
```

### Périmètres

Tout le dépôt, un module, un ensemble de fichiers, un sous-arbre, et une inclusion avec exclusion.

### Empreinte

Un même extrait lu avec des fins de ligne LF et CRLF produit le même `content_hash`.

Tous doivent être acceptés.

---

# T18 — Tests négatifs

Un fichier de la suite de conformité par cas de T16, avec la raison de refus attendue.

---

# T19 — Exemple canonique TAKIBO

Ajouter une fixture de contrat avec les valeurs réelles, vérifiées le 2026-09-13 :

```text
Kind:      ASSERTION
Status:    OBSERVED
Validity:  VALID

Subject:   endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
Relation:  HANDLED_BY
Object:    symbol:java:com.takibo.managementservice.interfaces.rest.api.OAuthClientController#register

Snapshot:
  repository:  takibo-iam
  commit:      80eb595f6d03eea67eb86eae4c7640f94bd3f94c
  mode:        COMMIT

Evidence 1:
  path:          takibo-management-service/src/main/java/com/takibo/managementservice/interfaces/rest/api/OAuthClientController.java
  lines:         26-26    @RequestMapping("/api/v1/orgs/{orgId}/spaces/{spaceId}/clients")
  method:        java.spring.request-mapping
  content_hash:  sha256:09ccb00cbc0c7ee30ae55351c08e700b9f2c64d4516c99121b8088f3a81e2144

Evidence 2:
  path:          (même fichier)
  lines:         34-35    @PostMapping / public ResponseEntity<...> register(
  method:        java.spring.request-mapping
  content_hash:  sha256:554a3321bd5d9cdc6a59094935ac3d2e3d531ad045904cf06f53c565bb3b4a37

Produced by:
  producer_type:     EVALUATOR
  producer_id:       spring-api
  producer_version:  1.0.0
  execution_id:      <fixture>
  catalog_id:        spring-api-rules
  catalog_version:   1
```

Les empreintes ont été calculées depuis le contenu Git du commit, selon la règle de T10. Les extraits
de ligne ci-dessus servent à la lecture de ce récit : ils ne font pas partie du fait.

Cette fixture ne constitue pas une analyse réelle effectuée par Taxo.

---

# Critères d'acceptation

1. Il existe une version machine du contrat : JSON Schema, validateur sémantique et suite de conformité.
2. `ASSERTION`, `ABSENCE` et `COVERAGE` sont représentables, chacune avec sa structure propre et sa règle de preuve.
3. `OBSERVED`, `INFERRED` et `HUMAN_VALIDATED` sont représentables, chacun avec ses producteurs autorisés.
4. `VALID`, `STALE` et `REVALIDATION_REQUIRED` sont représentables ; un fait soumis est `VALID`.
5. Identité et occurrence sont séparées ; le périmètre et le producteur entrent dans l'identité d'une `COVERAGE`.
6. Les références suivent la syntaxe `type:clé` et la liste fermée des types v1.
7. Chaque fait référence son instantané ; toute preuve appartient à cet instantané.
8. Le périmètre est structuré (`include`, `exclude`) et représente dépôt, module, fichiers, sous-arbre et exclusions.
9. La provenance suit `produced_by` ; une projection ou une personne n'est jamais enregistrée comme évaluateur.
10. `content_hash` suit l'algorithme de T10 ; LF et CRLF donnent la même empreinte.
11. Les 18 cas de T16 sont refusés, chacun avec sa raison.
12. Le vocabulaire des relations est versionné ; une relation inconnue est refusée.
13. Tout champ inconnu est refusé ; aucun score de confiance n'est requis, généré ni accepté.
14. Aucun champ n'est destiné à conserver un extrait brut de code source ; la preuve n'en stocke jamais.
15. La fixture TAKIBO de T19 est acceptée.
16. La suite de conformité ne dépend d'aucune technologie d'analyse particulière.
17. Aucun LLM n'est utilisé.
18. Tous les tests sont verts.

---

# Définition de terminé

À la fin de TAXO-01A, n'importe quel futur producteur peut dire :

```text
Voici un fait Taxo.
```

et Taxo répond mécaniquement :

```text
VALIDE
```

ou :

```text
REFUSÉ
raison : une assertion observée exige une preuve
```

Sans connaître :

- Java ;
- Spring ;
- React ;
- Python ;
- le framework analysé ;
- le futur stockage de la mémoire ;
- la projection qui consommera ce fait.

---

# Ce que ce récit débloque

```text
TAXO-01A  Contrat machine du fait
       ↓
TAXO-01B  Références stables et identité
       ↓
TAXO-01D  Exécution d'évaluateur et couverture  ←  TAXO-01C  Instantané au commit (en parallèle)
          premier producteur de faits réels : scanner.py converti en Inventory v0
       ↓
TAXO-01E  Persistance
       ↓
TAXO-01F  Comparaison et banc Git
       ↓
TAXO-01G  API de lecture et vue de vérification
       ↓
TAXO-02 à 05  Inventory, Java Analyzer, Spring API, Spring Security
       ↓
TAXO-PROJ-PR-01   Projection PR              démo technique
       ↓
TAXO-PROJ-API-01  Projection Diagramme API
       ↓
TAXO-ASK-01       Ask Taxo minimal           démo produit
```

Ask Taxo ne sera fiable que parce que les faits qu'il consomme auront franchi cette frontière.
