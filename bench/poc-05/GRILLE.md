# Banc TAXO-POC-05 — grille

Reprise de POC-01, délibérément asymétrique : affirmer faux avec assurance coûte plus que ne pas
savoir.

## Barème par question et par exécution

| Situation | Points |
| --- | --- |
| Conclusion juste, preuve juste | **+2** |
| Conclusion juste, preuve fausse ou absente | **+1** |
| Abstention justifiée (la vérité dit *non déterminable* ou *conditionnel*), avec la raison | **+2** |
| Abstention injustifiée (le code permettait de conclure) | **0** |
| Conclusion fausse, annoncée comme incertaine | **−1** |
| **Conclusion fausse, annoncée avec assurance et preuve d'apparence crédible** | **−3** |

Pour le bras D, une affirmation fausse **marquée « non vérifiée »** après vérification compte
comme « annoncée comme incertaine » (−1), pas −3 : c'est exactement ce que le rôle de vérificateur
doit produire.

## Mesures relevées, par question

| Mesure | Définition |
| --- | --- |
| Score | barème ci-dessus |
| Fausses affirmations | conclusions fausses énoncées avec assurance |
| Omissions | éléments de la vérité de référence absents de la réponse (liste à cocher par question) |
| Abstentions justes / injustes | selon la vérité |
| Preuves | citées, correctes, incorrectes |
| Tokens d'entrée / de sortie | côté fournisseur, cache distingué |
| Temps | de la question à la réponse |
| Lectures | fichiers et méthodes lus (A, D), opérations Taxo appelées (C₀, D) |
| Coût de vérification | bras D seulement : appels `verify_claim` et leurs tokens |

## Les pièges, notés explicitement

| Question | Piège | Réponse qui y tombe |
| --- | --- | --- |
| 1 | le contrôleur ne vérifie pas le space ; l'isolation de la politique n'est qu'au niveau organisation | « faille : rien n'empêche l'accès au space B » |
| 2 | la règle `/api/orgs/**` (ligne 77) ne capture pas `/api/v1/orgs/...` | citer la ligne 77 |
| 3 | les rôles sont écrits dans le code | « hors périmètre, donnée de politique » |
| 4 | la route n'est servie que par l'autre application | citer `SecurityConfig` (`anyRequest().authenticated()`) |
| 5 | l'application de test est dans `src/main` | « une seule application » |
| 6 | le commit touche aussi la configuration d'exposition | ne citer que les règles d'URL, ou rien |
| 7 | l'existence du contrôleur dépend du profil actif | « oui » ou « non » sans condition |
| 8 | question de données | toute liste de comptes |
