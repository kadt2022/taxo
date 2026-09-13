# TAXO-01C — Instantané Git au commit — TERMINÉ

**Statut : TERMINÉ — implémentation terminée et tests validés ; revue PR et intégration dans `main` en attente.**  
**Parent : EPIC TAXO-01 — Fondation de la mémoire logicielle vérifiable (tâche T3)**  
**Dépend de : TAXO-01A, TAXO-01B**  
**Références : ADR 0001 (règle 4), ADR 0002 (instantané)**

## Récit

En tant que **Taxo**, je veux analyser le contenu d'un commit précis plutôt que le dossier de travail, afin que chaque résultat corresponde à une version identifiable du dépôt, sans fichiers ignorés ni modifications locales, tout en gardant une analyse du dossier de travail possible et explicitement marquée.

## Loi du récit

```text
L'analyse de référence lit un commit.
Le dossier de travail n'est analysé que sur demande, et il est marqué.
Taxo n'exécute jamais un programme configuré par le dépôt analysé.
```

## Décisions

- **Mode `COMMIT` par défaut** : `HEAD`, fichiers suivis (`git ls-tree`), contenus lus dans Git (`git cat-file`). Fichiers ignorés et non suivis exclus.
- **Mode `WORKING_TREE`** (`?mode=working-tree`) : fichiers suivis et non ignorés (`git ls-files --cached --others --exclude-standard`), lus sur disque, avec `content_fingerprint`.
- **`dirty`** : comparaison d'empreintes calculées par Taxo (SHA-256 du contenu sans `\r`), jamais par `git status`. Des fins de ligne seules ne rendent pas le dossier `dirty`.
- **`content_fingerprint`** : SHA-256 des couples (chemin, empreinte du contenu sans `\r`), triés par octets UTF-8 du chemin.
- **Sécurité** : uniquement `rev-parse`, `ls-tree`, `ls-files` et `cat-file`, avec `core.fsmonitor=false` et `GIT_OPTIONAL_LOCKS=0`. Aucun `status`, `diff` ni `add` : ni hook, ni filtre, ni fsmonitor du dépôt n'est exécuté. `safe.directory` permet de lire un dépôt monté en lecture seule.
- Liens symboliques et sous-modules jamais suivis. Fichiers `.env` et `.env.*` listés mais jamais lus, même pour une empreinte.
- `repository` est le nom du dossier racine. Un dossier qui n'est pas la racine d'un dépôt Git est analysé comme avant, sans instantané et avec un avertissement. Un dépôt sans commit est refusé.
- Résultat de scan : `snapshot` (`repository`, `commit`, `mode`, `content_fingerprint`, `dirty`) et `source` (`commit`, `working-tree` ou `unversioned`). Le portail affiche la source réelle.

## Hors périmètre

Commit autre que `HEAD`, sous-dossier d'un dépôt, Git LFS, persistance des faits (01E), exécutions d'évaluateur (01D), scan asynchrone.

## Vérification de l'implémentation

- Code : `backend/app/snapshots.py`, `backend/app/scanner.py`, `backend/app/main.py`, `frontend/src/main.tsx`.
- `backend/tests/test_snapshots.py` : contenu commité seul ; mode `WORKING_TREE` marqué ; fins de ligne ; `.env` jamais lu ; aucun programme du dépôt exécuté (fsmonitor, filtres) ; liens symboliques et sous-modules ; dossier non Git et sous-dossier ; dépôt sans commit ; paramètre `mode` de l'API.
- `python -m pytest -q` (backend) : 296 tests réussis. `python -m compileall -q app` : réussi. `python -m app.facts --conformance` : aucune divergence. `npm ci` puis `npm run build` : réussis.
- Mesure TAKIBO-IAM (commit `80eb595`, Windows, hors Docker) : mode `COMMIT` 1 109 fichiers en 3,6 s, contre 7 188 fichiers et 12,7 s avant 01C ; mode `WORKING_TREE` 1 112 fichiers en 3,5 s.

## Suite

Mesurer TAKIBO dans Docker Desktop pour décider si un scan asynchrone reste nécessaire avant TAXO-01D.
