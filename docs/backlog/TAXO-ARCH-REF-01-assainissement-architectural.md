# TAXO-ARCH-REF-01 — Assainissement architectural et responsabilités

Statut : tranche A (audit) rédigée le 2026-10-02, sur `main` à `08bb050` (après TAXO-COV-01 PR A). Frontières
validées le 2026-10-02, avec l'ordre A → C → B → D → E ; `_Neighborhood` et `RunScan` ne sont pas touchés. Les trois
divergences sont corrigées par des PR dédiées avant la tranche C, jamais dans une restructuration.

Règle absolue : à données identiques, mêmes faits, verdicts, comparaisons, enveloppes, limites, erreurs
publiques, réponses API et déterminisme. Un défaut trouvé est documenté et exposé par un test, jamais corrigé
silencieusement dans une restructuration.

## 1. Mesures avant refactoring

Complexité mesurée par complexipy (même métrique que Sonar, environ 3 points plus sévère : `_coverage` du
voisinage valait 21 ici et 18 chez Sonar). Aucune n'est un seuil architectural ; ce sont des indices.

| Module | Lignes | Plus complexes | Imports directs |
| --- | --- | --- | --- |
| `protocol/application/exchange.py` | 568 (dont `Exchange` : 353, 27 méthodes) | `call` 20, `get_diff` 15, `_envelope_coverage` 14, `languages` 10 | 13 |
| `comparison/application/compare.py` | 198 | `summary` 18, `changes` 16, `_producers` 12 | 6 |
| `neighborhood/application/query.py` | 278 | `_accept` 13, `_summaries` 11, `_walk` 11 | 8 |
| `scans/application/run_scan.py` | ~120 | `__call__` 13, `_run` 13 | 12 |
| `evaluations/application/run_evaluator.py` | ~95 | `__call__` 14 | — |
| `scans/infrastructure/sqlalchemy/fact_memory.py` | 336 | `_rank_adjacencies` 16, `add` 12 | — |
| `protocol/domain/verdict.py` | 154 | `reaching` 11, `judge` 10 | — |

Sonar sur la dernière PR : 0 alerte, 97,3 % de couverture du nouveau code, 0 % de duplication.
Tests directement concernés : protocole 27, voisinage 13 + 19 (conformance), comparaison 17 + 7, couverture
bornée 14, Minia exploration 27 (consomme le protocole), architecture 14, moteur 13.

Hors du chantier : `minia/application/ask.py` (555 lignes, Minia est exclu), les analyseurs Java/Spring
(`syntax.py`, `applications.py`, `rules.py` : volumineux mais propres à leur langage, hors du cœur).

## 2. Sens des dépendances

Vérifié sur tout `app/` : aucun module de domaine n'importe l'infrastructure, FastAPI, SQLAlchemy ou une
application ; aucune application n'importe l'infrastructure ni un analyseur concret. Le test
`test_dependency_boundaries` le garde déjà. Aucune inversion à corriger.

Deux couplages ne sont pas visibles dans les imports :

- **Le voisinage lit l'intérieur d'`Exchange`** (19 accès) : `exchange._own` (privé),
  `exchange.service.catalogs`, `exchange.service.languages_of`, `exchange.service.facts`,
  `exchange.scan.result`, `exchange.evaluations`, `exchange.refs`. Il dépend de la forme interne de
  l'échange et du service, pas d'une interface.
