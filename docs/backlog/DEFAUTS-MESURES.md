# Défauts mesurés le 2026-09-19

*Chaque ligne vient d'une mesure, pas d'une intuition. Les preuves sont dans
[le journal](../../bench/JOURNAL-2026-09-19.md), qui reste figé. Ce document-ci évolue : il est la
file de correction.*

Ordre par valeur décroissante, où la valeur est « combien de mauvaises réponses ce défaut a
réellement produites ».

---

## D1 — Taxo ignore l'unité déployable

**Mesuré.** Le dépôt TAKIBO contient deux applications Spring Boot. Taxo conclut sur une route
depuis une configuration de sécurité que l'application qui la sert **ne charge pas**. Sur
`/api/health`, il a eu raison par accident : une seule chaîne correspondait.

**Conséquence** : quatre questions sur douze du banc POC-02 en dépendaient, et Taxo n'a pu en
traiter aucune correctement.

**Ce qu'il faut** : lire `settings.gradle`, les `build.gradle` et les `pom.xml` ; en déduire le
graphe des modules et les unités déployables (classe `@SpringBootApplication` + plugin Boot, ou
`Main-Class` de manifeste) ; rattacher chaque endpoint et chaque configuration à son unité.

**Double bénéfice** : c'est exactement l'information que la page « Architecture » doit afficher.
Corriger ce défaut sert le moteur documentaire autant que l'évaluateur.

---

## D2 — Le silence du parsing : ce qui n'est pas compris ne produit rien

**Mesuré.** `@Endpoint(id="auditstores")` avec ses `@ReadOperation` et `@WriteOperation`
(`AuditStoreEndpoint.java:10,19,31`) est un endpoint HTTP. Taxo ne le voit pas — et surtout,
**il ne dit pas qu'il ne l'a pas vu**. Un agent l'a trouvé ; l'inventaire de Taxo annonçait 45
endpoints là où il y en a 47.

C'est le défaut le plus grave, parce qu'il transforme une lacune en affirmation : « voici les 45
endpoints » se lit comme une liste complète.

**Ce qu'il faut** : renverser la logique du catalogue. Au lieu de produire des faits pour ce qu'il
sait lire et rien pour le reste, l'évaluateur doit **repérer les constructions qu'il ne sait pas
interpréter** et les déclarer en `NOT_INTERPRETED` avec leur emplacement. Concrètement : un fichier
qui contient une annotation d'endpoint non modélisée doit produire une couverture, pas un silence.

---

## D3 — Fausse absence : `OUT_OF_SCOPE` déclaré sans avoir cherché

**Mesuré.** Taxo déclare les rôles exigés « hors périmètre — donnée de politique, pas de code ».
C'est faux : `PolicyEvaluator.java:111-117` teste quatre codes de rôle en dur et `:256-262` refuse
la surface sans eux. La même erreur figurait dans la vérité de référence écrite avant le POC.

**Règle à coder** : une absence n'est légitime que relativement à ce qui a été cherché. `OUT_OF_SCOPE`
doit citer ce qui a été inspecté et pourquoi la réponse n'y est pas, sinon c'est une affirmation
déguisée.

---

## D4 — Le diff se tait sur les vrais changements de protection

**Mesuré.** Entre `8ac9f996` et `f18ff9ca`, quatre changements réels — actuator passé de public à
admin plateforme, fermeture d'un contournement par percent-encoding, durcissement des clients
OAuth2, restriction du signup. Taxo a rapporté **zéro**.

C'est la conséquence de D1, D2 et D5 : trois de ces quatre changements vivent hors du catalogue.
À rouvrir **après** eux, pas avant.

**Acquis à conserver** : la clé de comparaison doit porter sur la connaissance, jamais sur
l'emplacement. Mesuré : 34 faux positifs avec `fichier:ligne`, 0 avec le verdict.

---

## D5 — `anyRequest()` n'est pas modélisé

**Mesuré.** Six routes sur 45 ne concluent pas parce que la règle fourre-tout finale
(`.anyRequest().authenticated()` ou `.anyRequest().access(...)`) n'est pas lue. Taxo déclare
honnêtement « non conclu », mais Spring, lui, conclut.

---

## D6 — Le vocabulaire de l'`ABSENCE` est trop catégorique

**Mesuré.** Taxo produit « le filtre `OrgBoundaryFilter` ne s'applique pas à cette route ». Trois
sessions ont corrigé : le filtre **est** monté sur la chaîne et traversé ; c'est `shouldNotFilter`
qui le neutralise sur ce chemin. Et un appel portant `?spaceId=<UUID>` le réactive.

« Ne s'applique pas » et « monté mais inerte sur ce chemin, sauf paramètre de requête » ne sont pas
la même affirmation.

---

## D7 — Les faits bruts ne passent pas à l'échelle

**Mesuré.** Le bundle de 45 routes pèse ~248 000 tokens, soit **67 % de tout le code Java du
dépôt** qu'il décrit. Le rendu compact des mêmes faits pèse ~2 767 tokens, 90 fois moins, et suffit
à répondre.

**Règle** : toute sortie destinée à être lue — par un humain, une page, ou n'importe quel
consommateur — passe par une projection compacte. Le fait brut reste le format de stockage, jamais
le format de livraison.

---

## Ce que ces corrections ne rachètent pas

Les bancs du 2026-09-19 ont mesuré qu'un agent muni des faits de Taxo n'est pas plus exact qu'un
agent qui lit le code, sur ce dépôt et avec ce modèle. Corriger D1 à D7 rend Taxo **juste** ; cela
ne le rend pas **nécessaire à un agent**. C'est pourquoi le positionnement change : Taxo produit une
connaissance du logiciel pour des humains et des pages, pas une mémoire pour des modèles.
