# ADR 0003 — Premier analyseur de code : Java lu par sa syntaxe, endpoints Spring en faits

Date : 2026-09-26
Statut : Proposé
Dépend de : ADR 0002 (contrat du fait), ADR 0004 (monolithe modulaire), ADR 0007 (faits Git)
Récits : TAXO-03 (analyseur Java), TAXO-04 (évaluateur Spring API)

## Contexte

Jusqu'ici, Taxo établit des faits sur la forme du dépôt (fichiers, langages, technologies, historique Git)
mais aucun sur ce que fait le code. La première connaissance « chère » annoncée par le plan est la
surface HTTP d'une application Spring : quels endpoints existent, et quelle méthode traite chacun. C'est
la base de la démo technique (« qu'est-ce qui a changé entre ces deux commits ? ») et de la chaîne
d'autorisation (TAXO-05).

Le plan recommandait, pour le spike TAXO-03, JavaParser et JavaSymbolSolver dans un processus JVM
séparé. Deux contraintes ont pesé depuis :

- Taxo tourne en un seul processus Python (ADR 0004), en CI comme en Docker. Une JVM ajoute un runtime,
  un protocole entre processus et un second outillage de build ;
- l'évaluation doit rester rapide : elle rejoue chaque instantané comparé (impact d'un commit, parent
  puis commit).

Le POC de la chaîne d'autorisation (`backend/poc/authchain`) lisait Spring par expressions régulières. Il
a prouvé le mécanisme, et ses limites : pas de constantes, pas de tableaux, pas de types imbriqués.

## Décision

1. **L'analyseur Java lit la syntaxe avec tree-sitter** (`tree-sitter`, `tree-sitter-java`, roues
   binaires, sans JVM ni compilation). Il ne lit que les sources de l'instantané : aucun Gradle ni Maven
   n'est exécuté, aucun jar n'est lu.
2. **Frontière Java / Spring** (décision du 2026-09-13, inchangée) :
   - `app/evaluators/java` donne les primitives Java : paquetage, imports, types (imbriqués compris),
     supertypes, annotations et leurs valeurs, méthodes annotées, constantes chaînes. Il ne connaît aucun
     framework ;
   - `app/evaluators/spring_api` est propriétaire du concept d'endpoint.
3. **Résoudre seulement ce qui est écrit.** Une valeur d'annotation est résolue si elle est une chaîne,
   une concaténation de chaînes, ou une constante `static final String` trouvée sans ambiguïté :
   - dans le type ou un type englobant ;
   - par import statique ;
   - dans un type du dépôt désigné par son nom, un import ou le même paquetage.

   Tout le reste (méthode, propriété `${…}`, constante d'un type absent) reste non résolu : l'analyseur
   rend le texte tel qu'écrit, jamais une supposition.
4. **Un endpoint est un fait `OBSERVED`** : `endpoint:<VERBE> <chemin>` `HANDLED_BY`
   `symbol:java:<type qualifié>#<méthode>`. Il a deux preuves à la ligne, avec leur empreinte : le mapping
   du contrôleur et celui de la méthode. Le chemin est combiné comme Spring le fait (un seul `/` entre les
   parties, `/` en tête, `/` final gardé). `@RequestMapping` sans `method` donne le verbe `ANY` : il
   accepte tous les verbes, et Taxo n'en choisit pas un.
5. **Jamais une fausse absence.** Sont déclarés `NOT_INTERPRETED`, avec pour périmètre le fichier qui
   les porte :
   - un mapping non résolu (sur la méthode, ou sur le contrôleur entier) ;
   - un mapping porté par un type qui n'est pas un contrôleur (interface, classe de base) ;
   - un contrôleur qui hérite d'un type absent des sources, comme une interface générée au build depuis
     une spécification OpenAPI, ou d'un type porteur de mappings ;
   - un fichier en erreur de syntaxe.

   Dans tous ces cas, ses propres mappings restent des faits. Un fichier illisible (trop gros, non UTF-8)
   est `READ_ERROR`. S'il y a une zone non interprétée, l'exécution est `PARTIAL`.
6. **Périmètre déclaré.** La couverture `ANALYSED` du dépôt exclut les sources de test (`src/test`) et
   les sorties de build (`build`, `target`, `out`…), nommées dans `scope.exclude`. Sur un dépôt sans
   Java, l'évaluateur a cherché et n'a trouvé aucun endpoint Spring : `ANALYSED`, sans fait. Une
   affirmation de Minia sur un endpoint y reste « non trouvé dans le périmètre analysé », jamais « faux »
   (ADR 0009).

## Conséquences

- Les endpoints entrent dans tout ce qui consomme les faits sans qu'aucun consommateur ne change :
  - l'analyse globale ;
  - l'impact d'un commit (endpoint introduit, retiré, ou traité par une autre méthode : `MODIFIED`) ;
  - le protocole `taxo-query/1` (`find_facts`, `verify_claim`, `diff_facts`) ;
  - Minia.
- Pas de résolution de types au-delà du dépôt, ni d'appels (`CALLS`, `DISPATCHES_TO`) : ils viendront
  avec TAXO-03 étendu et 01H.
- Hors de cette version :
  - méta-annotations (`@MaRoute` portant `@GetMapping`) ;
  - routes fonctionnelles (`RouterFunction`) ;
  - Kotlin ;
  - `params`, `headers`, `consumes`, `produces` (un même chemin traité par deux méthodes donne deux faits).

  Une route écrite ainsi n'est pas vue : c'est la limite connue du périmètre `ANALYSED`, à lever par les
  prochaines versions de l'évaluateur.
- Validé sur deux projets Spring publics :
  - `spring-petclinic` : 17 endpoints, `SUCCESS` ;
  - `spring-petclinic-rest` : 1 endpoint, et ses 9 contrôleurs générés depuis OpenAPI déclarés
    `NOT_INTERPRETED` au lieu d'une API déclarée vide.
