# TAXO-ID-01 — Identité des méthodes : une signature syntaxique normalisée

Statut : rédigé le 2026-09-27, réalisé le 2026-09-27.

Dépend de : ARCHITECTURE § 5 (références), TAXO-01B (identité canonique), ARCHITECTURE § 7.3 (analyseur Java).
Amende : la forme des références `symbol:java:` (ARCHITECTURE § 14).

## Pourquoi maintenant

Aujourd'hui, une méthode est désignée par son type et son nom :

```text
symbol:java:com.example.api.UserController#list
```

Deux surcharges (`list()` et `list(String)`) reçoivent la même référence. Pour `HANDLED_BY`, deux
endpoints traités par deux méthodes différentes semblent traités par la même. La navigation (TAXO-01I)
exposerait cette ambiguïté dès sa première tuile, et les appels (`CALLS`) la multiplieraient. Chaque
analyse qui produit des faits sous cette forme ajoute de la mémoire à identité ambiguë.

## Décision de contrat

### 1. Forme

```text
symbol:java:<type qualifié>#<nom>(<type>,<type>,...)
symbol:java:<type qualifié>#<init>(<type>,...)         constructeur
symbol:java:<type qualifié>                             type (inchangé)
```

Exemples :

```text
symbol:java:com.example.api.UserController#list()
symbol:java:com.example.api.UserController#list(String)
symbol:java:com.example.api.UserController#search(List,int[])
```

### 2. Une identité syntaxique, et elle le dit

La liste des paramètres est construite à partir des **types écrits dans la source**, normalisés par
les règles ci-dessous. Ce n'est pas la signature résolue par le compilateur : un type n'est pas
résolu vers son nom qualifié. La JLS (§8.4.2) définit la signature d'une méthode par son nom et les
types de ses paramètres ; ces règles en suivent la structure, sans prétendre en calculer les types.

Le catalogue qui produit une telle référence le déclare (point 5). Un consommateur ne doit jamais
lire `#list(String)` comme « le paramètre est `java.lang.String` ».

### 3. Règles de normalisation

| Écrit | Normalisé | Règle |
| --- | --- | --- |
| `list(String name)` | `list(String)` | le nom du paramètre est exclu |
| `list( final @NotNull String name )` | `list(String)` | modificateurs, annotations et espaces exclus |
| `f(String[] a)`, `f(String a[])` | `f(String[])` | un tableau écrit sur le déclarateur est reporté sur le type |
| `f(int[] a[])` | `f(int[][])` | les dimensions s'additionnent |
| `f(String... a)` | `f(String[])` | un paramètre variable est un tableau (JLS §8.4.1) : `f(String...)` et `f(String[])` ont la même signature |
| `f(List<String> a)`, `f(Map<K, List<V>> m)` | `f(List)`, `f(Map)` | les arguments de type sont retirés : deux surcharges ne peuvent différer que par eux (même effacement, JLS §8.4.2) |
| `f(Map.Entry e)` | `f(Map.Entry)` | un nom composé reste composé |
| `f(java.util.List a)` | `f(java.util.List)` | un nom qualifié reste qualifié, tel qu'écrit |
| `<T> f(T t)` | `f(T)` | une variable de type reste son nom écrit (voir limites) |
| `f(int x)` | `f(int)` | types primitifs inchangés |
| `f(@A int @B [] x)` | `f(int[])` | annotations de type exclues |

Le type d'un récepteur explicite (`f(Foo this)`) est exclu : il ne fait pas partie de la signature.

### 4. Jamais de fusion silencieuse

Si deux déclarations d'un même type produisent la même référence normalisée, les deux restent
distinctes et ambiguës. Par exemple, `f(java.util.List)` et `f(List)` d'imports différents, ou
deux variables de type homonymes. L'évaluateur :

- ne produit aucun fait dont l'une d'elles serait sujet ou objet ;
- déclare `NOT_INTERPRETED` sur `symbol:java:<type>#<nom>`, avec pour périmètre le fichier, et la
  raison « identité syntaxique ambiguë ».

Deux méthodes ne partagent jamais une référence : c'est le critère d'acceptation principal.

### 5. Version du schéma d'identité

Le changement de forme est un changement de contrat du catalogue, pas du logiciel analysé :

