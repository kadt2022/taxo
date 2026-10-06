# Limites et régressions à suivre

Les cas de régression utilisent des dépôts synthétiques. Ce fichier décrit les capacités génériques
à compléter ; il ne conserve aucune donnée d’un projet analysé.

| Capacité | État et garantie à préserver |
| --- | --- |
| Attribution à une application | établie seulement si classpath, chargement et conditions sont résolus |
| Couverture du parsing | constructions non reconnues à signaler ; endpoints Actuator encore à couvrir |
| Périmètre | une capacité absente ne doit pas être présentée comme une absence du phénomène |
| Impact de sécurité | comparer les faits et exposer les limites de chaque côté |
| Sécurité HTTP | `anyRequest()` pris en charge ; sélecteurs dynamiques non résolus à signaler |
| Absence | aucun évaluateur livré n’en produit ; exige périmètre et méthode avant toute future production |
| Structure Gradle mono-module | le projet Gradle racine n'est pas matérialisé comme module (constaté sur `student-course-demo`) ; à corriger avec son test de régression, séparément de TAXO-01K |
| Volume des faits | voisinage borné, budget de travail, preuve accessible et frontière explicite |
