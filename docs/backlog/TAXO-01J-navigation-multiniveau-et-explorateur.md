# TAXO-01J — Navigation multiniveau et explorateur de la Maille

Statut : rédigé le 2026-10-03, soumis à revue. Aucune ligne de code avant validation. Étape 5 du
[PLAN](PLAN.md). Ce récit reprend et termine les critères laissés ouverts par
[TAXO-01I](TAXO-01I-voisinage-et-projectabilite.md) : plusieurs niveaux, sens combiné, couverture
locale. Il ajoute le premier usage humain du voisinage : un explorateur dans le portail.

Source de vérité : [ARCHITECTURE § 9, § 10.1, § 11 et § 12](../ARCHITECTURE.md). En cas de divergence,
le document cible prévaut ; ce récit amende § 9 et § 12.3 dans les PR qui livrent.

Dépend de : TAXO-01I (première tranche, livrée), mémoire versionnée (TAXO-01E), couverture bornée
(TAXO-COV-01), connaissance d'une analyse en un seul foyer (TAXO-ARCH-REF-01). Validation : graphes
synthétiques dont la vérité est écrite à la main, un oracle indépendant du moteur, et un essai sur dépôt
réel. Jamais Taxo jugeant Taxo.

## Intention

En tant que personne qui découvre ou relit un logiciel, je choisis un nœud de la Maille (une route, un
fichier, un module, un commit), je vois ce qui le relie au reste sur plusieurs niveaux, je développe une
branche, je change de point de départ et je consulte la preuve de chaque lien. Je vois aussi, à chaque
endroit, ce que Taxo ne montre pas et pourquoi : profondeur atteinte, budget atteint, zone non lue, aucun
analyseur.

En tant que consommateur programmatique (API, test, Minia), je demande la même chose par le protocole :
une Tuile à plusieurs niveaux, bornée, déterministe, reprenable branche par branche.

Les deux usages passent par **le même moteur et le même contrat**. Taxo reste générique : aucune
relation, aucun type de nœud, aucun framework n'est nommé dans le moteur ou dans l'explorateur ;
tout vient du vocabulaire et des catalogues des évaluateurs exécutés. L'explorateur fonctionne sans
Minia et sans aucun modèle de langage.

## Pourquoi maintenant

- Les fondations sont posées : mémoire versionnée indexée par ancre et par rang, comparaison
  persistée, couverture bornée, une seule définition de ce qu'une analyse sait d'elle-même.
- Le voisinage n'est aujourd'hui utilisable que par le protocole, à un saut. La connaissance de Taxo
  n'est pas encore **parcourable** par une personne.
- L'Arbre, la Forêt, les chemins entre domaines et les Tuiles adaptatives (§ 9.5, § 10, § 11)
  réutiliseront ce parcours multiniveau. Il doit exister, être juste et mesuré avant elles.

## Ce qui existe et est réutilisé, pas reconstruit

| Besoin | Existant réutilisé |
| --- | --- |
| Parcours borné, ordre stable, budgets, frontière à trois natures, reprise liée | `app/neighborhood/application/query.py` (`neighborhood/1`, à un saut) |
| Adjacence indexée, entrante et sortante, rangs matérialisés à l'ingestion | `FactReading.neighbor`, index `ix_fact_occurrences_outgoing` / `_incoming` (TAXO-01E) |
| Existence d'une ancre | `FactReading.has_reference` |
| Génération des faits d'une analyse | `FactReading.revision` |
| Ce que l'analyse sait lire, langages non lus, analyseurs capables | `AnalysisKnowledge`, `from_summary`, `UNREAD_COVERAGE` (TAXO-ARCH-REF-01) |
| Enveloppe bornée, références `F…`/`E…`, `not_sent`, budget d'échange | protocole `taxo-query/1`, `Response`, `Exchange` |
| Preuves d'un fait | `get_evidence` |
| Relations disponibles d'une analyse | `describe` |
| Vocabulaire, libellés | `app/facts/domain/fact.py` (`RELATIONS`), `frontend/src/vocabulary.ts` |
| Pages du portail, routeur par hash, sélecteur d'analyse | TAXO-UI-05, `nav.ts`, `pages.tsx`, TAXO-01F tranche C |

