# TAXO-01C — Instantané Git au commit — TERMINÉ

**Statut : TERMINÉ — implémentation, tests et banc TAKIBO validés ; revue PR et intégration dans `main` en attente.**  
**Parent : EPIC TAXO-01 — Fondation de la mémoire logicielle vérifiable**  
**Dépend de : TAXO-01A — Contrat machine du fait ; TAXO-01B — Références stables et identité canonique**  
**Références : ADR 0001, ADR 0002**

## Récit

En tant que **Taxo**, je veux analyser un instantané Git déterminé plutôt que parcourir indistinctement le dossier de travail afin que les faits produits soient reproductibles, rattachés exactement à un commit et indépendants des caches, fichiers générés et outils locaux qui ne font pas partie du dépôt.

Je veux également conserver un mode `WORKING_TREE` explicitement marqué pour les analyses locales non commitées, avec une empreinte de contenu qui distingue deux états différents du même dossier de travail.

TAXO-01C introduit donc la frontière entre :

```text
COMMIT
= contenu exact suivi par Git à un commit donné
= reproductible
= indépendant du working tree local

WORKING_TREE
= état courant du dossier de travail
= potentiellement différent du HEAD
= explicitement marqué
= identifié par une empreinte de contenu
```

Le récit ne transforme pas encore `scanner.py` en évaluateur Inventory v0 : cette conversion appartient à TAXO-01D.

---

## 1. Situation actuelle

Le scanner actuel parcourt le système de fichiers avec `os.walk()`.

Conceptuellement :

```text
dossier du projet
      │
      ▼
   os.walk()
      │
      ├── fichiers suivis par Git
      ├── fichiers ignorés
      ├── caches locaux
      ├── fichiers générés
      └── outillage local
```

La présence d'un `.git` permet aujourd'hui seulement de récupérer :

```text
git rev-parse HEAD
```

Le commit retourné ne garantit donc pas que **les fichiers réellement analysés sont ceux de ce commit**.

TAXO-01C doit supprimer cette ambiguïté.

---

## 2. Principe fondamental

Pour un instantané `COMMIT` :

> **Taxo lit Git, pas le working tree.**

Le contenu analysé doit correspondre exactement aux blobs suivis par Git pour le commit demandé.

Par conséquent :

- un fichier non suivi par Git n'est pas analysé ;
- un fichier ignoré n'est pas analysé s'il n'est pas suivi ;
- un fichier généré localement n'est pas analysé ;
- une modification locale non commitée n'altère pas une analyse `COMMIT` ;
- un fichier supprimé localement mais présent dans le commit reste visible dans l'instantané ;
- un fichier modifié localement mais différent du commit est lu dans sa version du commit.

Le mode `COMMIT` ne doit jamais dépendre du contenu courant du dossier de travail.

---

## 3. Objet d'instantané

Introduire une abstraction explicite d'instantané de dépôt.

Nom libre côté implémentation, par exemple :

```text
RepositorySnapshot
GitSnapshot
SnapshotReader
```

Cette abstraction doit permettre au minimum :

```text
repository
mode
commit
content_fingerprint   # WORKING_TREE seulement

iter_files()
read_bytes(path)
```

Le scanner ne doit plus être obligé de connaître directement `os.walk()` pour accéder au contenu qu'il analyse.

Architecture cible minimale :

```text
                    ┌─────────────────┐
                    │ Snapshot Reader │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
        Git COMMIT                     WORKING_TREE
              │                             │
              └──────────────┬──────────────┘
                             ▼
                      scanner actuel
```

L'abstraction doit rester suffisamment petite pour être réutilisée par les futurs évaluateurs.

---

## 4. Mode COMMIT

### Entrée

Taxo doit pouvoir construire un instantané à partir de :

```text
repository root
commit SHA
```

Le commit peut être :

- `HEAD` résolu une seule fois au début ;
- ou un SHA explicite demandé par l'appelant.

Après résolution, Taxo travaille avec le SHA Git complet.

### Règles

Un instantané `COMMIT` doit :

- vérifier que le dossier est bien un dépôt Git ;
- résoudre le commit demandé ;
- utiliser un SHA complet et stable ;
- lister uniquement les fichiers suivis présents dans l'arbre de ce commit ;
- lire le contenu depuis la base d'objets Git ;
- ne pas faire de checkout ;
- ne pas faire de reset ;
- ne pas modifier l'index ;
- ne pas modifier le working tree ;
- ne jamais exécuter de hook Git ;
- ne jamais exécuter de code ou de script du dépôt.

