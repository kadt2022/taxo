# MIP 0.1 — contrat de lecture d'une Tuile

**Version :** `mip/0.1`. **Récit :** [TAXO-01N / MIP-01](backlog/TAXO-01N-ask-taxo-general.md), PR A.
**Architecture :** ARCHITECTURE § 12.0.

MIP 0.1 permet à un consommateur, avec ou sans modèle de langage, de demander une **Tuile bornée** autour d'une
référence de la Maille. Il ne lit que la Maille. Il n'a qu'un moteur, celui de `taxo-query/1` :

`MIP 0.1 → adaptateur (app/mip) → get_neighborhood de taxo-query/1 (neighborhood/2) → Maille`

Ce n'est pas un second protocole (ARCHITECTURE § 12.3) : une requête MIP devient exactement une opération
`get_neighborhood`, dont la validation, les budgets et les codes d'erreur s'appliquent tels quels. L'adaptateur ne
lit que la forme de sa propre requête et plafonne les bornes. `EXPAND` a trois formes, toutes servies par
`get_neighborhood` : la première Tuile autour d'une référence (TILE, § 9.5) ; l'extension depuis un nœud de frontière
arrêté par la profondeur ou non atteint (`DEPTH`, `NOT_REACHED`, sans jeton), demandée comme une nouvelle Tuile
centrée sur ce nœud, avec sa profondeur restante ; la reprise d'une adjacence coupée par un budget, avec le jeton
`continuation` de sa frontière (l'EXPAND du § 9.5).

Ce document fige le contrat servi. Ce qui n'y est pas écrit n'est pas servi.

## 1. Relevé du moteur (avant la PR A)

Le contrat est relevé sur le code réel. Les chemins et noms ci-dessous sont ceux du dépôt au moment de la PR A.

| Point | Constat |
| --- | --- |
| Entrée du moteur | `Exchange.call` (`protocol/application/exchange.py`) → `get_neighborhood` → `neighborhood()` (`protocol/application/neighborhood_operation.py`). |
| Lecture de la demande | `read_demand` (`protocol/application/neighborhood_request.py`). `engine: neighborhood/2` est passé explicitement. `follow` + `direction` (`BOTH` admis en V2) traduisent `relations` + `direction`. |
| Plafonds | `V2_CEILINGS` : `depth` 4, `max_nodes` 200, `max_edges` 400 (défauts du moteur : 1, 30, 60). Octets : `DEFAULT_OPERATION_BYTES` 8 000, `MAX_OPERATION_BYTES` 32 000 (`exchange.py`). |
| Présentation | `LayeredView` (`protocol/application/neighborhood_view.py`) : `anchor`, `node_details`, `items` (avec `via`, `level`, `occurrence`, preuve résumée), `frontier`, `coverage`, `bounds`, `consumed`, `stop_reason`, `not_sent`. |
| Frontières | `SELECTION` (coupe ou nœud non développé, avec sa reprise), `CONTEXT` (`NO_ANALYZER`), `KNOWLEDGE` d'analyse (`ANALYSIS_INCOMPLETE`, `NOT_ANALYSED`…) et de nœud (`NOT_INTERPRETED`, `READ_ERROR`, avec `causes` et `categories` TAXO-01M). |
| Reprise | Par entrée de frontière `SELECTION` (`continuation`), et pour l'arrêt lui-même quand il en a une, liée à la version du moteur, à l'instantané, aux pas et à la révision des faits (`neighborhood/domain/continuation.py`). Pas de reprise globale. |
| Référence absente | Réponse `OK`, `anchor.known = false`, `stop_reason = ROOT_UNKNOWN`. Aucun code `NOT_FOUND`. |
| Codes d'erreur | `INVALID_ARGUMENT`, `NO_CONSENT`, `NOT_AVAILABLE`, `OUT_OF_SCOPE`, `BUDGET_EXHAUSTED`, `INTERNAL` (`protocol/domain/envelope.py`). |
| Accès | Projet inconnu : 404 ; aucune analyse ou analyse inconnue : 409. Taxo n'a pas d'authentification : il écoute sur `127.0.0.1` (`compose.yaml`). MIP n'élargit pas cette surface. |

Écart avec l'exemple illustratif du récit : les noms suivent ceux du protocole existant (`reference`,
`max_nodes`), en minuscules séparées par `_`, et la cible ne porte pas de `kind` (le préfixe de la référence le dit
déjà). Aucun nom du domaine de la Maille n'est changé.

