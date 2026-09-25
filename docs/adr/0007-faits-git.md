# ADR 0007 — Git, deuxième évaluateur : l'historique en faits

Date : 2026-09-25
Statut : Proposé
Dépend de : ADR 0002 (contrat du fait), ADR 0004 (monolithe modulaire)

## Contexte

Jusqu'ici, Git servait à ouvrir un instantané et à afficher des commits ; aucun fait ne décrivait
l'historique. TAXO-EVAL-02 fait de Git un évaluateur comme l'inventaire : il observe l'instantané et
produit des faits conservés, que d'autres couches interrogent ensuite. Trois principes guident la
décision :

> Les évaluateurs savent observer. Taxo sait conserver et relier les faits. La requête sait
> sélectionner. Minia sait expliquer.

Le contrat v1 ne connaissait ni les commits ni les personnes, et sa preuve désignait toujours un
fichier (`path`, `content_hash`). Or la preuve d'un commit n'est pas un fichier : c'est l'objet Git.

## Décision

### 1. Extension additive du contrat v1

Aucun fait v1 existant ne change de sens ni de validité.

- Deux types de référence : `commit:<sha complet>` (40 ou 64 hexadécimaux minuscules) et
  `person:<clé>` (courriel de l'auteur, sinon son nom).
- Quatre relations, toutes `OBSERVED` :

  | Relation | Sujet | Objet | Qualificatifs |
  | --- | --- | --- | --- |
  | `HAS_COMMIT` | `repository` | `commit` | `authored_at`, `subject` |
  | `AUTHORED_BY` | `commit` | `person` | `name` |
  | `CHILD_OF` | `commit` | `commit` | `position` (1 = premier parent) |
  | `CHANGES` | `commit` | `file` | `change`, `old_path` pour un renommage |

- Une preuve porte soit un fichier (`path`, `content_hash`, lignes et symbole facultatifs), soit un
  objet Git (`object: commit:<sha>`), jamais les deux (`oneOf` du schéma).
- Les relations d'historique exigent une preuve par objet Git, et elles seules l'acceptent
  (`EVIDENCE_OBJECT`). La règle 4 de l'ADR 0002 reste entière : `evidence.repository` et
  `evidence.commit` sont ceux de l'instantané ; l'objet cité est atteignable depuis ce commit.

Sept cas de conformité couvrent l'extension (83 au total).

### 2. Pas de fenêtre de présentation

`GitEvaluator.evaluate(snapshot)` n'a pas d'autre paramètre : il lit **tout** l'historique atteignable
depuis le commit de l'instantané (un instantané du dossier de travail lit celui de `HEAD`). Il ne
décide jamais que « les 10 derniers commits » comptent ; c'est à la requête de sélectionner
(TAXO-QUERY-01).

`MAX_COMMITS` (50 000) n'est qu'un budget de lecture, pas une fenêtre. Au-delà, le premier commit
non lu est déclaré `NOT_INTERPRETED` et l'exécution est `PARTIAL` : rien n'est tronqué en silence.
Un chemin que le contrat ne sait pas représenter (par exemple `a:b.txt`) déclare son commit
`NOT_INTERPRETED` au lieu d'être ignoré.

La lecture reste celle des lectures Git de Taxo : aucun hook, filtre, fsmonitor, pilote de diff
externe ni vérification de signature du dépôt ; `--diff-merges=first-parent` pour une fusion ;
`-M` pour les renommages ; aucun contenu de fichier n'est lu.

### 3. Évaluateurs de contenu et évaluateurs d'historique

Un évaluateur déclare `describes_content`. L'historique décrit l'ascendance de l'instantané, pas son
contenu : comparer les faits Git d'un commit à ceux de son parent donnerait toujours « un commit
ajouté ». L'impact d'un commit et Minia ne comparent donc que les évaluateurs de contenu.

### 4. L'analyse globale conserve les faits de chaque évaluateur

`POST /api/projects/{id}/scans` exécute tous les évaluateurs enregistrés sur le même instantané.
L'inventaire reste l'évaluateur principal : s'il échoue, l'analyse échoue ; un autre évaluateur en
échec est signalé dans `evaluations` sans empêcher l'analyse du code.

Les faits et la couverture sont conservés dans la table `analysis_facts`, séparée de `scans.result`
(qui ne garde que des résumés bornés). Ils s'interrogent après l'analyse :
`GET /api/projects/{id}/scans/{scan_id}/facts?evaluator=&kind=&subject=&relation=&object=`.
Chaque fait garde sa provenance (`produced_by`) et ses preuves.

Les faits Git et ceux du code se rejoignent par la même référence `file:` : `object=file:README.md`
rend à la fois `CONTAINS` (inventaire) et `CHANGES` (Git).

Un troisième évaluateur s'ajoute au registre sans modifier les deux premiers.

## Conséquences

- La base grossit avec l'historique : environ quatre à six faits par commit.
- La sélection (« les 3 derniers », un commit, une période) est une projection sur ces faits,
  livrée par TAXO-QUERY-01 ; ni l'évaluateur ni le stockage ne la connaissent.
- Hors périmètre : évaluateurs de sécurité, dépendances, tests, CI ; génération de documentation ;
  raisonnement d'un modèle sur tout l'historique.