Le moteur à un saut **devient** le moteur multiniveau : on l'étend, on n'en écrit pas un second. Une
requête `depth: 1` actuelle doit rendre exactement la même réponse qu'aujourd'hui (non-régression
prouvée par l'instantané de comportement, ARCH-REF-01 § 9).

## Définitions (normatives)

| Terme | Définition |
| --- | --- |
| **Ancre** | la référence d'où part la Tuile, connue de l'analyse ou non |
| **Pas** | un couple (relation, sens) que le parcours suit ; le sens est `OUTGOING` ou `INCOMING` |
| **Niveau** d'un nœud | sa distance en pas depuis l'ancre, **dans la Tuile rendue**, à sa première découverte (parcours en largeur) |
| **Arête** | un fait d'assertion rendu, dans son orientation réelle. L'unité est l'**identité** du fait : plusieurs occurrences d'une même identité forment une seule arête |
| **Arêtes parallèles** | plusieurs arêtes distinctes entre les deux mêmes nœuds (relations différentes, ou mêmes relations et identités différentes) ; toutes sont conservées tant que le budget le permet |
| **Parents multiples** | un nœud atteint par plusieurs arêtes ; il est rendu une fois, toutes les arêtes qui l'atteignent sont rendues |
| **Revisite** | une arête dont l'autre extrémité est déjà dans la Tuile ; rendue, marquée, jamais redéveloppée. Elle ferme un cycle ou rejoint un parent multiple |
| **Développé** | un nœud dont tous les pas demandés ont été parcourus jusqu'au bout dans cette Tuile |
| **EXPAND** | la même opération relancée depuis un nœud de la frontière de sélection, avec sa position de reprise (§ 9.5, règle 7) |

Le niveau est un fait de la **vue**, pas du logiciel : « à deux sauts dans cette Tuile » ne veut jamais
dire « à deux sauts au plus dans le logiciel ».

## Exigences

### 1. Parcours multiniveau

- `depth` de 1 à **4**, défaut 1 (compatibilité). Valeur initiale, à mesurer ; jamais une promesse.
- Parcours en **largeur**, niveau par niveau. Dans un niveau, les nœuds sont développés dans l'ordre où
  ils ont été découverts ; pour chaque nœud, les pas dans l'ordre de `priority` ; pour chaque pas, les
  voisins dans l'ordre stable existant (référence canonique UTF-16, identité, empreinte d'occurrence).
- Un nœud découvert au dernier niveau n'est pas développé : frontière de sélection `DEPTH`, décompte
  `UNKNOWN`.
- À paramètres, analyse et génération de faits identiques, la sélection et l'ordre sont identiques.
- La forme d'un parcours ne dépend que des faits, jamais d'un nom de relation ou de type : aucun
  `if relation == …` dans le moteur.

### 2. Sens entrant, sortant et combiné

- `direction` : `OUTGOING`, `INCOMING` ou **`BOTH`**. `BOTH` suit chaque relation dans les deux sens,
  le sortant d'abord, puis l'entrant.
- Forme générale, pour composer des parcours mixtes : `steps`, une liste ordonnée de pas
  `{"relation": …, "direction": …}`. `follow` + `direction` en est le raccourci. Un pas ne peut figurer
  qu'une fois ; l'ordre de `steps` est la priorité.
- **Orientation réelle** dans tous les sens : un fait `A → B` trouvé depuis `B` reste `A → B`. Chaque arête
  dit par quel pas elle a été atteinte (`via`).
- Une même identité atteinte par deux pas différents (par exemple `A → B` sortant depuis `A`, puis
  entrant depuis `B` dans `BOTH`) n'est rendue qu'une fois.

### 3. Cycles, parents multiples, arêtes parallèles

- Un nœud n'apparaît qu'une fois ; son niveau est celui de sa première découverte.
- Toute arête rencontrée vers un nœud déjà présent est **rendue** (budget permettant), marquée
  `revisit: true`, et n'entraîne aucun développement. Un cycle, une boucle sur un même nœud (`A → A`) et
  un graphe dense terminent toujours.
