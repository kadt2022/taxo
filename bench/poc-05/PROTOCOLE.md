# Banc TAXO-POC-05 — protocole

*Préparé le 2026-09-27, avant toute exécution. Une fois signé (§ Signature), aucune ligne de ce
dossier ne change. Une modification de Taxo après un résultat ouvre une **nouvelle campagne**,
jamais une correction de celle-ci.*

## La question

> Pour répondre à des questions d'architecture et de sécurité sur un dépôt réel, où Taxo aide-t-il
> un modèle : pendant l'exploration, après elle comme vérificateur, ou nulle part ?

Le banc de 2026-09-19 (POC-01 à POC-04) n'a pas démontré de gain d'exactitude avec les
configurations testées. Celui-ci teste des rôles différents pour Taxo. Il doit pouvoir répondre :
**nulle part**.

## Ce qui est gelé

| Élément | Valeur |
| --- | --- |
| Dépôt analysé | `kadt2022/takibo-iam`, commit `6d9b2144f36749e5664c5139415154ea332159a7` |
| Taxo | SHA de `main` inscrit à la signature (au plus tôt après la fusion de TAXO-ID-01) : `__________` |
| Modèle | un seul modèle et une seule version pour tous les bras, inscrits à la signature : `__________` |
| Budget | par question et par exécution : même plafond de tokens d'entrée et même délai pour tous les bras, inscrits à la signature |

## Les bras

Tous les bras reçoivent le même dépôt au même commit, le même modèle, les mêmes questions, dans le
même ordre, dans une session **fraîche**. Aucun n'a accès au dépôt Taxo ni à ce dossier.

| Bras | Exploration | Taxo | Statut en v0 |
| --- | --- | --- | --- |
| **A — code seul** | lecture et recherche libres dans le dépôt | aucun | exécuté |
| **B — Taxo + lecture ciblée** | opérations Taxo, puis lecture du code des seuls symboles désignés (`get_source`) | pendant | **différé** : `get_source` n'existe pas encore |
| **C₀ — Taxo seul** | opérations `taxo-query/1` existantes (`describe`, `find_facts`, `get_evidence`, `get_coverage`, `verify_claim`, `get_commit`, `get_diff`, `diff_facts`), sans lecture du dépôt | pendant | exécuté |
| **D — code, puis vérification** | comme A | **après** : chaque affirmation vérifiable est soumise à `verify_claim` ; une affirmation non confirmée est marquée « non vérifiée » dans la réponse finale, jamais supprimée ni réécrite | exécuté |

Le bras D mesure « Minia enquête librement, Taxo contrôle ses conclusions ». Son coût propre (les
appels `verify_claim`) est compté à part.

## Consigne commune

> Tu disposes du dépôt Java TAKIBO au commit `6d9b214`. Réponds aux questions de `QUESTIONS.md`
> dans l'ordre. Pour chaque réponse : une conclusion, puis les preuves (fichier et lignes) qui la
> soutiennent. Si tu ne peux pas conclure, dis-le et dis pourquoi : « non déterminable depuis le
> code » est une réponse permise, parfois la seule juste. Ne devine pas.

Bras C₀, en plus :

> Tu n'as pas accès aux fichiers. Tu interroges un outil d'analyse par le protocole `taxo-query/1`.
> Ses faits portent un statut (`OBSERVED`, `INFERRED`), des preuves et des couvertures qui disent ce
> qu'il n'a pas interprété. Ils peuvent être incomplets ou faux.

Bras D, après la réponse :

> Voici le résultat de la vérification de tes affirmations structurées. Garde ta réponse ; marque
> « non vérifiée » chaque affirmation que l'outil n'a pas confirmée.

## Déroulé

1. Signature : SHA de Taxo, modèle, budgets, vérités validées. Commit horodaté.
2. Trois exécutions par bras et par question ; l'ordre des bras est tiré au sort à chaque
   exécution et consigné.
3. Tokens comptés **côté fournisseur** (entrée, sortie, cache distingués). Si un compte exact est
   inaccessible, l'estimation est déclarée comme telle.
4. Notation par une personne, à l'aveugle du bras quand c'est possible, selon `GRILLE.md`.
   **Taxo ne juge pas Taxo** : aucune vérité ni aucune note ne vient de ses faits.
5. Résultats **par question**, régressions comprises, puis médiane et dispersion.

## Décision attendue

| Constat | Décision |
| --- | --- |
| C₀ ou D > A en score, sans perte de sécurité (aucune fausse affirmation de plus) | ouvrir la piste agent (TAXO-01I, appels, `get_source`), puis réexécuter avec B |
| D > A, C₀ ≤ A | Taxo vérificateur : MINIA-11 devient le rôle, la piste d'exploration est gelée |
| A ≥ C₀ et A ≥ D | la piste agent est gelée ; Taxo reste un outil de documentation et d'impact (E1 à E3) |

Les jalons E1 à E3 (structure, dépendances, changements) ne dépendent pas de ce banc.

## Signature

- [ ] Vérités de référence validées par le propriétaire de TAKIBO — date : `______`
- [ ] SHA de Taxo, modèle et budgets inscrits — date : `______`
