# TAXO-01A — Contrat machine du fait

Statut : À FAIRE  
Parent : EPIC TAXO-01 — Fondation de la mémoire logicielle vérifiable (`EPIC-TAXO-01-fondation-memoire-verifiable.md`)  
Références : ADR 0001, ADR 0002 (amendé le 2026-09-13)

## Récit

En tant que Taxo,  
je veux disposer d'un contrat machine unique et versionné pour représenter un fait,  
afin que tous les évaluateurs produisent des connaissances ayant la même signification et que les
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

Ces informations pourront provenir d'évaluateurs différents, écrits dans des langages différents.

Leur seule frontière commune doit être le contrat du fait Taxo.

---

# Loi du récit

```text
Un évaluateur ne produit pas du JSON libre.

Il produit un fait Taxo valide
ou son résultat est refusé, avec la raison.
```

---

# Hors périmètre

Ce récit ne réalise pas :

- la persistance des faits ;
- les migrations de la base ;
- la **création** des instantanés Git (TAXO-01C) — la **référence** à un instantané, elle, fait partie du contrat ;
- la normalisation des références et le calcul de l'identité stable (TAXO-01B) ;
- la réévaluation de la validité (TAXO-01H) ;
- l'analyse Java ou Spring ;
- l'Inventory Evaluator ;
- les diagrammes, Ask Taxo, MCP, le Knowledge Graph ;
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

Chaque nature a sa propre structure :

| Nature | Structure | Statuts possibles |
| --- | --- | --- |
| `ASSERTION` | `subject`, `relation`, `object`, `qualifiers` | `OBSERVED`, `INFERRED`, `HUMAN_VALIDATED` |
| `ABSENCE` | `pattern`, `scope`, `method` | `OBSERVED` uniquement |
| `COVERAGE` | `subject`, `coverage_type`, `scope` | `OBSERVED` uniquement |

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

# T3 — Implémenter les statuts de connaissance

Le contrat doit supporter :

```text
OBSERVED
INFERRED
HUMAN_VALIDATED
```

### OBSERVED

Produit mécaniquement depuis une source, par une règle de détection nommée.

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

Un évaluateur ne soumet que des faits `VALID`. Les états `STALE` et `REVALIDATION_REQUIRED` sont
représentables, mais seule la mémoire les pose (TAXO-01H).

## Résultat attendu

La validité est distincte du statut.

```text
Status   : HUMAN_VALIDATED
Validity : REVALIDATION_REQUIRED
```

est un état valide du modèle, mais pas un fait qu'un évaluateur peut soumettre.

---

# T5 — Séparer identité et occurrence

La structure du fait distingue :

**L'identité** — ce que le fait affirme, stable d'un commit à l'autre :

| Nature | Champs d'identité |
| --- | --- |
| `ASSERTION` | nature, sujet, relation, objet, qualificatifs |
| `ABSENCE` | nature, motif, méthode, périmètre (hors commit) |
| `COVERAGE` | nature, sujet, type de couverture, identifiant de l'évaluateur |

**L'occurrence** — où et comment le fait a été établi : statut, validité, instantané, preuves,
dérivation ou validation, producteur.

Le calcul effectif de l'identité appartient à TAXO-01B. Ce récit fixe seulement la séparation, pour
que 01B n'ait pas à remodeler le contrat.

---

# T6 — Références d'entités : syntaxe et types v1

Un sujet ou un objet est une référence `type:clé`.

La liste des types v1 est **fermée** :

