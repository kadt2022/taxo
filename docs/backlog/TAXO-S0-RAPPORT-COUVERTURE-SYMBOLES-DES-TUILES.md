# Rapport S0 — Couverture des symboles des tuiles actuelles (TAKIBO)

**Statut :** MESURÉ — référence avant tout changement des tuiles
**Date :** 2026-10-18 · **Lot :** S0 du récit « TAXO — Contrat de suffisance structurelle des tuiles » · **Auteur :** le monstre des mers
**Portée :** aucune modification des tuiles, du protocole ni des analyseurs ; une mesure, reproductible, et ses limites.

## 1. Ce qui a été mesuré

Pour 25 méthodes de TAKIBO (`D:\Takibu\Takibo-IAM`, analyse du dernier commit), la tuile **actuelle** de Minia (`paths._tile` :
méthode, en-tête de classe, champs utilisés, en-tête des types joints) est construite, puis chaque nom utilisé par la méthode est
rangé dans un des trois états :

- **Porté** : la tuile le porte (déclaré dans la méthode, déclaration du champ, en-tête du type) ;
- **Connu, non porté** : Taxo le connaît (appel relié par `CALLS`, type du projet, méthode de la classe) mais la tuile ne le porte
  pas (signature ou en-tête absents) ;
- **Non résolu** : ni la tuile ni les faits ne l'identifient.

Les « symboles pertinents » viennent d'une analyse lexicale indépendante de l'évaluateur (outil `backend/scripts/tile_symbol_coverage.py`,
testé par `tests/test_tile_symbol_coverage.py`). **Couverture stricte** = portés ÷ symboles. **Avec liens** = (portés + connus non
portés) ÷ symboles.

Reproduire : `python scripts/tile_symbol_coverage.py <dépôt> --limit 25` depuis `backend`.

## 2. Résultat

*Chiffres recalculés après les remarques de revue de la PR 175 : l'outil ne compte plus le nom écrit d'un constructeur comme un symbole
(414 symboles au lieu de 416), ne prend plus un argument d'appel pour une déclaration et lit chaînes et commentaires en une passe.*

414 symboles dans 20 tuiles construites (5 des 25 méthodes retenues n'ont pas de tuile : `NOT_AVAILABLE`, cause non détaillée par l'outil).

| Mesure | Valeur |
|---|---|
| Couverture stricte (portés ÷ symboles) | **29,5 %** (122 sur 414) |
| Couverture avec les liens connus de Taxo | **42,8 %** (177 sur 414) |
| Non résolus | 237 (57 %) |

Le critère A1 du récit (tous les symboles identifiés ou déclarés non résolus avec cause) **échoue aujourd'hui** : les 237 non
résolus ne sont pas déclarés un par un.

| Méthode | Symboles | Portés | Connus, non portés | Non résolus | Couverture stricte | Avec liens | Octets |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `PkceEnforcementFilter.doFilterInternal` | 37 | 11 | 7 | 19 | 30 % | 49 % | 2 113 |
| `TenantResolutionFilter.doFilterInternal` | 37 | 10 | 13 | 14 | 27 % | 62 % | 3 773 |
| `PolicyBasedAuthorizationManager.authorize` | 95 | 30 | 17 | 48 | 32 % | 49 % | 4 969 |
| `TakibuAuditUserContextFilter.doFilterInternal` | 17 | 5 | 1 | 11 | 29 % | 35 % | 776 |
| `JwtAuthenticationFilter.doFilterInternal` | 58 | 21 | 4 | 33 | 36 % | 43 % | 2 486 |
| `BoundaryMembershipService.assertActorInSpaceOrg` | 39 | 8 | 8 | 23 | 21 % | 41 % | 2 143 |
| `OrgBoundaryFilter.doFilterInternal` | 23 | 6 | 2 | 15 | 26 % | 35 % | 770 |
| `AdaptiveDecisionPort.evaluate` | 3 | 3 | 0 | 0 | 100 % | 100 % | 104 |
| `AuditEventStore.healthCheck` | 2 | 1 | 0 | 1 | 50 % | 50 % | 127 |
| `ResolvedOAuthClient.immutable` | 5 | 1 | 0 | 4 | 20 % | 20 % | 827 |
| `JpaSigningKeyRepository.activateFirstIssuer` | 8 | 3 | 1 | 4 | 38 % | 50 % | 463 |
| `TakiboTokenClaims.<init>` | 0 | 0 | 0 | 0 | 100 % | 100 % | 87 |
| `TechnicalRole.permissions` | 4 | 1 | 0 | 3 | 25 % | 25 % | 143 |
| `GovernanceRoleAssignmentRepository.findAssignedTechnicalRoleCodes` | 6 | 3 | 0 | 3 | 50 % | 50 % | 153 |
| `RoleRepositoryAdapter.findBySpaceIdAndCode` | 13 | 4 | 1 | 8 | 31 % | 38 % | 352 |
| `JpaRoleAssignmentRepository.deleteOrgLevelAssignment` | 8 | 3 | 0 | 5 | 38 % | 38 % | 572 |
| `SlugNormalizer.normalize` | 22 | 2 | 0 | 20 | 9 % | 9 % | 668 |
| `SpaceEntity.updateStatus` | 9 | 3 | 0 | 6 | 33 % | 33 % | 259 |
| `MessageAction.<init>` | 12 | 1 | 1 | 10 | 8 % | 17 % | 415 |
| `OutboxMessageClaimRepositoryImpl.claimRunnable` | 16 | 6 | 0 | 10 | 38 % | 38 % | 1 485 |

