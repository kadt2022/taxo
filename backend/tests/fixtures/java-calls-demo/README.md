# java-calls-demo

Petit dépôt Java scénarisé de [TAXO-01K](../../../../docs/backlog/TAXO-01K-appels-java-entre-classes.md) : la vérité
de référence des appels Java. Il n'est ni compilé ni exécuté ; il est écrit pour compiler, comme le suppose le
premier fragment.

`expected.json` dit, écrit à la main avant tout producteur, ce que Taxo doit établir : les déclarations, les types
déclarés des champs, les implémentations, les appels avec chacun de leurs sites, et chaque site qui reste non
interprété avec sa raison fermée. Ces listes sont complètes : un fait de plus est une erreur.

Chaque cas du récit y figure une fois au moins :

| Cas | Où |
| --- | --- |
| appel vers une classe concrète des sources | `CourseController#getCourses()` → `CourseCatalog#refresh()` |
| appel vers une interface des sources | `CourseController#getCourses()` → `CourseService#getCourses()` |
| deux sites identiques, une seule arête | `catalog.refresh()`, lignes 26 et 27 |
| appel sans receveur, `this.champ` | `audit()`, `this.courseService.register(name)` |
| implémentation d'interface | `CourseServiceImpl` → `CourseService`, type et méthodes |
| surcharge ambiguë | `catalog.label(title)` |
| type de receveur inconnu (`T`) | `Holder#fingerprint()` |
| méthode héritée d'une dépendance externe | `courseRepository.findAll()` |
| méthode d'un type des sources qui étend un type externe | `courseRepository.findByTitle(title)` |
| receveur paramètre ou variable locale | `title.trim()`, `known.isEmpty()` |
| appel dans une lambda | `() -> catalog.refresh()` |
| formes hors fragment | `new HashMap<>()`, `List.copyOf(…)` |
