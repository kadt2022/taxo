# Plan Taxo

Mise à jour : 2026-09-30. Référence : [ARCHITECTURE.md](../ARCHITECTURE.md).

## Priorité active

Développer la cible produit sur des fixtures synthétiques génériques, sans dépendance à un dépôt
client ni à une expérimentation agent. La navigation et l’API sont utilisables sans Minia.

1. Nettoyage du dépôt : retirer les démonstrateurs, les bancs spécifiques et leurs données.
2. Voisinage et Tuile explicite : première tranche `get_neighborhood` à un saut implémentée,
   avec budgets et reprise. Suite : couverture locale détaillée et parcours multi-niveaux. Contrat : [TAXO-01I](TAXO-01I-voisinage-et-projectabilite.md).
3. Première vue arborescente sur ce même moteur : preuves, frontières et renvois.
4. Étendre les faits : E2/E3, appels Java, lecteur Python, selon leurs propres dépendances.
5. Profils adaptatifs et Forêt après le voisinage ; cache seulement si les mesures le justifient.

Les hypothèses statistiques restent hors de cette séquence. Un résultat d’évaluation d’un agent
ne bloque pas le développement des capacités humaines et API.

## Validation indépendante

**Taxo ne juge pas Taxo** : les résultats attendus viennent de fixtures dont la vérité est établie
indépendamment du moteur, avec des preuves vérifiables. Les anciens POC sont retirés ; mesurer
la qualité, les coûts et l’utilité du produit reste nécessaire. Des évaluations génériques d’agents
restent possibles, sans conditionner la navigation humaine ni l’API. Le choix de leurs protocoles
et budgets devra être explicite ; ce nettoyage ne décide pas de leur résultat.

Recommandation à confirmer : juger les Tuiles sur leurs critères d’usage humain/API et mesurer
les économies de tokens séparément.
La limite `securityMatcher(...)` reste suivie. Le retrait de l’ancien banc ne décide pas du calendrier
de sa correction et ne transforme pas l’abstention de Taxo en vérité de référence.

## Limites suivies

Voir [DEFAUTS-MESURES.md](DEFAUTS-MESURES.md). Les configurations de sécurité non résolues
restent sans conclusion ; aucune règle spécifique à un projet ne sert à les compléter.

## Exigences restantes des récits archivés

Les récits 01E, 01F, 01G et l'épique TAXO-01 sont retirés du backlog, pas leurs exigences non
réalisées. Celles-ci restent visibles ici. Chacune est **reportée** par défaut ; la remplacer par un
autre choix ou l'abandonner est une décision à consigner ci-dessous. Le texte d'origine est dans
l'historique Git.

| Origine | Exigence non réalisée | Situation actuelle | Devenir |
| --- | --- | --- | --- |
| 01E | Mémoire versionnée : un fait existe une fois, chaque exécution ajoute une **occurrence** (exécution, instantané, provenance) ; identité stable indexée | les faits sont stockés par analyse, une ligne par fait, sans occurrence ni identité indexée (`scans/infrastructure/sqlalchemy/fact_store.py` le dit lui-même) | reportée ; à trancher avant la comparaison sur faits persistés et avant le cache  |
| 01E | Réexécution sur le même instantané sans doublon ; deux versions de producteur distinguées par leurs occurrences | chaque analyse enregistre ses propres faits | reportée, avec la ligne précédente |
| 01F | Comparer deux instantanés **depuis les faits persistés**, sans relire le dépôt | l'impact d'un commit réexécute les évaluateurs sur le parent et sur le commit (`history/application/queries.py`) | reportée ; dépend des occurrences de 01E |
| 01F | `EVIDENCE_CHANGED` : un fait dont seule la preuve se déplace reste inchangé, et ce déplacement est signalé à part avec les deux preuves | le fait est compté inchangé, sans signal distinct (`history/domain/impact.py`) | reportée |
| 01F | Changement de statut à identité constante signalé | compté inchangé (ARCHITECTURE § 5.2) | reportée |
| 01F | Banc Git scénarisé A, B, C, et deux versions d'évaluateur sur un même commit | « non comparable » est déclaré quand les catalogues diffèrent ; pas de banc scénarisé dédié | reportée |
| 01G | Contrat de lecture complet et paginé (fait par identité, faits d'un instantané, validité) et vue de vérification fait par fait | lecture filtrée par protocole (`find_facts`, `get_evidence`, `get_coverage`) et pages du portail ; pas de pagination générale ni de vue par fait | reportée ; en partie couverte par le voisinage |
| 01H (épique) | Validité : `STALE`, `REVALIDATION_REQUIRED`, et saisie de validations humaines (`HUMAN_VALIDATED`) | champs au contrat, aucun moteur ([ARCHITECTURE § 5.5 et § 6](../ARCHITECTURE.md)) | reportée, avec son premier usage |

## Décision du 2026-09-29

Le dépôt produit ne contient plus de code expérimental jetable ni de données d’une application
cliente. Les anciens documents et expériences restent dans l’historique Git. Le travail actif
porte sur l’implémentation de la cible, en conservant les exigences non réalisées ci-dessus.
