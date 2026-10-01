# TAXO-01F — Comparer deux analyses depuis la mémoire, sans relire le dépôt

Statut : rédigé le 2026-10-01. Priorité active du plan ([PLAN](PLAN.md)), après TAXO-01E. Tranche A
en cours : API de comparaison.

Source de vérité : [ARCHITECTURE § 5.2, § 8 et § 15](../ARCHITECTURE.md). En cas de divergence, le
document cible prévaut.

Dépend de : mémoire versionnée (TAXO-01E, terminée). Validation : un banc Git scénarisé dont la vérité
est écrite à la main, jamais Taxo jugeant Taxo.

## Intention

En tant qu'utilisateur de Taxo, je choisis deux analyses déjà faites d'un même projet, A puis B. Taxo
me dit ce qui a changé entre elles, preuves à l'appui, **sans relire le dépôt ni relancer un
analyseur** :

```text
Analyse A (commit 1a2b…) → Analyse B (commit 3c4d…)

12 faits ajoutés
 4 faits disparus
 7 faits modifiés
 3 preuves déplacées
 1 statut changé
 Non comparable : spring-security (catalogue 2 → 3, cause possible : évolution du producteur)
```

Chaque compte s'ouvre sur la liste des faits concernés.

## Pourquoi maintenant

TAXO-01E a séparé l'identité de ses occurrences. Sur la base réelle, 393 075 occurrences répètent
une identité déjà vue ailleurs (ratio 1,54). Comparer deux analyses devient une opération sur des
identités enregistrées. Aujourd'hui, l'impact d'un commit relance chaque évaluateur sur le parent et
sur le commit (`history/application/queries.py`). C'est lent, et cela dépend du dépôt.

## Ce qui existe et est réutilisé, pas reconstruit

| Besoin | Existant |
| --- | --- |
| Règles introduit, retiré, modifié | `history/domain/impact.py` : `compare` (même sujet et même relation, un seul retiré et un seul introduit → modifié) |
| Non comparable | `same_schema` : catalogues différents pour un évaluateur → non comparable, jamais calculé |
| Zones inconnues | `unknowns` : couvertures `NOT_INTERPRETED`, `READ_ERROR` |
| Identités et occurrences | `fact_identities`, `fact_occurrences`, `fact_evidence`, `producer_executions` (TAXO-01E) |
| Preuves et faits rendus exactement | `SqlAlchemyFactMemory` |

## Définitions (normatives)

Pour un évaluateur comparable, avec I(A) et I(B) les identités de chaque analyse :

| Résultat | Règle |
| --- | --- |
| **Ajouté** | identité dans I(B) seulement, sauf si elle forme une modification |
| **Disparu** | identité dans I(A) seulement, sauf si elle forme une modification |
| **Modifié** | assertion de même sujet et même relation : exactement une disparue et une ajoutée (règle actuelle) |
| **Inchangé** | même identité des deux côtés, quelles que soient ses preuves, son statut ou sa validité ; compté, jamais listé |
| **Preuve déplacée** (`EVIDENCE_CHANGED`) | parmi les inchangés : preuves différentes (chemin, lignes, symbole, empreinte, méthode ; jamais le commit) ; les deux preuves sont rendues |
| **Statut changé** | parmi les inchangés : statut ou validité différent ; les deux valeurs sont rendues |

- L'inchangé se définit **au niveau de l'identité**. Un fait dont seule la preuve se déplace, ou dont
  seul le statut change, compte parmi les inchangés **et** dans son signal à part. Les signaux ne
  retirent rien au compte des inchangés.
- **Non comparable** : si les catalogues d'un évaluateur diffèrent entre A et B, ses faits ne sont pas
  comparés. La réponse le dit, avec « cause possible : évolution du producteur ». Un changement de
  producteur n'est jamais présenté comme un changement du logiciel.
- Un évaluateur présent d'un seul côté : non comparable, avec sa raison.
- **Exécution en échec** : si l'exécution d'un évaluateur a échoué (`FAILED`) dans A ou dans B, ses
  faits ne sont pas comparés. La raison est « exécution en échec dans A » (ou B), comme le fait déjà
  l'impact actuel. Sinon, chaque fait de l'autre côté passerait à tort pour ajouté ou disparu. Une
  exécution partielle (`PARTIAL`) reste comparable, avec ses zones inconnues rendues. Le statut vient
  du résumé enregistré de l'analyse.
- Les couvertures ne sont pas des changements. Les zones non interprétées de chaque côté sont rendues
  à part.
- Les deux analyses doivent appartenir au même projet. Sinon, refus.
- Le sens compte : A → B n'est pas B → A. Ajouté et disparu s'échangent, rien d'autre ne change.

## Exigences

