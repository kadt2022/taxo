# ADR 0006 — L'hypothèse statistique n'est pas un fait

Date : 2026-09-23
Statut : Proposé
Dépend de : ADR 0002 (contrat du fait), ADR 0004 (monolithe modulaire)

## Contexte

TAXO-LAB-01 étudie ce qu'un modèle statistique apporte lorsqu'il travaille sur la mémoire de Taxo.
À terme, Taxo aurait deux moteurs : un moteur déterministe qui établit des faits, et un moteur
statistique qui en propose. Il faut fixer, **avant tout code**, la frontière entre les deux.

Aujourd'hui, `INFERRED` désigne une dérivation **déterministe** : des prémisses, une règle, des
contre-exemples vérifiés, des lacunes déclarées. Une prédiction statistique n'a rien de tout cela.
La ranger sous `INFERRED`, ou ajouter un quatrième statut au contrat, mélangerait « déduit » et
« deviné » dans la même mémoire.

L'ADR 0004 (règle 14) pose déjà que le LLM ne produit pas de faits. Cet ADR étend la règle à tout
modèle statistique, quelle que soit sa taille.

## Décision

### 1. Une hypothèse est un objet distinct, pas un fait

Le contrat du fait v1 **ne change pas** : ni nouveau statut, ni nouveau type de producteur.

Une `Hypothesis` porte :

| Champ | Contenu |
| --- | --- |
| `subject` | la référence visée, au format du contrat (`endpoint:PUT /api/orders/{id}`) |
| `question` | la propriété prédite, prise dans un catalogue fermé et versionné |
| `scores` | un score par étiquette possible, lus dans les sorties numériques du modèle |
| `calibration` | l'identifiant et la version de la calibration appliquée aux scores |
| `decision` | une étiquette, ou `ABSTAIN` si aucun score calibré n'atteint le seuil |
| `representation` | l'empreinte de l'entrée remise au modèle, et la liste des faits qui la composent |
| `model` | famille, identifiant, version, nombre de paramètres, empreinte des poids |
| `snapshot` | l'instantané sur lequel porte l'hypothèse |

- **Les scores ne sont jamais du texte généré.** Un nombre écrit par un modèle génératif n'est pas une
  probabilité : les scores viennent des logits, ou d'une tête de classification.
- **`ABSTAIN` est une décision, pas une classe.** Elle résulte des scores calibrés et d'un seuil
  déclaré ; elle n'est pas une étiquette que le modèle apprend à prédire.

### 2. Une hypothèse n'est jamais une prémisse

Une hypothèse ne peut apparaître ni dans `derivation.premises`, ni dans `evidence`, ni dans
`validation` d'un fait. Comme elle n'est pas un fait, aucun chemin du contrat ne le permet : la règle
tient par construction, et un test d'architecture la vérifie.

### 3. Seul un vérificateur transforme une hypothèse en fait

```text
mémoire de faits ──► représentation ──► HypothesisModel ──► Hypothesis
                                                              │
                                                         vérificateur
                                                     ┌────────┴────────┐
                                                 CONFIRMED          REJECTED
                                                     │                 │
                                          fait produit par       journal des
                                          le vérificateur        hypothèses
```

- **Confirmée** : le vérificateur (un évaluateur déterministe, un oracle dynamique, un humain)
  produit le fait **sous sa propre provenance**, avec ses propres preuves. Le fait ne cite pas
  l'hypothèse comme prémisse ; il peut seulement mentionner qu'elle a motivé la vérification.
- **Rejetée** : rien n'entre dans la mémoire de faits. L'hypothèse et son verdict restent dans le
  **journal des hypothèses**.
- **Non vérifiée** : elle reste une hypothèse, visible comme telle, jamais présentée comme un fait.

Le journal est la future mémoire d'**expériences** : c'est lui qui permettra de calibrer les modèles
(« sur 200 hypothèses à 0,9, combien confirmées ? »). Il est séparé de la mémoire de faits.

### 4. Le modèle vit derrière un port, dans sa propre capacité

Conformément à l'ADR 0004 (la capacité précède la couche) :

```text
backend/app/hypotheses/
├── domain/           Hypothesis, HypothesisModel (Protocol), catalogue des questions
├── application/      propose_hypotheses, verify_hypothesis
└── infrastructure/   adaptateurs de modèles (réseau minimal, petit transformer, SmolLM2…)
```

```python
class HypothesisModel(Protocol):
    model_id: str
    model_version: str
    parameter_count: int

    def score(self, representation: Representation) -> Mapping[str, float]: ...
```

Le domaine ne connaît ni `torch` ni `transformers` ; seuls les adaptateurs en dépendent. Remplacer un
modèle par un autre ne modifie rien hors de `infrastructure`.

### 5. La représentation est construite par Taxo, jamais par le modèle

Le modèle ne lit ni le dépôt ni le code : il reçoit une `Representation` construite depuis la mémoire
de faits. Elle déclare ce qui est connu, ce qui est inconnu (la couverture), et la question posée.
Pour une expérience, les faits qui déterminent seuls l'étiquette en sont retirés et la liste des
retraits est enregistrée (règle anti-tautologie de TAXO-LAB-01).

## Conséquences

- Le contrat v1, son schéma et sa suite de conformité restent inchangés.
- Toute projection qui affiche une hypothèse la présente comme telle, avec son modèle et ses scores.
- Une mémoire de faits ne contient que ce qui a été observé, déduit ou validé : on peut toujours
  répondre « pourquoi Taxo affirme-t-il cela ? » sans passer par un modèle statistique.
- Tant que TAXO-LAB-01 n'a pas conclu, la capacité `hypotheses` n'est pas branchée au produit :
  aucune API, aucune projection ne l'expose.

## Questions ouvertes

- Format et persistance du journal des hypothèses (dépend de TAXO-01E).
- Catalogue des questions v1 : il sera fixé par TAXO-LAB-01 (qui peut appeler l'endpoint ?).
- Durée de validité d'une hypothèse : l'instantané suffit-il, ou faut-il l'invalider avec la mémoire
  (comparaison de TAXO-01F) ?
