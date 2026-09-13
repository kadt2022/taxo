# ADR 0002 : Le contrat du fait Taxo

Date : 2026-09-12
Amendé : 2026-09-13 (voir « Historique »)
Statut : Proposé
Dépend de : ADR 0001

## Contexte

Tous les évaluateurs et toutes les projections de Taxo échangent des faits. Si leur signification
n'est pas fixée avant le deuxième évaluateur, chaque nouvel évaluateur imposera une réécriture.

Ce document fixe la **signification** d'un fait, pas son stockage : ni base, ni graphe, ni
technologie de sérialisation ne sont décidés ici.

## Décision

### 1. Trois natures de fait

| Nature | Ce qu'il affirme | Structure propre | Statuts possibles |
| --- | --- | --- | --- |
| `ASSERTION` | un sujet est lié à un objet par une relation | `subject`, `relation`, `object`, `qualifiers` | `OBSERVED`, `INFERRED`, `HUMAN_VALIDATED` |
| `ABSENCE` | un motif est introuvable dans un périmètre | `pattern`, `scope`, `method` | `OBSERVED` uniquement |
| `COVERAGE` | ce qu'une exécution a analysé, reconnu ou n'a pas su lire | `subject`, `coverage_type`, `scope` | `OBSERVED` uniquement |

- **Seule une assertion porte une relation.**
- **Une absence n'a pas de preuve** : c'est sa définition. Sa rigueur vient de son motif, de son
  périmètre et de sa méthode. Une absence littérale ne prouve pas une absence à l'exécution.
- Types de couverture v1 : `ANALYSED`, `RECOGNIZED`, `NOT_INTERPRETED`, `OUT_OF_SCOPE`, `READ_ERROR`.

### 2. Identité et occurrence

Un fait a une **identité stable** : ce qu'il affirme, indépendamment du commit.

| Nature | Champs d'identité |
| --- | --- |
| `ASSERTION` | nature, sujet, relation, objet, qualificatifs |
| `ABSENCE` | nature, motif, méthode, périmètre (hors commit) |
| `COVERAGE` | nature, sujet, type de couverture, identifiant de l'évaluateur |

Un fait a aussi des **occurrences** : chaque instantané où il a été établi. Une occurrence porte le
statut, la validité, l'instantané, les preuves, la dérivation ou la validation, et le producteur.

La comparaison de deux instantanés s'appuie sur l'identité :

```text
commit A  absent
commit B  introduit
commit C  modifié     (même sujet et relation, objet ou qualificatifs différents ;
                       ou changement de statut d'une même identité)
commit D  retiré
```

Le calcul effectif de l'identité (normalisation, empreinte) relève du récit TAXO-01B.

### 3. Références d'entités

Un sujet ou un objet est une référence `type:clé`. La liste des types v1 est **fermée** :

```text
repository   module   file   symbol   endpoint   route-pattern
technology   language   annotation   role   permission   policy-rule
```

Exemples :

```text
repository:takibo-iam
module:takibo-management-service
file:takibo-security-management/src/main/java/.../SecurityConfig.java
symbol:java:com.takibo.managementservice.interfaces.rest.api.OAuthClientController#register
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
route-pattern:/api/v1/**
technology:Spring Boot
language:Java
annotation:org.springframework.security.access.prepost.PreAuthorize
role:R_ORG_ADMIN
permission:P_ORG_SPACES_CREATE
policy-rule:POL_OAUTH_CLIENT_ADMIN_REQUIRED
```

- Une valeur littérale n'est admise que dans `object` lorsque la relation le prévoit, ou dans
  `qualifiers`.
- Les clés naturelles ne contiennent jamais de numéro de ligne ni d'identifiant technique généré.
- Ajouter un type est une évolution explicite du contrat.

### 4. Champs