```text
repository   module   file   symbol   endpoint   route-pattern
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

# T8 — Définir la provenance du producteur

Chaque fait doit contenir :

```text
evaluator_id
evaluator_version
catalog_id
catalog_version
execution_id
```

Exemple :

```text
evaluator_id:       spring-security
evaluator_version:  1.2.0
catalog_id:         spring-security-rules
catalog_version:    1
```

L'horodatage d'analyse appartient à l'exécution référencée par `execution_id`, pas au fait : un même
commit peut être analysé plusieurs fois.

## Pourquoi

Deux analyses du même commit peuvent produire des résultats différents parce que l'évaluateur a évolué.

Taxo doit pouvoir distinguer :

```text
le logiciel a changé
```

de :

```text
Taxo analyse mieux le même logiciel
```

---

# T9 — Définir la preuve

Une `ASSERTION` `OBSERVED` doit contenir au moins une preuve.

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

## Règle

Aucun champ du contrat ne peut contenir de texte source. C'est la garantie structurelle qu'aucune
valeur sensible n'est copiée dans un fait : il n'existe pas d'emplacement pour elle.

---

# T10 — Définir les règles d'ABSENCE

Un fait `ABSENCE` contient obligatoirement :

```text
pattern   type et valeur du motif cherché
scope     périmètre de la recherche
method    méthode de recherche
```

Il ne contient ni relation ni preuve.

Exemple :

```text
Kind:     ABSENCE
Status:   OBSERVED

Pattern:
  type:   literal
  value:  "P_SPACE_USER_CREATE"

Scope:    tracked files at commit <commit>
Method:   literal-string-search
```

## Interdit

```text
P_SPACE_USER_CREATE n'existe pas.
```

Une absence Taxo signifie uniquement :

> le mécanisme déclaré n'a pas trouvé le motif dans le périmètre déclaré.

---

# T11 — Définir les règles de COVERAGE

Un fait `COVERAGE` contient obligatoirement :

```text
subject
coverage_type
scope
```

Il peut contenir une preuve (par exemple, le fichier non interprété).

Exemple :

```text
Kind:           COVERAGE
Status:         OBSERVED
Subject:        symbol:java:...PolicyEvaluator
Coverage type:  NOT_INTERPRETED
Scope:          catalogue spring-security-rules v1
```

---

# T12 — Définir les règles d'INFERRED

Un fait `INFERRED` contient :

```text
premises
derivation_rule
counter_examples_checked
known_gaps
```

Au moins une prémisse et une règle sont obligatoires.

Exemple :

```text
Conclusion:
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
PROTECTED_BY
symbol:java:...PolicyBasedAuthorizationManager

Premises:
F-101
F-105

Rule:
security.route-covers-endpoint

Known gaps:
PolicyEvaluator internal rules not interpreted
```

## Interdit

Aucun pourcentage de confiance. Tout champ de confiance est refusé.

---

# T13 — Définir HUMAN_VALIDATED

Une connaissance validée par une personne contient au minimum :

```text
validated_by
validated_at
statement
anchors
```

Chaque ancrage désigne un symbole et son `content_hash`, calculé selon T9, pour détecter
ultérieurement que le code concerné a changé.

Exemple :

```text
Anchor:
symbol:java:...PolicyEvaluator#denyOAuthClientSurface

content_hash:
sha256:<empreinte des lignes de la méthode>
```

---

# T14 — Vocabulaire versionné

Le contrat utilise le vocabulaire v1 de l'ADR 0002 :

```text
CONTAINS
WRITTEN_IN
USES_TECHNOLOGY
DECLARED_BY

HANDLED_BY
ACCEPTS
RETURNS

