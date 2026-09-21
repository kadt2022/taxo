# Note — Capacité générative et probabilité

*Rédigée le 2026-09-21. Note d'analyse : elle n'acte aucune décision. Si l'une de ses
conséquences est retenue, elle devra être versée dans un ADR et mesurée.*

## La question

> Peut-on obtenir une capacité générative **générale** en faisant évoluer des états structurés
> selon des règles, tout en utilisant la probabilité **uniquement** comme mécanisme de sélection
> et d'incertitude ?

Elle concerne directement Taxo : le dépôt est déjà une instance stricte de cette architecture.
Un Fait est un état structuré, un évaluateur est une règle d'observation, une dérivation est une
règle d'inférence citée par nom et par version, et **aucune probabilité n'apparaît nulle part**.
La question revient donc à demander jusqu'où cette discipline peut porter.

## Réponse courte

Trois réponses selon le sens donné à « générale ».

| Sens de « capacité générative générale » | Réponse |
| --- | --- |
| **Expressivité** : produire n'importe quelle structure calculable | **Oui**, et c'est acquis depuis les années 1930. Sans intérêt pour la question posée. |
| **Généralité dans un domaine dont les règles sont connaissables** (jeux, mathématiques formelles, sémantique d'un langage, synthèse de programmes) | **Oui**, et souvent *mieux* qu'une approche probabiliste, parce que la sortie est vérifiable par construction. |
| **Généralité en domaine ouvert** (langue naturelle, monde réel, queue longue) | **Non**, sauf à relâcher la contrainte sur la probabilité — et le relâchement nécessaire est exactement celui qui fait cesser à la probabilité d'être « seulement » un sélecteur. |

La suite explique pourquoi la frontière tombe là, et non ailleurs.

## 1. L'expressivité n'a jamais été le problème

Faire évoluer des états structurés selon des règles est Turing-complet sous à peu près toutes ses
formes : systèmes de Post, réécriture de termes, grammaires de graphes, algorithmes de Markov,
automates cellulaires (la règle 110 suffit). L'ensemble des structures atteignables est donc, en
principe, tout ce qui est calculable.

Il faut le dire une fois pour l'écarter : **toute objection sérieuse à la thèse ne porte pas sur ce
que le système *peut* produire, mais sur la probabilité qu'il le produise dans un budget fini.**

## 2. L'argument du support : ce que la probabilité-sélection ne peut pas faire

Soit `s₀` l'état initial, `R` l'ensemble des règles, et `clôture_R(s₀)` l'ensemble des états
atteignables. Une politique probabiliste `π` choisit, à chaque pas, quelle règle appliquer.

```text
support( sorties(π, R, s₀) )  ⊆  clôture_R(s₀)      pour toute π
```

Une loi de probabilité sur les applications de règles **redistribue la masse** sur les états
atteignables. Elle n'en ajoute jamais un seul. Même chose pour la probabilité-incertitude : une
croyance est une mesure sur le même ensemble d'états ; représenter « je ne sais pas lequel » ne
crée pas un état que les règles ne construisaient pas.

Conséquence directe, et c'est le cœur de la réponse :

> **Sous la contrainte posée, la généralité du système est exactement la généralité de `R`.**
> La probabilité ne peut pas la réparer, parce que sa seule prise est la mesure, jamais le support.

Une politique ne peut élargir le support que si elle est autorisée à *proposer* des transitions
absentes de `R`. Ce n'est plus un sélecteur : c'est un générateur. La question contient donc sa
propre frontière.

## 3. Le vrai débat porte sur la mesure, pas sur le support

L'argument du §2 admet une échappatoire immédiate : prendre pour `R` les règles d'une machine
universelle. La clôture devient alors tout le calculable, et la contrainte d'expressivité
disparaît. Ce que l'on obtient est l'induction de Solomonoff, incalculable, dont les approximations
(recherche de Levin, énumération de programmes) sont exponentielles.

Autrement dit :

> **La généralité n'est pas une propriété de la clôture. C'est une propriété de la mesure sur la
> clôture.** Un système est généralement génératif quand les structures utiles y ont une
> probabilité atteignable dans un budget fini.

Ce déplacement recadre tout. Un grand modèle de langage n'est pas « plus expressif » qu'un système
de règles ; il porte une mesure apprise, continue, sur un espace ouvert. C'est là qu'est sa
généralité — pas dans son expressivité.

## 4. Le trilemme

Trois voies seulement, pour une générativité en domaine ouvert avec des états structurés :

1. **Écrire `R` en entier.** Le pari de Cyc, tenu depuis plus de quarante ans, avec des millions
   d'assertions. Il bute sur le goulot d'acquisition des connaissances (Feigenbaum) et sur la
   fragilité aux bords du domaine. Les problèmes du cadre et de la qualification (McCarthy et
   Hayes) disent pourquoi : les préconditions d'une règle ne sont pas énumérables dans un monde
   ouvert. Les logiques non monotones atténuent, elles ne suppriment pas.
2. **Des règles qui produisent des règles**, avec une sélection fixée à la main. Formellement
   possible : AM puis EURISKO (Lenat) ont réellement découvert des concepts, puis se sont arrêtés
   sur le mur des « heuristiques d'heuristiques ». La programmation logique inductive bute depuis
   trente ans sur l'invention de prédicats — c'est-à-dire sur la création de vocabulaire neuf, qui
   est précisément ce que demande un domaine ouvert. La recherche devient intraitable avant d'être
   incorrecte.
3. **Un sélecteur appris.** Cela marche, remarquablement. Mais la probabilité a alors cessé d'être
   un sélecteur : elle est devenue le mécanisme de généralisation, puisque c'est elle qui attribue
   une masse à des configurations jamais vues. La contrainte de l'énoncé est violée — discrètement,
   mais entièrement.

Aucune quatrième voie connue. La thèse tient donc si et seulement si on accepte de restreindre le
domaine.

## 5. Ce que montrent les systèmes réels

La restriction au domaine fermé n'est pas une consolation : c'est là que l'architecture est
**supérieure** aux approches purement probabilistes, parce que la sortie est vérifiable par
construction.

| Système | Règles | Rôle de la probabilité | Portée obtenue |
| --- | --- | --- | --- |
| AlphaZero / MuZero | coups légaux | priors et échantillonnage dans l'arbre | générativité réelle, créative (le coup 37), **dans un domaine entièrement clos** |
| Démonstrateurs automatiques, SMT | règles d'inférence | heuristique de branchement | preuves neuves, vérifiables |
| Systèmes L, grammaires de formes, *wave function collapse* | réécriture | choix de production | générativité riche, domaine fermé par construction |
| Apprentissage bayésien de programmes (Lake, Salakhutdinov, Tenenbaum) | programmes structurés | prior **et** postérieur sur les programmes | génération d'un caractère nouveau après un seul exemple |
| AlphaGeometry | moteur déductif fermé | un modèle propose les constructions auxiliaires | le moteur seul plafonne ; le modèle le fait franchir le palier |

Les deux dernières lignes sont les plus instructives, parce qu'elles trichent avec l'énoncé et que
la triche est le résultat.

L'apprentissage bayésien de programmes place la probabilité sur *l'espace des règles elles-mêmes* :
ce n'est plus de la sélection, c'est de l'acquisition. Et AlphaGeometry montre le partage à l'état
pur : les constructions auxiliaires que le modèle propose appartiennent déjà au langage du moteur —
le modèle n'ajoute **aucune expressivité**, il ne fait que déplacer la masse de probabilité dans un
branchement infini. C'est exactement le §3, mesuré sur un banc réel.

## 6. Où se situe Taxo

Taxo a déjà tranché, et du bon côté pour ce qu'il fait.

- **L'état structuré** est le Fait : entités typées, relations d'un vocabulaire v1 fermé
  (`backend/app/facts/domain/fact.py`), instantané, provenance.
- **Les règles d'observation** sont les évaluateurs, versionnés, à catalogue déclaré.
- **Les règles d'inférence** sont explicites et citées : le contrat impose à tout fait `INFERRED`
  un bloc `derivation` avec `premises`, `rule`, `counter_examples_checked` et `known_gaps`
  (`contract-v1.schema.json`). `MATCHED_BY` + `AUTHORIZED_BY` → `PROTECTED_BY`, jamais depuis
  `HANDLED_BY` : TAXO-POC-01 est une règle d'inférence écrite avant son implémentation.
- **La probabilité est absente**, et l'absence est délibérée : « ces statuts ne sont pas des scores
  de confiance » (manifeste §4.2).

Deux observations, dont la seconde est un résultat et pas seulement un choix de style.

**Taxo est l'aveu assumé du §4.1.** « Il n'existe pas d'évaluateur universel » (manifeste §7) est
la reconnaissance du goulot d'acquisition. Un évaluateur par framework, par version. La parade du
dépôt n'est pas technique, elle est économique : le critère du **fait cher** — « trois lignes de
shell donnent-elles le même résultat avec la même signification ? » — choisit *quelles parties du
domaine méritent d'être fermées*. C'est, à ma connaissance, la meilleure réponse praticable au
goulot : renoncer à la couverture générale, et acheter la clôture seulement là où elle se rentabilise.

**La représentation catégorielle de l'incertitude est strictement plus informative qu'un scalaire.**
C'est le point que la question mérite le plus. Un système qui utilise la probabilité comme
mécanisme d'incertitude répondrait `P(absence) = 0,7`. Taxo distingue trois choses que ce nombre
écrase (TAXO-01I) :

```text
ABSENCE couverte   j'ai cherché dans un périmètre adéquat, il n'y a rien
NOT_INTERPRETED    le mécanisme existe, je ne sais pas le lire
UNKNOWN            aucune capacité n'a travaillé sur cette question
```

Les trois peuvent porter la même probabilité et n'ont pas la même conséquence : la première autorise
à signer, la deuxième désigne où lire le code, la troisième interdit de conclure. Sur l'usage d'audit
qui est celui de Taxo, **passer à la probabilité serait une perte d'information, pas un gain de
nuance.** C'est un contre-exemple net à l'idée que la probabilité-incertitude est toujours un
enrichissement.

## 7. Conséquences proposées pour Taxo

Elles découlent de l'analyse ; elles ne sont pas décidées ici.

1. **Aucun score de confiance sur un Fait, jamais.** Un `P` sur un fait détruirait la distinction du
   §6 et rendrait la réfutabilité inopérante : on ne réfute pas 0,7.
2. **La probabilité est légitime à un seul endroit : la sélection de ce qu'on envoie.** Classer les
   tuiles d'un `ContextSelection`, ordonner un parcours de voisinage — là, une heuristique, même
   apprise, ne change *que ce qui est montré*, jamais *ce qui est vrai*. Frontière actionnable :
   **la probabilité peut ordonner des tuiles ; elle ne peut ni créer ni annoter un Fait.**
3. **La générativité ouverte reste dehors, et c'est cohérent.** ADR 0005 fixe
   `Code → Facts → Tuiles → Contexte → LLM` et interdit l'inversion. L'analyse ci-dessus confirme
   ce choix : la seule architecture qui obtient une générativité ouverte *sans* laisser la
   probabilité entrer dans l'état est **proposer-puis-vérifier**, avec une frontière de confiance
   asymétrique.
4. **Proposer-puis-vérifier n'inverse pas le sens de dérivation** — à une condition de forme. Si le
   LLM propose une chaîne candidate et que celle-ci rentre comme **question** adressée à un
   évaluateur, qui la confirme avec preuve et couverture ou la refuse, alors rien de probabiliste
   n'entre en mémoire : seul le verdict déductif y entre. C'est l'architecture d'AlphaGeometry, et
   c'est compatible avec l'interdiction de l'ADR 0005, qui porte sur les *résumés* entrant comme
   faits, pas sur les *hypothèses* entrant comme requêtes. La distinction mérite d'être écrite
   explicitement dans l'ADR, car elle est aujourd'hui implicite et un lecteur pressé lira
   l'interdiction comme fermant aussi cette boucle.

## 8. Comment nous saurons que cette note est fausse

- Si un système purement à règles, **sans prior appris**, atteint une robustesse de domaine ouvert
  sur un banc à queue longue, le §4 est faux et le trilemme n'en est pas un.
- Si l'invention de prédicats devient traitable à l'échelle, la voie 2 du trilemme rouvre et la
  réponse en domaine ouvert passe à « oui ».
- Pour Taxo, la prédiction est mesurable : **si le coût marginal d'un nouvel évaluateur ne décroît
  pas** à mesure que les primitives s'accumulent (TAXO-03 puis 04 puis 05), la clôture ne passera
  pas à l'échelle des frameworks réels, et le critère du fait cher devra devenir plus sélectif
  encore, pas moins.

## Conclusion

Oui pour tout domaine dont vous pouvez fermer les règles — et dans ce cas, mieux qu'une approche
probabiliste, puisque la sortie est vérifiable. Non en domaine ouvert, et ce non ne tient pas à un
manque d'expressivité : il tient à ce qu'aucune mesure fixée à la main ne rend les structures utiles
atteignables dans un budget fini.

> **La probabilité-sélection redistribue la masse ; elle n'élargit pas le support.
> La généralité est une propriété de la mesure, et une mesure générale s'apprend.**

Taxo n'a pas à trancher ce débat. Il a à ne pas se tromper de côté : son état reste déductivement
clos et réfutable, et la générativité ouverte reste chez le consommateur, qui propose et
n'établit jamais.