- Les arêtes parallèles sont toutes rendues, chacune avec sa référence de fait. Aucune n'est fusionnée
  avec une autre : deux relations entre les mêmes nœuds sont deux faits.
- Plusieurs occurrences d'une même identité ne produisent qu'une arête, qui porte `occurrences` (décompte
  qualifié). **À vérifier en tranche A** : comment la tranche à un saut rend aujourd'hui deux occurrences
  d'une même identité. Si elle les rend en double, la correction suit la règle des refactorisations : un
  test qui l'expose, une correction séparée, la décision notée ici.
- Chaque nœud dit combien d'arêtes rendues l'atteignent (`parents`) et par laquelle il a été découvert
  (`discovered_by`) : c'est ce dont l'Arbre (§ 10.1) aura besoin pour ses renvois. Ce lien d'affichage
  n'est jamais une relation `CONTAINS`.

### 4. Budgets

| Budget | Défaut | Plafond | Compte |
| --- | --- | --- | --- |
| `depth` | 1 | 4 | niveaux depuis l'ancre |
| `max_nodes` | 30 | 200 | nœuds rendus, ancre comprise |
| `max_edges` | 60 | 400 | arêtes rendues, revisites comprises |
| `max_fanout` | aucun | 200 | arêtes rendues par nœud développé ; protège la Tuile d'un nœud à fort degré |
| `max_work` | 100 | 2 000 | lectures d'adjacence, y compris vides (définition actuelle conservée) |
| `max_bytes` | celui de l'opération | celui de l'échange | réponse sérialisée, frontière comprise |

- Les plafonds sont initiaux, à mesurer (tranche F). Augmenter un plafond est une décision documentée,
  pas un réglage silencieux.
- Un nœud à fort degré n'est jamais chargé en entier : chaque lecture d'adjacence est bornée par ce qui
  reste de budget.
- **Lecture par lots** (amendement du port `FactReading`) : `neighbors(scan, anchor, relation, direction,
  after, limit)` rend jusqu'à `limit` occurrences en une requête indexée, dans l'ordre des rangs.
  `limit` vaut au plus le budget d'arêtes restant plus un (pour savoir s'il en reste). Une lecture par
  lots compte pour **un** travail. `neighbor` reste servi (comparaison, commits). L'adaptateur historique
  `fact_store.py` et la mémoire versionnée l'implémentent tous deux ; le test de conformance SQLite et
  PostgreSQL le couvre.
- L'enveloppe minimale qui ne tient pas dans `max_bytes` donne une erreur explicite, jamais une Tuile
  amputée en silence (comportement actuel conservé).

### 5. Frontières

Les trois natures de § 9.3 restent séparées. Ce récit les **localise** :

| Nature | Raison | Portée | Décompte | Reprise |
| --- | --- | --- | --- | --- |
| Sélection | `DEPTH` | un nœud non développé | `UNKNOWN` | EXPAND depuis ce nœud |
| Sélection | `FANOUT`, `NODES`, `EDGES`, `BYTES`, `WORK` | un nœud et un pas, coupés au milieu de leurs voisins | `AT_LEAST: 1` si une arête non rendue a été lue, sinon `UNKNOWN` | position de reprise de ce nœud et de ce pas |
| Sélection | `NOT_REACHED` | un nœud découvert mais pas encore développé quand un budget global a coupé | `UNKNOWN` | EXPAND depuis ce nœud |
| Connaissance | `NOT_ANALYSED` (langages non lus pour un pas) | l'analyse, par pas | `UNKNOWN` | une capacité d'analyse |
| Connaissance | `NOT_INTERPRETED`, `READ_ERROR` **locales** | un nœud rendu | `UNKNOWN` | une capacité d'analyse |
| Connaissance | `ANALYSIS_INCOMPLETE` | un analyseur | `UNKNOWN` | une capacité d'analyse |
| Contexte | `NO_ANALYZER` | un pas | `UNKNOWN` | l'exécution ou la construction d'une capacité |

