# ADR 0002 : Le contrat du fait Taxo

Date : 2026-09-12
Amendé : 2026-09-13, deux fois (voir « Historique »)
Statut : Proposé
Dépend de : ADR 0001

## Contexte

Tous les évaluateurs et toutes les projections de Taxo échangent des faits. Si leur signification
n'est pas fixée avant le deuxième évaluateur, chaque nouvel évaluateur imposera une réécriture.

Ce document fixe la **signification** d'un fait, pas son stockage : ni base, ni graphe, ni
technologie de sérialisation ne sont décidés ici.

## Décision

### 1. Trois natures de fait

| Nature | Ce qu'il affirme | Structure propre | Preuve | Statut |
| --- | --- | --- | --- | --- |
| `ASSERTION` | un sujet est lié à un objet par une relation | `subject`, `relation`, `object`, `qualifiers` | obligatoire si `OBSERVED` | `OBSERVED`, `INFERRED`, `HUMAN_VALIDATED` |
| `ABSENCE` | un motif est introuvable dans un périmètre | `pattern`, `scope`, `method` | **interdite** | `OBSERVED` uniquement |
| `COVERAGE` | ce qu'une exécution a analysé, reconnu ou n'a pas su lire | `subject`, `coverage_type`, `scope` | facultative | `OBSERVED` uniquement |

- **Seule une assertion porte une relation.**
- **Une absence n'a pas de preuve** : c'est sa définition. Sa rigueur vient de son motif, de son
  périmètre et de sa méthode. Une absence littérale ne prouve pas une absence à l'exécution.
- Types de couverture v1 : `ANALYSED`, `RECOGNIZED`, `NOT_INTERPRETED`, `OUT_OF_SCOPE`, `READ_ERROR`.

### 2. Identité et occurrence

Un fait a une **identité stable** : ce qu'il affirme, indépendamment du commit.

| Nature | Champs d'identité |
| --- | --- |
| `ASSERTION` | nature, sujet, relation, objet, qualificatifs |
| `ABSENCE` | nature, motif, méthode, périmètre |
| `COVERAGE` | nature, sujet, type de couverture, périmètre, identifiant du producteur |

Le périmètre participe à l'identité d'une couverture : « `PolicyEvaluator` non interprété dans le
module A » et « `PolicyEvaluator` non interprété dans tout le dépôt » sont deux faits distincts.

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

Le calcul effectif de l'identité (normalisation, forme canonique, empreinte) relève du récit TAXO-01B.

### 3. Références d'entités

Un sujet ou un objet est une référence `type:clé`. La liste des types v1 est **fermée** :

```text
repository   module   directory   file   symbol   endpoint   route-pattern
technology   language   annotation   role   permission   policy-rule
```

Exemples :

```text
repository:takibo-iam
module:takibo-management-service
directory:takibo-security-management/src/main/java
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

- `directory` désigne un sous-arbre : chemin relatif à la racine du dépôt, séparateurs `/`, sans
  `/` final.
- Une valeur littérale n'est admise que dans `object` lorsque la relation le prévoit, ou dans
  `qualifiers`.
- Les clés naturelles ne contiennent jamais de numéro de ligne ni d'identifiant technique généré.
- Ajouter un type est une évolution explicite du contrat.

### 4. Périmètre

`scope` est une structure, jamais une phrase libre.

```text
scope:
  include[]   au moins une référence
  exclude[]   facultatif
```

Types de référence admis dans `include` et `exclude` : `repository`, `module`, `directory`, `file`.

| Périmètre | Représentation |
| --- | --- |
| tout le dépôt | `include: [repository:takibo-iam]` |
| un module | `include: [module:takibo-security-management]` |
| un ensemble de fichiers | `include: [file:a/B.java, file:a/C.java]` |
| un sous-arbre | `include: [directory:takibo-security-management/src/main/java]` |
| une exclusion | `exclude: [directory:takibo-security-management/src/test]` |

- Le périmètre dit **où**. Le **comment** est porté ailleurs : la méthode pour une `ABSENCE`, le
  catalogue du producteur pour une `COVERAGE`. « catalogue Security v1 » n'est donc jamais un
  périmètre.
- Le commit n'en fait pas partie : il appartient à l'instantané.
- La forme canonique du périmètre (références normalisées, listes triées et sans doublon) est
  calculée en TAXO-01B ; c'est elle qui entre dans l'identité.

### 5. Producteur

Un fait est produit par l'une des trois familles de producteurs de l'ADR 0001.

```text
produced_by:
  producer_type      EVALUATOR | PROJECTION | HUMAN
  producer_id        identifiant de l'évaluateur, de la projection ou de la personne
  producer_version   obligatoire pour EVALUATOR et PROJECTION ; absent pour HUMAN
  execution_id       obligatoire pour EVALUATOR et PROJECTION ; absent pour HUMAN
  catalog_id         obligatoire pour EVALUATOR ; absent sinon
  catalog_version    obligatoire pour EVALUATOR ; absent sinon
