# TAXO-01 — Fondation de la mémoire logicielle vérifiable

Statut : À FAIRE  
Nature : épique, découpé en récits TAXO-01A à TAXO-01I (voir `docs/backlog/PLAN.md`)  
Références : ADR 0001, ADR 0002, `docs/backlog/PLAN.md`  
Remplace : T03, T05, T06 et T08 de l'ancien récit TAXO-EVAL-01

## Récit

En tant que Taxo,  
je veux transformer les observations produites par mes évaluateurs en une mémoire logicielle
versionnée, prouvable et interrogeable,  
afin que les évaluateurs suivants et les futures projections — notamment les diagrammes,
l'analyse d'impact, le bot de PR, MCP et Ask Taxo — puissent réutiliser les mêmes faits sans
relire ni réinterpréter directement le dépôt.

## Intention

Ce récit ne construit pas encore Ask Taxo.

Il construit ce qui rendra Ask Taxo fiable.

À la fin du récit, une future projection doit pouvoir demander à Taxo :

```text
Que sait-on de cet endpoint ?
Quelles relations lui sont associées ?
Quelles preuves soutiennent ces faits ?
Quelle partie n'a pas été interprétée ?
À quel commit ces connaissances appartiennent-elles ?
Par quel producteur, et dans quelle version, ont-elles été établies ?
```

sans devoir reparcourir le code source.

## Lois du récit

```text
Aucun fait sans statut, sans instantané et sans producteur.

La preuve dépend de la nature du fait :
  ASSERTION OBSERVED → au moins une preuve
  ABSENCE            → motif + périmètre + méthode, aucune preuve
  COVERAGE           → sujet + type + périmètre, preuve facultative

Une projection ou une personne n'est jamais enregistrée comme évaluateur.

Toute exécution d'évaluateur déclare sa couverture.

Une projection ne doit jamais avoir besoin de réinterpréter le dépôt
pour connaître la provenance d'un fait.

Une connaissance devenue invalide ou incertaine doit être marquée,
jamais silencieusement conservée comme vraie.
```

## Hors périmètre

- l'analyse Java ;
- Spring MVC ;
- Spring Security ;
- l'analyse des endpoints ;
- l'analyse métier de TAKIBO ;
- les diagrammes eux-mêmes ;
- Ask Taxo et son interface conversationnelle ;
- MCP ;
- le bot de PR ;
- tout moteur de graphe imposé ;
- toute recherche vectorielle ;
- tout appel à un LLM.

Ce récit prépare ces capacités, il ne les implémente pas.

---

# T1 — Schéma machine du fait Taxo

Dériver de l'ADR 0002 un contrat machine versionné représentant au minimum :

- nature du fait ;
- sujet ;
- relation ;
- objet ;
- qualificatifs ;
- statut ;
- validité ;
- instantané ;
- preuves ;
- producteur : type (`EVALUATOR`, `PROJECTION`, `HUMAN`), identifiant, version, exécution ;
- catalogue de détection, pour un évaluateur ;
- périmètre structuré (`include`, `exclude`) ;
- dérivation ;
- validation humaine.

L'horodatage d'analyse appartient à l'exécution référencée, pas au fait.

Le contrat doit être validable automatiquement.

Exemples de règles obligatoires (détail complet : ADR 0002 et TAXO-01A) :

```text
ASSERTION OBSERVED
→ au moins une preuve du même instantané

ABSENCE
→ motif + périmètre + méthode, aucune preuve

COVERAGE
→ sujet + type de couverture + périmètre, preuve facultative

INFERRED
→ au moins une prémisse et une règle

HUMAN_VALIDATED
→ producteur HUMAN, validation et ancrage

Statut
→ compatible avec la nature et le type de producteur

Toute relation
→ appartient au vocabulaire versionné

Aucun champ
→ n'est destiné à conserver un extrait brut de code source
```

Les producteurs restent responsables de ne jamais émettre de secret ou de valeur sensible.

## Résultat attendu

Un producteur ne peut pas enregistrer un résultat ambigu ou incomplet en contournant le contrat
Taxo.

---

# T2 — Références stables des entités

Introduire la notion d'entité Taxo adressable indépendamment des numéros de ligne.

Exemples :

