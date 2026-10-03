# TAXO-01J — Navigation multiniveau et explorateur de la Maille

Statut : rédigé le 2026-10-03, révisé le même jour après la première revue (#84) ; soumis à nouvelle
revue. Aucune ligne de code avant validation du contrat corrigé. Étape 5 du [PLAN](PLAN.md). Ce récit
reprend et termine les critères laissés ouverts par [TAXO-01I](TAXO-01I-voisinage-et-projectabilite.md) :
plusieurs niveaux, sens combiné, couverture locale. Il ajoute le premier usage humain du voisinage : un
explorateur dans le portail.

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

Le moteur à un saut **devient** le moteur multiniveau : on l'étend et on le découpe (§ « Découpage
architectural »), on n'en écrit pas un second. Une requête `neighborhood/1` doit rendre exactement la même
réponse qu'aujourd'hui (non-régression prouvée par l'instantané de comportement, ARCH-REF-01 § 9).

### Constats vérifiés dans le code (revue de #84)

- **Occurrences.** Le moteur actuel rend **chaque occurrence** comme un élément distinct : l'adjacence est
  rangée par occurrence (`outgoing_rank`, `incoming_rank`), et la référence `F…` est calculée sur le
  contenu complet du fait (provenance et preuves comprises). Deux producteurs qui enregistrent une même
  identité donnent deux éléments, deux `F…`. Ce récit conserve cette propriété ; la première version
  proposait de fusionner les occurrences, ce qui aurait perdu statuts, provenances, dérivations et preuves.
- **Version 1.** `neighborhood/1` refuse `depth` différent de 1, `direction: BOTH`, `max_edges` au-delà de
  200 et `max_work` au-delà de 1 000.
- **Recherche.** `find_facts` ne filtre que par égalité exacte (`subject`, `relation`, `object`,
  `nature`) ; il n'a ni recherche par préfixe ni reprise. Aucun index ne porte le texte des références :
  `fact_identities` n'indexe ni sujet ni objet (références de longueur non bornée).
- **Preuves.** `get_evidence` n'accepte qu'un `F…` transmis dans **le même échange**.
- **Couvertures.** Les occurrences de couverture n'ont pas d'empreinte d'ancre (`subject_hash` vide) :
  aucune lecture indexée « couvertures de ce nœud » n'existe aujourd'hui.

## Définitions (normatives)

| Terme | Définition |
| --- | --- |
| **Ancre** | la référence d'où part la Tuile, connue de l'analyse ou non |
| **Pas** | un couple (relation, sens) que le parcours suit ; le sens est `OUTGOING` ou `INCOMING` |
| **Niveau** d'un nœud | sa distance en pas depuis l'ancre, **dans la Tuile rendue**, à sa première découverte (parcours en largeur) |
| **Élément** | une **occurrence** d'un fait d'assertion rendue, dans son orientation réelle, avec sa référence `F…`, son statut, sa provenance, sa dérivation et ses preuves propres. C'est l'unité que comptent les budgets et que rend la réponse |
| **Lien** | le regroupement, pour l'affichage, des éléments qui partagent une même **identité** de fait. Il ne remplace jamais ses éléments : il les liste tous |
| **Liens parallèles** | plusieurs liens distincts entre les deux mêmes nœuds (relations différentes, ou mêmes relations et identités différentes) ; tous sont conservés tant que le budget le permet |
| **Parents multiples** | un nœud atteint par plusieurs éléments ; il est rendu une fois, tous les éléments qui l'atteignent sont rendus |
| **Revisite** | un élément dont l'extrémité atteinte est déjà dans la Tuile ; rendu, marqué, jamais redéveloppé. Il ferme un cycle ou rejoint un parent multiple |
| **Développé** | un nœud dont tous les pas demandés ont été parcourus jusqu'au bout dans cette Tuile |
| **EXPAND** | la même opération relancée depuis un nœud de la frontière de sélection, avec sa position de reprise (§ 9.5, règle 7) |
| **Séquence canonique** | l'ordre dans lequel le parcours propose les éléments, à analyse et paramètres de forme donnés (§ 4) ; il ne dépend d'aucun budget |

Le niveau est un fait de la **vue**, pas du logiciel : « à deux sauts dans cette Tuile » ne veut jamais
dire « à deux sauts au plus dans le logiciel ».

## Exigences

### 1. Parcours multiniveau

- `depth` de 1 à **4**, défaut 1. Valeur initiale, à mesurer ; jamais une promesse.
- Parcours en **largeur**, niveau par niveau. Dans un niveau, les nœuds sont développés dans l'ordre où
  ils ont été découverts ; pour chaque nœud, les pas dans l'ordre de priorité ; pour chaque pas, les
  occurrences dans l'ordre stable existant (référence canonique UTF-16, identité, empreinte d'occurrence).
- Un nœud découvert au dernier niveau n'est pas développé : frontière de sélection `DEPTH`, décompte
  `UNKNOWN`.
- À paramètres, analyse et génération de faits identiques, la sélection et l'ordre sont identiques.
- La forme d'un parcours ne dépend que des faits, jamais d'un nom de relation ou de type : aucun
  `if relation == …` dans le moteur.

### 2. Sens entrant, sortant et combiné

- `direction` : `OUTGOING`, `INCOMING` ou **`BOTH`**. `BOTH` suit chaque relation dans les deux sens,
  le sortant d'abord, puis l'entrant.
