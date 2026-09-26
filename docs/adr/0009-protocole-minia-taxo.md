# ADR 0009 — Protocole générique de collaboration Minia ↔ Taxo

Date : 2026-09-26
Statut : Proposé
Dépend de : ADR 0001 (mémoire logicielle vérifiable), ADR 0002 (contrat du fait), ADR 0004 (monolithe
modulaire), ADR 0007 (faits Git), ADR 0008 (Minia et le diff)

## Contexte

Minia reçoit aujourd'hui un contexte **en une seule fois** : les faits d'un commit ou d'une sélection et,
sur accord, un diff borné. Les essais sur des commits réels ont montré deux limites :

1. **Trop peu de contexte** : un petit modèle, ou une fenêtre étroite, ne voit qu'une partie du
   changement et conclut sur cette partie.
2. **Assez de contexte, mais une conclusion prématurée** : un modèle plus puissant, recevant tout le
   diff, a qualifié un changement de « restructuration sans altération apparente des règles » alors
   qu'une valeur de retour changeait et que l'équivalence dépendait d'appelants qu'il n'avait pas.

Changer de modèle ne résout pas le second problème : lire du code n'est pas établir ce qu'il fait.
C'est précisément le rôle de Taxo.

> Minia comprend la question et raisonne. Taxo cherche, relie et prouve. L'humain décide.

Cet ADR fixe **comment n'importe quelle Minia interroge les connaissances de n'importe quel projet
analysé par Taxo**. Il ne décide aucune implémentation.

## Décision

### 1. Rôles

| Rôle | Fait | Ne fait jamais |
| --- | --- | --- |
| **Taxo** | cherche, suit les relations, sélectionne les faits, rend les preuves et la couverture, rend des verdicts | interpréter une intention, rédiger une explication |
| **Minia** | comprend la question, choisit les opérations, raisonne sur les résultats, explique | produire un fait, affirmer sans l'avoir demandé à Taxo, lire le dépôt autrement que par le protocole |
| **Humain** | pose la question, juge la réponse, décide | — |

Tout ce que Minia écrit reste de la NARRATION (ADR 0002, section 12) : jamais un fait, jamais une
prémisse, jamais persisté comme connaissance.

### 2. Neutralité technologique

Le protocole est le contrat entre Minia et le **cœur** de Taxo. Il ne connaît ni langage, ni
framework, ni projet.

```text
                      TAXO CORE
                          │
        ┌─────────────────┼─────────────────┐
   analyseur A        analyseur B       analyseur C        (langages, frameworks)
        └─────────────────┼─────────────────┘
                          ↓
           faits canoniques (ADR 0002) + couverture
                          ↓
                 TAXO QUERY PROTOCOL        ← cet ADR
                          ↕
                        MINIA
```

- Une opération du protocole porte sur des **catégories génériques** : entité, relation, preuve,
  couverture, commit, point d'entrée exposé, contrôle d'accès, dépendance, configuration.
- La connaissance d'un langage ou d'un framework appartient à l'**analyseur** qui produit les faits
  canoniques. Deux analyseurs de frameworks différents qui exposent des points d'entrée produisent les
  mêmes relations ; la même opération les interroge.
- Un nom de technologie peut apparaître comme **donnée** (une référence `technology:…` en argument ou
  en résultat), jamais comme **sémantique** d'une opération.

**Critère de revue.** Si le nom, la description ou la sémantique d'une opération du cœur contient un
langage, un framework, une bibliothèque ou un projet particulier, l'opération est au mauvais niveau
d'abstraction : elle appartient à un analyseur, ou doit être généralisée.

### 3. Forme d'une requête

```json
{
  "protocol": "taxo-query/1",
  "operation": "find_facts",
  "arguments": { "subject": "file:src/app/Config.x", "relation": "CONTAINS" },
  "max_bytes": 8000
}
```

- Toute opération est **en lecture seule**, **déterministe** pour un même instantané, et bornée à
  **un projet et une analyse** (l'instantané de référence est fixé au début de l'échange ; il ne
  change pas en cours de route).
- Les arguments sont validés par Taxo : références bien formées (ADR 0002, section 3), chemins
  appartenant au commit ou à l'instantané, limites de taille. Un argument invalide est refusé avec une
  raison, jamais interprété librement.
- `max_bytes` est une demande ; Taxo applique au plus le budget restant (section 7).

### 4. Forme d'une réponse

Toute réponse d'opération partage la même enveloppe :