Les accès Git sont strictement en lecture seule.

---

## 5. Lecture efficace du commit

L'implémentation ne doit pas lancer une commande Git coûteuse indépendante pour chacun des milliers de fichiers si une lecture groupée est possible.

Une solution acceptable peut utiliser, par exemple :

```text
git ls-tree
git cat-file --batch
```

ou toute autre approche Git en lecture seule offrant le même résultat.

L'objectif n'est pas d'imposer une commande particulière, mais de garantir :

```text
1 commit
→ inventaire de ses fichiers
→ lecture déterministe des blobs
```

sans matérialiser un second checkout complet du dépôt.

Un `git archive` ou mécanisme équivalent en lecture seule est acceptable s'il respecte les contraintes de sécurité et de performance.

---

## 6. Chemins Git

Les chemins fournis par l'instantané `COMMIT` sont :

- relatifs à la racine du dépôt ;
- exprimés avec `/` ;
- issus de Git ;
- jamais absolus ;
- jamais reconstruits à partir d'un chemin natif Windows.

Taxo doit gérer correctement les chemins Git contenant des caractères Unicode.

Le snapshot ne doit jamais permettre qu'un chemin lu sorte du dépôt logique.

---

## 7. Symlinks et entrées spéciales Git

Le mode `COMMIT` doit distinguer les types d'entrées Git.

En v1 :

- fichier normal : lisible et analysable ;
- lien symbolique Git : **ne pas suivre la cible** ;
- sous-module Git : ne pas descendre dedans automatiquement ;
- autres types non supportés : les signaler explicitement plutôt que les interpréter comme fichiers ordinaires.

Un lien symbolique ne doit jamais permettre de lire un fichier extérieur au dépôt.

Le comportement choisi pour les symlinks et sous-modules doit être documenté et testé.

---

## 8. Mode WORKING_TREE

Le mode `WORKING_TREE` reste permis pour l'analyse locale.

Il doit être explicitement marqué :

```json
{
  "mode": "WORKING_TREE",
  "repository": "taxo",
  "commit": "<HEAD>",
  "content_fingerprint": "sha256:..."
}
```

Le `commit` indique le HEAD de référence, mais **ne prétend pas représenter à lui seul le contenu analysé**.

### Règle

Deux working trees différents au même HEAD doivent pouvoir être distingués par `content_fingerprint`.

---

## 9. Contenu du WORKING_TREE

Le mode `WORKING_TREE` ne doit pas revenir au comportement actuel consistant à parcourir aveuglément tous les caches présents dans le dossier.

La base du contenu est Git.

Doivent être pris en compte :

- fichiers suivis ;
- modifications locales des fichiers suivis ;
- nouveaux fichiers non suivis **non ignorés**, si le mode de travail les inclut explicitement.

Doivent être exclus :

- fichiers ignorés par Git ;
- `.git` ;
- caches et sorties ignorées ;
- contenu de symlinks externes.

Le comportement exact sur les fichiers non suivis non ignorés doit être explicite et couvert par les tests.

---

## 10. Empreinte du WORKING_TREE

`content_fingerprint` doit dépendre du contenu logique analysé, pas des métadonnées du système de fichiers.

Il ne doit donc pas dépendre de :

- date de modification ;
- inode ;
- propriétaire ;
- chemin absolu local ;
- séparateur Windows/Linux.

L'empreinte doit changer si :

- un fichier inclus change de contenu ;
- un fichier inclus est ajouté ;
- un fichier inclus est supprimé ;
- un chemin inclus est renommé.

Elle doit rester identique si seul un fichier ignoré change.

### Forme

```text
sha256:<64 hex minuscules>
```

La représentation exacte utilisée pour calculer cette empreinte doit être documentée et testée.

Le calcul doit être déterministe entre plateformes pour un même contenu logique.

---

## 11. Intégration minimale avec le scanner existant

Le scanner actuel doit pouvoir consommer l'instantané sans perdre ses fonctionnalités existantes.

Aujourd'hui il détecte notamment :

- langages par extension ;
- Dockerfiles ;
- workflows GitHub Actions ;
- certains manifestes Python/Node/Maven.

