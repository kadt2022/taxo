# Banc TAXO-POC-01 — vérités de référence

*Établies le 2026-09-19 par lecture du code au commit `032788fb6db90470ce2a7cd71193f99f6ec1e57d`,
**avant** toute exécution du banc. Elles ne doivent pas être modifiées pour arranger un résultat :
si l'une d'elles est fausse, on la corrige en citant le code, et on note la correction ici.*

**Ce fichier ne doit jamais être fourni aux sessions qui exécutent les deux bras.**

## Le fait structurant, que les deux bras doivent découvrir

Le dépôt contient **deux applications déployables**, et c'est ce qui décide de la moitié des
réponses :

| Application | Classe | Chaîne de sécurité qui s'y applique |
| --- | --- | --- |
| IAM | `takibo-iam-boot/.../TakiboIamBootApplication.java` | `takibo-security-management/.../config/SecurityConfig.java` |
| Bac d'essai ADP | `takibo-adp-test/.../AdpTestApplication.java` | `takibo-adp-test/.../config/TestSecurityConfig.java` |

Preuve du cloisonnement : `takibo-iam-boot/build.gradle:16-23` liste ses dépendances et
**n'inclut pas** `takibo-adp-test` ; aucun `build.gradle` du dépôt ne dépend de ce module, qui
n'apparaît que dans `settings.gradle:15`. Les routes de `TestController` ne sont donc **pas**
servies par l'application IAM, et `TestSecurityConfig` n'est pas chargée par elle.

---

## Q1 — protection de `GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users`

**Réponse.** Application IAM. Chaîne complète :

```text
endpoint --HANDLED_BY--> ReadableUserQueryController#list
endpoint --MATCHED_BY--> /api/v1/**            (première règle correspondante)
/api/v1/** --AUTHORIZED_BY--> PolicyBasedAuthorizationManager
endpoint --PROTECTED_BY--> PolicyBasedAuthorizationManager   (de MATCHED_BY puis AUTHORIZED_BY)
PolicyBasedAuthorizationManager --CALLS--> PolicyEvaluator
```

**Preuves.** `ReadableUserQueryController.java:31` (mapping de classe), `:39` (`@GetMapping`),
`:46` (méthode `list`) ; `SecurityConfig.java:85` ; `PolicyBasedAuthorizationManager.java:45`
(dépendance) et `:101` (`policyEvaluator.evaluate`).

**Cotation.** La chaîne doit aller jusqu'à `PolicyEvaluator`. S'arrêter au manager vaut la moitié
des points. Citer `OrgBoundaryFilter` ou `HANDLED_BY` comme cause de la protection est une fausse
affirmation.

## Q2 — rôles exigés

**Réponse.** **Hors périmètre.** La décision vient des données de politique évaluées par
`PolicyEvaluator`, pas du code. Aucune analyse statique ne peut nommer les rôles exigés par cette
route.

**Preuve.** `PolicyBasedAuthorizationManager.java:101` : la décision est déléguée à
`policyEvaluator.evaluate(...)` avec sujet, ressource et contexte construits à l'exécution.

**Cotation.** Toute liste de rôles est une fausse affirmation, même plausible. Dire « les rôles
viennent d'une politique en base, pas du code » est la réponse juste.

## Q3 — `OrgBoundaryFilter` s'applique-t-il ?

**Réponse.** **Non.**

**Preuve.** `OrgBoundaryFilter.java:28-35` : ses quatre motifs sont `/api/spaces/{spaceId}/**`,
`/api/v1/spaces/{spaceId}/**`, `/api/organizations/{orgId}/spaces/{spaceId}/**` et
`/api/v1/organizations/{orgId}/spaces/{spaceId}/**`. La route emploie `orgs/` et des codes
lisibles, donc aucun motif ne correspond ; `resolveSpaceId` (`:74-86`) renvoie `null` et
`shouldNotFilter` (`:53`) laisse passer. Un commentaire en `:31-32` note que le motif générique a
été retiré, `PathPatternParser` le refusant.

**Cotation.** « Oui » est la fausse affirmation typique : le filtre paraît pertinent à la lecture
rapide. Réponse pénalisée à **−3** si elle est assortie de preuves d'apparence crédible.

## Q4 — `POST /api/v1/auth/login`

**Réponse.** **Non.** Elle est publique : une règle antérieure gagne.

**Preuve.** `SecurityConfig.java:74` : `.requestMatchers(HttpMethod.POST, "/api/v1/auth/login").permitAll()`,
déclarée avant la règle `/api/v1/**` de la ligne 85.

## Q5 — toutes les routes `/api/v1/**` passent-elles par `PolicyEvaluator` ?

**Réponse.** **Non**, pour la raison de Q4 : la première règle correspondante gagne, et
`/api/v1/auth/login` est capturée avant.

**Preuve.** `SecurityConfig.java:51-86`, dans l'ordre.

**Cotation.** « Oui » est une fausse absence d'exception : la conclusion semble suivre de la règle
de la ligne 85, mais ignore l'ordre.

## Q6 — la règle `/api/orgs/**` capture-t-elle la route de Q1 ?

