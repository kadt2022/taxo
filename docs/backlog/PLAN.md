# Plan Taxo

Mise à jour : 2026-10-02. Référence : [ARCHITECTURE.md](../ARCHITECTURE.md).

## Priorité active

Développer la cible produit sur des fixtures synthétiques génériques, sans dépendance à un dépôt
client ni à une expérimentation agent. La navigation et l’API sont utilisables sans Minia.

1. ✅ Nettoyage du dépôt : démonstrateurs, bancs spécifiques et leurs données retirés.
2. ✅ Première Tuile : `get_neighborhood` à un saut, avec budgets et reprise ([TAXO-01I](TAXO-01I-voisinage-et-projectabilite.md)).
3. ✅ **Mémoire versionnée des faits** : identité et occurrence séparées, Taxo basculé dessus
   ([TAXO-01E](TAXO-01E-memoire-versionnee-des-faits.md)). Récit terminé :
   migration réelle validée (43 analyses, 1 124 370 occurrences), 1 498 Mo contre 3 586 Mo pour
   `analysis_facts`.
4. → **Comparaison depuis les faits enregistrés** : comparer deux analyses sans relire le dépôt
   ([TAXO-01F](TAXO-01F-comparaison-persistee.md)).
   - **Une page par fonction** : Overview devient un tableau de bord, Analyses et Comparaisons ont leur
     page ([TAXO-UI-05](TAXO-UI-05-navigation-par-pages.md)), avant la tranche D de 01F. Livrée (#70 à #72).
   - **Tranche D** : le résultat d'une comparaison, par domaine, en phrases. Livrée (#73).
   - **Couverture bornée** : une absence de preuve n'est jamais une preuve d'absence
     ([TAXO-COV-01](TAXO-COV-01-couverture-bornee.md)), découverte par l'exercice « Taxo analyse Taxo ».
     Livrée (#74, #75).
   - Assainissement architectural ([TAXO-ARCH-REF-01](TAXO-ARCH-REF-01-assainissement-architectural.md)).
     Terminé (#76 à #82).
   - Tranche E : l'impact d'un commit depuis les analyses enregistrées, sans relire le dépôt. Livrée ;
     TAXO-01F est terminé.
5. ✅ Navigation multiniveau et explorateur de la Maille ([TAXO-01J](TAXO-01J-navigation-multiniveau-et-explorateur.md)),
   qui termine [TAXO-01I](TAXO-01I-voisinage-et-projectabilite.md) : plusieurs niveaux, sens combiné, couverture
   locale. PR 1 (moteur et protocole) livrée (#85) ; PR 2 (forme compacte et explorateur) livrée (#86) ; PR 3
   (mesures et essai réel) livrée par la PR de cette branche. Récit terminé.
6. Première projection Arbre, sur `get_neighborhood`, indépendante du stockage physique.
7. Profils adaptatifs et Forêt ; cache seulement si les mesures le justifient.
8. Enrichissement de la Maille : E2/E3, appels Java, lecteur Python, selon leurs propres dépendances.
   Appels Java : proposition [TAXO-01K](TAXO-01K-appels-java-entre-classes.md), qui propose de passer avant
   l'Arbre ; ordre à valider.

La mémoire versionnée passe avant la suite des Tuiles parce que la dette de stockage est constatée
(une copie complète de chaque fait par analyse), pas parce que les Tuiles en dépendraient : elles
lisent le port de stockage, pas ses tables. Le gain de place est un résultat à mesurer par 01E.

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
| 01E | Mémoire versionnée : un fait existe une fois, chaque exécution ajoute une **occurrence** (exécution, instantané, provenance) ; identité stable indexée | les faits sont stockés par analyse, une ligne par fait, sans occurrence ni identité indexée (`scans/infrastructure/sqlalchemy/fact_store.py` le dit lui-même) | réalisée : [TAXO-01E](TAXO-01E-memoire-versionnee-des-faits.md) |
| 01E | Une réanalyse du même instantané ne crée pas de nouvelle identité ; chaque nouvelle analyse ou exécution conserve sa propre occurrence ; deux versions de producteur distinguées par leurs occurrences | chaque analyse enregistre ses propres faits | réalisée : TAXO-01E |
| 01F | Comparer deux instantanés **depuis les faits persistés**, sans relire le dépôt | l'impact d'un commit réexécute les évaluateurs sur le parent et sur le commit (`history/application/queries.py`) | livrée : [TAXO-01F](TAXO-01F-comparaison-persistee.md), tranche A (#67) ; l'impact d'un commit lit la mémoire quand les deux analyses existent, tranche E |
| 01F | `EVIDENCE_CHANGED` : un fait dont seule la preuve se déplace reste inchangé, et ce déplacement est signalé à part avec les deux preuves | le fait est compté inchangé, sans signal distinct (`history/domain/impact.py`) | livrée : TAXO-01F, tranche A (#67) |
| 01F | Changement de statut à identité constante signalé | compté inchangé (ARCHITECTURE § 5.2) | livrée : TAXO-01F, tranche A (#67) |
| 01F | Banc Git scénarisé A, B, C, et deux versions d'évaluateur sur un même commit | « non comparable » est déclaré quand les catalogues diffèrent ; pas de banc scénarisé dédié | livrée : TAXO-01F, tranche A (#67) |
| 01G | Contrat de lecture complet et paginé (fait par identité, faits d'un instantané, validité) et vue de vérification fait par fait | lecture filtrée par protocole (`find_facts`, `get_evidence`, `get_coverage`) et pages du portail ; pas de pagination générale ni de vue par fait | reportée ; en partie couverte par le voisinage |
| 01H (épique) | Validité : `STALE`, `REVALIDATION_REQUIRED`, et saisie de validations humaines (`HUMAN_VALIDATED`) | champs au contrat, aucun moteur ([ARCHITECTURE § 5.5 et § 6](../ARCHITECTURE.md)) | reportée, avec son premier usage |

## Décision du 2026-09-29

Le dépôt produit ne contient plus de code expérimental jetable ni de données d’une application
cliente. Les anciens documents et expériences restent dans l’historique Git. Le travail actif
porte sur l’implémentation de la cible, en conservant les exigences non réalisées ci-dessus.

## Décision du 2026-09-30

La mémoire versionnée (01E) passe avant la suite des Tuiles, suivie de la comparaison persistée (01F).
Motif : la copie complète de chaque fait par analyse est constatée sur une base réelle (849 814
occurrences pour 36 analyses). Le taux de déduplication n'est pas connu ; il sera mesuré et publié
par 01E, même s'il déçoit. Le voisinage garde exactement son comportement observable.