- Forme générale, pour composer des parcours mixtes : `steps`, une liste ordonnée de pas
  `{"relation": …, "direction": …}`. `follow` + `direction` en est le raccourci ; les deux formes sont
  exclusives. Un pas ne peut figurer qu'une fois ; l'ordre de `steps` est la priorité.
- **Orientation réelle** dans tous les sens : un fait `A → B` trouvé depuis `B` reste `A → B`. Chaque
  élément dit par quel pas il a été atteint (`via`).
- Une même **occurrence** atteinte par deux pas (par exemple `A → B` sortant depuis `A`, puis entrant
  depuis `B` dans `BOTH`) n'est rendue qu'une fois, au premier pas qui l'atteint. Deux occurrences
  distinctes d'une même identité restent deux éléments.

### 3. Cycles, parents multiples, liens parallèles, occurrences multiples

- Un nœud n'apparaît qu'une fois ; son niveau est celui de sa première découverte.
- Tout élément vers un nœud déjà présent est **rendu** (budget permettant), marqué `revisit: true`, et
  n'entraîne aucun développement. Un cycle, une boucle sur un même nœud (`A → A`) et un graphe dense
  terminent toujours.
- Les liens parallèles sont tous rendus : deux relations entre les mêmes nœuds sont deux faits.
- **Occurrences multiples d'une identité** : chaque occurrence est un élément à part entière, avec son
  `F…`, son statut, sa provenance (`produced_by`), sa dérivation et ses preuves. Rien n'est choisi
  arbitrairement entre elles, rien n'est perdu. Chaque élément porte `identity`, une clé opaque et stable
  dans l'analyse, qui permet au client de **regrouper** visuellement les occurrences d'un même fait en un
  lien. Le portail montre un lien avec le nombre de ses occurrences, et le détail les liste toutes, chacune
  avec ses preuves (§ 9). Si une occurrence d'un lien n'a pas tenu dans le budget, le lien le dit
  (« au moins une autre occurrence non transmise ») au lieu de paraître complet.
- Chaque nœud dit combien d'éléments rendus l'atteignent (`parents`) et par lequel il a été découvert
  (`discovered_by`) : c'est ce dont l'Arbre (§ 10.1) aura besoin pour ses renvois. Ce lien d'affichage
  n'est jamais une relation `CONTAINS`.

### 4. Budgets et monotonie

| Budget | Défaut | Plafond | Compte |
| --- | --- | --- | --- |
| `depth` | 1 | 4 | niveaux depuis l'ancre |
| `max_nodes` | 30 | 200 | nœuds rendus, ancre comprise |
| `max_edges` | 60 | 400 | éléments rendus (occurrences), revisites comprises |
| `max_fanout` | aucun | 200 | éléments rendus par nœud développé ; protège la Tuile d'un nœud à fort degré |
| `max_work` | 100 | 2 000 | lectures d'adjacence, y compris vides (définition actuelle conservée) |
| `max_bytes` | celui de l'opération | celui de l'échange | réponse sérialisée, frontière comprise |

- Les plafonds sont initiaux, à mesurer (tranche F). Augmenter un plafond est une décision documentée,
  pas un réglage silencieux.
- Un nœud à fort degré n'est jamais chargé en entier : chaque lecture d'adjacence est bornée par ce qui
  reste de budget.
- **Lecture par lots** (amendement du port de lecture) : `neighbors(scan, anchor, relation, direction,
  after, limit)` rend jusqu'à `limit` occurrences en une requête indexée, dans l'ordre des rangs, chacune
  avec sa clé d'occurrence et sa clé d'identité. `limit` vaut au plus le budget d'éléments restant plus un
  (pour savoir s'il en reste). Une lecture compte pour **un** travail. `neighbor` reste servi (comparaison,
  commits). Les deux adaptateurs l'implémentent ; le test de conformance SQLite et PostgreSQL le couvre.
- L'enveloppe minimale qui ne tient pas dans `max_bytes` donne une erreur explicite, jamais une Tuile
  amputée en silence (comportement actuel conservé).

**Paramètres de forme et budgets globaux.** Deux familles, qui n'ont pas la même propriété :

- **Paramètres de forme** : ancre, pas, priorité, `depth`, `max_fanout`, `evidence`. Ils définissent la
  séquence canonique : quels éléments, dans quel ordre. `max_fanout` en fait partie parce qu'une coupure
  d'éventail fait passer le parcours au nœud suivant : elle change l'ordre, pas seulement le point d'arrêt.
- **Budgets globaux** : `max_nodes`, `max_edges`, `max_work`, `max_bytes`. Ils ne décident que du point
  où la séquence canonique s'arrête.

**Règle d'arrêt au premier refus.** Quand un budget global refuse un élément, le parcours s'arrête là. Il
ne saute jamais un élément pour en accepter un suivant (par exemple une revisite, qui ne coûte pas de
nœud, après un élément refusé faute de nœud). Le découpage des lectures par lots dépend du budget restant,
mais ne change jamais la séquence canonique : il ne décide que du nombre de lectures.

**Monotonie, énoncée exactement.**

1. À paramètres de forme identiques, la suite des éléments rendus est un **préfixe** de la séquence
   canonique. Augmenter un ou plusieurs budgets globaux, dans n'importe quelle combinaison, rend une suite
   dont la plus petite est un préfixe : mêmes éléments, même ordre, mêmes `F…` dans un échange neuf.
   Les nœuds rendus suivent : ceux de la petite Tuile sont un préfixe de ceux de la grande.
2. La **frontière n'est pas monotone** et ne doit pas l'être : un nœud coupé dans la petite Tuile peut
   être développé dans la grande ; le motif d'arrêt peut changer. La propriété porte sur les éléments et
   les nœuds, pas sur la frontière.
