# ADR 0011 — Appels : l'occurrence observée, la liaison déduite, les candidats hors des arêtes

Date : 2026-09-27
Statut : **Projet** — à décider avant le premier récit d'appels Java. Rien n'est implémenté.
Amende : ADR 0002 (vocabulaire v1, relations `CALLS` et `DISPATCHES_TO`, preuves)
Dépend de : ADR 0003 (analyseur Java), TAXO-ID-01 (identité des méthodes)

## Contexte

L'ADR 0002 fixe :

- `CALLS` : symbol → symbol, `OBSERVED` ;
- `DISPATCHES_TO` : symbol → symbol, `INFERRED`, règle v1 « implémentation unique dans le périmètre
  analysé ».

Avant d'en produire le premier fait, trois difficultés sont apparues.

1. **Un appel écrit, une liaison et une exécution sont trois propositions différentes.** La JLS
   distingue le choix de la déclaration à la compilation (§15.12.2) de la recherche de la méthode
   invoquée à l'exécution (§15.12.4). Voir `this.check(x)` dans le code ne dit pas, à soi seul,
   quelle déclaration est sélectionnée : il faut les surcharges, l'héritage et le type de `x`. Cela
   dit encore moins quel corps s'exécute.
2. **« Implémentation unique dans le périmètre » ne prouve pas la cible d'un appel.** Le périmètre peut
   omettre une dépendance, du code généré ou une autre application. Même dans un périmètre fermé,
   deux sites qui appellent la même interface peuvent recevoir des objets différents. Une arête
   globale `Interface#m DISPATCHES_TO Impl#m` contaminerait tous les parcours.
3. **Un site d'appel doit être retrouvable.** Dans `check(); check();`, les deux appels ont le même
   fichier, la même ligne et la même empreinte. Les preuves actuelles (`path`, `line_start`,
   `line_end`, `content_hash`) ne les distinguent pas. Rien ne dit non plus si une preuve montre
   l'appel ou la déclaration de la cible.

## Décision proposée

### 1. Identité des méthodes

Les références de méthode portent leur signature syntaxique normalisée (TAXO-ID-01) :
`symbol:java:<type>#<nom>(<types>)`. Aucune relation d'appel n'est produite avant cette identité.

### 2. `CALLS` : liaison déduite, occurrence observée en preuve

`A CALLS B` signifie :

> Dans l'instantané, le corps de `A` contient au moins un site d'appel dont la règle de résolution
> nommée sélectionne la déclaration `B`.

- **Statut `INFERRED`**, et non plus `OBSERVED`. La sélection d'une déclaration est une déduction :
  une règle, des prémisses (type du receveur, déclarations candidates, arité, surcharges écartées).
  Seule l'occurrence syntaxique est observée, et elle est portée par les preuves.
- **`CALLS` vise la déclaration sélectionnée, jamais le corps exécuté.** Un appel à une méthode
  d'interface a pour objet la déclaration d'interface. `CALLS` n'affirme ni que le site est atteint,
  ni quel corps s'exécute.
- **Une arête, plusieurs sites.** Chaque site qui soutient l'arête est une preuve de rôle
  `call-site` (point 5). Deux sites, deux preuves. Une modification de ligne change une preuve, pas
  l'arête.
- **Règles de résolution nommées et bornées.** Le récit d'appels fixe, **pour chaque forme prise en
  charge** :
  1. les prémisses qui permettent de sélectionner une déclaration ;
  2. les cas explicitement couverts ;
  3. le diagnostic produit quand une prémisse manque.

  Une forme syntaxique (`this.f()`, champ, paramètre, statique) ne suffit pas. Même `this.f(x)`
  demande de traiter les surcharges, l'héritage et le type de `x`. Un type déclaré connu est une
  prémisse utile, jamais une liaison à lui seul. Par exemple, pour un premier fragment :
  - un appel non qualifié à une méthode `private` du même type, d'arité unique parmi les déclarations
    de ce nom, sans méthode de même nom héritée ;
  - sinon, `NOT_INTERPRETED` sur le site, avec la raison.
- **Pas d'élargissement par nom.** Une recherche de méthodes par nom n'est jamais présentée comme une
  résolution Java.

Conséquences pour le contrat :

- `RELATIONS['CALLS']` passe de `{'OBSERVED'}` à `{'INFERRED'}` : le schéma, le validateur et la suite
  de conformité changent ensemble ;
- les consommateurs affichent la déduction : « Confirmée par Taxo, par déduction », prémisses
  visibles (déjà en place depuis TAXO-05) ;
- le POC `authchain`, qui produit des `CALLS` `OBSERVED`, est aligné ou retiré.

**Alternative écartée** : garder `CALLS` `OBSERVED` en définissant l'observation comme « liaison
produite par un résolveur ». C'est défendable pour un compilateur, mais la frontière entre ce qui est
lu et ce qui est déduit deviendrait invisible, et elle changerait de sens selon le résolveur.