```text
repository:takibo-iam
module:takibo-management-service
directory:takibo-security-management/src/main/java
file:.../OAuthClientController.java
symbol:java:...OAuthClientController#register
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
technology:Spring Boot
route-pattern:/api/v1/**
```

Les références doivent être stables entre deux commits tant que l'entité logique n'a pas changé.

## Pourquoi maintenant

Ask Taxo, les diagrammes et l'analyse d'impact devront pouvoir partir d'une entité et demander :

```text
donne-moi les faits dont elle est sujet
donne-moi les faits qui pointent vers elle
donne-moi les relations autour d'elle
```

sans connaître le stockage interne.

## Résultat attendu

Taxo possède un langage commun pour relier les faits produits par plusieurs producteurs.

---

# T3 — Instantané versionné

L'analyse de référence cible un commit précis.

Un instantané contient au minimum :

```text
repository
commit
mode
dirty
content_fingerprint   (obligatoire en WORKING_TREE)
```

L'horodatage d'analyse appartient à l'exécution, pas à l'instantané : un même commit peut être
analysé plusieurs fois, par des versions de producteur différentes (voir T8).

Modes :

```text
COMMIT
WORKING_TREE
```

Le mode `COMMIT` est la référence.

Le mode `WORKING_TREE` reste disponible mais doit signaler explicitement que les fichiers analysés
peuvent différer du commit HEAD.

## Conséquence voulue

Une réponse future de Taxo pourra dire :

```text
Cette connaissance correspond au commit abc123.
Le HEAD actuel est def456.
```

et ne présentera jamais silencieusement une ancienne analyse comme l'état courant.

---

# T4 — Exécution d'évaluateur et couverture déclarée

Chaque exécution d'évaluateur porte au minimum :

```text
producer_id
producer_version
catalog_id
catalog_version
snapshot
started_at
finished_at
status
scope          (structure de l'ADR 0002 : include, exclude)
```

États :

```text
RUNNING
SUCCESS
PARTIAL
FAILED
UNSUPPORTED
```

Chaque exécution produit au moins un fait `COVERAGE`.

La couverture distingue notamment :

```text
analysé
reconnu
non interprété
hors périmètre
erreur de lecture
```

Exemple futur :

```text
Spring Security Evaluator 1.2

Reconnu :
- SecurityFilterChain
- hasAuthority

Non interprété :
- PolicyEvaluator custom

Status:
SUCCESS
```

Le statut décrit l'**exécution technique** : `PARTIAL` signifie que des fichiers n'ont pas pu être
lus, `FAILED` que l'exécution n'a pas abouti. Les limites de **compréhension** relèvent de la
couverture. Une exécution complète avec des éléments non interprétés reste `SUCCESS` ; sinon,
l'évaluateur Security serait `PARTIAL` pour toujours sur TAKIBO.

## Résultat attendu

Taxo peut expliquer non seulement ce qu'il sait, mais également jusqu'où l'analyse est allée.

---

# T5 — Persistance de la mémoire vérifiable

Remplacer le JSON libre de `scans.result` comme source de vérité par des structures persistantes
permettant d'interroger séparément :

- instantanés ;
- exécutions ;
- faits ;
- occurrences ;
- preuves ;
- couvertures ;
- dérivations ;
- validations humaines.

L'identité stable d'un fait est calculée et indexée.

Le choix physique du stockage reste une décision d'implémentation.

Aucun moteur de graphe n'est requis par ce récit.

## Résultat attendu

Les faits sont conservés indépendamment de la projection qui les utilisera.

---

# T6 — Relations et voisinage d'une entité

Permettre d'interroger les faits dans les deux directions.

Exemple futur :

```text
endpoint:X
    HANDLED_BY
    symbol:Y
```

Taxo doit pouvoir répondre :

```text
faits dont endpoint:X est sujet
```

mais également :

```text
faits dont symbol:Y est objet
```

et fournir le voisinage immédiat d'une entité.

Ce mécanisme ne constitue pas encore un Knowledge Graph dédié.

Il fournit simplement les primitives nécessaires pour que les relations entre faits soient
navigables.

## Résultat attendu

Une future projection de diagramme peut parcourir des relations sans relire le repository.

---

# T7 — Validité, dérivation et invalidation

Implémenter les règles de validité prévues par l'ADR 0002.

### Fait ASSERTION OBSERVED

Ses preuves appartiennent à son instantané.