**Couverture locale.** Une lacune de connaissance est rattachée à un nœud rendu quand une couverture
`NOT_INTERPRETED` ou `READ_ERROR` de l'analyse porte sur ce nœud, ou sur un fichier cité dans une preuve
d'une arête rendue qui l'atteint. La lecture est bornée : une requête indexée par lot de nœuds rendus,
jamais un parcours de toutes les couvertures. Si l'index nécessaire manque, la tranche C l'ajoute ;
si le coût dépasse le budget de travail, la lacune reste à l'échelle de l'analyse
(`scope: ANALYSIS`) et le dit, comme aujourd'hui. Une lacune locale n'est jamais présentée comme la seule
lacune : la frontière d'analyse reste.

Un parcours qui s'achève sans aucune coupure de sélection rend `ADJACENCY_COMPLETE`. Cela veut dire que
les pas demandés ont été parcourus jusqu'à la profondeur demandée **dans les faits enregistrés**,
jamais que le logiciel est entièrement connu.

### 6. Continuations

- **Pas de curseur global** pour une Tuile à plusieurs niveaux. Reprendre l'état complet d'un parcours en
  largeur exigerait un jeton proportionnel à la Tuile et rendrait la reprise fragile.
- Chaque coupure de sélection porte sa propre reprise : **EXPAND** depuis ce nœud, avec `after` (la
  position dans ses voisins pour ce pas) et la profondeur restante proposée.
- Le jeton existant est étendu sans changer sa nature : lié à la version du moteur, à l'instantané, aux
  paramètres de la Tuile d'origine, à la génération de faits, et désormais **au nœud et au pas** qu'il
  reprend. Il est refusé sur une autre analyse, une autre génération ou d'autres paramètres. Il n'est
  jamais une autorisation.
- Des EXPAND successifs depuis toutes les frontières de sélection atteignent toutes les arêtes connues
  accessibles dans la profondeur demandée, chacune au moins une fois. Le client fusionne nœuds et arêtes
  par référence et par identité ; le portail le fait (tranche D).

### 7. Preuves

- Chaque arête garde son `ref` `F…`, son statut, sa dérivation pour un fait `INFERRED`, et
  `evidence_count`.
- Option `evidence` : `NONE` (défaut, compatibilité) ou `SUMMARY`. Avec `SUMMARY`, chaque arête porte ses
  preuves résumées (chemin, lignes, symbole, méthode), dans le budget d'octets. Si elles ne tiennent pas,
  l'arête est rendue sans elles et `not_sent` le dit.
- Raison : `get_evidence` n'accepte qu'un `F…` transmis **dans le même échange**. L'explorateur fait un
  échange par action ; sans preuves résumées dans la Tuile, il devrait rejouer le parcours pour obtenir
  une preuve. Le contenu du code n'est jamais transmis : une preuve est une localisation (§ 9.5,
  règle 6 ; § 12.6).

### 8. Contrat du protocole

`get_neighborhood` évolue de `neighborhood/1` vers **`neighborhood/2`**. Une requête qui n'utilise aucun
nouvel argument reçoit exactement la réponse de `neighborhood/1`, au numéro de version près, qui reste
`neighborhood/1` dans ce cas. Arguments ajoutés :

```json
{
  "operation": "get_neighborhood",
  "arguments": {
    "analysis": "…",
    "root": "endpoint:GET /orders",
    "steps": [{"relation": "HANDLED_BY", "direction": "OUTGOING"},
              {"relation": "SERVED_BY", "direction": "OUTGOING"}],
    "depth": 3,
    "max_nodes": 60, "max_edges": 120, "max_fanout": 20, "max_work": 300,
    "evidence": "SUMMARY",
    "continuation": "…"
  },
  "max_bytes": 40000
}
```

Réponse, champs ajoutés aux champs actuels (aucun champ actuel ne change de sens) :

