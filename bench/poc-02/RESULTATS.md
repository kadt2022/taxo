# Banc TAXO-POC-02 — exhaustivité : résultats

*Une exécution par bras, 2026-09-19. Voir `../JOURNAL-2026-09-19.md` pour la synthèse de la
journée et les limites de l'ensemble.*

## Question

Liste complète des endpoints qui n'atteignent pas `PolicyEvaluator`, avec la règle gagnante, plus
trois chiffres : total, non-atteignants, non classés.

## Résultats

| Bras | Tokens | Durée | Outils | Réponse rendue | Les 8 vraies |
| --- | --- | --- | --- | --- | --- |
| A — agent seul | 120 419 | 352 s | 31 | 10 sur 47 | 8/8 |
| B — agent + faits bruts | 128 209 | 440 s | 35 | 12 sur 49 | 8/8 |
| C — agent + rendu compact | **104 193** | **321 s** | **22** | **8 sur 45** | 8/8 |
| D — filtre, sans modèle | **0** | **1 ms** | 0 | 8, dont 6 « non conclu » | 8/8 |

Aucune fausse affirmation nulle part. Les quatre bras trouvent les huit bonnes routes.

Les totaux divergent parce que **ma question ne fixait pas la convention** : A compte deux
opérations actuator, B compte quatre routes déclarées en source de test, C s'en tient aux
mappings de `src/main` et déclare les deux autres catégories en réserve. Les trois conventions
sont défendables et chacune a été déclarée par son bras.

## Tailles mesurées

| | Octets | Tokens estimés |
| --- | --- | --- |
| Tout le Java du dépôt (782 fichiers) | 1 485 600 | ~371 400 |
| Bundle brut de faits, 45 routes | 992 760 | ~248 190 |
| Les deux configs de sécurité + le manager | 23 339 | ~5 834 |
| Rendu compact, 45 routes | 11 071 | ~2 767 |

## Ce que ça établit

1. **Les faits bruts ne passent pas à l'échelle.** 67 % de la taille du code qu'ils décrivent, et
   le bras qui les reçoit est le plus lent et le plus cher.
2. **Le rendu compact gagne** : −13 % de tokens et −29 % d'appels d'outil contre l'agent seul, avec
   la seule réponse exactement conforme à l'étalon. C'est le premier gain mesuré de la journée.
3. **Zéro modèle, 1 ms, réponse exacte** — avec six entrées honnêtement marquées « non conclu ».
   C'est la seule chose qu'aucun agent ne sait faire à aucun prix.
4. **Et l'agent seul est plus exhaustif que Taxo.** Il trouve `@Endpoint(id="auditstores")`
   (`AuditStoreEndpoint.java:10,19,31`), que ni le POC ni mon étalon ne voyaient. La complétude de
   Taxo est relative à son catalogue, et son catalogue ignore les endpoints actuator.

## Erreur de protocole

Le rendu compact avait été copié dans le dossier du bras B. **B1 l'a lu** : son run mélange les
bras B et C. Le bras B propre n'a pas été rejoué. Ses chiffres sont donc à lire comme
« faits bruts *plus* rendu compact », ce qui ne change pas la conclusion sur la taille du bundle.

## Limites

Une seule exécution par bras : les écarts de tokens sont cohérents mais pas établis
statistiquement. Un seul dépôt, un seul modèle.
