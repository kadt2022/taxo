# Rapport S3 — Les imports dans les tuiles (TAKIBO)

**Statut :** MESURÉ — avant / après sur les mêmes 25 méthodes que S0 (414 symboles après les corrections de revue de la PR 175)
**Date :** 2026-10-18 · **Lot :** S3 du récit « TAXO — Contrat de suffisance structurelle des tuiles » · **Auteur :** le monstre des mers
**Portée :** les tuiles de Minia. Aucune modification du contrat MIP ni des opérations du protocole, aucun autre analyseur.

## 1. Ce qui change

- **La tuile d'une méthode porte ses imports** : `imports: [{line, text}]`, les lignes du fichier telles qu'écrites, avec leur
  numéro. Ce sont les imports dont le **nom simple est utilisé** dans la tuile (méthode, champs, en-tête de classe) ; les
  **imports avec joker** sont toujours joints et marqués `wildcard`, car ils ne disent pas quel type est utilisé.
- **Un import n'est qu'un nom écrit.** Il donne le nom complet d'un type ; il ne le résout pas. La tuile garde les deux
  distincts, et ne rattache jamais un type à un joker.
- **Pas de recopie** : un import déjà donné pour un fichier dans l'échange n'est pas redonné ; la tuile d'une autre méthode du même
  fichier ne porte que les imports nouveaux. Une `imports_scope` par réponse dit une fois ce que les imports couvrent : un type sans
  import ici est du même paquet, de `java.lang`, d'un paquet importé avec joker, ou non cité dans cette tuile.
- **Lecture** : `SourceOperation.imports` lit le fichier au même titre que `get_source` (même consentement, même commit, mêmes refus).
  Ce n'est pas une opération du protocole : rien n'est ajouté au contrat. Un fichier illisible est dit (`not_sent`,
  `limits.unavailable_imports`), jamais tu, et la tuile part sans ses imports.
- **Le modèle** reçoit une section `--- imports (fichier) ---` avec le code des lignes, et la note de portée une fois par réponse.

## 2. Mesure avant / après (TAKIBO, 25 méthodes, 20 tuiles, 414 symboles)

| Configuration | Portés par la tuile | Identifiés par la tuile | Avec la règle du langage | Avec les liens connus | Non résolus |
|---|---|---|---|---|---|
| Lot S0 : tuile sans imports, règles du lot S0 | 29,5 % (122) | 29,5 % (122) | 29,5 % | 42,8 % | 237 |
| **Tuile avec imports, règles du lot S0** | 29,5 % (122) | **44,7 %** (185) | 44,7 % | **58,0 %** | 174 |
| Tuile sans imports, outil corrigé | 30,4 % (126) | 30,4 % (126) | 37,2 % | 50,5 % | 205 |
| Tuile avec imports, outil corrigé | 30,4 % (126) | **46,6 %** (193) | 53,4 % | **66,7 %** | 138 |

« Identifiés par la tuile » = portés, ou nom complet donné par un import. « Règle du langage » ajoute les types de `java.lang`, visibles
sans import. « Liens connus » ajoute ce que Taxo relie sans que la tuile le porte.

### 2.1 Les vraies améliorations, séparées des biais de l'outil