### Faits ABSENCE et COVERAGE

Leur périmètre et leur méthode ou type de couverture sont enregistrés. Une absence n'a pas de
preuve ; une couverture peut en avoir.

### Fait INFERRED

Ses prémisses sont explicitement enregistrées.

Si une prémisse n'est plus valable dans l'instantané utilisé :

```text
INFERRED
→ STALE
```

### Fait HUMAN_VALIDATED

Ses ancrages sont enregistrés.

Si un ancrage change :

```text
HUMAN_VALIDATED
→ REVALIDATION_REQUIRED
```

## Exemple

```text
F1 OBSERVED
endpoint X HANDLED_BY symbol Y

F2 OBSERVED
route-pattern Z AUTHORIZED_BY symbol M

F3 INFERRED
endpoint X MATCHED_BY route-pattern Z
premises: F1 + F2

F4 INFERRED
endpoint X PROTECTED_BY symbol M
premises: F2 + F3
```

Si F2 ou F3 disparaît ou change, F4 ne doit pas rester silencieusement `VALID`.

## Résultat attendu

La mémoire Taxo sait reconnaître qu'une conclusion doit être recalculée ou revue.

---

# T8 — Comparaison de deux instantanés

Comparer les occurrences sur la base de l'identité stable des faits.

Produire au minimum :

```text
INTRODUCED
REMOVED
MODIFIED
UNCHANGED
```

La comparaison distingue :

```text
évolution du logiciel
```

de :

```text
cause possible : évolution du producteur
```

lorsque les versions d'un producteur (évaluateur ou projection) ou de son catalogue diffèrent.

## Exemple

```text
Commit A + Security Evaluator 1.0
→ mécanisme non interprété

Commit A + Security Evaluator 1.1
→ mécanisme interprété
```

Taxo ne doit pas présenter cela comme une modification du logiciel.

## Résultat attendu

Les futures projections de dérive et de PR peuvent s'appuyer sur une comparaison honnête.

---

# T9 — API de lecture orientée projections

Exposer une API minimale permettant aux futures projections d'interroger la mémoire.

Capacités attendues :

```text
faits d'un instantané
fait par identité
faits par sujet
faits par objet
faits par relation
voisinage d'une entité
preuves d'un fait
couverture d'une exécution
évaluateurs exécutés pour un instantané
faits non interprétés
faits STALE
faits REVALIDATION_REQUIRED
comparaison de deux instantanés
```

Cette API n'est pas Ask Taxo.

Elle est le contrat de lecture que pourront utiliser :

- Ask Taxo ;
- les diagrammes ;
- MCP ;
- l'analyse d'impact ;
- la documentation ;
- le bot de PR.

## Résultat attendu

Aucune projection future n'a besoin d'accéder directement aux tables internes ou au scanner.

---

# T10 — Vue minimale de vérification

Le portail affiche suffisamment d'informations pour contrôler visuellement la mémoire :

```text
Fact ID
Kind
Status
Validity
Subject
Relation
Object
Scope
Snapshot
Producer type
Producer
Producer version
Evidence
Coverage / gaps
```

Aucun chatbot et aucun diagramme dans ce récit.

L'objectif est de permettre à l'équipe de vérifier les faits produits par Taxo avant de construire
des projections plus riches.

---

# T11 — Banc de test Git contrôlé

Créer dans les tests un petit repository Git avec plusieurs commits scénarisés.

Scénarios minimum :

```text
commit A
- fichier Java

commit B
- ajout d'un fichier
- ajout d'un manifeste

commit C
- suppression d'un fichier
- modification d'un manifeste
```

Tester :

- instantanés au commit ;
- faits introduits ;
- faits retirés ;
- faits modifiés ;
- preuves ;
- couverture ;
- changement de version d'évaluateur.

## Résultat attendu

La chronologie reconstruite par Taxo correspond exactement aux changements scénarisés.

---

# T12 — Test de préparation à Ask Taxo

Ajouter un test fonctionnel qui ne fait intervenir aucun LLM.

À partir de faits de test représentant par exemple :

