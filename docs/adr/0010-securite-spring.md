# ADR 0010 — Sécurité Spring : règles d'URL en faits, protection par déduction

Date : 2026-09-27
Statut : Proposé
Dépend de : ADR 0002 (contrat du fait), ADR 0003 (analyseur Java), ADR 0009 (protocole Minia–Taxo)
Récit : TAXO-05 (évaluateur Spring Security)

## Contexte

`taxo.spring-api` dit quelles routes existent et quelle méthode traite chacune. La question suivante,
celle de la démo technique, est : **qui a le droit d'appeler cette route ?** C'est aussi la plus
dangereuse à mal répondre. Déclarer publique une route protégée fait perdre confiance ; déclarer
protégée une route ouverte fait courir un risque réel. Le plan en fait un critère bloquant.

Le POC `backend/poc/authchain` a prouvé le mécanisme (première règle gagnante, prémisses) avec des
expressions régulières. Il reste un POC : pas de constantes, pas de verbe partiel, pas de chaînes
multiples.

## Décision

1. **Évaluateur `taxo.spring-security`**, catalogue `spring-security` : `PERMITS_ALL`,
   `AUTHORIZED_BY` (`OBSERVED`), `MATCHED_BY`, `PROTECTED_BY` (`INFERRED`). Il reprend les endpoints de
   `taxo.spring-api`, qui reste propriétaire du concept d'endpoint, et lit les règles dans les chaînes
   d'appels que donne l'analyseur Java (nouvelle primitive, générique : appels fluents, arguments,
   lambdas, type déclaré d'une variable).
2. **Une règle lue est un fait observé**, à la ligne : `route-pattern:<VERBE> <motif>` (le verbe
   seulement s'il est écrit) `PERMITS_ALL`, ou `AUTHORIZED_BY` l'expression écrite (`hasRole("ADMIN")`)
   ou le type qui décide (`access(manager)`, si son type est dans les sources). Le qualificatif
   `filter_chain` nomme la chaîne de filtres qui la porte.
3. **La correspondance a trois issues** : toutes les requêtes de la route (`ALL`), aucune (`NONE`),
   certaines ou inconnu (`SOME`). `MATCHED_BY` ne vient que d'une règle `ALL` précédée de règles
   `NONE`, qui deviennent les contre-exemples vérifiés.
4. **`PROTECTED_BY` s'appuie sur `MATCHED_BY` puis `AUTHORIZED_BY`**, jamais sur `HANDLED_BY`.
   L'objet est `policy-rule:<expression>` ou `symbol:java:<type>`. Ses limites connues sont dites : les
   rôles sont des données, la décision d'un gestionnaire n'est pas lue.
5. **Anti-faux-positif.** L'endpoint est `NOT_INTERPRETED`, sans conclusion, quand :
   - une règle antérieure n'est pas lue ou ne vise qu'une partie des requêtes ;
   - aucune règle ne capture la route ;
   - plusieurs chaînes de filtres sont candidates ou le périmètre `securityMatcher` n'est pas lu ;
   - `web.ignoring()` peut viser la route ;
   - `access("…")` n'est pas une expression qui ne peut que restreindre (SpEL non évalué : `or`,
     `true`, `permitAll`, appel de bean), ou `access(…)` un gestionnaire ni du dépôt ni restrictif de
     Spring ;
   - l'analyse des endpoints n'a pas établi certaines routes (ses zones non interprétées sont reprises).
   - le dépôt contient plusieurs applications Spring Boot (`@SpringBootApplication`…) : l'application
     qui sert la route et les chaînes qu'elle charge ne sont pas établies. Les règles restent des faits
     observés ; aucune route n'est rattachée tant que l'unité déployable n'est pas modélisée (D1).

   Seule une chaîne dont le receveur est une variable de type `HttpSecurity` de Spring (nom qualifié ou
   import) est une configuration : une API maison aux mêmes noms de méthode ne l'est pas, et un receveur
   de type inconnu donne une configuration vue mais non lue.

   Sont aussi déclarés `NOT_INTERPRETED` :
   - la sécurité de méthode (`@PreAuthorize`…) ;
   - les filtres et `AuthorizationManager` maison.
6. **Pas de règle, pas d'affirmation.** Sans `authorizeHttpRequests` dans les sources (configuration
   par défaut de Spring Boot, XML, Kotlin), rien n'est affirmé et un avertissement le dit. Une question
   sur la protection d'une route y reste « non trouvé dans le périmètre analysé », jamais « non
   protégée ».
7. **Une confirmation par déduction le dit.** Dans Minia, un `verify_claim` confirmé par un fait
   `INFERRED` s'affiche « Confirmée par Taxo, par déduction », avec prémisses, contre-exemples et
   limites (ADR 0009).

## Conséquences

- Les autorisations entrent dans l'impact d'un commit, le protocole et Minia sans changement de ces
  consommateurs. Une règle ajoutée devant une autre change le `MATCHED_BY` des routes concernées.
- Hors de cette version :
  - l'ordre des chaînes (`@Order`) ;
  - les méta-annotations ;
  - `context-path` et `spring.mvc.servlet.path` ;
  - les variantes d'URL de `antMatchers` (dites en lacune connue) ;
  - les expressions SpEL ;
  - la sécurité de méthode elle-même.
- Les sources Java sont lues deux fois (endpoints, puis sécurité) : acceptable à ce stade. Une mémoire
  partagée des primitives entre évaluateurs pourra l'éviter.
- Le POC `authchain` reste la vérité de référence du mécanisme, pas du code de production.
