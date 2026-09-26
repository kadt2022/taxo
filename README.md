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

Le plus simple sous Windows : double-cliquer sur `taxo-console.bat` à la racine du dépôt. Il prépare
l'environnement Python et la base SQLite, installe le portail au premier lancement, démarre l'API
(port 8000) et le portail (port 5173), puis ouvre la console d'administration. Les dépôts lisibles se
règlent dans la ligne `TAXO_ALLOWED_ROOTS` en tête du fichier. Étapes détaillées :

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

Depuis `backend`, `python -m app.facts --conformance` rejoue les 84 exemples de
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

### Analyse globale et historique (TAXO-EVAL-01)

Le comportement par défaut de Taxo est l'**analyse globale** du projet (« Lancer l'analyse globale ») :
elle produit les faits du projet, ceux du code et ceux de tout l'historique Git (TAXO-EVAL-02), sans
choisir de commits à montrer. La liste des commits est une consultation distincte, faite seulement sur
demande, avec un nombre de commits explicite : aucune fenêtre n'est imposée par défaut. Le plafond de 100 commits par consultation borne le coût d'une requête ; ce n'est
pas une valeur par défaut.

### Une vue humaine du projet (TAXO-UI-01)

Après l'analyse globale, le portail présente d'abord ce que Taxo a compris du projet : une vue d'ensemble
(technologies, fichiers analysés, historique Git) et, pour ce que Taxo ne sait pas encore déterminer
(architecture, API, sécurité), la mention « Non analysé » : une absence d'information n'est jamais
présentée comme un résultat. La navigation ne propose que les sections réellement disponibles
(Vue d'ensemble, Technologies, Historique). Le vocabulaire du contrat de faits est traduit dans la couche
de présentation (`frontend/src/vocabulary.ts`), sans rien renommer côté backend. Évaluateurs, versions,
identifiants d'exécution, couverture et relations restent consultables sous « Détails de l'analyse ».

### Des analyses et une Minia progressives (TAXO-UX-02)

Taxo ne paraît jamais figé pendant qu'il travaille, et n'invente aucune progression : chaque étape
affichée correspond à un événement réel du serveur.

- `POST /api/projects/{id}/analyses` lance l'analyse globale en tâche de fond (`202`), puis
  `GET …/analyses/{job}/events` diffuse ses événements en Server-Sent Events : `analysis.started`,
  `snapshot.ready`, `evaluator.started`, `evaluator.progress` (fichiers lus, commits lus, avec un total
  seulement s'il est connu), `evaluator.completed` ou `evaluator.failed`, `analysis.consolidating`, puis
  `analysis.completed` ou `analysis.failed`. `Last-Event-ID` reprend après le dernier événement reçu.
  `POST …/scans` reste disponible et synchrone.
- Le portail montre les étapes dès le clic ; les résultats d'un évaluateur remplacent les anciens dès
  qu'il termine, les autres cartes restent visibles et marquées « Mise à jour… ». Un évaluateur en échec
  est signalé sans interrompre l'analyse.
- Minia annonce ses étapes (sélection des faits, contexte, « Minia interprète N faits Taxo ») et, si le
  fournisseur le permet (Ollama), affiche sa réponse pendant qu'elle l'écrit :
  `POST …/commits/{sha}/ask/stream` et `POST /api/projects/{id}/ask/stream`. Ce texte est provisoire ;
  les faits cités et la réponse validée n'arrivent qu'à la fin.

Les journaux d'analyse vivent dans la mémoire du processus : un déploiement à plusieurs instances devra
les partager, ou router un client vers l'instance qui a lancé son analyse.

### Historique et impact des commits (TAXO-HIST-01)

Sur demande, le portail affiche les derniers commits d'un projet, lus directement dans Git, puis la fiche d'un
commit (fichiers touchés, lignes ajoutées et retirées) et ce que Taxo en comprend : chaque évaluateur
analyse le parent et le commit, et les faits sont comparés par identité canonique (ajoutés, retirés,
modifiés), avec les zones non interprétées. Un fichier `.env` est nommé, jamais lu. Pour un commit de
fusion, le premier parent sert de référence ; `?parent=` en choisit un autre.

API : `GET /api/projects/{id}/history/commits?limit=<nombre>` (obligatoire, 1 à 100), `…/commits/{sha}` et `…/commits/{sha}/impact`.

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

### Git, deuxième évaluateur (TAXO-EVAL-02, ADR 0007)

L'analyse globale exécute tous les évaluateurs sur le même instantané. À côté de l'inventaire, Git
transforme **tout** l'historique atteignable en faits : `HAS_COMMIT` (dépôt → commit, date et message),
`AUTHORED_BY` (commit → personne), `CHILD_OF` (commit → parent) et `CHANGES` (commit → fichier, avec le
type de changement et l'ancien chemin d'un renommage). Leur preuve est l'objet Git, dans le commit de
l'instantané. L'évaluateur n'a aucune fenêtre de commits ; au-delà d'un budget de lecture de 50 000
commits, la suite est déclarée non interprétée. Si Git échoue, l'analyse du code aboutit quand même.

Les faits de chaque évaluateur sont conservés et s'interrogent après l'analyse :
`GET /api/projects/{id}/scans/{scan_id}/facts?evaluator=&kind=&subject=&relation=&object=`. Les faits
Git et ceux du code se rejoignent par la même référence `file:`. L'impact d'un commit et Minia ne
comparent que les évaluateurs de contenu.

### Interroger Taxo (TAXO-QUERY-01)

> Les évaluateurs savent observer. Taxo sait conserver et relier les faits. La requête sait sélectionner.
> Minia sait expliquer.

Le panneau « Interroger Taxo » sélectionne, parmi les faits Git conservés par la dernière analyse
globale, ceux que la requête vise, sans relire le dépôt :

- un nombre explicite de derniers commits : « les 10 derniers commits » → 10, « 3 derniers » → 3 ;
- un commit, par son identifiant (7 caractères au moins) : « le commit 5b9022b » ;
- une période, en dates ISO : « depuis 2026-09-01 », « entre 2026-09-01 et 2026-09-10 », « en 2026-09 » ;
- un nombre et une période ensemble : « les 3 derniers commits depuis 2026-09-01 ».

Aucun nombre n'est supposé : « Analyse le projet » ou « les derniers commits » restent une requête
globale, jamais « les 10 derniers commits ». Les commits suivent l'ordre de `git log --date-order`
(un commit avant ses parents), reconstruit à partir des faits `CHILD_OF`. Chaque fait sélectionné garde sa
provenance et sa preuve.

« Demander à Minia » transmet au modèle uniquement les faits de la sélection. Sans sélection (requête
globale), ou sans commit correspondant, le modèle n'est pas appelé et Minia le dit.

API : `GET /api/projects/{id}/query?q=…` et `POST /api/projects/{id}/ask` avec `{"question": "…"}`.

### Protocole Taxo, opérations v1 (TAXO-QUERY-02, ADR 0009)

> Minia comprend la question et raisonne. Taxo cherche, relie et prouve. L'humain décide.

Les opérations que Minia, ou tout autre client, peut demander à Taxo sur la dernière analyse d'un projet.
Elles sont en lecture seule et ne connaissent ni langage, ni framework, ni projet : elles interrogent les
relations et les références du contrat du fait.

| Opération | Rend |
| --- | --- |
| `describe` | les opérations disponibles pour ce projet, les analyseurs et les relations présentes |
| `find_facts` | les faits qui correspondent à `subject`, `relation`, `object` ou `nature` (au moins un) |
| `get_evidence` | les preuves d'un fait reçu dans l'échange (`F…`) |
| `get_coverage` | ce qui a été analysé ou non, éventuellement pour un périmètre (`scope`) |
| `get_commit` | les faits Git d'un commit, sans contenu |
| `get_diff` | les blocs modifiés d'un fichier touché par un commit, sur double consentement (ADR 0008) |
| `verify_claim` | `CONFIRMED`, `REFUTED` ou `NOT_PROVEN` (avec sa raison) pour une affirmation structurée |

```http
POST /api/projects/{id}/taxo-query
{"consent": {"diff": false}, "max_bytes": 64000,
 "requests": [{"operation": "verify_claim",
               "arguments": {"subject": "commit:…", "relation": "CHANGES", "object": "file:src/app.txt"}}]}
```

- **Un échange par requête** : jusqu'à 20 opérations partagent l'instantané, le budget (64 000 octets par
  défaut, de 16 240 à 200 000 ; 8 000 par opération par défaut, 32 000 au plus) et les références `F…` / `E…`.
  Le budget est une limite stricte, refus compris : chaque opération encore possible garde 512 octets pour
  un refus éventuel.
- **Enveloppe commune** : `outcome` `OK` ou `ERROR` (codes `INVALID_ARGUMENT`, `NO_CONSENT`,
  `NOT_AVAILABLE`, `OUT_OF_SCOPE`, `BUDGET_EXHAUSTED`, `INTERNAL`), couverture toujours présente, et
  `not_sent` pour ce qui n'a pas tenu, sans jamais couper un élément au milieu.
- **Verdicts** : `REFUTED` n'est rendu que sur une relation exclusive (un commit a un auteur, un fichier un
  langage). « Non trouvé » reste `NOT_PROVEN`, avec `NOT_FOUND_IN_ANALYSED_SCOPE`, `NOT_INTERPRETED` ou
  `NOT_ANALYSED`. La réfutation par un fait `ABSENCE` attend le premier analyseur qui en produit.
- **`get_diff`** n'est proposé que si `MINIA_SOURCE_CONTEXT=diff`, et ne répond qu'avec
  `"consent": {"diff": true}` ; les refus de l'historique (`.env`, binaires, fichiers trop gros…) restent.
- `diff_facts` (réservée par l'ADR, activée par TAXO-MINIA-09b) rend les faits qu'un commit introduit, modifie
  ou retire, d'après l'impact (comparaison avec le premier parent). Ce sont des changements, sans référence
  `F…`, avec la localisation de leurs preuves.
- Les autres opérations réservées (`find_endpoint`, `find_callers`, `get_source`…) répondent `NOT_AVAILABLE`
  tant qu'aucun analyseur ne les nourrit.

### Minia interroge Taxo (TAXO-MINIA-09, ADR 0009)

Dans « Interroger Taxo », Minia ne reçoit plus un paquet de faits fixe, quel que soit le fournisseur (Ollama,
Claude, Gemini, Mistral) : elle **interroge Taxo**, une opération du protocole à la fois (`describe`, `find_facts`, `get_commit`…), et
décident de la suivante d'après les résultats. Taxo fixe les garde-fous : une description, au plus 8
opérations choisies par Minia, puis au plus 10 affirmations vérifiées, dans le budget de l'échange.

Minia conclut par des **énoncés typés**, et rien d'autre n'est affiché :

| Énoncé | Affichage |
| --- | --- |
| `claim` : une phrase et son affirmation structurée (sujet, relation, objet) | toujours avec le verdict de Taxo : confirmée (avec le fait et ses preuves), contredite (avec ce qui la contredit), non prouvée (avec la raison), ou non vérifiable (affirmation mal formée) |
| `interpretation` : un raisonnement, une hypothèse | « non vérifié » |
| `unknown` : ce qui manque pour conclure | dans « Ce que Taxo ne sait pas » |

La **trajectoire** est visible en direct puis sous la réponse : chaque opération, ses arguments, son issue,
sa taille et ce qui n'a pas été transmis. Une opération refusée (`NO_CONSENT`, `OUT_OF_SCOPE`…) est rendue
à Minia comme un résultat, jamais comme une instruction.

Chaque réponse de Taxo est bornée à la place qui reste dans la fenêtre du modèle au tour suivant ; quand
cette place devient trop petite, Minia doit conclure avec ce qu'elle a. C'est ce qui permet à un modèle local
à petite fenêtre (Ollama, `MINIA_OLLAMA_NUM_CTX=16384`) de suivre le même protocole que les fournisseurs
distants (TAXO-MINIA-09c) : mêmes opérations, mêmes vérifications, mêmes garde-fous.

Si l'exploration échoue (réponse illisible, opération répétée, limite atteinte, fenêtre dépassée), Taxo
**bascule en mode paquet** : le fonctionnement précédent. La réponse le dit.

**Question sur un commit (TAXO-MINIA-09b).** Taxo ouvre l'échange par ce que Git sait du commit
(`get_commit`) ; Minia demande ensuite ce qu'il change selon Taxo (`diff_facts`) et, seulement si le réglage
`MINIA_SOURCE_CONTEXT=diff` et la case de la demande l'autorisent, le diff d'un fichier (`get_diff`). Le diff
n'est plus joint d'avance : Minia le lit fichier par fichier, sur demande. Le mode paquet reste utilisé
quand le commit n'appartient pas à la dernière analyse globale, ou pour l'autre côté d'une fusion
(comparaison avec un autre parent que le premier).

### Minia : demander ce que signifie un commit (TAXO-MINIA-01)

Dans la fiche d'un commit, « Demander à Minia » pose une question en langage courant. Minia répond à
partir de ce que Git sait du commit (auteur, date, message, fichiers et statuts, renommages compris,
sans contenu) et des seuls faits de Taxo : les faits changés par le commit, leurs preuves (chemin et
lignes, jamais le contenu), les zones non interprétées et les évaluateurs en échec. Elle ne reçoit pas le
code source, sauf le diff du commit sur double accord (TAXO-MINIA-02, ci-dessous). La réponse est présentée en trois blocs séparés : **Fait Taxo** (les faits cités, affichés
depuis Taxo), **Interprétation Minia** (non vérifiée) et **Inconnu / non interprété**. Une référence
inventée par le modèle est écartée et signalée. Ce que Git sait du commit est toujours affiché, tiré de
Git et non du modèle. Si Taxo n'a vu changer aucun fait et qu'aucun évaluateur n'a échoué, le modèle
n'est pas appelé et Minia dit qu'elle ne sait pas (une zone non interprétée seule ne suffit pas). Aucune réponse n'est conservée, et une réponse n'est jamais
enregistrée comme un fait (ADR 0004, règle 14). Minia est indépendante de Clochette.

Minia fonctionne avec un modèle servi par [Ollama](https://ollama.com), gratuit. `MINIA_OLLAMA_URL`
peut viser un Ollama local ou distant : sans `MINIA_SOURCE_CONTEXT=diff` (voir TAXO-MINIA-02), Minia
n'envoie jamais de code source, seulement la projection Taxo décrite ci-dessus ; si Ollama est distant,
ces données quittent la machine de Taxo.

```powershell
ollama pull qwen2.5:3b
$env:MINIA_PROVIDER = 'ollama'                       # valeur par défaut
$env:MINIA_OLLAMA_URL = 'http://127.0.0.1:11434'     # valeur par défaut
$env:MINIA_OLLAMA_MODEL = 'qwen2.5:3b'
```

Sans `MINIA_OLLAMA_MODEL`, Minia est désactivée et le reste de Taxo fonctionne normalement.

Minia fixe la fenêtre de contexte d'Ollama (`MINIA_OLLAMA_NUM_CTX`, 16 384 tokens par défaut). Sans ce
réglage, Ollama garderait sa petite fenêtre par défaut et tronquerait en silence le début d'un long
message, c'est-à-dire les consignes de Minia. Minia ajuste son message à la fenêtre, avec une borne sûre
(pas plus de tokens que d'octets UTF-8, quelle que soit la langue) : les faits qui ne tiennent pas ne
sont pas transmis et la réponse le dit ; le diff prend la place laissée par les faits de Taxo. Une
demande qui ne tiendrait toujours pas est refusée (`MINIA_CONTEXT_TOO_LARGE`) plutôt que tronquée.
Augmenter `MINIA_OLLAMA_NUM_CTX` donne plus de place, au prix de mémoire.

Un modèle local peut être lent : `MINIA_OLLAMA_TIMEOUT_SECONDS` (900 s par défaut) est le temps laissé à
Ollama pour répondre à **un tour** ; la connexion, elle, doit aboutir en 10 s. Un délai dépassé est dit comme
tel (« Ollama n'a pas répondu dans les 900 s »), distinct d'un Ollama injoignable, et n'entraîne pas de repli
en mode paquet : le modèle y serait aussi lent. En exploration, une question peut compter plusieurs tours.
API : `GET /api/minia/status` et `POST …/commits/{sha}/ask` avec `{"question": "…", "parent": null}`.
Le modèle est derrière l'interface `MiniaModel` : un adaptateur Claude pourra s'ajouter sans toucher au
reste (`MINIA_PROVIDER=claude`, pas encore disponible).

### Minia lit le diff d'un commit (TAXO-MINIA-02, ADR 0008)

> Taxo établit. Git montre ce qui a changé. Minia lit les deux et explique.

Sur accord explicite, Minia reçoit aussi le diff du commit : seulement les blocs modifiés, lus par
l'historique avec ses refus (`.env` et fichiers confidentiels, binaires, liens, sous-modules, gros
fichiers : jamais lus). Limites : 20 fichiers, 1 500 lignes, 32 Ko et la place laissée par les faits de Taxo ; le code passe avant les tests,
qui cèdent les premiers quand la place manque ; les fichiers générés (verrous de
dépendances, fichiers minifiés, snapshots) ne sont pas lus. La réponse dit combien de fichiers ont été
transmis et pourquoi les autres ne l'ont pas été. Le diff n'est jamais un fait : Minia ne cite que des
faits de Taxo, et ce qu'elle déduit du diff reste dans « Ce que Minia en déduit », non vérifié. Le code
est traité comme une donnée : un commentaire du genre « ignore les instructions précédentes » n'est
jamais suivi.

```powershell
$env:MINIA_SOURCE_CONTEXT = 'diff'    # défaut : off, aucun code transmis
```

Il faut aussi cocher « Autoriser Minia à lire le diff de ce commit » (`"source_context": true` dans
l'API). Si `MINIA_OLLAMA_URL` vise une autre machine, le portail avertit que le diff quittera la machine
de Taxo, et la case n'est pas cochée par défaut.

### Minia Ollama ou Minia Claude (TAXO-MINIA-05)

Minia peut être servie par plusieurs fournisseurs. Elle fait le même travail quel que soit celui choisi :
mêmes consignes, même contexte borné, même réponse validée par Taxo, jamais un fait. Chaque question
choisit son fournisseur dans le portail (liste « Minia », affichée dès que deux fournisseurs sont
configurés) ; la réponse indique lequel a répondu, ce qui permet de comparer.

```powershell
$env:MINIA_OLLAMA_MODEL = 'qwen2.5:3b'        # Minia Ollama : local
$env:MINIA_CLAUDE_MODEL = 'claude-opus-5'     # Minia Claude : distant, activée seulement par ce choix
$env:ANTHROPIC_API_KEY  = '…'                 # identifiants de l'API Claude (jamais dans le dépôt)
$env:MINIA_PROVIDER     = 'ollama'            # fournisseur proposé par défaut
```

Claude est un service distant : la question et les faits Taxo transmis (chemins, messages de commit,
auteurs) quittent la machine de Taxo, et le diff aussi s'il est autorisé. Le portail l'affiche, et la case
du diff n'est pas cochée par défaut avec Claude. La réponse de Claude est contrainte par un schéma JSON
(`cited`, `answer`, `unknown`) ; une réponse déclinée ou coupée est signalée, jamais affichée à moitié.
Sans `ANTHROPIC_API_KEY`, Taxo démarre et Minia Claude le dit à la première question.

### Minia Gemini (TAXO-MINIA-06)

Troisième fournisseur de Minia, même travail que les deux autres. L'API Gemini a un niveau gratuit, ce qui
permet de tester un gros modèle distant sans acheter de crédits.

```powershell
setx GEMINI_API_KEY "..."                       # clé créée dans Google AI Studio (jamais dans le dépôt)
$env:MINIA_GEMINI_MODEL = 'gemini-3.8-flash'    # nom exact d'un modèle ouvert à ce projet (AI Studio)
$env:MINIA_GEMINI_TIER  = 'free'                # défaut ; 'paid' si la clé est facturée
```

Au niveau gratuit, Google peut utiliser les données envoyées pour améliorer ses produits : le portail
l'indique (« niveau gratuit ») et le déconseille pour du code privé ; le diff reste décoché par défaut. La
clé passe dans un en-tête, jamais dans l'URL. Une réponse bloquée, déclinée ou coupée est signalée, un
quota atteint aussi.

### Minia Mistral (TAXO-MINIA-10)

Quatrième fournisseur de Minia, même travail que les autres, mode exploration compris (ADR 0009). L'API de
Mistral (La Plateforme) a un niveau gratuit pour tester.

```powershell
setx MISTRAL_API_KEY "..."                          # clé créée sur console.mistral.ai (jamais dans le dépôt)
$env:MINIA_MISTRAL_MODEL = 'mistral-small-latest'   # nom exact d'un modèle ouvert à ce compte
$env:MINIA_MISTRAL_TIER  = 'free'                   # défaut ; 'paid' si la clé est facturée
$env:MINIA_MISTRAL_NUM_CTX = '32768'                # fenêtre du modèle en tokens (défaut prudent)
```

La place donnée à Minia se déduit de la fenêtre : fenêtre moins la réponse (8 192 tokens) et les consignes,
avec la même borne sûre que pour Ollama (jamais plus de tokens que d'octets). En exploration, le budget de
l'échange suit cette place ; si une demande dépasse quand même, Taxo revient au mode paquet, qui s'ajuste.

Les modèles ouverts au compte se listent avec `GET https://api.mistral.ai/v1/models` (en-tête
`Authorization: Bearer <clé>`). Au niveau gratuit, Mistral peut utiliser les données envoyées pour
entraîner ses modèles : le portail l'indique (« niveau gratuit ») et le déconseille pour du code privé ; le
diff reste décoché par défaut. La réponse est contrainte par un schéma JSON ; une réponse coupée est
signalée, une surcharge passagère (5xx) est réessayée deux fois avant tout texte, un quota atteint (429)
jamais.

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
