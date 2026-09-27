# Banc TAXO-POC-01 — grille de dépouillement

Une grille par exécution. Trois exécutions par bras : `A1 A2 A3`, `B1 B2 B3`.

```text
Bras : ___   Exécution : ___   Date : ____-__-__
Modèle : ____________   Commit du dépôt : 032788fb6d   Baseline POC : 97b8625
```

| Q | Conclusion juste | Preuve juste | « Je ne sais pas » justifié | Fausse affirmation | Points | Note |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | | | | | | |
| Q2 | | | | | | |
| Q3 | | | | | | |
| Q4 | | | | | | |
| Q5 | | | | | | |
| Q6 | | | | | | |
| Q7 | | | | | | |
| Q8 | | | | | | |
| Q9 | | | | | | |
| Q10 | | | | | | |
| Q11 | | | | | | |
| Q12 | | | | | | |

```text
Total points        : ___ / 24
Fausses affirmations: ___
Fausses absences    : ___
Preuves incorrectes : ___
Durée totale        : ___ min
Tokens consommés    : ___
```

## Barème

| Situation | Points |
| --- | --- |
| Conclusion juste, preuve juste | +2 |
| Conclusion juste, preuve fausse ou absente | +1 |
| « Je ne sais pas » justifié par la vérité de référence | +2 |
| « Je ne sais pas » injustifié | 0 |
| Conclusion fausse, annoncée comme incertaine | −1 |
| Conclusion fausse, assurée, avec preuve d'apparence crédible | −3 |

## Lecture du résultat

Trois chiffres décident, dans cet ordre :

1. **Fausses affirmations.** Si le bras B en produit plus que le bras A, Taxo échoue, quel que soit
   le total. Un outil qui fait affirmer faux avec des preuves est pire qu'un outil absent.
2. **Total de points.** L'écart B − A, et sa stabilité sur trois exécutions.
3. **Tokens et temps.** Un gain de justesse payé par une consommation supérieure reste un gain,
   mais il doit être dit.

Questions à regarder une par une, elles portent l'essentiel de l'information :

- **Q9, Q10, Q11, Q12** : le bras A peut gagner. Il lit `build.gradle`, le POC ne le lit pas.
- **Q3, Q5, Q6** : le bras B doit gagner. Ce sont les pièges que les faits documentent.
- **Q2** : les deux doivent refuser. Une liste de rôles, des deux côtés, est une fausse affirmation.
