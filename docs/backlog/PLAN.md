# Plan Taxo

Mise à jour : 2026-09-13
Références : ADR 0001, ADR 0002, `EPIC-TAXO-01-fondation-memoire-verifiable.md`

## MVP

> Sur un projet Spring Boot, Taxo inventorie le dépôt, découvre les endpoints HTTP, relève leurs
> mécanismes d'autorisation observables et déclare ceux qu'il ne sait pas interpréter. Il rattache
> chaque résultat au code et au commit, et conserve ces faits dans une mémoire versionnée que les
> projections (PR, diagrammes, Ask Taxo, MCP) consomment sans relire le dépôt.

## Vue d'ensemble

```text
ÉPIQUE TAXO-01  Mémoire logicielle vérifiable
      ↓
TAXO-02         Inventory Evaluator
      ↓
TAXO-03         Java Analyzer (spike, puis ADR 0003)
      ↓
TAXO-04         Spring API Evaluator
      ↓
TAXO-05         Spring Security Evaluator      + TAXO-01H
      ↓
PREMIÈRE DÉMO   PR ou diagramme : décision ouverte (voir plus bas)
```

## NOW : épique TAXO-01, Mémoire logicielle vérifiable

Rien d'autre n'est ouvert tant que les récits 01A à 01G ne sont pas terminés.

| Récit | Contenu | Tâches de l'épique | Statut |
| --- | --- | --- | --- |
| **01A** Contrat machine du fait | natures et structures, statuts, validité, identité et occurrence, syntaxe des références, référence d'instantané, preuve et empreinte, vocabulaire v1, règles de cohérence, suite de conformité | T1 | rédigé : `TAXO-01A-contrat-machine-du-fait.md` |
| **01B** Références stables et identité | normalisation des clés, stabilité entre commits, calcul de l'identité stable d'un fait | T2 | à rédiger |
| **01C** Instantané au commit | lecture d'un commit en lecture seule ; mode `WORKING_TREE` marqué, avec empreinte du contenu ; fichiers ignorés par Git exclus | T3 | à rédiger |
| **01D** Exécution d'évaluateur et couverture | identité, version, catalogue, statut technique (`SUCCESS`, `PARTIAL`, `FAILED`, `UNSUPPORTED`), couverture déclarée séparée ; `scanner.py` converti en Inventory v0, premier producteur de faits réels | T4 | à rédiger |
| **01E** Persistance | instantanés, exécutions, faits, occurrences, preuves, couvertures ; `scans.result` n'est plus la source de vérité | T5 | à rédiger |
| **01F** Comparaison et banc Git | introduit, retiré, modifié, inchangé ; « cause possible : évaluateur » ; dépôt de test A/B/C | T8, T11 | à rédiger |
| **01G** API de lecture et vue de vérification | faits par instantané, identité, sujet, objet ou relation ; preuves ; couverture ; évaluateurs exécutés ; comparaison ; liste dans le portail | T9, T10 | à rédiger |

Récits de l'épique placés au moment où ils servent :

| Récit | Contenu | Tâches | À réaliser avec |
| --- | --- | --- | --- |
| **01H** Validité et invalidation | `STALE`, `REVALIDATION_REQUIRED` | T7 | TAXO-05, premier producteur de faits `INFERRED` |
| **01I** Voisinage et projectabilité | voisinage d'une entité, reconstruction d'un flux depuis les seuls faits, trois fins de parcours | T6, T12 | la première projection de diagramme |

```text
01A Contrat ──► 01B Références ──┐
                                 ├──► 01D Exécution ──► 01E Persistance ──► 01F Comparaison ──► 01G API + vue
01C Instantané ──────────────────┘
```

01C est indépendant de 01A et 01B, et peut avancer en parallèle.

**Première démo possible après 01F** : Taxo compare deux commits, dit ce qui a changé dans
l'inventaire avec les preuves, et distingue une évolution du logiciel d'une évolution de Taxo.

## NEXT