- **Le port des faits n'est pas déclaré.** `Exchange.languages` teste `hasattr(self.service.facts, 'objects')`
  parce que deux magasins (`SqlAlchemyFactMemory`, et `SqlAlchemyAnalysisFacts`, qui ne sert plus qu'aux tests)
  n'exposent pas les mêmes méthodes. C'est un port implicite, typé par le canard.

## 3. Constat principal : la connaissance d'une analyse est reconstruite cinq fois

TAXO-COV-01 a nommé quatre notions : langage présent, capacité déclarée, couverture effective, verdict. Elles
n'ont pas de foyer : chaque consommateur les reconstruit.

| Notion | Reconstruite dans |
| --- | --- |
| « zone non lue » (`NOT_INTERPRETED` + `READ_ERROR`) | **7 définitions** : `capability._UNREAD`, `verdict._UNREADABLE`, `exchange._UNREADABLE`, `fact_comparison._UNKNOWN`, `history/domain/impact._UNKNOWN_COVERAGE`, `scans/application/routes.py` (littéral), `neighborhood` (littéral) |
| langages présents | `RunScan.__call__` (calcul), `Exchange.languages` (résultat, sinon `facts.objects`, sinon `query`), `CompareAnalyses._languages` (résultat, sinon `store.languages`), voisinage (résultat seulement) |
| contrat de catalogue (langages lus) | `TaxoQuery.capabilities` + `TaxoQuery._current` + `TaxoQuery.languages_of`, `CompareAnalyses.capabilities` (dictionnaire construit à part dans `bootstrap`), `Exchange.analyzers` (via `_catalog(coverage[0])`) |
| analyseur vu par une analyse (`Analyzer`) | `Exchange.analyzers` (depuis les faits de couverture), `neighborhood._summarized` (depuis les résumés) |
| « a-t-il lu un langage présent ? » | `capability.applicable` (comparaison, moteur) et `Analyzer.reads_present` (verdict) : le même prédicat, deux fois |

Conséquence observée, pas théorique : le P2 de Codex sur #74 (un contrat inconnu pris pour « indépendant du
langage ») venait exactement de là, `None` signifiant « indépendant » à un endroit et « inconnu » à un autre.

### Trois divergences de comportement trouvées (exposées par un test, corrigées par des PR dédiées)

1. **Contrat de catalogue inconnu.** Verdict et voisinage : il ne lit rien de connu (`frozenset()`).
   Comparaison : il est traité comme indépendant du langage (`None`), donc comparé comme avant. C'était un choix
   écrit dans le récit COV-01, mais la même notion a deux politiques. → décision à prendre, correction séparée.
2. **Analyse antérieure à COV-01.** Constaté sur l'analyse de référence de Taxo (`33f0bd0`, ancien code),
   dans un même échange : `verify_claim(endpoint:GET /api/health, HANDLED_BY)` rend `NOT_ANALYSED` et nomme
   Python et TypeScript non analysés ; `get_neighborhood` sur la même route et la même relation ne rend
   **aucune frontière**, parce qu'il ne lit que le résumé, qui ne porte pas les langages, et y voit
   `spring-api` en `SUCCESS`. Le défaut corrigé par COV-01 survit donc dans le voisinage des analyses
   antérieures. → test qui l'expose dans la tranche A, correction séparée.
3. **Contrat d'un résumé antérieur.** Trouvée en préparant la tranche C. Un résumé antérieur à COV-01 ne nomme
   pas le catalogue de ses exécutions. Verdict et restitution (`/coverage`) relisent celui que ses couvertures
   ont enregistré ; le voisinage prenait le catalogue **actuel** de l'analyseur. Quand ce contrat n'est plus
   connu, le verdict nommait Java et Python non analysés, le voisinage Python seul. C'est contraire à la règle
   COV-01 : une couverture se juge selon le contrat de son producteur. → test qui l'expose, correction séparée :
   le voisinage relit le contrat enregistré, `TaxoQuery.languages_of` ne se rabat plus sur le catalogue actuel.
   Invariant relevé à cette occasion : une analyse n'exécute chaque évaluateur qu'une fois. Le registre et
   `RunScan` le garantissent, pas la base (contrainte sur `(scan_id, execution_id)`). Le voisinage ne choisit
   aucune exécution à la place d'une autre : des contrats différents pour un même producteur sont inconnus.
   Le verdict (contrat de la première couverture) et la comparaison (union des contrats) s'appuient sur le
   même invariant sans le dire. Tant qu'il tient, rien ne diverge. `AnalysisKnowledge` (tranche C) portera
   une seule règle pour ce cas.

## 4. Audit par classe

### `Exchange` (`protocol/application/exchange.py`) — concentration réelle