## 2. Requête

`POST /api/projects/{project_id}/mip/query`, ou `MipService.query(project_id, requête)` sans serveur HTTP.

```json
{
  "mip": "mip/0.1",
  "expression": "EXPAND",
  "target": {"reference": "symbol:java:com.example.demo.service.CourseService#register(String)"},
  "analysis": "<analyse rendue par une étape précédente>",
  "relations": ["CALLS"],
  "direction": "INCOMING",
  "bounds": {"depth": 2, "max_nodes": 50, "max_facts": 100, "max_bytes": 16000},
  "continuation": "<reprise d'une frontière SELECTION>"
}
```

| Champ | Obligatoire | Règle |
| --- | --- | --- |
| `mip` | non | `mip/0.1` s'il est donné. |
| `expression` | oui | `EXPAND` est servie. `PROJECT` est refusée : `NOT_AVAILABLE`. |
| `target.reference` | oui | Une référence **résolue** par Taxo, par exemple par `find_references`, y compris par nom (`match: NAME`, PR A2). Le MIP ne devine jamais une référence. |
| `analysis` | non | Sans lui, la dernière analyse ; elle est rendue dans `snapshot.analysis` et doit être renvoyée aux étapes suivantes. |
| `relations` | oui | 1 à 16 relations distinctes ; leur vocabulaire est vérifié par `get_neighborhood`. |
| `direction` | oui | `INCOMING`, `OUTGOING` ou `BOTH`. Aucun défaut caché. « Qui appelle X ? » : `CALLS`, `INCOMING`. |
| `bounds` | non | `depth`, `max_nodes`, `max_facts`, `max_bytes` : entiers de 1 à 10⁶. `max_bytes` vaut pour la Tuile MIP telle qu'elle est reçue : si elle ne tient pas, `BUDGET_EXHAUSTED`. Une valeur au-dessus du plafond du serveur est **plafonnée**, pas refusée. Sans valeur, le défaut du moteur. |
| `continuation` | non | La reprise d'une frontière `SELECTION` d'une Tuile précédente, avec les mêmes `relations`, `direction` (ou le même `profile`) et `analysis`. |
| `profile` | non | Un profil déclaré (§ 2.1). Il remplace `relations` et `direction`, qui sont alors interdits. |

Tout autre champ, tout type faux et toute valeur hors du contrat donnent `INVALID_ARGUMENT`.

### 2.1 Profils de Tuile adaptative (TAXO-MIP-ADT-01, PR A)

Champ facultatif et additif : une requête sans `profile` est servie exactement comme avant. Un profil est un
manifeste fermé et versionné (`app/mip/domain/profiles.py`, ARCHITECTURE § 9.5) : types d'ancre acceptés, pas suivis
(relation et sens, dans leur ordre de priorité), chacun nommé par sa règle, profondeur par défaut, preuves résumées, et
limites connues. Il se résout en `steps` et `depth` de `neighborhood/2` : la même demande écrite en mode explicite
rend la même sélection, dans le même ordre. `bounds.depth` remplace la profondeur du profil. Un profil inconnu, ou une
ancre d'un type qu'il n'accepte pas, donne `INVALID_ARGUMENT`. `PROJECT` reste refusée.

| Profil | Ancre | Pas (règle) | Profondeur |
| --- | --- | --- | --- |
| `method-context/1` | `symbol` | `CONTAINS` entrant (`owner`), `ANNOTATED_WITH` sortant (`annotations`), `CALLS` sortant (`callees`) et entrant (`callers`), `IMPLEMENTS` sortant (`implemented-method`) et entrant (`implementations`) | 1 |
| `calls/1` | `endpoint`, `symbol` | `HANDLED_BY` (`handler`), `CALLS` (`callees`), `DISPATCHES_TO` (`dispatch`), sortants | 2 |
| `structure/1` | `module`, `application` | `CONTAINS` (`members`), `DEPENDS_ON` (`dependencies`), `BUILT_FROM` (`built-from`), sortants | 1 |
| `security/1` | `endpoint` | `HANDLED_BY` (`handler`), `SERVED_BY` (`application`), `MATCHED_BY` (`route-rule`), `AUTHORIZED_BY` (`authorization`), `PROTECTED_BY` (`protection`), sortants | 2 |