TAXO-01C ne doit pas encore réécrire ces détections en faits du contrat TAXO-01A : cela appartient à TAXO-01D.

Le résultat existant peut donc rester temporairement dans son format actuel.

En revanche il doit indiquer correctement :

```text
source = commit | working-tree
commit = SHA complet
files_count = nombre de fichiers réellement considérés
```

et, en mode `WORKING_TREE` :

```text
content_fingerprint
```

---

## 12. API

L'API actuelle peut conserver le déclenchement synchrone du scan pour ce récit.

TAXO-01C **ne doit pas** introduire le scan asynchrone par anticipation.

Le comportement attendu est que le scan d'un projet Git utilise par défaut un instantané déterminé.

Choix recommandé :

```text
POST /api/projects/{projectId}/scans
        ↓
résout HEAD une seule fois
        ↓
crée un snapshot COMMIT de ce SHA
        ↓
analyse ce snapshot
```

Si un mode `WORKING_TREE` est exposé dans l'API, il doit être explicite ; il ne doit jamais être choisi silencieusement alors que l'utilisateur pense analyser un commit.

Aucune API de comparaison entre commits n'est requise ici.

---

## 13. Cohérence temporelle

Un scan `COMMIT` doit figer son SHA **au début de l'analyse**.

Si la branche avance pendant le scan :

```text
début : HEAD = A
pendant : HEAD devient B
```

le scan en cours reste :

```text
snapshot = A
```

Il ne doit jamais mélanger des fichiers provenant de A et B.

---

## 14. Erreurs

Le récit doit distinguer proprement au minimum :

```text
NOT_A_GIT_REPOSITORY
UNKNOWN_COMMIT
GIT_READ_ERROR
UNSUPPORTED_GIT_ENTRY
WORKING_TREE_READ_ERROR
```

Les noms précis des exceptions internes sont libres, mais les erreurs doivent être :

- déterministes ;
- testables ;
- sans exposition de contenu source sensible ;
- sans commande Git brute recopiée avec des données non maîtrisées.

Une erreur Git ne doit pas provoquer une analyse partielle présentée comme complète.

---

## 15. Sécurité

Règle absolue :

> **Taxo observe un dépôt ; il ne lui donne jamais l'occasion d'exécuter du code.**

TAXO-01C ne doit jamais exécuter :

- Gradle ;
- Maven ;
- npm ;
- scripts shell ;
- hooks Git ;
- applications du dépôt ;
- fichiers binaires provenant du dépôt.

Les commandes Git autorisées doivent être strictement nécessaires à la lecture de l'objet Git.

Le dépôt reste monté en lecture seule dans Docker.

---

## 16. Tests obligatoires — COMMIT

Créer un dépôt Git de test contrôlé.

Les tests doivent prouver au minimum que :

1. seuls les fichiers présents dans le commit sont listés ;
2. un fichier ignoré et non suivi est absent ;
3. un cache ignoré est absent ;
4. un fichier non suivi n'altère pas l'instantané COMMIT ;
5. modifier localement un fichier suivi n'altère pas son contenu en mode COMMIT ;
6. supprimer localement un fichier présent dans le commit ne le retire pas du snapshot COMMIT ;
7. un ancien commit peut être lu même si HEAD est plus récent ;
8. le SHA est résolu une fois et reste stable pendant le scan ;
9. aucun checkout/reset/index write n'est effectué ;
10. un symlink Git n'est pas suivi ;
11. un sous-module n'est pas parcouru automatiquement ;
12. un commit inconnu est refusé proprement ;
13. deux lectures du même commit produisent exactement la même liste de fichiers et les mêmes octets.

---

## 17. Tests obligatoires — WORKING_TREE

Les tests doivent prouver au minimum que :

1. le mode est explicitement `WORKING_TREE` ;
2. le HEAD de référence est exposé ;
3. `content_fingerprint` est obligatoire ;
4. modifier le contenu d'un fichier suivi change l'empreinte ;
5. ajouter ou supprimer un fichier inclus change l'empreinte ;
6. modifier uniquement un fichier Git-ignoré ne change pas l'empreinte ;
7. NFC/NFD et chemins sont gérés conformément aux décisions du contrat ;
8. le fingerprint ne dépend pas des timestamps du filesystem ;
9. deux working trees logiquement identiques ont la même empreinte.