MATCHED_BY
PERMITS_ALL
AUTHORIZED_BY
ANNOTATED_WITH
CALLS
IMPLEMENTS
DISPATCHES_TO
PROTECTED_BY
```

Une relation inconnue est refusée par défaut.

Ajouter une relation au vocabulaire est une évolution explicite.

`NOT_INTERPRETED` n'est pas une relation : c'est un type de couverture (T2).

---

# T15 — Implémenter les règles de cohérence

Le validateur doit refuser, avec la raison :

| # | Cas | Raison attendue |
| --- | --- | --- |
| 1 | `ASSERTION` `OBSERVED` sans preuve | OBSERVED exige une preuve |
| 2 | preuve d'un autre dépôt ou d'un autre commit que l'instantané | preuve hors instantané |
| 3 | `INFERRED` sans prémisse ou sans règle | INFERRED exige une dérivation |
| 4 | `HUMAN_VALIDATED` sans validation complète ou sans ancrage | validation incomplète |
| 5 | `ABSENCE` sans motif, périmètre ou méthode | absence non bornée |
| 6 | `ABSENCE` ou `COVERAGE` avec un statut autre que `OBSERVED` | statut interdit pour cette nature |
| 7 | `ASSERTION` sans relation, ou relation hors vocabulaire | relation invalide |
| 8 | `COVERAGE` sans type de couverture, ou type inconnu | couverture invalide |
| 9 | référence mal formée, ou type d'entité hors liste | référence invalide |
| 10 | nature, statut ou validité inconnus | valeur inconnue |
| 11 | validité différente de `VALID` à la soumission | validité réservée à la mémoire |
| 12 | champ inconnu, dont tout champ de confiance | champ non prévu par le contrat |
| 13 | instantané `WORKING_TREE` sans empreinte de contenu | instantané non identifiable |
| 14 | `content_hash` au mauvais format | empreinte invalide |

---

# T16 — Tests positifs

Créer, sous forme de fichiers de la suite de conformité, des exemples valides pour au minimum :

### ASSERTION / OBSERVED

```text
repository:taxo
USES_TECHNOLOGY
technology:FastAPI
```

### ASSERTION / INFERRED

```text
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
PROTECTED_BY
symbol:java:...PolicyBasedAuthorizationManager
```

### ASSERTION / HUMAN_VALIDATED

```text
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
PROTECTED_BY
policy-rule:POL_OAUTH_CLIENT_ADMIN_REQUIRED
```

### ABSENCE

```text
pattern: literal "P_SPACE_USER_CREATE"
scope:   tracked files at commit
method:  literal-string-search
```

### COVERAGE

```text
symbol:java:...PolicyEvaluator
coverage_type: NOT_INTERPRETED
```

### Empreinte

Un même extrait lu avec des fins de ligne LF et CRLF produit le même `content_hash`.

Tous doivent être acceptés.

---

# T17 — Tests négatifs

Un fichier de la suite de conformité par cas de T15, avec la raison de refus attendue.

---

# T18 — Exemple canonique TAKIBO

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
  evaluator_id:       spring-api
  evaluator_version:  1.0.0
  catalog_id:         spring-api-rules
  catalog_version:    1
  execution_id:       <fixture>
```

Les empreintes ont été calculées depuis le contenu Git du commit, selon la règle de T9. Les extraits
de ligne ci-dessus servent à la lecture de ce récit : ils ne font pas partie du fait.

Cette fixture ne constitue pas une analyse réelle effectuée par Taxo.

---

# Critères d'acceptation

1. Il existe une version machine du contrat : JSON Schema, validateur sémantique et suite de conformité.
2. `ASSERTION`, `ABSENCE` et `COVERAGE` sont représentables, chacune avec sa structure propre.
3. `OBSERVED`, `INFERRED` et `HUMAN_VALIDATED` sont représentables.
4. `VALID`, `STALE` et `REVALIDATION_REQUIRED` sont représentables ; un fait soumis est `VALID`.
5. Identité et occurrence sont séparées dans la structure.
6. Les références suivent la syntaxe `type:clé` et la liste fermée des types v1.
7. Chaque fait référence son instantané ; toute preuve appartient à cet instantané.
8. La provenance de l'évaluateur et de son catalogue est obligatoire.
9. `content_hash` suit l'algorithme de T9 ; LF et CRLF donnent la même empreinte.
10. Les 14 cas de T15 sont refusés, chacun avec sa raison.
11. Le vocabulaire des relations est versionné ; une relation inconnue est refusée.
12. Tout champ inconnu est refusé ; aucun score de confiance n'est requis, généré ni accepté.
13. Aucun champ ne permet de stocker du texte source.
14. La fixture TAKIBO de T18 est acceptée.
15. La suite de conformité ne dépend d'aucune technologie d'analyse particulière.
16. Aucun LLM n'est utilisé.
17. Tous les tests sont verts.

---

# Définition de terminé

À la fin de TAXO-01A, n'importe quel futur évaluateur peut dire :

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
raison : OBSERVED exige une preuve
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
Spring API / Security
       ↓
Première projection (PR ou diagramme)
       ↓
Ask Taxo
```

Ask Taxo ne sera fiable que parce que les faits qu'il consomme auront franchi cette frontière.