## 3. Ce que contiennent les 237 non résolus

| Nature | Symboles | Part |
|---|---|---|
| Membres et appels (`warn`, `map`, `doFilter`, `getRequestURI`…) | 145 | 61 % |
| Types qu'un **import simple** désigne dans le fichier | 63 | 27 % |
| Types du paquet `java.lang` (`String`, `Override`, `IllegalArgumentException`…) | 28 | 12 % |
| Autre (même paquet, inconnu ou externe sans import) | 1 | < 1 % |

**Lecture.** Sur les 92 types non résolus, 63 sont désignés par un import simple du fichier et 28 sont des types de `java.lang`, visibles
sans import : **les imports n'identifient que les 63 premiers** ; les 28 autres relèvent d'une règle du langage. Avec les 63, la couverture
identifiée monterait à **44,7 %** ((122 + 63) ÷ 414) et la couverture avec liens à **58,0 %** ; avec la règle du langage en plus, à
51 % et 65 % au plus (estimations, à confirmer par S3). Les 145 membres et appels restent : ce sont, pour la plupart, des appels sur des
types externes (journalisation, API de Spring et du JDK). Les identifier demande de typer le receveur et de classer la dépendance
« hors du projet » (règle `frontier-classification/2`, lot S6 et § 3.5 du récit).

Noms non résolus les plus fréquents : `String` (12 méthodes), `Override` (9), `HttpServletRequest` (6), `HttpServletResponse` (5),
`FilterChain` (5), `ServletException` (5), `IOException` (5), `doFilter` (5), `log` (4, champ généré par Lombok), `warn` (4).

## 4. Limites de la mesure

- **Analyse lexicale approchée.** Elle ne comprend pas Java. Biais connus : un nom de type tout en majuscules (`UUID`, 5 cas) est
  rangé comme constante et donc compté parmi les « membres » ; `log` (champ généré par `@Slf4j`) est compté comme champ non
  résolu ; une variable de type d'une lettre est ignorée.
- **« Connu, non porté » se fonde sur le nom simple** d'un appel relié par `CALLS`, pas sur la surcharge exacte.
- **Échantillon déterministe, non aléatoire** : 25 méthodes (les trois étudiées, puis des méthodes régulièrement espacées), 20 tuiles.
  Un seul projet et un seul commit : ces valeurs décrivent cette exécution, pas Taxo en général.
- **La durée de l'analyse n'est pas un résultat de ce rapport** : elle a varié de 47 à 190 secondes selon l'exécution et la mise
  en place sur la même machine, sans cause établie.
- La fidélité du code restitué (pièce coupée sur une ligne vide, plages de lignes) n'est pas mesurée ici ; elle fait l'objet du critère A4.

## 5. Ce que S0 dit des lots suivants

1. **S3 (imports)** est le gain le plus net et le moins coûteux : il identifie les 63 types qu'un import simple désigne ; les
   28 types de `java.lang` demandent une règle du langage, pas un import.
2. **Les membres et appels sur types externes (145)** forment la plus grande part restante : ils dépendent de la classification
   « hors du projet » et du typage du receveur, pas des champs.
3. La couverture des **champs** et des **champs hérités** (S2) n'est pas mesurée séparément ici : les champs non résolus sont inclus
   dans « membres et appels » ou dans le rôle champ. Une mesure dédiée est à ajouter avant S2.

Chaque lot suivant exige l'autorisation du Capitaine Pi, après présentation de ces résultats.