| | |
| --- | --- |
| Responsabilité actuelle | un échange `taxo-query/1` sur une analyse fixée |
| État mutable | `calls`, `used` (budget), `refs` (références F/E), `diff_files/lines/bytes` (limites du diff, § 12.6), caches `_coverage`, `_languages` |
| Entrant | `TaxoQuery.open`, API `taxo-query`, Minia (exploration), voisinage (qui lit son intérieur) |
| Sortant | `service.facts` (port implicite), `service.history`, `service.catalogs/capabilities`, `verdict`, `envelope`, `neighborhood` |
| Règles métier | disponibilité des opérations, consentement et limites du diff, règles de couverture de l'enveloppe, appel du verdict |

Axes de changement indépendants, avec preuves :

1. **Cycle de vie et budget** — `call` (compteur), `_max_bytes`, `used`. Change quand le protocole change ses
   limites (§ 12.5).
2. **Validation, routage, erreurs** — `call` fait tout à la fois : protocole, arguments, `max_bytes`,
   opérations réservées, inconnues, indisponibles, puis `getattr(self, operation)`, puis la traduction de
   trois familles d'exceptions. Complexité 20, la plus haute du module. Change avec l'enveloppe et les codes.
3. **Connaissance de l'analyse** — `coverage`, `languages`, `complete`, `needed`, `analyzers`,
   `_envelope_coverage` (+ `TaxoQuery.capabilities/_current/languages_of`). Exactement ce que COV-01 a
   modifié ; rien à voir avec le transport.
4. **Historique et diff** — `_commit`, `get_commit`, `get_diff` (consentement, fichiers générés, limites
   cumulées avec leur propre état), `diff_facts`. Change avec § 12.6 et avec l'historique ; seule partie qui
   appelle `service.history`.
5. **Opérations sur les faits** — `describe`, `find_facts`, `get_evidence`, `get_coverage`, `verify_claim`,
   et l'assemblage des réponses (`_response`, `_add_fact`, `_add_evidence`, `_add_facts` + `References`).

Ce qui doit **rester ensemble** : l'assemblage des réponses et `References` (une même référence pour un
même fait dans tout l'échange : c'est l'état de l'échange) ; le budget et `call` (le budget est consommé
par appel). `References` est cohésive et autonome : on la garde telle quelle.

### `CompareAnalyses` (`comparison/application/compare.py`) — mélange modéré

| Bloc | Méthodes | Raison de changer |
| --- | --- | --- |
| choisir les analyses (tranche C de 01F) | `choices`, `_choice` | le sélecteur du portail ; partage seulement `projects`, `scans` et `store.commit` |
| contexte et comparabilité | `_analyses`, `_languages`, `_read`, `_producers`, `_side_of`, `_unread` | la politique de capacité (COV-01) |
| calcul et cache | `_compute`, `_differences`, `_kept`, `_lock` | les règles de différence (déjà dans `comparison/domain`) |
| restitution paginée | `summary`, `changes`, `_facts` | l'API |

Le calcul, le cache et la pagination **doivent rester ensemble** : les pages relisent le cache, c'est la
décision 6 de 01F. Le contexte de comparabilité est une copie locale de la connaissance d'analyse (§ 3).
`choices` est un autre cas d'usage logé dans la même classe.

### `_Neighborhood` (`neighborhood/application/query.py`) — cohésive, on la garde

État du parcours (`nodes`, `selected`, `refs`, `work`, `position`, `after`), budget (`limits`, `max_bytes`),
acceptation (`_accept`), continuation (`_cursor`, `_resume`, `binding`) et rendu (`render`, `fits`) changent
**ensemble**, pour une seule raison : l'algorithme de parcours borné et rejouable (§ 9.4). Les séparer
obligerait chaque morceau à connaître l'état des autres. **Décision : aucun découpage.**
Seules les fonctions de module `_coverage`, `_summaries`, `_unread_languages`, `_summarized` relèvent de la
connaissance d'analyse (§ 3), et l'accès à l'intérieur d'`Exchange` est un couplage à retirer.

### `RunScan` (`scans/application/run_scan.py`) — saine, on la garde

