# Plan Taxo

Mise à jour : 2026-09-19 (repositionnement : intelligence logicielle, correction des défauts mesurés)
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

## NOW : corriger les défauts mesurés

**Repositionné le 2026-09-19.** Taxo n'est plus présenté comme une mémoire pour agents IA : quatre
bancs, consignés dans le [journal](../../bench/JOURNAL-2026-09-19.md), n'ont pas démontré de gain
d'exactitude avec les configurations testées. Une approche nouvelle reste mesurable, à exactitude
toujours mesurée. Taxo est un **moteur d'intelligence logicielle** : il documente un logiciel — ses
modules, ses unités déployables, ses dépendances, ses surfaces — et ce qui change entre deux états,
pour des humains et pour des pages.

Le code est conservé. Ce qui change, c'est ce qu'on en dit, et l'ordre des corrections. La file est
[DEFAUTS-MESURES.md](DEFAUTS-MESURES.md) ; chaque entrée vient d'une mesure du 2026-09-19 :

| # | Défaut | Pourquoi dans cet ordre |
| --- | --- | --- |
| **D1** | l'unité déployable est ignorée | quatre questions sur douze en dépendaient, et c'est la première information de la page Architecture |
| **D2** | le silence du parsing : ce qui n'est pas compris ne produit rien | transforme une lacune en affirmation — l'inventaire annonçait 45 endpoints, il y en a 47 |
| **D3** | `OUT_OF_SCOPE` déclaré sans avoir cherché | une absence n'est vraie que relativement à ce qui a été inspecté |
| **D5** | `anyRequest()` non modélisé | six routes sur 45 sans conclusion |
| **D6** | vocabulaire de l'`ABSENCE` trop catégorique | « ne s'applique pas » n'est pas « monté mais inerte sur ce chemin » |
| **D7** | les faits bruts ne passent pas à l'échelle | 248 000 tokens contre 2 767 pour la même information |
| **D4** | le diff se tait sur les vrais changements de protection | à rouvrir **après** D1, D2 et D5, dont il dépend |

Corpus visé, mesuré le 2026-09-19 : 24 dépôts Git, et **7 projets de code sans aucun suivi Git** —
DOCUMENTUM (534 fichiers), UdeS (798), TKM BUREAU (226), import-massif (192), jeux-video (116),
Demo (41), CROCHET (22). Majoritairement Gradle/Java, puis Node, un cas .NET.

Deux décisions restent ouvertes, et elles conditionnent la suite : accepter ou non un dossier sans
dépôt Git — aujourd'hui refusé par `NOT_A_GIT_REPOSITORY`, ce qui exclut ces sept projets — et ce
que « générique » recouvre exactement, au vu de ce corpus.