- `spring-api` passe de `catalog_version` 1 à 2, `taxo.spring-api` de 0.1.x à 0.2.0 ;
- `spring-security` suit, s'il est fusionné : ses prémisses citent le handler ;
- la documentation du catalogue nomme le schéma : `java-symbol-syntactic/1`.

### 6. Limites déclarées

- **Écritures différentes du même type.** `List` et `java.util.List` donnent deux identités. Un
  changement de style d'import change donc l'identité de la méthode, et un diff le montrera comme une
  méthode retirée et une méthode ajoutée. Les résoudre exige une résolution de types, hors de ce récit.
- **Variables de type.** Renommer `T` en `E` change l'identité. L'effacement vers la borne exigerait
  de lire les bornes : hors de ce récit.
- **Types imbriqués hérités, imports statiques de types** : écrits tels quels, non résolus.

## Migration

### Les faits déjà enregistrés ne sont pas réécrits

Un ancien `#list` peut désigner plusieurs méthodes : il ne peut pas être renommé automatiquement vers
une seule référence nouvelle. Les analyses déjà enregistrées gardent leurs faits dans leur forme
d'origine, avec leur `catalog_version` 1. Aucune migration de données n'est faite.

### Comparer deux états

- **Impact d'un commit** (TAXO-HIST-01, `diff_facts`). L'impact réévalue le parent et le commit avec
  le même évaluateur, dans la même exécution (`history/application/queries.py`, `_evaluate`). Les deux
  côtés utilisent donc le même schéma par construction. Un test le garantit : sur un commit qui ne
  touche aucun contrôleur, l'impact ne rapporte aucun changement de `HANDLED_BY`, même après la montée
  de version.
- **Comparaison de faits enregistrés.** Une comparaison entre deux analyses enregistrées, aujourd'hui
  ou plus tard, vérifie l'égalité de `catalog_id` et `catalog_version` pour chaque évaluateur. Si elles
  diffèrent, l'évaluateur est déclaré **non comparable**, avec la raison « schéma d'identité
  différent ». Ses faits ne sont jamais comparés : un changement de Taxo ne doit pas apparaître comme
  un changement massif du logiciel.

### Consommateurs

- `taxo.spring-security` : les prémisses `HANDLED_BY` citent la nouvelle forme ; les tests suivent.
- Portail : `reference()` affiche la clé telle quelle ; vérifier la lisibilité de `#list(String)`.
- Minia et `verify_claim` : une affirmation dans l'ancienne forme (`#list`) n'est plus trouvée. Elle
  donne `NOT_PROVEN`, jamais `REFUTED`, puisque `HANDLED_BY` n'est pas exclusive. `describe` et les
  exemples du protocole montrent la nouvelle forme.
- Exemples d'ARCHITECTURE § 5, § 7.4 et § 12 : mis à jour, ou annotés « forme antérieure à TAXO-ID-01 ».

## Acceptation

1. L'analyseur Java donne, pour chaque méthode et constructeur annoté, sa liste de types de
   paramètres normalisée ; chaque ligne de la table du point 3 a son test.
2. `HANDLED_BY` a pour objet la référence complète. Deux surcharges traitant deux endpoints donnent
   deux objets différents.
3. Deux déclarations de même référence normalisée ne produisent aucun fait et sont déclarées
   `NOT_INTERPRETED`, avec la raison.
4. Le catalogue `spring-api` est en version 2, et la documentation nomme le schéma d'identité.
5. L'impact d'un commit sans changement de contrôleur ne rapporte aucun changement de `HANDLED_BY`.
6. Une comparaison de faits enregistrés de versions de catalogue différentes est déclarée non
   comparable, jamais calculée. Si une telle comparaison n'existe pas encore, le test porte sur la
   fonction de comparaison.
7. Les faits d'analyses antérieures restent lisibles et ne sont pas réécrits.
8. Les tests existants de `spring-api`, `spring-security`, du protocole et du portail passent avec la
   nouvelle forme.

## Hors périmètre

- Résolution des types des paramètres vers leur nom qualifié.
- Effacement des variables de type vers leurs bornes.
- Références de méthodes non annotées (elles viendront avec les appels).
- Lambdas : leur identité propre sera fixée avec les appels (ARCHITECTURE § 14).