`__call__ → _run → _consolidate` est une orchestration lisible : instantané, inventaire principal, filtre des
analyseurs sans rien à lire (COV-01), autres analyseurs, puis persistance dans l'ordre exigé par 01E (instantané,
exécutions, faits, complétude). Ses 12 imports sont des ports. **Décision : aucune modification.**
Remarque sans action : `_consolidate` garde deux chemins de persistance (`provenance is None`), hérités d'avant
01E ; les retirer serait un changement de comportement, hors de ce récit.

### Moteur d'évaluation (`RunEvaluator`, `EvaluatorRegistry`) — sain

`RunEvaluator` valide la sortie, ajoute la provenance, écrit les couvertures du moteur (échec, `UNSUPPORTED`).
Une seule raison de changer : le contrat d'exécution. **Aucune modification.**

### Mémoire des faits (`SqlAlchemyFactMemory`, `SqlAlchemyComparisonStore`) — infrastructure cohésive

Stockage versionné, index de voisinage, lectures bornées. `_rank_adjacencies` (16) est complexe par nature
(rangs d'adjacence). **Aucune modification** ; seul le port lu par le protocole est à déclarer (§ 2).

### Composition (`bootstrap/application.py`) — à simplifier sur un point

Les contrats de catalogue y prennent deux formes : `registry.all()` pour `TaxoQuery`, un dictionnaire
construit à la main pour `CompareAnalyses`. Une seule valeur devrait être construite et injectée.

## 5. Frontières proposées

1. **Connaissance d'une analyse** (domaine, générique) — un foyer unique pour ce que COV-01 a nommé :
   - `Reads` (objet valeur) : *indépendant du langage*, *ces langages*, ou *contrat inconnu*. Trois cas
     explicites au lieu de `None` / `frozenset()` ; la confusion du P2 Codex devient impossible à écrire.
   - `CatalogContracts` (objet valeur) : `(catalog_id, version) → relations, Reads`, construit une fois par
     la composition, injecté dans le protocole, le voisinage et la comparaison.
   - `AnalysisKnowledge` (objet valeur) : langages présents, inventaire complet ou non, exécutions vues
     (statut, relations, couvertures, `Reads`), et les prédicats aujourd'hui dispersés : *a lu un langage
     présent*, *atteint la relation pour ce sujet*, *langages non lus*, *langages inconnus*. Une seule
     définition de « zone non lue ».
   - Un chargeur applicatif construit `AnalysisKnowledge` depuis une analyse et le port des faits, avec des
     lectures bornées (le voisinage l'exige). Le verdict reste dans `protocol/domain/verdict.py` et consomme
     cette connaissance.
2. **Protocole** :
   - `Exchange` garde : cycle de vie, budget, références, assemblage des réponses, opérations sur les faits.
   - `call()` se découpe en *valider la requête* et *traduire l'échec* ; le dispatch devient une table
     explicite `opération → méthode` au lieu de `getattr(self, operation)`.
   - Les opérations d'historique (`get_commit`, `get_diff`, `diff_facts`, leur résolution de commit et les
     compteurs du diff) forment un collaborateur avec son propre état, que l'échange compose.
   - Le voisinage reçoit une interface étroite et publique de l'échange (connaissance, références, port des
     faits, contrôle du projet) au lieu de lire son intérieur.
   - Le port des faits lu par le protocole est déclaré ; le magasin de test l'implémente ; `hasattr` disparaît.
3. **Comparaison** : `choices` devient son propre cas d'usage ; le contexte de comparabilité utilise
   `AnalysisKnowledge` ; calcul, cache et pagination restent ensemble.
4. **Inchangés, et c'est une décision** : `_Neighborhood`, `RunScan`, `RunEvaluator`, la mémoire des faits,
   `References`.

## 6. Patterns : problème → candidat → bénéfice → coût → décision

