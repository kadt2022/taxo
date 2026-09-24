# TAXO-LAB-01 — Capacité statistique sur mémoire structurée

Statut : rédigé le 2026-09-23, **non ouvert**. Fiche d'abord, code ensuite : aucune ligne
d'expérience n'est écrite avant que les hypothèses, les métriques et les seuils ci-dessous soient
validés puis figés. L'épique TAXO-01 reste prioritaire.

Source de vérité : cette fiche. Elle applique le [manifeste](../manifeste.md) à une question de
recherche : ce qui est mesuré est dit mesuré, ce qui est supposé est dit supposé.

Dépend de : TAXO-POC-01 (chaîne d'autorisation, `anyRequest()` compris) ; ADR 0006 (l'hypothèse
statistique n'est pas un fait).

## Question

> Quelle capacité supplémentaire un modèle statistique apporte-t-il lorsqu'il dispose d'une
> représentation logicielle explicite, vérifiable et structurée ?

Il ne s'agit pas de démontrer qu'un système est « intelligent ». Il s'agit de mesurer une capacité
précise, et le nombre de paramètres et d'exemples nécessaires pour l'obtenir, selon que le modèle
reçoit la représentation de Taxo ou le code brut.

## Capacité étudiée

Pour chaque endpoint HTTP d'une application Spring : **qui peut réellement l'appeler ?** Classes
d'étiquettes : `PUBLIC`, `AUTHENTICATED_ONLY`, `RESTRICTED` (rôle, propriétaire ou politique), plus
une conclusion dérivée « écriture moins protégée que la lecture de la même ressource ».

## Hypothèses préenregistrées

Les seuils marqués « proposé » sont validés par le porteur du projet puis **figés avant le premier
entraînement**. Une hypothèse réfutée est publiée comme telle.

**H1 — Représentation structurée.** À budget d'entraînement égal (mêmes exemples, même nombre de
paramètres, même effort de réglage), un petit modèle recevant la représentation de Taxo généralise
mieux sur les familles de validation jamais vues qu'un modèle de même taille recevant le code brut.
Mesure : F1 macro, courbes en fonction des paramètres **et** du nombre d'exemples.
Proposé : B atteint le F1 de C avec au moins 10 fois moins de paramètres ou d'exemples.

**H2 — Complémentarité.** Sur les cas où l'analyse déterministe (A) s'abstient, l'ajout du petit
modèle augmente la part de cas décidés sans que le taux de conclusions incorrectes parmi les cas
nouvellement décidés dépasse un seuil. Proposé : au moins 30 % des abstentions de A décidées,
au plus 2 % de conclusions incorrectes parmi elles.

**H3 — Vérification.** Soumettre les hypothèses du modèle à un vérificateur donne une meilleure
précision que la prédiction directe du modèle. Pour ne pas être tautologique, le vérificateur de H3
**n'est pas** la source des étiquettes de test : c'est un oracle partiel et coûteux (un nombre fixé
d'appels). Mesure : à budget d'oracle fixé, précision et nombre de failles confirmées quand le modèle
choisit les cas à vérifier, comparés à un ordre aléatoire et à l'ordre de A.

**H4 — Ignorance.** Un modèle qui s'abstient correctement est préférable à un modèle qui maximise
le rappel au prix de conclusions non vérifiées. Pour être réfutable, « préférable » est défini par
une **matrice de coûts préenregistrée** : proposé, conclusion incorrecte = 10, abstention = 1,
conclusion correcte = 0. Mesure : coût moyen, courbe risque-couverture, calibration (ECE). H4 est
réfutée si un modèle sans abstention obtient un coût moyen inférieur.

## Variantes comparées

| Variante | Chaîne | Rôle |
| --- | --- | --- |
| A — déterministe | code → Taxo → conclusion ou abstention | référence ; définit les cas de H2 |
| B — petit modèle + Taxo | code → Taxo → représentation → modèle → `Hypothesis` → vérificateur | variable étudiée |
| C — petit modèle sans Taxo | code → modèle → conclusion | témoin de H1 |
| D — LLM + Taxo | code → Taxo → contexte → LLM | comparaison avec les approches actuelles, **après** A, B, C |

Bases triviales obligatoires : classe majoritaire, et une règle écrite à la main en moins de
20 lignes. Si l'une égale B, B n'apporte rien et c'est le résultat.

Tailles : au moins cinq tailles par variante statistique, espacées d'un facteur 10 (de l'ordre de
10³ à 10⁷ paramètres). Chaque point est la moyenne d'au moins trois graines, avec son écart.

## Règle anti-tautologie

La représentation donnée à B ne contient **jamais** l'étiquette ni un fait qui la détermine à lui seul
(par exemple `MATCHED_BY anyRequest` + `authenticated` pour `AUTHENTICATED_ONLY`). Deux régimes
sont mesurés et publiés séparément :

