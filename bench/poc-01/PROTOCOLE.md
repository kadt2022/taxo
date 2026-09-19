# Banc TAXO-POC-01 — protocole

*Écrit le 2026-09-19, avant toute exécution. Aucune ligne de ce dossier ne doit être modifiée
après le premier run : un banc que l'on ajuste après coup ne mesure plus rien.*

## La question

> Un agent qui reçoit des faits vérifiés produits par Taxo répond-il mieux, sur l'architecture de
> sécurité d'un dépôt réel, que le même agent qui reçoit le dépôt seul ?

Le banc doit pouvoir répondre **non**. Si le gain est faible, c'est la thèse de Taxo qu'on révise.

## Ce qui est gelé

| Élément | Valeur |
| --- | --- |
| Producteur | `poc.spring-authorization-chain` version `0.0.1`, catalogue `spring-security-poc/0` |
| Commit du POC (baseline **POC-01**) | `97b8625` sur `feat/taxo-poc-01-evaluateur-jetable` |
| Dépôt analysé | TAKIBO, commit `032788fb6db90470ce2a7cd71193f99f6ec1e57d` |
| Bundle de faits | `faits/r01.json` … `faits/r07.json`, sortie brute de la CLI, **non éditée** |

Le trou connu de cette baseline — `anyRequest()` n'est pas modélisé — **n'est pas corrigé**. Il est
mesuré. La correction donnera POC-01.1, et le même banc, inchangé, dira ce qu'elle a changé.

## Les deux bras

Les deux bras reçoivent le **même dépôt**, le **même commit**, le **même modèle**, les **mêmes
questions dans le même ordre**, et aucun accès à ce dossier.

| Bras | Ce qu'il reçoit |
| --- | --- |
| **A — agent seul** | le dépôt TAKIBO au commit gelé, rien d'autre |
| **B — agent + Taxo** | le même dépôt, plus les sept fichiers de `faits/` |

Règles communes :

- session **fraîche**, sans l'historique de conception de Taxo ni de ce banc ;
- le dépôt Taxo n'est pas fourni : il contient les vérités de référence ;
- trois exécutions par bras, pour mesurer la stabilité ;
- chaque réponse doit citer ses preuves (fichier et lignes) ou déclarer qu'elle n'en a pas ;
- « je ne sais pas », « hors périmètre » et « indécidable statiquement » sont des réponses
  autorisées et parfois correctes.

## Consigne à coller dans chaque session

> Tu disposes du dépôt Java `<chemin>` au commit `032788fb6d`. Réponds aux questions de
> `QUESTIONS.md` dans l'ordre. Pour chaque réponse : une conclusion, puis les preuves (fichier et
> lignes) qui la soutiennent. Si tu ne peux pas conclure, dis-le et dis pourquoi. Ne devine pas.

Le bras B ajoute :

> Tu disposes également de faits produits par un outil d'analyse, dans `faits/`. Chaque fait porte
> son statut (`OBSERVED` ou `INFERRED`), ses preuves, et pour une inférence ses prémisses. Les
> couvertures disent ce que l'outil n'a pas su interpréter. Ces faits peuvent être incomplets ou
> faux : tu restes responsable de tes réponses.

## Mesures

Par question et par exécution :

| Mesure | Définition |
| --- | --- |
| **Exactitude** | la conclusion correspond à la vérité de référence |
| **Fausse affirmation** | une conclusion fausse énoncée avec assurance |
| **Fausse absence** | « je ne sais pas » alors que le code permettait de conclure |
| **Preuve correcte** | fichier et lignes cités existent et soutiennent la conclusion |
| **Preuve incorrecte** | lignes inexistantes, hors sujet, ou qui ne soutiennent pas la conclusion |
| **Temps** | durée de la réponse |
| **Tokens** | consommation de la session |

Barème, délibérément asymétrique :

| Situation | Points |
| --- | --- |
| Conclusion juste, preuve juste | **+2** |
| Conclusion juste, preuve fausse ou absente | **+1** |
| « Je ne sais pas » justifié (la vérité de référence dit *indécidable*) | **+2** |
| « Je ne sais pas » injustifié | **0** |
| Conclusion fausse, annoncée comme incertaine | **−1** |
| **Conclusion fausse, annoncée avec assurance et preuve d'apparence crédible** | **−3** |

Cette asymétrie est le cœur du banc. Un outil qui se tait coûte du temps. Un outil qui affirme
faux en citant des lignes réelles coûte la confiance, et c'est précisément ce que Taxo prétend
empêcher. Il doit donc être puni plus sévèrement que l'ignorance — y compris quand c'est lui.

## Ce que le banc ne mesure pas

- La performance brute : le POC produit sa chaîne en 0,26 s, mais il ne lit que du Spring et
  seulement par expressions régulières.
- La généricité : un seul dépôt, un seul framework. « Taxo n'est pas fait pour ce projet » ne
  devient réfutable qu'avec un second terrain.
- La persistance, le MCP et le lineage : rien de tout cela n'existe encore.
