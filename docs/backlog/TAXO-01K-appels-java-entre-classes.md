# TAXO-01K — Appels Java entre classes : du contrôleur au service et au repository

Statut : **proposition à valider avant implémentation**.  
Date : 2026-10-03.  
Source de vérité : `ARCHITECTURE.md` § 2, § 5.6, § 7.3, § 8, § 12.3 et surtout § 14.  
Dépend de : lecteur Java syntaxique existant, contrat des faits, couverture bornée, voisinage multiniveau / Explorer.  
Ne dépend pas de Minia.

## Constat

L'essai sur le petit projet `student-course-demo` montre une limite nette de la Maille actuelle :

```text
GET /api/courses
  → CourseController#getCourses()
  → fin
```

Taxo établit `HANDLED_BY` entre la route et la méthode du contrôleur, mais aucun producteur ne crée aujourd'hui les relations `CALLS`, `IMPLEMENTS` ou `DISPATCHES_TO`.

La Tuile ne coupe rien : elle restitue fidèlement la connaissance existante. Le manque est donc en amont, dans la production de faits Java.

Le contrat connaît déjà :

- `CALLS` : `symbol → symbol` ;
- `IMPLEMENTS` : `symbol → symbol` ;
- `DISPATCHES_TO` : `symbol → symbol`.

Aucun analyseur livré ne les produit. `ARCHITECTURE § 14` propose déjà une sémantique de `CALLS`, mais son premier fragment est limité à un appel local `f()` vers une méthode privée sans paramètre de la même classe. Ce fragment ne couvre pas le cas utile observé :

```java
courseService.getCourses()
```

où le receveur est un champ typé par une autre classe ou interface.

## Intention

En tant que personne qui explore une route, je veux suivre les appels Java établis statiquement au-delà du contrôleur, sans que Taxo invente un flux d'exécution.

Exemple attendu lorsque les déclarations sont résolues :

```text
GET /api/courses
  → HANDLED_BY CourseController#getCourses()
  → CALLS CourseService#getCourses()
  → CALLS ...
```

Quand la cible n'est pas établie, la chaîne doit s'arrêter avec une raison localisée et explicite.

Cette capacité reste générique Java. Elle ne connaît ni `Controller`, ni `Service`, ni `Repository`, ni Spring Data par leur rôle métier.

## Décision d'architecture proposée

### 1. `CALLS` désigne une déclaration, pas le corps réellement exécuté

`CALLS(A, B)` signifie :

> Le corps de `A` contient au moins un site d'appel pour lequel une règle de résolution nommée établit la déclaration `B`.

Statut : **`INFERRED`**, conformément à la proposition de `ARCHITECTURE § 14`.

La preuve directe est le site d'appel. La dérivation nomme la règle de résolution et les prémisses utilisées.

`CALLS` ne signifie jamais :

- que `B` est le corps réellement exécuté ;
- que l'appel a lieu à l'exécution ;
- qu'une branche est atteignable ;
- qu'une transaction, une autorisation ou un effet métier se produit.

### 2. Ne pas mélanger résolution d'appel et injection de dépendances

Pour résoudre :

```java
private final CourseService courseService;

public List<Course> getCourses() {
    return courseService.getCourses();
}
```

Taxo n'a pas besoin de prouver comment `courseService` a été injecté.

Le **type déclaré du receveur** suffit pour résoudre la déclaration visée par l'appel. Que le champ soit rempli par un constructeur explicite, `@Autowired`, Lombok ou un autre mécanisme concerne la construction de l'objet, pas la résolution syntaxique de `courseService.getCourses()`.

Le premier fragment ne doit donc pas dépendre de Spring DI ni de Lombok.

### 3. `IMPLEMENTS` reste distinct

Quand une classe des sources implémente explicitement une interface des sources, Taxo peut produire un fait `IMPLEMENTS` seulement si les deux déclarations sont établies sans ambiguïté.

Deux niveaux, deux statuts (décision proposée, à valider dans PR A) :

