# Banc TAXO-POC-01 — résultats de la baseline

*Six exécutions du 2026-09-19, ordre `A1 B1 A2 B2 A3 B3`, sessions fraîches, même modèle
(Opus 5, configuration par défaut — le niveau d'effort n'était pas réglable), même commit
`032788fb6d`, mêmes douze questions.*

## Corrections apportées à la vérité de référence

Trois réponses de référence étaient fausses ou imprécises. Elles sont corrigées **en citant le
code**, et la correction est notée ici comme la doctrine l'exige. Les six runs avaient répondu
avant que ces corrections soient écrites ; aucune question n'a été modifiée.

| Question | Étalon initial | Correction, et la preuve |
| --- | --- | --- |
| **Q2** rôles exigés | « hors périmètre : donnée de politique, pas de code » | **Faux.** `PolicyEvaluator.java:111-117` teste quatre codes en dur (`PLATFORM_ADMIN`, `ORG_OWNER`, `ORG_ADMIN`, `SPACE_ADMIN`) et `:256-262` refuse la surface users sans ce statut. Les rôles **sont** dans le code. |
| **Q10** `/api/public/info` | « indécidable : deux chaînes candidates » valait +2 | **Faux.** `takibo-adp-test/build.gradle:8` ne dépend que de `takibo-adp-spring` : `SecurityConfig` n'est pas sur son classpath. La question est décidable, et refuser de conclure est une fausse absence. |
| **Q12** applications | « deux » | **Incomplet.** Deux applications Spring Boot, plus `takibo-install-keys`, jar CLI exécutable (`build.gradle:2` `java-library`, `:33` `Main-Class`). Trois livrables, deux applications web. |

La première correction est la plus lourde de conséquences : **la couverture `OUT_OF_SCOPE` que le
POC produit sur les rôles est une fausse absence**, pas une limite honnête.

## Mesures brutes

| Run | Durée | Tokens | Appels d'outil | Points | Fausses affirmations | Fausses absences |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | 343,6 s | 135 171 | 34 | 24 / 24 | 0 | 0 |
| B1 | 340,7 s | 157 282 | 28 | 24 / 24 | 0 | 0 |
| A2 | 395,0 s | 152 612 | 37 | 24 / 24 | 0 | 0 |
| B2 | 418,3 s | 163 977 | 30 | 24 / 24 | 0 | 0 |
| A3 | 345,0 s | 144 598 | 50 | 24 / 24 | 0 | 0 |
| B3 | 365,2 s | 146 453 | 25 | 24 / 24 | 0 | 0 |

| Moyenne | Durée | Tokens | Appels d'outil | Points |
| --- | --- | --- | --- | --- |
| **A — agent seul** | 361,2 s | 144 127 | 40,3 | 24 / 24 |
| **B — agent + Taxo** | 374,7 s | 155 904 | 27,7 | 24 / 24 |
| **Écart B − A** | **+3,7 %** | **+8,2 %** | **−31,3 %** | **0** |

## Règle éliminatoire

> Si le bras B produit davantage de fausses affirmations que le bras A, POC-01 échoue.

**Zéro fausse affirmation des deux côtés.** La règle éliminatoire ne se déclenche pas. Elle ne
départage rien non plus.

## Verdict

**Aucun gain mesurable.** Les six exécutions répondent correctement aux douze questions, avec des
preuves valides, avec ou sans les faits de Taxo. Le banc a saturé : à ce niveau de difficulté, avec
ce modèle et ce dépôt, lire le code suffit.

Ce que les faits ont changé, en revanche, est mesurable et va dans les deux sens :

- **−31 % d'appels d'outil.** Les sessions B ont beaucoup moins exploré : les faits leur ont donné
  d'emblée les fichiers et les lignes utiles.
- **+8 % de tokens.** Lire le bundle coûte plus cher que l'exploration qu'il économise.
- **Trois faits à corriger par run.** Les trois sessions B ont dû contredire le bundle : l'`ABSENCE`
  sur `OrgBoundaryFilter`, énoncée comme « le filtre ne s'applique pas » alors qu'il est monté sur
  la chaîne et simplement inerte ; et les deux « aucune conclusion » de `r06` et `r07`, décidables
  par le graphe Gradle. B2 a en outre relevé que la couverture déclarant que la décision ne vient
  pas du code est fausse.

## Ce que le POC aurait répondu seul

En notant le bundle gelé comme s'il était le répondant, contre la vérité de référence corrigée :

| | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 | Q9 | Q10 | Q11 | Q12 | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| POC-01 seul | 2 | 0 | 1 | 2 | 2 | 2 | 2 | 2 | 1 | 0 | 0 | 0 | **14 / 24** |
| Agent, les deux bras | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | **24 / 24** |

Le POC perd ses points là où il est aveugle aux unités déployables (Q9 partiel, Q10, Q11, Q12) et
là où il déclare hors périmètre ce que le code décide (Q2).

## Ce que ce résultat autorise à dire, et ce qu'il n'autorise pas

Il autorise à dire que **sur ces douze questions, avec ce modèle, les faits de Taxo n'ont pas rendu
l'agent plus exact**. Ils l'ont rendu moins bavard en outils et un peu plus cher en tokens.

Il n'autorise pas à conclure que Taxo est inutile :

- le banc a saturé, donc il ne mesure pas l'écart, il mesure un plafond. Il faudrait des questions
  plus dures, un dépôt plus grand, ou un modèle plus faible pour que l'écart devienne visible ;
- aucune des questions ne demandait d'**exhaustivité** — « combien de routes échappent à
  `PolicyEvaluator` ? », « quelle route a changé de protection entre deux commits ? » — là où un
  agent échantillonne et où des faits persistés devraient gagner ;
- rien n'a été mesuré sur la reproductibilité entre deux commits, qui est la promesse centrale.

## Ce qu'il faut corriger avant POC-01.1

Par ordre d'importance mesurée, et non supposée :

1. **L'unité déployable.** Quatre questions sur douze en dépendent. Le POC lit du Java et ignore
   `settings.gradle` et les `build.gradle` : il peut conclure depuis une configuration que
   l'application servant la route ne charge pas.
2. **La fausse absence sur les rôles.** Déclarer `OUT_OF_SCOPE` ce que `PolicyEvaluator` décide en
   Java est exactement l'erreur que la doctrine interdit : une absence n'est vraie que relativement
   à un périmètre, et ce périmètre était mal posé.
3. **`anyRequest()`**, le trou connu, gelé pour cette baseline.
4. **Le vocabulaire de l'`ABSENCE`.** « Le filtre ne s'applique pas » et « le filtre est monté mais
   inerte sur ce chemin » ne sont pas la même affirmation.

## Archivage

Les six réponses brutes n'ont pas été écrites dans des fichiers : elles sont conservées dans la
transcription de la session qui a lancé les runs. Durées, tokens et appels d'outil ci-dessus sont
relevés à la source. C'est un écart au protocole, qui demandait l'archivage des réponses brutes.