```json
{
  "engine_version": "neighborhood/2",
  "parameters": {"root": "…", "steps": ["…"], "depth": 3, "evidence": "SUMMARY"},
  "nodes": ["endpoint:GET /orders", "symbol:java:…#all()", "…"],
  "node_details": [
    {"reference": "endpoint:GET /orders", "level": 0, "known": true, "expanded": true,
     "parents": 0, "discovered_by": null},
    {"reference": "symbol:java:…#all()", "level": 1, "known": true, "expanded": false,
     "parents": 1, "discovered_by": "F1"}
  ],
  "items": [
    {"ref": "F1", "fact": {"…": "…"}, "evidence_count": 1, "evidence": [{"path": "…", "line_start": 9}],
     "via": {"from": "endpoint:GET /orders", "relation": "HANDLED_BY", "direction": "OUTGOING"},
     "level": 1, "revisit": false, "occurrences": {"kind": "EXACT", "value": 1}}
  ],
  "frontier": [
    {"nature": "SELECTION", "node": "symbol:java:…#all()", "reason": "DEPTH", "count": {"kind": "UNKNOWN"},
     "continuation": "…"},
    {"nature": "KNOWLEDGE", "scope": "NODE", "node": "file:…/Broken.java", "reason": "NOT_INTERPRETED",
     "count": {"kind": "UNKNOWN"}}
  ],
  "stop_reason": "DEPTH"
}
```

- `describe` annonce `neighborhood/2`, les plafonds, et pour chaque relation disponible les sens où elle
  a des producteurs exécutés.
- `stop_reason` garde ses valeurs actuelles et ajoute `DEPTH`, `FANOUT`.
- ARCHITECTURE § 9 (première tranche → multiniveau), § 9.1 (sens combiné), § 12.3 sont amendés dans la PR
  du moteur.

### 9. Explorateur dans le portail

Une page **Explorer** (TAXO-UI-05, nouvelle entrée de `PAGES`), adressable par le routeur :
`#/explorer?analyse=…&racine=…&pas=…&profondeur=…`. Elle consomme le protocole (`POST
/api/projects/{id}/taxo-query`) : aucun second contrat, aucun modèle de langage.

**Choisir le point de départ**
- Champ de recherche d'une référence, validé par Taxo (ancre inconnue : la page le dit, sans graphe
  vide trompeur). Les suggestions viennent des faits de l'analyse (`find_facts`), bornées.
- Liens d'entrée depuis les autres pages : une route (page Routes), un fichier touché par un commit, un
  module (page Architecture), une règle (page Sécurité), un commit de l'historique. Chacun ouvre l'explorateur sur cette référence.
- L'analyse est explicite : la plus récente par défaut, changeable avec le sélecteur des comparaisons.

**Régler le parcours**
- Les relations proposées sont celles que `describe` annonce pour l'analyse, groupées par domaine
  (vocabulaire du portail), avec leurs sens possibles. Une relation sans producteur exécuté est montrée
  désactivée, avec la raison.
- Sens : sortant, entrant, les deux. Profondeur : 1 à 4. Budgets : trois préréglages nommés (« compact »,
  « standard », « large ») qui se résolvent en budgets explicites, affichés.

**Voir**
- Une **vue en couches** : une colonne par niveau, les nœuds dans l'ordre stable du moteur, les arêtes
  dessinées en SVG, orientées (flèche dans le sens réel du fait, même en parcours entrant). Les revisites
  sont dessinées en pointillé vers le nœud existant ; les arêtes parallèles sont distinctes.
- Une **vue en liste** équivalente, accessible au clavier et aux lecteurs d'écran ; c'est la vue de
  référence des tests.
- Chaque nœud montre son type, sa référence lisible, et ses marques de frontière : « non développé »,
  « suite disponible (au moins n) », « zone non lue », « aucun analyseur pour ce pas ». Des comptes,
  jamais de pourcentage ; jamais « complet ».

**Naviguer**
- **Développer** un nœud de frontière : EXPAND, résultat fusionné dans la vue (nœuds par référence, arêtes
  par identité), sans recharger le reste.
- **Voir la suite** d'une liste coupée : reprise avec sa position.
- **Recentrer** : le nœud devient l'ancre d'une nouvelle Tuile ; l'historique de navigation (précédent,
  suivant) et l'adresse le suivent.
- Une action en cours peut être abandonnée ; une réponse arrivée trop tard est ignorée (règle existante
  du portail).

**Consulter les preuves**
- Sélectionner une arête ouvre son détail : sujet, relation, objet, statut, analyseur et version,
  dérivation et prémisses pour un fait `INFERRED`, preuves résumées (chemin, lignes, symbole).
