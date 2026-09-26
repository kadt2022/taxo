# Banc TAXO-POC-03 — diff entre deux commits : résultats

*2026-09-19. Une exécution par bras. Voir `../JOURNAL-2026-09-19.md` pour la synthèse.*

## La fenêtre

`8ac9f99633997e825a92efc50ad0e8decab4a3d8` → `f18ff9caf16ca850bcd03004112ca169ff0f483a`,
7 commits, dépôt TAKIBO. Choisie parce qu'elle contient à la fois des ajouts de surface et un
durcissement de sécurité explicite (`fix(security): restrict actuator endpoints`).

## Question

Qu'est-ce qui a changé dans la surface HTTP et dans sa protection ? Ajouts, retraits, protections
modifiées avec avant/après, nombre d'inchangés, et ce qui n'a pas pu être déterminé.

## Résultats

| | Taxo, déterministe | Agent seul |
| --- | --- | --- |
| Coût | **30,5 s, 0 token** | 503 s, 123 204 tokens |
| Ajouts / retraits de surface | 4 / 2 — juste | idem, plus 2 sondes actuator |
| **Protections modifiées** | **0 signalé** | **4 réelles, prouvées ligne à ligne** |

### Les quatre changements que Taxo n'a pas vus

1. **`/actuator/**` : `permitAll` anonyme → autorité plateforme.** `SecurityConfig.java:52` avant,
   `:65-70` après ; `POST /actuator/loggers/{name}` compris. *(revérifié directement)*
2. **Contournement par percent-encoding fermé** sur les 27 routes sous policy :
   `request.getRequestURI()` devient `UrlPathHelper.getPathWithinApplication()`. *(revérifié)*
3. **Clients OAuth2** : avant, aucune règle du `PolicyEvaluator` ne matchait `/api/orgs/**`
   (`TmsSpaceRoute` exige `seg[2] == "v1"`), donc `POL_DEFAULT_ALLOW` ; après, règle explicite
   exigeant portée SPACE et rôle admin.
4. **`signup`** : les organisations existantes sont désormais refusées.

Trois de ces quatre changements vivent hors du catalogue du POC : dans le Java du `PolicyEvaluator`,
dans le traitement du chemin par le manager, dans la configuration actuator.

## L'acquis technique, lui, est réel

La clé de comparaison décide de tout :

| Clé | Protections « modifiées » rapportées |
| --- | --- |
| Sur l'**emplacement** (`fichier:ligne`) | **34** — toutes fausses : les règles s'étaient seulement décalées |
| Sur la **connaissance** (le verdict) | **0** — exact |

C'est la doctrine d'identité de l'ADR 0005 validée par un chiffre : 34 faux positifs → 0.

## Conclusion

Un tableau de bord CI alimenté par ce POC aurait affiché « aucun changement de protection » sur une
PR qui ferme un contournement d'autorisation et referme actuator. **Rapide, gratuit, déterministe —
et silencieux sur l'essentiel.** En sécurité, c'est la pire propriété possible : le déterminisme
sans complétude produit un silence confiant.

Le diff sur la connaissance fonctionne. Ce qui manque, c'est un catalogue assez complet pour qu'un
« aucun changement » soit croyable — c'est-à-dire TAXO-03, 04 et 05, soit des mois.

## Fichiers

`etats-avant-apres.json` : les verdicts par route aux deux commits, tels que produits par le POC
gelé (`97b8625`).
