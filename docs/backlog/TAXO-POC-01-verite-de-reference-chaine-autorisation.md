# TAXO-POC-01 — Vérité de référence : une chaîne d'autorisation TAKIBO

Statut : vérité de référence écrite **avant** tout évaluateur, le 2026-09-17, pour servir d'étalon au
POC et au benchmark. Elle ne doit pas être modifiée pour faire passer un évaluateur : si elle est
fausse, on corrige en citant le code, et on note la correction ici.

Source de vérité : le code de TAKIBO au commit `032788fb6db90470ce2a7cd71193f99f6ec1e57d`. Les
relations, natures et statuts suivent l'ADR 0002 et le contrat TAXO-01A.

## Objectif

Établir, pour **une seule route réelle**, la chaîne complète qui mène à `PolicyEvaluator`, avec pour
chaque fait sa nature, son statut, sa preuve et, pour les inférences, ses prémisses. Puis déclarer
honnêtement ce qui reste hors de portée d'une analyse statique.

## Route retenue

```text
endpoint:GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users
```

Choisie parce qu'elle réunit les trois difficultés qui rendent le fait cher : l'ordre des règles de
sécurité décide du résultat, un filtre d'apparence évidente ne s'y applique pas, et la règle
effective d'autorisation est une donnée, pas du code.

## Faits attendus

| # | Fait | Nature | Statut | Preuve |
| --- | --- | --- | --- | --- |
| F1 | `endpoint:GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users` **HANDLED_BY** `symbol:ReadableUserQueryController#list` | ASSERTION | OBSERVED | `takibo-identity-core/.../ReadableUserQueryController.java:31` (mapping de classe), `:39` (`@GetMapping`), `:46` (méthode `list`) |
| F2 | `route-pattern:/api/v1/**` **AUTHORIZED_BY** `symbol:PolicyBasedAuthorizationManager` | ASSERTION | OBSERVED | `takibo-security-management/.../config/SecurityConfig.java:85` |
| F3 | `endpoint:GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users` **MATCHED_BY** `route-pattern:/api/v1/**` | ASSERTION | INFERRED | prémisses : les règles `SecurityConfig.java:51-86` dans leur ordre ; règle : première correspondance gagnante |
| F4 | `endpoint:GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users` **PROTECTED_BY** `symbol:PolicyBasedAuthorizationManager` | ASSERTION | INFERRED | prémisses : F3 puis F2 — jamais F1 |
| F5 | `symbol:PolicyBasedAuthorizationManager` **CALLS** `symbol:PolicyEvaluator` | ASSERTION | OBSERVED | `takibo-security-management/.../infrastructure/adp/PolicyBasedAuthorizationManager.java:45` (dépendance), `:101` (appel `policyEvaluator.evaluate`) |

F4 doit exposer ses prémisses, pas seulement son résultat : c'est ce qui permet d'expliquer
*pourquoi* la route est protégée, étape par étape.

## Hors périmètre déclaré

Ces limites doivent être **produites** par l'évaluateur, pas seulement écrites ici.

- **La décision d'autorisation elle-même.** `PolicyEvaluator` tranche à partir des données de
  politique. Aucune analyse statique ne peut dire quels rôles cette route exige. La chaîne s'arrête à
  F5 et le déclare.
- **Les règles antérieures non modélisées.** Si l'évaluateur ne sait pas interpréter une des règles
  des lignes 51 à 86, il ne peut pas conclure sur la première correspondance : il doit produire une
  couverture, pas une inférence.
- **L'exécution.** Tout ce qui dépend de la requête réelle (paramètre `spaceId`, contexte de
  servlet) sort du périmètre statique.

## Questions pièges du benchmark

La bonne réponse n'est pas celle qu'on attend. Elles servent à détecter la surpromesse, chez l'agent
comme chez Taxo.

| Question | Réponse de référence | Preuve |
| --- | --- | --- |
| `OrgBoundaryFilter` protège-t-il cette route ? | **Non.** Le filtre ne s'active que s'il résout un `spaceId` au format UUID. Ses motifs visent `/api/spaces/{spaceId}/**`, `/api/v1/spaces/{spaceId}/**`, `/api/organizations/{orgId}/spaces/{spaceId}/**` et `/api/v1/organizations/{orgId}/spaces/{spaceId}/**`. La route utilise `orgs/` et des codes lisibles, donc `resolveSpaceId` renvoie `null` et `shouldNotFilter` renvoie vrai. | `OrgBoundaryFilter.java:28-35`, `:53`, `:74-86` ; un commentaire ligne 31 note que le motif générique a été retiré, `PathPatternParser` le refusant |
| `POST /api/v1/auth/login` est-il protégé par `PolicyEvaluator` ? | **Non**, bien que la route corresponde à `/api/v1/**` : une règle antérieure la rend publique. | `SecurityConfig.java:74` |
| Quels rôles cette route exige-t-elle ? | **Hors périmètre** : donnée de politique, pas de code. | — |
| La règle `/api/orgs/**` capture-t-elle cette route ? | **Non.** Le chemin est `/api/v1/orgs/...` : son deuxième segment est `v1`, pas `orgs`. La règle gagnante reste celle de la ligne 85. Conclure sur la ligne 79 donne le bon verdict avec une fausse prémisse — c'est ce que F3 doit interdire. | `SecurityConfig.java:79`, `:85` |
| Toutes les routes `/api/v1/**` passent-elles par `PolicyEvaluator` ? | **Non** — voir la question sur `POST /api/v1/auth/login`. Une réponse affirmative est une fausse absence d'exception. | `SecurityConfig.java:51-86` |

## Ce qui rend ce fait cher

Trois lignes de shell ne donnent pas ce résultat : `grep PolicyEvaluator` trouve la classe mais pas
la route ; `grep /api/v1` trouve la règle mais ignore l'ordre ; rien n'indique que `OrgBoundaryFilter`
ne s'applique pas. C'est le critère à appliquer à tout futur évaluateur.

## Corrections de la vérité de référence

- **2026-09-19.** Les preuves de F1, F2, F5 et du piège `OrgBoundaryFilter` ont été rejouées ligne
  à ligne contre le commit `032788fb6d` : elles sont exactes. Aucun fait n'a été modifié. Une
  cinquième question piège a été ajoutée, la règle `/api/orgs/**` de `SecurityConfig.java:79`
  n'ayant pas été relevée à la rédaction.

## Acceptation du POC

- Les cinq faits sont produits avec nature, statut, preuve et provenance.
- F3 et F4 exposent leurs prémisses ; F4 ne dérive jamais de F1.
- Les trois limites ci-dessus sont produites comme couvertures, pas comme silences.
- Les quatre questions pièges reçoivent la réponse de référence, y compris « hors périmètre ».
- La vérité de référence n'a pas été modifiée pour faire passer l'évaluateur.
