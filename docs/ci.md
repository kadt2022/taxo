# Integration continue Taxo

Recit : TAXO-CI-01. Le workflow `.github/workflows/taxo-ci.yml` s'inspire de
Takibo CI : taches separees, caches, rapports conserves en cas d'echec et statut
final unique. Il est adapte a Python 3.12, Node.js 24 et PostgreSQL 17 de Taxo.

## Declenchement et controles

Chaque PR vers `main`, chaque push sur `main` et chaque lancement manuel execute :

1. **Taxo Backend** : installation, compilation Python et tous les tests pytest.
2. **Taxo Frontend** : `npm ci`, type-check TypeScript et build Vite.
3. **Taxo PostgreSQL** : migrations aller-retour, verification de l'alignement du
   modele SQLAlchemy, ecriture via l'API et relecture depuis une nouvelle instance.
4. **Taxo Docker Smoke** : apres les trois controles precedents, construction des
   images et demarrage Compose ; verification du portail, du proxy nginx, de
   l'API, d'un scan reel et de son historique persiste.
5. **Taxo CI Status** : succes uniquement si les quatre controles ont reussi.
   Un controle annule, ignore ou en echec ne produit jamais un statut vert.

Les PR documentaires executent aussi la CI : le statut reste disponible pour
une protection de branche. Les executions depassees sur une meme reference sont
annulees. Les rapports JUnit, le build frontend et les logs Compose sont conserves
sept jours. Les permissions GitHub sont limitees a la lecture du code ; aucun
secret externe n'est necessaire. Les identifiants PostgreSQL sont jetables et
reserves aux services crees par la CI. Aucune image n'est publiee et aucun
deploiement n'est effectue.

## Protection de main

Le controle a rendre obligatoire dans les regles GitHub est **Taxo CI Status**.
La creation du workflow ne modifie pas automatiquement la protection de branche.

Sonar n'est pas active : Taxo n'a pas encore de projet Sonar ni de configuration
associee dans ce depot. L'ajouter demandera un projet et un jeton propres a Taxo.
Les secrets et parametres de Takibo ne sont pas reutilises.

## Executer localement

Les commandes habituelles restent `python -m pytest -q` dans `backend` et
`npm ci` puis `npm run build` dans `frontend`.

Le controle PostgreSQL exige une **base de test jetable** : le workflow execute
`alembic downgrade base` avant de reconstruire le schema. Le script
`.github/scripts/check_database.py` utilise `DATABASE_URL` et le chemin Python
du backend ; il ne cree pas les tables et teste ainsi les migrations reelles.

Le test Compose utilise les ports locaux 18000 et 18080. Dans la CI,
`TAXO_REPOSITORIES` pointe sur le checkout Linux, et le projet Compose `taxo-ci`
dispose de son propre volume. Les conteneurs et volumes CI sont supprimes en fin
d'execution, y compris en cas d'echec.

Le workflow part de `main` et ne depend pas de TAXO-01A : pytest decouvre
automatiquement ses tests de contrat lorsque la PR correspondante est integree.
