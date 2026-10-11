# TAXO-MINIA-ENQUETE-01 — Lot D : inventaire de `verify_claim` et proposition de compatibilité

**Statut :** PROPOSITION, en attente d'arbitrage du responsable du produit (ROUGE protocole).
**Date :** 11 octobre 2026.
**Récit :** [TAXO-MINIA-ENQUETE-01](TAXO-MINIA-ENQUETE-01-memoire-de-parcours.md), § 10 « Transition avec `verify_claim`
et `taxo-query/1` », AC-17, et choix de mise en œuvre retenus à l'acceptation.

Ce document ne change aucun code. Il recense où `verify_claim` et ses verdicts sont utilisés, état de `main` au
11 octobre 2026 (commit `d76c24f`), et propose une transition. Aucune option ne sera engagée sans arbitrage écrit.

## 1. Ce que fait `verify_claim` aujourd'hui

`verify_claim` est une opération de `taxo-query/1` (§ 12.3 et § 12.4 d'ARCHITECTURE). Elle reçoit une affirmation
**structurée** (`subject`, `relation`, `object` facultatif) et rend `CONFIRMED`, `REFUTED` ou `NOT_PROVEN` avec une
raison (`NOT_FOUND_IN_ANALYSED_SCOPE`, `NOT_INTERPRETED`, `NOT_ANALYSED`), les faits, les preuves et des `limits`.

Le verdict porte sur la **présence d'un triplet dans la Maille**, pas sur un raisonnement. Ce qui heurte INV-01, c'est
l'usage qu'en fait Minia : chaque `claim` du modèle est soumis à `verify_claim`, puis l'écran l'affiche sous
« Affirmations vérifiées par Taxo », « Confirmée par Taxo », « Contredite par Taxo ». Le lecteur comprend que Taxo
juge la conclusion du modèle.

## 2. Inventaire

### 2.1 Protocole et contrat

| Endroit | Usage |
| --- | --- |
| `backend/app/protocol/application/exchange.py` | opération `verify_claim` (version `V1`, arguments `_CLAIM_ARGUMENTS`, table des opérations, liste proposée par `describe`) |
| `backend/app/protocol/domain/verdict.py` | `judge` : règles des trois verdicts et de leurs raisons (73 lignes) |
| `backend/app/knowledge/…`, `backend/app/neighborhood/application/knowledge_frontier.py`, `backend/app/comparison/application/compare.py` | lisent la même connaissance des analyseurs que le verdict ; pas d'appel à `verify_claim` |
| MIP 0.1 (`backend/app/mip/`) | ne sert que `EXPAND` ; la correspondance `VERIFY` = `verify_claim` n'existe que dans la documentation |

### 2.2 Consommateurs

| Consommateur | Usage | Touché par le récit ? |
| --- | --- | --- |
| Minia, question sur un commit (`about_commit_events` → `_explore` → `_verified`) | chaque `claim` du modèle passe par `verify_claim` avant affichage, au plus `MAX_CLAIMS` | oui : verdict sur une conclusion du modèle |
| Minia, question sur le projet (`about_project_events` → `_explore` → `_verified`) | idem | oui |
| Minia, exploration (`exploration.SYSTEM`) | le modèle peut appeler `verify_claim` comme toute opération proposée ; le prompt lui demande des `claim` vérifiables | oui |
| Minia, enquête (lot C, PR #134, **non fusionnée**) | `verify_claim` retiré des opérations proposées ; aucune vérification des conclusions | conforme une fois #132 à #134 fusionnées ; absent de `main` à ce jour |
| `backend/scripts/minia_bench.py` | deux métriques lisent `statement.verdict` : les `CONFIRMED` faux (affirmation confirmée absente de la vérité établie à la main) et `unjustified()` (affirmations non confirmées) | oui : sans verdict, la première rendrait zéro et la seconde compterait chaque affirmation |
| Client HTTP direct de `taxo-query/1` | documenté dans le README (exemple de requête `verify_claim`) | non, s'il reste inchangé |

### 2.3 Écrans

| Fichier | Usage |
| --- | --- |
| `frontend/src/exploration.tsx` (22 occurrences) | libellés `VERDICTS`, `verdictText`, classes `verdict-*`, bloc « Affirmations vérifiées par Taxo » et « Ce que Taxo a vérifié », libellé d'opération « Vérification d'une affirmation » |
| `frontend/src/minia.tsx` | pied : « Taxo a vérifié chacune de ses affirmations » |
| `frontend/src/query.tsx` | pied : même phrase |

### 2.4 Tests

| Fichier | Occurrences | Objet |
| --- | --- | --- |
| `test_protocol.py` | 25 | contrat de `verify_claim` (confirmation, réfutation exclusive, analyseur absent, refus) |
| `test_verdict_limits.py` | 19 | limites et budget de la réponse |
| `test_coverage_bounds.py` | 19 | `NOT_ANALYSED` / `NOT_FOUND_IN_ANALYSED_SCOPE` selon la couverture |
| `test_knowledge_divergences.py`, `test_knowledge_coherence.py`, `test_behaviour_snapshot.py`, `test_mip_profiles.py`, `test_multi_executions.py`, `test_analysis_knowledge.py` | 27 au total | cohérence verdict / voisinage / couverture, instantané de comportement |
| `test_minia_explore.py`, `test_minia_general.py`, `test_minia_tiles.py`, `test_minia_source_reading.py`, `test_minia_confidentiality.py`, `method_security_sources.py` | 26 au total | Minia appelle `verify_claim` et affiche le verdict |
| `test_minia_bench.py` | 3 | métriques fondées sur le verdict |
| `frontend/src/exploration.test.tsx`, `frontend/src/minia.test.tsx` | 33 | rendu des verdicts |

### 2.5 Documentation

`README.md` (tableau des opérations, exemple, section Minia « Frontière preuve / texte libre »),
`docs/ARCHITECTURE.md` § 12.0, § 12.3, § 12.4 (« Minia propose, Taxo vérifie »), récits TAXO-COV-01, TAXO-01N,
TAXO-ARCH-REF-01 et récits terminés (historique, à ne pas réécrire).

## 3. Ce que les lots A à C apportent sans toucher au contrat

Ces lots sont en revue (PR #132 à #134) et **ne sont pas encore sur `main`** : sur `main`, les questions Minia
passent toujours par `_explore` et `_verified`. Le récit ne peut pas se clore sur ce point avant leur fusion.

- Le parcours d'enquête (lots A à C) n'offre pas `verify_claim` et ne rend aucun verdict : il restitue trois zones
  (transmis, exploration et notes, hors exploration) et confronte la déclaration finale au journal des livraisons
  (discordance de traçabilité, jamais réfutation).
- `taxo-query/1`, `verify_claim` et `judge` sont inchangés ; tous les tests ci-dessus passent.

## 4. Options

### Option 1 — Coexistence, protocole inchangé (recommandée)

- `verify_claim` reste dans `taxo-query/1`, sémantique et version inchangées : c'est un contrôle déterministe d'un
  triplet contre la Maille, utile aux clients du protocole et aux tests de cohérence.
- Minia cesse de présenter des verdicts sur les conclusions du modèle dans **tous** ses parcours, par une évolution
  interne à Minia et à l'écran, sans changement de protocole :
  - les questions sur un commit et sur le projet passent au parcours d'enquête (un récit d'écran suit) ;
  - en attendant, l'écran remplace « Affirmations vérifiées par Taxo » et chaque libellé de verdict par une
    formulation descriptive, qui garde la raison rendue par Taxo :

    | Réponse de `verify_claim` | Libellé actuel | Libellé descriptif proposé |
    | --- | --- | --- |
    | `CONFIRMED` | Confirmée par Taxo (par déduction si `INFERRED`) | Correspond à un fait de la Maille (déduit, si `INFERRED`) |
    | `REFUTED` | Contredite par Taxo | Un fait de la Maille porte une autre valeur sur cette relation exclusive |
    | `NOT_PROVEN` + `NOT_FOUND_IN_ANALYSED_SCOPE` | Non prouvée | Aucun fait correspondant là où Taxo analyse |
    | `NOT_PROVEN` + `NOT_INTERPRETED` | Non prouvée | Zone vue par Taxo sans savoir la lire : rien n'est établi |
    | `NOT_PROVEN` + `NOT_ANALYSED` | Non prouvée | Aucun analyseur de Taxo ne couvre cette dimension : rien n'est établi |

    Un `NOT_ANALYSED` ou un `NOT_INTERPRETED` ne se présente jamais comme une recherche faite dans un périmètre
    analysé ;
  - la même transition couvre les autres endroits où l'écran parle encore de verdict ou de vérification :
    - le détail « Ce que Taxo a vérifié » (`frontend/src/exploration.tsx`), qui affiche la valeur brute `verdict` :
      il devient « Ce que Taxo a comparé » et montre le libellé descriptif ci-dessus avec la raison, jamais
      `CONFIRMED` ou `REFUTED` ;
    - le libellé de l'opération `verify_claim` dans la trajectoire (« Vérification d'une affirmation ») devient
      « Comparaison d'une affirmation à la Maille » ;
    - les pieds de réponse de `frontend/src/minia.tsx` et `frontend/src/query.tsx` (« Taxo a vérifié chacune de ses
      affirmations », « sans verdict de Taxo ») disent à la place que chaque affirmation a été comparée aux faits
      de la Maille, et que cette comparaison ne juge pas la conclusion de Minia ;
    - les autres phrases de `frontend/src/exploration.tsx` : « Minia n'a fait aucune affirmation à vérifier »
      devient « Minia n'a fait aucune affirmation à comparer », « Taxo n'a vérifié que : … » devient « Taxo n'a
      comparé que : … », et « Non vérifiable : Taxo n'a pas pu la vérifier » devient « Non comparée : Taxo n'a pas
      pu la comparer à la Maille » ;
    - l'étape de progression émise par `backend/app/minia/application/ask.py` (« Taxo vérifie les affirmations de
      Minia ») devient « Taxo compare les affirmations de Minia à la Maille », et le refus au-delà du plafond
      (« Taxo ne vérifie plus ») devient « Taxo ne compare plus » ;
    - le badge « non vérifié » sur ce que Minia déduit reste : il dit vrai, et ne prête aucun verdict à Taxo ;
  - le banc garde sa mesure de justesse et change seulement ce qu'elle lit :
    - « `CONFIRMED` faux » compare aujourd'hui une affirmation confirmée par Taxo à la vérité établie à la main
      (`security_truth`). Elle devient « affirmation fausse au regard de la vérité établie » : chaque affirmation
      de la réponse est comparée directement à `security_truth`, sans passer par un verdict de Taxo. Une
      conclusion fausse qui cite pourtant un élément réellement livré reste donc comptée comme fausse ;
    - s'y ajoute une mesure de traçabilité, « référence citée absente des livraisons » (discordance de la
      déclaration), qui ne remplace pas la précédente : une citation exacte n'atteste pas une conclusion juste ;
    - `unjustified()` devient « affirmation sans élément MIP déclaré », lue sur la déclaration finale.