```

Une seule structure, avec des champs conditionnels, plutôt que trois structures distinctes : le
validateur applique la matrice ci-dessous, et toute projection lit la provenance de la même façon.

| Producteur | `ASSERTION` | `ABSENCE` | `COVERAGE` |
| --- | --- | --- | --- |
| `EVALUATOR` | `OBSERVED`, `INFERRED` | `OBSERVED` | `OBSERVED` |
| `PROJECTION` | `INFERRED` | interdit | interdit |
| `HUMAN` | `HUMAN_VALIDATED` | interdit | interdit |

- **Une projection ou une personne n'est jamais enregistrée comme évaluateur.**
- Un évaluateur ne produit un fait `INFERRED` que par une règle nommée appliquée à des faits du même
  instantané (par exemple `MATCHED_BY` ou `DISPATCHES_TO`).
- Pour `HUMAN`, la personne est `producer_id` ; le bloc `validation` porte la date, l'énoncé et les
  ancrages.
- Un LLM n'est pas un producteur : ce qu'il écrit est de la NARRATION (section 12).

### 6. Champs

| Champ | Obligatoire | Contenu |
| --- | --- | --- |
| `contract_version` | oui | version du contrat du fait (v1) |
| `kind` | oui | `ASSERTION`, `ABSENCE` ou `COVERAGE` |
| champs d'identité | oui | selon la nature (sections 1 et 2) |
| `status` | oui | `OBSERVED`, `INFERRED` ou `HUMAN_VALIDATED` |
| `validity` | oui | `VALID`, `STALE` ou `REVALIDATION_REQUIRED` |
| `snapshot` | oui | `repository`, `commit`, `mode` (`COMMIT` ou `WORKING_TREE`) ; `content_fingerprint` obligatoire en `WORKING_TREE` |
| `evidence[]` | selon la nature | au moins une pour une `ASSERTION` `OBSERVED` ; facultatif pour une `COVERAGE` ; interdit pour une `ABSENCE` |
| `derivation` | si `INFERRED` | `premises` (identités de faits), `rule`, `counter_examples_checked`, `known_gaps` |
| `validation` | si `HUMAN_VALIDATED` | `validated_at`, `statement`, `anchors` (symbole et empreinte) |
| `produced_by` | oui | section 5 |

- L'horodatage d'analyse appartient à l'**exécution** référencée par `execution_id`, pas au fait ni
  à l'instantané : un même commit peut être analysé plusieurs fois. Pour une personne, la date est
  `validation.validated_at`.
- **Tout champ inconnu est refusé**, en particulier tout champ de confiance.
- **Le contrat ne comporte aucun champ destiné à conserver un extrait brut de code source.** Les
  producteurs restent responsables de ne jamais émettre de secret ou de valeur sensible, y compris
  dans les champs textuels (qualificatifs, valeur d'un motif, énoncé d'une validation, valeurs
  littérales).

### 7. Preuve

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
- **La preuve ne stocke jamais de texte source brut** : seulement chemin, lignes, symbole, méthode
  et empreinte.
- `content_hash` est calculé ainsi :
  1. prendre les lignes citées (le fichier entier si aucune ligne n'est citée) ;
  2. décoder en UTF-8 ;
  3. retirer tout caractère `\r` ;
  4. joindre les lignes par `\n`, sans `\n` final ;
  5. appliquer SHA-256 ; écrire `sha256:` suivi de l'empreinte en hexadécimal minuscule.

  La normalisation des fins de ligne est indispensable : les fichiers de TAKIBO sont en LF dans Git
  et en CRLF dans le dossier de travail Windows (`core.autocrlf=true`). Sans elle, un même code
  aurait deux empreintes, et Taxo annoncerait de fausses modifications.

### 8. Vocabulaire des relations (v1)

Limité à ce dont les premiers évaluateurs ont besoin. Le vocabulaire est versionné ; ajouter une
relation est une évolution explicite. La colonne « producteur habituel » est indicative : la règle
contraignante est la matrice de la section 5.

| Relation | Sujet → objet | Statut habituel | Producteur habituel |
| --- | --- | --- | --- |
| `CONTAINS` | repository ou module → module ou file | `OBSERVED` | Inventory |
| `WRITTEN_IN` | file → language | `OBSERVED` | Inventory |
| `USES_TECHNOLOGY` | repository ou module → technology | `OBSERVED` | Inventory |
| `DECLARED_BY` | technology → file (manifeste) | `OBSERVED` | Inventory |
| `ANNOTATED_WITH` | symbol → annotation (valeurs en qualificatifs) | `OBSERVED` | analyseur de langage |
| `CALLS` | symbol → symbol | `OBSERVED` | analyseur de langage |
| `IMPLEMENTS` | symbol → symbol (interface) | `OBSERVED` | analyseur de langage |
| `DISPATCHES_TO` | symbol (méthode d'interface) → symbol (implémentation) | `INFERRED` | analyseur de langage |
| `HANDLED_BY` | endpoint → symbol | `OBSERVED` | Spring API |
| `ACCEPTS` / `RETURNS` | endpoint → symbol (type) | `OBSERVED` | Spring API |
| `PERMITS_ALL` | route-pattern → (aucun) | `OBSERVED` | Spring Security |
| `AUTHORIZED_BY` | route-pattern → symbol ou expression littérale | `OBSERVED` | Spring Security |
| `MATCHED_BY` | endpoint → route-pattern | `INFERRED` | Spring Security |
| `PROTECTED_BY` | endpoint → symbol ou policy-rule | `INFERRED` ou `HUMAN_VALIDATED` | Spring Security, projection, personne |

- `DISPATCHES_TO` est toujours une inférence : c'est le conteneur (Spring) qui choisit
  l'implémentation à l'exécution. Règle v1 : « implémentation unique dans le périmètre analysé ».
  Le fait devient `STALE` dès qu'une deuxième implémentation apparaît.
- `MATCHED_BY` est toujours une inférence : il applique la sémantique de correspondance des motifs
  du framework. Règle v1 : « premier motif correspondant dans l'ordre de déclaration » ; les motifs
  antérieurs qui ne correspondent pas figurent dans `counter_examples_checked`.
- **`PROTECTED_BY` ne se déduit jamais de `HANDLED_BY`.** Il s'appuie sur `MATCHED_BY` puis
  `AUTHORIZED_BY`, pour que Taxo puisse expliquer pourquoi un endpoint est protégé, prémisse par
  prémisse (voir les exemples).
- `NOT_INTERPRETED` n'est pas une relation : c'est un type de couverture (section 1).

### 9. Statuts, validité et confiance

- **`OBSERVED`** : extrait mécaniquement d'une source par une règle de détection nommée. Produit
  uniquement par un évaluateur.
- **`INFERRED`** : dérivé d'autres faits par une règle nommée. Produit par un évaluateur ou par une
  projection. Si une prémisse n'est plus présente dans l'instantané, le fait devient `STALE`.
- **`HUMAN_VALIDATED`** : affirmé ou confirmé par une personne identifiée, ancré sur des symboles et
  leurs empreintes. Produit uniquement par une personne. Si un ancrage change, le fait devient
  `REVALIDATION_REQUIRED`. C'est aussi la voie pour documenter ce qu'aucun évaluateur ne sait encore
  interpréter.

**La validité est décidée par la mémoire, pas par le producteur.** Un producteur ne soumet que des
faits `VALID`. `STALE` et `REVALIDATION_REQUIRED` sont posés par Taxo lors de la réévaluation.

**Confiance.** Aucun pourcentage en v1, et tout champ de confiance est refusé. Une conclusion
`INFERRED` s'appuie sur sa dérivation lisible. Un score chiffré ne pourra être introduit que par un
ADR qui décrit sa méthode et son calibrage.

### 10. Règles de cohérence

1. Une `ASSERTION` `OBSERVED` porte au moins une preuve.
2. Une `ABSENCE` porte un motif, un périmètre et une méthode ; elle n'a ni relation ni preuve.
3. Une `COVERAGE` porte un sujet, un type de couverture et un périmètre ; sa preuve est facultative.
4. Toute preuve appartient au dépôt et au commit de l'instantané du fait.
5. Un fait `INFERRED` porte au moins une prémisse et une règle de dérivation.
6. Un fait `HUMAN_VALIDATED` porte une validation complète et au moins un ancrage.
7. Le statut est compatible avec la nature et avec le type de producteur (matrice de la section 5).
8. Un évaluateur déclare son catalogue ; un évaluateur ou une projection déclare sa version et son
   exécution ; une personne ne déclare ni catalogue, ni version, ni exécution.
9. Un périmètre porte au moins une inclusion, et n'utilise que les types `repository`, `module`,
   `directory` et `file`.
10. Toute relation appartient au vocabulaire de la version du contrat ; tout type de référence
    appartient à la liste fermée.
11. Un fait soumis par un producteur est `VALID`.
12. Tout champ inconnu est refusé.
13. Un instantané `WORKING_TREE` porte une empreinte de contenu.
14. Chaque exécution d'évaluateur produit au moins un fait `COVERAGE`.
15. Un producteur n'altère jamais les faits d'un autre : il enrichit un sujet en ajoutant les siens.
16. Quand deux instantanés ont été analysés par des versions différentes d'un producteur ou de son
    catalogue, chaque différence est marquée « cause possible : évolution du producteur ».

### 11. Forme machine

Le contrat est matérialisé par trois éléments, indépendants de toute technologie d'analyse :

- un **JSON Schema** versionné pour la structure ;
- un **validateur sémantique** pour les règles qui croisent plusieurs champs (règles 4, 7 et 8, par
  exemple) ;
- une **suite de conformité** : des fichiers d'exemples valides et invalides, avec pour chacun le
  résultat attendu. Tout producteur, en Python comme sur la JVM, doit la passer.

### 12. Conséquences pour les projections et pour Ask Taxo

- **Une projection qui persiste une conclusion** la soumet comme fait `INFERRED`, avec
  `producer_type: PROJECTION`, des prémisses et une règle nommée. Elle ne se présente jamais comme
  un évaluateur.
- **NARRATION.** Le texte qu'une projection ajoute pour rendre un résultat lisible (par exemple
  « l'administrateur crée un Space », écrit par un LLM) est un **niveau d'affichage**, pas un statut.
  Il n'a pas d'identité, n'est jamais persisté et ne sert jamais de prémisse. Il est remplacé par un
  fait dès qu'un fait existe.
- **Ask Taxo est une projection.** Il lit des faits ; un LLM peut l'aider à comprendre la question
  et à rédiger la réponse, mais ce texte reste de la NARRATION.
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

### Pourquoi cet endpoint est-il protégé ?

```text
F1  ASSERTION  OBSERVED                           producteur : EVALUATOR spring-api
    endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
    HANDLED_BY
    symbol:java:...OAuthClientController#register
    preuves : OAuthClientController.java:26 (@RequestMapping), :34-35 (@PostMapping)

