# Plan Taxo

Mise à jour : 2026-09-19 (réorientation : prouver un fait cher et le mesurer avant 01E)
Références : ADR 0001, ADR 0002, ADR 0004, `EPIC-TAXO-01-fondation-memoire-verifiable.md`

## MVP

> Sur un projet Spring Boot, Taxo inventorie le dépôt, découvre les endpoints HTTP, relève leurs
> mécanismes d'autorisation observables et déclare ceux qu'il ne sait pas interpréter. Il rattache
> chaque résultat au code et au commit, et conserve ces faits dans une mémoire versionnée que les
> projections (PR, diagrammes, Ask Taxo, MCP) consomment sans relire le dépôt.

## Vue d'ensemble

```text
ÉPIQUE TAXO-01     Mémoire logicielle vérifiable
      ↓
TAXO-02            Inventory Evaluator
      ↓
TAXO-03            Java Analyzer : primitives Java (spike, puis ADR 0003)   + TAXO-01H
      ↓
TAXO-04            Spring API Evaluator : endpoints
      ↓
TAXO-05            Spring Security Evaluator
      ↓
TAXO-PROJ-PR-01    Projection PR                           DÉMO TECHNIQUE
      ↓
TAXO-PROJ-API-01   Projection Diagramme API                + TAXO-01I
      ↓
TAXO-ASK-01        Ask Taxo minimal                        DÉMO PRODUIT
```

## Deux démonstrations

| Démo | Question | Ce qu'elle prouve | Jalon |
| --- | --- | --- | --- |
| **Technique** | « Qu'est-ce qui a changé entre ces deux commits, et est-ce risqué ? » | reproductibilité, versionnement, preuves, changement du logiciel ou changement de producteur | TAXO-PROJ-PR-01 |
| **Produit** | « Explique-moi cette API et donne-moi son diagramme. » | expérience du nouvel arrivant, exploitation de la mémoire, diagramme construit depuis les faits, preuves, zones non interprétées | TAXO-ASK-01, après TAXO-PROJ-API-01 |

La démo technique est le premier jalon. La démo produit la suit sur la même mémoire.

## NOW : prouver un fait cher, puis mesurer

Réorientation actée le 2026-09-17. L'épique TAXO-01 a livré la forme — contrat, identité,
instantané, exécution, couverture — mais pas encore la preuve que Taxo établit une connaissance
qu'une commande shell ne donne pas : sur UAA, l'inventaire demande 30 s là où `git ls-files` répond
en 1,1 s. Persister des faits dont l'utilité n'est pas mesurée bâtirait sur une intention, ce que le
[manifeste](../manifeste.md) interdit.

| # | Étape | Ce qu'elle tranche |
| --- | --- | --- |
| 1 | **[TAXO-POC-01](TAXO-POC-01-verite-de-reference-chaine-autorisation.md)** | une chaîne d'autorisation est-elle produite sur une route réelle, avec preuves, prémisses et limites déclarées comme couvertures ? |
| 2 | **Benchmark manuel** (§12 du manifeste) | agent seul contre le même agent muni des faits : exactitude, complétude, fausses absences, validité des preuves, stabilité, temps, tokens |
| 3 | **01E Persistance** | ouverte si — et seulement si — le gain est net |
| 4 | **MCP-01** | trois outils (`find_facts`, `get_evidence`, `get_coverage`), chaque réponse portant sa couverture |
| 5 | **HIST-01** | lineage Git : ce qu'il faut recalculer, ce qui peut être réutilisé |

01F et 01G reprennent ensuite l'ordre de l'épique. Rien d'autre ne s'ouvre avant la chaîne prouvée.

État des récits de l'épique :

