# Banc TAXO-POC-04 — impact d'un symbole

Dépôt : Keycloak, commit `4c094e12c3`. Périmètre de la question : les modules `server-spi`,
`server-spi-private`, `services`, `model/storage`, `model/storage-private`, `core`, `common`,
`saml-core`, `saml-core-api`, `crypto/default`, `quarkus/config-api` — environ 3 060 fichiers Java.

---

**Le symbole** : la méthode `getUserById(RealmModel, String)` **déclarée par l'interface**
`org.keycloak.storage.user.UserLookupProvider`
(`server-spi/src/main/java/org/keycloak/storage/user/UserLookupProvider.java:45`).

Attention : plusieurs méthodes du dépôt portent ce nom sans être celle-là. La question ne porte que
sur ce symbole, y compris lorsqu'il est appelé à travers un type qui en hérite.

**Q1.** Donne la **liste complète** des fichiers qui référencent ce symbole dans le périmètre
ci-dessus, avec les numéros de ligne.

**Q2.** Combien d'occurrences au total, et dans combien de fichiers ?

**Q3.** Si l'on change le contrat de cette méthode — par exemple en ajoutant un paramètre — quels
sont les sites d'appel à modifier, et lesquels sont des implémentations de l'interface plutôt que
des appels ?

**Q4.** Qu'est-ce que tu n'as pas pu déterminer, et pourquoi ?

---

Règles : chaque affirmation appuyée par un fichier et une ligne. **L'exhaustivité fait partie de la
réponse** : une liste juste mais incomplète n'est pas une liste juste. Un fichier déclaré incertain
coûte moins cher qu'un fichier affirmé à tort.