Ce qu'un profil ne peut pas promettre est dit, jamais tu : une relation sans producteur exécuté (`DISPATCHES_TO`
aujourd'hui) rend la frontière `CONTEXT` `NO_ANALYZER` du moteur ; une relation produite en partie
(`ANNOTATED_WITH`, relevée sur les types et les méthodes Java mais pas sur leurs paramètres ni leurs champs) est
déclarée dans `limits`.
`security/1` est un parcours documentaire : il ne démontre pas qu'une route est protégée.

## 3. Réponse : la Tuile

| Champ | Contenu | Source |
| --- | --- | --- |
| `mip`, `expression`, `outcome` | `mip/0.1`, l'expression, `OK` | — |
| `snapshot` | `{analysis, commit}` : l'instantané de toute la Tuile | échange |
| `root` | `{reference, known}` : la référence demandée, sans substitution | `anchor` |
| `nodes` | nœuds atteints : niveau, parents, développés ou non | `node_details` |
| `facts` | faits de la Maille tels quels (statut, provenance), avec `via`, `level`, `occurrence` et la preuve résumée (`evidence`) | `items` |
| `coverage` | ce qui a été analysé, par producteur | `coverage` |
| `frontier` | limites : coupes et nœuds non développés (avec reprise), analyseur absent, zones non interprétées et leurs catégories | `frontier` |
| `bounds` | `requested` (demandé), `applied` (appliqué après plafonnement), `consumed` (nœuds, faits) | `bounds`, `consumed` |
| `stop_reason` | `ADJACENCY_COMPLETE`, `DEPTH`, `ROOT_UNKNOWN`, ou la coupe (`NODES`, `EDGES`, `WORK`, `BYTES`, `FANOUT`) | `stop_reason` |
| `truncated` | `true` si un budget a coupé la Tuile ou si un élément n'a pas été envoyé | dérivé de `stop_reason` et `not_sent` |
| `not_sent` | ce qui n'a pas tenu dans les octets | `not_sent` |
| `continuation` | la reprise de l'arrêt, quand le moteur en rend une ; sinon `null`, et les reprises sont dans `frontier` | `continuation` |
| `wire` | `taxo-query/1`, `get_neighborhood`, `neighborhood/2`, révision des faits | — |
| `profile` | avec un profil seulement : son manifeste (`id`, `anchors`, `depth`, `steps` avec leur `rule`, `evidence`, `limits`) et `resolved`, les paramètres explicites appliqués par le moteur | profil, `parameters` |
| `facts[].selection` | avec un profil seulement : `rule`, la règle du pas qui a retenu le fait, et `path`, les références des faits parcourus depuis l'ancre jusqu'à lui (`null` si un fait du chemin n'a pas été rendu) | `via`, `node_details.discovered_by` |

| `classification` | toute Tuile `OK` : `version` (`tile-classification/1`), `nature`, `language`, `profile`, `content`, `provenance`, et `commit_metadata` quand des faits Git sont transmis (§ 3.1) | calculée sur la Tuile rendue |
| `disclosure` | toute Tuile `OK` : `version` (`tile-disclosure/1`) et `restrictions`, les protections qui s'appliquent au contenu présent avant un fournisseur de modèle (§ 3.1) | calculée sur la Tuile rendue |

`bounds.applied.max_bytes` est le budget de la Tuile reçue. Le moteur mesure ses propres octets mais ignore ce que
l'adaptateur ajoute (classification, et pour un profil : manifeste, règles, chemins) : si la Tuile dépasse, l'adaptateur la redemande **une fois**, dans un
nouvel échange sur la même analyse, avec un budget moteur réduit de ce surplus. Les deux appels sont déterministes ;
la Tuile rendue est coupée par les octets et le dit (`truncated`). Si elle dépasse encore, ou si le budget ne contient
pas l'enveloppe du moteur, le refus est `BUDGET_EXHAUSTED`.

Lecture honnête d'une Tuile :

- `root.known = false` : la référence n'est pas dans **cette analyse**. Ce n'est pas une preuve qu'elle n'existe pas
  dans le dépôt.
- `stop_reason = DEPTH` : la profondeur demandée est atteinte. C'est une borne choisie, pas une troncature.
- `truncated = true` : la Tuile ne dit pas tout faute de place. Une reprise est dans `frontier`.
- Une zone `NOT_INTERPRETED` est une lacune, jamais une absence d'appel.

### 3.1 Classification et divulgation (TAXO-MIP-ADT-01 § 21 bis)

La classification **décrit** la Tuile rendue ; elle n'en fait pas partie, ne change pas sa sélection et ne duplique
aucun fait. Elle est calculée après la coupe par les budgets : une catégorie est annoncée si et seulement si un
contenu de cette catégorie est transmis. Champs additifs : un consommateur qui les ignore lit la Tuile comme avant.

| Champ | Règle |
| --- | --- |
| `nature` | Le type de la référence centrale, lu dans sa syntaxe : `METHOD` (symbole appelable `…#nom(…)`), `TYPE` (symbole sans membre : la Maille ne distingue pas classe, interface, record ou énumération), `MEMBER` (autre symbole), sinon le type de référence en majuscules (`ENDPOINT`, `COMMIT`, `MODULE`, `FILE`, `ROUTE_PATTERN`…). Vaut aussi pour une ancre inconnue de l'analyse. |
| `language` | Celui que la référence écrit (`symbol:java:…`), sinon celui d'un fait `WRITTEN_IN` transmis, sinon `null`. |
| `profile` | L'identifiant du profil appliqué, ou `null`. |
| `content` | Dans cet ordre, parmi : `FACTS` (au moins un fait), `RELATIONS` (un fait qui relie deux nœuds de la Tuile, jamais une valeur littérale), `EVIDENCE` (une preuve résumée transmise), `CODE_SOURCE`, `COMMIT_METADATA` (un fait `HAS_COMMIT`, `CHILD_OF`, `AUTHORED_BY` ou `CHANGES`), `COVERAGE`, `FRONTIER`. `CODE_SOURCE` n'est jamais annoncé par une Tuile : le code n'y est jamais (ARCHITECTURE § 9.5, règle 6) ; une pièce source sera consultée à part, sous consentement (`get_source`, réservée). |
| `commit_metadata` | Présent avec `COMMIT_METADATA` : nombre de commits et champs Git transmis (`sha`, puis ceux des qualificatifs présents : `authored_at`, `committed_at`, `message`, et `author` seulement si un fait `AUTHORED_BY` est transmis). |
| `provenance` | `snapshot` de la Tuile, `facts_revision`, et les producteurs (identifiant, version) des faits transmis. |

`disclosure.restrictions` est séparé de la classification. `PERSON_IDENTITY` : une référence `person:` est transmise ;
elle est remplacée par un pseudonyme avant tout fournisseur de modèle. `COMMIT_MESSAGE` : un message de commit est
transmis ; ses trailers sont retirés et ses identités pseudonymisées (ARCHITECTURE § 12.6, point 8). Une restriction
décrit une protection à appliquer, jamais ce que le contenu signifie.

Un refus ne transporte aucun contenu : il n'a ni `classification` ni `disclosure`.

## 4. Refus

```json
{"mip": "mip/0.1", "expression": "PROJECT", "outcome": "ERROR",
 "error": {"code": "NOT_AVAILABLE", "message": "..."}}
```

Un refus venu du moteur porte aussi `snapshot`. Les codes sont ceux du registre existant ; aucun n'est ajouté.
Un refus est une réponse du contrat (HTTP 200), sauf un projet inconnu (404) et une analyse absente ou inconnue (409),
comme pour `taxo-query`.

## 5. Garanties

- Lecture seule : aucune écriture, aucune analyse lancée, aucun accès au système de fichiers, aucun diff, aucune
  source (`get_source` n'existe pas).
- Un seul moteur : les faits, nœuds, frontières et couvertures de la Tuile sont ceux de `get_neighborhood`, à
  l'identique (test de parité).
- Aucun modèle de langage n'est requis ni appelé.
- La sémantique se teste sans serveur HTTP (`MipService`).

## 6. Hors de MIP 0.1

`PROJECT` servie, profils au-delà des quatre du § 2.1, autorisations par consommateur, capsule de Tuile autonome, transport MCP.