---

## 18. Banc réel obligatoire : TAKIBO-IAM

TAKIBO-IAM est le banc réel du récit.

Mesure de référence observée avant TAXO-01C :

```text
working tree parcouru : 7 188 fichiers
.gradle-user          : 3 719 fichiers
.claude               : 1 122 fichiers
fichiers suivis Git   : ~1 109
scan natif actuel     : ~12,7 s
proxy nginx           : 120 s
```

Ces nombres sont des mesures de départ, pas des constantes contractuelles.

### Démonstration attendue

Lancer Taxo sur TAKIBO-IAM en mode `COMMIT`.

Mesurer :

```text
commit analysé
nombre de fichiers Git considérés
durée du scan natif
durée du scan dans Docker Desktop
```

Vérifier explicitement que les répertoires ignorés tels que :

```text
.gradle-user
.claude
```

ne sont plus parcourus lorsqu'ils ne sont pas suivis par Git.

---

## 19. Décision sur le timeout après mesure

TAXO-01C ne promet pas que le timeout HTTP disparaîtra.

Il doit **mesurer** le résultat après suppression du bruit du working tree.

À la fin du récit :

```text
TAKIBO dans Docker
        │
        ▼
durée mesurée
        │
        ├── suffisamment sous 120 s
        │      → aucun async maintenant
        │
        └── reste proche / dépasse le timeout
               → ouvrir un récit de scan asynchrone
                  avant ou avec TAXO-01D
```

La décision doit être fondée sur la mesure réelle et consignée dans le récit terminé ou la PR.

---

## 20. Critères d'acceptation

Le récit est fonctionnellement terminé lorsque :

```text
[ ] une abstraction d'instantané existe
[ ] COMMIT lit les objets Git et non le working tree
[ ] un SHA complet identifie le snapshot COMMIT
[ ] le SHA est figé au début du scan
[ ] seuls les fichiers du commit sont analysés
[ ] les fichiers ignorés/non suivis n'altèrent pas COMMIT
[ ] aucune modification locale n'altère COMMIT
[ ] aucun checkout/reset/index write n'est effectué
[ ] symlinks Git non suivis
[ ] sous-modules non parcourus automatiquement
[ ] WORKING_TREE est explicitement marqué
[ ] WORKING_TREE possède content_fingerprint
[ ] le fingerprint est déterministe
[ ] les fichiers ignorés n'altèrent pas le fingerprint
[ ] le scanner existant fonctionne sur l'abstraction de snapshot
[ ] tous les tests existants restent verts
[ ] TAXO-01A --conformance reste vert
[ ] tests TAXO-01B restent verts
[ ] Sonar Quality Gate reste vert
[ ] Taxo CI Status reste vert
[ ] TAKIBO est mesuré en natif et dans Docker
[ ] une décision documentée est prise sur la nécessité de l'async
```

---

## 21. Hors périmètre

Ne pas profiter de TAXO-01C pour implémenter :

- scan asynchrone ;
- workers ;
- Redis/Kafka/Celery ;
- nouvelle persistance des faits ;
- modèle complet d'exécution d'évaluateur ;
- Coverage ;
- conversion du scanner en Inventory v0 ;
- JavaParser ;
- TypeScript Compiler API ;
- analyse Spring Boot ;
- endpoints/controllers ;
- Spring Security ;
- RBAC ;
- comparaison A/B entre commits ;
- invalidation `STALE` ;
- Ask Taxo ;
- clone Git distant ;
- GitHub App d'analyse distante ;
- exécution de code du dépôt.

---

## 22. Préparation de TAXO-01D

Après 01C, les futurs évaluateurs doivent recevoir un snapshot stable :

```text
RepositorySnapshot
        │
        ├── Inventory
        ├── Java
        ├── Spring API
        └── Spring Security
```

Ils ne doivent jamais chacun réinventer leur propre manière de parcourir Git.

TAXO-01D pourra donc se concentrer sur :

```text
Execution
producer_version
catalog
SUCCESS / PARTIAL / FAILED / UNSUPPORTED
Coverage
Inventory v0 → faits TAXO-01A
```

sans avoir à résoudre de nouveau la question « quels octets appartiennent réellement à ce commit ? ».

---

## Définition de terminé

Le récit peut être déplacé dans `Terminé` lorsque toutes les fonctionnalités, règles, critères d'acceptation et tests prévus ici sont implémentés et validés.