1. **cas décidables par A** : B ne fait que relire A ; ce régime sert de contrôle, pas de preuve ;
2. **cas où A s'abstient** (règle illisible, constante de motifs, plusieurs `SecurityFilterChain`,
   `securityMatcher`, héritage, méthode `@PreAuthorize`) : seul ce régime compte pour H1 et H2.

## Oracles et étiquettes

Trois sources, jamais confondues, chacune inscrite dans l'étiquette :

| Source | Ce qu'elle établit | Usage |
| --- | --- | --- |
| oracle dynamique | comportement observé : l'application démarrée reçoit des requêtes anonymes, client, propriétaire, admin ; on relève 2xx, 401, 403 | étiquette principale |
| oracle statique | propriété déduite du code par un analyseur indépendant de Taxo | contrôle ; jamais seule source d'une étiquette de test |
| vérité de référence | étiquette établie à la main, avec preuve citée, avant tout modèle | cas que l'oracle dynamique ne sait pas reproduire (état difficile, données de politique) |

Un cas sans étiquette sûre est **exclu et compté**, pas étiqueté au mieux.

## Données et découpage

```text
familles artificielles       → entraînement
familles artificielles       → validation   (familles jamais vues, séparation par famille)
TAKIBO réel                  → test final   (jamais vu, jamais utilisé pour régler)
```

- une famille est un gabarit de configuration (ordre des règles, `anyRequest`, plusieurs chaînes,
  `securityMatcher`, héritage, rôles, politique déléguée…) ; la séparation se fait par famille, jamais
  au hasard ;
- les familles sont écrites à partir de la documentation Spring Security, pas de TAKIBO ; la fiche des
  familles note leur origine, pour détecter une fuite par le concepteur ;
- le test final est lancé **une seule fois** par variante, après gel des modèles.

## Décision préalable : l'hypothèse n'est pas un fait

Tranchée par l'[ADR 0006](../adr/0006-hypothese-statistique.md) (proposé) : une prédiction de modèle
est une `Hypothesis`, objet distinct du fait. Le contrat v1 ne change pas. Une hypothèse n'est jamais
une prémisse ; seul un vérificateur produit un fait, sous sa propre provenance ; les hypothèses
rejetées restent dans le journal des hypothèses.

Pendant LAB-01, les hypothèses vivent dans l'espace de l'expérience et n'entrent pas dans la mémoire
de Taxo. Les modèles expérimentaux sont entraînés à partir de zéro ; un modèle pré-entraîné
(SmolLM2-135M) n'est ajouté qu'ensuite, comme point de comparaison, derrière le même port.

## Ce que LAB-01 ne tranche pas

LAB-01 répond à une seule question : **un modèle statistique ajoute-t-il une capacité** à la mémoire
vérifiée ? Il ne dit pas si la boucle observer, vérifier, historiser apporte de la valeur. Cette boucle
se construit sans modèle : comparaison d'instantanés (01F), contraintes explicites, oracle dynamique,
journal des vérifications. L'endpoint oublié du POC-01 a été détecté par une règle déterministe.

Un résultat nul de LAB-01 signifie donc, pour ce domaine, que la valeur vient de la mémoire et de la
vérification, pas de la statistique. Il ne remet pas en cause la boucle.

LAB-01 est **hors ligne** : les modèles sont entraînés puis gelés. Un modèle qui apprend en continu
de ses propres vérifications (sentinelle adaptative) relève d'une expérience ultérieure, ouverte
seulement si LAB-01 conclut positivement, et sous trois garde-fous posés dès maintenant :

1. **La sentinelle n'agit que sur sa connaissance** : vérifier, interroger un oracle, alerter. Elle ne
   modifie jamais le logiciel surveillé.
2. **Un échantillon d'audit tiré au hasard** est vérifié indépendamment des choix du modèle. Sans lui,
   le modèle n'apprend et n'est mesuré que là où il a choisi de regarder, et une dérive reste invisible.
3. **Une nouvelle version du modèle ne remplace l'ancienne** qu'après avoir fait au moins aussi bien
   sur un banc figé, jamais sur ses propres données récentes. Chaque version est enregistrée
   (ADR 0006, champ `model`).

## Acceptation

1. Hypothèses, matrice de coûts, seuils et découpage figés et datés dans cette fiche avant le premier
   entraînement.
2. Les quatre hypothèses reçoivent un verdict (confirmée, réfutée, non concluante) avec intervalles
   de confiance ; le petit nombre d'endpoints de TAKIBO est déclaré dans le résultat.
3. Les deux régimes de la règle anti-tautologie sont publiés séparément.
4. Chaque étiquette porte sa source ; les cas exclus sont comptés.
5. Le banc est versionné dans le dépôt et rejouable : données, graines, versions, tailles de modèles.

## Hors périmètre

Toute intégration de modèle dans le produit Taxo ; tout LLM avant la fin de A, B, C ; toute
généralisation au-delà de Spring Security et de TAKIBO. Un résultat positif ici vaut pour ce
domaine : ce sera une première mesure, pas une loi.
