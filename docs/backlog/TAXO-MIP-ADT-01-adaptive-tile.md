# TAXO-MIP-ADT-01 — Adaptive Tile : la Maille au service des intelligences artificielles

**Projet :** Taxo V2  
**Date :** 10 octobre 2026  
**Nature :** récit d'implémentation majeur  
**Statut :** accepté par le responsable du produit le 10 octobre 2026 (fusion avec TAXO-MIP-SOURCE-01, champ `profile`
et annotations observées acceptés ; classification des Tuiles ajoutée le même jour, § 21 bis). PR A en cours.  
**Priorité :** haute.  
**Dépendance préalable :** [TAXO-MINIA-SEC-01](TAXO-MINIA-SEC-01-fiabilisation-et-confidentialite.md) — fiabilité et
confidentialité.  
**Rattachement :** [TAXO-MIP-SOURCE-01](TAXO-MIP-SOURCE-01-lecture-du-code-par-la-maille.md), qu'il absorbe (§ 0), et
[TAXO-01N / MIP-01](TAXO-01N-ask-taxo-general.md).

---

## 0. Articulation avec TAXO-MIP-SOURCE-01 (fusion décidée le 10 octobre 2026)

TAXO-MIP-SOURCE-01, accepté le 10 octobre 2026, porte déjà `get_source` et la lecture progressive des méthodes par
Minia. Ce récit en reprend tout le contenu (PR B et C) et y ajoute les profils adaptatifs (PR A). Trois
articulations étaient possibles :

| Option | Effet | Avis |
| --- | --- | --- |
| **Fusion** : ce récit absorbe TAXO-MIP-SOURCE-01 | un seul récit, un seul propriétaire de `get_source` ; les exigences E1 à E6 et les tests d'acceptation de SOURCE-01 deviennent des exigences des PR B, C et D ci-dessous | **recommandée** |
| Dépendance : SOURCE-01 garde `get_source` et Minia, ce récit ne garde que les profils | pas de doublon, mais la démonstration du § 30 et le banc du § 24 E appartiennent aux deux récits à la fois | possible |
| Remplacement : SOURCE-01 est abandonné | perd un récit déjà accepté et ses règles reprises de TAXO-UI-06 | déconseillée |

Avec la fusion :

- le fichier de TAXO-MIP-SOURCE-01 reste dans le backlog, jamais supprimé, avec un renvoi vers ce récit ; il sera
  rangé dans `termines/` avec celui-ci ;