| Récit | Contenu | Tâches de l'épique | Statut |
| --- | --- | --- | --- |
| **01A** Contrat machine du fait | natures et règles de preuve par nature, statuts et producteurs autorisés, validité, identité et occurrence, syntaxe des références, référence d'instantané, périmètre structuré, provenance `produced_by`, preuve et empreinte, vocabulaire v1, règles de cohérence, suite de conformité | T1 | terminé / mergé : [récit](Terminé/TAXO-01A-contrat-machine-du-fait-TERMINÉ.md) |
| **01B** Références stables et identité | normalisation des clés et du périmètre, stabilité entre commits, calcul de l'identité stable d'un fait | T2 | terminé / mergé : [récit](Terminé/TAXO-01B-references-stables-identite-canonique-TERMINÉ.md) |
| **01C** Instantané au commit | lecture d'un commit en lecture seule ; mode `WORKING_TREE` marqué, avec empreinte du contenu ; fichiers ignorés par Git exclus | T3 | terminé / mergé : [récit](Terminé/TAXO-01C-instantane-git-au-commit-TERMINÉ.md) |
| **ARCH-01** Modularisation du backend | capacités, ports et adaptateurs ; refactoring sans changement métier ([ADR 0004](../adr/0004-monolithe-modulaire.md)) | préalable à T4 | terminé / mergé : [récit](TAXO-ARCH-01-modulariser-backend.md) |
| **01D** Exécution d'évaluateur et couverture | identité, version, catalogue, statuts T4 (`RUNNING`, `SUCCESS`, `PARTIAL`, `FAILED`, `UNSUPPORTED`), couverture déclarée séparée ; `evaluators/inventory` converti en Inventory v0 | T4 | terminé / mergé : [récit](TAXO-01D-execution-evaluateur-et-couverture.md) |
| **01E** Persistance | instantanés, exécutions, faits, occurrences, preuves, couvertures ; `scans.result` n'est plus la source de vérité | T5 | rédigé ; ouvert après la preuve et la mesure : [récit](TAXO-01E-persistance-de-la-memoire.md) |
| **01F** Comparaison et banc Git | introduit, retiré, modifié, inchangé ; « cause possible : évolution du producteur » ; dépôt de test A/B/C | T8, T11 | rédigé, à ouvrir après 01E : [récit](TAXO-01F-comparaison-et-banc-git.md) |
| **01G** API de lecture et vue de vérification | faits par instantané, identité, sujet, objet ou relation ; preuves ; couverture ; évaluateurs exécutés ; comparaison ; liste dans le portail | T9, T10 | rédigé, à ouvrir après 01F : [récit](TAXO-01G-api-de-lecture-et-vue-de-verification.md) |

Récits de l'épique placés au moment où ils servent :

| Récit | Contenu | Tâches | À réaliser avec |
| --- | --- | --- | --- |
| **01H** Validité et invalidation | `STALE`, `REVALIDATION_REQUIRED` | T7 | TAXO-03, premier producteur de faits `INFERRED` (`DISPATCHES_TO`) |
| **01I** Voisinage et projectabilité | voisinage d'une entité, reconstruction d'un flux depuis les seuls faits, trois fins de parcours ([récit](TAXO-01I-voisinage-et-projectabilite.md)) | T6, T12 | TAXO-PROJ-API-01 |

```text
01A Contrat ──► 01B Références ──┐
                                 ├──► ARCH-01 ──► 01D Exécution ──► 01E Persistance ──► 01F Comparaison ──► 01G API + vue
01C Instantané ──────────────────┘
```

01C est indépendant de 01A et 01B, et peut avancer en parallèle.

**Première démo possible après 01F** : Taxo compare deux commits, dit ce qui a changé dans
l'inventaire avec les preuves, et distingue une évolution du logiciel d'une évolution de Taxo.

## NEXT : trajectoire après l'épique

| Récit | Résultat attendu |
| --- | --- |
| **TAXO-02** Inventory Evaluator | inventaire complet sous forme de faits ; lecture de Gradle (`build.gradle`, `settings.gradle`), aujourd'hui ignoré par Inventory v0 alors que TAKIBO est un projet Gradle |
| **TAXO-03** Java Analyzer | analyseur de langage : classes, méthodes, annotations et leurs valeurs, constantes, types, appels, héritage, interfaces, résolution de symboles, sous forme de faits (`ANNOTATED_WITH`, `CALLS`, `IMPLEMENTS`, `DISPATCHES_TO`…). **Ne connaît pas le concept d'endpoint.** Spike de deux jours sur TAKIBO, puis ADR 0003 ; recommandation à confirmer : JavaParser + JavaSymbolSolver, sources seules, processus JVM séparé qui passe la suite de conformité de 01A. Avec 01H : `DISPATCHES_TO` devient `STALE` si une deuxième implémentation apparaît |
| **TAXO-04** Spring API Evaluator | évaluateur de framework, **propriétaire du concept d'endpoint** : consomme les primitives du Java Analyzer et produit `HANDLED_BY`, `ACCEPTS`, `RETURNS` avec des preuves dans la source |
| **TAXO-05** Spring Security Evaluator | propriétaire des concepts Spring Security : `PERMITS_ALL`, `AUTHORIZED_BY` (`OBSERVED`), puis `MATCHED_BY` et `PROTECTED_BY` (`INFERRED`) ; mécanismes maison déclarés `NOT_INTERPRETED` ; critère anti-faux-positif bloquant |
| **TAXO-PROJ-PR-01** Projection PR | **démo technique** : commentaire de PR listant les endpoints et autorisations ajoutés, modifiés ou retirés entre base et tête, avec preuves et commits ; distingue changement du logiciel et changement de producteur (cas 2) |
| **TAXO-PROJ-API-01** Projection Diagramme API | diagramme d'un endpoint construit depuis les seuls faits, statut de chaque élément, trois fins de parcours (cas 3) ; avec 01I |
| **TAXO-ASK-01** Ask Taxo minimal | **démo produit** : « explique-moi cette API et donne-moi son diagramme » ; résout la cible, interroge la mémoire, appelle la projection Diagramme API, affiche preuves et zones non interprétées ; le LLM ne sert qu'à comprendre la question et à rédiger (NARRATION) |
| **TAXO-TILES-01** Contrat de la Tuile | `KnowledgeTile` : projection vérifiable d'un ensemble de faits sur une frontière, trois résolutions, identité portant sur la connaissance, couverture et trous déclarés, coût annoncé ([récit](TAXO-TILES-01-contrat-de-la-tuile.md)) |
| **TAXO-TILES-02** La Maille | `MemoryMesh` : relations dérivées des prémisses, invalidation incrémentale, sélection par parcours depuis une ancre sous budget ; réutilise le voisinage de 01I ([récit](TAXO-TILES-02-la-maille.md)) |
| **TAXO-TILES-03** Contexte et protocole agent | `ContextSelection` : tuiles minimales pour une tâche, preuve paresseuse, déduplication de session, cache par empreinte, catégorie `ZERO-LLM`, banc d'amplification ([récit](TAXO-TILES-03-contexte-et-protocole-agent.md)) |

