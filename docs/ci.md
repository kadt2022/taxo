# Integration continue Taxo

Recit : TAXO-CI-01. Le workflow `.github/workflows/taxo-ci.yml` s'inspire de
Takibo CI : taches separees, caches, rapports conserves en cas d'echec et statut
final unique. Il est adapte a Python 3.12, Node.js 24 et PostgreSQL 17 de Taxo.

## Declenchement et controles

Chaque PR vers `main`, chaque push sur `main` et chaque lancement manuel execute :

1. **Taxo Preflight** : versions des outils, presence des fichiers requis (dont
   `compose.yaml`) et validation de la configuration Compose.
2. **Taxo Backend** : installation, compilation Python et tous les tests pytest,
   avec couverture.
3. **Taxo Frontend** : `npm ci`, type-check TypeScript et build Vite.
4. **Taxo PostgreSQL** : migrations aller-retour, verification de l'alignement du
   modele SQLAlchemy, ecriture via l'API et relecture depuis une nouvelle instance.
5. **Taxo Docker Smoke** : apres les trois controles precedents, construction des
   images et demarrage Compose ; verification du portail, du proxy nginx, de
   l'API, d'un scan reel et de son historique persiste.
6. **Taxo Sonar Analysis** : analyse SonarQube Cloud avec la couverture backend,
   en attendant le resultat du Quality Gate.
7. **Taxo Quality Gate** : confirme que le Quality Gate Sonar est passe.
8. **Taxo CI Status** : statut final unique. Un controle annule, ignore ou en
   echec ne produit jamais un statut vert, sauf le cas Sonar non applicable
   decrit ci-dessous.

Les PR documentaires executent aussi la CI : le statut reste disponible pour
une protection de branche. Les executions depassees sur une meme reference sont
annulees. Les rapports JUnit, le build frontend et les logs Compose sont conserves
sept jours. Les permissions GitHub sont limitees a la lecture du code. Les
identifiants PostgreSQL sont jetables et reserves aux services crees par la CI.
Aucune image n'est publiee et aucun deploiement n'est effectue.

## Politique Sonar

| Contexte | Sonar Analysis et Quality Gate | Taxo CI Status |
| --- | --- | --- |
| push sur `main`, lancement manuel | executes, obligatoires | vert seulement si tous les controles, Sonar compris, sont verts |
| PR interne (branche de ce depot) | executes, obligatoires | vert seulement si tous les controles, Sonar compris, sont verts |
| PR externe : fork ou Dependabot | non applicables, volontairement ignores | vert si les cinq controles executables sont verts |

GitHub ne transmet pas les secrets du depot aux PR issues d'un fork ni aux PR de
Dependabot. Le job Sonar ne s'execute donc que dans un contexte de confiance : un
evenement autre que `pull_request`, ou une PR dont la branche appartient a ce
depot et qui n'est pas ouverte par Dependabot. Le workflow n'utilise pas
`pull_request_target` : le code d'un fork ne recoit jamais les secrets.

Pour une PR externe, le resume de **Taxo CI Status** indique :

```text
Sonar Analysis: NOT APPLICABLE - untrusted fork PR
Quality Gate: NOT APPLICABLE - untrusted fork PR
```

Un Quality Gate rouge fait echouer **Taxo Sonar Analysis**, donc **Taxo CI
Status**. L'etat `skipped` n'est accepte pour Sonar et le Quality Gate que dans le
contexte externe. Dans un contexte de confiance, un Sonar ignore, annule ou en
echec rend le statut rouge.

## Configuration requise

Secrets du depot, lus uniquement par **Taxo Sonar Analysis** :

- `SONAR_TOKEN`
- `SONAR_PROJECT_KEY`
- `SONAR_ORGANIZATION`

Dans un contexte de confiance, un secret manquant fait echouer l'analyse avec un
message explicite. Les secrets et parametres de Takibo ne sont pas reutilises.

## Protection de main

Le controle a rendre obligatoire dans les regles GitHub est **Taxo CI Status**.
La creation du workflow ne modifie pas automatiquement la protection de branche.

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