- la PR B de ce récit est la PR A de SOURCE-01 : elle reprend les règles de `get_source` écrites dans
  [TAXO-UI-06](TAXO-UI-06-vue-chaine-uml-taxo.md) (code d'un symbole localisé par une preuve, plafonds, instantané de
  l'analyse, empreinte égale au `content_hash`, double consentement, fichiers jamais lus). Les renvois de TAXO-UI-06
  à SOURCE-01 désignent désormais cette PR ;
- la dépendance envers TAXO-MINIA-SEC-01 est inchangée : aucune transmission de code à un LLM avant sa clôture.

## 1. Décision fondamentale

Le responsable du produit confirme la doctrine architecturale de Taxo :

**Taxo n'est pas une intelligence artificielle. Il n'a pas vocation à le devenir.**

Taxo extrait des informations présentes dans le logiciel, construit une cartographie, conserve des relations, des
observations, des preuves et les limites de leur extraction.

Il n'a pas à comprendre les intentions des développeurs, la signification métier d'une annotation ou les
conséquences d'une configuration.

Cette responsabilité appartient aux consommateurs intelligents de la Maille, notamment les LLM, par
l'intermédiaire de Minia.

La séparation recherchée est :

**Maille → MIP → Minia → LLM**

- **Maille :** représentation persistée du logiciel analysé, de ses faits, relations, provenances et frontières.
- **MIP :** Maille Interaction Protocol, contrat permettant de consulter la Maille et de transporter des Tuiles.
- **Adaptive Tile :** Tuile dont la sélection d'informations dépend d'un profil déclaré, d'une ancre et d'un budget.
- **Minia :** orchestrateur logiciel des échanges, des demandes, des autorisations et des réponses.
- **LLM :** composant chargé du raisonnement, de l'interprétation, de l'explication et des hypothèses.
- **Humain :** décideur final.

La simplicité déterministe de Taxo est une propriété architecturale à préserver.

**Il est interdit d'introduire dans Taxo un raisonnement sémantique ou probabiliste pour compenser les erreurs d'un
LLM.**

Cette interdiction n'empêche pas Taxo de résoudre mécaniquement des références et de construire des relations
structurelles selon des règles explicites. Ces opérations restent traçables, limitées et indépendantes d'une
interprétation métier.

## 2. Pourquoi ce récit existe

Taxo possède déjà les principales fondations de la Maille :

- des faits et relations entre éléments logiciels ;
- des preuves localisées ;
- des instantanés de code ;
- des arbres et voisinages d'appels ;
- des mécanismes de couverture et de frontières ;
- des budgets et des continuations ;
- un protocole `taxo-query/1` ;
- un premier adaptateur MIP 0.1 ;
- une boucle d'exploration Minia–LLM.

Pourtant, le banc de 18 tests réalisé sur `student-course-demo`, le 10 octobre 2026, montre une limite importante.

Minia sait retrouver certaines chaînes d'appels, mais manque parfois des informations nécessaires pour interpréter
le comportement réel des méthodes. Elle peut alors supposer, s'abstenir, ou produire des affirmations incorrectes.

Les tests 9, 11 et 18 révèlent notamment des erreurs concernant les protections de routes Java Spring.

Deux simulations manuelles consistant à transmettre de petits extraits de code ont amélioré certaines réponses.
Ces essais restent préliminaires : les extraits avaient été choisis par le testeur, et non découverts de manière
autonome par Minia.

**Le problème à résoudre n'est pas de rendre Taxo plus intelligent.**

Le problème est de permettre aux LLM de demander et de recevoir les informations exactes dont ils ont besoin,
progressivement, à travers la Maille. L'Adaptive Tile a précisément été conçue pour cela.

## 3. Ne pas réinventer l'Adaptive Tile

La définition existante dans [`ARCHITECTURE.md`](../ARCHITECTURE.md), § 9.5, reste la référence.

Une Tuile adaptative est une projection de la Maille choisie pour un consommateur à partir :

1. d'une ancre résolue ;
2. d'un profil déclaré et versionné ;
3. d'un budget ;
4. d'un instantané déterminé.

Les profils sont fermés et déterministes. Un profil ne comporte ni interprétation libre de la question, ni
instruction destinée à un LLM.

Pour une même analyse, la même ancre, le même profil et les mêmes budgets, la sélection produite est identique.

Chaque élément transmis doit pouvoir être expliqué par sa provenance, son chemin dans la Maille et la règle qui l'a
sélectionné.

La Tuile n'est pas un nouveau stockage et n'est pas un nouveau type de fait. Elle représente une portion
consultable de la Maille.

**Ce récit complète l'Adaptive Tile existante ; il ne crée pas un Adaptive Tile Engine parallèle.**

## 4. Résultat produit attendu

Un utilisateur interroge Ask Taxo : « Est-ce que GET /api/students est protégée contre les injections ? »

Minia transmet la question à un LLM autorisé. Le LLM commence son exploration : « Donne-moi la méthode qui traite
cette route. » Minia demande la référence correspondante à Taxo. Taxo retrouve le contrôleur à travers la Maille et
restitue une Tuile.

La Tuile peut contenir, selon la demande autorisée :

- la référence canonique de la méthode ;
- sa classe propriétaire ;
- les annotations réellement présentes (voir § 6.2, écart 1) ;
- sa déclaration ;
- les références des appels sortants ;
- les références des appelants ;
- ses preuves et leur localisation ;
- l'instantané analysé ;
- les frontières connues ;
- une référence vers son extrait source, si disponible.

Le corps de la méthode Java peut être consulté séparément, sous autorisation explicite.

Le LLM lit ce code, identifie les méthodes qui lui paraissent pertinentes, puis demande les Tuiles suivantes.
L'exploration continue aussi longtemps que les budgets et autorisations le permettent. Le modèle peut ensuite
proposer une interprétation ou une correction.

**Taxo ne transforme jamais cette interprétation en observation du code.**

## 5. Exemple de dialogue d'acceptation

Le scénario suivant constitue une simulation fonctionnelle.

**Utilisateur :** « Vérifie si GET /api/students présente un risque d'injection. »

**Minia → LLM :** « Taxo a localisé la route GET /api/students. Elle est associée à
`StudentController.searchStudents()`. Quels éléments souhaites-tu consulter ? »

**LLM :** « Donne-moi la déclaration complète de la méthode, ses annotations et son code. »

**Minia → MIP :** demande de consultation de la référence canonique correspondante, avec un profil de contexte de
méthode et une demande de source autorisée.

**Taxo → Minia :** Tuile de `StudentController.searchStudents()` avec :

- déclaration de la méthode ;
- annotations présentes ;
- appels vers `StudentQueryUtils.normalize()` et `StudentService.searchByName()` ;
- provenance et lignes ;
- références permettant l'expansion.

Pièce source demandée, si le consentement est accordé.

**LLM :** « Je voudrais lire le code des deux méthodes appelées. »

**Minia :** les demandes sont transmises à Taxo et servies selon les budgets.

**Taxo :** fournit les deux Tuiles ciblées et les extraits disponibles.

**LLM :** « Je constate que `StudentService` porte `@Service`. Peux-tu le confirmer ? »

**Minia → Taxo :** « Restitue les annotations observées sur la déclaration de `StudentService`. »

**Taxo :** « Annotation relevée sur cette déclaration : `@Component`. »

**Minia → LLM :** « Correction : la déclaration inspectée porte `@Component`, pas `@Service`. »

**LLM :** « Merci. Je corrige ma description. Je poursuis l'analyse du chemin conduisant à la requête SQL. »

Dans ce dialogue :

- Taxo ne connaît pas la signification de `@Service` ;
- Taxo ne prétend pas que `@Component` protège ou exécute quoi que ce soit ;
- Minia n'invente pas les annotations ;
- le LLM peut se tromper, être corrigé et poursuivre ;
- l'identité des observations demeure indépendante du raisonnement du modèle.

Le verdict de Taxo sur l'affirmation « `StudentService` porte `@Service` » reste `NOT_PROVEN`
(`NOT_FOUND_IN_ANALYSED_SCOPE` si la déclaration a été lue), jamais `REFUTED` : `ANNOTATED_WITH` n'est pas une
relation exclusive (ARCHITECTURE § 12.4). « Pas `@Service` » est la lecture que Minia tire de la liste complète des
annotations observées, présentée comme telle.

Le comportement cible est atteint lorsque cette exploration se déroule sans sélection manuelle des méthodes par le
testeur.

---

## 6. État réel de l'implémentation au démarrage

Le développeur commence par vérifier la révision locale effective et les capacités livrées. Les spécifications plus
anciennes marquées « à construire » dans la documentation ne remplacent pas l'état réel du code.

### 6.1 Capacités (vérifiées au commit `e3bfc45` de `main`, 10 octobre 2026)

| Capacité | État |
|---|---|
| `taxo-query/1` | disponible |
| `find_references` (préfixe et `match: NAME`) | disponible |
| `get_neighborhood` : `neighborhood/1` et `neighborhood/2` (pas combinés `steps`, reprises) | disponible |
| `verify_claim` avec `limits` | disponible |
| MIP 0.1 `EXPAND`, `POST /api/projects/{id}/mip/query` | servie ; la requête n'accepte que `relations` et une seule `direction`, pas `steps` ni `profile` |
| MIP `PROJECT` | réservée, refus explicite (`NOT_AVAILABLE`) |
| Profils de Tuile adaptative (§ 9.5) | documentés, aucun manifeste ni résolveur dans le code |
| `get_source` | réservée, non implémentée |
| Navigation Minia par opérations successives | disponible |
| Lecture progressive des corps Java par Minia | non livrée |

Fichiers principaux à examiner :

- `backend/app/mip/domain/query.py`, `backend/app/mip/domain/tile.py`, `backend/app/mip/application/service.py` ;
- `backend/app/protocol/application/exchange.py`, `backend/app/protocol/application/neighborhood_request.py` ;
- `backend/app/neighborhood/domain/` (parcours, nœuds avec niveau et fait découvreur) ;
- `backend/app/minia/domain/exploration.py` ;
- `backend/app/evaluators/java/syntax.py`, `backend/app/evaluators/java/sources.py` ;
- `docs/ARCHITECTURE.md`, notamment § 5.6, § 9.5, § 12 et § 14.

Les fonctionnalités existantes sont réutilisées sans réécriture inutile.

### 6.2 Écarts constatés entre ce récit, le code et ARCHITECTURE § 9.5

Relations réellement produites par les analyseurs livrés (catalogues des évaluateurs) :

| Relation | Producteur | Ce qu'elle relie réellement |
| --- | --- | --- |
| `CONTAINS` | appels Java (`taxo.java-calls`) | fichier → type ; type → membres (méthodes, champs, types) ; méthode → paramètre ou variable receveur d'un appel établi ; record → accesseur implicite (`INFERRED`) |
| `CALLS` | appels Java | méthode → méthode, `INFERRED`, prouvé par ses sites d'appel |
| `TYPED_AS` | appels Java | champ, paramètre ou variable → type **des sources** ; pas de type de retour de méthode |
| `EXTENDS`, `IMPLEMENTS` | appels Java | type → supertype des sources (`OBSERVED`) ; méthode → méthode d'interface (`IMPLEMENTS`, `INFERRED`) |
| `ANNOTATED_WITH` | Spring Security seul | **uniquement** le type qui active la sécurité de méthode (`@EnableMethodSecurity`) |
| `AUTHORIZED_BY` | Spring Security | règle d'URL ou méthode → expression (`@PreAuthorize` lu) |
| `HANDLED_BY`, `SERVED_BY`, `MATCHED_BY`, `PROTECTED_BY`, `CONFIGURES`, `PERMITS_ALL` | Spring API, Spring Boot, Spring Security | voir ARCHITECTURE § 5.6 |
| `DISPATCHES_TO`, `ACCEPTS`, `RETURNS` | aucun | jamais produites |

Écarts qui en découlent :

1. **Annotations.** Le lecteur Java lit déjà toutes les annotations des types et des méthodes, valeurs écrites
   comprises, mais la Maille n'en garde qu'une (`@EnableMethodSecurity`). `@Component`, `@Service` ou `@Toto` ne
   sont donc pas des faits aujourd'hui : le § 5, les tests B2 et B3 et la vérification d'une annotation par
   `verify_claim` ne sont servables que par une pièce source (PR B). Pour qu'ils soient des **observations**, il
   faut que le lecteur Java produise `ANNOTATED_WITH` (`OBSERVED`, relation déjà au vocabulaire) pour chaque
   annotation écrite sur un type ou une méthode des sources, sans aucune interprétation. C'est un enrichissement de
   la Maille : **décision du responsable du produit**, proposée comme PR A2 (§ 23).
2. **`method-context/1`.** `EXTENDS` ne relie que des types, `TYPED_AS` ne donne pas le type de retour, et la
   classe propriétaire d'une méthode s'atteint par `CONTAINS` **entrant**. Le profil suit donc des pas combinés
   (`steps` de `neighborhood/2`) ; le type de retour reste dans la pièce source.
3. **`calls/1`.** `DISPATCHES_TO` n'est jamais produite : le profil la déclare et rend une frontière de contexte
   (§ 9.5, règle 5), sans promettre de dispatch.
4. **`security/1`.** Le tableau du § 9.5 ne connaît pas `CONFIGURES` ni `ANNOTATED_WITH`, livrés par
   TAXO-MINIA-SEC-01 (#120), et sa route → méthode → `AUTHORIZED_BY` demande aussi des pas combinés. Le profil
   reste celui du § 9.5 en version 1 ; l'ajout de ces relations est une version 2 à décider à part.
5. **Contrat du profil.** Le § 9.5, règle 2, exige que le contrat « profil → paramètres explicites » soit fixé et
   testé avant le premier profil. Le moteur sait déjà dire, pour chaque nœud, son niveau et le fait qui l'a
   découvert (le chemin se reconstruit) ; il ne connaît pas la « règle du profil » qui l'a retenu.
6. **Entrée MIP.** Choisir un profil demande un champ facultatif `profile` dans la requête `EXPAND` et, dans la
   Tuile, les paramètres résolus et la règle par élément. Ces ajouts sont compatibles (champs facultatifs) mais
   touchent le contrat MIP : **décision du responsable du produit** avant leur publication. Un profil reste une
   forme d'`EXPAND` (§ 9.5 : TILE = `get_neighborhood`) ; `PROJECT` reste refusée.
7. **Faits `INFERRED` existants** (`CALLS`, `IMPLEMENTS` entre méthodes, accesseurs de record, `SERVED_BY`,
   `MATCHED_BY`, `PROTECTED_BY`) : inventoriés ici, conservés sans changement de sens (§ 15).
8. **ARCHITECTURE § 5.6** indique encore « aucun » producteur pour `CALLS`, `CONTAINS` entre symboles, `EXTENDS`,
   `IMPLEMENTS` et `TYPED_AS`, livrés depuis TAXO-01K et TAXO-01L. À corriger dans la PR A, qui touche ce
   vocabulaire.

## 7. Architecture technique cible

Le parcours général reste :

Utilisateur → Ask Taxo → Minia → LLM → demande de consultation par Minia → MIP → `taxo-query/1` → Maille → Tuile →
Minia → LLM

Le LLM choisit ce qu'il souhaite lire. Minia traduit ce choix en demandes structurées, connues du protocole et
soumises aux autorisations. Taxo exécute la consultation de manière déterministe.

Le MIP ne possède aucune logique de sécurité Spring, de persistance JPA, de SQL ou de raisonnement applicatif.
Minia ne constitue pas un deuxième moteur de faits.

Le système ne nécessite pas d'inventer un modèle d'intelligence artificielle supplémentaire pour incarner Minia. Il
s'agit d'une couche d'orchestration logicielle capable de travailler avec différents fournisseurs LLM.

## 8. Structure fondamentale d'une Tuile

La structure MIP existante est conservée. Une Tuile dispose notamment :

- d'une version de protocole ;
- d'une expression demandée ;
- d'un résultat ou refus ;
- d'un instantané ;
- d'une référence centrale ;
- des nœuds sélectionnés ;
- des faits sélectionnés ;
- des preuves accessibles ;
- des informations de couverture ;
- des frontières ;
- des bornes demandées et appliquées ;
- des informations de consommation ;
- d'un indicateur de troncature ;
- d'une continuation lorsque disponible.

L'Adaptive Tile ajoute à cette logique la sélection par un profil explicite. Les éléments sélectionnés par un profil
sont rattachables à une règle de sélection et, lorsqu'ils proviennent d'un parcours, à leur chemin depuis l'ancre.

Le contenu d'une Tuile n'est pas complété par des informations supposées. Un élément absent de la réponse peut
signifier :

- non disponible dans la Maille ;
- non couvert par l'analyse ;
- non sélectionné par le profil ;
- hors budget ;
- non transmis pour confidentialité ;
- non autorisé ;
- arrêt du parcours à une frontière.

Ces situations restent distinctes.

## 9. Profils adaptatifs

Les profils ne sont pas des prompts. Ce sont des déclarations techniques versionnées qui sélectionnent des
relations et des paramètres de parcours.

### Profil de contexte de méthode

Nom proposé : `method-context/1`. Ancre : référence canonique d'un symbole de méthode.

Objectif : donner au consommateur une vue bornée de la méthode et de son contexte immédiatement disponible dans la
Maille.

Relations candidates, uniquement lorsqu'elles sont réellement produites (§ 6.2) : `CONTAINS`, `ANNOTATED_WITH`,
`CALLS`, `TYPED_AS`, `IMPLEMENTS`, `EXTENDS`.

La disponibilité de ces relations et leur orientation sont vérifiées dans le contrat et les analyseurs existants. Le
profil ne promet pas une relation simplement parce qu'elle appartient au vocabulaire.

### Profil d'exploration des appels

Nom proposé : `calls/1`. Ancre : route ou méthode. Relations principales : `HANDLED_BY`, `CALLS`, `DISPATCHES_TO`.

Il reprend la logique de l'axe Appels déjà présent dans le portail.

### Profil de structure

Le profil `structure/1`, déjà envisagé dans l'architecture, s'appuie sur les relations de structure disponibles.

### Profil de sécurité structurelle

Le profil `security/1` déjà documenté peut sélectionner les relations disponibles autour d'une route et de sa
configuration.

**Il ne prétend pas démontrer la sécurité effective de la route.** Son nom désigne un parcours documentaire, pas une
conclusion.

Les profils déjà conçus dans `ARCHITECTURE.md` priment sur les noms proposés ici. Toute incompatibilité est signalée
avant modification.

## 10. Règle de déterminisme des profils

Chaque profil a un manifeste déclaratif fermé. Le manifeste indique notamment :

- son identifiant et sa version ;
- les références d'ancrage acceptées ;
- les relations suivies ;
- le sens du parcours ;
- la profondeur ;
- l'ordre de priorité ;
- les limites applicables ;
- la politique de présentation des preuves ;
- les conditions connues d'incomplétude.

Pour une même analyse et une même demande effective, le résultat est reproductible. La sélection issue d'un profil
est reproductible par les paramètres explicites du moteur de voisinage.

**Aucune logique cachée de classement par intelligence artificielle n'intervient dans le choix des faits.**

Un profil peut être choisi par Minia après une demande du LLM, mais Taxo n'interprète jamais le sens de cette
demande pour fabriquer un profil improvisé.

## 11. Respect du contrat MIP existant

Le MIP 0.1 sert actuellement `EXPAND`. Le comportement de cette expression et les réponses existantes sont
préservés.

L'expression `PROJECT` existe dans le vocabulaire mais demeure refusée tant qu'une règle de projection n'est pas
spécifiée, testée et validée.

Première étape : réaliser les profils en les traduisant vers les paramètres explicites du moteur existant, sans
modifier silencieusement la requête publique MIP 0.1.

L'activation de `PROJECT` et toute modification du contrat sont présentées au responsable du produit avant
réalisation.

Aucun nouveau protocole concurrent de `taxo-query/1`. Aucune seconde base de faits. Aucune duplication des
algorithmes de voisinage.

## 12. La lecture ciblée du code Java

C'est la capacité majeure à compléter.

L'opération `get_source`, actuellement réservée, permet de consulter le code exact d'un symbole présent dans un
instantané autorisé. La demande porte sur une référence de symbole, pas sur un chemin libre fourni par le LLM.

Exigences :

- résolution exacte du symbole ;
- gestion des méthodes surchargées ;
- respect de la classe et de la signature ;
- lecture dans l'instantané fixé ;
- extraction du corps de méthode concerné ;
- possibilité de restituer sa déclaration et ses annotations, lorsque demandé ;
- références de fichier et lignes ;
- empreinte du contenu ;
- limite de taille ;
- refus explicite en cas de contenu indisponible ou interdit.

Le mécanisme réutilise le lecteur de sources et l'analyse syntaxique déjà disponibles. Le pilote porte sur Java,
sans créer dans le protocole une opération nommée exclusivement pour Spring ou Java.

Les exigences E1 à E6 de [TAXO-MIP-SOURCE-01](TAXO-MIP-SOURCE-01-lecture-du-code-par-la-maille.md) et les règles de
`get_source` écrites dans TAXO-UI-06 font partie de ce chapitre (§ 0).

### Distinction impérative

Une Tuile transporte une projection factuelle de la Maille. Un extrait de code source est une **pièce source
consultée sous consentement**.

Il peut être associé à la consultation d'une Tuile, mais il ne devient pas automatiquement une nouvelle relation ou
un nouveau fait. La représentation machine préserve cette distinction.

Pour un consommateur, Minia peut présenter la Tuile et sa pièce source associée dans un même contexte d'échange
autorisé. Le format filaire existant n'est pas modifié pour insérer arbitrairement des fichiers dans toutes les
Tuiles.

## 13. Cohérence des instantanés

Aucun mélange entre plusieurs versions du dépôt. Une recherche, une Tuile, sa continuation, les sources demandées et
les affirmations vérifiées se rattachent à l'analyse choisie.

Si la Maille a été construite sur le commit A et que le dépôt local se trouve désormais sur le commit B, une demande
de code liée à A ne retourne jamais silencieusement le code de B.

La sélection du code utilise les mécanismes de snapshot existants. Pour un instantané de type working-tree, les
empreintes et les conditions de cohérence sont également respectées.

En cas d'impossibilité de garantir la cohérence, le code n'est pas transmis et la raison est communiquée. Le contenu
et ses métadonnées correspondent au même état source.

## 14. Annotations : extraction sans interprétation

Ce récit confirme explicitement la décision du responsable du produit : **Taxo n'a pas à comprendre la signification
des annotations.**

Exemple :

```java
@Toto(role = "ADMIN")
public Student get(Long id) {
    return repository.findById(id);
}
```

Taxo peut restituer :

- annotation : `@Toto(role = "ADMIN")` ;
- méthode : `get(Long)` ;
- type de retour : `Student` (par la pièce source, § 6.2, écart 2) ;
- appel observé ou relation mécaniquement résolue vers `findById` ;
- emplacement exact.

Taxo ne cherche pas à savoir :

- si `@Toto` est une annotation officielle ;
- si elle appartient à Spring ;
- si elle protège la méthode ;
- si elle fonctionne correctement ;
- si elle présente un problème de sécurité.

Il n'est pas nécessaire de construire un catalogue JSON de la sémantique des annotations Spring.

Les annotations inconnues sont conservées comme observations syntaxiques lorsqu'elles sont lisibles. Les expressions
ou valeurs impossibles à résoudre sont restituées dans leur forme écrite et marquées comme telles.

Un test utilise une annotation fictive inconnue des bibliothèques de Taxo pour démontrer cette neutralité.

## 15. Relations déterministes et conclusions métier

Certaines relations structurelles nécessitent une résolution mécanique. Par exemple, une instruction
`service.get()` peut conduire Taxo à une déclaration candidate si les règles d'identification permettent de la
sélectionner. Cette relation conserve la provenance, les prémisses et les limites de cette résolution. Cela ne
signifie pas que Taxo comprend le comportement de `service.get()` à l'exécution.

De même, une annotation `@PreAuthorize` peut être constatée dans le code sans que Taxo déclare que l'accès à la
méthode est effectivement sécurisé.

Le code actuel possède des relations et des faits `INFERRED`, notamment autour de certaines règles de sécurité
(inventaire au § 6.2, écart 7). Ils sont conservés pendant ce récit, sans modification silencieuse de leur
signification. Toute décision visant à réduire ou modifier leur sémantique relève d'un changement séparé, soumis au
responsable du produit.

**Le récit Adaptive Tile ne provoque pas une refonte cachée des analyseurs existants.**

## 16. Réutilisation des axes Appels et Chaîne

Les vues Appels et Chaîne sont deux projections de la même Maille. Aucun graphe supplémentaire n'est construit pour
le LLM.

L'axe Appels reste adapté à la consultation des chemins entre méthodes. La vue Chaîne permet de découvrir d'autres
relations lorsque le besoin le justifie.

La première réalisation de l'Adaptive Tile reste ciblée. Le consommateur peut demander :

- des appelants ;
- des méthodes appelées ;
- des déclarations associées ;
- des annotations ;
- des relations de structure disponibles.

Il n'obtient pas automatiquement toutes les relations de la Chaîne simplement parce qu'il demande une méthode.

La proposition future de deux modes d'exploration utilisateur reste hors du périmètre de ce récit, sauf validation
spécifique.

## 17. Contrôle de la quantité d'informations

L'Adaptive Tile doit contribuer à réduire les échanges inutiles. Mais la réduction des tokens n'est pas garantie par
le simple emploi d'une Tuile. Il faut distinguer :

- la taille du contexte transmis au LLM ;
- le nombre d'appels au modèle ;
- le nombre de consultations de la Maille ;
- le coût de répétition de l'historique conversationnel ;
- la durée totale de la réponse.

La composition reste bornée. Une demande de `StudentService.get()` ne déclenche pas la lecture automatique de toutes
les méthodes appelées. Un profil peut récupérer des références utiles pour les explorations suivantes sans
transmettre leurs corps.

Une limite atteinte produit une frontière ou un refus explicite. Une continuation ne devient pas un moyen de
contourner les plafonds globaux de l'échange.

Les doublons inutiles dans une même trajectoire Minia sont évités lorsque leur suppression respecte la sémantique des
demandes.

## 18. Confidentialité des Tuiles et des sources

La confidentialité est un prérequis bloquant. Le récit TAXO-MINIA-SEC-01 assure les protections de transmission
avant l'activation de nouvelles lectures de code à destination d'un LLM.

### Informations d'identité

Les noms, adresses électroniques et identités d'auteurs de commits ne sont pas transmis sans nécessité à un
fournisseur de modèle.

Exemple — Tuile locale autorisée :

- commit : identifiant de révision ;
- date : 2 août 2026 ;
- auteur : valeur originale conservée localement.

Représentation destinée au LLM :

- commit : identifiant de révision ;
- date : 2 août 2026, uniquement si demandée ou pertinente ;
- auteur : `******`, ou champ omis.

Un nom masqué visuellement dans le portail ne constitue pas une protection si sa valeur originale figure encore dans
le payload. Les pseudonymes restent propres à la demande, sans permettre de retrouver directement l'identité.

### Secrets

Les secrets sont masqués avant transmission, tout en conservant les observations utiles. Exemple : un mot de passe
codé en dur peut être signalé comme valeur littérale présente, sans envoyer le secret lui-même.

Les journaux et les trajectoires ne reconstituent pas les secrets masqués.

### Autorisations de code

`get_source` exige son propre double consentement :

1. activation explicite côté serveur ;
2. autorisation explicite pour la requête concernée.

Le consentement `get_diff` n'autorise jamais `get_source`.

Le fournisseur distant nécessite un avertissement clair et une autorisation non présélectionnée.

Le code n'est jamais transmis automatiquement au motif qu'une Tuile contient la référence de la méthode.

### Protection des frontières

- Aucune lecture arbitraire de chemin.
- Aucune exécution de code du dépôt.
- Aucun contenu confidentiel lu en dehors des politiques existantes.
- Aucune traversée de liens ou de fichiers interdits.
- Tout refus est explicite, sans divulgation du contenu refusé.

## 19. Compatibilité avec les différents LLM

Le MIP ne dépend d'aucun fournisseur. Minia expose le même contrat de consultation à différents LLM :

- les fournisseurs distants déjà pris en charge par Minia ;
- Ollama et les modèles locaux ;
- les fournisseurs futurs.

La structure des observations n'est pas adaptée à la manière de raisonner d'un fournisseur particulier. La
différence entre fournisseurs relève de leurs capacités à utiliser les Tuiles et à interpréter leur contenu.

Les budgets et le format de transmission peuvent être adaptés par Minia, sans changer l'autorité des observations de
Taxo.

Le fonctionnement sans LLM reste disponible : la Maille et le MIP peuvent être consultés de manière autonome.

## 20. Modes de fonctionnement du produit

Les capacités existantes de Taxo seul sont préservées.

**Taxo Core :** analyse le dépôt, produit les faits, construit la Maille, expose les Tuiles, permet la navigation et
la consultation sans LLM.

**Taxo Collaborative :** réutilise exactement la même Maille, ajoute Minia et le LLM, permet l'exploration
conversationnelle, utilise les Tuiles et les sources autorisées, produit des interprétations distinctes des
observations.

L'échec, l'indisponibilité ou la lenteur du fournisseur LLM n'empêche pas Taxo Core de remplir sa mission.

## 21. Séparation entre observations et interprétations

Le portail et Minia conservent une distinction explicite :

- **Observations Taxo :** uniquement des éléments extraits ou des relations structurelles déterministes, avec
  provenance et limites.
- **Pièces sources :** les extraits du véritable code autorisé, rattachés à un instantané et à un emplacement.
- **Interprétations du LLM :** les raisonnements, hypothèses, explications et recommandations.

Un LLM qui écrit « Cette méthode est vulnérable aux injections SQL » ne crée pas un fait Taxo. La présence dans les
sources d'une concaténation SQL peut être montrée. L'affirmation de vulnérabilité appartient à l'analyse du LLM et
peut nécessiter une validation technique supplémentaire.

Une affirmation structurée peut être soumise à `verify_claim`, mais le verdict ne couvre que l'assertion que Taxo
peut réellement vérifier. Une phrase de portée plus large n'hérite jamais automatiquement d'un verdict favorable.

## 21 bis. Classification des Adaptive Tiles (normatif)

Exigence du responsable du produit du 10 octobre 2026. Chaque Tuile expose des **métadonnées de classification
versionnées**, et à part ses **restrictions de divulgation**.

| Métadonnée | Contenu |
|---|---|
| Nature | ce que désigne l'ancre : `METHOD`, `TYPE`, `MEMBER`, `ENDPOINT`, `COMMIT`, `MODULE`, `FILE`… lue dans la syntaxe de la référence. La Maille ne distingue pas aujourd'hui une classe d'une interface, d'un record ou d'une énumération : la nature d'un type reste `TYPE` tant qu'aucun fait ne le dit |
| Langage | celui que la référence écrit, ou celui d'un fait `WRITTEN_IN` transmis ; sinon inconnu (`null`) |
| Profil adaptatif | l'identifiant du profil appliqué, ou aucun |
| Catégories de contenu présentes | parmi `FACTS`, `RELATIONS`, `EVIDENCE`, `CODE_SOURCE`, `COMMIT_METADATA`, `COVERAGE`, `FRONTIER` |
| Provenance et instantané | analyse, commit, révision des faits, producteurs des faits transmis |
| Restrictions de divulgation | séparées de la classification descriptive : protections qui s'appliquent au contenu présent avant un fournisseur de modèle |

Règles :

1. La classification décrit la Tuile ; elle n'est pas la Tuile, ne change pas sa sélection et ne duplique aucun fait.
2. `CODE_SOURCE` n'est annoncé que lorsque du code a réellement été transmis après autorisation. Une Tuile de faits ne
   l'annonce jamais ; une pièce source associée (PR B) porte sa propre classification et reste distincte des faits.
3. `COMMIT_METADATA` correspond aux métadonnées Git effectivement transmises : SHA, dates et autres champs présents,
   l'auteur seulement s'il est transmis. L'identité de l'auteur est masquée dans toute transmission à un LLM
   (restriction `PERSON_IDENTITY`, couche de TAXO-MINIA-SEC-01).
4. La classification est construite à partir des données réellement présentes, sans inventer d'élément manquant.
5. Elle ne contient aucune interprétation fonctionnelle du code.
6. Elle réutilise les structures de la Maille et du MIP, sans second stockage ni duplication des faits.
7. Tests de cohérence obligatoires : catégories annoncées = contenu réellement transmis, y compris en cas de refus
   (aucune classification), de troncature et d'absence de code.
8. Champs additifs : les consommateurs MIP existants restent compatibles ; tout changement incompatible est soumis à
   validation.

Le socle (classification et restrictions de toute Tuile MIP) est livré par la PR A. La PR B l'étend à la pièce source
(`CODE_SOURCE`), la PR C le transmet à Minia.

## 22. Compatibilité et non-régression

Le récit ne casse aucune consultation actuellement servie :

- `neighborhood/1` conserve ses réponses existantes ;
- `neighborhood/2` conserve ses règles, frontières et reprises ;
- MIP `EXPAND` reste compatible ;
- MIP `PROJECT` reste refusée tant qu'elle n'a pas été approuvée et implémentée ;
- les références et faits ne changent pas de signification ;
- les budgets existants restent effectifs ;
- les droits d'accès existants restent effectifs ;
- les consultations d'historique Git restent opérationnelles ;
- les vues Appels et Chaîne continuent de fonctionner ;
- les consommateurs existants ne sont pas forcés de comprendre un nouveau format incompatible.

Une modification incompatible exige une nouvelle version explicite et l'accord du responsable du produit.

## 23. Plan d'implémentation proposé

### PR A — Composition adaptative sur la Maille existante

Objectif : rendre les profils déclaratifs utilisables sur le moteur existant.

Travaux :

- réutiliser les Tuiles MIP 0.1 ;
- définir la résolution déterministe des profils (manifestes fermés → paramètres explicites de `neighborhood/2`,
  pas combinés compris) ;
- vérifier les relations disponibles (§ 6.2) ;
- exposer les paramètres réellement appliqués ;
- tracer les règles et chemins de sélection ;
- préserver frontières, budgets, preuves et continuations ;
- tester le même résultat pour les mêmes paramètres, et l'égalité avec la même demande en mode explicite ;
- maintenir le refus de `PROJECT` ;
- mettre ARCHITECTURE § 5.6 et § 9.5 en accord avec les producteurs réels.
- livrer le socle de classification et de restrictions de divulgation de toute Tuile (§ 21 bis) et ses tests de
  cohérence.

Ne pas construire un nouveau graphe. Le domaine (manifestes, résolution, tests) peut être préparé sans toucher au
contrat ; le champ `profile` de la requête MIP et les champs ajoutés à la Tuile attendent l'accord du § 6.2,
écart 6.

### PR A2 — Annotations observées (si l'écart 1 du § 6.2 est accepté)

Objectif : que les annotations écrites soient des observations de la Maille, sans interprétation.

Travaux : `ANNOTATED_WITH` (`OBSERVED`) de chaque type et méthode des sources vers chaque annotation écrite, valeurs
dans leur forme écrite et marquées non résolues si besoin ; preuve à la ligne ; aucune liste d'annotations connues ;
test avec `@Toto` ; mesure du nombre de faits ajoutés sur les fixtures ; aucune modification des faits Spring
Security existants.

### PR B — Lecture source ciblée

Objectif : activer `get_source` conformément au contrat approuvé (reprend la PR A de TAXO-MIP-SOURCE-01).

Travaux :

- résolution exacte des références ;
- extraction de méthode et déclaration ;
- lecture depuis l'instantané fixé ;
- métadonnées de provenance et empreinte ;
- double consentement indépendant ;
- contrôles de confidentialité ;
- limitations de taille ;
- refus en cas d'ambiguïté ou d'indisponibilité ;
- tests Java, surcharges et instantanés.
- classification de la pièce source (`CODE_SOURCE` seulement si le code est transmis), distincte des faits.

Ne jamais exposer une opération de lecture arbitraire de fichier. Aucune transmission à un LLM avant la clôture de
TAXO-MINIA-SEC-01.

### PR C — Orchestration Minia

Objectif : permettre au LLM de demander les Tuiles et sources nécessaires (reprend la PR B de TAXO-MIP-SOURCE-01).

Travaux :

- exposer uniquement les capacités effectivement activées ;
- conserver la demande de référence avant toute consultation ;
- permettre des demandes successives ;
- transmettre les Tuiles avec leur provenance ;
- associer les sources consenties sans les confondre avec des faits ;
- gérer refus, budgets et frontières ;
- éviter les consultations redondantes ;
- conserver la séparation entre observations et interprétations.

Ne pas ajouter un second modèle de raisonnement obligatoire.

### PR D — Tests de bout en bout et mesures

Objectif : vérifier le comportement réel de l'ensemble (reprend la PR C de TAXO-MIP-SOURCE-01).

Travaux :

- rejouer les 18 questions du banc ;
- trois essais par question ;
- même dépôt, même instantané, même modèle ;
- mesurer les résultats et leur stabilité ;
- mesurer le nombre d'appels ;
- mesurer le volume transmis ;
- mesurer les temps et les coûts disponibles ;
- exécuter les tests de confidentialité ;
- vérifier les non-régressions ;
- produire un rapport avant/après.

Cette PR ne sert pas de prétexte à un élargissement fonctionnel.

La PR A peut être préparée pendant que le récit de confidentialité est finalisé, mais aucune capacité nouvelle de
transmission de code à un LLM n'est activée avant validation des protections.

## 24. Tests d'acceptation obligatoires

### A — Structure et déterminisme

- **A1.** Une Tuile issue d'un profil restitue les mêmes faits et le même ordre pour une même analyse, une même ancre
  et un même budget.
- **A2.** Les relations entrantes et sortantes ne sont jamais inversées dans la représentation.
- **A3.** Chaque élément possède une provenance ou une référence de preuve conforme au contrat.
- **A4.** Une frontière ne devient jamais une affirmation d'absence.
- **A5.** Un profil dont les relations ne sont pas disponibles indique son incomplétude.
- **A6.** Les catégories de contenu annoncées par la classification sont exactement celles du contenu transmis, y
  compris après troncature, pour une ancre inconnue et en cas de refus (§ 21 bis).

### B — Sources Java

- **B1.** La lecture de `StudentService.get(Long)` retourne cette méthode, et non une surcharge différente.
- **B2.** La déclaration de classe associée restitue `@Component` même si le LLM avait demandé à confirmer
  `@Service`.
- **B3.** Une annotation fictive `@Toto` est extraite sans interprétation de son rôle.
- **B4.** Le code retourné correspond au commit de l'analyse.
- **B5.** Une source non autorisée est refusée sans transmission.
- **B6.** Une demande de lecture de fichier entier est refusée par le contrat ciblé.

### C — Confidentialité

- **C1.** Aucun auteur Git ni courriel interdit dans le payload fournisseur.
- **C2.** Aucun secret original dans les Tuiles transmises.
- **C3.** Le consentement au diff ne permet pas de lire une méthode.
- **C4.** Le consentement au source ne permet pas de contourner les exclusions.
- **C5.** Les journaux n'exposent pas les contenus masqués.

### D — Exploration intelligente

- **D1.** Le LLM retrouve une route puis son contrôleur sans sélection manuelle des références par le testeur.
- **D2.** Il demande les méthodes pertinentes à partir des références déjà reçues.
- **D3.** Une méthode comportant plusieurs appels ne provoque pas la transmission automatique de tous leurs corps.
- **D4.** Le LLM peut demander une nouvelle Tuile à partir d'un nœud précédent.
- **D5.** Les budgets et les refus arrêtent correctement l'exploration.
- **D6.** Une erreur d'annotation du LLM peut être corrigée en consultant les observations Taxo.

### E — Banc de référence

Rejouer les 18 tests du rapport du 10 octobre 2026, avec trois essais par question. Surveiller particulièrement :

- test 9 : rôle STUDENT et protection de GET `/api/students` ;
- test 11 : annotations et configuration de sécurité ;
- test 12 : règles d'URL et annotations de méthode ;
- test 17 : vérification d'âge ;
- test 18 : présence de `@PreAuthorize` et `@EnableMethodSecurity` ;
- tests 1 et 3 : fausse ignorance ;
- tests 5 et 6 : chaînes d'appels et conclusions excessives.

Comparer les performances avant/après, sans compter automatiquement une réponse prudente comme une réussite
fonctionnelle.

Le rapport du banc et ses 18 questions ne sont pas encore dans le dépôt (voir TAXO-MINIA-SEC-01) : ils y entrent,
sans donnée personnelle, avant la PR D.

## 25. Mesures attendues

Le rapport final indique, pour chaque scénario :

| Mesure | Attendu |
|---|---|
| Résultat fonctionnel | correct, partiel, sans réponse ou faux |
| Répétabilité | résultat des trois essais |
| Opérations Taxo | nombre réel |
| Appels LLM | nombre réel |
| Octets transmis | volume réel |
| Tokens | mesure fournisseur si disponible |
| Latence | durée totale et postes mesurables |
| Code transmis | méthodes et volume |
| Confidentialité | fuites détectées |
| Sources | références et limites disponibles |

Un critère essentiel est l'absence de nouvelles affirmations fausses portant le verdict `CONFIRMED`. Une conclusion
de sécurité erronée ne doit pas pouvoir paraître certifiée par un fait voisin. L'échec de cette exigence bloque la
validation du récit, même si le nombre de réponses correctes augmente.

## 26. Critères de réussite du récit

Le récit est considéré comme techniquement réussi lorsque :

1. la composition adaptative fonctionne sans moteur parallèle ;
2. les profils sont déterministes, explicites et versionnés ;
3. la lecture ciblée restitue des sources cohérentes avec l'instantané ;
4. les protections et consentements sont testés ;
5. Minia permet au LLM de découvrir lui-même les éléments nécessaires ;
6. les Tuiles conservent leurs preuves, limites et frontières ;
7. aucune interprétation du LLM ne devient automatiquement une observation Taxo ;
8. les tests de non-régression existants passent ;
9. le banc de référence montre des résultats mesurés et documentés ;
10. les limites et échecs résiduels sont présentés sans embellissement.

Les objectifs de réduction de coût et d'amélioration des réponses sont mesurés, non présumés.

## 27. Hors périmètre

Ne pas ajouter dans ce récit :

- un catalogue de significations des annotations Spring ;
- un analyseur probabiliste dans Taxo ;
- un nouveau moteur de graphe ;
- une seconde base de faits ;
- un nouveau protocole concurrent du MIP ;
- une refonte générale des analyseurs de sécurité ;
- un agent autonome modifiant du code ;
- des modifications automatiques des dépôts analysés ;
- de nouveaux diagrammes UML ;
- une refonte de l'interface Explorer ;
- une exploration illimitée de la Chaîne ;
- un système d'entraînement ou de fine-tuning ;
- une refonte générale du système multi-LLM ;
- une généralisation immédiate de `get_source` à tous les langages.

Ces évolutions éventuelles relèvent du backlog futur.

## 28. Gouvernance et discipline de développement

L'équipe de développement dispose d'une autonomie technique dans le périmètre validé. Elle doit :

- travailler sur des branches dédiées ;
- préparer un plan de travail interne ;
- réutiliser les composants existants ;
- appliquer KISS, YAGNI et SOLID avec discernement ;
- ajouter les tests pertinents ;
- exécuter les vérifications backend et frontend concernées ;
- vérifier la CI ;
- documenter les écarts et décisions ;
- produire un compte rendu professionnel par PR.

Tout changement de contrat non compatible, élargissement de périmètre ou décision architecturale lourde est présenté
au responsable du produit avant réalisation.

**Aucune fusion sans son accord explicite.** Les PR peuvent être préparées et soumises à revue sans être fusionnées.

## 29. Livrables attendus

À l'issue du travail :

- Adaptive Tile utilisable avec des profils déclarés ;
- lecture ciblée de code Java autorisée et traçable ;
- intégration de la navigation Minia–LLM ;
- tests unitaires, contractuels et de bout en bout ;
- tests de non-divulgation ;
- rapport avant/après des 18 questions ;
- documentation technique actualisée ;
- démonstration complète sur `student-course-demo` ;
- PR séparées, vérifiées et non fusionnées avant décision.

La documentation indique explicitement ce qui est opérationnel, ce qui reste réservé et ce qui n'est pas pris en
charge.

---

## 30. Démonstration finale exigée

L'équipe de développement présente un dialogue complet dans Ask Taxo.

- **Utilisateur :** « GET /api/students est-elle vulnérable aux injections ? »
- **LLM :** « Je veux voir le contrôleur. »
- **Minia :** demande une Tuile via MIP.
- **Taxo :** rend la Tuile du contrôleur.
- **LLM :** « Je veux lire cette méthode et ses annotations. »
- **Minia :** demande la pièce source autorisée.
- **Taxo :** rend le contenu exact du symbole.
- **LLM :** « Je veux explorer les appels vers les services. »
- **Minia :** demande les expansions correspondantes.
- **Taxo :** rend les Tuiles suivantes.
- **LLM :** « La classe StudentService porte `@Service`. Confirme. »
- **Taxo :** rend les annotations observées sur la déclaration de classe : `@Component`.
- **LLM :** « Je corrige. Je poursuis mon analyse. »
- **Minia :** présente la réponse finale, avec observations, sources consultées, interprétations et limites
  clairement séparées.

La démonstration se déroule avec de vrais résultats Taxo et de vrais extraits du dépôt, sans préparation manuelle
des Tuiles par le testeur. Elle montre que le LLM peut demander plusieurs Tuiles successives, que les budgets sont
respectés et que le système protège les informations sensibles.

## 31. Vision finale

Taxo n'a pas vocation à concurrencer directement l'intelligence des LLM actuels ou futurs. Il fournit aux
consommateurs une représentation déterministe du logiciel, consultable progressivement.

Plus les capacités de raisonnement des modèles progressent, plus ceux-ci peuvent exploiter cette représentation sans
qu'il soit nécessaire de transférer leurs responsabilités à Taxo.

La Maille demeure stable dans son rôle. Le MIP demeure neutre. L'Adaptive Tile fournit exactement la portion de
Maille demandée dans les limites autorisées. Minia organise les consultations. Le LLM interprète. L'humain décide.

**Formule directrice :** TAXO OBSERVE. LA MAILLE CONSERVE. LE MIP TRANSPORTE. L'ADAPTIVE TILE SÉLECTIONNE. MINIA
ORCHESTRE. LE LLM RAISONNE. L'HUMAIN DÉCIDE.

### Décision finale du récit

Nous ne cherchons pas à rendre Taxo intelligent. Nous cherchons à rendre son contenu suffisamment accessible, fiable,
structuré et traçable pour que les intelligences artificielles puissent l'exploiter correctement.

**La force de Taxo est sa fidélité aux sources, non sa capacité à interpréter ce qu'elles signifient.**
