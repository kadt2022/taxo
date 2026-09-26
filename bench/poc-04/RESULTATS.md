# Banc TAXO-POC-04 — impact d'un symbole sur Keycloak : résultats

*2026-09-19. Dernière expérience autorisée par la décision gelée du
[journal](../JOURNAL-2026-09-19.md). Une exécution par bras.*

## Le terrain

Keycloak au commit `4c094e12c3`, 6 577 fichiers Java. Index SCIP produit par `scip-java 0.12.3`
sur 12 modules (~3 060 fichiers) : `services`, `server-spi`, `server-spi-private`, `core`,
`common`, `saml-core`, `saml-core-api`, `model/storage`, `model/storage-private`, `crypto/default`,
`quarkus/config-api`.

**Coût de l'indexation : 23 minutes**, dans les 60 du timebox. Rien n'a été développé : `scip-java`
et le CLI `scip` ont été pris tels qu'ils existent. Deux obstacles d'environnement, documentés
parce qu'ils coûteront le même temps à quiconque recommence :

1. `scip-java` ne sait pas lancer Maven sous Windows — Java ne peut pas exécuter un script sans
   extension (`CreateProcess error=193`, puis `error=2` sur un projet Maven minimal).
2. Dans un conteneur Linux, le `mvnw` monté depuis Windows n'a pas le bit exécutable. Contourné en
   copiant les sources **dans** le conteneur, sans toucher au dépôt de l'utilisateur.

Index : **76,6 Mo**. Converti en JSON : 120 Mo. La liste des références du symbole, extraite :
**3,1 Ko, ~786 tokens**.

## Le symbole

`org.keycloak.storage.user.UserLookupProvider#getUserById(RealmModel, String)`
(`server-spi/.../UserLookupProvider.java:45`).

Choisi pour sa difficulté mesurée : **71 fichiers** du dépôt contiennent le texte `getUserById`, et
**13 déclarations distinctes** portent ce nom. Un grep ne tranche pas ; il faut résoudre les types.

## Résultats

| | A — agent seul | B — agent + index SCIP |
| --- | --- | --- |
| Durée | 395 s | **262 s** (−34 %) |
| Tokens | 87 903 | **83 881** (−4,6 %) |
| Appels d'outil | 27 | **22** (−19 %) |
| Réponse | **47 occurrences, 30 fichiers** | **47 occurrences, 30 fichiers** |
| Listes de fichiers | identiques | identiques |
| Q3 : 1 déclaration + 1 implémentation + 45 appels | oui | oui |

**Les deux bras donnent la même réponse, et elle est juste.**

## Le fait le plus intéressant : l'index était incomplet, et les deux agents l'ont vu

L'index SCIP annonce **41 occurrences**. La réponse est **47**. Les 6 manquantes sont toutes dans
`UserStorageManager.java` : la redéfinition `@Override` (ligne 408) et ses cinq auto-appels non
qualifiés (458, 483, 511, 583, 814), dont quatre à l'intérieur de lambdas.

La raison est structurelle, pas un bug : `scip-java` attribue à la redéfinition un **symbole
propre**. Interroger le symbole de l'interface ne remonte donc ni l'implémentation ni ses appels
internes. Pour une question d'impact — « qu'est-ce qui casse si je change ce contrat ? » — c'est
précisément ce qu'il faut.

Le bras B, qui avait l'index, l'a corrigé. Le bras A, qui ne l'avait pas, a trouvé les 47 seul et a
en plus détaillé, avec fichiers et lignes, les implémentations **hors périmètre** qui casseraient
aussi (`JpaUserProvider`, `UserCacheSession`, LDAP, Kerberos, SSSD, Ipatuura) — que l'index ne
couvrait pas.

## Application de la règle de décision gelée

> Si l'index apporte un avantage net sur l'exhaustivité, ou réduit fortement le travail, Taxo est
> redéfini autour de l'intelligence d'impact logiciel. Si l'agent seul reste aussi bon, Taxo est
> archivé.

- **Avantage net sur l'exhaustivité : non.** Réponses identiques, et l'index était lui-même
  incomplet (41 contre 47) pour la question posée.
- **Réduction forte du travail : non, pas à ce prix.** −34 % de durée et −19 % d'appels d'outil sont
  réels, mais −4,6 % de tokens seulement, contre **23 minutes d'indexation** à payer d'abord. Il
  faudrait une quinzaine de questions sur le même commit pour amortir, et l'index périme au commit
  suivant.

**L'agent seul est resté aussi bon. La règle conclut à l'archivage.**

## Limites de cette mesure

Une seule exécution par bras, un seul symbole, un seul dépôt, un seul modèle. Un symbole avec des
centaines de dépendants, ou un modèle moins capable, pourrait renverser le résultat — mais ce
serait une autre expérience, et la règle de décision interdisait un quatrième banc pour sauver le
résultat.