- Aucun contenu de fichier n'est affiché ; l'accès au code reste soumis au consentement de § 12.6 et hors
  de ce récit.

**Dire ce qui manque**
- Un bandeau rappelle la portée : faits enregistrés de cette analyse, relations suivies, profondeur.
- Les frontières de connaissance et de contexte sont listées à part des frontières de sélection : un
  budget ne lève jamais une zone non lue.

### 10. Généricité et indépendance

- Le moteur et l'explorateur ne nomment aucun framework, aucune relation, aucun type de nœud. Les
  libellés viennent du vocabulaire ; un type ou une relation inconnus du portail s'affichent par leur nom
  brut, sans planter.
- `app/neighborhood` n'importe aucun évaluateur (garde-fou d'architecture étendu).
- Aucun appel à Minia ou à un fournisseur de modèle depuis l'explorateur (test du portail).

## Tranches

Trois PR, chacune complète et utilisable. Pas de micro-PR.

### PR 1 — Moteur multiniveau (tranches A, B, C)

- **A — Profondeur.** Parcours en largeur sur le moteur existant, `node_details`, `via`, `level`,
  `revisit`, `occurrences`, `max_fanout`, reprise par nœud et par pas, lecture par lots
  (`FactReading.neighbors`, deux adaptateurs, conformance PostgreSQL). Non-régression `depth: 1` par
  l'instantané de comportement.
- **B — Sens.** `BOTH` et `steps` ; une identité atteinte par deux pas n'est rendue qu'une fois.
- **C — Couverture locale et preuves.** Lacunes locales par nœud ; `evidence: SUMMARY`.
- ARCHITECTURE § 9, § 9.1, § 12.3 amendés ; `describe` mis à jour.

### PR 2 — Explorateur (tranches D, E)

- **D — Page Explorer.** Sélection de l'analyse et de l'ancre, réglages, vue en couches et vue en liste,
  développer, voir la suite, recentrer, historique, adresse, liens d'entrée depuis les autres pages.
- **E — Détail et frontières.** Panneau d'arête et de preuves, marques et liste des frontières par
  nature, états vides distingués (ancre inconnue, rien sur un périmètre couvert, aucun analyseur).

### PR 3 — Mesures et essai réel (tranche F)

- Campagne de performance (ci-dessous), essai sur dépôt réel, plafonds confirmés ou corrigés et
  documentés, captures du portail. Peut être fusionnée avec la PR 2 si les mesures n'appellent aucun
  changement.

## Campagne de tests

La vérité de chaque cas est écrite à la main, ou calculée par un **oracle indépendant** : un parcours en
largeur de référence, écrit dans le test en quelques lignes sur un graphe en mémoire, sans réutiliser une
ligne du moteur. Un moteur et un oracle qui partagent leur code partageraient leurs erreurs.

### Unitaires (backend)

- Validation des arguments : `depth`, `steps` (doublons, relation hors vocabulaire, sens invalide),
  `follow` + `direction` ⇔ `steps`, budgets hors plafond, `evidence`, jeton d'une autre analyse, d'une
  autre génération, d'autres paramètres, d'un autre nœud.
- Construction des frontières : chaque raison, chaque décompte (`AT_LEAST` seulement si une arête non
  rendue a été lue).
- Fusion d'identités atteintes par deux pas ; occurrences multiples d'une identité.

### Graphes synthétiques (intégration, mémoire réelle SQLite et PostgreSQL)

Un générateur de petits graphes enregistrés comme faits d'une analyse, sans évaluateur. Pour chacun, la
Tuile attendue est écrite à la main :

| Graphe | Ce qu'il prouve |
| --- | --- |
| chaîne de 6 nœuds | niveaux, `DEPTH` exactement au bon nœud |
| étoile de degré 1 000 | `max_fanout`, `max_work`, aucune lecture de toute l'adjacence, reprise jusqu'au dernier voisin |
| cycle de 3, boucle `A → A` | terminaison, revisites rendues, aucun redéveloppement |
| losange (deux chemins vers D) | parent multiple, niveau minimal, `parents: 2`, `discovered_by` stable |
| deux relations A → B et deux identités A → B | arêtes parallèles toutes rendues |
| graphe mixte entrant/sortant | `BOTH` et `steps`, orientation réelle, identité rendue une fois |
| ancre inconnue, relation sans producteur, relation produite sans fait | trois réponses vides distinctes |
| nœud dans un fichier `NOT_INTERPRETED` | lacune locale rattachée au bon nœud |