Les trois récits TILES forment le substrat commun des projections : ce que la PR, le diagramme, Ask
Taxo et un futur MCP consomment sans relire le dépôt. Ils sont rédigés mais **non ouverts**, et
supposent les faits de TAXO-04 et TAXO-05. Vocabulaire figé par l'[ADR 0005](../adr/0005-vocabulaire-tuile-maille-contexte.md).

Critères du spike TAXO-03 (vérifiables sur TAKIBO) :

1. Le Java Analyzer fournit les informations et résolutions nécessaires pour permettre au Spring API
   Evaluator de reconstruire les endpoints Spring du banc TAKIBO : annotations de classe et de
   méthode avec leurs valeurs résolues, y compris un `@PostMapping` sans argument. La
   reconstruction elle-même est vérifiée par un prototype jetable qui n'appartient pas au Java
   Analyzer.
2. `TechnicalRole.ORG_OWNER.code()` (`PolicyEvaluator.java:396`) résolu en `"R_ORG_OWNER"`, ou
   déclaré `NOT_INTERPRETED`.
3. `spaceRepository.save` mène à `SpaceRepository`, puis à `SpaceRepositoryAdapter` (`IMPLEMENTS`).
4. `@RequireActiveSpace` résolu vers son nom complet, alors qu'il vient d'un autre module.
5. Aucun Gradle exécuté, aucun jar lu, temps d'analyse mesuré.
6. Tout échec de résolution produit un fait `COVERAGE` ; l'analyse ne s'arrête jamais en entier.

Spring sert de cas de test difficile au spike. Le Java Analyzer ne devient pas pour autant un
analyseur Spring.

## LATER

Dependencies, Data, Documentation Drift, autres diagrammes, Impact Analysis, MCP, Structure,
Configuration, Frontend, Tests, CI/CD, Deployment, inventaire Documentation, Business Flows,
Release notes, source Sonar, source Runtime.

Les 17 récits du document de vision restent la description de ces capacités, pas un backlog.

## Décisions prises

