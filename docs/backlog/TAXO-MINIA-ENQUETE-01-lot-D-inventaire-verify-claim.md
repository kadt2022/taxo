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
| Minia, enquête (lot C, #134) | `verify_claim` retiré des opérations proposées ; aucune vérification des conclusions | déjà conforme |
| `backend/scripts/minia_bench.py` | mesure les verdicts `CONFIRMED` faux (affirmation confirmée absente de la vérité établie à la main) | oui, si les verdicts disparaissent de Minia |
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
| `test_minia_bench.py` | 3 | métrique des `CONFIRMED` faux |
| `frontend/src/exploration.test.tsx`, `frontend/src/minia.test.tsx` | 33 | rendu des verdicts |

### 2.5 Documentation

`README.md` (tableau des opérations, exemple, section Minia « Frontière preuve / texte libre »),
`docs/ARCHITECTURE.md` § 12.0, § 12.3, § 12.4 (« Minia propose, Taxo vérifie »), récits TAXO-COV-01, TAXO-01N,
TAXO-ARCH-REF-01 et récits terminés (historique, à ne pas réécrire).

## 3. Ce qui est déjà fait sans toucher au contrat

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
  - en attendant, l'écran remplace « Affirmations vérifiées par Taxo » / « Confirmée par Taxo » par une formulation
    descriptive (« Correspond à un fait de la Maille », « Aucun fait correspondant dans le périmètre analysé ») ;
  - le banc remplace la métrique « `CONFIRMED` faux » par « référence citée absente des livraisons ».
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
l'option 2 ouverte si un client externe du protocole apparaît. Le récit TAXO-MINIA-ENQUETE-01 se clôt alors sur les
lots A à C, cet inventaire et la décision ; l'écran d'enquête et le retrait des verdicts dans Minia forment un récit
suivant.
