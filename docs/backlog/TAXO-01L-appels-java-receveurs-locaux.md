# TAXO-01L — Appels Java : receveurs paramètres et variables locales, accesseurs de record, lambdas

Statut : **proposé**, à valider avant toute implémentation. Rédigé le 2026-10-08.  
Suite de : [TAXO-01K](TAXO-01K-appels-java-entre-classes.md) (« Décision proposée pour le fragment suivant »).  
Source de vérité : `ARCHITECTURE.md` § 5.5, § 5.6 et § 14.  
Dépend de : `taxo.java-calls` livré par TAXO-01K (PR A à D).  
Ne dépend pas de Minia. Ne touche pas MIP.

## Constat

Sur `student-analysis-java` (le projet `student-course-demo` de TAXO-01K, commit `01163f1`), la vue Appels de
`GET /api/courses` s'arrête dans `CourseAccessControlService#filterCoursesByAccess` sur une frontière qui donne
trois raisons : appel dans une lambda, receveur paramètre ou variable locale non suivi, forme d'appel non lue.
Les trois existent réellement dans la méthode :

```java
public Collection<Course> filterCoursesByAccess(Collection<Course> courses, Integer studentAge, String studentInstruction) {
    return courses.stream()                                    // receveur paramètre, type de la JDK
            .filter(course -> course.minAge() == null ...)     // chaîne ; appel dans une lambda
            .filter(course -> ... studentInstruction.equals(course.requiredInstruction()))
            .toList();
}
```

La frontière dit vrai. Ce récit lève celles des raisons qui peuvent l'être **sans inventer de cible**, et garde
la JDK et les bibliothèques comme frontière explicite.

## Mesure avant (2026-10-08)

Essai reproductible `backend/scripts/java_calls_trial.py`, SQLite, `taxo.java-calls` 1.0.0. Le classement des
sites non interprétés par tranche est fait par un script de mesure hors produit (voir « Méthode de mesure ») :
il dit ce que chaque tranche **pourrait** lever, pas ce que Taxo produira.

| Dépôt | Commit | Sites vus | Résolus | Non interprétés |
| --- | --- | --- | --- | --- |
| `student-analysis-java` | `01163f1` | 104 | 24 (23 `CALLS`) | 80 |
| `bibliotheque` | `d2e3c46` | 147 | 28 | 119 |
| `spring-petclinic` | `500158f` | 253 | 7 | 246 |

Raisons d'arrêt sur `student-analysis-java` : `UNSUPPORTED_CALL_FORM` 39, `LAMBDA_OR_LOCAL_CONTEXT` 19,
`RECEIVER_KIND_DEFERRED` 12, `TARGET_TYPE_OUTSIDE_SNAPSHOT` 10. Les neuf routes atteignent leur service puis leur
repository (`HANDLED_BY` puis `CALLS`, profondeur 3, 20 à 43 ms, 7,7 à 14,5 Ko pour 32 Ko).

### Ce que cachent les receveurs paramètres et variables locales (`RECEIVER_KIND_DEFERRED`)

| Type écrit du receveur | student | bibliotheque | petclinic |
| --- | --- | --- | --- |
| Type des sources, hiérarchie toute dans les sources | 0 | 0 | 1 |
| Type des sources dont la hiérarchie atteint `java.io.Serializable` | 0 | 16 | 49 |
| Record des sources, appel d'un accesseur implicite (`request.code()`) | 8 | 5 | 0 |
| Type hors des sources (JDK, bibliothèque) | 4 | 8 | 76 |
| **Total** | **12** | **29** | **126** |

**Lecture.** Suivre les paramètres et les variables locales **seuls** ne relierait presque rien (1 site sur 167) :
deux verrous de TAXO-01K arrêtent ensuite presque tous les autres :

- un supertype hors des sources rend le site `SUPER_TYPE_UNRESOLVED`. Pour une entité, c'est
  `java.io.Serializable`, interface qui ne déclare aucune méthode ; pour un record, c'est sa superclasse
  implicite `java.lang.Record`, qui ne déclare que `equals`, `hashCode` et `toString`, déjà traités comme les
  méthodes d'`Object` ;
- un accesseur de record (`Course#minAge()`) n'est écrit nulle part : il est déclaré implicitement par le
  composant `Integer minAge` de l'en-tête. Taxo ne produit aujourd'hui aucun `CONTAINS` pour les membres d'un
  record sans corps ; `course.minAge()` n'a donc aucune cible possible.