**2026-09-13 (revue de la PR #1)**

- La règle de preuve est formulée par nature : obligatoire pour une `ASSERTION` `OBSERVED`,
  interdite pour une `ABSENCE`, facultative pour une `COVERAGE`.
- Provenance générique `produced_by` (`EVALUATOR`, `PROJECTION`, `HUMAN`) : une projection ou une
  personne n'est jamais enregistrée comme évaluateur.
- Périmètre structuré (`include`, `exclude`) ; il entre dans l'identité d'une `COVERAGE`.
- Frontière Java / Spring : le Java Analyzer produit les primitives Java ; le Spring API Evaluator
  est propriétaire du concept d'endpoint.
- `PROTECTED_BY` s'appuie sur `MATCHED_BY` puis `AUTHORIZED_BY`.
- Promesse sur les secrets limitée à ce que le contrat garantit.
- Deux démonstrations : technique (PR) puis produit (Ask Taxo) ; la projection Diagramme API et
  Ask Taxo minimal ont leur place dans la trajectoire.
- 01H est placé avec TAXO-03, premier producteur de faits `INFERRED` (`DISPATCHES_TO`), et non plus
  avec TAXO-05.

**2026-09-13 (suite)**

- Premier producteur de faits réels : `scanner.py` est converti en **Inventory v0 dans 01D**.
  TAXO-02 est réservé à l'enrichissement (Gradle, métriques). Le banc Git de 01F travaille donc
  sur de vrais faits, sans évaluateur factice.
- `.gitattributes` ajouté au dépôt Taxo : fins de ligne LF dans Git, cohérent avec la règle
  d'empreinte de l'ADR 0002.

**2026-09-13**

- ADR 0002 amendé : une `ABSENCE` n'a pas de preuve ; structures propres à chaque nature ;
  `NOT_INTERPRETED` devient un type de couverture ; séparation identité / occurrence ; liste fermée
  des types de référence ; algorithme de `content_hash` avec normalisation LF ; validité posée par
  la mémoire ; champs inconnus refusés ; relations `IMPLEMENTS` et `DISPATCHES_TO` ; forme machine
  (schéma, validateur, suite de conformité) ; NARRATION et trois fins de parcours pour les projections.
- TAXO-01A corrigé en conséquence.
- Le document TAXO-01 est un épique ; fichiers renommés en `EPIC-TAXO-01-…` et `TAXO-01A-…` ;
  brouillon `TAXO-01-fondation-des-faits.md` supprimé.

## Banc d'essai TAKIBO

Le développement se fait sur de petits projets de test contrôlés, et la valeur se valide sur
TAKIBO. Les cas ci-dessous ont été vérifiés dans le code les 12 et 13 septembre 2026 (commit `80eb595`).

### Cas 1 : anti-faux-positif (critère bloquant de TAXO-05)

`POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients` n'a aucune annotation de sécurité, mais il
est protégé par quatre couches :

```text
SecurityConfig.java:83               /api/v1/** → PolicyBasedAuthorizationManager
PolicyBasedAuthorizationManager:101  → PolicyEvaluator.evaluate
PolicyEvaluator.java:285-324         POL_OAUTH_CLIENT_ADMIN_REQUIRED
OAuthClientController.java:25, :79   @RequireActiveSpace, spaceBoundaryGuard.assertTokenMatches
```

Critère : aucun endpoint couvert par une règle d'URL `.access(...)` n'est signalé comme non protégé.
Résultat attendu : `MATCHED_BY route-pattern:/api/v1/**` puis
`PROTECTED_BY PolicyBasedAuthorizationManager` (`INFERRED`), et `PolicyEvaluator` en
`NOT_INTERPRETED`.

### Cas 2 : changement de sécurité sans contrôleur (TAXO-PROJ-PR-01)

Le commit `4523e46` (PR #37, 2026-07-19, « make TMS routes default deny ») modifie
`PolicyEvaluator.java`, `PolicyBasedAuthorizationManager.java` et leurs tests, sans toucher aucun
contrôleur. Attendu entre `4523e46^` et `4523e46` : mécanisme d'autorisation modifié, endpoints
potentiellement concernés (`INFERRED`), avec fichiers et commits.

### Cas 3 : projection de flux (TAXO-PROJ-API-01, 01I)

`POST /api/v1/orgs/{orgId}/spaces` suit la chaîne réelle `SpaceController#createSpace`,
`SpaceApplicationService#createSpace`, `SpaceRegistrationOrchestrator#registerSpace`, puis deux
branches : `SpaceRepository#save` (vers la table `spaces`) et `SpaceEventPublisherPort#publish`
(vers l'outbox, où la suite n'est pas établie).

Pièges à couvrir :

- les appels passent par des interfaces, donc le lien vers l'implémentation est `DISPATCHES_TO`
  (`INFERRED`) ;
- `OrgBoundaryFilter` est dans la chaîne de filtres mais ne s'applique pas à cette route
  (`OrgBoundaryFilter.java:28-35`, `:57`) : la sécurité se calcule endpoint par endpoint ;
- la projection doit s'arrêter sur une fin « non interprétée » ou « non analysée » là où la suite
  n'est pas établie ; sans évaluateur Data, la table `spaces` n'apparaît pas.

### Cas 4 : deux surfaces pour un même concept (TAXO-04)

`POST /api/spaces/{spaceId}/users`, route historique (`UserController.java:30`), et
`/api/v1/orgs/{orgCode}/spaces/{spaceCode}/users`, route lisible (`ReadableUserController.java:46`).
La résolution d'une cible doit renvoyer des candidats, pas un choix.

### Cas 5 : code de debug dans `src/main` (TAXO-05)

`SecurityAccessTestController` porte 7 `@PreAuthorize` sous `/debug/secure/**`, dans `src/main`.
Taxo relève le fait. La question « est-il actif en production ? » est une conclusion à ne pas simuler.

### Cas 6 : fins de ligne et empreintes (01A, 01C)

`OAuthClientController.java` contient 0 octet CR dans le commit `80eb595` et 89 dans le dossier de
travail Windows (`core.autocrlf=true`). Critère : le même code produit la même empreinte, qu'il soit
lu depuis le commit ou depuis le dossier de travail. Empreintes de référence dans la fixture de
TAXO-01A (T19).
