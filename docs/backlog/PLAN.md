# Plan Taxo

Mise à jour : 2026-09-29 (document cible unique ; une seule séquence proposée)
Référence : [ARCHITECTURE.md](../ARCHITECTURE.md), seul document d'architecture. Les ADR 0001 à 0012
et les récits TAXO-TILES-01 à 03 y sont fondus (§ 18) ; leur texte reste dans l'historique Git.
Le backlog ne garde que le travail à venir et ses étalons : les récits livrés ou remplacés sont retirés
et restent dans l'historique Git.

## Ce que Taxo promet

Taxo documente un logiciel par des faits vérifiables, rattachés au code et à un commit : ses modules,
ses unités déployables, ses routes, ce qui les protège, et ce qui change entre deux états. Ce qu'il ne
sait pas interpréter, il le dit, avec sa raison. Minia explique et propose ; Taxo vérifie. Le détail
de ce qui est livré est dans [ARCHITECTURE § 16](../ARCHITECTURE.md).

## Séquence proposée

Une seule file de référence. **L'ordre est une recommandation, pas un ordre acté** : il se décide
étape par étape et chaque arbitrage est consigné ci-dessous. Ce n'est pas non plus une chaîne de
dépendances : les étapes 4 et 6 ne dépendent techniquement ni de Minia ni du banc et peuvent avancer
en parallèle des étapes 1 et 2 si la priorité le demande.

| # | Étape | Résultat attendu | Dépend techniquement de | Référence |
| --- | --- | --- | --- | --- |
| 1 | **Questions libres sur les routes et la sécurité** | Minia répond sur les routes, les applications et les protections avec le protocole existant ; chaque réponse expose ses limites (non interprété, non analysé) | — | § 12 |
| 2 | **Banc POC-05** | versions de Taxo et du modèle, questions, vérités établies à la main sans Taxo, budgets : figés avant la campagne, puis mesurés (#48). Aucune modification de Taxo pendant la campagne | 1 | § 17 |
| 3 | **Décision Tuile sur critères d'usage** | objectif de TAXO-01I fixé : voisinage réutilisable pour l'API et la navigation humaine, apport à Minia mesuré séparément | — | § 9, [01I](TAXO-01I-voisinage-et-projectabilite.md) |
| 4 | **Voisinage et Tuile explicite** | `get_neighborhood` en mode explicite (§ 9.1 à 9.4) : priorité, budgets, frontière à trois natures, reprise ; contrat de rejeu fixé et testé avant le premier profil adaptatif | 3 | § 9, § 12.3 |
| 5 | **Première vue arborescente** | une racine, les relations déjà produites, renvois, preuves et frontière ; réutilise le voisinage | 4 | § 10 |
| 6 | **E2 puis E3** | dépendances déclarées, puis changements de structure entre deux commits, validés sur des projets sans Spring | — | § 7.5 |
| 7 | **Appels Java** | décision du § 14, migration du contrat et cas négatifs, puis le premier fragment | — | § 14 |
| 8 | **E4 et Forêt** | un lecteur Python sous le même contrat ; la Forêt s'enrichit au rythme des faits produits | 5 | § 10.2 |
| 9 | **Cache et invalidation** | seulement si les mesures le justifient | 4 | § 15 |

Les profils adaptatifs (`security/1`, `structure/1`) viennent après l'étape 4 ; `commit-impact/1`
attend en plus le raccord fichier → symbole (§ 9.5).

La mesure suit le § 17 : exactitude, omissions, fausses affirmations, qualité des preuves, abstentions
pertinentes, temps humain, latence, tokens et coût total. Taxo ne juge pas Taxo : la vérité de
référence est établie sans lui.

## Défauts mesurés

La file détaillée est [DEFAUTS-MESURES.md](DEFAUTS-MESURES.md).

| Défaut | État |
| --- | --- |
| **D1** unité déployable | résolu par E1 tranche 2 là où les prémisses s'établissent ; sinon non interprété |
| **D2** silence du parsing | en partie : mappings non résolus et héritages non suivis déclarés ; `@Endpoint` d'actuator encore silencieux |
| **D3** `OUT_OF_SCOPE` sans avoir cherché | propre au POC `authchain` ; règle à reprendre par tout évaluateur qui déclarera `OUT_OF_SCOPE` |
| **D4** diff muet sur la protection | l'impact compare déjà les faits de sécurité ; à vérifier après l'étape 2 |
| **D5** `anyRequest()` | lu par `taxo.spring-security` |
| **D6** `ABSENCE` trop catégorique | propre au POC ; à respecter dès qu'une `ABSENCE` sera produite |
| **D7** faits bruts trop gros | étapes 3 à 5 |

## Questions ouvertes

- L'ordre de la séquence proposée, étape par étape.
- **Recommandation, à confirmer** : juger la Tuile sur des critères d'usage explicites (utilité pour
  l'humain et pour l'API), évalués séparément des économies de tokens (étape 3).
- **Recommandation, à confirmer** : ne pas corriger avant le banc la limite `securityMatcher(...)` non
  résolue (serveur d'autorisation). La version mesurée la déclare ; ce que l'on attend alors **de
  Taxo** sur ces routes est une abstention correcte. Ce n'est pas la vérité de référence du banc,
  établie à la main dans le code : un bras qui lit le code peut établir ce que Taxo ne résout pas
  encore. Une correction ultérieure donnerait lieu à une autre campagne.
- Accepter ou non un dossier sans dépôt Git (refusé aujourd'hui par `NOT_A_GIT_REPOSITORY`).
- Ce que « générique » recouvre exactement, au vu du corpus mesuré le 2026-09-19.

## Hors séquence

Capacités du contrat encore sans moteur : la validité (`STALE`, `REVALIDATION_REQUIRED`) et la saisie
de validations humaines (`HUMAN_VALIDATED`), [ARCHITECTURE § 5.5 et § 6](../ARCHITECTURE.md). Elles
viendront avec leur premier usage.

Data, dérive de documentation, configuration, frontend, tests, CI/CD, flux métier, notes de version,
sources Sonar et exécution. Les récits de vision décrivent ces capacités ; ils ne sont pas un backlog.

## Décisions

**2026-09-29 (document cible unique)**

- [ARCHITECTURE.md](../ARCHITECTURE.md) remplace les douze ADR et les récits TILES. Il définit Nœud,
  Graphe, Maille, Chemin, Tuile, Tuile adaptative, Frontière, Arbre, Forêt et Contexte.
- Le plan se réduit à une séquence proposée, dont l'ordre reste à décider étape par étape.

**2026-09-27 (TAXO-UI-02, page Routes)**

- Le portail montre les routes et leur chaîne de preuve, lues dans les seuls faits. Ni Minia, ni
  graphe, ni protocole nouveau. Une `COVERAGE` porte sa raison (`reason`, hors identité).

**2026-09-27 (E1 tranche 2)**

- `taxo.spring-boot` : `application BUILT_FROM module` et `endpoint SERVED_BY application`, déduit du
  classpath, du balayage et des conditions. Ce qui ne s'établit pas statiquement reste non interprété,
  jamais attribué par paquetage ou par nom.
- Le banc POC-05 (#48) n'est pas signé sur `c9bb788` : la version de Taxo mesurée est choisie à
  l'étape 2.

Les décisions antérieures sont dans l'historique Git de ce fichier.