Les mêmes verrous arrêtent aussi des receveurs **champs** déjà suivis : `SUPER_TYPE_UNRESOLVED` à cause de
`Serializable` ou `Record` sur 16 sites de petclinic et 5 de bibliotheque.

### Ce que cachent les lambdas (`LAMBDA_OR_LOCAL_CONTEXT`)

| Forme dans la lambda | student | bibliotheque | petclinic |
| --- | --- | --- | --- |
| Appel sans receveur d'une méthode du type (`canAccessCourse(...)`) | 1 | 0 | 1 |
| Receveur capturé : paramètre de la méthode englobante | 1 (`String`) | 0 | 0 |
| Receveur paramètre de lambda au type inféré (`course -> course.minAge()`) | 9 | 3 | 4 |
| Paramètre de lambda au type écrit (`(Course c) -> ...`) | 0 | 0 | 0 |
| Chaîne, création `new T()` | 8 | 11 | 5 |
| **Total** | **19** | **14** | **10** |

**Lecture.** Le type de `course` dans `courses.stream().filter(course -> ...)` ne vient pas des sources : il
faut savoir que `Collection<E>.stream()` rend `Stream<E>` et que `Stream<T>.filter` reçoit un `Predicate<T>`.
Ce sont des signatures de la JDK. Les lire, c'est sortir de « seules les sources comptent » : ce n'est pas une
question de génériques des sources mais une décision de dépendance (catalogue de signatures externes ou lecture
des JAR), donc **hors de ce récit** (voir « Hors périmètre »).

### Estimation après (plafond, non promise)

Avec les tranches A, B et C ci-dessous, le script de mesure estime au plus :

| Dépôt | Résolus avant | Plafond estimé après | Devenus frontière JDK explicite |
| --- | --- | --- | --- |
| `student-analysis-java` | 24 | 32 | 4 |
| `bibliotheque` | 28 | 54 | 8 |
| `spring-petclinic` | 7 | 73 | 76 |

La tranche D (lambdas) ajouterait au plus 1 site sur student (`canAccessCourse`) et 1 sur petclinic.

Plafond seulement : le script compare les types par nom simple et ne vérifie ni surcharges, ni arguments, ni
portée fine. PR E mesure les vrais nombres avec Taxo.

### Remarque sur `student-analysis-java`

À `01163f1`, ce projet ne compile pas : `Course` et `Student` sont des records à cinq composants, mais
`CourseRepository#save` et `StudentRepository#save` appellent `new Course(id, code, title)` et
`new Student(id, name, email)` avec trois arguments. Sans effet sur la mesure (`new T()` est hors fragment),
mais `CALLS` suppose un code qui compile (`known_gaps`) : la fixture de ce récit, elle, doit compiler.

## Intention

En tant que personne qui explore une route, je veux que Taxo suive un appel dont le receveur est un paramètre,
une variable locale ou un accesseur de record des sources, et un appel sans receveur écrit dans une lambda,
sans jamais inventer de cible, et que la JDK reste une frontière dite comme telle.

Exemple attendu sur `student-analysis-java` :

```text
CourseController#createCourse(CreateCourseRequest)
  CALLS → CourseController.CreateCourseRequest#code()      (accesseur implicite)
  CALLS → CourseController.CreateCourseRequest#title()
  CALLS → CourseService#createCourse(String,String)

CourseAccessControlService#canAccessCourse(Course,Integer,String)
  CALLS → Course#minAge()
  CALLS → Course#requiredInstruction()
  frontière : studentInstruction.equals(...) → TARGET_TYPE_OUTSIDE_SNAPSHOT (java.lang.String)
```

**Priorité inchangée : moins de `CALLS`, mais vrais.** Un accesseur de record appelé est un `CALLS` vers la
déclaration de l'accesseur ; aucune nouvelle relation (« utilise », « lit ») n'est créée.

## Décisions proposées (à valider)

### 1. Paramètres et variables locales deviennent des prémisses, sans assouplir § 5.5

TAXO-01K les a reportés parce qu'ils n'ont pas de symbole : leur type ne pouvait pas être une prémisse. Ce récit
leur en donne un, dans `java-symbol-syntactic` :

