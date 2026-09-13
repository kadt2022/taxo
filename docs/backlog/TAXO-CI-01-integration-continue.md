# TAXO-CI-01 : integration continue

Statut : EN COURS

## Recit

En tant que contributeur Taxo, je veux une CI qui verifie automatiquement chaque
PR et main, afin de reperer les regressions avant integration.

Branche : `chore/taxo-ci-01-integration-continue`.
Base : `main`, commit `3e35df2`, independamment de la PR TAXO-01A encore ouverte.

## Criteres d'acceptation

- Tous les tests backend s'executent et produisent un rapport JUnit.
- Le type-check et le build frontend s'executent avec les dependances verrouillees.
- Les migrations sont verifiees sur PostgreSQL 17, y compris un aller-retour.
- La persistance est relue depuis une nouvelle instance de l'application.
- Les images Docker demarrent ensemble et un scan passe par le proxy du portail.
- Un statut final echoue si une verification echoue, est annulee ou ignoree.
- Les journaux sont conserves et les ressources de test sont nettoyees.
- La CI ne necessite aucun secret externe et ne deploie rien.
- Le workflow est execute sur GitHub et sa PR est ouverte sous le compte utilisateur.

## Perimetre

Workflow, scripts de verification et documentation. Aucun changement fonctionnel
de l'application, aucun ajout Sonar ou modification de protection de branche.
