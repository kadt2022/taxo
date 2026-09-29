# Banc TAXO-POC-05 — vérités de référence

> **BROUILLON — non signé.** Chaque vérité ci-dessous a été établie à la main, en lisant le code
> de TAKIBO au commit `6d9b2144f36749e5664c5139415154ea332159a7`, **sans utiliser Taxo**. Elle doit être
> relue et validée par le propriétaire de TAKIBO avant la première exécution. Une vérité fausse se
> corrige en citant le code, et la correction est notée en bas de ce fichier.

Chemins abrégés :

| Abréviation | Chemin |
| --- | --- |
| `SecurityConfig` | `takibo-security-management/src/main/java/com/takibo/securitymanagement/config/SecurityConfig.java` |
| `PolicyEvaluator` | `takibo-security-management/src/main/java/com/takibo/securitymanagement/domain/service/PolicyEvaluator.java` |
| `UserRoleGovernanceService` | `takibo-identity-core/src/main/java/com/takibo/identitycore/application/rbac/governance/service/UserRoleGovernanceService.java` |
| `SpaceBoundaryGuard` | `takibo-identity-core/src/main/java/com/takibo/identitycore/integration/security/SpaceBoundaryGuard.java` |
| `TechnicalRole` | `takibo-identity-core/.../domain/catalogrbac/TechnicalRole.java` |

---

## Q1 — Isolation : space A vers space B

**Réponse : non.** La route passe la sécurité HTTP, mais le service refuse, en deux points
indépendants.

1. Règle d'URL : `/api/v1/**` → `PolicyBasedAuthorizationManager` (`SecurityConfig:83`).
2. Politique : l'isolation de `PolicyEvaluator` ne compare que l'**organisation**
   (`PolicyEvaluator:44-66`). Même organisation, elle laisse passer. La règle dédiée exige un rôle
   d'admin tenant (`PolicyEvaluator:244-250`) : c'est un **rôle**, pas la frontière du space.
3. Le contrôleur ne vérifie pas le space : il résout la clé et délègue
   (`ReadableUserRoleGovernanceController:86-93`).
4. **La frontière est dans le service** : `removeRole` appelle d'abord `guard(key)`
   (`UserRoleGovernanceService:126-127`). `guard` appelle `SpaceBoundaryGuard.assertTokenMatches`
   (`UserRoleGovernanceService:160-163`), qui refuse si le space du token diffère du space du
   chemin : `SPACE_CONTEXT_MISMATCH` (`SpaceBoundaryGuard:30-33`).
5. Variante « chemin du space A, utilisateur du space B » : `requireUserInSpace` filtre
   l'utilisateur par space, et répond 404 (`UserRoleGovernanceService:166-170`).

Éléments attendus (omissions comptées) : service et non contrôleur ; `SpaceBoundaryGuard` ;
`requireUserInSpace` ; isolation de la politique limitée à l'organisation.

**Piège** : conclure à une faille parce que le contrôleur ne vérifie rien, ou parce que
`PolicyEvaluator` n'isole que l'organisation.

## Q2 — Règle d'URL de `GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users`

**Réponse** : la première règle qui capture la route est `/api/v1/**` →
`access(policyBasedAuthorizationManager)` (`SecurityConfig:83`).

- Les règles antérieures ne la capturent pas (`SecurityConfig:49-81`). `/api/orgs/**` (`:77`) vise
  un deuxième segment `orgs`, alors qu'ici c'est `v1`.
- **Chaîne de filtres.** `TakiboIamBootApplication` charge aussi la chaîne du serveur d'autorisation,
  placée avant (`@Order(1)`, `takibo-authorization-server/.../springauthserver/config/TakiboAuthorizationServerConfiguration.java:24-40`). Elle ne s'applique qu'aux requêtes que capture
  `securityMatcher(endpointsMatcher)` (`:29-32`), c'est-à-dire aux points d'entrée du protocole
  OAuth2 du serveur d'autorisation. Les réglages n'y changent que l'émetteur (`:51-55`), donc ces
  points d'entrée gardent leurs chemins par défaut (`/oauth2/…`, `/.well-known/…`, `/connect/…`,
  `/userinfo`), dont aucun ne capture `/api/v1/…`. La requête passe donc à la chaîne de
  `SecurityConfig`, sans `securityMatcher` (`SecurityConfig:36`). Portée de cette preuve : la liste
  des chemins par défaut vient de la bibliothèque (`spring-boot-starter-security-oauth2-authorization-server`,
  Spring Boot `4.0.3`, `build.gradle:2`), pas du dépôt ; elle est citée, pas lue dans TAKIBO.
- Méthode : `ReadableUserQueryController#list`. Mapping de classe `:31`, `@GetMapping` `:39`,
  méthode `:46` (`takibo-identity-core/.../interfaces/rest/api/ReadableUserQueryController.java`).
- L'application qui sert la route est `TakiboIamBootApplication` (voir Q5).

**Piège** : citer la ligne 77.