- paramètre : `symbol:java:<Type>#m(<signature>)/<nom>` ;
- variable locale : même forme ; si le même nom est déclaré plusieurs fois dans le corps (deux boucles
  `for (Pet pet : ...)`), le nom est suivi de son rang de déclaration dans le corps, en ordre du fichier
  (`/pet#2`). L'identité ne dépend pas des lignes, pour rester stable quand le code au-dessus bouge.

Faits produits, seulement pour une déclaration qui sert de receveur à un site (la Maille ne grossit pas d'un
fait par variable) :

| Fait | Relation | Statut |
| --- | --- | --- |
| la méthode déclare le paramètre ou la variable | `symbol:java:<Type>#m(…)` `CONTAINS` `…#m(…)/<nom>` | `OBSERVED` |
| son type déclaré est un type des sources | `…#m(…)/<nom>` `TYPED_AS` `symbol:java:<Type>` | `OBSERVED` |

Comme pour un champ : un type hors des sources ne donne aucun `TYPED_AS` et le site est
`TARGET_TYPE_OUTSIDE_SNAPSHOT` ; un type générique (`T`) donne `RECEIVER_TYPE_UNKNOWN`.

**Portée réelle** : le receveur désigne la déclaration visible au site (bloc englobant le plus proche, déclarée
avant le site), et non plus « tout nom déclaré n'importe où dans le corps masque le champ ». Une variable `var`
n'a pas de type écrit : `RECEIVER_TYPE_UNKNOWN` (aucune inférence d'expression). Un nom déclaré par un motif
(`instanceof Pet pet`) ou dans une ressource suit la même règle que la variable locale ; si sa portée n'est pas
établie sans ambiguïté, le site garde `RECEIVER_KIND_DEFERRED`.

### 2. Supertypes de la JDK connus du contrat, comme `Object`

Trois supertypes externes sont connus par leur seule déclaration publique, inscrite au contrat :

- `java.io.Serializable` et `java.lang.Cloneable` : aucune méthode ; ils ne cachent aucune cible ;
- `java.lang.Record` : `equals/1`, `hashCode/0`, `toString/0`, traités exactement comme les méthodes d'`Object`
  (résolus seulement s'ils sont redéclarés à la même signature, sinon `OVERLOAD_AMBIGUOUS`).

Aucun symbole n'est créé pour eux : pas d'`EXTENDS` ni d'`IMPLEMENTS` vers la JDK (règle de TAXO-01K
inchangée). La liste est fermée ; `java.lang.Enum`, qui déclare de nombreuses méthodes, n'y entre pas.

### 3. Accesseurs implicites de record

Pour chaque composant `T x` d'un record des sources, sans méthode `x()` écrite dans son corps :

| Fait | Relation | Statut | Preuve |
| --- | --- | --- | --- |
| le record déclare le champ du composant | `symbol:java:<Record>` `CONTAINS` `…<Record>#x` | `OBSERVED` | le composant |
| le champ a un type des sources | `…<Record>#x` `TYPED_AS` `symbol:java:<T>` | `OBSERVED` | le composant |
| le record déclare l'accesseur | `symbol:java:<Record>` `CONTAINS` `…<Record>#x()` | **à décider** (`INFERRED` recommandé) | le composant |

Décision à prendre pour le statut de l'accesseur :

