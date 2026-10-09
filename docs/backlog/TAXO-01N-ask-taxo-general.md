# TAXO-01N — Ask Taxo général

Statut : **accepté le 2026-10-09**, avec l'exigence de ne pas enfermer le MIP (voir « Rapport au MIP »). Ne touche pas le MIP.

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
- Le protocole `taxo-query/1` ne change pas : aucune opération nouvelle, aucun argument nouveau, aucun sens
  modifié. Les opérations réservées (`find_callers`…) restent réservées.
- Neutralité : aucune ligne d'Ask, de Minia ou du panneau ne nomme Java, Spring, une relation ou un type de
  référence en dur ; tout vient de `describe`.
- Budgets et garde-fous inchangés (8 opérations choisies, 10 affirmations vérifiées, octets par tour et par
  échange).
- Aucune réponse conservée.

## Rapport au MIP

TAXO-01N **n'est pas** le MIP et ne le préfigure pas. Le MIP reste hors périmètre : rien ici ne le modifie,
rien ici ne doit le bloquer ni l'enfermer.

Ce que le MIP prévoit, et que ce récit ne réalise pas : le transport normalisé de Tuiles autonomes, un contrat
indépendant de Minia, des intentions et des autorisations formalisées, des capsules de preuves et une
trajectoire normalisées, l'indépendance du transport, l'exécution locale d'un plan d'exploration contrôlé.

Exigences pour ne pas enfermer le MIP :

1. Réutiliser les primitives existantes de Taxo (`find_references`, `get_neighborhood` et sa Tuile,
   `verify_claim`), sans en créer de propres à Minia.
2. La forme d'un tour de Minia (décision 1) est un détail de l'adaptateur Minia ↔ modèle, jamais un contrat de
   Taxo : rien côté Taxo ne la lit ni ne la connaît.
3. L'unité rendue au consommateur reste la Tuile telle que le voisinage la produit (faits, preuves, limites,
   statuts, frontières, reprises), pas un format de réponse inventé pour Minia.
4. Le repli paquet (PR B) est déjà une exécution locale par Taxo d'une demande bornée, sans aller-retour avec le
   modèle à chaque opération. Il reste une capacité de l'application Ask, pas une esquisse du MIP.
5. Aucun choix de ce récit ne fixe le transport (FastAPI, HTTP), l'algorithme de parcours ou un langage.

## Décisions à prendre

| # | Question | Recommandation |
| --- | --- | --- |
| 1 | Comment Minia transmet-elle des arguments propres à chaque opération (listes `steps`, `follow`, entiers `depth`…) ? | Un champ unique `arguments`, objet JSON écrit en chaîne, lu et validé par Taxo. Le schéma d'un tour reste plat et stable pour tous les fournisseurs, et une opération future n'oblige pas à le modifier. Alternative : allonger la liste à plat (rapide, mais à refaire à chaque opération). |
| 2 | En mode paquet, comment Taxo trouve-t-il l'élément nommé sans modèle ? | Déterministe : les mots de la question (identifiants, chemins) sont cherchés par `find_references`, au plus quelques ancres, ambiguïté signalée et jamais tranchée au hasard. Aucun score, aucune similarité floue. |
| 3 | Le bouton « Sélectionner » (sans Minia) devient-il général ? | Non dans ce récit : il garde les sélections de commits, et une question générale l'invite à « Demander à Minia » ou ouvre l'Explorer sur l'élément reconnu. Un moteur de requête structurée sans modèle serait un récit à part. |

## Tranches (chacune testable seule)

- **PR A — Minia appelle tout le protocole.** Arguments par opération (décision 1), consignes d'exploration
  rendues générales (exemples hors commits), tests avec modèle scénarisé, non-régression des commits.
- **PR B — Repli paquet général.** Ancres trouvées de façon déterministe (décision 2), paquet bâti sur le
  voisinage borné (`neighborhood/2`, forme compacte), `unknown` utile sans ancre.
- **PR C — Panneau.** Texte et exemples des deux familles, ancres utilisées visibles, liens vers l'Explorer,
  soin visuel au niveau de l'Explorer.
- **PR D — Mesure.** Banque de questions sur les fixtures (`bibliotheque`, `spring-petclinic`), vérité établie
  indépendamment de Taxo, résultats par fournisseur, limites publiées même si elles déçoivent.

## Limites

- Taxo ne répond que ce que la Maille sait : un appel non interprété reste une frontière, pas une réponse.
- Un petit modèle local explore moins bien : le repli paquet garantit une réponse bornée, pas une réponse riche.
- La reconnaissance d'un élément nommé est littérale (préfixe de référence) ; une description vague (« la
  classe qui gère les vétérinaires ») ne trouve rien sans nom.

## Hors périmètre

- Le MIP ; nouvelles opérations du protocole, activation des opérations réservées, `get_source`.
- Nouveaux évaluateurs ou nouvelles relations (lambdas Java, lecteur Python).
- Recherche plein texte ou sémantique, embeddings, conservation de conversations.
- L'Arbre (étape 6 du PLAN), qui reste le récit suivant.