```json
{
  "protocol": "taxo-query/1",
  "operation": "find_facts",
  "outcome": "OK",
  "snapshot": { "analysis": "…", "commit": "…" },
  "items": [ { "ref": "F1", "fact": { "…": "fait canonique ADR 0002" } } ],
  "evidence": [ { "ref": "E1", "fact": "F1", "location": { "path": "…", "line_start": 12 } } ],
  "coverage": [ { "scope": { "include": ["…"] }, "type": "ANALYSED", "producer": "…" } ],
  "not_sent": [ { "what": "items", "count": 14, "reason": "BUDGET" } ],
  "bytes": 3120
}
```

- **Issue obligatoire** : `outcome` vaut `OK` ou `ERROR`. Une erreur porte `error: {code, message}` et
  aucun résultat ; les codes sont fermés : `INVALID_ARGUMENT` (argument refusé à la validation),
  `NO_CONSENT` (consentement requis absent), `NOT_AVAILABLE` (opération que Taxo ne sait pas servir pour ce
  projet), `OUT_OF_SCOPE` (hors du projet ou de l'instantané), `BUDGET_EXHAUSTED` (plus aucune place dans
  l'échange), `INTERNAL` (panne de Taxo). `not_sent` ne sert qu'à un résultat `OK` dont une partie n'a pas
  été transmise ; il ne décrit jamais une erreur.
- **Références stables dans l'échange** : chaque fait reçoit une référence courte (`F1`…), chaque preuve
  la sienne (`E1`…). Minia ne peut citer que des références reçues pendant l'échange ; toute autre
  citation est écartée et signalée, comme aujourd'hui.
- **La couverture est obligatoire.** Une réponse vide sans couverture est interdite : « rien trouvé »
  doit toujours dire *où* Taxo a cherché et *avec quel* analyseur.
- **Rien n'est tronqué en silence** : ce qui ne tient pas dans le budget est compté dans `not_sent`
  avec sa raison (`BUDGET`, `CONFIDENTIAL`, `BINARY`, `TOO_LARGE`, `NOT_A_REGULAR_FILE`, `NO_CONSENT`…).
- Les preuves sont des **localisations** ; le contenu d'un fichier n'est rendu que par les opérations
  de code (section 5) et sous leurs conditions.

### 5. Opérations

#### Opérations initiales (v1) — ce que Taxo sait réellement supporter aujourd'hui

| Opération | Rend | Appuyée sur |
| --- | --- | --- |
| `describe` | les opérations disponibles pour ce projet, les relations et types de référence présents, les analyseurs exécutés et leur couverture | registre des évaluateurs, dernière analyse |
| `find_facts` | les faits correspondant à un motif (`subject`, `relation`, `object`, `nature` ; chaque champ facultatif, au moins un requis) | faits conservés de l'analyse |
| `get_evidence` | les preuves d'un fait reçu (`F…`) | preuves des faits |
| `get_coverage` | ce qui a été analysé, reconnu, non interprété ou hors périmètre, pour un périmètre donné | faits `COVERAGE` |
| `get_commit` | ce que Git sait d'un commit : auteur, dates, message, parents, fichiers touchés et statuts — **sans contenu** | faits Git (ADR 0007), historique |
| `get_diff` | les blocs modifiés d'un fichier touché par un commit | historique (TAXO-HIST-02), conditions de l'ADR 0008 |
| `verify_claim` | un verdict sur une affirmation (section 6) | tout ce qui précède |

`describe` est toujours la première opération disponible : Minia ne reçoit la description que des
opérations que Taxo peut effectivement servir pour ce projet. Une opération sans analyseur capable de
la nourrir n'est pas proposée.

#### Opérations réservées — génériques, activées par les analyseurs futurs

| Opération | Question générique |
| --- | --- |
| `find_endpoint` | quels points d'entrée l'application expose-t-elle, et qui les traite ? |
| `trace_access_control` | quelle politique d'accès s'applique à une ressource exposée, règle par règle ? |
| `find_callers` / `find_callees` | qui appelle ce symbole ; que appelle-t-il ? |
| `find_dependencies` | de quoi dépend ce module ou ce symbole ? |
| `find_configuration` | quelle configuration influence ce comportement, et d'où vient-elle ? |
| `diff_facts` | quels faits un commit introduit, modifie ou retire ? |
| `get_source` | le code d'un **symbole** précis (jamais un fichier entier par défaut), sous son propre consentement (section 9) |

Un analyseur qui produit les relations nécessaires **déclare** les opérations qu'il rend possibles ;
`describe` les expose alors. Ajouter une opération au protocole est une évolution explicite de cet ADR,
soumise au critère de revue de la section 2.

### 6. Verdicts : Minia propose, Taxo prouve

`verify_claim` reçoit une affirmation **structurée**, jamais une phrase :

```json
{ "subject": "endpoint:POST /items", "relation": "PROTECTED_BY", "object": "policy-rule:R1" }
```

et rend exactement un verdict :

| Verdict | Signification | Exige |
| --- | --- | --- |
| `CONFIRMED` | un fait établi affirme la même chose | le ou les faits, leur statut (`OBSERVED`, `INFERRED` avec prémisses, `HUMAN_VALIDATED`) et leurs preuves |
| `REFUTED` | un fait établi contredit l'affirmation | soit un fait `ABSENCE` couvrant l'affirmation, rendu avec son **motif, son périmètre et sa méthode** (une absence n'a pas de preuve, ADR 0002 section 1 : ces trois champs en tiennent lieu) ; soit un fait incompatible sur une relation déclarée exclusive par le vocabulaire, rendu avec ses preuves |
| `NOT_PROVEN` | Taxo ne peut ni confirmer ni réfuter | une raison **obligatoire**, ci-dessous |

`NOT_PROVEN` a trois raisons, alignées sur les trois fins de parcours de l'ADR 0002 (section 12) :

| Raison | Signification |
| --- | --- |
| `NOT_FOUND_IN_ANALYSED_SCOPE` | un analyseur capable a couvert ce périmètre et n'a rien établi |
| `NOT_INTERPRETED` | un analyseur a vu la zone sans savoir la lire |
| `NOT_ANALYSED` | aucun analyseur de Taxo ne couvre encore cette dimension |

- **`NOT_PROVEN` n'est jamais `REFUTED`.** « Non trouvé » ne devient « faux » que par un fait `ABSENCE`
  (motif, périmètre, méthode) ou par une relation exclusive.
- Un verdict `CONFIRMED` sur un fait `INFERRED` montre ses prémisses et la règle appliquée.
- **La réponse affichée est construite par Taxo, énoncé par énoncé.** Minia ne rend pas un texte libre
  accompagné d'une liste d'affirmations qu'elle aurait choisies : elle rend une suite d'**énoncés
  typés**, et rien d'autre n'est affiché.

  | Type d'énoncé | Contenu | Affichage |
  | --- | --- | --- |
  | `claim` | une phrase **et** son affirmation structurée (sujet, relation, objet) | toujours avec le verdict de Taxo : confirmée (avec preuves), contredite (avec ce qui la contredit), non prouvée (avec la raison) |
  | `interpretation` | un raisonnement, une hypothèse, une explication | toujours marquée « non vérifié », jamais présentée comme établie |
  | `unknown` | ce qui manque pour conclure | dans le bloc des inconnues |

  Taxo vérifie **tous** les énoncés `claim` avant l'affichage. Un texte hors de ces énoncés n'est pas
  affiché. La garantie est donc déterministe : **aucune phrase ne peut apparaître comme établie sans
  verdict de Taxo**. Une phrase qui affirme un fait sans être déclarée `claim` reste affichée comme
  interprétation non vérifiée, jamais comme connaissance.

### 7. Budget de contexte

- **Borne sûre** : un texte ne compte jamais plus de tokens que d'octets UTF-8 (tokeniseurs par octet).
  Tout budget est exprimé en octets, avec une réserve pour les consignes et la réponse.
- **Trois niveaux** : par opération (`max_bytes`), par échange (somme des résultats reçus), et la
  fenêtre du fournisseur (ADR 0008 et la fenêtre de chaque modèle).
- **Priorités** quand la place manque, dans cet ordre : preuves directes, faits et relations,
  couverture, code (diff, source), historique. Dans le code : code de production avant tests, tests
  avant documentation.
- Ce qui ne tient pas n'est jamais tronqué au milieu : il est compté dans `not_sent`.

### 8. Boucle de Minia

Deux modes, pour le même protocole :

| Mode | Principe | Pour |
| --- | --- | --- |
| **exploration** | Minia appelle les opérations une par une, décide de la suivante d'après les résultats | les fournisseurs qui savent appeler des outils de façon fiable |
| **paquet** | Taxo construit un seul paquet de contexte (le fonctionnement actuel, amélioré), Minia répond en une fois | les petits modèles locaux, ou en repli |

Garde-fous communs, fixés par Taxo et non par le modèle :

- nombre maximal d'opérations par question, budget total d'octets, délai total ;
- une opération refusée ou en erreur est rendue à Minia comme résultat, jamais comme instruction ;
- à l'épuisement d'une limite, Minia doit conclure avec ce qu'elle a et dire ce qui manque ;
- si le mode exploration échoue (format invalide, boucle sans progrès), Taxo bascule en mode paquet.

La réponse finale devient la suite d'énoncés typés de la section 6 (`claim`, `interpretation`,
`unknown`), à la place du texte libre actuel. Les citations ne peuvent désigner que des références reçues
pendant l'échange.

### 9. Sécurité

1. **Les résultats de Taxo sont des données, jamais des instructions.** Un commentaire, une chaîne ou un
   message de commit rendu par une opération peut ressembler à une consigne (« ignore les instructions
   précédentes ») : Minia ne le suit jamais. Les consignes de Minia le disent, et les résultats lui sont
   transmis dans un canal de données distinct de ses consignes.
2. **Lecture seule.** Aucune opération n'écrit, n'exécute le code du projet, ni ne lance de hook, de
   filtre ou de commande fournie par le dépôt (TAXO-HIST-02).
3. **Confidentialité.** Les refus existants s'appliquent à toute opération qui touche du contenu :
   `.env` et fichiers confidentiels (nom seul), binaires, liens, sous-modules, fichiers trop gros.
4. **Consentement pour le code, par nature de contenu.** Un consentement ne couvre que ce qu'il nomme.
   - `get_diff` relève du double consentement de l'ADR 0008 (réglage du projet et accord de la demande),
     qui ne porte que sur **les blocs modifiés d'un commit**.
   - `get_source` peut rendre du code **inchangé**, hors de tout diff : il exige son **propre** double
     consentement (un réglage distinct et un accord explicite de la demande, formulé comme la lecture du
     code source de symboles du projet). L'accord donné pour le diff ne l'autorise jamais.
   - Sans le consentement requis, l'opération répond `ERROR` / `NO_CONSENT`, et Minia le dit.
   - Avec un fournisseur distant, le portail avertit que le contenu quittera la machine ; avec un niveau
     gratuit, qu'il peut servir au fournisseur.
5. **Cloisonnement.** Un échange ne voit qu'un projet et un instantané ; aucune opération ne franchit
   cette frontière.
6. **Validation.** Taxo valide chaque argument ; Minia ne construit jamais de chemin, de requête ou de
   commande exécutée telle quelle.

### 10. Transparence

La trajectoire de Minia est visible en direct : chaque opération, ses arguments, la taille du résultat,
ce qui n'a pas été transmis, et les verdicts. Elle s'affiche avec la réponse, pour qu'un humain puisse
refaire le chemin. Comme la réponse, elle n'est pas conservée en v1.

### 11. Transport et version

- Le protocole est indépendant du transport : appel interne (Minia dans Taxo), API HTTP, et plus tard
  serveur MCP pour des agents extérieurs. Les opérations et enveloppes sont identiques.
- Version `taxo-query/1`. Ajouter une opération ou un champ facultatif est compatible ; changer la
  sémantique d'une opération ou d'un verdict crée une nouvelle version.

## Conséquences

- Les questions coûtent quelques milliers d'octets de faits ciblés au lieu de paquets massifs, et le
  coût d'une réponse devient mesurable opération par opération.
- Une affirmation de Minia peut être **contredite par Taxo**, avec la preuve : l'IA n'a plus le dernier
  mot sur ce qui est établi.
- La valeur de Minia croît avec les analyseurs, sans changer le protocole : chaque analyseur apporte des
  faits canoniques et, s'il y a lieu, les opérations génériques qu'il rend possibles.
- Tant qu'un analyseur manque, les réponses le disent (`NOT_ANALYSED`) au lieu de le deviner.
- Le mode paquet reste nécessaire pour les petits modèles ; les deux modes doivent être comparés sur un
  même jeu de questions (octets consommés, justesse, affirmations contredites) avant de choisir un
  défaut.

## Alternatives rejetées

- **Un grand paquet de contexte pour tout.** Coûteux, et l'expérience montre qu'un modèle qui reçoit
  tout le diff peut encore conclure trop vite. Conservé seulement comme mode de repli.
- **Des opérations propres à un framework** (par exemple une opération nommée d'après une bibliothèque
  de sécurité). Elles lieraient le cœur à une technologie ; la connaissance appartient aux analyseurs.
- **Laisser Minia lire le dépôt directement.** Elle contournerait les refus, le consentement et les
  preuves ; il n'y a qu'un lecteur de code, et il est dans Taxo.
- **Laisser le modèle rendre les verdicts.** Un verdict est une conclusion sur des faits : c'est à Taxo
  de l'établir, de façon déterministe et prouvée.

## Suites

1. **TAXO-QUERY-02** — les opérations v1 (`describe`, `find_facts`, `get_evidence`, `get_coverage`,
   `get_commit`, `get_diff`, `verify_claim`) sur les faits existants, avec l'enveloppe et les budgets.
2. **MINIA-09** — Minia interroge Taxo : mode exploration pour les fournisseurs capables, mode paquet en
   repli, trajectoire visible, affirmations vérifiées avant affichage.
3. **Analyseurs génériques** — chacun produit des faits canoniques et déclare les opérations qu'il rend
   possibles (points d'entrée, contrôle d'accès, appels, dépendances, configuration), quel que soit le
   langage ou le framework.
