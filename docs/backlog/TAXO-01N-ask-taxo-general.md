# TAXO-01N — MIP, première tranche : Ask Taxo général

Statut : **accepté le 2026-10-09.** Le même jour, il est fusionné avec le MIP, qui passe au centre de Taxo :
ce récit en est la première tranche (voir « Le MIP »). La règle antérieure « MIP hors périmètre » est levée
pour ce récit.

## Problème

« Interroger Taxo » ne répond utilement qu'aux questions sur les commits. Une question comme « qui appelle
`OwnerRepository.findById` ? », « que contient le module `api` ? » ou « quelles routes sont servies par
`VetController` ? » donne au mieux « précisez un nombre de derniers commits ». Pourtant la Maille porte déjà ces faits
(`CONTAINS`, `CALLS`, `IMPLEMENTS`, `EXTENDS`, `HANDLED_BY`, `SERVED_BY`, `DEPENDS_ON`, `USES_TECHNOLOGY`…), et le
protocole sait les servir (`find_references`, `get_neighborhood`).

Causes constatées dans le code (`main` à fa16f73) :

| # | Constat | Où |
| --- | --- | --- |
| 1 | Le bouton « Sélectionner » ne reconnaît que trois sélections (N derniers commits, un commit, une période) ; toute autre phrase devient `GLOBAL`. | `backend/app/projection/domain/request.py` |
| 2 | La sélection ne lit que les faits de l'évaluateur `taxo.git`. | `backend/app/projection/application/query.py` |
| 3 | En exploration, un tour de Minia ne peut transmettre que huit arguments à plat (`subject`, `relation`, `object`, `nature`, `fact`, `scope`, `commit`, `path`). `find_references` (`prefix`, `type`, `analysis`) et `get_neighborhood` (`root`, `analysis`, `steps`, `depth`…) sont annoncés par `describe` mais **inutilisables** : leurs arguments ne passent jamais. Minia ne peut donc ni trouver un symbole par son nom, ni parcourir la Maille. | `backend/app/minia/domain/exploration.py` (`ARGUMENTS`, `STEP_SCHEMA`, `parse_step`) |
| 4 | Quand l'exploration échoue (fréquent avec un petit modèle local), le repli en mode paquet ne sait préparer que des commits : la question générale retombe sur `NEEDS_SELECTION`. | `backend/app/minia/application/ask.py` (`_project_steps`) |
| 5 | Le panneau n'annonce que des exemples de commits. | `frontend/src/query.tsx` (`AskTaxo`) |

Le problème n'est donc pas le savoir de Taxo mais le chemin entre la question et ce savoir.

## Comportement attendu

Une seule entrée « Interroger Taxo » accepte toute question sur le projet analysé :

- **historique** (commits, auteurs, périodes) : comportement actuel, inchangé ;
- **structure et code** (contenu d'un module, d'un fichier, d'une classe ; appels entrants et sortants ;
  implémentations ; routes et leurs gestionnaires ; dépendances entre modules ; technologies) : répondu depuis la
  Maille de la dernière analyse globale.

Minia trouve l'élément nommé (`find_references`), parcourt son voisinage (`get_neighborhood`), puis conclut. Chaque
affirmation est vérifiée par Taxo avant l'affichage, comme aujourd'hui. Ce que Taxo ne sait pas est dit avec sa
frontière (`NOT_INTERPRETED`, catégorie de TAXO-01M, non analysé). Une question sans élément reconnaissable reçoit
une réponse honnête : ce que Taxo sait servir pour ce projet et comment nommer un élément.

## Critères d'acceptation

1. En exploration, Minia peut appeler **toute** opération que `describe` annonce, avec **tous** ses arguments
   déclarés ; un argument non déclaré reste ignoré et nommé, un argument invalide reste refusé par Taxo.
2. Sur une fixture synthétique, avec un modèle de test scénarisé, « qui appelle X ? » aboutit à
   `find_references` → `get_neighborhood` → affirmations `CALLS` **confirmées** par `verify_claim`.
3. En mode paquet (repli ou petit modèle), une question qui nomme un élément connu reçoit le voisinage borné de
   cet élément, au lieu de `NEEDS_SELECTION`.
4. Une question sans élément reconnu et sans sélection de commits reçoit un `unknown` utile (ce que Taxo sait,
   exemples), jamais une invention.
5. Les questions sur les commits gardent exactement leur comportement actuel (tests existants inchangés et verts).
6. Le panneau présente des exemples des deux familles et, pour chaque référence citée, un lien vers l'Explorer
   centré sur elle.
7. Mesure publiée : une banque de questions dont la vérité est établie à la main sur les fixtures, résultat par
   fournisseur (répondu, confirmé, non prouvé, repli, erreur).

## Invariants

