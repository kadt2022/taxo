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
| `target.reference` | oui | Une référence **résolue** par Taxo (par exemple par `find_references`). Le MIP ne devine jamais une référence. |
| `analysis` | non | Sans lui, la dernière analyse ; elle est rendue dans `snapshot.analysis` et doit être renvoyée aux étapes suivantes. |
| `relations` | oui | 1 à 16 relations distinctes ; leur vocabulaire est vérifié par `get_neighborhood`. |
| `direction` | oui | `INCOMING`, `OUTGOING` ou `BOTH`. Aucun défaut caché. « Qui appelle X ? » : `CALLS`, `INCOMING`. |
| `bounds` | non | `depth`, `max_nodes`, `max_facts`, `max_bytes` : entiers positifs. Une valeur au-dessus du plafond du serveur est **plafonnée**, pas refusée. Sans valeur, le défaut du moteur. |
| `continuation` | non | La reprise d'une frontière `SELECTION` d'une Tuile précédente, avec les mêmes `relations`, `direction` et `analysis`. |

Tout autre champ, tout type faux et toute valeur hors du contrat donnent `INVALID_ARGUMENT`.

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

Lecture honnête d'une Tuile :

- `root.known = false` : la référence n'est pas dans **cette analyse**. Ce n'est pas une preuve qu'elle n'existe pas
  dans le dépôt.
- `stop_reason = DEPTH` : la profondeur demandée est atteinte. C'est une borne choisie, pas une troncature.
- `truncated = true` : la Tuile ne dit pas tout faute de place. Une reprise est dans `frontier`.
- Une zone `NOT_INTERPRETED` est une lacune, jamais une absence d'appel.

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

`PROJECT` servie, recherche par nom (PR A2), autorisations par consommateur, capsule de Tuile autonome, transport MCP.