- **`INFERRED` (recommandé)** par une règle `java.record.implicit-accessor/1` (prémisse : le `CONTAINS` du
  champ du composant), sur le modèle d'`IMPLEMENTS` entre méthodes : ce qui est écrit, c'est le composant ;
  `x()` est déclaré par le langage, aucune ligne ne l'écrit. Le statut dit donc comment le fait est établi.
  Conséquence : § 14 doit admettre qu'un `CALLS` cite une prémisse `INFERRED` d'une règle nommée du même
  producteur (§ 5.5 n'est pas assoupli : la prémisse reste un fait du même instantané). C'est un changement de
  doctrine, à valider.
- `OBSERVED`, preuve à la ligne du composant : § 14 inchangé, mais le statut présenterait comme lu dans les
  sources une déclaration qui n'y est pas écrite. Écarté pour cette raison.

Un accesseur écrit explicitement dans le corps est une méthode ordinaire, déjà couverte par TAXO-01K.

### 4. Appels sans receveur dans une lambda : à qui les attribuer

§ 14 dit : « créer une lambda n'est pas l'appeler ; ses appels ne sont jamais attribués à la méthode
englobante ». Ce récit **ne change pas** cette règle. Deux options :

- **Symbole de lambda (recommandé)** : la lambda reçoit un symbole `…#m(…)/lambda#<rang>` (rang dans le corps,
  ordre du fichier), contenu par la méthode (`CONTAINS`, `OBSERVED`, preuve : la lambda). Le `CALLS` part de
  la lambda. La vue Chaîne montre `méthode → contient → lambda → appelle → cible` ; la vue Appels ne relie
  pas la méthode à sa lambda (`CONTAINS` n'est pas une exécution) et dessine une frontière « lambda ». Honnête,
  mais `filterStudentsByCourseAccess → canAccessCourse` n'apparaît pas d'un seul trait dans la vue Appels.
- Attribution à la méthode englobante, marquée « dans une lambda » : la flèche apparaît d'un trait, mais § 14
  est réécrit et `CALLS` ne voudrait plus dire « le corps de A contient un site » au même sens.

Mesuré : 2 sites sur 3 dépôts. Cette tranche vient donc en dernier ; elle peut être reportée sans gêner A, B, C.

Les receveurs **capturés** dans une lambda (paramètre, variable ou champ de la méthode englobante) suivent les
règles 1 à 3 depuis le symbole de lambda. Un **paramètre de lambda** au type inféré reste
`LAMBDA_OR_LOCAL_CONTEXT` ; un paramètre de lambda au type écrit suit la règle 1 (aucun mesuré, mais la règle
coûte peu une fois la portée réelle suivie).

## Invariants (repris de TAXO-01K, non négociables)

- `CALLS` est générique `symbol → symbol`, `INFERRED`, et vise la déclaration, jamais le corps exécuté.
- Un appel non établi est `NOT_INTERPRETED` avec une raison fermée ; aucune cible inventée, aucun symbole de la
  JDK ou d'une bibliothèque.
- `ARCHITECTURE § 5.5` n'est pas assoupli : chaque `CALLS` cite des faits du même instantané.
- Aucune relation nouvelle (`USES`, `READS`…), aucune relation Spring, JPA ou contrôleur.
- `DISPATCHES_TO` et MIP restent hors périmètre ; rien ici ne les bloque.
- Aucune logique Java dans l'Explorer ni dans le moteur de voisinage.
- Même instantané, même version d'évaluateur : mêmes faits, mêmes diagnostics, même ordre.
- La version de l'évaluateur et du catalogue `java-calls` change (nouvelle règle, nouveaux faits) : deux
  analyses de versions différentes restent distinguées par leurs occurrences (TAXO-01E, TAXO-01F).

## Critères d'acceptation

1. `r.f()` où `r` est un paramètre au type des sources, hiérarchie dans les sources, produit `CALLS` avec en
   prémisses le `CONTAINS` et le `TYPED_AS` du paramètre.
2. Même chose pour une variable locale déclarée avant le site dans un bloc englobant ; deux variables de même
   nom dans deux blocs voisins donnent deux symboles distincts et chaque site vise la bonne.
3. Un paramètre ou une variable qui masque un champ de même nom est suivi comme paramètre ou variable, jamais
   comme le champ ; un champ masqué seulement dans un autre bloc reste suivi comme champ.
4. Un receveur de type JDK ou bibliothèque donne `TARGET_TYPE_OUTSIDE_SNAPSHOT`, sans `TYPED_AS` ni symbole
   externe ; `var` et un type générique donnent `RECEIVER_TYPE_UNKNOWN`.
5. Une hiérarchie qui n'atteint, hors des sources, que `Serializable`, `Cloneable` ou `Record` ne donne plus
   `SUPER_TYPE_UNRESOLVED` ; tout autre supertype externe le donne toujours.
6. `record R(T x)` sans méthode `x()` écrite : `r.x()` produit `CALLS` vers `R#x()`, dont le `CONTAINS` a pour
   preuve la ligne du composant et le statut retenu par la décision 3 ; avec `x()` écrite, la cible est la méthode écrite et aucun accesseur implicite
   n'est produit.
7. `r.equals(o)` sur un record ne vise jamais `Record` ni l'accesseur ; même règle que pour `Object`.
8. Un appel sans receveur dans une lambda produit, selon la décision 4, un `CALLS` depuis le symbole de lambda ;
   il n'est jamais attribué à la méthode englobante tant que § 14 n'est pas réécrit.
9. Un receveur paramètre de lambda au type inféré reste `LAMBDA_OR_LOCAL_CONTEXT`.
10. La fixture `java-calls-demo` (ou une fixture sœur) compile, et ses vérités attendues sont écrites à la main
    avant d'exécuter Taxo ; `taxo.java-calls` les retrouve exactement.
11. Aucun `CALLS` faux sur les trois dépôts mesurés : chaque `CALLS` **nouveau** par rapport à TAXO-01K est
    vérifié un à un à la main sur les trois, `spring-petclinic` compris (le plus grand nombre de nouveaux
    sites).
12. Le portail nomme juste les nouveaux symboles : un paramètre, une variable locale ou une lambda n'est jamais
    dit « la méthode » (aujourd'hui `symbolNoun` dans `frontend/src/sentences.ts` prend tout symbole contenant
    `(` pour une méthode), et `TYPED_AS` n'est plus libellé « type de champ » quand son sujet n'est pas un champ
    (`frontend/src/domains.ts`). Le classement suit la forme de symbole décidée au contrat, sans logique Java
    dans l'Explorer.

## Découpage proposé

Chaque PR est testable seule, sur la fixture.

- **PR A — Contrat et vérité de référence.** Formes de symbole paramètre, variable, lambda ; liste fermée des
  supertypes JDK connus ; statut de l'accesseur implicite (décision 3) ; attribution des lambdas (décision 4) ;
  `ARCHITECTURE § 14` mis à jour ; fixture et `expected.json` étendus ; conformité ; libellés du portail pour
  les nouvelles formes de symbole et pour `TYPED_AS`, avec leurs tests (critère 12). Aucun producteur encore.
- **PR B — Paramètres et variables locales.** Portée réelle dans le lecteur (`sites.py`), faits déclaratifs,
  résolution ; tests unitaires par forme et par raison.
- **PR C — Supertypes JDK connus et accesseurs de record.** Les deux verrous mesurés ; tests de non-régression
  sur `Serializable` (rouge sans correctif, vert avec).
- **PR D — Appels dans les lambdas.** Selon la décision 4 ; peut être reportée.
- **PR E — Mesure.** Les trois dépôts avec `java_calls_trial.py`, nombres réels contre le plafond ci-dessus,
  coût dans les Tuiles et taille de la Maille ; récit clos.

## Limites

- Les arguments ne sont toujours pas typés : l'hypothèse « le code compile » reste dans `known_gaps`.
- Les surcharges se départagent toujours par nom et arité seulement.
- Les chaînes (`a.b().c()`) restent `UNSUPPORTED_CALL_FORM`, même quand le premier appel vise une méthode des
  sources dont le type de retour est écrit ; sur student, la plupart finissent de toute façon dans la JDK
  (`Optional.orElseThrow`, `Stream.filter`). À mesurer dans un récit séparé.
- Spring Data reste une frontière juste (déclarations hors des sources).

## Hors périmètre

- types des paramètres de lambda inférés par les génériques de la JDK (`stream().filter(c -> c.f())`) : il faut
  les signatures de la JDK, donc une décision de dépendance (catalogue de signatures externes, lecture des JAR) ;
  à proposer comme récit séparé si le besoin est confirmé ;
- chaînes d'appels, appels statiques `T.f()`, créations `new T()`, `super.f()` ;
- références de méthode (`Course::minAge`) ;
- classes anonymes et locales ;
- `DISPATCHES_TO`, dispatch dynamique, MIP ;
- inférence de type d'expression, `var` ;
- lecture des JAR, exécution de Gradle ou Maven ;
- toute relation nouvelle ou spécifique à un framework.

## Méthode de mesure

Les nombres « avant » viennent de `backend/scripts/java_calls_trial.py <dépôt> <commit>`. Le classement par
tranche vient d'un script de mesure hors produit, gardé avec les essais du projet (`essais/`) : il relit les
sites `NOT_INTERPRETED` du `diagnostic`, retrouve le nœud du site dans l'arbre syntaxique, cherche la
déclaration du receveur (paramètre, variable, champ, paramètre de lambda) et compare son type écrit, par nom
simple, aux types des sources et à leur hiérarchie. C'est une estimation : il ne résout rien et ne vérifie ni
surcharges, ni arguments, ni portée fine.

Dépôts : `student-analysis-java` à `01163f17`, `bibliotheque` à `d2e3c46` (git bundle des essais du projet),
`spring-petclinic` à `500158f7`.