```text
endpoint:X
    HANDLED_BY
    symbol:Y            (le contrôleur)                          OBSERVED

route-pattern:Z
    AUTHORIZED_BY
    symbol:M            (le gestionnaire d'autorisation)         OBSERVED

endpoint:X
    MATCHED_BY
    route-pattern:Z                                              INFERRED

symbol:M
    CALLS
    symbol:N            (la classe de politique du projet)       OBSERVED

COVERAGE
    symbol:N
    coverage_type: NOT_INTERPRETED
```

Les références suivent la syntaxe de TAXO-01A (`symbol:java:…`). On évite `evaluator:N` : dans
Taxo, le mot « évaluateur » désigne les évaluateurs de Taxo, pas une classe du projet analysé.

l'API de lecture doit permettre de reconstruire :

```text
endpoint:X
      ↓ HANDLED_BY
symbol:Y

sécurité connue :
endpoint X → MATCHED_BY route Z → AUTHORIZED_BY symbol M → CALLS symbol N

limite :
symbol N non interprété
```

avec :

- les statuts ;
- les preuves et les prémisses ;
- le commit ;
- les producteurs et leurs versions ;
- les zones non interprétées.

## Pourquoi ce test est important

Il démontre que la mémoire construite par TAXO-01 contient déjà tout ce dont une future projection
« Donne-moi le diagramme de cette API » aura besoin pour travailler sans relire le code.

Il ne teste pas le rendu du diagramme.

Il teste la **projectabilité de la connaissance**.

---

# Critères de terminé

1. Le schéma machine du fait existe, est versionné et applique les règles de cohérence de l'ADR 0002.
2. Les entités disposent de références stables utilisables par plusieurs producteurs.
3. Une analyse peut cibler un commit précis sans dépendre du dossier de travail.
4. Le mode `WORKING_TREE` est explicitement identifiable.
5. Chaque exécution d'évaluateur possède son identité, sa version, son état et sa couverture déclarée.
6. Les faits, occurrences, preuves, couvertures et dérivations sont persistés et interrogeables.
7. `scans.result` n'est plus la source de vérité.
8. Une entité peut être interrogée dans les deux directions de ses relations.
9. Les faits `INFERRED` deviennent `STALE` lorsque leurs prémisses ne sont plus valides.
10. Les faits `HUMAN_VALIDATED` deviennent `REVALIDATION_REQUIRED` lorsque leurs ancrages changent.
11. Deux instantanés du banc de test se comparent exactement.
12. Un changement de version d'un producteur ou de son catalogue est distingué d'un changement du logiciel.
13. Les preuves et les limites de couverture restent consultables.
14. L'API de lecture fournit les primitives nécessaires aux projections futures.
15. Le test de préparation à Ask Taxo démontre qu'un flux relationnel peut être reconstruit uniquement depuis les faits persistés.
16. Une projection ou une personne n'est jamais enregistrée comme évaluateur.
17. Les garde-fous actuels sont conservés sans assouplissement : lecture seule, aucune exécution du dépôt, `.env` jamais lu, liens symboliques ignorés (`scanner.py` les ignore tous), limite de volume. Tout assouplissement futur passe par un ADR.
18. Tests verts.

---

# Ce que TAXO-01 rend possible ensuite

```text
TAXO-01
Mémoire vérifiable
       ↓
TAXO-02
Inventory Evaluator
       ↓
TAXO-03
Java Analyzer (primitives Java)
       ↓
TAXO-04
Spring API Evaluator (endpoints)
       ↓
TAXO-05
Spring Security Evaluator
       ↓
TAXO-PROJ-PR-01
Projection PR                     démo technique
       ↓
TAXO-PROJ-API-01
Projection Diagramme API
       ↓
TAXO-ASK-01
Ask Taxo minimal                  démo produit
```

Deux démonstrations, deux objectifs.

**Démo technique : PR et comparaison de commits.**

```text
Taxo :
- compare deux commits ;
- montre les endpoints et les autorisations qui ont changé, avec preuves ;
- reproduit exactement le même résultat à chaque exécution ;
- distingue un changement du logiciel d'un changement de producteur.
```

**Démo produit : Ask Taxo.**

```text
Dev :
« Taxo, explique-moi cette API
et donne-moi son diagramme. »

Taxo :
- répond depuis les faits persistés ;
- montre les relations observées ;
- distingue les inférences ;
- affiche les preuves ;
- signale les zones non interprétées ;
- précise le commit analysé ;
- ne relit pas le dépôt pour inventer une réponse.
```