### 3. `DISPATCHES_TO` : suspendu jusqu'à l'ancrage sur le site

- La règle v1 « implémentation unique dans le périmètre analysé » est **retirée**.
- Aucun `DISPATCHES_TO` n'est produit tant qu'un site n'est pas une référence adressable. Ce jour-là,
  le fait sera ancré sur le site, avec des prémisses sur son receveur. Il se lira : « si ce site
  transfère le contrôle, sa cible est celle-ci », jamais « ce site s'exécute ».
- L'introduction d'un type de référence de site (par exemple `callsite:`) est un amendement séparé,
  quand un besoin de requête ou de résolution par site est mesuré.

### 4. Candidats : un résultat de résolution, jamais une arête

- **Pas de relation `MAY_CALL`**, ni de statut « possible ». Un fait « peut-être » finit toujours lu
  comme un fait.
- Un site non résolu est déclaré `NOT_INTERPRETED`. Son diagnostic dit :
  - la raison (`receiver_not_established`, `overload_ambiguous`, `declaration_absent`…) ;
  - les candidats trouvés ;
  - s'il est complet (`candidate_set_complete: false` par défaut) ;
  - ce que « candidat » signifie : type compatible trouvé dans le périmètre, ou cible possible selon
    une analyse nommée. Les deux ne se mélangent pas dans une même liste.
- **Une seule candidate reste une candidate.**
- **Lambdas et références de méthode.** Créer une lambda n'est pas l'appeler : les appels de son corps
  appartiennent à la lambda, jamais à la méthode englobante. Une référence de méthode (`this::f`)
  n'est pas un appel à `f`. Tant que la lambda n'a pas d'identité propre, son corps est une région
  `NOT_INTERPRETED`.

  *Constat* : la primitive « chaînes d’appels » de l’analyseur Java (TAXO-05, PR #45) garde les lambdas à
  part (`Argument.function`), mais rattache leur méthode à la méthode englobante. Sans effet pour la
  sécurité, cela serait faux pour `CALLS` : à corriger dans le récit d'appels.

### 5. Preuves : position précise, propriétaire lexical, rôle

Trois champs facultatifs sont ajoutés aux preuves (`evidence`). Ils sont rétrocompatibles : aucune
preuve existante ne change.

| Champ | Contenu | Pourquoi |
| --- | --- | --- |
| `column_start`, `column_end` | position dans la ligne, en octets UTF-8, à partir de 0, fin exclusive, comme les positions de tree-sitter | distinguer `check(); check();` ; la colonne dans la ligne ne dépend pas des fins de ligne (CRLF/LF, cas 6 du plan), contrairement à un décalage absolu dans le fichier |
| `symbol` (existant) | le propriétaire lexical de l'occurrence : la méthode, ou plus tard la lambda | savoir **où** l'appel est écrit |
| `role` | `call-site`, `target-declaration`, `receiver-declaration`… (liste fermée dans le catalogue de l'évaluateur) | deux preuves d'une même arête peuvent ne pas être deux appels. `method` nomme la règle d'extraction, `role` dit ce que la preuve soutient |

`content_hash` reste calculé sur les lignes (ADR 0002). La position affine la localisation, pas
l'empreinte.

### 6. `IMPLEMENTS` inchangé

`IMPLEMENTS` relie deux types. Une relation entre une méthode d'implémentation et la déclaration
d'interface serait distincte, et n'est pas dans ce projet.

## Conséquences

- L'ordre de réalisation devient :
  1. TAXO-ID-01 (identité) ;
  2. TAXO-01I (voisinage sur les faits existants) ;
  3. décision de cet ADR ;
  4. premières liaisons Java, fragment borné ;
  5. essai A/B/C.

  `IMPLEMENTS` et `DISPATCHES_TO` ne sont pas dans le premier récit d'appels.
- L'analyse reste statique et sans JVM (ADR 0003). Un moteur de liaison externe (Eclipse JDT par
  exemple) pourra être comparé sur les cas mesurés comme manquants, jamais imposé.
- Une absence de `CALLS` ne prouve jamais une absence d'appel. Seule une propriété bornée l'est :
  « aucun appel textuel direct dans les corps entièrement analysés ».
- Un chemin fait de liaisons n'est pas une exécution réalisable. Les projections disent « déclarations
  à examiner », jamais « voici pourquoi la requête a été refusée ».

## Questions ouvertes

1. Faut-il, pour `CALLS`, un qualificatif `invocation` (statique, virtuel, `super`, constructeur) dès
   le premier fragment, ou seulement avec le dispatch ?
2. L'identité d'une lambda : position (`#m(...)$lambda@L12:C8`), ou ordre dans la méthode ? La
   position change à chaque édition ; l'ordre, à chaque insertion.
3. Faut-il publier les diagnostics de résolution comme couvertures `NOT_INTERPRETED` par site, ou
   comme un troisième espace (résultats de résolution) consultable par l'API ?