| Source | Effet | Nature |
|---|---|---|
| **Imports dans la tuile** | **+63 symboles, +15,2 points** (identifiés, avec ou sans les liens) | amélioration de la tuile, mesurée |
| Champ `log` déclaré par `@Slf4j` (annotation dans l'en-tête de la tuile) | +4 symboles portés, +1,0 point | correction de l'outil : la tuile portait déjà l'annotation |
| Types de `java.lang` | +28 symboles, +6,8 points | règle du langage de l'outil, pas un contenu de tuile |
| `UUID` et noms en majuscules écrits comme des types | reclassés de « constante » à « type » ; identifiés quand un import les nomme | correction de l'outil |

Les 63 types identifiés par un import sont exactement les 63 que l'estimation de S0 attribuait aux imports simples. L'estimation de S0
(51 % et 65 % après recalcul, bornes hautes) mettait aussi les 28 types de `java.lang` sur le compte des imports : ils ne sont pas
importés. Mesuré : **53,4 %** avec la règle du langage et **66,7 %** avec les liens, soit 2 points et 2 points au-dessus de ces
estimations : la correction de l'outil ajoute aussi les 4 champs `log` et reclasse en types, identifiés par leur import, des noms comme
`UUID` que S0 comptait parmi les constantes.

### 2.2 Les types et les jokers

125 symboles sont des types. 63 sont identifiés par un import. **Un seul** reste non résolu alors qu'un import avec joker est présent :
la tuile le dit (« joker présent, paquets candidats : … ») sans en choisir un. Aucune résolution n'est inventée.

## 3. Coût

- Tuiles construites chacune seule : les imports ajoutent **6 723 octets** aux 22 685 octets de ces 20 tuiles (**29,6 %**). L'échantillon est
  fait de petites tuiles (environ 1,1 Ko) : la part des imports y est élevée.
- **Déduplication** : sur les 11 méthodes lues dans l'essai 3 (dont six de `PolicyEvaluator`), les tuiles portent **2 490 octets
  d'imports au lieu de 4 633** (46 % de moins). Un fichier dont plusieurs méthodes sont lues ne redonne jamais le même import.
- Sur l'échantillon de 20 méthodes de classes différentes, la déduplication n'a rien à retirer (6 723 octets dans les deux cas) : son
  effet dépend du nombre de méthodes lues par fichier.

## 4. Les cinq conditions du Capitaine Pi

1. **Imports exacts, type importé distinct de type résolu** : les lignes sont transmises telles qu'écrites avec leur numéro ; l'état
   « identifié par un import » est distinct de « porté par la tuile » dans la mesure.
2. **Aucune résolution inventée pour un joker** : marqués `wildcard`, jamais rattachés à un type ; le seul cas ambigu est dit.
3. **Pas de recopie inutile** : déduplication par fichier et par échange (−46 % sur le scénario de l'essai 3).
4. **Même mesure avant / après** : mêmes 25 méthodes, 414 symboles ; la configuration du lot S0 est reproduite (29,5 % /
   42,8 %, recalculés avec l'outil corrigé).
5. **Aucun contrat MIP ni autre analyseur modifié** : la lecture est une méthode interne, pas une opération du protocole.

## 5. Tests

- Domaine : extraction des lignes d'import (commentaires de ligne et de bloc ignorés, texte exact conservé), arrêt avant la déclaration.
- Tuile : sélection par nom entier, jokers marqués, déduplication par fichier, tuile relue sans import redonné, fichier illisible dit
  sans perdre le code, rendu pour le modèle (du code seulement, note de portée une fois). **Les 7 tests échouent sur l'ancien code.**
- Outil de mesure : états « importé », « règle du langage », champ `log` généré, joker, quatre mesures, noms en majuscules.
- Remarques de revue de la PR 176 : un import après un commentaire fermé sur sa ligne (`/* note */ import a.B;`) reste un import, et son
  texte est celui de l'import sans ses commentaires ; un échec de lecture des imports est dit au modèle (« Imports non lus »), pour un
  chemin comme pour une lecture de tuiles.
- Sept budgets d'octets de `test_minia_target.py` passent de 2 500 à 3 000 : ces tests fixent un budget pour que seule la première
  tuile tienne ; les imports alourdissent la tuile, le comportement attendu est inchangé (35 tests passent avec 3 000).

## 6. Limites

- **Analyse lexicale approchée** (voir le rapport S0) : un import est joint dès que son nom apparaît dans le texte de la tuile, y
  compris dans un commentaire, ce qui peut en joindre un de trop sans rien faire perdre.
- **Les imports n'identifient pas les appels sur types externes** : 138 symboles restent non résolus, surtout des membres et des appels
  (`warn`, `map`, `doFilter`…) dont le receveur n'est pas typé. C'est le lot S6 et la règle `frontier-classification/2`.
- **Trois noms de constantes** (`TOKEN_ENDPOINT`…) restent classés « membre » : sans import qui les nomme, le texte ne dit pas que ce
  sont des constantes d'un autre type.
- **L'Explorer** n'est pas concerné : sa tuile passe par `get_source`, dont le contrat n'a pas changé. Montrer les imports à un humain
  passe par une décision séparée (ADR).
- Un projet, un commit, un échantillon déterministe. La durée de l'analyse (125 à 190 s selon les exécutions) n'est pas un résultat.

## 7. Suite

Les lots S1, S2, S4, S5 et S6 attendent chacun l'autorisation du Capitaine Pi. Les nombres 53,4 % et 66,7 % sont mesurés sur ces 25
méthodes ; ils ne sont pas une performance générale de Taxo.