### Propriétés (sur graphes aléatoires, graine fixée et rejouable)

Sur des centaines de graphes générés (densité, cycles, degrés variés), contre l'oracle :

1. **Déterminisme** : deux appels identiques rendent des réponses identiques à l'octet.
2. **Honnêteté** : tout fait rendu appartient à l'analyse et à un pas demandé ; aucune arête inversée
   n'est fabriquée ; toute preuve rendue appartient à l'analyse.
3. **Budgets** : nœuds, arêtes, éventail, travail, octets et profondeur jamais dépassés.
4. **Unicité** : chaque nœud une fois, chaque identité une fois.
5. **Niveaux** : le niveau de chaque nœud égale sa distance dans le sous-graphe rendu.
6. **Préfixe** : à budgets plus grands, la Tuile rendue contient la plus petite, dans le même ordre.
7. **Complétude par reprise** : la fusion d'une Tuile et des EXPAND successifs depuis toutes ses
   frontières de sélection égale exactement ce que l'oracle atteint à la profondeur demandée.
8. **Frontière fidèle** : un nœud non développé figure toujours dans la frontière ; aucun nœud développé
   n'y figure avec `DEPTH`.
9. **Compatibilité** : pour `depth: 1` sans nouvel argument, la réponse égale celle de `neighborhood/1`.

La bibliothèque de propriétés (Hypothesis) n'est ajoutée que si la revue l'accepte ; sinon, générateur
maison à graine fixe, mêmes propriétés.

### Intégration (protocole et dépôts scénarisés)

- Dépôt Spring scénarisé : depuis une route, `HANDLED_BY` puis `SERVED_BY` jusqu'à l'application ; arrêt
  sur une zone non lue nommée. Vérité écrite à la main.
- Depuis un `file:`, en entrant, `CHANGES` vers les commits, puis `CHILD_OF` (profondeur 2).
- Dépôt mixte Java et Python : `NOT_ANALYSED` pour les pas que l'analyseur Java ne peut lire en Python.
- Échange complet : `describe`, `get_neighborhood` à trois niveaux, `get_evidence` d'une arête, EXPAND ;
  budgets d'échange respectés ; références `F…` stables dans l'échange.
- Cohérence de la connaissance (`test_knowledge_coherence`) étendue : la Tuile multiniveau nomme les
  mêmes langages non lus que le verdict, `/coverage` et la comparaison.

### Performances (mesurées, jamais promises)

- Graphe synthétique de 100 000 occurrences avec un nœud de degré 50 000 : temps et nombre de requêtes
  SQL d'une Tuile à profondeur 3, comptés. Garde-fou : nombre de requêtes ≤ `max_work` + une constante
  documentée, indépendant du degré.
- Même mesure sur PostgreSQL en CI (job existant), plan d'exécution vérifié sur les index d'adjacence.
- Dépôt réel (une analyse de référence existante) : temps, taille de réponse, limites rencontrées, notés
  dans ce récit ; aucune économie de tokens revendiquée.

### Portail (Vitest et DOM)

- Fusion de Tuiles : nœuds par référence, arêtes par identité, EXPAND sans doublon, reprise idempotente.
- Mise en couches : niveaux, ordre stable, revisites, arêtes parallèles, sens réel des flèches en
  parcours entrant.
- Libellés et frontières : chaque raison a sa phrase ; aucun pourcentage ; jamais « complet » ; type ou
  relation inconnus affichés bruts.
- Interactions : choisir une ancre, développer, voir la suite, recentrer, précédent/suivant, adresse ;
  réponse tardive ignorée ; ancre inconnue dite.
- Accessibilité : la vue en liste se parcourt au clavier, chaque arête et chaque frontière ont un nom
  accessible.
- Garde-fou : la page Explorer n'appelle aucune route de Minia.
- Un parcours de bout en bout dans Chromium (Playwright, déjà installé dans l'environnement mais pas
  encore dans le portail : son ajout est une décision de la revue) sur une analyse de test : ouvrir,
  développer, consulter une preuve.