- Minia ne produit aucun fait et ne lit pas le dépôt ; toute affirmation affichée comme établie a un verdict de
  Taxo (ARCHITECTURE § 12.1, § 12.4).
- Le protocole existant ne change pas de sens : aucune sémantique modifiée, aucune rupture. Seuls des ajouts
  compatibles selon ARCHITECTURE § 12.5 : un champ facultatif de `find_references` (décision 4) et une opération
  d'exécution de plan (décision 5). Les opérations réservées (`find_callers`…) restent réservées.
- Neutralité : aucune ligne d'Ask, de Minia ou du panneau ne nomme Java, Spring, une relation ou un type de
  référence en dur ; tout vient de `describe`.
- Budgets et garde-fous inchangés (8 opérations choisies, 10 affirmations vérifiées, octets par tour et par
  échange).
- Aucune réponse conservée.

## Le MIP

> La Maille est la connaissance. La Tuile est la portion transportable de cette connaissance. Le MIP est le
> contrat qui permet d'interagir avec elle, en préservant les preuves, les limites et l'autorité de Taxo.

Le MIP (Maille Interaction Protocol) permet d'interroger une Maille et de transporter des Tuiles vérifiables,
sans transmettre toute la Maille. Il ne dépend ni de Minia, ni d'un modèle de langage, ni d'un transport
(appel local, HTTP, MCP). Son cycle : une intention arrive ; le MIP la valide, borne le périmètre et le budget ;
Taxo explore **localement** et construit une Tuile (faits, preuves, provenance, statuts, frontières, reprises) ;
le MIP la transporte ; le consommateur interprète et propose des affirmations ; le MIP les fait vérifier par
Taxo, qui rend un verdict avec ses preuves ou les laisse non prouvées. Un consensus entre modèles ne devient
jamais un fait.

Ce qui existe déjà, dans le protocole `taxo-query/1` (ARCHITECTURE § 12) : la Tuile bornée de
`get_neighborhood` avec frontières et reprises, les verdicts de `verify_claim`, les budgets en octets,
le consentement au diff, deux transports (interne et HTTP), la trajectoire visible.

Ce qui manque, et ce que ce récit apporte :

