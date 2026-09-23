# Taxo

Premier socle local de la plateforme de documentation logicielle : Python/FastAPI, PostgreSQL, React/TypeScript. Le projet est développé dans `D:\Taxo\taxo`. La conception originale reste dans `D:\Taxo`.

## Fonctionnalités livrées

- Enregistrer un projet local dans une racine autorisée.
- Parcourir les fichiers sans exécuter les programmes du dépôt.
- Détecter Java, Python, JavaScript, TypeScript, SQL, Docker, GitHub Actions, Maven et certaines dépendances déclarées dans `package.json` et `pom.xml`.
- Conserver chaque analyse et la provenance de chaque détection.
- Consulter les résultats et les analyses précédentes dans le portail français.

Par défaut, une analyse lit le commit `HEAD` dans Git : seuls les fichiers de ce commit sont analysés, sans aucune lecture du dossier de travail. `?commit=<identifiant complet>` analyse un autre commit. `?mode=working-tree` analyse le dossier de travail (fichiers suivis et non ignorés) en le marquant comme tel, avec une empreinte de contenu et l'indicateur `dirty`. Un dossier qui n'est pas la racine d'un dépôt Git est refusé (`NOT_A_GIT_REPOSITORY`). Taxo n'exécute ni hook, ni filtre, ni fsmonitor du dépôt, et ne lit jamais `.env`. Une dépendance déclarée ne prouve pas qu'elle est utilisée à l'exécution.

## Démarrer avec Docker

Installer et démarrer Docker Desktop, puis depuis la racine du projet :

```powershell
docker compose up --build
```

Ouvrir http://localhost:18080 ; documentation API sur http://localhost:18000/docs.
Dans le formulaire, utiliser `/repositories`, monté en lecture seule : ce dossier doit être la racine d'un dépôt Git.
Définir `$env:TAXO_REPOSITORIES = 'D:/MonProjet'` avant le lancement (la valeur par défaut `D:/Taxo` n'est pas un dépôt Git).
Les données PostgreSQL sont conservées dans un volume Docker. Les migrations Alembic sont appliquées au démarrage du backend.

## Développement sans Docker

Python 3.12+ et Node.js 22.12+ sont nécessaires. Dans un premier terminal PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements.txt
$env:DATABASE_URL = 'sqlite:///./taxo.db'
$env:TAXO_ALLOWED_ROOTS = 'D:\Taxo;D:\Taxo\taxo'
cd backend
..\.venv\Scripts\python -m alembic upgrade head
..\.venv\Scripts\python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

SQLite est uniquement une facilité de développement. Pour PostgreSQL, utiliser une URL `postgresql+psycopg://utilisateur:motdepasse@localhost:5432/taxo`.

Dans un second terminal :

```powershell
cd frontend
npm ci
npm run dev
```

Ouvrir l'adresse affichée par Vite. Dans ce mode, le formulaire accepte les chemins Windows autorisés.

## Vérifications

```powershell
cd backend
..\.venv\Scripts\python -m pytest -q
cd ../frontend
npm run build
```

## Architecture et prochaines étapes

### Contrat du fait : TAXO-01A

Le contrat machine v1 est disponible dans `backend/app/facts` : JSON Schema,
validateur sémantique, empreintes normalisées et suite de conformité indépendante
du langage. Voir [le guide du contrat](backend/app/facts/README.md) pour les
formats, les décisions de représentation et les limites de validation.

Depuis `backend`, `python -m app.facts --conformance` rejoue les 76 exemples de
faits, les 8 vecteurs d'empreinte et les vecteurs d'identite canonique (19 positifs,
5 negatifs). Le scanner existant conserve son format
actuel jusqu'à TAXO-01D ; le contrat n'est pas encore une mémoire persistante.

Le backend est organisé par capacité : `projects`, `snapshots`, `facts`, `scans` et
`evaluators/inventory`. Le domaine est indépendant des frameworks ; les cas
d'utilisation passent par des ports, câblés dans `bootstrap.application`.
`main.py` conserve la factory Uvicorn. Alembic charge les mappings via
`bootstrap.database`. Voir [ADR 0004](docs/adr/0004-monolithe-modulaire.md).

L'inventaire reçoit un Snapshot et produit désormais une `EvaluatorExecution` avec
Facts, Coverage, provenance et statut technique via le moteur `evaluations`. Les
métadonnées historiques de l'API restent disponibles jusqu'à TAXO-01E, qui
introduira la persistance de la mémoire. Le portail interroge toujours la même API.

### Mode hypothèses (expérimental, ADR 0006)

Par défaut, Taxo fonctionne en mode documentaire : aucun modèle n'est chargé ni téléchargé. Le mode
hypothèses s'active avec `TAXO_HYPOTHESES=smollm2-135m` ; au démarrage, Taxo prépare alors les poids
du modèle. Les poids ne sont jamais dans le dépôt : `backend/app/hypotheses/infrastructure/models.json`
porte la source, la révision exacte et l'empreinte SHA-256 de chaque fichier, et tout fichier absent ou
altéré est retéléchargé puis vérifié.

```powershell
cd backend
..\.venv\Scripts\python -m pip install -r requirements-hypotheses.txt
..\.venv\Scripts\python -m app.hypotheses fetch smollm2-135m --record   # premier épinglage, à relire puis commiter
..\.venv\Scripts\python -m app.hypotheses status
```

Une hypothèse n'est pas un fait : elle n'entre jamais dans la mémoire et aucune API ne l'expose tant
que TAXO-LAB-01 n'a pas conclu. Les poids sont rangés dans `TAXO_MODELS_DIR`
(par défaut `~/.cache/taxo/models`).

Les scans sont synchrones et bornés à 50 000 fichiers dans cette version. Avant de traiter de gros dépôts : introduire une file durable, des workers isolés, des délais et une reprise après échec.

Prochaines briques non implémentées : analyseurs JavaParser et TypeScript Compiler API, modèle de relations versionné, extraction des endpoints/DTO, comparaison sémantique, documentation générée, GitHub App et assistant IA. Aucun LLM n'est appelé.

Cette version est réservée à un poste local de confiance : pas d'authentification ni de gestion multi-utilisateur. Les ports Docker sont limités à localhost et les dépôts montés en lecture seule. Ne pas l'exposer publiquement telle quelle.

Le code de Taxo est aussi monté en lecture seule dans Docker sous /taxo-source ; ce chemin peut être enregistré pour analyser Taxo lui-même.
