# TAXO-UI-02 — La page Routes

Statut : réalisé le 2026-09-27.

## Pourquoi

Rendre Taxo utile **sans aucune IA** : pour chaque route d'une application Spring, montrer ce que Taxo
prouve, avec ses preuves, et ce qu'il ne sait pas. C'est la chaîne de preuve d'E1 (tranche 2), rendue
visible :

```
route → traitée par → servie par → chaîne → règle applicable → protection → état
```

## Périmètre

- Un tableau des routes : route, méthode qui la traite, application, règle, protection, état.
- Un filtre par chemin ou verbe, et par état.
- Un clic sur une route montre chaque fait : ses preuves (fichier et lignes), ses prémisses, ce qui a
  été écarté, ses limites connues. Une route non interprétée montre la raison exacte, par évaluateur.
- Hors périmètre : Minia, graphe, tuile, conversation, nouvelle opération du protocole.

## Règles

- **Aucune déduction dans la page.** Un état n'est affiché que si un fait le porte :

  | État | Fait qui le porte |
  | --- | --- |
  | Protégée | `PROTECTED_BY` |
  | Règle permitAll() | `MATCHED_BY` vers un motif `PERMITS_ALL` de la **même** chaîne de filtres |
  | Non interprétée | une couverture `NOT_INTERPRETED` sur la route |
  | Sans conclusion | aucun des trois |

- Une route protégée qui porte aussi une zone non interprétée (sécurité de méthode) reste
  « Protégée », avec la mention « avec réserve » et la raison dans son détail.
- Les zones où des routes ont pu échapper à l'analyse (héritage non suivi, fichier lu en partie) sont
  listées sous « Des routes peuvent manquer ».

## Contrat

La raison d'une couverture était perdue : seuls cinq avertissements par évaluateur étaient conservés.
Une `COVERAGE` porte désormais `reason`, un texte facultatif hors identité (ADR 0002, historique du
2026-09-27). `taxo.spring-api`, `taxo.spring-boot` et `taxo.spring-security` le renseignent.

## Acceptation

1. `GET /api/projects/{id}/scans/{scan_id}/routes` rend les routes et leurs faits. Une analyse inconnue
   donne 404.
2. Une règle `permitAll()` d'une autre chaîne ne rend jamais une route « permitAll » (test de projection).
3. Sur TAKIBO (`6d9b214`) : 45 routes ; 5 protégées, 2 capturées par `permitAll()`, 38 non
   interprétées avec leur raison.
   - `GET /api/admin/users` montre `TestController#adminUsers(Authentication)`, `AdpTestApplication`,
     la chaîne `TestSecurityConfig#securityFilterChain(HttpSecurity)`, la règle
     `/** → adpAuthorizationManager()` et `SecurityConfig` écartée « hors du classpath ».
   - `GET /debug/secure/secret` est non interprétée : « condition @Profile », et « sécurité de méthode
     non interprétée (@PreAuthorize) ».
4. Aucune phrase de Minia ni formule probabiliste dans la page (test de rendu).
