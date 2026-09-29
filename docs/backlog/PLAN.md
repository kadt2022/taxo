# Plan Taxo

Mise à jour : 2026-09-29 (document cible unique ; une seule séquence active)
Référence : [ARCHITECTURE.md](../ARCHITECTURE.md), seul document d'architecture. Les ADR 0001 à 0012
et les récits TAXO-TILES-01 à 03 y sont fondus (§ 18) ; leur texte reste dans l'historique Git.

## Ce que Taxo promet

Taxo documente un logiciel par des faits vérifiables, rattachés au code et à un commit : ses modules,
ses unités déployables, ses routes, ce qui les protège, et ce qui change entre deux états. Ce qu'il ne
sait pas interpréter, il le dit, avec sa raison. Minia explique et propose ; Taxo vérifie. Le détail
de ce qui est livré est dans [ARCHITECTURE § 16](../ARCHITECTURE.md).

## Séquence active

Une seule file. Chaque étape suppose la précédente mergée ; l'ordre ne change que par une décision
consignée ci-dessous.

| # | Étape | Résultat attendu | Référence |
| --- | --- | --- | --- |
| 1 | **Questions libres sur les routes et la sécurité** | Minia répond sur les routes, les applications et les protections avec le protocole existant ; chaque réponse expose ses limites (non interprété, non analysé) | § 12 |
| 2 | **Banc POC-05** | versions de Taxo et du modèle, questions, vérités établies à la main sans Taxo, budgets : figés avant la campagne, puis mesurés (#48). Aucune modification de Taxo pendant la campagne | § 17 |
| 3 | **Décision Tuile sur critères d'usage** | trancher TAXO-01I sur un objectif précis : voisinage réutilisable pour l'API et la navigation humaine, apport à Minia mesuré séparément | § 9, [01I](TAXO-01I-voisinage-et-projectabilite.md) |
| 4 | **Première vue arborescente** | une racine, les relations déjà produites, renvois, preuves et frontière ; réutilise le voisinage | § 10 |
| 5 | **E2 puis E3** | dépendances déclarées, puis changements de structure entre deux commits, validés sur des projets sans Spring | § 7.5 |
| 6 | **Appels Java** | décision du § 14, migration du contrat et cas négatifs, puis le premier fragment | § 14 |
| 7 | **E4 et Forêt** | un lecteur Python sous le même contrat ; la Forêt s'enrichit au rythme des faits produits | § 10.2 |
| 8 | **Cache et invalidation** | seulement si les mesures le justifient | § 15 |

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
| **D7** faits bruts trop gros | étapes 3 et 4 |

## Questions ouvertes

- Limite connue avant le banc : les routes servies derrière une chaîne `securityMatcher(...)` non
  résolue (serveur d'autorisation) restent sans conclusion de sécurité.
- Accepter ou non un dossier sans dépôt Git (refusé aujourd'hui par `NOT_A_GIT_REPOSITORY`).
- Ce que « générique » recouvre exactement, au vu du corpus mesuré le 2026-09-19.

## Hors séquence

Data, dérive de documentation, configuration, frontend, tests, CI/CD, flux métier, notes de version,
sources Sonar et exécution. Les récits de vision décrivent ces capacités ; ils ne sont pas un backlog.

## Décisions

**2026-09-29 (document cible unique)**

- [ARCHITECTURE.md](../ARCHITECTURE.md) remplace les douze ADR et les récits TILES. Il définit Nœud,
  Graphe, Maille, Chemin, Tuile, Tuile adaptative, Frontière, Arbre, Forêt et Contexte.
- Le plan se réduit à la séquence active ci-dessus. L'étape 3 remplace un blocage fondé sur les seuls
  tokens par des critères d'usage explicites.

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