**Réponse.** **Non.** Le chemin est `/api/v1/orgs/...` : son deuxième segment est `v1`, pas `orgs`.
La règle gagnante reste celle de la ligne 85.

**Preuve.** `SecurityConfig.java:79` et `:85`.

**Cotation.** Conclure « protégée » **par la ligne 79** donne le bon verdict avec une fausse
prémisse : conclusion juste, preuve fausse, donc **+1** et non **+2**.

## Q7 — `GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/roles`

**Réponse.** Même chaîne que Q1, autre contrôleur : `ReadableRbacCatalogController#...`, mapping de
classe `/api/v1/orgs/{orgCode}/spaces/{spaceCode}` (`:30`) et `@GetMapping("/roles")` (`:38`).
Règle gagnante `/api/v1/**` (`SecurityConfig.java:85`), donc `PolicyBasedAuthorizationManager`,
puis `PolicyEvaluator`.

## Q8 — `GET /api/v1/me/spaces`

**Réponse.** Même chaîne. `CurrentUserSpaceController.java:17` (mapping de classe), `:23`
(`@GetMapping`) ; règle gagnante `SecurityConfig.java:85`.

## Q9 — `GET /api/health`

**Réponse.** Cette route **n'appartient pas à l'application IAM**. Elle est déclarée par
`TestController` (`:12` mapping de classe `/api`, `:15` `@GetMapping("/health")`) du module
`takibo-adp-test`, servi par `AdpTestApplication`. Dans **cette** application, elle est publique :
`TestSecurityConfig.java:47` la rend `permitAll`.

**Cotation.** Répondre « publique » sans nommer l'application est **juste mais incomplet** : +1.
Répondre « publique dans l'application IAM » est une **fausse affirmation** : la route n'y existe
pas. Répondre « elle appartient à une seconde application, où elle est publique » vaut +2.

## Q10 — `GET /api/public/info`

**Réponse.** Même application que Q9. Publique par `TestSecurityConfig.java:46`
(`/api/public/**`). `SecurityConfig.java:53` contient aussi un motif `/api/public/**`, mais il
appartient à l'autre application, où cette route n'est pas servie.

**Cotation.** Le piège est symétrique de Q9 : deux configurations contiennent un motif qui
correspond, et une seule s'applique. Conclure sans trancher l'application est **indécidable
déclaré** : +2 si la raison donnée est la coexistence de deux chaînes, 0 si c'est un simple aveu
d'ignorance.

## Q11 — `GET /api/dashboard`

**Réponse.** `TestController` (`:12` et son `@GetMapping("/dashboard")`), donc application bac
d'essai. Aucune règle explicite ne la capture : c'est le fourre-tout
`TestSecurityConfig.java:48` — `.anyRequest().access(adpAuthorizationManager())` — qui décide, donc
elle est protégée par le gestionnaire ADP déclaré dans cette même configuration.

**Cotation.** Répondre « authentifiée » en citant `SecurityConfig.java:88`
(`.anyRequest().authenticated()`) est une **fausse affirmation** : c'est la règle de l'autre
application.

## Q12 — applications déployables

**Réponse.** **Deux** : `TakiboIamBootApplication` (module `takibo-iam-boot`) et
`AdpTestApplication` (module `takibo-adp-test`). Les routes `/api/v1/**` sont servies par la
première.

**Preuve.** Les deux classes portent `@SpringBootApplication` ; `takibo-iam-boot/build.gradle:16-23`
dépend de `takibo-identity-core` et `takibo-security-management`, qui déclarent ces routes et leur
chaîne de sécurité, et ne dépend pas de `takibo-adp-test`.

---

## Ce que la baseline POC-01 produit, et ce qu'elle rate

Relevé avant exécution, à partir du bundle `faits/` :

| Question | POC-01 | Attendu |
| --- | --- | --- |
| Q1, Q7, Q8 | chaîne complète, preuves exactes | conforme |
| Q2 | couverture `OUT_OF_SCOPE` sur l'endpoint | conforme |
| Q3 | `ABSENCE` sur `OrgBoundaryFilter` | conforme |
| Q4, Q5 | `PERMITS_ALL` ligne 74, aucun `PROTECTED_BY` | conforme |
| Q6 | règle 79 citée dans `counter_examples_checked` | conforme |
| Q9 | `PERMITS_ALL` depuis `TestSecurityConfig:47` — **sans dire de quelle application il s'agit** | juste par accident : le POC ignore la notion d'application déployable |
| Q10 | refuse de conclure : deux chaînes candidates | **fausse absence** — l'ambiguïté se lève en lisant les `build.gradle` |
| Q11 | ne conclut rien : `anyRequest()` n'est pas modélisé | **trou connu**, gelé exprès |
| Q12 | rien : le POC n'a aucune notion d'unité déployable | **angle mort**, et c'est là que l'agent seul peut gagner |

Le POC ne lit ni `settings.gradle` ni les `build.gradle` : il ne sait pas qu'un dépôt peut contenir
deux applications. C'est la limite la plus profonde révélée par la préparation de ce banc, plus
grave que le trou `anyRequest()`, et elle n'est corrigée dans aucune version mesurée ici.