| Champ | Obligatoire | Contenu |
| --- | --- | --- |
| `contract_version` | oui | version du contrat du fait (v1) |
| `kind` | oui | `ASSERTION`, `ABSENCE` ou `COVERAGE` |
| champs d'identité | oui | selon la nature (section 2) |
| `status` | oui | `OBSERVED`, `INFERRED` ou `HUMAN_VALIDATED` |
| `validity` | oui | `VALID`, `STALE` ou `REVALIDATION_REQUIRED` |
| `snapshot` | oui | `repository`, `commit`, `mode` (`COMMIT` ou `WORKING_TREE`) ; `content_fingerprint` obligatoire en `WORKING_TREE` |
| `evidence[]` | si `ASSERTION` `OBSERVED` | voir section 5 |
| `derivation` | si `INFERRED` | `premises` (identités de faits), `rule`, `counter_examples_checked`, `known_gaps` |
| `validation` | si `HUMAN_VALIDATED` | `validated_by`, `validated_at`, `statement`, `anchors` (symbole et empreinte) |
| `produced_by` | oui | `evaluator_id`, `evaluator_version`, `catalog_id`, `catalog_version`, `execution_id` |

- L'horodatage d'analyse appartient à l'**exécution** référencée par `execution_id`, pas au fait ni
  à l'instantané : un même commit peut être analysé plusieurs fois.
- **Tout champ inconnu est refusé**, en particulier tout champ de confiance.
- **Aucun champ ne peut contenir de texte source.** C'est la garantie structurelle qu'aucune valeur
  sensible n'est copiée dans un fait : il n'existe tout simplement pas d'emplacement pour elle.

### 5. Preuve

```text
repository     takibo-iam
commit         80eb595f6d03eea67eb86eae4c7640f94bd3f94c
path           takibo-security-management/src/main/java/.../SecurityConfig.java
line_start     83
line_end       83
symbol         (facultatif)
method         java.spring-security.request-matcher
content_hash   sha256:<hex>
```