- Coût : écran et tests Minia ; zéro risque pour les clients du protocole.

### Option 2 — Dépréciation annoncée

- Comme l'option 1, plus un champ additif `deprecated` sur `verify_claim` dans `describe`, et un retrait prévu dans
  une future `taxo-query/2`.
- Coût : extension additive du contrat ; engage une version future sans incompatibilité démontrée aujourd'hui.

### Option 3 — Nouvelle version `taxo-query/2` sans verdict

- `verify_claim` remplacé par une opération d'observation (« ce triplet est-il dans la Maille, avec quelles
  preuves et quelles limites ») sans vocabulaire de verdict.
- Coût élevé : nouveau contrat, double maintenance, environ 90 références dans les tests de protocole et de cohérence à dédoubler. Aucune
  incompatibilité démontrée ne la justifie aujourd'hui (règle d'équipe : extension additive d'abord).

## 5. Recommandation

Option 1. Elle respecte INV-01 dans tout Minia, ne change pas silencieusement le contrat public (AC-17), et laisse
l'option 2 ouverte si un client externe du protocole apparaît. Le récit TAXO-MINIA-ENQUETE-01 se clôt alors, après fusion des
lots A à C, sur cet inventaire et la décision ; l'écran d'enquête et le retrait des verdicts dans Minia forment un récit
suivant.
