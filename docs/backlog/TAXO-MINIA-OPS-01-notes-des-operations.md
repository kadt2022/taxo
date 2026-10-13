# TAXO-MINIA-OPS-01 — Notes d'usage des opérations proposées à Minia (expérience)

Statut : expérience, sur une branche séparée, **non fusionnée**. Elle ne sera proposée à la fusion que si le rejeu
avant/après ne montre aucune régression.

## Problème

`describe` publie, pour chaque opération, ses **arguments** (`backend/app/protocol/application/exchange.py`,
`_ARGUMENTS`), pas son **usage**. Un petit modèle (Gemini Flash-Lite) choisit alors mal : une Tuile `security/1` sur
une méthode pour une question sur une route, une méthode cherchée quand la question nomme une route HTTP, un sens de
relation inversé. Un premier essai, un guide d'environ 1,2 Ko sur les 19 relations ajouté aux consignes, a dégradé
le test 9 du banc.

## Hypothèse mesurée

Une note **courte**, jointe à chaque opération par Minia, aide le modèle à choisir l'opération et la référence, sans
lui imposer un catalogue. Elle se mesure : octets ajoutés, puis rejeu avant/après.

## Comportement attendu

- Minia joint une note (`note`) à `describe`, `find_references`, `get_neighborhood`, `find_facts` et
  `verify_claim` : à quoi sert l'opération, quelle référence elle attend, l'erreur fréquente à éviter
  (`backend/app/minia/domain/operation_notes.py`).
- La note de `get_tile` dit la règle d'ancre générique : choisir un profil dont l'ancre est le type de la référence.
  La liste des profils et de leurs ancres reste celle que publie déjà `offered()`.
- La note de `get_source` reste **telle quelle** ; la distinction « Code lu » n'est pas touchée.

## Invariants

- Le protocole `taxo-query/1`, le contrat MIP et la réponse de `describe` ne changent pas : la note est ajoutée par
  Minia à la liste qu'elle envoie au modèle. La réponse de `describe` transmise dans la trajectoire reste celle de Taxo.
- Une note ne nomme que des relations et des types de référence que Taxo publie (test).
- La somme des notes de `operation_notes.py` reste sous `MAX_NOTES_BYTES` (600 octets) : un guide plus long ne
  revient pas sans que les tests le disent.
- Aucun verdict nouveau : la note de `verify_claim` ne change pas sa sémantique (coexistence décidée le 2026-10-11),
  et le parcours d'enquête ne propose toujours pas `verify_claim`.

## Mesure des octets (hors ligne, sans modèle)

Méthode : la question de `tests/test_minia_source_reading.py` sur son dépôt de démonstration, modèle scénarisé qui
conclut au premier tour ; on mesure la liste `operations` et le premier message réellement envoyés au modèle, sur
`main` (`42fc8d3`) et sur cette branche.

| Mesure | Avant | Après | Écart |
| --- | --- | --- | --- |
| Liste des opérations, sans lecture du code (10 opérations) | 2 699 o | 3 373 o | +674 o (+25 %) |
| Liste des opérations, avec lecture du code (11 opérations) | 3 251 o | 3 925 o | +674 o (+21 %) |
| Premier message, sans lecture du code | 8 961 o | 9 635 o | +674 o (+7,5 %) |
| Premier message, avec lecture du code | 9 657 o | 10 331 o | +674 o (+7,0 %) |
| Consignes (`SYSTEM`) | 3 187 o | 3 187 o | 0 |

La liste repart à chaque tour : une exploration complète (ouverture et 8 opérations au plus, 9 tours) envoie au plus
environ 6 Ko de plus. C'est la moitié du guide de 1,2 Ko par tour, et environ 170 jetons par tour. Pour un modèle
dont Taxo connaît la fenêtre (Ollama), ces octets sont retirés de la place des réponses de Taxo, jamais ajoutés
au-delà.

## Rejeu avant/après

Questions : `backend/scripts/minia_bench_operations.json`, les questions 5 (`findStudents`), 9 (STUDENT et
`GET /api/students`) et 13 (mots de passe en dur) du banc de référence, à l'identique, et la question 19 « Quelle
route HTTP permet de lister les étudiants ? ». Le tableau de comparaison du banc dit maintenant aussi les opérations
refusées, les replis en mode paquet et l'exactitude **par question**.

Commandes, depuis `backend`, avec le dépôt `student-course-demo` et le fournisseur Gemini configuré comme pour
Taxo (`MINIA_GEMINI_MODEL`, `GEMINI_API_KEY`) :

```
git worktree add ../../taxo-avant origin/main
python scripts/minia_bench.py <student-course-demo> --provider gemini --runs 3 --source \
  --questions scripts/minia_bench_operations.json --app ../../taxo-avant/backend --label avant \
  --out avant.json --payloads avant.jsonl
python scripts/minia_bench.py <student-course-demo> --provider gemini --runs 3 --source \
  --questions scripts/minia_bench_operations.json --label apres --out apres.json --payloads apres.jsonl
python scripts/minia_bench.py --compare avant.json apres.json
```

Le rejeu n'a pas été fait dans l'environnement de développement : il n'y a ni clé de fournisseur ni dépôt
`student-course-demo`. Selon la règle du banc, le récit n'en dépend pas pour avancer ; son résultat décide seulement
de la proposition à la fusion. Une régression sur une question donnera une note révisée ou l'abandon de l'expérience.

## Limites

- Les notes sont écrites en français, comme les consignes de Minia.
- `find_references` cite `endpoint` et `symbol` comme exemples : ce sont des types du contrat (ARCHITECTURE § 5),
  pas des notions d'un cadre.
- Seul le parcours d'exploration reçoit les notes des cinq opérations. Le parcours d'enquête reçoit seulement la
  règle d'ancre de `get_tile`, partagée par `tiles.offered()`.
- La question 19 vérifie la présence de `/api/students` et de `GET` dans la réponse affichée ; sa vérité vient de la
  vérité du banc, pas d'une relecture des sources.

## Hors périmètre

- Toute modification du protocole, de `describe`, du contrat MIP ou des profils.
- Le guide des 19 relations, qui n'est pas réintroduit.
- Les notes de `get_coverage`, `get_commit`, `get_diff`, `diff_facts` et `get_evidence`, dont les arguments disent
  déjà l'usage.
- Les notes dans le parcours d'enquête : un futur récit si le rejeu montre un gain.