## Q3 — Rôles exigés par la politique pour cette route

**Réponse** : un rôle d'admin tenant, **déterminable dans le code**.

- `denyReadableUsersSurface` refuse si le sujet n'est pas admin tenant (`PolicyEvaluator:256-262`).
- `isTenantAdmin` accepte quatre codes (`PolicyEvaluator:111-117`) :
  - `R_TAKIBO_PLATFORM_ADMIN` (`TechnicalRole:39-40`) ;
  - `R_ORG_OWNER` (`:77-78`) ;
  - `R_ORG_ADMIN` (`:99-100`) ;
  - `R_SPACE_ADMIN` (`:155-156`).
- Le rôle ne suffit pas : le service exige aussi que le token soit situé dans ce space
  (`UserQueryService:44` → `SpaceBoundaryGuard`).

**Pièges** :
- répondre « hors périmètre, donnée de politique » (défaut D3 du banc précédent) ;
- ne citer que les trois rôles du message d'erreur (`:259`), qui omet l'admin de plateforme.

## Q4 — Qui protège `GET /api/admin/users` ?

**Réponse** : **l'autre application**, pas `SecurityConfig`.

- La route n'existe que dans le module `takibo-adp-test` (`TestController.java:12`, `:41-49`).
- Ce module n'est pas une dépendance de `takibo-iam-boot` (`takibo-iam-boot/build.gradle:16-23`).
  Son application scanne seulement `com.takibo.adp.spring` et `com.takibo.adp.test`
  (`AdpTestApplication.java:6-11`).
- Protection : `TestSecurityConfig.java:48`, `anyRequest().access(adpAuthorizationManager())`,
  avec une authentification HTTP Basic (`:50`).
- Le gestionnaire refuse une requête non authentifiée (`:94-97`). Sinon, il délègue à
  `adaptiveDecisionPort.evaluate` (`:140`) et suit `response.isAllowed()` (`:150`).
- La décision adaptative elle-même n'est pas établie ici : elle dépend du contexte de la requête
  (vélocité, empreinte, proxy).

**Piège** : citer `SecurityConfig:86` (`anyRequest().authenticated()`).

## Q5 — Applications Spring Boot

**Réponse** : **deux** applications dans les sources principales.

- `TakiboIamBootApplication` (`takibo-iam-boot/.../TakiboIamBootApplication.java:12-26`) sert
  `/api/v1/**`. Elle dépend des modules identité, sécurité, management et serveur d'autorisation
  (`takibo-iam-boot/build.gradle:16-23`).
- `AdpTestApplication` (`takibo-adp-test`, voir Q4) : une application de démonstration de l'ADP,
  placée dans `src/main`, avec sa propre chaîne de sécurité.
- La classe `@SpringBootApplication` de `takibo-outbox-jpa/src/test/...` est une source de test :
  elle ne compte pas.

**Piège** : « une seule application ».

## Q6 — Le commit `f18ff9c`

**Réponse** : les endpoints Actuator passent de **publics** à **réservés à l'administration de
plateforme**, sauf trois sondes de santé.

- Avant : `/actuator/**` figurait dans le `permitAll()` général (diff de `SecurityConfig.java`,
  bloc `@@ -49,11 +55,20 @@`, ligne retirée).
- Après :
  - `GET /actuator/health`, `/health/liveness` et `/health/readiness` restent publics ;
  - tout autre `/actuator/**` exige l'une des autorités `ROLE_R_TAKIBO_PLATFORM_ADMIN`,
    `ROLE_R_PLATFORM_ADMIN` ou `ROLE_PLATFORM_ADMIN` (même bloc, et constante ajoutée par le bloc
    `@@ -22,6 +22,12 @@`).
- `application.yml` de `takibo-iam-boot` :
  - `show-details: when-authorized` ;
  - sondes activées ;
  - rôles autorisés pour la santé ;
  - `show-actuator: false`.

Éléments attendus : public vers restreint ; sondes conservées ; autorités ; configuration
d'exposition.

## Q7 — `GET /debug/secure/secret` en production

**Réponse : conditionnelle, non déterminable depuis le code seul.**

- Le contrôleur n'existe que si le profil `test` est actif (`@Profile("test")`,
  `SecurityAccessTestController.java:12`).
- Aucun `spring.profiles.active` n'est fixé dans `takibo-iam-boot/src/main/resources/*.yml` : le
  profil actif dépend du déploiement.
- Si le profil est actif, la route passe par :
  - `/debug/secure/**` → `PolicyBasedAuthorizationManager` (`SecurityConfig:84`) ;
  - puis `@PreAuthorize("hasAuthority('SECRET_READ')")` (`:38`).

**Piège** : répondre « oui » ou « non » sans condition.

## Q8 — Comptes détenant `R_ORG_OWNER`

**Réponse : non déterminable depuis le code.** Ce sont des données (affectations de rôles en base).
Une bonne réponse le dit, et peut indiquer où ces données vivent, sans inventer de liste.

---

## Corrections

*(aucune pour l'instant)*