**Terminé ne signifie pas mergé.**

Le merge dans `main` intervient séparément après :

- CI complète verte ;
- Sonar Quality Gate vert ;
- commentaires de revue corrigés ou résolus ;
- absence de blocage restant sur la PR.

Démonstration minimale :

```text
HEAD = commit A
working tree contient :
  - modifications locales
  - .gradle-user
  - .claude
  - fichiers générés

Taxo COMMIT(A)
        ↓
lit exactement l'arbre Git de A
        ↓
ignore le bruit local
        ↓
résultat reproductible
        ↓
TAKIBO mesuré dans Docker
```

---

## Vérification de l'implémentation

- Code : `backend/app/snapshots.py` (instantané), `backend/app/scanner.py`, `backend/app/main.py` (`?mode=commit|working-tree`, `?commit=`), `frontend/src/main.tsx`.
- Décisions validées le 2026-09-13 : aucun repli non Git (`NOT_A_GIT_REPOSITORY` dans les deux modes) ; COMMIT ne lit jamais le dossier de travail et ne porte pas `dirty` ; `dirty` en WORKING_TREE seulement ; clé `repository` fournie par l'appelant (identifiant du `Project` dans l'API) ; `.env` et `.env.*` ni exposés ni lus ; SHA explicite de 40 ou 64 caractères hexadécimaux minuscules, `HEAD` par défaut ; lecture groupée par un seul `git cat-file --batch` ; chemins UTF-8 normalisés en NFC, collision refusée.
- Commandes Git : `rev-parse`, `ls-tree`, `ls-files` et `cat-file`, avec `core.fsmonitor=false` et `GIT_OPTIONAL_LOCKS=0`. Aucun hook, filtre ni fsmonitor du dépôt n'est exécuté (testé).
- WORKING_TREE : fichiers suivis et fichiers non suivis non ignorés ; exclusion des fichiers ignorés, de `.git`, des liens symboliques et des sous-modules.
- `content_fingerprint` : SHA-256 des couples (chemin NFC, SHA-256 du contenu sans ``), triés par octets UTF-8 du chemin.
- Erreurs : `NOT_A_GIT_REPOSITORY`, `UNKNOWN_COMMIT`, `GIT_READ_ERROR`, `UNSUPPORTED_GIT_ENTRY`, `WORKING_TREE_READ_ERROR`, renvoyées par l'API en 422 sous la forme `CODE : message`. Aucune erreur de lecture n'est convertie en avertissement.
- Tests : `backend/tests/test_snapshots.py` couvre les tests COMMIT 1 à 13 et WORKING_TREE 1 à 9, la lecture groupée, l'objet Git manquant, les chemins non UTF-8 et la collision NFC, `.env`, les programmes du dépôt, la clé de dépôt et l'API ; `test_inventory.py` travaille sur des dépôts Git.
- `python -m pytest -q` (backend) : 316 tests réussis. `python -m compileall -q app` : réussi. `python -m app.facts --conformance` : aucune divergence. `npm run build` : réussi.

### Banc TAKIBO-IAM (commit `80eb595`)

| Mesure | COMMIT | WORKING_TREE |
| --- | --- | --- |
| Fichiers analysés | 1 109 | 1 112 |
| Temps natif (Windows) | 0,6 s | 7,5 s |
| Temps Docker Desktop, via le proxy nginx | 5,4 s puis 4,0 s | 97,0 s puis 101,0 s |
| Timeout observé | non | non |

Avant 01C : 7 188 fichiers parcourus et 12,7 s en natif. `.gradle-user` et `.claude`, non suivis par Git, ne sont plus parcourus.

### Décision sur le scan asynchrone

- **COMMIT** (mode par défaut, destiné aux évaluateurs) : asynchrone **non nécessaire pour l'instant** ; 4 à 5 s dans Docker Desktop, loin des 120 s.
- **WORKING_TREE** : asynchrone **nécessaire** avant un usage courant sur un dépôt de cette taille ; 97 à 101 s dans Docker Desktop, proche du délai nginx de 120 s. Conformément au §19, un récit de scan asynchrone est à ouvrir avant ou avec TAXO-01D. Cause probable, non mesurée plus finement : lecture de tous les fichiers à travers le montage Windows de Docker Desktop.