| Problème observé | Candidat | Bénéfice | Coût | Décision |
| --- | --- | --- | --- | --- |
| `None` vaut « indépendant » ici et « inconnu » là (P2 Codex) | objet valeur `Reads` | l'erreur ne peut plus s'écrire | un petit type | **retenu** |
| la connaissance d'analyse reconstruite 5 fois, deux politiques divergentes | objet valeur `AnalysisKnowledge` + chargeur | une règle unique « absence de preuve ≠ preuve d'absence » | migration de 4 consommateurs | **retenu** |
| `call()` mêle validation, routage, erreurs ; `getattr` comme registre implicite | table `opération → méthode` | ajout et test d'une opération lisibles ; aucune méthode exposée par accident | une table | **retenu (une table, pas de classes)** |
| une classe Command par opération | Command / Handler | — : les opérations partagent l'état de l'échange ; chacune recevrait l'échange entier | 9 classes, de l'indirection | **rejeté** |
| historique et diff : axe et état propres (§ 12.6) | collaborateur composé | le consentement et les limites du diff isolés et testables | un module | **retenu** |
| `hasattr` sur le magasin des faits | Port (`Protocol`) | dépendance explicite | une déclaration | **retenu** |
| politique « contrat inconnu » divergente | Strategy / Policy | — : il faut une décision, pas deux stratégies | — | **rejeté** ; décision séparée |
| cache LRU de la comparaison | extraction | — : dix lignes, utilisées une fois | — | **rejeté** |
| cycle de vie de l'échange | State | — : un compteur suffit | — | **rejeté** |

Aucun Singleton, Service Locator ni héritage introduit.

## 7. Garde-fous proposés (tranche E)

Des invariants, pas des noms de fichiers :

- le domaine n'importe ni infrastructure ni framework (existe : `test_dependency_boundaries`) ;
- le cœur générique (connaissance, verdict, protocole, voisinage, comparaison, moteur) ne nomme aucun
  langage ni analyseur (existe depuis COV-01 ; étendu au nouveau module) ;
- le voisinage n'accède à aucun membre privé de l'échange (analyse de l'AST des accès `exchange._…`) ;
- **cohérence** : sur une même analyse, `verify_claim`, `get_neighborhood` et la comparaison décrivent les
  mêmes langages non lus (invariant de comportement, qui aurait attrapé la divergence 2) ;
- la comparaison ne lit jamais le dépôt (existe : `test_comparing_never_reads_the_repository`).

## 8. Tranches

L'ordre candidat est modifié : la connaissance d'analyse passe **avant** le protocole, parce que c'est elle
qui retire de `Exchange` son axe le plus chargé, et que le voisinage en a besoin pour cesser de lire
l'intérieur de l'échange.

| Tranche | Contenu | Comportement |
| --- | --- | --- |
| **A — Audit** | ce document ; deux tests qui exposent les divergences du § 3 (`tests/test_knowledge_divergences.py`, seule l’assertion divergente est attendue en échec (`divergence`, équivalent strict d’`xfail`) : les étapes préalables restent vérifiées, et la marque devra être retirée quand la divergence sera corrigée) ; mesures | inchangé |
| **C — Connaissance** | `Reads`, `CatalogContracts`, `AnalysisKnowledge`, chargeur ; consommateurs migrés un par un (verdict, enveloppe, voisinage, comparaison) | inchangé : les trois divergences du § 3 sont corrigées avant, à part |
| **B — Protocole** | `call()` découpé, table d'opérations, collaborateur historique, interface étroite pour le voisinage, port des faits déclaré | inchangé |
| **D — Comparaison** | `choices` séparé ; comparabilité via la connaissance | inchangé |
| **E — Garde-fous** | tests d'architecture du § 7, ARCHITECTURE.md (frontières retenues), mesures après | inchangé |
| Correction séparée (divergence 3) | le voisinage d'un résumé antérieur lit le contrat que ses couvertures ont enregistré, jamais le catalogue actuel | **modifié**, annoncé |
| Correction séparée | les deux premières divergences du § 3 : un contrat inconnu n'est jamais comparé (`CONTRACT_UNKNOWN_*`, après `CATALOG_CHANGED`) ; le voisinage d'une analyse antérieure relit ses langages comme les verdicts | **modifié**, annoncé |

Chaque tranche est une PR réversible. Les sorties publiques (enveloppes, verdicts, comparaisons, erreurs)
restent identiques : les tests existants sont la référence, et aucune attente n'est modifiée sans le dire.