1. **Aucune lecture du dépôt, aucun évaluateur exécuté.** Un test le prouve : lecteur d'instantané
   et exécuteur interdits.
2. **Calcul sur les identités enregistrées.** Les ensembles sont comparés dans la base, par
   `identity_hash`. Seuls les faits des listes demandées sont reconstruits. Comparer deux analyses de
   500 000 faits ne charge jamais les deux analyses entières en mémoire.
3. **Comptes d'abord, listes paginées ensuite**, triées de façon stable, avec reprise.
4. **Déterminisme** : mêmes analyses, même réponse.
5. **Rien d'inventé** : ni pourcentage ni score, seulement des comptes. Chaque fait listé ouvre sa
   preuve.
6. **SQLite et PostgreSQL**, comme toute la mémoire.

## Tranches

Un seul récit ; chaque tranche est une PR.

### A — Comparaison depuis la mémoire (API)

- Cas d'usage `CompareAnalyses(projet, A, B)` et opération de lecture sur la mémoire. Les ensembles
  d'identités et les différences d'occurrences sont calculés en SQL.
- API : comptes par catégorie et par évaluateur, non comparables avec leur raison, zones inconnues,
  puis listes paginées par catégorie.
- **Banc Git scénarisé**, avec la vérité écrite à la main pour chaque transition :
  - commits A, B et C sur un petit projet Spring : une route ajoutée, une route retirée, une
    autorisation modifiée, une méthode déplacée de quelques lignes, un fichier non interprété ;
  - deux versions d'un même évaluateur sur un même commit, pour le non comparable ;
  - A → B, B → C, A → C et B → A.
- Mesure sur la base réelle : comparer deux grosses analyses du même projet, avec durée et mémoire,
  publiées telles quelles.

### B — Portail

- Depuis la vue d'ensemble : « Comparer avec… » une autre analyse du projet.
- Écran « Analyse A → Analyse B » : commits et dates, comptes par catégorie, non comparables et zones
  inconnues visibles, chaque compte ouvrant sa liste. Une preuve déplacée montre l'avant et l'après.
- Comptes seulement, aucun pourcentage. Minia n'intervient pas dans cet écran.

### C — Impact d'un commit sans relire le dépôt

- Si le commit et son parent ont chacun une analyse enregistrée, l'impact du commit est calculé par la
  tranche A, sans exécuter d'évaluateur.
- **Choix des analyses, déterministe** : pour chaque commit, la plus récente analyse en mode `COMMIT`
  de ce commit exact. Un commit analysé plusieurs fois donne toujours la même paire tant qu'aucune
  nouvelle analyse n'est faite. La réponse nomme les deux analyses utilisées. L'API accepte aussi deux
  identifiants d'analyse explicites. Les règles de comparabilité (catalogue, échec) s'appliquent
  ensuite, évaluateur par évaluateur.
- Sinon, le comportement actuel est conservé et la réponse dit qu'il a fallu relire le dépôt.

## Hors périmètre

- Moteur de validité (`STALE`, `REVALIDATION_REQUIRED`) et validations humaines.
- Comparaison entre projets différents.
- Retrait d'`analysis_facts`.
- Explication des changements par Minia.

## Décisions (2026-10-01)

1. **Occurrences multiples** : pour une identité, les occurrences sont un multiensemble. Nombres
   différents : `OCCURRENCE_COUNT_CHANGED` (2 → 3). Preuve et statut ne sont comparés occurrence par
   occurrence que si chaque côté en a une seule. Nombres égaux mais plusieurs occurrences : si leurs
   contenus diffèrent, `OCCURRENCES_CHANGED`, les deux côtés rendus. Aucun appariement arbitraire.
   Le contenu comparé comprend tout ce que dit l'occurrence (preuves, statut, validité, dérivation,
   validation, raison, graphie) : une seule occurrence de chaque côté dont seul ce reste change est
   aussi `OCCURRENCES_CHANGED`.
6. **Pages** : une analyse complète ne change plus. Une comparaison calculée est gardée (les identités
   de ses différences seulement, pour quelques comparaisons), et les pages suivantes ne relisent pas
   les analyses.
2. **Même catalogue, nouvelle version de producteur** : comparable. La version est rendue comme
   contexte de provenance, jamais comme changement du logiciel.
3. **`WORKING_TREE`** : comparable, l'empreinte de contenu est affichée à la place du commit. Une
   empreinte identique ne supprime pas la comparaison : ce sont deux analyses distinctes.
4. **Analyses comparables** : seulement les analyses dont la mémoire est complète ; une consolidation
   interrompue n'est jamais comparée.
5. **Indépendance** : comparer A et B ne dépend pas de la taille d'une troisième analyse C. Toute
   lecture passe par un index lié à A ou à B.