## Acceptation

1. Une Tuile de profondeur 1 à 4 ne rend que des faits de l'analyse demandée et des pas demandés, dans
   leur orientation réelle.
2. Une requête `depth: 1` sans nouvel argument rend exactement la réponse actuelle (instantané de
   comportement).
3. Cycles, boucles et graphes denses terminent ; chaque nœud est rendu une fois, à son niveau minimal ;
   les revisites sont rendues et marquées ; les arêtes parallèles sont toutes rendues.
4. `BOTH` et `steps` suivent les deux sens sans fabriquer d'arête inverse ; une identité atteinte par deux
   pas est rendue une fois.
5. Tous les budgets sont respectés ; un nœud à fort degré n'est jamais lu en entier ; le nombre de
   requêtes est borné indépendamment du degré.
6. Chaque coupure figure dans la frontière avec sa nature, sa portée, un décompte qualifié et, pour une
   coupure de sélection, sa reprise. La fusion des EXPAND atteint tout ce que l'oracle atteint.
7. Les lacunes de connaissance sont rattachées aux nœuds quand c'est établi, et restent à l'échelle de
   l'analyse sinon, en le disant. Un budget ne lève jamais une lacune de connaissance.
8. `evidence: SUMMARY` rend des preuves de l'analyse, sans contenu de fichier, dans le budget.
9. Dans le portail, une personne choisit une ancre, développe, recentre, revient en arrière et consulte
   la preuve d'une arête, sans Minia, et voit ce qui n'est pas montré et pourquoi.
10. Aucune ligne du moteur ni de l'explorateur ne nomme un framework, une relation ou un type de nœud.
11. Les évaluateurs existants ne changent pas.
12. Les mesures de performance et l'essai réel sont consignés ici.

## Hors périmètre

- Chemins entre deux nœuds donnés (§ 11) : prochain récit, qui réutilisera ce parcours.
- Arbre, Forêt (§ 10), profils et Tuiles adaptatives (§ 9.5).
- Nouvelles relations (`CALLS`, `IMPLEMENTS`, `DISPATCHES_TO`, fichier → symbole déclaré).
- Contenu du code dans l'explorateur ; consentement au code (§ 12.6).
- Explication par Minia ; Minia peut appeler `neighborhood/2`, sans écran dédié.
- Cache de Tuiles : seulement si les mesures le justifient.

## Décisions soumises à la revue

1. **Transport du portail** : l'explorateur consomme le protocole `taxo-query/1`, sans route REST dédiée.
   Recommandé : un seul contrat, déjà borné et versionné. Alternative : une route `GET` dédiée, plus simple
   à mettre en cache, mais un second contrat à garder aligné.
2. **Preuves résumées dans la Tuile** (`evidence: SUMMARY`), plutôt qu'une référence de fait valable
   d'un échange à l'autre. Recommandé : aucun changement du modèle de références.
3. **Pas de curseur global** : reprise par nœud et par pas (EXPAND). Recommandé.
4. **Profondeur maximale 4**, budgets initiaux du tableau § 4, révisés par la tranche F.
5. **Unité d'arête = identité de fait**, occurrences comptées ; à confirmer après la vérification de la
   tranche A.
6. **Lecture d'adjacence par lots**, comptée comme un travail. Recommandé : la définition de `max_work`
   (lectures d'adjacence) est conservée.
7. **Vue en couches maison** (CSS et SVG) plutôt qu'une bibliothèque de graphe. Recommandé pour la
   première livraison : aucune dépendance, ordre et accessibilité maîtrisés. Une bibliothèque de mise en
   page pourra venir avec la Forêt si les couches ne suffisent plus.
8. **Bibliothèque de propriétés** : Hypothesis (absente aujourd'hui) ajoutée aux dépendances de test, ou
   générateur maison à graine fixe. Recommandé : Hypothesis, pour la réduction automatique des contre-exemples.
9. **Test de bout en bout** : Playwright ajouté au portail pour un seul parcours, ou tests DOM seulement.
   Recommandé : un seul parcours Playwright, lancé en CI.
