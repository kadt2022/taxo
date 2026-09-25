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
..\.venv\Scripts\python -m app.hypotheses fetch
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

### Historique et impact des commits (TAXO-HIST-01)

Le portail affiche les 10 derniers commits d'un projet, lus directement dans Git, puis la fiche d'un
commit (fichiers touchés, lignes ajoutées et retirées) et ce que Taxo en comprend : chaque évaluateur
analyse le parent et le commit, et les faits sont comparés par identité canonique (ajoutés, retirés,
modifiés), avec les zones non interprétées. Un fichier `.env` est nommé, jamais lu. Pour un commit de
fusion, le premier parent sert de référence ; `?parent=` en choisit un autre.

API : `GET /api/projects/{id}/history/commits?limit=10`, `…/commits/{sha}` et `…/commits/{sha}/impact`.

Chaque fichier de la fiche s'ouvre en diff côte à côte (TAXO-HIST-02) : le parent à gauche, le commit à
droite, avec les numéros de ligne ; `…/commits/{sha}/diff?path=…&parent=…`. Seul un fichier touché par
le commit est accepté. Aucun contenu n'est renvoyé pour un fichier confidentiel (`.env`, `.env.*`), un
binaire, un fichier de plus de 1 Mo, un lien ou un sous-module : seule la raison est donnée. Le diff
montre ce que Git a changé ; l'impact reste ce que Taxo en comprend.

Le diff se relie ensuite aux faits (TAXO-HIST-03) : `…/commits/{sha}/diff/facts?path=…&parent=…` donne
les faits changés par le commit dont une preuve porte sur ce fichier. Le lien est `LINE` quand la plage
de lignes d'une preuve recouvre une ligne modifiée (elle est marquée ◆ dans le diff), `FILE` sinon. Il
passe uniquement par les preuves, jamais par une lecture du texte. L'inventaire, seul évaluateur du
produit aujourd'hui, prouve par fichier entier : ses liens sont donc `FILE`.
L'impact sur les chaînes d'autorisation passe encore par le POC Spring, hors produit :
`py -m poc.authchain.impact --root <dépôt> --commit <sha>` (résultat marqué `provisional`).

### Minia : demander ce que signifie un commit (TAXO-MINIA-01)

Dans la fiche d'un commit, « Demander à Minia » pose une question en langage courant. Minia répond à
partir des seuls faits de Taxo : les faits changés par le commit, leurs preuves (chemin et lignes,
jamais le contenu), les zones non interprétées et les évaluateurs en échec. Elle ne reçoit jamais le
code source. La réponse est présentée en trois blocs séparés : **Fait Taxo** (les faits cités, affichés
depuis Taxo), **Interprétation Minia** (non vérifiée) et **Inconnu / non interprété**. Une référence
inventée par le modèle est écartée et signalée. Si Taxo n'a vu changer aucun fait, le modèle n'est pas
appelé et Minia dit qu'elle ne sait pas. Aucune réponse n'est conservée, et une réponse n'est jamais
enregistrée comme un fait (ADR 0004, règle 14). Minia est indépendante de Clochette.

Minia fonctionne avec un modèle local servi par [Ollama](https://ollama.com), gratuit :

```powershell
ollama pull qwen2.5:3b
$env:MINIA_PROVIDER = 'ollama'                       # valeur par défaut
$env:MINIA_OLLAMA_URL = 'http://127.0.0.1:11434'     # valeur par défaut
$env:MINIA_OLLAMA_MODEL = 'qwen2.5:3b'
```

Sans `MINIA_OLLAMA_MODEL`, Minia est désactivée et le reste de Taxo fonctionne normalement.
API : `GET /api/minia/status` et `POST …/commits/{sha}/ask` avec `{"question": "…", "parent": null}`.
Le modèle est derrière l'interface `MiniaModel` : un adaptateur Claude pourra s'ajouter sans toucher au
reste (`MINIA_PROVIDER=claude`, pas encore disponible).

### Clochette (SmolLM2-135M, expérimental, ADR 0006)

Clochette est installée par l'étape `python -m app.hypotheses fetch` de la procédure ci-dessus : elle
télécharge une seule fois la révision épinglée dans `TAXO_MODELS_DIR` (par défaut
`~/.cache/taxo/models`), vérifie l'empreinte SHA-256 de chaque fichier et échoue si l'une ne
correspond pas. Relancée, elle ne retélécharge que les fichiers absents ou altérés. Elle ne charge pas
le modèle : `torch` n'est pas nécessaire pour l'installer.

Les poids ne sont jamais dans le dépôt : `backend/app/hypotheses/infrastructure/models.json` porte la
source, la révision exacte et les empreintes. Épingler une nouvelle révision
(`fetch --record`) est une opération de maintenance de Taxo, jamais une étape d'installation.

Par défaut, Taxo démarre en mode documentaire et ne charge aucun modèle. Avec
`TAXO_HYPOTHESES=smollm2-135m`, le démarrage vérifie le cache et ne télécharge que ce qui manque. Avec
Docker, `TAXO_HYPOTHESES=smollm2-135m docker compose up` installe Clochette au premier démarrage dans le
volume `taxo_models`, réutilisé ensuite. Exécuter le modèle demande en plus
`pip install -r backend/requirements-hypotheses.txt`.

Pour converser avec Clochette en local, à titre expérimental et hors produit (cache vérifié, chat
template officiel, aucun téléchargement, aucune réponse ne devient un fait), le laboratoire utilise la
variante `smollm2-135m-instruct`, distincte du modèle de base de TAXO-LAB-01 : depuis `backend`,
`py -m app.hypotheses fetch smollm2-135m-instruct`, puis `py -m lab.clochette_chat`, après
`py -m pip install -r requirements-hypotheses.txt`.

Une hypothèse n'est pas un fait : elle n'entre jamais dans la mémoire et aucune API ne l'expose tant
que TAXO-LAB-01 n'a pas conclu.

Les scans sont synchrones et bornés à 50 000 fichiers dans cette version. Avant de traiter de gros dépôts : introduire une file durable, des workers isolés, des délais et une reprise après échec.

Prochaines briques non implémentées : analyseurs JavaParser et TypeScript Compiler API, modèle de relations versionné, extraction des endpoints/DTO, comparaison sémantique, documentation générée, GitHub App et assistant IA. Aucun LLM n'est appelé.

Cette version est réservée à un poste local de confiance : pas d'authentification ni de gestion multi-utilisateur. Les ports Docker sont limités à localhost et les dépôts montés en lecture seule. Ne pas l'exposer publiquement telle quelle.

Le code de Taxo est aussi monté en lecture seule dans Docker sous /taxo-source ; ce chemin peut être enregistré pour analyser Taxo lui-même.