**Feuille de route actuelle** : la section [« Élargissement : Taxo au-delà de Spring »](#élargissement--taxo-au-delà-de-spring).
Elle donne l'ordre des jalons (E1 à E4) et la correspondance avec les défauts D1 à D7. Les tables
qui suivent (épique, NEXT) décrivent la trajectoire planifiée avant le gel du 2026-09-19. Elles sont
conservées comme mémoire du projet et comme description des récits, pas comme file d'attente.

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
| **01H** Validité et invalidation | `STALE`, `REVALIDATION_REQUIRED` | T7 | les premiers faits `INFERRED` (`MATCHED_BY`, `PROTECTED_BY` de TAXO-05) ; `DISPATCHES_TO` est suspendu (ADR 0011) |
| **01I** Voisinage et projectabilité | voisinage borné d'une entité, frontière déclarée, trois fins de parcours ([récit](TAXO-01I-voisinage-et-projectabilite.md)) | T6, T12 | après TAXO-ID-01, sur les faits existants ; TAXO-PROJ-API-01 le réutilise |

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
| **TAXO-03** Java Analyzer | analyseur de langage : types, méthodes, annotations et leurs valeurs, constantes, supertypes, chaînes d'appels. **Ne connaît pas le concept d'endpoint.** Décidé par l'ADR 0003 : **tree-sitter, dans le processus Python, sans JVM**, sources seules. Première tranche livrée avec TAXO-04. Suite : identité par signature (TAXO-ID-01), puis appels selon l'ADR 0011 (`CALLS` déduit, fragment borné ; `DISPATCHES_TO` suspendu jusqu'à l'ancrage sur le site) |
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

Critères du spike TAXO-03 (vérifiables sur TAKIBO). Rédigés le 2026-09-13, ils restent des cas
d'essai ; les critères 3 et 4 relèvent désormais de l'ADR 0011 (appels, fragment borné) :

1. Le Java Analyzer fournit les informations et résolutions nécessaires pour permettre au Spring API
   Evaluator de reconstruire les endpoints Spring du banc TAKIBO : annotations de classe et de
   méthode avec leurs valeurs résolues, y compris un `@PostMapping` sans argument. La
   reconstruction elle-même est vérifiée par un prototype jetable qui n'appartient pas au Java
   Analyzer.
2. `TechnicalRole.ORG_OWNER.code()` (`PolicyEvaluator.java:396`) résolu en `"R_ORG_OWNER"`, ou
   déclaré `NOT_INTERPRETED`.
3. `spaceRepository.save` mène à la déclaration `SpaceRepository#save` (`CALLS`, déduit) ; le lien vers
   `SpaceRepositoryAdapter` reste un candidat tant que le dispatch n'est pas ancré sur le site.
4. `@RequireActiveSpace` résolu vers son nom complet, alors qu'il vient d'un autre module.
5. Aucun Gradle exécuté, aucun jar lu, temps d'analyse mesuré.
6. Tout échec de résolution produit un fait `COVERAGE` ; l'analyse ne s'arrête jamais en entier.

Spring sert de cas de test difficile au spike. Le Java Analyzer ne devient pas pour autant un
analyseur Spring.

## Élargissement : Taxo au-delà de Spring

Spring est le premier cas difficile, pas le périmètre de Taxo. Un **lecteur de langage** donne la
structure de tout code, maison compris : types, fonctions, imports, appels. Un **lecteur de
framework** y ajoute un sens particulier : routes, règles de sécurité. L'élargissement a des jalons
aussi concrets que la sécurité Spring. Chacun :
- se valide sur un projet **sans Spring** ;
- a une démonstration et des critères d'acceptation ;
- déclare ce qu'il ne lit pas.

| Jalon | Résultat | Validé sur | Tranche |
| --- | --- | --- | --- |
| **E1** Structure et unités déployables | modules et leur graphe, depuis `settings.gradle`, `build.gradle`, `pom.xml`, `package.json` (workspaces), `pyproject.toml` ; langage de chaque module ; unités déployables (point d'entrée d'application, `Dockerfile`, service `compose`) ; chaque fichier rattaché à son module | Taxo lui-même (Python et TypeScript, `compose.yaml`), puis TAKIBO (deux applications Spring Boot) | défaut **D1** de la PR #13. TAXO-05 ne fait que le **neutraliser** dans le cas détecté : plusieurs points d'entrée Spring Boot, aucune route rattachée. E1 le **résout** : il établit, pour chaque route, l'application qui l'expose et les chaînes de filtres que cette application charge. C'est son critère d'acceptation explicite |
| **E2** Dépendances | dépendances déclarées : entre modules du dépôt, et vers l'extérieur avec leur version déclarée. Ce que le fichier de build ne déclare pas (version calculée par un plugin, catalogue non lu) est `NOT_INTERPRETED` | Taxo lui-même, puis un dépôt Node | relation de dépendance à ajouter au vocabulaire v1 : amendement de l'ADR 0002 |
| **E3** Changements de structure entre deux commits | module ajouté ou retiré, dépendance ajoutée, retirée ou changée de version, unité déployable modifiée, avec preuves | l'historique de Taxo lui-même | l'impact d'un commit est déjà générique : aucun consommateur ne change |
| **E4** Deuxième langage | un lecteur Python (tree-sitter) : modules, classes, fonctions, imports entre modules du dépôt. Même contrat, même identité syntaxique, mêmes règles de non-interprétation. Aucun évaluateur de framework ne connaît un autre langage | le backend de Taxo | éprouve le socle hors de Java : ce qui ne tient pas dans le contrat devient un ADR, pas une exception |

Correspondance avec les défauts mesurés de la PR #13 :

| Défaut | Où il est traité |
| --- | --- |
| **D1** unité déployable | neutralisé par TAXO-05 (#45) dans le cas détecté ; résolu par **E1** |
| **D2** silence du parsing | en partie : `taxo.spring-api` déclare ses mappings non résolus et ses héritages non suivis. Une construction d'endpoint non modélisée (`@Endpoint` d'actuator) reste silencieuse : récit à ouvrir avec E1 |
| **D3** `OUT_OF_SCOPE` sans avoir cherché | produit par le POC `authchain`, pas par les évaluateurs livrés ; règle à reprendre dans tout évaluateur qui déclarera `OUT_OF_SCOPE` |
| **D4** diff muet sur la protection | après E1 : l'impact compare déjà les faits de TAXO-05 entre parent et commit |
| **D5** `anyRequest()` | lu par TAXO-05 (#45) |
| **D6** `ABSENCE` trop catégorique | produit par le POC, pas par les évaluateurs livrés ; à respecter quand une `ABSENCE` sera produite |
| **D7** faits bruts trop gros | la Tuile compacte (TAXO-01I), mesurée par l'essai A/B/C |

Ordre proposé, **à décider** :

1. #45 ;
2. TAXO-ID-01 ;
3. **E1** ;
4. TAXO-01I ;
5. **E2**, puis **E3** ;
6. décision de l'ADR 0011 et premières liaisons Java ;
7. **E4** ;
8. essai A/B/C.

Placer E1 avant TAXO-01I est un **choix de priorité**, pas une dépendance technique. Une Tuile peut
déjà montrer les faits existants et leurs limites ; elle ne crée aucun rattachement entre
applications. E1 passe d'abord parce qu'il donne vite une capacité utile au-delà de Spring. Il passe
aussi avant les appels pour la même raison.

Le positionnement de la PR #13 (moteur d'intelligence logicielle, bancs du 2026-09-19) conditionne
l'essai A/B/C. Ces bancs n'ont pas démontré de gain d'exactitude avec les configurations testées :
cela justifie le repositionnement, sans interdire de mesurer une approche nouvelle. L'essai mesure
donc une hypothèse plus étroite : une Tuile compacte avec sa frontière (défaut D7) coûte moins
qu'une exploration par extraits. La qualité est toujours mesurée : exactitude, omissions, fausses
affirmations, abstentions correctes. Un gain de tokens obtenu au prix de la qualité est un échec. Si
l'essai ne confirme pas l'hypothèse, la valeur de Taxo reste celle de la documentation vérifiable, et
c'est elle qu'on présente.

## LATER

Data, Documentation Drift, autres diagrammes, Configuration, Frontend, Tests, CI/CD, inventaire
Documentation, Business Flows, Release notes, source Sonar, source Runtime.

Les récits du document de vision restent la description de ces capacités, pas un backlog. Structure,
Dependencies, Deployment et Impact Analysis ont quitté cette liste : ils sont les jalons E1 à E3.

## Décisions prises

**2026-09-27 (architecture de la Maille, ADR 0011 en projet)**

- La Maille existante est rendue navigable avant d'étendre la couverture Java. Ordre :
  1. TAXO-ID-01, identité des méthodes par signature syntaxique normalisée, avec sa migration ;
  2. TAXO-01I, voisinage borné sur les faits existants, avec frontière en trois natures ;
  3. décision de l'ADR 0011 : `CALLS` déduit, `DISPATCHES_TO` suspendu jusqu'à l'ancrage sur le site,
     candidats hors des arêtes, preuves avec colonne, propriétaire et rôle ;
  4. premières liaisons Java, fragment borné, avec prémisses et diagnostic par forme ;
  5. essai A/B/C.

  Cet ordre est à croiser avec les jalons d'élargissement E1 à E4 (section « Élargissement »).
- L'essai A/B/C compare Taxo à un agent qui cherche et lit des extraits, pas des fichiers entiers.
  Questions, réponses attendues et cas où `NOT_PROVEN` est la bonne réponse sont fixés avant l'essai.
  Le « facteur 8 à 10 » de l'ADR 0005 reste attaché au prototype historique, mesuré contre des
  fichiers entiers : il ne prédit pas ce gain.
- Ce qui existe (couvertures, `not_sent`, versions de producteur et de catalogue, verdicts) est
  réutilisé, pas reconstruit.

**2026-09-27 (ADR 0010)**

- Première tranche de TAXO-05 : règles d'URL `authorizeHttpRequests` en faits (`PERMITS_ALL`,
  `AUTHORIZED_BY`), rattachées aux endpoints par déduction (`MATCHED_BY`, puis `PROTECTED_BY`).
- Critère anti-faux-positif : une conclusion n'est produite que si elle vaut pour toute requête de la
  route ; sinon l'endpoint est `NOT_INTERPRETED`. Sécurité de méthode et mécanismes maison déclarés.
- Plusieurs applications Spring Boot dans le dépôt : aucune route rattachée (D1 neutralisé, résolu
  par E1).
- Une confirmation de Minia fondée sur un fait `INFERRED` est dite « par déduction », prémisses visibles.

**2026-09-26 (ADR 0003)**

- L'analyseur Java lit la syntaxe avec tree-sitter, dans le processus Python, au lieu de JavaParser dans
  une JVM séparée : ni runtime ni build de plus, et une évaluation assez rapide pour être rejouée à
  chaque comparaison de commits.
- Première tranche de TAXO-03 et TAXO-04 : endpoints Spring MVC (`HANDLED_BY`), preuves à la ligne,
  zones non résolues déclarées `NOT_INTERPRETED`. Appels, `DISPATCHES_TO` et 01H restent à venir.

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

- les appels passent par des interfaces : `CALLS` vise la déclaration d'interface, et le lien vers
  l'implémentation reste un candidat jusqu'à un `DISPATCHES_TO` ancré sur le site (ADR 0011) ;
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