| Manque | Dans ce récit |
| --- | --- |
| Un contrat MIP écrit | Tranche 0 : ARCHITECTURE le définit sur l'existant, `taxo-query/1` en devient la première version filaire. |
| Un consommateur qui peut se servir de tout le contrat | Tranche A (#108). |
| Trouver un élément par son nom | Tranche A2 (décision 4). |
| L'exécution locale d'un plan borné, sans aller-retour avec le modèle à chaque opération | Tranche B : une opération générique du MIP, servie à tout consommateur ; le repli paquet d'Ask l'utilise (décision 5). |

Ce qui reste pour la tranche suivante du MIP (récit à part) : intentions et autorisations par consommateur
(périmètre, validation adaptée à la lecture ou à l'action, sur le modèle INTENTION → PREUVES → VALIDATION →
AUTORISATION → ACTION), capsule de Tuile autonome et vérifiable hors échange, transport MCP.

Exigences :

1. Réutiliser les primitives existantes (`find_references`, `get_neighborhood` et sa Tuile, `verify_claim`).
2. La forme d'un tour de Minia est un détail de l'adaptateur Minia ↔ modèle : le MIP ne la connaît pas.
3. L'unité transportée est la Tuile, jamais un format de réponse inventé pour un consommateur.
4. Le contrat ne fige ni le transport (FastAPI, HTTP), ni l'algorithme de parcours, ni un langage.
5. Le modèle propose, Taxo garde le contrôle déterministe de ce qui est exécuté : un plan est validé et borné
   avant d'être exécuté, jamais interprété.

## Décisions à prendre

| # | Question | Recommandation |
| --- | --- | --- |
| 1 | Comment Minia transmet-elle des arguments propres à chaque opération (listes `steps`, `follow`, entiers `depth`…) ? | Un champ unique `arguments`, objet JSON écrit en chaîne, lu et validé par Taxo. Le schéma d'un tour reste plat et stable pour tous les fournisseurs, et une opération future n'oblige pas à le modifier. Alternative : allonger la liste à plat (rapide, mais à refaire à chaque opération). |
| 2 | En mode paquet, comment Taxo trouve-t-il l'élément nommé sans modèle ? | Déterministe : les mots de la question (identifiants, chemins) sont cherchés par `find_references`, au plus quelques ancres, ambiguïté signalée et jamais tranchée au hasard. Aucun score, aucune similarité floue. |
| 3 | Le bouton « Sélectionner » (sans Minia) devient-il général ? | Non dans ce récit : il garde les sélections de commits, et une question générale l'invite à « Demander à Minia » ou ouvre l'Explorer sur l'élément reconnu. Un moteur de requête structurée sans modèle serait un récit à part. |
| 4 | Comment trouver un élément par son nom simple (`VetController`, `OwnerRepository.findById`) ? `find_references` compare un **préfixe de la clé entière** (`neighborhood/domain/references.py`, `reference_index.search`) : une clé Java commence par le paquet (`com.example.web.VetController…`), donc le nom seul ne la trouve pas. Sans réponse, les critères 2 et 3 échouent sur les exemples mêmes du récit. | Un champ facultatif `match` de `find_references` : `KEY` (défaut, comportement actuel inchangé) ou `NAME`. En `NAME`, la clé et le préfixe demandé sont d'abord **normalisés** : chaque séparateur d'un jeu fixe et neutre (`.`, `/`, `#`, `:`, `$`) devient un même séparateur canonique ; le préfixe normalisé est ensuite comparé au début de **chaque suffixe de la clé qui commence à un segment**. Une suite ordonnée de segments est ainsi trouvée quel que soit le séparateur écrit : `OwnerRepository.findById` trouve `…OwnerRepository#findById(…)`, et `VetController` trouve `…web.VetController`. Aucune règle propre à un langage, aucune recherche de segments isolés (qui serait ambiguë). Ces deux exemples exacts sont des tests de la tranche A2. Servi par un index borné (une entrée par début de segment) à côté de l'index actuel, avec migration testée ; une analyse antérieure sans cet index le dit (`NOT_AVAILABLE`) au lieu de rendre une liste vide. Alternative sans contrat : exiger un nom qualifié, ce qui ne répond pas à la cible. Décision de contrat et de format persistant : la tienne. |
| 5 | Que contient un plan d'exploration exécuté localement ? | Une opération `run_plan` : une suite ordonnée et bornée d'opérations **en lecture** déjà servies par le MIP (au plus 8 étapes, dans le budget de l'échange). Un argument peut renvoyer à une référence rendue par une étape précédente par un chemin borné (`{"from": 1, "item": 0, "field": "reference"}`), jamais par une expression. Taxo valide tout le plan avant d'exécuter la première étape ; il rend la trajectoire et chaque réponse (Tuiles comprises). Aucune écriture, aucune boucle, aucun branchement dans cette version. |
| 6 | Le nom filaire change-t-il ? | Non : `taxo-query/1` reste l'identifiant de la première version filaire du MIP. Renommer casserait les consommateurs sans rien apporter ; un nouveau nom viendra avec une vraie nouvelle version. |

## Tranches (chacune testable seule)

- **PR 0 — Contrat MIP.** ARCHITECTURE définit le MIP (objet, cycle, Tuile, verdicts, budgets, ce qui existe et
  ce qui manque) sur l'existant, sans rien casser ; PLAN.md le place au centre. Documentation seule.

- **PR A — Minia appelle tout le protocole.** Arguments par opération (décision 1), consignes d'exploration
  rendues générales (exemples hors commits), tests avec modèle scénarisé, non-régression des commits.
- **PR A2 — Recherche par nom** (si décision 4 acceptée). Champ facultatif `match` de `find_references`, index des
  segments et sa migration, `describe` l'annonce ; tests de contrat, de migration et de non-régression de `KEY`.
- **PR B — Exécution locale d'un plan.** L'opération `run_plan` (décision 5), annoncée par `describe`, testée
  pour tout consommateur ; puis le repli paquet d'Ask : ancres trouvées de façon déterministe (décision 2), plan
  exécuté localement, paquet bâti sur les Tuiles rendues, `unknown` utile sans ancre.
- **PR C — Panneau.** Texte et exemples des deux familles, ancres utilisées visibles, liens vers l'Explorer,
  soin visuel au niveau de l'Explorer.
- **PR D — Mesure.** Banque de questions sur les fixtures (`bibliotheque`, `spring-petclinic`), vérité établie
  indépendamment de Taxo, résultats par fournisseur, limites publiées même si elles déçoivent.

## Limites

- Taxo ne répond que ce que la Maille sait : un appel non interprété reste une frontière, pas une réponse.
- Un petit modèle local explore moins bien : le repli paquet garantit une réponse bornée, pas une réponse riche.
- La reconnaissance d'un élément nommé est littérale (préfixe de la clé, ou d'un de ses segments si la décision 4
  est acceptée) ; une description vague (« la
  classe qui gère les vétérinaires ») ne trouve rien sans nom.

## Hors périmètre

- Intentions et autorisations par consommateur, capsule de Tuile autonome, transport MCP : tranche suivante du MIP.
- Opérations d'écriture ou d'action, activation des opérations réservées, `get_source`.
- Nouveaux évaluateurs ou nouvelles relations (lambdas Java, lecteur Python).
- Recherche plein texte ou sémantique, embeddings, conservation de conversations.
- L'Arbre, qui reste le récit suivant.
