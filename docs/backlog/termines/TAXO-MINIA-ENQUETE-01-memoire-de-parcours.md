# TAXO-MINIA-ENQUETE-01 — Enquête navigable dans la Maille et mémoire de parcours de Minia

> **État : TERMINÉ le 11 octobre 2026** (PR #131 à #135 ; bilan en fin de récit). Accepté le même jour par le responsable du produit : récit, arbitrages 1 à 5 (§ 15) et découpage en lots A à D ; `verify_claim` arbitré en coexistence (lot D).  
> **Date : 11 octobre 2026**  
> **Décideur : responsable du produit**  
> **Nature : récit d'architecture et critères d'acceptation**  
> **Périmètre : Minia, sa conversation avec le LLM, et l'utilisation des opérations MIP existantes**

## 1. Décision architecturale recherchée

**Taxo est le cartographe. Minia est le commissionnaire. Le LLM est l'enquêteur intelligent.**

Taxo décrit la Maille, en rend les Tuiles, les relations, les éléments de provenance, les limites et les extraits de code autorisés. Il atteste **ce qu'il a observé, retrouvé, exécuté et transmis**, sans confirmer ou rejeter la conclusion formulée par le LLM.

Minia présente la question et les opérations disponibles au LLM, transmet ses demandes à Taxo, lui restitue les résultats et tient un **carnet de navigation** : chemins parcourus, branches restantes, sources déjà demandées, reprises et hypothèses de travail. Elle ne décide ni du sens métier ou sécuritaire du code, ni de la véracité du raisonnement.

Le LLM conduit l'enquête : il choisit un nœud, demande une Tuile ou le code d'une méthode, suit une branche, revient en arrière, examine d'autres pistes et finit par répondre avec ses sources et ses limites. « Confronter » signifie **examiner et croiser librement les informations pour enquêter**, pas soumettre chaque idée à un tribunal de faits.

**Objectif vérifiable :** permettre une exploration progressive, ramifiée et reprenable, sans limite *globale* de profondeur de la Maille, tout en conservant des budgets stricts *par opération et par tranche d'enquête* et une borne totale configurable.

## 2. Problème actuel et justification

L'Explorer humain sait afficher le parcours suivant d'un graphe, recentrer une Tuile et poursuivre depuis une frontière. Un LLM doit bénéficier de capacités équivalentes par le MIP, sans être cantonné à un résumé figé ou à une seule chaîne d'appels.

Dans la documentation actuelle de Taxo :

- `neighborhood/2` sait parcourir **1 à 4 niveaux par demande**, expose les frontières et les reprises, sans que cette profondeur soit une limite sur l'ensemble d'une enquête ;
- `get_tile` expose des profils (`method-context/1`, `calls/1`, `structure/1`, `security/1`) ;
- `find_references`, `get_evidence` et `get_source` permettent de localiser, documenter et lire un symbole, lorsque les capacités et permissions nécessaires existent ;
- les opérations sont bornées par des budgets, la fenêtre du modèle, des règles de protection et les consentements ;
- la boucle Minia documentée est courte (description puis au plus huit opérations choisies par le modèle), sans mémoire persistante d'enquête ; la trajectoire actuelle n'est pas conservée ;
- la présentation actuelle des `claim` repose encore sur `verify_claim` et sur des verdicts de Taxo. **Ce dernier point est contraire au partage de responsabilités demandé ici et nécessite une transition explicite.**

Ce récit **réutilise** le moteur de la Maille et les opérations en place. Il ne prescrit ni nouveau moteur de graphe, ni réanalyse du dépôt, ni duplication de la Maille, ni serveur Redis.

## 3. Périmètre

### Inclus dans la première livraison proposée

1. Mémoire **individuelle et persistante** par enquête, projet, analyse et génération.
2. Parcours libre par Tuiles successives : nœuds, arêtes, sens entrant/sortant, éventails, frontières, reprises, branches parallèles ou alternatives.
3. Lecture de code source *sur demande du LLM*, par `get_source`, **uniquement** si elle est disponible et autorisée ; les refus et troncatures sont visibles.
4. État compact adressé au LLM à chaque tranche ; accès au détail sur demande.
5. Journal de ce qui a été **demandé, retourné et effectivement transmis** ; déclaration **structurée** du LLM dans sa réponse finale, avec références MIP et identifiants de transmission.
6. Notes de travail `HYPOTHESIS_LLM` attribuées au LLM, liées à des références et à la génération.
7. Budget renouvelable *par demande justifiée du LLM*, sous plafond total et avec détection mécanique des répétitions improductives.
8. Sauvegarde, interruption, reprise et séparation stricte des enquêtes, avec **version minimisée de la question explicitement confirmée par l’utilisateur** pour toute enquête déclarée reprenable.
9. **Un port mémoire et un adaptateur SQLite en mode WAL**, sans abstraction de stockage supplémentaire.
10. Modification de la restitution conversationnelle : Taxo décrit des observations et un journal, **pas des verdicts sur les conclusions du LLM**.

### Exclus de cette première livraison

- Mémoire collective entre enquêtes et utilisateurs ; partage ou réutilisation inter-enquêtes des Tuiles : **phase ultérieure**, avec décision explicite sur les permissions et les gains mesurés.
- RocksDB, LMDB, Redis, mémoire vectorielle, embeddings, recherche sémantique des notes.
- Nouveau langage de requête MIP, second moteur de parcours, outil qui lit le dépôt hors MIP, exécution du code étudié.
- Déduction automatique d'hypothèses par Minia, classement sémantique de la « bonne » branche, vérification des conclusions par Taxo.
- Levée des limites de confidentialité, de fenêtre de contexte, de temps ou de budgets d'exploitation.

## 4. Contrat de responsabilités

| Acteur | Doit | Ne doit pas |
|---|---|---|
| **Taxo** | Cartographier, restituer faits/relations/couvertures/preuves/source autorisée et rendre traçable la transmission | Dire que l'interprétation du LLM est `CONFIRMED`, `REFUTED` ou « vraie » |
| **Minia** | Exposer les capacités réelles, acheminer les appels, mémoriser les états, signaler les branches possibles et les budgets | Choisir le sens des faits, inventer une exploration, modifier une observation Taxo, transformer une hypothèse en fait |
| **LLM** | Décider des investigations, demander les sources utiles, former et réviser ses hypothèses, rédiger les réponses en indiquant leurs limites | Présenter comme consultée une source non reçue ; interpréter « absent de Taxo » comme « absent du logiciel » |
| **MIP** | Imposer validation des arguments, autorisations, quotas, versionnement, provenance et frontières | Porter des conclusions métier ou décider d'un chemin d'enquête à la place du LLM |
| **Utilisateur** | Poser la question, accorder ou refuser les consentements, décider d'une poursuite soumise à autorisation | Être supposé avoir autorisé du code source par défaut |

**Invariant de séparation :** le journal Taxo décrit un événement de transmission ; la déclaration du LLM décrit son utilisation alléguée ; la réponse du LLM est une interprétation. Ce sont trois registres distincts. La concordance des deux premiers assure une **traçabilité de livraison et d'utilisation déclarée**, jamais une lecture cognitive ni la justesse automatique de la conclusion.

## 5. Scénario de référence : arbre à quatre niveaux, branches multiples

Point d'entrée : `POST /api/enrollments` dans le dépôt de démonstration Java. Le parcours ci-dessous correspond à des méthodes présentes dans ce projet ; les échanges Minia/LLM sont **simulés**.

```text
N1  EnrollmentController.enroll()
    └── N2  EnrollmentService.enroll()
            ├── N3  StudentService.findStudent()
            │       └── N4  StudentRepository.findById()
            ├── N3  CourseService.findCourse()
            │       └── N4  CourseRepository.findById()
            └── N3  EnrollmentRepository.save()
```

1. Minia transmet la question, l'analyse active, l'état disponible, les opérations et les permissions au LLM.
2. Le LLM demande le point d'entrée, puis la Tuile de `EnrollmentController.enroll()` et le code autorisé de cette méthode.
3. Il demande la Tuile et le code de `EnrollmentService.enroll()` ; Taxo lui rend **trois appels distincts**.
4. Minia inscrit les trois branches dans le carnet, sans imposer un ordre de visite.
5. Le LLM choisit `StudentService.findStudent()` et `CourseService.findCourse()` ; il demande le code et leurs Tuiles. `EnrollmentRepository.save()` reste **découverte, non explorée**.
6. Les Tuiles suivantes mènent aux repositories (`findById()`). La frontière demeure explicite : d'autres branches peuvent exister selon la couverture, les relations choisies et les limites de Taxo.
7. Si une Tuile s'arrête à une profondeur de quatre niveaux, le LLM peut demander **une nouvelle Tuile depuis le nœud de frontière**, sans prétendre avoir atteint la fin du graphe.
8. En cas d'interruption, Minia restaure **la version protégée et confirmée par l'utilisateur de la question initiale** (pour une enquête reprenable), la frontière exacte, le parcours, les **reçus** des sources déjà consultées, les hypothèses et les budgets. Elle ne republie pas les sources : tout contenu nécessaire doit être redemandé à Taxo sous les droits du moment.

**Critère métier :** les branches multiples sont conservées et retrouvables indépendamment, y compris lorsque deux branches convergent vers un même nœud ou lorsqu'un cycle apparaît.

## 6. Modèle minimal de mémoire

### 6.1 Une enquête, un instantané

Chaque enquête possède :

- `investigation_id` : identifiant opaque ;
- `owner_scope` : périmètre d'accès déjà autorisé (utilisateur/espace/tenant si applicable) ;
- `project_id`, `analysis_id`, `generation_id` et `commit_id` lorsqu'il existe ;
- `question_minimisee` : **obligatoire pour une enquête persistée déclarée reprenable** ; version protégée/minimisée **fournie ou explicitement confirmée par l'utilisateur**. Minia ne juge jamais si une reformulation conserve le sens de la question initiale. Ce champ, et non la formulation brute d'origine, est la question restaurée ;
- `status` (`ACTIVE`, `PAUSED`, `COMPLETE`, `EXPIRED`, `STALE`), dates de création/activité/expiration ;
- `revision` : version de l'état pour écriture atomique et protection contre les mises à jour concurrentes.

L'identifiant de commit **seul** ne remplace pas `analysis_id` et `generation_id` : deux générations de faits sur le même commit ne sont pas librement interchangeables.

**Source de la génération.** Minia s'exécute dans le serveur de Taxo : elle lit `generation_id` sur l'échange du protocole qu'elle ouvre pour l'enquête, c'est-à-dire la révision des faits que lisent les opérations de cet échange. Elle ne le lit ni dans une réponse MIP ni dans le stockage de la Maille, et n'interprète jamais un jeton opaque. Ce récit n'ajoute donc aucun champ public à MIP ; un client externe qui voudrait la même garantie demanderait un marqueur de génération dans les réponses, à arbitrer comme évolution additive du protocole.

**Règle de reprise de la question.** Une version minimisée peut être fournie par l'utilisateur ou proposée à sa confirmation, mais **Minia ne décide jamais qu'elle est équivalente à la question initiale**. Seule la version explicitement confirmée par l'utilisateur, après contrôle de confidentialité, peut être persistée pour la reprise. Sans confirmation ou si le texte confirmé ne peut être conservé de façon autorisée, **ne pas déclarer l'enquête reprenable** : l'utilisateur devra fournir une nouvelle question. Le scénario `save → interrupt → restore` et INV-04 s'appliquent seulement aux enquêtes déclarées reprenables ; aucune reprise silencieuse.

### 6.2 Carnet de navigation

La représentation logique contient :

| Objet logique | Contenu minimal |
|---|---|
| `visited_nodes` | Identifiants canoniques des nœuds effectivement visités et actions réalisées sur chacun |
| `edges_seen` | Identité des occurrences et des arêtes, direction et provenance ; conservation des convergences |
| `frontier` | Nœuds découverts non développés, raisons d'arrêt et jetons de reprise **liés à leur génération** |
| `source_receipts` | Référence de symbole MIP, analyse/génération, identifiant de transmission, classification, empreinte si présente, statut, troncature/refus ; **métadonnées seulement**, jamais le texte source |
| `operations` | Nom/arguments normalisés, issue (`OK`, `ERROR`, `REFUSED`, `INTERRUPTED`), références et compteurs, empreinte de réponse, horodatage, éléments réellement transmis (`delivery_id` lié aux identifiants MIP) et `not_sent` ; jamais la réponse elle-même : une Tuile ou un autre résultat complet reste en mémoire vive (§ 8.3, INV-10) et se redemande après redémarrage ; sans contenu source ni message modèle intégral |
| `hypotheses` | Notes `HYPOTHESIS_LLM`, texte non autoritatif, nœuds liés, génération, auteur LLM, statut (`OPEN`, `REVISED`, `CLOSED`, `STALE`) |
| `budget` | Consommation par tranche et cumul par enquête, renouvellements et refus |

Deux statuts doivent rester indépendants : une Tuile peut être **explorée** sans que le code source ait été **consulté**, et inversement. « Visité » ne signifie pas « entièrement connu ». Les frontières de **sélection**, de **connaissance** et de **contexte** de Taxo ne sont jamais confondues.

**Références :** ne jamais persister `F1`, `E1` ou un identifiant court limité à un échange comme s'il était valable au prochain. Conserver des identités durables lorsque le protocole en fournit, et revalider par le MIP les poignées, jetons et autorisations avant réutilisation.

### 6.3 Interface unique de stockage

Un **port métier** `ParcoursMemoryStore` (nom indicatif), dont les seules responsabilités sont :

```text
create(investigation)
load(investigation_id, authorized_scope)
commit(investigation_id, expected_revision, events, new_state)
mark_status(investigation_id, status, expected_revision)
expire(cutoff, policy)
```

Première réalisation : **un adaptateur SQLite WAL**. Pas de framework de mémoire, d'abstraction « multi-backends » ou de stockage d'une seconde Maille. La structure physique minimale proposée comporte deux ensembles :

- `minia_investigations` : métadonnées et état courant compact, sérialisé et versionné ;
- `minia_investigation_events` : journal append-only minimal des opérations, transmissions, notes, budgets et changements d'état.

`commit()` écrit **état + événements dans la même transaction**, avec contrôle de `revision`. Le WAL améliore la coexistence lectures/écritures, mais SQLite conserve **un seul écrivain à la fois** : ne pas promettre une concurrence illimitée. Les index, les migrations et le plan de sauvegarde sont à définir lors de l'implémentation, pas dans une nouvelle couche d'architecture.

Un cache RAM facultatif reste une **optimisation éphémère** de la session d'enquête active, pas une deuxième source de vérité ni un niveau de persistance. Il ne contient, si activé, que des **résultats non-source** (p. ex. Tuiles et relations autorisées) : **aucun extrait `get_source`, aucun diff**. Il est détruit à la fin de la session ou à l'arrêt du processus. Il n'a **aucune durée de conservation propre** et ne peut pas être utilisé pour restaurer une enquête.

## 7. Cycle d'une enquête et état transmis au LLM

```text
Question utilisateur
       ↓
Minia : ouvrir/reprendre enquête + vérifier analyse, droits, budgets
       ↓
Minia → LLM : question + capacités MIP + ÉTAT COMPACT
       ↓
LLM : choisir librement Tuile, frontière, preuve ou code
       ↓
Minia → MIP → Taxo : opération strictement autorisée
       ↓
Taxo → Minia : faits/source/limites + journal de réponse
       ↓
Minia : enregistrer le résultat reçu et l’état, annoncer les éléments en partance,
       transmettre au LLM, puis journaliser les éléments effectivement livrés
       ↺
LLM : explorer / noter / demander un renouvellement / répondre
```

L'**état compact** est dérivé de la mémoire, jamais rédigé comme une opinion de Minia :

```json
{
  "question_minimisee": "Comment l'inscription à un cours fonctionne-t-elle ?",
  "snapshot": {"analysis": "A", "generation": "G"},
  "visited": ["EnrollmentController.enroll", "EnrollmentService.enroll"],
  "frontier": ["StudentService.findStudent", "CourseService.findCourse", "EnrollmentRepository.save"],
  "open_hypotheses": [],
  "source_receipts": ["EnrollmentController.enroll", "EnrollmentService.enroll"],
  "budget": {"used_operations": 4, "remaining_operations": 4},
  "details_available_on_request": true
}
```

Cet exemple est **illustratif** : les identifiants réels sont ceux du MIP, et les noms de champs ne constituent pas une nouvelle API publique. L'état compact ne réinjecte ni tout le code ni tout l'historique. Le LLM peut demander les détails nécessaires via Minia. Un `source_receipt` prouve au plus qu'un contenu a été livré auparavant : **il ne permet pas de reconstruire ce contenu**. Toute nouvelle consultation de code exige `get_source` et une nouvelle évaluation des droits, du consentement et de la protection.

### Après interruption

1. Authentifier et autoriser le propriétaire/périmètre de la reprise.
2. Charger l'enquête et contrôler `analysis_id`, `generation_id`, disponibilité de l'instantané, statut et expiration.
3. Restituer **exactement** l'état sauvegardé pour cette génération : **question minimisée confirmée**, frontières, branches, notes, consommations, reçus et demandes interrompues ; aucun contenu source n'est implicitement restauré.
4. Si la génération n'est plus disponible ou a changé, garder le carnet en lecture historique avec état `STALE`, **ne jamais** poursuivre ses jetons/poignées sur une autre Maille ; ouvrir une nouvelle enquête pour la nouvelle génération si l'utilisateur le souhaite.
5. Réétablir les capacités et consentements de la nouvelle demande avant toute lecture de code ou appel distant.

Une opération en cours au moment d'un incident doit être marquée `INTERRUPTED` ou rester absente du journal « transmis », selon ce qui a été réellement enregistré. Une lecture MIP peut être redemandée dans les limites d'autorisation ; jamais un résultat non sauvegardé ne doit être présenté comme transmis.

## 8. Budget renouvelable, pas de profondeur globale fixe

### 8.1 Budget par tranche

Minia conserve les plafonds de **chaque opération MIP** (nœuds, arêtes, éventail, octets, profondeur par Tuile, travail, temps et consentement) et impose un budget de tranche (nombre d'opérations, octets/tokens de contexte et durée). Le système possède aussi un **plafond total d'enquête** configurable pour éviter une succession infinie de tranches.

Les valeurs initiales sont **à calibrer par mesure**. Ne pas annoncer « illimité » : seul le nombre de niveaux explorables **par succession de Tuiles** n'est pas fixé à quatre. Le budget de tranche peut partir des limites actuelles de Minia, puis être ajusté après banc de latence et de couverture.

### 8.2 Renouvellement demandé par le LLM

Le renouvellement est une action **interne à Minia**, pas une nouvelle opération de la Maille. La demande doit inclure au minimum :

- identifiants de branches/frontières encore pertinentes **déjà découvertes** ;
- justification courte de l'intérêt de ces branches pour la question initiale ;
- ressources souhaitées (nouvelle tranche ou opérations ciblées).

Minia contrôle mécaniquement que ces branches figurent dans la mémoire, que la requête n'est pas une répétition improductive évidente, que les autorisations demeurent valides et que les plafonds totaux ne sont pas dépassés. Elle **n'évalue pas la qualité scientifique** de la justification. Si le budget ne peut pas être renouvelé, elle rend au LLM un arrêt explicite et les branches encore ouvertes ; la réponse à l'utilisateur indique le périmètre réellement exploré. Tout dépassement de plafond global nécessite l'autorisation prévue par le produit, pas une auto-extension indéfinie du LLM.

### 8.3 Boucles

Une boucle de graphe (`A → B → A`) est normale et **n'est pas une erreur**. Le suivi doit retenir les arêtes et revisites sans redévelopper automatiquement les mêmes éléments à l'infini.

Minia détecte les **demandes identiques répétées sans progrès** par leur clé normalisée (`analyse`, `génération`, `opération`, `ancre`, `profil/relations`, `direction`, `paramètres`, `continuation`) et le journal des résultats. Après répétition, elle **signale** le doublon et rappelle les branches restantes. Une revisite volontaire, avec paramètres ou but différents, reste possible.

**Réutilisation strictement délimitée :** un reçu persistant n'est **jamais un cache de résultat**. Minia peut éviter un nouvel appel à Taxo **uniquement** si le résultat complet **non-source** (Tuile/relations) est encore en **RAM dans la même session active**, sur le même instantané et la même génération, après contrôle actuel des droits, du périmètre et du budget. La nouvelle transmission au LLM est enregistrée distinctement, avec lien vers le résultat initial ; elle n'est pas présentée comme un nouvel appel Taxo. `get_source` et `get_diff` ne sont **jamais** servis par un cache de parcours : ils sont redemandés à Taxo avec le consentement courant. Après redémarrage, perte du cache ou changement de génération, les reçus ne suffisent pas ; il faut réinterroger Taxo. La suppression d'un cache RAM n'altère jamais la frontière persistée.

## 9. Notes du LLM : `HYPOTHESIS_LLM`

Une note comporte : `note_id`, auteur/modèle si connu, `investigation_id`, `analysis_id`, `generation_id`, texte de travail, références de nœuds/occurrences, date et statut.

Règles :

1. **Jamais un fait Taxo**, jamais un signal `CONFIRMED`, jamais un élément alimentant la Maille.
2. Peut être modifiée ou abandonnée par le LLM ; les versions de notes restent distinguables dans le journal.
3. Si la Maille change, la note reste éventuellement consultable comme **historique d'une ancienne génération** (`STALE`), pas comme une conclusion transférable.
4. Une note qui cite un nœud inconnu ou une génération incompatible ne devient pas valide par simple texte : Minia signale que la référence n'est pas retrouvée dans le carnet.
5. **Taille maximale et filtre de confidentialité existant** avant persistance, avec refus si la protection requise n'est pas assurée. Les notes sont destinées à des hypothèses courtes, pas à archiver le code ou les messages modèles complets. Une note qui **reprend une ligne du code livré** dans la demande en cours (espaces normalisés, lignes assez longues pour signer une recopie) est **refusée avant persistance** : elle cite le symbole, jamais son code (§ 11, INV-10). Ce contrôle déterministe est testé ; au-delà (code réécrit, code jamais livré), on **ne promet pas** de détection : le risque résiduel est documenté, limité par la taille, et la même protection s'applique à la restauration et à la transmission.

## 10. Traçabilité sans pouvoir de verdict

Pour chaque élément présenté au LLM, on distingue :

**A. Journal de Taxo / opération MIP** : demande exacte permise, identité de l'analyse, nature du résultat, références et preuves, refus/limites, éléments effectivement fournis à Minia.

**B. Journal de Minia** : éléments réellement insérés dans le message transmis au LLM après filtrage, éventuels retraits (`not_sent`), état/empreinte de transmission et réponse du fournisseur ou incident. « Obtenu de Taxo » n'est **pas** automatiquement « envoyé au LLM ».

**C. Déclaration structurée du LLM** : dans la réponse finale, une liste explicite de références MIP qu'il **déclare** avoir utilisées, corrélée aux identifiants de transmission de Minia, plus sa réponse et ses limites. Ce registre est **non autoritatif** ; Minia compare **des identifiants**, jamais une phrase libre, au journal B. La correspondance atteste une livraison, **pas** une lecture cognitive ni une interprétation correcte.

### Forme minimale de la déclaration finale (contrat interne à Minia)

La sortie structurée finale exige `answer`, `used_mip_items` (liste, éventuellement vide) et `remaining_unknowns`. Chaque entrée de `used_mip_items` contient :

- `mip_reference` : **référence MIP exactement reçue**, symbole ou occurrence/poignée fournie par Taxo, sans référence inventée ;
- `delivery_id` : identifiant opaque attribué à **l'élément effectivement envoyé au LLM** dans le journal B ; il permet d'éviter l'ambiguïté si la même référence est livrée plusieurs fois ;
- `kind` : `TILE`, `FACT`, `EVIDENCE` ou `SOURCE` selon la nature réellement transmise. Une Tuile (`get_tile`, `get_neighborhood`) est une `TILE`, une preuve une `EVIDENCE`, un code une `SOURCE` ; toute autre livraison (références trouvées par `find_references`, description, faits) est un `FACT`, tel que le journal B l'a inscrite.

L'analyse et la génération sont liées à l'enquête et à chaque `delivery_id`. Minia vérifie **structure, appartenance à l'enquête et à la génération, correspondance stricte à la référence MIP livrée, type et présence dans le journal des transmissions**. Une réponse absente ou mal formée est signalée comme telle, sans attestation de consultation ni verdict sur le fond. Les identifiants courts de l'ancien échange (`F1`, `E1`) ne sont jamais traités comme durables : le journal préserve leur association au bon échange/à la bonne génération.

Exemple **illustratif, non une nouvelle API publique** :

```json
{
  "answer": "Le contrôleur délègue au service ; l'enquête reste limitée aux éléments reçus.",
  "used_mip_items": [
    {
      "mip_reference": "symbol:java:com.example.school.service.StudentService#findStudents()",
      "delivery_id": "D-014",
      "kind": "SOURCE"
    }
  ],
  "remaining_unknowns": ["Autres chemins non explorés"]
}
```

`D-014` n'est valide que si un événement B atteste une livraison de **ce** symbole en tant que `SOURCE`. La déclaration ne réexpédie ni le code ni les Tuiles. Les notes `HYPOTHESIS_LLM` ont leur propre enregistrement et ne deviennent pas des preuves par cette déclaration.

La présentation ne doit plus annoncer : « Taxo confirme que la réponse du LLM est correcte » ou « Taxo réfute son hypothèse ». Une divergence de références se présente comme une **discordance de traçabilité**, pas comme une réfutation d'une idée. Les lacunes d'analyse restent des lacunes, pas des absences démontrées.

### Transition avec `verify_claim` et `taxo-query/1`

**Constat :** le MIP documenté et certains consommateurs actuels utilisent `verify_claim` et les verdicts `CONFIRMED` / `REFUTED` / `NOT_PROVEN` ; le portail possède des rendus spécifiques. Il faut donc :

1. **Désactiver l'obligation de verdict sémantique dans le nouveau parcours conversationnel**, sans supprimer les contrôles structurels, de sécurité, de provenance, de validité des références et d'autorisation.
2. **Ne pas changer silencieusement** la sémantique de `verify_claim` sous la même version filaire. Inventorier consommateurs, tests, schémas et écrans ; proposer séparément la dépréciation, la coexistence temporaire ou une version de contrat si l'API publique doit évoluer.
3. Faire apparaître dans la restitution trois zones descriptives : « Ce que Taxo a transmis », « Exploration et notes du LLM », « Ce qui reste hors périmètre ou non exploré » — sans verdict d'autorité sur le raisonnement.
4. Maintenir les mécanismes déterministes de contrôle de requête et d'accès. **Taxo bête ne signifie pas Taxo permissif.**

Aucun effacement de `verify_claim`, ni migration destructive, n'est autorisé implicitement par ce récit.

## 11. Confidentialité, droits, expiration et intégrité

- **Aucune persistance du code source brut ni des résultats complets de `get_source`/`get_diff`** dans le carnet ou le cache disque ; ni des prompts/réponses modèles complets. Seuls des reçus, références et états minimisés sont durables. Les Tuiles non-source ne sont éventuellement réutilisables qu’en RAM **pendant la session active** ; le code est redemandé à Taxo avec les autorisations du moment.
- **Double consentement** de `get_source` conservé : option serveur et consentement de la demande, indépendants de `get_diff`. Une reprise n'hérite jamais implicitement du consentement passé.
- **Question pour reprise** : aucune question brute ni proposition de reformulation non confirmée n'est persistée. La confirmation de l'utilisateur ne contourne pas les contrôles de confidentialité et ne vaut pas consentement à la lecture du code.
- **Messages sortants** : passage obligatoire par la protection de confidentialité existante ; les notes et états restaurés sont traités comme de nouvelles données, jamais comme des consignes fiables.
- **Séparation des droits** : aucune lecture, restauration ou mutualisation entre utilisateurs/organisations/projets sans preuve d'autorisation actuelle ; droits révoqués = accès refusé immédiatement, avant expiration.
- **Versionnement** : aucune fusion de parcours entre générations ; les références temporaires sont revalidées auprès de Taxo.
- **Durées** : proposer des valeurs configurables **uniquement pour les enquêtes persistées** (p. ex. 7 jours d'inactivité), non figées par ce récit. **Aucun TTL propre à la RAM** : elle est uniquement un cache de session, perdu à sa fermeture/au redémarrage. La mémoire collective est exclue de la phase 1.
- **Expiration logique à la lecture** : une entrée expirée n'est jamais restituée ; nettoyage opportuniste sur les opérations de maintenance et au démarrage, avec bornage du volume. La suppression logique SQLite/WAL ne garantit pas l'effacement physique instantané des anciennes pages ou sauvegardes : limiter les données sensibles persistées et définir une procédure adaptée à leur classification.
- **Robustesse** : transactions atomiques, intégrité des champs sérialisés, migrations explicites, verrouillage/concurrence par révision, absence de fuite dans logs/erreurs et restauration d'un état compatible seulement.

## 12. Invariants non négociables

**INV-01 — Autorité.** Aucune conclusion du LLM ne devient un fait Taxo ni ne reçoit un verdict automatique de Taxo dans le parcours cible.

**INV-02 — Initiative.** Le LLM choisit les explorations ; Minia indique les possibilités et applique le contrat, sans classer sémantiquement les branches.

**INV-03 — Navigation.** Une limite de profondeur *par Tuile* ne devient pas une limite globale de l'enquête ; les frontières sont reprises explicitement, et les arêtes multiples restent distinctes.

**INV-04 — Exactitude de l'état.** Pour toute enquête **déclarée reprenable**, à analyse et génération identiques : `save → interrupt → restore` préserve **exactement la question minimisée confirmée par l'utilisateur**, la frontière, les nœuds visités, les notes et leur statut, les reçus de sources et le budget consommé, selon la même version de schéma. En l'absence de confirmation ou si la confidentialité empêche la conservation, l'enquête n'est pas déclarée reprenable et l'utilisateur doit fournir une nouvelle question ; aucune reprise silencieuse.

**INV-05 — Instantané.** Un parcours ou une poignée de génération `G1` ne peut jamais être appliqué silencieusement à `G2`.

**INV-06 — Confidentialité.** Aucune source non autorisée ou donnée interdite ne quitte Taxo via Minia ; une demande antérieure ne vaut pas consentement permanent.

**INV-07 — Journal fidèle.** « Transmis au LLM » n'est enregistré que pour le contenu réellement envoyé. L'envoi au LLM et l'écriture du carnet ne tiennent pas dans une même transaction : les opérations dont la réponse part sont donc **annoncées et enregistrées avant l'envoi**. Après un arrêt du processus pendant l'appel, la reprise inscrit chaque annonce restée sans livraison comme **peut-être transmise** (`TRANSMISSION_UNCERTAIN`), ni livrée ni retenue, jamais absente ; « utilisé selon le LLM » est une **déclaration finale structurée** (`mip_reference`, `delivery_id`, `kind`), mécaniquement confrontable au registre des transmissions, sans verdict sur le fond.

**INV-08 — Budget.** Pas de renouvellement sans justification minimale valide, ni dépassement des plafonds fixés par le système ; répétitions sans progrès signalées sans juger les intentions.

**INV-09 — Sobriété.** Une seule Maille, un seul port mémoire, un seul adaptateur SQLite WAL initial ; pas de cache collectif ni de moteur nouveau sans décision ultérieure.

**INV-10 — Reçu ≠ résultat.** Un reçu persisté ne permet jamais de restituer un résultat : seules des Tuiles non-source encore disponibles dans la RAM de la **même session**, sous droits actuels, peuvent éviter un appel. Aucune source n'est mise en cache par Minia ; après interruption ou perte du cache, toute nouvelle lecture repasse par Taxo.

## 13. Critères d'acceptation et tests

| ID | Scénario automatisé | Attendu |
|---|---|---|
| **AC-01** | Méthode appelant trois méthodes ; seules deux explorées | Les trois branches demeurent identifiées ; la troisième reste dans la frontière |
| **AC-02** | Quatre niveaux de parcours puis nouvelle Tuile ancrée sur une frontière | Le chemin global se poursuit ; aucune limite globale arbitraire de profondeur |
| **AC-03** | Graphe avec convergence et cycle `A→B→A` | Arêtes/revisites conservées ; pas de développement automatique infini |
| **AC-04** | `get_source` autorisé puis refusé (consentement retiré) | Lecture seulement dans la demande autorisée ; refus tracé sans texte source persistant |
| **AC-05** | L'utilisateur confirme explicitement la version minimisée, sauvegarde l'enquête reprenable, interrompt la session et recharge | Même **question confirmée**, même frontière, mêmes notes, statuts, reçus et budget ; aucun texte source restauré |
| **AC-06** | Crash entre requête MIP, réception et sauvegarde, ou pendant l'appel au LLM | Aucun résultat non transmis déclaré comme transmis ; un résultat peut-être parti reste tracé comme tel ; état restauré cohérent |
| **AC-07** | Deux enquêtes concurrentes sur des projets/utilisateurs distincts | Aucun mélange de références ou de notes ; accès croisé refusé |
| **AC-08** | Génération de Maille modifiée | Ancienne enquête marquée historique/`STALE` ; aucune reprise ancienne sur nouvelle génération |
| **AC-09** | Note LLM liée à des nœuds, puis restauration | `HYPOTHESIS_LLM` reste distincte des faits, liée à la bonne génération |
| **AC-10** | Budget de tranche épuisé puis demande justifiée | Renouvellement uniquement si références pertinentes présentes et plafond global disponible |
| **AC-11** | Demandes identiques répétées sans progrès | Minia signale la répétition et restitue les autres branches, sans conclure à tort |
| **AC-12** | Réponse finale structurée du LLM avec `mip_reference`, `delivery_id`, `kind` ; une référence inexistante ou non envoyée y est citée | Contrôle **par identifiants** avec le journal B ; discordance et absence de déclaration structurée signalées ; aucune attestation de consultation |
| **AC-13** | Réponse Taxo partiellement envoyée (`not_sent`) | Journal distingue obtenu, retenu, transmis et non transmis |
| **AC-14** | État compact après longue exploration | Budget de contexte respecté ; détails récupérables sur demande, sans rejouer tout l'historique |
| **AC-15** | Note/prompt contenant un secret reconnu, une donnée interdite ou une note trop longue | Filtre de confidentialité appliqué et limite de taille respectée ; blocage ou assainissement vérifié sur les motifs pris en charge, sans promettre la détection de tout code brut |
| **AC-16** | Enquête expirée ou droits révoqués | Restauration refusée sans fuite ; conservation historique seulement si politique l'autorise |
| **AC-17** | Ancien consommateur de `taxo-query/1` utilisant `verify_claim` | Pas de changement silencieux de sémantique ; plan de compatibilité et tests de non-régression |
| **AC-18** | Même `get_tile` non-source redemandé dans la **même session active**, cache RAM valide et autorisations toujours valides | Peut être restitué depuis RAM sans nouvel appel Taxo, avec nouvel événement de livraison et lien à l'origine ; après redémarrage, l'opération repasse par Taxo |
| **AC-19** | Rejouer `get_source` après première lecture, retirer le consentement, puis redémarrer | Aucun code ni diff mis en cache/persisté ; demande rejetée sans consentement et, avec nouveau consentement, **nouvel appel Taxo** plutôt qu'un reçu |
| **AC-20** | Reformulation proposée mais non confirmée (ou refusée) par l'utilisateur ; ou texte confirmé refusé par les contrôles de confidentialité | Enquête **non marquée reprenable**, aucune `question_minimisee` persistée ; nouvelle question exigée à la reprise ; Minia n'évalue jamais l'équivalence sémantique |

**Tests attendus :** unités du domaine de parcours (état, budget, frontières, notes), transactions et concurrence SQLite WAL, intégration MIP simulée avec réponses structurées, tests réels sur `student-analysis-java`, confidentialité avec fournisseurs local/distant, non-régression du protocole, tests d'interruption/redémarrage et mesures de performance.

La campagne de performance doit mesurer au minimum : latence ajoutée par sauvegarde/restauration, taille du carnet selon nœuds/branches, fréquence des opérations MIP évitées, taille du contexte envoyé au LLM et comportement sous concurrence. **Aucun gain de performance chiffré n'est présumé.**

## 14. Découpage de réalisation proposé (sous validation distincte)

1. **Lot A — Contrat et mémoire pure :** modèle d'état, port `ParcoursMemoryStore`, frontières, notes `HYPOTHESIS_LLM`, budget et invariants ; tests unitaires. Aucun changement de l'API publique.
2. **Lot B — SQLite WAL et reprise :** adaptateur, migrations, écriture atomique/journal, restauration, accès et expiration ; tests d'incident et de concurrence.
3. **Lot C — Orchestration Minia :** branchement aux opérations MIP existantes (`find_references`, `get_tile`/`get_neighborhood`, `get_evidence`, `get_source`), état compact, **déclaration finale structurée**, réutilisation RAM non-source et renouvellement justifié ; tests sur les trois branches de l'exemple.
4. **Lot D — Restitution et transition de contrat :** nouveau rendu sans autorité de verdict, inventaire des consommateurs de `verify_claim`, proposition de version/compatibilité, E2E, banc de latence. Aucun changement public de protocole avant arbitrage.

Ces lots sont un **ordre de revue**, pas une autorisation d'ouvrir ou fusionner des PR. Les noms exacts des modules et la compatibilité doivent être confirmés dans l'état du code au démarrage du travail ; les récits déjà approuvés priment, sans élargissement silencieux de périmètre.

## 15. Conditions de clôture et validation du responsable du produit

Le récit sera considéré livré lorsque :

- les invariants INV-01 à INV-10 et les critères AC-01 à AC-20 ont des tests reproductibles et exécutés ;
- la source de vérité reste Taxo, tandis que la mémoire de Minia n'est qu'un état de navigation ;
- le LLM peut parcourir une Maille ramifiée sur plusieurs Tuiles successives et demander du code sous consentement ;
- l'interruption/reprise reproduit l'état exactement, sans saturation du contexte ;
- la confidentialité, le versionnement, les budgets et les consommations sont vérifiables ;
- aucune migration silencieuse ne modifie la sémantique publique de `verify_claim` ;
- les performances, les limites et les écarts sont documentés honnêtement.

### Arbitrages — décidés le 11 octobre 2026

Les cinq arbitrages ci-dessous ont été validés tels quels par le responsable du produit le 11 octobre 2026.

1. Valider la suppression du **pouvoir de verdict sur les conclusions du LLM** dans le parcours cible, et demander l'étude de compatibilité des usages existants de `verify_claim`.
2. Valider **la phase 1 individuelle** (SQLite WAL), en reportant la mémoire collective et l'évaluation de RocksDB.
3. Valider le principe des **budgets renouvelables justifiés**, avec plafonds d'exploitation et tests de boucle ; fixer les valeurs seulement après mesure.
4. Valider les **notes `HYPOTHESIS_LLM`**, la **confirmation explicite de la question minimisée par l'utilisateur avant persistance et reprise**, les reçus sans contenu et la déclaration finale structurée du LLM.
5. Valider le découpage en lots avant toute modification, ouverture de PR ou fusion.

### Choix de mise en œuvre retenus à l'acceptation

- **Aucun changement de sémantique de `verify_claim`** ni de version de `taxo-query/1` dans les lots A à C. Le nouveau
  parcours cesse de présenter des verdicts sur les conclusions du LLM ; les contrôles structurels, de sécurité, de
  provenance, de références et d'autorisation restent en place.
- Le **lot D** s'arrête à l'inventaire des usages de `verify_claim` (consommateurs, tests, schémas, écrans) et à une
  proposition de compatibilité. Toute évolution publique du protocole attend un arbitrage explicite (ROUGE protocole).
- Chaque lot est une PR testable seule ; les valeurs de budget partent de celles de Minia aujourd'hui jusqu'à mesure.

> **Aucun changement de protocole public ni aucune fusion sans accord explicite du responsable du produit.**

## 16. Références de l'existant consulté

- [Architecture Taxo — § 9 : Maille, `neighborhood/2`, Explorer et frontières](https://github.com/kadt2022/taxo/blob/main/docs/ARCHITECTURE.md)
- [Architecture Taxo — § 12 : MIP, `taxo-query/1`, Minia, `verify_claim`, consentements](https://github.com/kadt2022/taxo/blob/main/docs/ARCHITECTURE.md)
- [README Taxo — exploration Minia, `get_tile`, `get_source`](https://github.com/kadt2022/taxo/blob/main/README.md)
- [Dépôt d'exercice — Student Course Demo](https://github.com/kadt2022/student-analysis-java)

**Note de traçabilité :** ces références décrivent le dépôt GitHub consulté lors de la rédaction ; elles ne constituent pas un test d'exécution de l'instance Taxo locale ni une preuve que toutes les fonctions sont activées sur la machine de développement.

## Bilan de clôture (11 octobre 2026)

| PR | Contenu |
| --- | --- |
| #131 | Le récit. |
| #132 (A) | Carnet de navigation pur : enquête, budget par tranches, notes `HYPOTHESIS_LLM`, journal des opérations et des livraisons, état versionné. |
| #133 (B) | Mémoire SQLite WAL du carnet, reprise, expiration, migrations et conflits d'écriture. |
| #134 (C) | Orchestration par Minia : enquête navigable par l'API (SSE), annonce avant l'envoi, déclaration confrontée aux livraisons, `verify_claim` absent de l'enquête. |
| #135 (D) | Inventaire de `verify_claim` ; coexistence retenue, `taxo-query/1` inchangé. |

Le rejeu contre un vrai modèle est fait par le responsable du produit hors du récit ; la clôture n'en dépend pas.
Un écart constaté donnera un nouveau récit.