3. **`depth`** : en largeur, la séquence à la profondeur `d` est un préfixe de la séquence à `d + 1`. La
   propriété 1 vaut donc aussi quand on augmente `depth`, seul ou avec des budgets globaux.
4. **`max_fanout`** n'est pas un budget au sens de la propriété 1. Augmenter l'éventail ne garantit qu'une
   **inclusion** (pas un préfixe), et seulement si aucun budget global n'a coupé la plus grande Tuile
   (motif d'arrêt `ADJACENCY_COMPLETE` ou `DEPTH`).
5. Ces propriétés supposent la même analyse et la même génération de faits ; une génération différente
   est refusée (§ 6).

### 5. Frontières

Les trois natures de § 9.3 restent séparées. Ce récit les **localise** :

| Nature | Raison | Portée | Décompte | Reprise |
| --- | --- | --- | --- | --- |
| Sélection | `DEPTH` | un nœud non développé | `UNKNOWN` | EXPAND depuis ce nœud |
| Sélection | `FANOUT`, `NODES`, `EDGES`, `BYTES`, `WORK` | un nœud et un pas, coupés au milieu de leurs occurrences | `AT_LEAST: 1` si une occurrence non rendue a été lue, sinon `UNKNOWN` | position de reprise de ce nœud et de ce pas |
| Sélection | `NOT_REACHED` | un nœud découvert mais pas encore développé quand un budget global a coupé | `UNKNOWN` | EXPAND depuis ce nœud |
| Connaissance | `NOT_ANALYSED` (langages non lus pour un pas) | l'analyse, par pas | `UNKNOWN` | une capacité d'analyse |
| Connaissance | `NOT_INTERPRETED`, `READ_ERROR` **locales** | un nœud rendu | `UNKNOWN` | une capacité d'analyse |
| Connaissance | `ANALYSIS_INCOMPLETE` | un analyseur | `UNKNOWN` | une capacité d'analyse |
| Contexte | `NO_ANALYZER` | un pas | `UNKNOWN` | l'exécution ou la construction d'une capacité |

**Couverture locale.** Une lacune de connaissance est rattachée à un nœud rendu quand une couverture
`NOT_INTERPRETED` ou `READ_ERROR` de l'analyse porte sur ce nœud, ou sur un fichier cité dans une preuve
d'un élément rendu qui l'atteint. Lecture indexée par lot de références : la tranche C renseigne
l'empreinte d'ancre des occurrences de couverture à l'enregistrement, et une migration la calcule pour les
analyses existantes. Si cette lecture dépasse le budget de travail, la lacune reste à l'échelle de
l'analyse (`scope: ANALYSIS`) et le dit, comme aujourd'hui. Une lacune locale n'est jamais présentée comme
la seule lacune : la frontière d'analyse reste.

Un parcours qui s'achève sans aucune coupure de sélection rend `ADJACENCY_COMPLETE`. Cela veut dire que
les pas demandés ont été parcourus jusqu'à la profondeur demandée **dans les faits enregistrés**,
jamais que le logiciel est entièrement connu.

### 6. Continuations

- **Pas de curseur global** pour une Tuile à plusieurs niveaux. Reprendre l'état complet d'un parcours en
  largeur exigerait un jeton proportionnel à la Tuile et rendrait la reprise fragile.
- Chaque coupure de sélection porte sa propre reprise : **EXPAND** depuis ce nœud, avec `after` (la
  position dans ses occurrences pour ce pas) et la profondeur restante proposée.
- Le jeton garde sa nature : lié à la version du moteur, à l'instantané, aux paramètres de forme de la Tuile
  d'origine, à la génération de faits, et désormais **au nœud et au pas** qu'il reprend. Il est refusé sur
  une autre analyse, une autre génération, d'autres paramètres de forme ou une autre version du moteur. Il
  n'est jamais une autorisation. Les budgets globaux peuvent changer d'une page à l'autre, comme
  aujourd'hui.
- Des EXPAND successifs depuis toutes les frontières de sélection atteignent toutes les occurrences
  accessibles dans la profondeur demandée. Le client fusionne nœuds par référence et éléments par clé
  d'occurrence ; le portail le fait (tranche D).

### 7. Preuves

- Chaque élément garde son `F…`, son statut, sa provenance, sa dérivation pour un fait `INFERRED`, et
  `evidence_count`.
- Option `evidence` : `NONE` (défaut) ou `SUMMARY`. Avec `SUMMARY`, chaque élément porte ses preuves
  résumées (chemin, lignes, symbole, méthode), dans le budget d'octets. Si elles ne tiennent pas, l'élément
  est rendu sans elles et `not_sent` le dit, élément par élément.
- **Récupération hors de l'échange.** Chaque élément porte aussi `occurrence`, une **poignée** opaque.
  `get_evidence` accepte soit `fact` (un `F…` de l'échange, inchangé), soit `occurrence` (une poignée).
  La poignée :
  - désigne une occurrence d'**une** analyse, à **une** génération de faits ; elle encode ces deux liens et
    la clé d'occurrence, rien d'autre ;
  - n'est **jamais une autorisation** : l'échange ne sert que l'analyse de son projet (route et
    `analysis`, contrôles actuels). Une poignée d'une autre analyse, d'un autre projet, ou d'une autre
    génération est refusée par `INVALID_ARGUMENT`, sans dire si l'occurrence existe ailleurs ;
  - rend les preuves complètes de cette occurrence, bornées par le budget de l'opération, avec les mêmes
    références `E…` que `get_evidence` aujourd'hui.

  Ainsi, une preuve omise faute de place reste récupérable dans un échange ultérieur, sans rejouer le
  parcours et sans donner aux références `F…` une portée qu'elles n'ont pas. Le contenu du code n'est
  jamais transmis : une preuve est une localisation (§ 9.5, règle 6 ; § 12.6).

### 8. Contrat du protocole

**Sélection de la version, sans ambiguïté.**

1. `engine` (nouvel argument facultatif) : `"neighborhood/1"` ou `"neighborhood/2"`. S'il est donné, il
   décide ; une requête invalide pour la version demandée est refusée avec le motif de cette version.
2. Sans `engine`, une requête est servie par `neighborhood/1` **si et seulement si** elle est valide pour
   `neighborhood/1` exactement : arguments de son ensemble, `depth` égal à 1, `direction` `INCOMING` ou
   `OUTGOING`, budgets dans ses plafonds (`max_edges` ≤ 200, `max_work` ≤ 1 000), reprise émise par
   `neighborhood/1`. Sa réponse est alors identique, à l'octet, à celle d'aujourd'hui.
3. Toute autre requête est servie par `neighborhood/2` si elle y est valide, sinon refusée avec le motif de
   `neighborhood/2`. Une valeur nouvelle portée par un ancien nom (`depth: 2`, `direction: BOTH`,
   `max_edges: 300`, `max_work: 1500`) relève donc de `neighborhood/2`.
4. Une reprise d'une version n'est jamais acceptée par l'autre.
5. L'explorateur envoie toujours `engine: "neighborhood/2"`. `describe` annonce les deux versions, leurs
   plafonds, et pour chaque relation disponible les sens où elle a des producteurs exécutés.

Requête `neighborhood/2` :

```json
{
  "operation": "get_neighborhood",
  "arguments": {
    "engine": "neighborhood/2",
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

Réponse `neighborhood/2`, champs ajoutés à ceux de `neighborhood/1` (aucun champ existant ne change de
sens) :

```json
{
  "engine_version": "neighborhood/2",
  "parameters": {"root": "…", "steps": ["…"], "depth": 3, "max_fanout": 20, "evidence": "SUMMARY"},
  "nodes": ["endpoint:GET /orders", "symbol:java:…#all()"],
  "node_details": [
    {"reference": "endpoint:GET /orders", "level": 0, "known": true, "expanded": true,
     "parents": 0, "discovered_by": null},
    {"reference": "symbol:java:…#all()", "level": 1, "known": true, "expanded": false,
     "parents": 1, "discovered_by": "F1"}
  ],
  "items": [
    {"ref": "F1", "fact": {"…": "…"}, "evidence_count": 1, "evidence": [{"path": "…", "line_start": 9}],
     "identity": "i:…", "occurrence": "o:…",
     "via": {"from": "endpoint:GET /orders", "relation": "HANDLED_BY", "direction": "OUTGOING"},
     "level": 1, "revisit": false}
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

- `stop_reason` garde ses valeurs et ajoute `DEPTH`, `FANOUT`.
- ARCHITECTURE § 9 (première tranche → multiniveau), § 9.1 (sens combiné), § 12.3 (`find_references`,
  poignée d'occurrence) sont amendés dans la PR du moteur.

**Recherche de références : `find_references`** (nouvelle opération, générique, servie aussi à Minia).

- Arguments : `analysis`, `prefix` (1 à 200 caractères), `type` facultatif (préfixe de type du contrat,
  par exemple `file`), `limit` (1 à 50, défaut 20), `after` (reprise).
- Rend les références **présentes dans l'analyse** (sujet ou objet d'au moins une assertion) dont la clé de
  recherche commence par `prefix`, dans l'ordre de cette clé, avec leur type. Ni comptage de degré ni
  score : une liste ordonnée, et `next` s'il en reste. Aucun « contient », aucune recherche floue dans cette
  tranche.
- Clé de recherche : la référence canonique, repliée en casse (`casefold`), tronquée à une longueur fixe
  pour l'index ; la référence complète est comparée au-delà. Deux références qui ne diffèrent qu'après la
  troncature sont toutes deux rendues, dans l'ordre de leur référence complète.
- Index : une projection `analysis_references(scan_id, search_key, reference_hash, reference, type)`,
  remplie à l'enregistrement dans la même transaction que les rangs, avec un index B-tree sur
  `(scan_id, search_key, reference_hash)` ; une migration la remplit pour les analyses existantes. Une
  recherche est une lecture par plage indexée, bornée par `limit + 1`, jamais un parcours des faits.
- Reprise : `after` est un jeton lié à l'analyse, à la génération, au préfixe et au type ; il reprend
  strictement après la dernière clé rendue.

### 9. Explorateur dans le portail

Une page **Explorer** (TAXO-UI-05, nouvelle entrée de `PAGES`), adressable par le routeur :
`#/explorer?analyse=…&racine=…&pas=…&profondeur=…`. Elle consomme le protocole (`POST
/api/projects/{id}/taxo-query`) : aucun second contrat, aucun modèle de langage.

**Choisir le point de départ**
- Champ de recherche d'une référence : suggestions par `find_references`, pendant la frappe (requête
  retardée, la dernière seulement prise en compte), page suivante sur demande. Une ancre inconnue de
  l'analyse est dite comme telle, sans graphe vide trompeur.
- Liens d'entrée depuis les autres pages : une route (page Routes), un fichier touché par un commit, un
  module (page Architecture), une règle (page Sécurité), un commit de l'historique. Chacun ouvre
  l'explorateur sur cette référence.
- L'analyse est explicite : la plus récente par défaut, changeable avec le sélecteur des comparaisons.

**Régler le parcours**
- Les relations proposées sont celles que `describe` annonce pour l'analyse, groupées par domaine
  (vocabulaire du portail), avec leurs sens possibles. Une relation sans producteur exécuté est montrée
  désactivée, avec la raison.
- Sens : sortant, entrant, les deux. Profondeur : 1 à 4. Budgets : trois préréglages nommés (« compact »,
  « standard », « large ») qui se résolvent en budgets explicites, affichés.

**Voir**
- Une **vue en couches** : une colonne par niveau, les nœuds dans l'ordre stable du moteur, les liens
  dessinés en SVG, orientés (flèche dans le sens réel du fait, même en parcours entrant). Les revisites
  sont dessinées en pointillé vers le nœud existant ; les liens parallèles sont distincts ; un lien qui
  regroupe plusieurs occurrences porte leur nombre.
- Une **vue en liste** équivalente, accessible au clavier et aux lecteurs d'écran ; c'est la vue de
  référence des tests.
- Chaque nœud montre son type, sa référence lisible, et ses marques de frontière : « non développé »,
  « suite disponible (au moins n) », « zone non lue », « aucun analyseur pour ce pas ». Des comptes,
  jamais de pourcentage ; jamais « complet ».

**Naviguer**
- **Développer** un nœud de frontière : EXPAND, résultat fusionné dans la vue (nœuds par référence,
  éléments par clé d'occurrence), sans recharger le reste.
- **Voir la suite** d'une liste coupée : reprise avec sa position.
- **Recentrer** : le nœud devient l'ancre d'une nouvelle Tuile ; l'historique de navigation (précédent,
  suivant) et l'adresse le suivent.
- Une action en cours peut être abandonnée ; une réponse arrivée trop tard est ignorée (règle existante
  du portail).

**Consulter les preuves**
- Sélectionner un lien ouvre son détail : sujet, relation, objet, puis **chaque occurrence** avec son
  statut, son analyseur et sa version, sa dérivation et ses prémisses pour un fait `INFERRED`, et ses
  preuves (résumées dans la Tuile, ou chargées par sa poignée si elles n'avaient pas tenu).
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
- Aucun appel à Minia ou à un fournisseur de modèle depuis l'explorateur (test du portail).

## Découpage architectural et responsabilités

Principe : le parcours est une **règle métier pure**, alimentée par des ports de lecture et observée par
une jauge de taille. Ni FastAPI, ni SQLAlchemy, ni le format du protocole n'y entrent. Le code actuel
mêle dans une classe le parcours, les budgets, la frontière, la sérialisation et les références `F…` ;
ce récit le découpe en le faisant grandir, sans second moteur.

### Composants

| Couche | Composant | Responsabilité unique | Raison de changer |
| --- | --- | --- | --- |
| Domaine `app/neighborhood/domain/` | `request.py` — `TileRequest`, `Step` | les paramètres d'une Tuile et leurs invariants (pas distincts, bornes, forme vs budgets) | le contrat d'un parcours |
| | `budget.py` — `Budget` | ce qui est consommé et ce qui reste ; dit quel budget refuse un élément | une règle de budget |
| | `traversal.py` — `Traversal` | le parcours en largeur : file des nœuds, niveaux, déduplication des nœuds et des occurrences, revisites, coupures de sélection et leurs positions ; produit un `TileGraph` | une règle de parcours |
| | `frontier.py` | les entrées de frontière et la qualification des décomptes (`EXACT`, `AT_LEAST`, `UNKNOWN`) | la règle d'honnêteté des comptes |
| | `continuation.py` | encoder, lier et vérifier une reprise ou une poignée (version, analyse, génération, nœud, pas) | le format d'une reprise |
| Application `app/neighborhood/application/` | `ports.py` | `AdjacencyReading` (lecture par lots, existence, génération), `CoverageReading` (lacunes par lot de références), `ReferenceSearch` | ce dont le cas d'usage a besoin du stockage |
| | `tile.py` — `BuildTile` | le cas d'usage : vérifier l'ancre, fixer la génération, faire tourner `Traversal` avec le port, ajouter les frontières de connaissance et de contexte, refuser si la génération a changé ; rend un `Tile` du domaine | l'enchaînement d'une Tuile |
| | `knowledge_frontier.py` | frontières de connaissance (analyse et locales) et de contexte, à partir d'`AnalysisKnowledge` et de `CoverageReading` | la règle de couverture (COV-01) |
| | `references.py` — `FindReferences` | la recherche bornée de références | le contrat de recherche |
| Protocole `app/protocol/` | `neighborhood_operation.py` | lire les arguments, **choisir la version** (§ 8), construire la `TileRequest`, fournir la jauge d'octets, présenter le `Tile` en `neighborhood/1` ou `neighborhood/2`, attribuer les `F…` | le format d'échange |
| | `Exchange.get_evidence`, `Exchange.find_references` | servir une preuve par `F…` ou par poignée, servir la recherche, dans l'enveloppe commune | le protocole |
| Persistance `app/scans/infrastructure/sqlalchemy/` | `fact_memory.py`, `fact_store.py` | `neighbors` par lots ; empreinte d'ancre des couvertures ; projection et index `analysis_references` ; migrations | le schéma et les requêtes |
| Portail `frontend/src/explorer/` | `protocol.ts` | construire les requêtes, lire les réponses ; aucun état d'écran | le contrat |
| | `graph.ts` | fusionner les Tuiles (nœuds par référence, éléments par occurrence, liens par identité) ; pur | la règle de fusion |
| | `layout.ts` | placer nœuds et liens en couches ; pur | la mise en page |
| | `sentences.ts` | dire chaque frontière, chaque marque ; pur | le vocabulaire affiché |
| | `state.ts` | l'état de navigation (ancre, historique, demandes en cours, réponses tardives ignorées) ; réducteur pur | la navigation |
| | `Explorer.tsx`, `LayerView.tsx`, `ListView.tsx`, `LinkPanel.tsx`, `AnchorSearch.tsx` | l'affichage et les interactions ; aucune règle métier | l'interface |

### Dépendances autorisées

```text
domain  ←  application  ←  protocol (adaptateur entrant)
               ↑
         ports ← infrastructure (adaptateur sortant)

portail : composants React → state.ts → graph.ts, layout.ts, sentences.ts ; protocol.ts → API
```

- Le domaine n'importe rien de l'application, du protocole, de l'infrastructure, ni FastAPI, SQLAlchemy ou
  un évaluateur. Il ne connaît la taille d'une réponse que par une **jauge** (`admits(element) -> bool`)
  fournie par le protocole : la règle « on s'arrête au premier refus » est dans le domaine, la mesure en
  octets est dans le protocole.
- L'application importe le domaine, les ports et `app/knowledge/domain`, rien d'autre.
- Le protocole importe l'application ; il ne parle jamais au stockage directement.
- L'infrastructure implémente les ports ; elle ne contient aucune règle de parcours.
- Dans le portail, `graph.ts`, `layout.ts`, `sentences.ts` et `state.ts` n'importent ni React ni le
  réseau ; les composants n'en réimplémentent aucune règle.
- Ces règles sont vérifiées par `tests/test_architecture.py` (imports interdits par couche, aucun nom de
  relation ou de type dans `app/neighborhood`) et par un test du portail sur les imports.

### Ce qui n'est pas abstrait

Pas de stratégie de parcours interchangeable, pas de registre de profils, pas de moteur de règles : un
seul parcours en largeur. Les profils (§ 9.5) et l'Arbre (§ 10.1) le réutiliseront quand ils viendront ;
rien n'est construit pour eux par avance, au-delà de `discovered_by` et `parents`, qui servent déjà
l'explorateur.

## Tranches

Trois PR, chacune complète et utilisable. Pas de micro-PR.

### PR 1 — Moteur multiniveau et protocole (tranches A, B, C)

- **A — Découpage et profondeur.** Le moteur actuel est découpé selon la section précédente,
  `neighborhood/1` restant identique à l'octet (instantané de comportement avant toute extension). Puis :
  parcours en largeur, `node_details`, `via`, `level`, `revisit`, `identity`, `max_fanout`, reprise par nœud
  et par pas, règle d'arrêt au premier refus, lecture par lots (deux adaptateurs, conformance PostgreSQL),
  sélection de version.
- **B — Sens.** `BOTH` et `steps` ; une occurrence atteinte par deux pas n'est rendue qu'une fois.
- **C — Couverture locale, preuves, recherche.** Empreinte d'ancre des couvertures et lacunes locales ;
  `evidence: SUMMARY` ; poignée d'occurrence et `get_evidence` par poignée ; `find_references` et sa
  projection indexée ; migrations.
- ARCHITECTURE § 9, § 9.1, § 12.3 amendés ; `describe` mis à jour.

### PR 2 — Explorateur (tranches D, E)

- **D — Page Explorer.** Recherche d'ancre, réglages, vue en couches et vue en liste, développer, voir la
  suite, recentrer, historique, adresse, liens d'entrée depuis les autres pages.
- **E — Détail et frontières.** Panneau de lien et de ses occurrences, preuves par poignée, marques et liste
  des frontières par nature, états vides distingués (ancre inconnue, rien sur un périmètre couvert, aucun
  analyseur).

### PR 3 — Mesures et essai réel (tranche F)

- Campagne de performance, essai sur dépôt réel, plafonds confirmés ou corrigés et documentés, captures du
  portail. Peut être fusionnée avec la PR 2 si les mesures n'appellent aucun changement.

## Campagne de tests

La vérité de chaque cas est écrite à la main, ou calculée par un **oracle indépendant** : un parcours en
largeur de référence, écrit dans le test en quelques lignes sur un graphe en mémoire, sans réutiliser une
ligne du moteur. Un moteur et un oracle qui partagent leur code partageraient leurs erreurs. Un test qui
reproduit les hypothèses du code testé ne prouve rien : chaque garde-fou est vérifié par une mutation qui
doit le faire échouer.

### Unitaires (domaine, sans base de données)

- `TileRequest` : `depth`, `steps` (doublons, relation hors vocabulaire, sens invalide), exclusivité de
  `follow` + `direction` et `steps`, budgets hors plafond, `evidence`.
- `Traversal` sur un port en mémoire : niveaux, revisites, parents, occurrences dédupliquées par clé,
  arrêt au premier refus de chaque budget, coupures et positions.
- `frontier` : chaque raison, chaque décompte (`AT_LEAST` seulement si une occurrence non rendue a été lue).
- `continuation` : reprise et poignée refusées sur une autre analyse, une autre génération, d'autres
  paramètres de forme, un autre nœud, une autre version.
- Sélection de version (§ 8) : table de cas écrite à la main, dont chaque valeur nouvelle portée par un
  ancien nom.

### Graphes synthétiques (intégration, mémoire réelle SQLite et PostgreSQL)

Un générateur de petits graphes enregistrés comme faits d'une analyse, sans évaluateur. Pour chacun, la
Tuile attendue est écrite à la main :

| Graphe | Ce qu'il prouve |
| --- | --- |
| chaîne de 6 nœuds | niveaux, `DEPTH` exactement au bon nœud |
| étoile de degré 1 000 | `max_fanout`, `max_work`, aucune lecture de toute l'adjacence, reprise jusqu'au dernier voisin |
| cycle de 3, boucle `A → A` | terminaison, revisites rendues, aucun redéveloppement |
| losange (deux chemins vers D) | parent multiple, niveau minimal, `parents: 2`, `discovered_by` stable |
| deux relations A → B, et deux identités A → B | liens parallèles tous rendus |
| une identité A → B enregistrée par deux producteurs, statuts, dérivations et preuves différents | deux éléments, deux `F…`, même `identity`, chacun avec sa provenance et ses preuves ; un seul lien regroupé dans le portail |
| graphe mixte entrant/sortant | `BOTH` et `steps`, orientation réelle, occurrence rendue une fois |
| ancre inconnue, relation sans producteur, relation produite sans fait | trois réponses vides distinctes |
| nœud dans un fichier `NOT_INTERPRETED` | lacune locale rattachée au bon nœud |
| références de préfixe commun, de casse différente, plus longues que la clé tronquée | `find_references` : ordre, repli de casse, reprise sans perte ni doublon |

### Propriétés (sur graphes aléatoires, graine fixée et rejouable)

Sur des centaines de graphes générés (densité, cycles, degrés variés, occurrences multiples), contre
l'oracle :

1. **Déterminisme** : deux appels identiques rendent des réponses identiques à l'octet.
2. **Honnêteté** : tout élément rendu appartient à l'analyse et à un pas demandé ; aucun fait inversé n'est
   fabriqué ; toute preuve rendue appartient à l'analyse.
3. **Budgets** : nœuds, éléments, éventail, travail, octets et profondeur jamais dépassés.
4. **Unicité** : chaque nœud une fois, chaque occurrence une fois ; deux occurrences d'une identité
   toujours deux éléments.
5. **Niveaux** : le niveau de chaque nœud égale sa distance dans le sous-graphe rendu.
6. **Monotonie des budgets globaux** (§ 4, propriété 1) : pour des paires de budgets tirées
   indépendamment sur `max_nodes`, `max_edges`, `max_work`, `max_bytes` et `depth` (chacun plus grand ou
   égal), les éléments de la petite Tuile sont un préfixe de ceux de la grande. Les générateurs forcent
   les interactions : revisites nombreuses (qui coûtent des éléments sans coûter de nœuds), budgets de
   nœuds atteints avant les budgets d'éléments et l'inverse, gros faits qui épuisent les octets.
   Une mutation du moteur qui « saute » un élément refusé doit faire échouer cette propriété.
7. **Éventail** (§ 4, propriété 4) : inclusion seulement, et seulement quand la grande Tuile n'est coupée
   par aucun budget global ; un cas où la préfixation échoue est gardé comme exemple écrit à la main.
8. **Complétude par reprise** : la fusion d'une Tuile et des EXPAND successifs depuis toutes ses
   frontières de sélection égale exactement l'ensemble des occurrences que l'oracle atteint à la
   profondeur demandée.
9. **Frontière fidèle** : un nœud non développé figure toujours dans la frontière ; aucun nœud développé
   n'y figure avec `DEPTH`.
10. **Compatibilité** : toute requête valide pour `neighborhood/1` rend la réponse de `neighborhood/1`.

### Intégration (protocole et dépôts scénarisés)

- Dépôt Spring scénarisé : depuis une route, `HANDLED_BY` puis `SERVED_BY` jusqu'à l'application ; arrêt
  sur une zone non lue nommée. Vérité écrite à la main.
- Depuis un `file:`, en entrant, `CHANGES` vers les commits, puis `CHILD_OF` (profondeur 2).
- Dépôt mixte Java et Python : `NOT_ANALYSED` pour les pas que l'analyseur Java ne peut lire en Python.
- Échange complet : `describe`, `find_references`, `get_neighborhood` à trois niveaux, `get_evidence` par
  `F…`, puis dans un **autre** échange `get_evidence` par poignée ; poignée d'une autre analyse et d'un autre
  projet refusées.
- Cohérence de la connaissance (`test_knowledge_coherence`) étendue : la Tuile multiniveau nomme les
  mêmes langages non lus que le verdict, `/coverage` et la comparaison.
- Garde-fous d'architecture : imports par couche, aucun nom de relation ou de type dans le moteur.

### Performances (mesurées, jamais promises)

- Graphe synthétique de 100 000 occurrences avec un nœud de degré 50 000 : temps et nombre de requêtes
  SQL d'une Tuile à profondeur 3, comptés. Garde-fou : nombre de requêtes ≤ `max_work` + une constante
  documentée, indépendant du degré.
- `find_references` sur 100 000 références : une lecture par plage, temps mesuré.
- Mêmes mesures sur PostgreSQL en CI (job existant), plans d'exécution vérifiés sur les index.
- Dépôt réel (une analyse de référence existante) : temps, taille de réponse, limites rencontrées, notés
  dans ce récit ; aucune économie de tokens revendiquée.

### Portail (Vitest, DOM et un parcours de bout en bout)

- `graph.ts` : fusion de Tuiles, EXPAND sans doublon, reprise idempotente, occurrences regroupées par
  identité sans en perdre une.
- `layout.ts` : niveaux, ordre stable, revisites, liens parallèles, sens réel des flèches en parcours
  entrant.
- `sentences.ts` : chaque raison a sa phrase ; aucun pourcentage ; jamais « complet » ; type ou relation
  inconnus affichés bruts.
- `state.ts` : historique, demandes concurrentes, réponse tardive ignorée.
- Composants : choisir une ancre par recherche, développer, voir la suite, recentrer, précédent/suivant,
  adresse ; ancre inconnue dite ; preuve chargée par poignée.
- Accessibilité : la vue en liste se parcourt au clavier, chaque lien, chaque occurrence et chaque
  frontière ont un nom accessible.
- Garde-fous : la page Explorer n'appelle aucune route de Minia ; les modules purs n'importent pas React.
- Un parcours de bout en bout dans Chromium (Playwright) sur une analyse de test : rechercher une ancre,
  développer, consulter une preuve.

## Acceptation

1. Une Tuile de profondeur 1 à 4 ne rend que des faits de l'analyse demandée et des pas demandés, dans
   leur orientation réelle.
2. Toute requête valide pour `neighborhood/1` rend exactement la réponse actuelle ; toute valeur nouvelle
   relève de `neighborhood/2`, selon la règle du § 8.
3. Cycles, boucles et graphes denses terminent ; chaque nœud est rendu une fois, à son niveau minimal ;
   les revisites sont rendues et marquées ; les liens parallèles sont tous rendus.
4. Chaque occurrence est un élément avec sa provenance, son statut, sa dérivation et ses preuves ; aucune
   n'est fusionnée, choisie ou perdue ; le regroupement par identité n'est qu'un affichage.
5. `BOTH` et `steps` suivent les deux sens sans fabriquer de fait inverse ; une occurrence atteinte par deux
   pas est rendue une fois.
6. Tous les budgets sont respectés ; l'arrêt se fait au premier refus ; un nœud à fort degré n'est jamais
   lu en entier ; le nombre de requêtes est borné indépendamment du degré.
7. La monotonie du § 4 est vérifiée telle qu'énoncée, et seulement elle.
8. Chaque coupure figure dans la frontière avec sa nature, sa portée, un décompte qualifié et, pour une
   coupure de sélection, sa reprise. La fusion des EXPAND atteint tout ce que l'oracle atteint.
9. Les lacunes de connaissance sont rattachées aux nœuds quand c'est établi, et restent à l'échelle de
   l'analyse sinon, en le disant. Un budget ne lève jamais une lacune de connaissance.
10. Une preuve est toujours récupérable : résumée dans la Tuile, ou par sa poignée dans un autre échange ;
    une poignée n'ouvre jamais une autre analyse ni un autre projet.
11. `find_references` trouve toute référence présente par un préfixe de sa forme canonique, par lecture
    indexée bornée, avec une reprise sans perte ni doublon.
12. Dans le portail, une personne recherche une ancre, développe, recentre, revient en arrière et consulte
    les preuves de chaque occurrence d'un lien, sans Minia, et voit ce qui n'est pas montré et pourquoi.
13. Le découpage et les dépendances de la section « Découpage architectural » sont respectés et vérifiés
    par les garde-fous ; aucune ligne du moteur ni de l'explorateur ne nomme un framework, une relation ou
    un type de nœud.
14. Les évaluateurs existants ne changent pas.
15. Les mesures de performance et l'essai réel sont consignés ici.

## Hors périmètre

- Chemins entre deux nœuds donnés (§ 11) : prochain récit, qui réutilisera ce parcours.
- Arbre, Forêt (§ 10), profils et Tuiles adaptatives (§ 9.5).
- Nouvelles relations (`CALLS`, `IMPLEMENTS`, `DISPATCHES_TO`, fichier → symbole déclaré).
- Recherche « contient » ou floue de références.
- Contenu du code dans l'explorateur ; consentement au code (§ 12.6).
- Explication par Minia ; Minia peut appeler `neighborhood/2` et `find_references`, sans écran dédié.
- Cache de Tuiles : seulement si les mesures le justifient.

## Décisions

Prises lors de la révision du 2026-10-03, à confirmer par la revue :

1. **Occurrences conservées** une à une ; le regroupement par identité n'est qu'un affichage (§ 3).
2. **Sélection de version** par validité exacte en `neighborhood/1`, sinon `neighborhood/2` ; `engine`
   explicite possible ; reprises non transférables (§ 8).
3. **Recherche de références** : opération `find_references`, projection indexée par analyse, recherche
   par préfixe, reprise (§ 8).
4. **Preuves** : `evidence: SUMMARY` dans la Tuile, et poignée d'occurrence pour `get_evidence` hors de
   l'échange ; jamais une autorisation (§ 7).
5. **Monotonie** : préfixe pour les budgets globaux et la profondeur, inclusion conditionnelle pour
   l'éventail, frontière non monotone ; règle d'arrêt au premier refus (§ 4).

Déjà proposées, inchangées :

6. Transport du portail par le protocole, sans route REST dédiée.
7. Pas de curseur global : reprise par nœud et par pas.
8. Profondeur maximale 4 ; budgets initiaux du § 4, révisés par la tranche F.
9. Lecture d'adjacence par lots, comptée comme un travail.
10. Vue en couches maison (CSS et SVG) ; une bibliothèque de mise en page pourra venir avec la Forêt.
11. Hypothesis ajoutée aux dépendances de test, pour la réduction automatique des contre-exemples.
12. Un seul parcours Playwright dans le portail, lancé en CI.