- **type → type** : `symbol:java:<Impl>` `IMPLEMENTS` `symbol:java:<Interface>`, `OBSERVED`, car la clause `implements` est écrite ; preuve à la ligne de la clause ;
- **méthode → méthode** : `symbol:java:<Impl>#m(…)` `IMPLEMENTS` `symbol:java:<Interface>#m(…)`, `INFERRED`, car aucune ligne ne l'écrit : c'est une déduction (même signature syntaxique normalisée, prémisse : l'`IMPLEMENTS` type → type). Règle `java.implements.same-signature/1`. Signature ambiguë ou supertype hors sources entre les deux : rien n'est produit.

Le niveau méthode est celui qui sert l'Explorer : il relie la déclaration appelée à son implémentation connue. Il demande d'ouvrir `INFERRED` à `IMPLEMENTS` dans le validateur (`backend/app/facts/domain/fact.py`, aujourd'hui `OBSERVED` seul) et dans `ARCHITECTURE § 5.6`.

Cette relation ne doit pas être utilisée pour prétendre que l'implémentation est le corps exécuté lors d'un appel sur l'interface.

### 4. `DISPATCHES_TO` reste suspendu

Aucun `DISPATCHES_TO` dans ce récit.

Un appel :

```java
courseService.getCourses()
```

où `courseService` est déclaré comme interface peut établir `CALLS` vers la déclaration de l'interface. Il ne doit pas devenir automatiquement un appel vers `CourseServiceImpl#getCourses()`.

Le dispatch dynamique sera un récit séparé lorsqu'un site d'appel sera une référence adressable et que son contrat aura été décidé.

## Premier fragment livré

Le premier fragment utile couvre les appels de méthode écrits directement dans le corps d'une méthode ou d'un constructeur (hors lambda, classe anonyme ou locale), dont le receveur est :

1. `this` ;
2. un champ du type courant, écrit `champ` ou `this.champ` ;
3. un paramètre de méthode ;
4. une variable locale ;

à condition que le lecteur Java connaisse le **type déclaré** du receveur et que ce type soit résolu vers **une déclaration unique présente dans l'instantané**.

Le type déclaré est le type **écrit** : `var`, paramètre de type générique (`T`) ou paramètre de lambda donnent `RECEIVER_TYPE_UNKNOWN`. Les arguments génériques sont ignorés (`List<Course>` vise `List`).

Les appels sans receveur (`f()`) du type courant restent couverts selon les mêmes règles de résolution et remplacent le fragment trop étroit proposé actuellement au § 14, avec deux conditions qu'il gardait : aucun type englobant ne déclare `f` de même arité, et aucun import statique ne peut fournir `f`. Sinon : `OVERLOAD_AMBIGUOUS`.

Hors fragment, avec `UNSUPPORTED_CALL_FORM` : `super.f()`, appel statique `Type.f()`, appel sur le résultat d'un autre appel (`a.b().c()` : seul le premier appel est candidat), `new T(...)` et `this(...)` / `super(...)`.

### Ce que le lecteur Java doit fournir (PR B)

Le lecteur actuel (`backend/app/evaluators/java/syntax.py`) ne suffit pas tel quel :

- `JavaType.methods` ne garde que les méthodes **annotées** ; `signatures` les garde toutes mais sans lignes ni modificateurs. L'évaluateur a besoin de toutes les déclarations ;
- `JavaFile.chains(names)` filtre par nom et ignore les appels imbriqués dans un argument (`a(b.c())`) ; l'évaluateur doit voir **tous** les sites ;
- `Chain.declared` n'existe que si le receveur est un identifiant : `this.champ` doit être ajouté ;
- un site doit porter ses colonnes (preuve `call-site`, § 14).

Ces primitives restent génériques : le lecteur ne connaît toujours aucun framework.

### Cible admissible

Pour un site :

```java
receiver.method(arg1, ..., argN)
```

Taxo cherche dans le type déclaré résolu du receveur une déclaration dont :

- le nom est `method` ;
- le nombre de paramètres est `N` ;
- la déclaration appartient aux sources lues ;
- la sélection est unique selon les règles du fragment.

Si une seule déclaration est ainsi établie, `CALLS` est produit.

Si plusieurs déclarations restent candidates, aucun `CALLS` n'est produit.

### Surcharges

Le nom + arité n'est pas une résolution Java complète.

Donc :

- une méthode unique par nom et arité peut être résolue dans ce fragment ;
- plusieurs surcharges de même nom et même arité donnent `NOT_INTERPRETED` ;
- une méthode varargs (`f(String...)`) n'a pas d'arité fixe : tout site de même nom est `OVERLOAD_AMBIGUOUS` ;
- deux déclarations de même signature dans un type (`JavaType.ambiguous`) donnent `OVERLOAD_AMBIGUOUS` ;
- un nom et une arité qui coïncident avec une méthode publique d'`Object` (`equals/1`, `hashCode/0`, `toString/0`…) ne sont résolus que si le type des sources la redéclare avec exactement la même signature ; sinon `OVERLOAD_AMBIGUOUS` ;
- Taxo n'essaie pas encore d'inférer les types d'expressions pour départager les surcharges ;
- une candidate unique après filtrage reste une cible seulement si la règle du fragment garantit son unicité.

Aucune préférence par proximité, ordre du fichier ou nom de classe.

### Héritage dans les sources

Le premier fragment peut suivre une super-classe ou une interface **présente dans les sources** si la chaîne de types est résolue sans ambiguïté.

Java choisit une surcharge parmi **toutes** les méthodes du type, héritées comprises. Taxo réunit donc les déclarations de même nom et même arité dans toute la hiérarchie du type déclaré :

- si elles ont toutes la même signature, ce sont des redéfinitions : la cible est la déclaration du type le plus proche du receveur ; si deux types au même niveau (deux interfaces) la déclarent, `OVERLOAD_AMBIGUOUS` ;
- si leurs signatures diffèrent, `OVERLOAD_AMBIGUOUS` ;
- si un supertype de la hiérarchie est externe ou non résolu (autre qu'`Object`, traité plus haut) :
  - et qu'une déclaration est trouvée dans les sources, le supertype pourrait déclarer une surcharge de même arité : `SUPER_TYPE_UNRESOLVED`. Taxo ne suppose pas qu'une bibliothèque ne déclare rien ;
  - et qu'aucune déclaration n'est trouvée dans les sources : `TARGET_DECLARATION_OUTSIDE_SNAPSHOT` (voir « Repositories ») ;
- si toute la hiérarchie est dans les sources et qu'aucune déclaration ne correspond : `NO_MATCHING_DECLARATION`.

Conséquence assumée : dans `CourseRepository extends JpaRepository<…>`, un appel à une méthode déclarée dans `CourseRepository` est `SUPER_TYPE_UNRESOLVED`, et un appel à `findAll()` est `TARGET_DECLARATION_OUTSIDE_SNAPSHOT`. PR D mesure ce que coûte cette prudence.

## Interfaces

Exemple :

```java
interface CourseService {
    List<Course> getCourses();
}

class CourseServiceImpl implements CourseService {
    public List<Course> getCourses() { ... }
}

class CourseController {
    private final CourseService courseService;

    List<Course> getCourses() {
        return courseService.getCourses();
    }
}
```

Résultat du récit :

```text
CourseController#getCourses()
  CALLS
CourseService#getCourses()
```

et, séparément, au niveau des méthodes (`INFERRED`, décision 3) :

```text
CourseServiceImpl#getCourses()
  IMPLEMENTS
CourseService#getCourses()
```

Taxo **ne relie pas** le premier appel au corps de `CourseServiceImpl#getCourses()` par `DISPATCHES_TO`.

L'Explorer peut donc montrer honnêtement la déclaration appelée puis l'implémentation connue comme relation distincte, sans prétendre connaître le dispatch.

## Repositories et dépendances externes

Cas typique :

```java
interface CourseRepository extends JpaRepository<Course, Long> {
}

courseRepository.findAll();
```

`findAll()` n'est pas déclaré dans `CourseRepository.java`. Il est hérité d'une dépendance externe.

Taxo n'exécute ni Gradle ni Maven et ne lit actuellement aucun JAR pour résoudre les méthodes externes.

### Décision pour ce récit

**Ne pas inventer de symbole externe `JpaRepository#findAll()`**.

Le site est déclaré `NOT_INTERPRETED`, avec une raison fermée du type :

```text
TARGET_DECLARATION_OUTSIDE_SNAPSHOT
```

et les informations disponibles :

- propriétaire lexical ;
- fichier et lignes du site ;
- receveur écrit ;
- type déclaré du receveur ;
- supertype externe connu par son nom écrit, si disponible.

Un futur lecteur des dépendances/JAR pourra résoudre ces déclarations sans changer la sémantique de `CALLS`.

Cette décision garde Taxo générique et évite toute règle spéciale « Spring Data ».

## Faits et couverture

### `CALLS`

Sujet : symbole de la méthode ou du constructeur contenant le site.  
Objet : symbole de la déclaration appelée.  
Statut : `INFERRED`.  
Producteur : nouvel évaluateur Java d'appels, séparé du lecteur syntaxique.

Une seule arête d'identité peut agréger plusieurs sites d'appel entre les mêmes symboles ; les preuves conservent chaque site.

Règle de dérivation initiale :

```text
java.calls.declared-receiver-unique-target/1
```

Prémisses (texte, comme les autres évaluateurs) : le type déclaré du receveur et la ligne où il est déclaré, la déclaration cible retenue, les types de la hiérarchie parcourus. `counter_examples_checked` : les déclarations de même nom écartées (autre arité).

Preuve : une preuve fichier par site, avec `symbol` = propriétaire lexical, et les champs proposés au § 14 (`column_start`, `column_end`, `role: call-site`). Ces champs n'existent pas encore dans `contract-v1.schema.json` : PR A les ajoute.

### `IMPLEMENTS`

Produit seulement quand le lien entre déclarations est résolu dans les sources : `OBSERVED` type → type, `INFERRED` méthode → méthode (décision 3).

### Couvertures

Chaque site que l'analyseur rencontre mais ne peut pas résoudre est localisé par `NOT_INTERPRETED`.

L'identité d'une couverture est (sujet, type, périmètre, producteur) et son périmètre s'arrête au fichier : deux sites non résolus d'une même méthode donneraient la même identité. Donc :

- une couverture `NOT_INTERPRETED` par **méthode ou constructeur propriétaire** (sujet : son symbole ; périmètre : son fichier) ;
- ses sites dans le champ `diagnostic` proposé au § 14 (ligne, colonnes, receveur écrit, type déclaré, raison fermée, candidats), hors identité. PR A l'ajoute au contrat ;
- `reason` (texte) reste la phrase lisible, comme pour les autres évaluateurs ;
- une couverture `ANALYSED` par fichier Java lu.

Raisons fermées initiales :

```text
RECEIVER_TYPE_UNKNOWN
RECEIVER_TYPE_AMBIGUOUS
TARGET_TYPE_OUTSIDE_SNAPSHOT
TARGET_DECLARATION_OUTSIDE_SNAPSHOT
NO_MATCHING_DECLARATION
OVERLOAD_AMBIGUOUS
SUPER_TYPE_UNRESOLVED
UNSUPPORTED_CALL_FORM
LAMBDA_OR_LOCAL_CONTEXT
PARSE_ERROR
```

Ces raisons sont des diagnostics de résolution, jamais des arêtes « possibles ».

`TARGET_TYPE_OUTSIDE_SNAPSHOT` (receveur `String`, `List`, `Optional`…) sera de loin la plus fréquente. Elle est comptée, mais PR D décide si chaque site doit être listé ou seulement compté par méthode, selon la taille ajoutée à la Maille.

## Lambdas, classes locales et anonymes

Conformément au § 14 :

- créer une lambda n'est pas l'appeler ;
- les appels contenus dans une lambda ne sont pas attribués à la méthode englobante ;
- classes anonymes et locales sont hors du premier fragment ;
- aucun appel n'est déplacé vers un propriétaire lexical approximatif.

Ils sont couverts plus tard par une règle dédiée.

## Explorer et Tuiles

Aucune logique Java n'entre dans le moteur de voisinage.

Dès que les faits existent, l'Explorer les suit comme les autres relations.

Exemple après livraison :

```text
route GET /api/courses
  └─ HANDLED_BY → CourseController#getCourses()
       └─ CALLS → CourseService#getCourses()
```

Si l'appel suivant est externe :

```text
CourseService#getCourses()
  └─ zone non lue :
       TARGET_DECLARATION_OUTSIDE_SNAPSHOT
       receiver: courseRepository
       declared type: CourseRepository
```

Le portail doit traduire la raison en langage humain, par exemple :

> Taxo voit l'appel `courseRepository.findAll()`, mais la déclaration appelée n'est pas présente dans les sources analysées.

Pas de bouton « Développer » vers une cible inventée.

## Validation indépendante

Un petit dépôt scénarisé devient la vérité de référence de ce récit.

### Fixture minimale

```text
java-calls-demo/
  controller/
    CourseController.java
  service/
    CourseService.java
    CourseServiceImpl.java
  repository/
    CourseRepository.java
```

Elle contient explicitement :

- appel vers une classe concrète des sources ;
- appel vers une interface des sources ;
- implémentation d'interface ;
- surcharge ambiguë ;
- type de receveur inconnu ;
- méthode héritée d'une dépendance externe ;
- méthode déclarée dans un type des sources qui étend un type externe (`SUPER_TYPE_UNRESOLVED`) ;
- receveur `var` ou de type générique `T` ;
- appel dans une lambda ;
- deux sites identiques entre les mêmes méthodes.

Les faits attendus sont écrits à la main avant d'exécuter Taxo.

`student-course-demo` sert ensuite d'essai réel de petite taille, mais ne remplace pas l'oracle.

Un essai sur `spring-petclinic` mesure enfin le comportement sur un dépôt réel.

## Critères d'acceptation

1. Une route dont le contrôleur appelle une méthode unique d'un service concret des sources produit la chaîne `HANDLED_BY → CALLS`.
2. Un appel sur un champ dont le type est une interface des sources produit `CALLS` vers la déclaration de l'interface, jamais directement vers une implémentation.
3. Une implémentation explicite et résolue produit `IMPLEMENTS` type → type (`OBSERVED`) et méthode → méthode (`INFERRED`), selon la décision validée en PR A.
4. Aucune relation `DISPATCHES_TO` n'est produite.
5. Deux surcharges de même nom et même arité donnent `NOT_INTERPRETED`, sans choix arbitraire.
6. Un appel vers une méthode héritée uniquement d'une dépendance externe ne fabrique aucun symbole cible ; il produit `TARGET_DECLARATION_OUTSIDE_SNAPSHOT`.
7. Les appels d'une lambda ne sont pas attribués à la méthode englobante.
8. Un appel sur une méthode d'un type des sources qui étend un type externe donne `SUPER_TYPE_UNRESOLVED`, jamais un `CALLS`.
9. Deux sites de `A` vers `B` ne créent pas deux identités `CALLS`, mais leurs deux preuves restent accessibles.
10. Le voisinage montre les nouveaux faits sans modification spécifique au moteur ou à l'Explorer.
11. Même instantané et même version d'évaluateur : mêmes faits, mêmes diagnostics, même ordre.
12. Un dépôt sans Java rend l'évaluateur `UNSUPPORTED` selon TAXO-COV-01.
13. Toute forme hors fragment est explicitement couverte comme non interprétée ; jamais une absence inventée.

## Découpage proposé

### PR A — Contrat et fixture

- décider et mettre à jour `ARCHITECTURE § 14` ;
- passer `CALLS` à `INFERRED` dans le vocabulaire (validateur `fact.py`, § 5.6) ;
- valider la décision 3 sur `IMPLEMENTS` et ouvrir `INFERRED` au niveau méthode ;
- ajouter au schéma les champs de preuve `column_start`, `column_end`, `role` et le `diagnostic` de couverture ;
- compléter validateur et conformité (le cas `t16-02-absence-relation.json` cite déjà `CALLS`) ;
- ajouter la fixture indépendante et ses vérités attendues ;
- aucun producteur `CALLS` encore.

### PR B — Résolution intra-sources

- primitives du lecteur Java nécessaires (voir « Ce que le lecteur Java doit fournir ») ;
- nouvel évaluateur `taxo.java-calls`, catalogue `java-calls` v1, qui lit Java (`UNSUPPORTED` sinon, TAXO-COV-01), ajouté au tableau du § 7 ;
- appels non qualifiés et receveurs typés présents dans les sources ;
- surcharges et héritage source bornés ;
- diagnostics `NOT_INTERPRETED` ;
- tests unitaires et conformance.

### PR C — Interfaces et restitution

- production `IMPLEMENTS` selon la décision de PR A ;
- Explorer / vocabulaire : libellés et explications des arrêts ; la phrase actuelle « La classe B implémente la méthode C.run() » (`frontend/src/sentences.test.ts`) doit distinguer type et méthode ;
- essai sur `student-course-demo`.

### PR D — Mesure réelle

- essai sur `spring-petclinic` ;
- temps d'analyse, nombre de sites vus/résolus/non interprétés ;
- distribution des raisons d'arrêt ;
- mesure du coût supplémentaire dans les Tuiles ;
- décision documentée sur le fragment suivant.

## Hors périmètre

- résolution complète du langage Java ;
- bytecode ;
- lecture des JAR ;
- exécution de Gradle/Maven ;
- DI Spring ;
- dispatch dynamique ;
- réflexion ;
- proxies Spring ;
- AOP ;
- appels via méthode de référence ;
- Kotlin ;
- dataflow ;
- appels inter-processus ;
- vulnérabilités / BOLA / IDOR ;
- inférence par LLM.

## Mesures à publier

Pour la fixture, `student-course-demo` et `spring-petclinic` :

- fichiers Java et méthodes lus ;
- sites d'appel rencontrés ;
- sites résolus ;
- sites non interprétés par raison ;
- `CALLS` distincts ;
- `IMPLEMENTS` distincts ;
- temps de l'évaluateur ;
- taille ajoutée à la Maille ;
- taille et temps d'une Tuile route → contrôleur → appels.

L'objectif n'est pas un pourcentage de couverture arbitraire. Les mesures servent à décider quel fragment de résolution apporte le plus de valeur ensuite.

## Relation avec le défaut Gradle mono-module

Le défaut découvert sur `student-course-demo` — projet Gradle racine non matérialisé comme module — est **séparé** de ce récit.

Il doit être corrigé et couvert par son propre test de régression. `taxo.java-calls` analyse les déclarations Java et ne doit pas dépendre de la reconnaissance Spring Boot du projet pour produire `CALLS`.

Ainsi, une lacune de structure ne masque pas une lacune de graphe d'appels, et inversement.

## Mise à jour du PLAN proposée

Après TAXO-01J :

1. corriger les régressions simples révélées par les petits dépôts (dont Gradle mono-module) ;
2. **TAXO-01K — appels Java entre classes** ;
3. première projection Arbre, qui bénéficiera immédiatement d'une Maille plus riche ;
4. profils adaptatifs / Forêt ;
5. E2/E3, lecteur Python et autres enrichissements selon mesures.

La priorité reste : petits dépôts scénarisés d'abord, dépôts réels ensuite, jamais l'inverse.