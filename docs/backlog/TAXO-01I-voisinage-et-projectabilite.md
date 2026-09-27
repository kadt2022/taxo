# TAXO-01I — Voisinage borné : la première Tuile

Statut : rédigé le 2026-09-17, révisé le 2026-09-27. À réaliser après TAXO-ID-01, sur les faits
existants.

Source de vérité : [T6 et T12 de l'EPIC TAXO-01](EPIC-TAXO-01-fondation-memoire-verifiable.md).

Dépend de : 01E (persistance), 01G (lecture), TAXO-ID-01 (identité des méthodes).
Étalon : [TAXO-POC-01](TAXO-POC-01-verite-de-reference-chaine-autorisation.md). Vocabulaire : ADR 0005.

## Pourquoi ce récit en premier

La Maille existe déjà : les faits enregistrés relient endpoints, handlers, motifs de route,
autorisations, commits et fichiers. Ce récit la rend **navigable** avant d'en étendre la couverture. On
valide ainsi la sélection, les budgets, la frontière et la navigation inverse sans nouvelle relation à
vérifier. On voit aussi où de nouveaux analyseurs seraient utiles.

Aucune relation n'est ajoutée pour la démonstration. En particulier, pas de `CALLS` : il viendra avec
l'ADR 0011.

## Intention

En tant que consommateur de Taxo (Minia, l'API, un test), je demande le voisinage d'une référence dans
une analyse, dans un sens donné. Je reçois une petite Tuile : les faits montrés et, séparément, ce
qu'elle laisse de côté et pourquoi.

## Ce qui existe et est réutilisé, pas reconstruit

| Besoin | Existant réutilisé |
| --- | --- |
| Faits et preuves d'une analyse | stockage des faits (01E), lecture (01G) |
| Limites de connaissance | couvertures `NOT_INTERPRETED`, `READ_ERROR`, `ANALYSED` des évaluateurs |
| Ce qui n'a pas été transmis | `not_sent` du protocole `taxo-query/1` (ADR 0009) |
| Budget de réponse | `max_bytes` et le mécanisme de réponse bornée du protocole |
| Références de faits et de preuves | `F…` / `E…` de l'échange, `get_evidence` |
| Versions | `produced_by` (évaluateur, version, catalogue) sur chaque fait |
| Déductions | `derivation` des faits `INFERRED`, montrée telle quelle |

Ce récit ajoute l'opération de voisinage, l'index par sujet et par objet s'il manque, et la
frontière. Rien d'autre.

## Périmètre

- **Une analyse et une racine.** L'analyse est explicite ; la racine est une référence `type:clé`.
- **Relations explicites.** La requête nomme les relations à suivre. Elles sont validées contre le
  vocabulaire v1 et les catalogues des évaluateurs **exécutés** dans l'analyse, jamais contre les
  relations qui ont au moins un fait enregistré :
  - relation hors du vocabulaire : erreur `INVALID_ARGUMENT` ;
  - relation déclarée par un évaluateur exécuté, sans aucun fait : acceptée, réponse vide
    **couverte**. Par exemple, `HANDLED_BY` sur un dépôt sans contrôleur ;
  - relation du vocabulaire qu'aucun évaluateur exécuté ne produit : acceptée, frontière de contexte,
    réponse `UNKNOWN`.
- **Direction `OUTGOING` ou `INCOMING`.** `BOTH` attendra.
- **Parcours en largeur, ordre stable.** Tri par relation, puis par référence (forme canonique de
  01B), puis par identité de fait.
- **Déduplication des nœuds, conservation des arêtes.** Une arête qui referme un cycle est montrée.
  Un nœud déjà visité n'est pas redéveloppé.
- **Budgets de sortie** : profondeur, nœuds, arêtes, octets sérialisés (frontière comprise).
- **Budget de travail** : un plafond de voisins examinés. Un nœud à fort degré n'est jamais chargé en
  entier pour en rendre trente.
- **Orientation réelle.** En navigation entrante, un fait `A → B` trouvé depuis `B` est rendu
  `A → B`. On ne fabrique jamais un `B → A`.

Forme de la requête, à adapter aux conventions du protocole :

```json
{
  "operation": "get_neighborhood",
  "arguments": {
    "root": "endpoint:GET /api/v1/orgs/{orgCode}/users",
    "follow": ["HANDLED_BY", "MATCHED_BY", "PROTECTED_BY", "AUTHORIZED_BY"],
    "direction": "OUTGOING",
    "depth": 2,
    "max_nodes": 30,
    "max_edges": 60
  },
  "max_bytes": 12000
}
```

Ces valeurs sont initiales, à mesurer : ce ne sont pas des performances promises.

## La Tuile rendue

Elle contient :

- l'analyse, et les paramètres normalisés (bornes appliquées comprises) ;
- la racine, et les nœuds rendus ;
- les faits sélectionnés, dans leur orientation, avec leur référence `F…`, leur statut et, pour un
  fait `INFERRED`, sa dérivation ;
- les preuves résumées (fichier, lignes), le détail restant accessible par `get_evidence` ;
- les budgets consommés et le **motif d'arrêt** ;
- la **frontière**.

### Frontière : trois natures, jamais confondues

| Nature | Exemple | Ce qui la lève |
| --- | --- | --- |
| **Sélection** | profondeur atteinte ; arêtes connues non rendues faute de budget | une nouvelle Tuile, à partir d'un nœud de la frontière |
| **Connaissance** | nœud couvert par un `NOT_INTERPRETED` (mécanisme maison, mapping non résolu) ; `READ_ERROR` | un analyseur, pas un budget |
| **Contexte** | aucun évaluateur ne produit les relations demandées sur ce type de nœud | une capacité à construire ; réponse `UNKNOWN` |

Pour chaque nœud non développé, la frontière nomme la référence et la nature. Les comptes d'éléments
omis sont qualifiés :

- `EXACT` si le moteur les a tous vus ;
- `AT_LEAST` s'il s'est arrêté en lisant ;
- `UNKNOWN` pour une région non analysée, qui n'a pas de nombre connu d'arêtes manquantes.

On n'affiche jamais « 7 omises » si le moteur n'en a vu que 7 avant d'arrêter.

### Trois fins de parcours (T6), et seulement trois

1. **Un fait connu** poursuit la chaîne. Un fait `ABSENCE` correctement couvert la termine sur une
   absence établie : c'est le seul cas où Taxo affirme une absence.
2. **Un mécanisme `NOT_INTERPRETED`** arrête la chaîne en nommant ce qui n'est pas interprété.
3. **`UNKNOWN`** : aucune capacité n'a couvert la question. L'absence de fait ne vaut jamais absence
   du phénomène.

### Réponse vide

Une réponse vide distingue :

- racine inconnue de l'analyse ;
- racine connue, aucune relation demandée trouvée, sur un périmètre couvert par un évaluateur qui
  produit ces relations ;
- analyse insuffisante pour conclure (`UNKNOWN`).

La complétude d'un parcours des **faits enregistrés** n'est jamais présentée comme la complétude du
**voisinage logiciel**.

### Continuation

Pas de curseur général dans cette tranche. Deux reprises seulement :

- **Nœud non développé** (profondeur atteinte) : le consommateur demande une nouvelle Tuile dont il
  est la racine.
- **Liste de voisins coupée** (budget de nœuds, d'arêtes, d'octets ou de travail atteint en parcourant
  les voisins d'un nœud). Redemander une Tuile autour de ce nœud rendrait le même début, dans le même
  ordre : les voisins suivants seraient inatteignables. La frontière porte donc, pour ce nœud, une
  **position de reprise** : la relation, le sens, et la clé de tri du dernier fait examiné. La requête
  accepte cette position (`after`) et reprend strictement après elle, dans le même ordre stable.

La position de reprise vaut pour l'analyse qui l'a produite ; elle est refusée sur une autre. Une
Tuile ne mélange jamais deux analyses.

## Minia

`get_neighborhood` est une opération de `taxo-query/1`. L'ajouter est une évolution de l'ADR 0009 :
la PR qui l'introduit amende la section 5.

- `describe` l'expose avec les relations disponibles dans l'analyse.
- Les limites d'opérations et de volume restent celles de l'échange entier. Une Tuile compte dans
  le budget comme toute réponse.
- Un fait déjà transmis dans l'échange garde sa référence `F…`.

## Démonstrations

1. **Chaîne d'une route.** Sur une fixture Spring (API et sécurité), depuis un endpoint :
   `HANDLED_BY` vers le handler, `MATCHED_BY` puis `AUTHORIZED_BY` vers le gestionnaire, puis arrêt
   sur la frontière de connaissance « mécanisme maison non interprété ». Si la sécurité n'est pas
   fusionnée, la démonstration s'arrête au handler : ce n'est pas un blocage.
2. **Navigation inverse.** Depuis un `file:`, remonter `CHANGES` vers les commits qui le modifient.
3. **Frontière de contexte.** Depuis un `symbol:` de méthode, suivre `CALLS` : aucune capacité ne le
   produit, réponse `UNKNOWN`, jamais « n'appelle rien ».
4. **Graphe pur.** Sur de petites fixtures du moteur, sans évaluateur : cycles, boucles sur un nœud,
   nœud à fort degré, chemins multiples.

La chaîne complète de TAXO-POC-01 jusqu'à `PolicyEvaluator` n'est **pas** un critère de ce récit :
elle demande `CALLS`. Ici, elle s'arrête honnêtement à la frontière.

## Acceptation

1. Une racine et une analyse valides ne rendent que des faits de cette analyse et des relations
   demandées. Une relation d'un évaluateur exécuté sans aucun fait donne une réponse vide couverte ;
   une relation qu'aucun évaluateur exécuté ne produit donne `UNKNOWN`.
2. Les sens entrant et sortant sont corrects, sans fait inverse fabriqué.
3. Les nœuds sont dédupliqués ; les arêtes distinctes sont conservées tant que le budget le permet.
4. Un cycle, ou une boucle sur un même nœud, termine.
5. À paramètres identiques, la sélection et l'ordre sont déterministes.
6. Profondeur, nœuds, arêtes, octets et plafond de travail sont respectés ; la taille est mesurée
   après sérialisation, frontière comprise. Si l'enveloppe minimale ne tient pas, la réponse est une
   erreur explicite, jamais une Tuile amputée en silence.
7. Un nœud à fort degré n'entraîne pas le chargement de tout son voisinage.
8. Chaque coupure est dans la frontière, avec sa nature. Aucun compte exact n'est inventé.
   Une liste de voisins coupée porte une position de reprise ; des reprises successives atteignent
   tous les voisins connus, chacun une seule fois, même quand leur nombre dépasse toute limite de
   réponse.
9. Tout parcours finit sur l'une des trois fins ; un test distingue `ABSENCE` couverte,
   `NOT_INTERPRETED` et `UNKNOWN`.
10. Un fait `INFERRED` rendu montre ses prémisses.
11. Les preuves référencées appartiennent à l'analyse de la Tuile.
12. Minia peut appeler l'opération, puis demander une Tuile autour d'une référence rendue.
13. Le test de projectabilité s'exécute sans aucun modèle de langage et sans relire le dépôt.
14. Un essai sur un dépôt réel rapporte le temps, la taille de réponse et les limites rencontrées. Il
    ne revendique aucune économie de tokens : c'est l'objet de l'essai A/B/C.
15. Les évaluateurs existants ne changent pas.

## Hors périmètre

- Nouvelles relations, dont `CALLS`, `IMPLEMENTS` et `DISPATCHES_TO` (ADR 0011).
- Direction `BOTH`, curseur général (au-delà de la position de reprise), pondération des relations, profils de parcours.
- Recherche de chemins entre deux nœuds.
- Écran de graphe (TAXO-PROJ-API-01), narration (TAXO-ASK-01), maille des tuiles (TAXO-TILES-02).
  Ces trois récits réutiliseront ce voisinage au lieu d'en créer un second.