F2  ASSERTION  OBSERVED                           producteur : EVALUATOR spring-security
    route-pattern:/api/v1/**
    AUTHORIZED_BY
    symbol:java:...PolicyBasedAuthorizationManager
    preuve : SecurityConfig.java:83

F3  ASSERTION  INFERRED                           producteur : EVALUATOR spring-security
    endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
    MATCHED_BY
    route-pattern:/api/v1/**
    dérivation : F1 + F2 ; règle spring-security.first-matching-pattern
    contre-exemples vérifiés : aucun motif déclaré avant la ligne 83 ne correspond à ce chemin
                               (SecurityConfig.java:51-82)

F4  ASSERTION  INFERRED                           producteur : EVALUATOR spring-security
    endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
    PROTECTED_BY
    symbol:java:...PolicyBasedAuthorizationManager
    dérivation : F2 + F3 ; règle spring-security.route-authorization-applies
    lacune connue : règle fine dans PolicyEvaluator (F6)

F5  ASSERTION  OBSERVED                           producteur : EVALUATOR java-analyzer
    symbol:java:...PolicyBasedAuthorizationManager
    CALLS
    symbol:java:...PolicyEvaluator#evaluate
    preuves : PolicyBasedAuthorizationManager.java:45, :101

F6  COVERAGE  OBSERVED                            producteur : EVALUATOR spring-security
    symbol:java:...PolicyEvaluator
    coverage_type : NOT_INTERPRETED
    périmètre : include [module:takibo-security-management]
```

À la question « pourquoi dis-tu que cet endpoint est protégé ? », Taxo répond par la chaîne
`endpoint → MATCHED_BY (F3) → /api/v1/** → AUTHORIZED_BY (F2) → PolicyBasedAuthorizationManager`,
avec chaque prémisse et sa preuve, et signale la limite F6.

### Absence, implémentation et validation humaine

```text
F7  ABSENCE  OBSERVED                             producteur : EVALUATOR java-analyzer
    motif : littéral "P_SPACE_USER_CREATE"
    périmètre : include [repository:takibo-iam]
    méthode : java.string-literal-search
    réserve : TAKIBO construit des préfixes de permission (HumanTokenSigner.java:81)

F8  ASSERTION  OBSERVED                           producteur : EVALUATOR java-analyzer
    symbol:java:...SpaceRepositoryAdapter
    IMPLEMENTS
    symbol:java:...SpaceRepository
    preuve : SpaceRepositoryAdapter.java:21

F9  COVERAGE  OBSERVED                            producteur : EVALUATOR java-analyzer
    repository:takibo-iam
    coverage_type : ANALYSED
    périmètre : include [repository:takibo-iam]

F10 ASSERTION  INFERRED                           producteur : EVALUATOR java-analyzer
    symbol:java:...SpaceRepository#save
    DISPATCHES_TO
    symbol:java:...SpaceRepositoryAdapter
    dérivation : F8 + F9 ; règle java.single-implementation-in-scope
                 (une seule relation IMPLEMENTS vers l'interface sur un périmètre analysé)

F11 ASSERTION  HUMAN_VALIDATED                    producteur : HUMAN <personne>
    endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
    PROTECTED_BY
    policy-rule:POL_OAUTH_CLIENT_ADMIN_REQUIRED
    ancrage : symbol PolicyEvaluator#denyOAuthClientSurface (PolicyEvaluator.java:285-324), empreinte
    validé le : <date>
```

F4, F6 et F11 montrent le chemin normal : Taxo conclut prudemment ce qu'il peut, déclare ce qu'il ne
comprend pas, et une personne comble l'écart jusqu'à ce qu'un évaluateur sache le faire.

## Conséquences

- Le graphe de connaissances n'est pas à construire : il émerge de faits dont les sujets et les
  objets sont des références stables.
- Un analyseur externe (JVM, TypeScript…) n'a qu'une obligation : produire des faits conformes et
  passer la suite de conformité.

## Historique

**2026-09-13 (revue de la PR #1)**

- La règle de preuve est formulée par nature : obligatoire pour une `ASSERTION` `OBSERVED`,
  interdite pour une `ABSENCE`, facultative pour une `COVERAGE`.
- Provenance générique `produced_by` (`EVALUATOR`, `PROJECTION`, `HUMAN`) et matrice
  producteur / nature / statut ; `validation.validated_by` est remplacé par le producteur `HUMAN`.
- Périmètre structuré (`include`, `exclude`) ; type de référence `directory` ; le périmètre et le
  producteur entrent dans l'identité d'une `COVERAGE`.
- `PROTECTED_BY` s'appuie sur `MATCHED_BY` et `AUTHORIZED_BY` ; exemples réécrits en conséquence ;
  producteur habituel indiqué pour chaque relation (analyseur de langage ou évaluateur de framework).
- Promesse sur les secrets ramenée à ce que le contrat garantit réellement.
- Ask Taxo explicitement placé parmi les projections.

**2026-09-13** : amendements issus de la relecture du récit TAXO-01A.

- Contradiction corrigée : une `ABSENCE` n'a pas de preuve (l'ancienne règle 1 exigeait une preuve
  pour tout fait `OBSERVED`, alors que l'exemple F6 était une absence sans preuve).
- Structures propres à chaque nature ; `NOT_INTERPRETED` passe de relation à type de couverture.
- Séparation explicite entre identité et occurrence.
- Liste fermée des types de référence.
- Algorithme et normalisation de `content_hash`.
- Validité décidée par la mémoire ; un producteur ne soumet que `VALID`.
- Champs inconnus refusés, y compris la confiance ; aucun champ destiné à un extrait de code source.
- Horodatage d'analyse déplacé vers l'exécution ; empreinte de contenu en mode `WORKING_TREE`.
- Relations `IMPLEMENTS` et `DISPATCHES_TO`.
- Forme machine : schéma, validateur sémantique, suite de conformité.
- Conséquences pour les projections : NARRATION et trois fins de parcours.