- `repository` et `commit` sont ceux de l'instantané du fait.
- `path` est relatif à la racine du dépôt, avec des séparateurs `/`.
- `method` est obligatoire : elle nomme la règle d'extraction et rend le fait reproductible.
- `content_hash` est calculé ainsi :
  1. prendre les lignes citées (le fichier entier si aucune ligne n'est citée) ;
  2. décoder en UTF-8 ;
  3. retirer tout caractère `\r` ;
  4. joindre les lignes par `\n`, sans `\n` final ;
  5. appliquer SHA-256 ; écrire `sha256:` suivi de l'empreinte en hexadécimal minuscule.

  La normalisation des fins de ligne est indispensable : les fichiers de TAKIBO sont en LF dans Git
  et en CRLF dans le dossier de travail Windows (`core.autocrlf=true`). Sans elle, un même code
  aurait deux empreintes, et Taxo annoncerait de fausses modifications.

### 6. Vocabulaire des relations (v1)

Limité à ce dont les premiers évaluateurs ont besoin. Le vocabulaire est versionné ; ajouter une
relation est une évolution explicite.

| Relation | Sujet → objet | Statut habituel |
| --- | --- | --- |
| `CONTAINS` | repository ou module → module ou file | `OBSERVED` |
| `WRITTEN_IN` | file → language | `OBSERVED` |
| `USES_TECHNOLOGY` | repository ou module → technology | `OBSERVED` |
| `DECLARED_BY` | technology → file (manifeste) | `OBSERVED` |
| `HANDLED_BY` | endpoint → symbol | `OBSERVED` |
| `ACCEPTS` / `RETURNS` | endpoint → symbol (type) | `OBSERVED` |
| `MATCHED_BY` | endpoint → route-pattern | `INFERRED` (le motif couvre le chemin) |
| `PERMITS_ALL` | route-pattern → (aucun) | `OBSERVED` |
| `AUTHORIZED_BY` | route-pattern → symbol ou expression littérale | `OBSERVED` |
| `ANNOTATED_WITH` | symbol → annotation (valeur en qualificatif) | `OBSERVED` |
| `CALLS` | symbol → symbol | `OBSERVED` |
| `IMPLEMENTS` | symbol → symbol (interface) | `OBSERVED` |
| `DISPATCHES_TO` | symbol (méthode d'interface) → symbol (implémentation) | `INFERRED` |
| `PROTECTED_BY` | endpoint → symbol ou policy-rule | `INFERRED` ou `HUMAN_VALIDATED` |

`DISPATCHES_TO` est toujours une inférence : c'est le conteneur (Spring) qui choisit
l'implémentation à l'exécution. La règle v1 est « implémentation unique dans le périmètre analysé ».
Le fait devient `STALE` dès qu'une deuxième implémentation apparaît.

`NOT_INTERPRETED` n'est plus une relation : c'est un type de couverture (section 1).

### 7. Statuts, validité et confiance

- **`OBSERVED`** : extrait mécaniquement d'une source par une règle de détection nommée.
- **`INFERRED`** : dérivé d'autres faits par une règle nommée. Si une prémisse n'est plus présente
  dans l'instantané, le fait devient `STALE`.
- **`HUMAN_VALIDATED`** : affirmé ou confirmé par une personne identifiée, ancré sur des symboles
  et leurs empreintes. Si un ancrage change, le fait devient `REVALIDATION_REQUIRED`. C'est aussi
  la voie pour documenter ce qu'aucun évaluateur ne sait encore interpréter.

**La validité est décidée par la mémoire, pas par le producteur.** Un évaluateur ne soumet que des
faits `VALID`. `STALE` et `REVALIDATION_REQUIRED` sont posés par Taxo lors de la réévaluation.

**Confiance.** Aucun pourcentage en v1, et tout champ de confiance est refusé. Une conclusion
`INFERRED` s'appuie sur sa dérivation lisible. Un score chiffré ne pourra être introduit que par un
ADR qui décrit sa méthode et son calibrage.

### 8. Règles de cohérence

1. Une `ASSERTION` `OBSERVED` porte au moins une preuve.
2. Toute preuve appartient au dépôt et au commit de l'instantané du fait.
3. Un fait `INFERRED` porte au moins une prémisse et une règle de dérivation.
4. Un fait `HUMAN_VALIDATED` porte une validation complète et au moins un ancrage.
5. Une `ABSENCE` porte un motif, un périmètre et une méthode ; elle n'a ni relation ni preuve.
6. Une `COVERAGE` porte un sujet, un type de couverture et un périmètre.
7. `ABSENCE` et `COVERAGE` sont toujours `OBSERVED`.
8. Toute relation appartient au vocabulaire de la version du contrat ; tout type de référence
   appartient à la liste fermée.
9. Un fait soumis par un évaluateur est `VALID`.
10. Tout champ inconnu est refusé.
11. Un instantané `WORKING_TREE` porte une empreinte de contenu.
12. Chaque exécution d'évaluateur produit au moins un fait `COVERAGE`.
13. Un évaluateur n'altère jamais les faits d'un autre : il enrichit un sujet en ajoutant les siens.
14. Quand deux instantanés ont été analysés par des versions différentes d'un évaluateur ou de son
    catalogue, chaque différence est marquée « cause possible : évolution de l'évaluateur ».

### 9. Forme machine

Le contrat est matérialisé par trois éléments, indépendants de toute technologie d'analyse :

- un **JSON Schema** versionné pour la structure ;
- un **validateur sémantique** pour les règles qui croisent plusieurs champs (règle 2, par exemple) ;
- une **suite de conformité** : des fichiers d'exemples valides et invalides, avec pour chacun le
  résultat attendu. Tout analyseur, en Python comme sur la JVM, doit la passer.

### 10. Conséquences pour les projections

- **NARRATION.** Le texte qu'une projection ajoute pour rendre un résultat lisible (par exemple
  « l'administrateur crée un Space », écrit par un LLM) est un **niveau d'affichage**, pas un statut.
  Il n'a pas d'identité, n'est jamais stocké et ne sert jamais de prémisse. Il est remplacé par un
  fait dès qu'un fait existe.
- **Trois fins de parcours.** Quand une projection suit des relations, chaque branche se termine
  d'une de ces trois façons, toujours affichée :

  | Fin | Signification | Établie par |
  | --- | --- | --- |
  | établie | le flux s'arrête réellement (écriture dans une table…) | faits `OBSERVED` |
  | non interprétée | un évaluateur a vu la suite sans savoir la lire | `COVERAGE` `NOT_INTERPRETED` |
  | non analysée | aucun évaluateur n'a couvert cette dimension pour l'instantané | absence d'exécution |

  Sans les faits `COVERAGE`, l'absence d'une relation serait indiscernable d'une fin de flux.

## Exemples

Relevés sur TAKIBO-IAM au commit `80eb595` les 12 et 13 septembre 2026.

```text
F1  ASSERTION  OBSERVED
    endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
    HANDLED_BY
    symbol:java:...OAuthClientController#register
    preuves : OAuthClientController.java:26 (@RequestMapping), :34-35 (@PostMapping)

F2  ASSERTION  OBSERVED
    route-pattern:/api/v1/**
    AUTHORIZED_BY
    symbol:java:...PolicyBasedAuthorizationManager
    preuve : SecurityConfig.java:83

F3  ASSERTION  OBSERVED
    symbol:java:...PolicyBasedAuthorizationManager
    CALLS
    symbol:java:...PolicyEvaluator#evaluate
    preuves : PolicyBasedAuthorizationManager.java:45, :101

F4  COVERAGE  OBSERVED
    symbol:java:...PolicyEvaluator
    coverage_type : NOT_INTERPRETED
    périmètre : catalogue Security v1 ; motif : autorisation maison fondée sur l'analyse du chemin

F5  ASSERTION  INFERRED
    endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
    PROTECTED_BY
    symbol:java:...PolicyBasedAuthorizationManager
    dérivation : F1 + F2 ; règle security.route-covers-endpoint
    lacune connue : règle fine dans PolicyEvaluator (F4)

F6  ABSENCE  OBSERVED
    motif : littéral "P_SPACE_USER_CREATE"
    périmètre : fichiers suivis au commit ; méthode : littéral exact
    réserve : TAKIBO construit des préfixes de permission (HumanTokenSigner.java:81)

F7  ASSERTION  OBSERVED
    symbol:java:...SpaceRepositoryAdapter
    IMPLEMENTS
    symbol:java:...SpaceRepository
    preuve : SpaceRepositoryAdapter.java:21

F8  ASSERTION  INFERRED
    symbol:java:...SpaceRepository#save
    DISPATCHES_TO
    symbol:java:...SpaceRepositoryAdapter
    dérivation : F7 + absence d'autre implémentation dans le périmètre analysé ;
                 règle java.single-implementation-in-scope

F9  ASSERTION  HUMAN_VALIDATED
    endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
    PROTECTED_BY
    policy-rule:POL_OAUTH_CLIENT_ADMIN_REQUIRED
    ancrage : symbol PolicyEvaluator#denyOAuthClientSurface (PolicyEvaluator.java:285-324), empreinte
    validé par : <personne>, <date>
```

F4, F5 et F9 montrent le chemin normal : Taxo déclare ce qu'il ne comprend pas, conclut prudemment
ce qu'il peut, et une personne comble l'écart jusqu'à ce qu'un évaluateur sache le faire.

## Conséquences

- Le graphe de connaissances n'est pas à construire : il émerge de faits dont les sujets et les
  objets sont des références stables.
- Un analyseur externe (JVM, TypeScript…) n'a qu'une obligation : produire des faits conformes et
  passer la suite de conformité.

## Historique

**2026-09-13** : amendements issus de la relecture du récit TAXO-01A.

- Contradiction corrigée : une `ABSENCE` n'a pas de preuve (l'ancienne règle 1 exigeait une preuve
  pour tout fait `OBSERVED`, alors que l'exemple F6 était une absence sans preuve).
- Structures propres à chaque nature ; `NOT_INTERPRETED` passe de relation à type de couverture.
- Séparation explicite entre identité et occurrence.
- Liste fermée des types de référence.
- Algorithme et normalisation de `content_hash`.
- Validité décidée par la mémoire ; un producteur ne soumet que `VALID`.
- Champs inconnus refusés, y compris la confiance ; garantie structurelle contre le texte source.
- Horodatage d'analyse déplacé vers l'exécution ; empreinte de contenu en mode `WORKING_TREE`.
- Relations `IMPLEMENTS` et `DISPATCHES_TO`.
- Forme machine : schéma, validateur sémantique, suite de conformité.
- Conséquences pour les projections : NARRATION et trois fins de parcours.