| Récit | Résultat attendu |
| --- | --- |
| **TAXO-02** Inventory Evaluator | inventaire complet sous forme de faits ; lecture de Gradle (`build.gradle`, `settings.gradle`), aujourd'hui ignoré par `scanner.py` alors que TAKIBO est un projet Gradle |
| **TAXO-03** Java Analyzer | spike de deux jours sur TAKIBO, puis ADR 0003 ; recommandation à confirmer : JavaParser + JavaSymbolSolver, analyse des sources seules, processus JVM séparé qui émet des faits et passe la suite de conformité de 01A |
| **TAXO-04** Spring API Evaluator | endpoints de TAKIBO avec chemin complet et `HANDLED_BY` |
| **TAXO-05** Spring Security Evaluator | règles d'URL, annotations, appels de gardes ; mécanismes maison déclarés `NOT_INTERPRETED` ; critère anti-faux-positif bloquant |
| **Première projection** | PR ou diagramme d'API (décision 1) |

Critères du spike TAXO-03 (vérifiables sur TAKIBO) :

1. Tous les endpoints relevés avec leur chemin complet, y compris un `@PostMapping` sans argument.
2. `TechnicalRole.ORG_OWNER.code()` (`PolicyEvaluator.java:396`) résolu en `"R_ORG_OWNER"`, ou
   déclaré `NOT_INTERPRETED`.
3. `spaceRepository.save` mène à `SpaceRepository`, puis à `SpaceRepositoryAdapter` (`IMPLEMENTS`).
4. `@RequireActiveSpace` résolu vers son nom complet, alors qu'il vient d'un autre module.
5. Aucun Gradle exécuté, aucun jar lu, temps d'analyse mesuré.
6. Tout échec de résolution produit un fait `COVERAGE` ; l'analyse ne s'arrête jamais en entier.

## LATER

Dependencies, Data, Documentation Drift, Diagrams, Impact Analysis, MCP, Ask Taxo, Structure,
Configuration, Frontend, Tests, CI/CD, Deployment, inventaire Documentation, Business Flows,
Release notes, source Sonar, source Runtime.

Les 17 récits du document de vision restent la description de ces capacités, pas un backlog.

## Décision ouverte

**Première démo : commentaire de PR ou diagramme de flux d'un endpoint ?**

- **Commentaire de PR.** Sur une PR de TAKIBO, Taxo commente les endpoints ajoutés, modifiés ou
  supprimés, et les changements du mécanisme d'autorisation, avec preuves et commits (cas 2).
  Besoin : 01A à 01G, TAXO-02 à 05. Montre ce qu'un agent ne sait pas faire : dire ce qui a changé
  entre deux commits, avec preuves et de façon reproductible. **Recommandation actuelle.**
- **Diagramme de flux d'un endpoint.** Pour un endpoint choisi (cas 3 :
  `POST /api/v1/orgs/{orgId}/spaces`), Taxo dessine la chaîne contrôleur → service → orchestrateur
  → dépôt, avec le statut de chaque élément et la fin de chaque branche (établie, non interprétée,
  non analysée). Besoin : 01A à 01G, 01I, TAXO-02 à 04, et un analyseur Java qui suit les appels
  (`CALLS`, `IMPLEMENTS`, `DISPATCHES_TO`) au-delà du contrôleur. Sans évaluateur Data, la branche
  s'arrête au dépôt avec une fin « non analysée » : la table `spaces` n'apparaît pas. La sécurité se
  superpose après TAXO-05. Plus parlant pour un nouvel arrivant, mais un agent sait déjà approcher
  ce résultat.

Les récits 01A à 01G servent aux deux : la décision ne bloque pas l'épique.

## Décisions prises

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

### Cas 2 : changement de sécurité sans contrôleur (démo PR)

Le commit `4523e46` (PR #37, 2026-07-19, « make TMS routes default deny ») modifie
`PolicyEvaluator.java`, `PolicyBasedAuthorizationManager.java` et leurs tests, sans toucher aucun
contrôleur. Attendu entre `4523e46^` et `4523e46` : mécanisme d'autorisation modifié, endpoints
potentiellement concernés (`INFERRED`), avec fichiers et commits.

### Cas 3 : projection de flux (démo diagramme, 01I)

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
  n'est pas établie.

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
TAXO-01A (T18).
