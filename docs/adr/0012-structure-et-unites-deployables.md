# ADR 0012 — Structure du dépôt : modules, dépendances entre modules, unités déployables

Date : 2026-09-27
Statut : Proposé
Amende : ADR 0002 (vocabulaire v1 : un type de référence, trois relations)
Récit : [TAXO-E1](../backlog/TAXO-E1-structure-et-unites-deployables.md) ; défaut D1 de `DEFAUTS-MESURES.md`

## Contexte

Taxo ne sait pas de quoi un dépôt est fait au-dessus du fichier. Or c'est la première question
d'une page Architecture : quels modules, qui dépend de qui, qu'est-ce qui se déploie. C'est aussi
une condition de justesse. Un dépôt peut contenir plusieurs applications, et une règle de sécurité
d'une application ne vaut pas pour les routes d'une autre (D1). TAXO-05 neutralise ce cas en ne
concluant rien dès qu'il voit deux applications. Il faut le résoudre.

Ce savoir n'est pas propre à Spring. Il se lit dans les descripteurs de build (Gradle, Maven,
npm, Python) et de déploiement (compose), quel que soit le langage.

## Décision

### 1. Vocabulaire

| Élément | Forme | Statut |
| --- | --- | --- |
| Référence `module` (existante) | `module:<dossier relatif>` ; `module:.` pour un projet à la racine | — |
| Référence **`application`** (nouvelle) | `application:<descripteur>#<nom>`, par exemple `application:compose.yaml#api` | — |
| `repository CONTAINS module` (existante) | un module et ses systèmes de build (`build_systems`) | `OBSERVED` |
| **`module DEPENDS_ON module`** | dépendance déclarée entre deux modules du dépôt, avec son système et sa configuration (`implementation`, `test`…) | `OBSERVED` |
| **`application BUILT_FROM module`** | l'unité déployable est construite à partir de ce module | `OBSERVED` |
| **`endpoint SERVED_BY application`** | l'application expose cette route | `INFERRED` (tranche 2) |

La clé d'une application nomme son descripteur, pour que deux fichiers compose qui déclarent un
même service restent distincts.

### 2. Une lecture déclarée, jamais devinée

Chaque descripteur est lu par sa forme écrite : chaînes littérales, blocs connus. Ce qui ne l'est
pas devient `NOT_INTERPRETED` sur le fichier qui le porte :
- inclusion calculée ;
- `projectDir` redéfini ;
- `includeBuild` ;
- `project(...)` non littéral ;
- module Maven par propriété ;
- service compose sans contexte littéral ;
- dépendance Python par chemin.

Une dépendance vers un module que Taxo ne connaît pas est déclarée, jamais inventée.

### 3. Deux tranches

1. **Structure générique** : l'évaluateur `taxo.structure` produit modules, dépendances entre
   modules et applications compose. Aucun framework n'y est connu.
2. **Applications Spring Boot** : l'évaluateur Spring établit les applications Spring Boot, puis
   `SERVED_BY` pour chaque route. Les prémisses sont :
   - le module qui porte le contrôleur ;
   - les dépendances transitives de l'application ;
   - les paquetages scannés.

   TAXO-05 rattache alors chaque route aux seules chaînes de filtres chargées par l'application
   qui la sert.

## Conséquences

- Le schéma, le validateur et la suite de conformité ajoutent le type `application` et les
  relations `DEPENDS_ON` et `BUILT_FROM` dès la tranche 1. `SERVED_BY` n'est ajoutée qu'avec la
  tranche 2.
- L'impact d'un commit montre, sans changement de consommateur :
  - un module ajouté ou retiré ;
  - une dépendance ajoutée ;
  - une application construite autrement.
- Hors de cette décision :
  - dépendances externes et leurs versions (E2) ;
  - images externes d'un service compose ;
  - `depends_on` d'exécution ;
  - Dockerfile sans compose ;
  - Kubernetes ;
  - Bazel ;
  - composite builds.
