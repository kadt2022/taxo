# Banc TAXO-POC-02 — vérité de référence

*Établie le 2026-09-19, **avant** toute exécution, au commit `032788fb6db90470ce2a7cd71193f99f6ec1e57d`.
À ne jamais fournir aux sessions qui exécutent les bras.*

## Comment l'inventaire a été établi

Le recensement ne s'appuie **pas** sur le POC, pour ne pas noter les agents contre les angles morts
de l'outil mesuré. Deux comptages indépendants :

1. `grep -cE "@(Get|Post|Put|Delete|Patch)Mapping|@RequestMapping\s*\(\s*method"` sur les sources
   principales (hors `/src/test/`) : **45 annotations**, réparties sur 15 contrôleurs.
2. Reconstruction des chemins complets par le parseur du POC : **45 endpoints**, mêmes 15
   contrôleurs, même distribution fichier par fichier.

Les deux comptages coïncident exactement. L'inventaire de référence est donc **45 endpoints**.

## Le partage entre les deux applications

| Application | Modules servis | Endpoints | Chaîne de sécurité |
| --- | --- | --- | --- |
| IAM (`takibo-iam-boot`) | identity-core, management-service, security-management | **38** | `SecurityConfig.java` |
| Bac d'essai (`takibo-adp-test`) | adp-test seul | **7** | `TestSecurityConfig.java` |

`takibo-adp-test/build.gradle:8` ne dépend que de `takibo-adp-spring` : **`PolicyEvaluator` n'existe
pas dans cette application**. Ses 7 endpoints ne l'atteignent donc jamais, quelle que soit leur
règle.

## Classement des 38 endpoints de l'application IAM

Les règles de `SecurityConfig.java:51-88` s'appliquent dans l'ordre, première correspondance
gagnante :

| Endpoints | Règle gagnante | Atteint `PolicyEvaluator` ? |
| --- | --- | --- |
| `POST /api/v1/auth/login` | `:74` `permitAll` | **non** |
| 28 autres routes `/api/v1/...` | `:85` `/api/v1/**` → `.access(...)` | oui |
| `POST /api/spaces/{spaceId}/users` | `:80` `/api/spaces/**` → `.access(...)` | oui |
| 8 routes `/debug/secure/...` | `:86` `/debug/secure/**` → `.access(...)` | oui |

Aucun endpoint de l'application IAM ne tombe sur `:88` `anyRequest().authenticated()`, et aucun
n'est capturé par `:53-60`, `:64-69` ni `:76` — ces règles visent des chemins qu'aucun contrôleur
ne sert.

## La réponse

**8 endpoints sur 45 n'atteignent pas `PolicyEvaluator`** :

| # | Endpoint | Raison | Preuve |
| --- | --- | --- | --- |
| 1 | `POST /api/v1/auth/login` | règle antérieure `permitAll` | `SecurityConfig.java:74` |
| 2 | `GET /api/health` | autre application, `permitAll` | `TestSecurityConfig.java:47` |
| 3 | `GET /api/public/info` | autre application, `permitAll` | `TestSecurityConfig.java:46` |
| 4 | `GET /api/dashboard` | autre application, `anyRequest().access(adpAuthorizationManager())` | `TestSecurityConfig.java:48` |
| 5 | `GET /api/admin/users` | idem | `TestSecurityConfig.java:48` |
| 6 | `POST /api/admin/users` | idem | `TestSecurityConfig.java:48` |
| 7 | `GET /api/data/sensitive` | idem | `TestSecurityConfig.java:48` |
| 8 | `GET /api/profile` | idem | `TestSecurityConfig.java:48` |

Les 37 autres l'atteignent, sous réserve des court-circuits d'exécution de
`PolicyBasedAuthorizationManager` (appelant anonyme, contexte absent, chemin illisible), qui sont
des propriétés de la requête et non de la route.

## Les pièges de cette question

- **`POST /api/v1/orgs/signup`** ressemble à une route publique d'inscription. Elle ne l'est pas :
  aucune règle antérieure ne la capture, donc `:85` gagne et elle atteint `PolicyEvaluator`. La
  classer publique est une fausse affirmation.
- **Les 8 routes `/debug/secure/...`** ont l'air d'un bac à sable de développement. Elles sont
  gouvernées comme les autres, par `:86`.
- **`POST /api/spaces/{spaceId}/users`** est la seule route non versionnée de l'application IAM ;
  elle est capturée par `:80`, pas par `:85`. Une réponse qui ne cite qu'une seule règle pour tout
  le dépôt rate cette nuance.
- **Le total de 45** n'est atteignable qu'en recensant les 15 contrôleurs. Une réponse qui annonce
  un total inférieur a échantillonné sans le dire.

## Cotation

| Mesure | Définition |
| --- | --- |
| **Rappel** | combien des 8 vraies réponses figurent dans la liste rendue |
| **Fausses affirmations** | endpoints classés « n'atteint pas » alors qu'ils l'atteignent |
| **Exhaustivité déclarée** | le total annoncé (45 attendu) et les non-classés reconnus |
| **Preuves** | fichier et ligne exacts, vérifiés par sondage |
| **Coût** | durée et tokens |

Un endpoint déclaré non classé n'est pas compté comme faux : c'est une lacune reconnue, et c'est
précisément ce que le banc veut distinguer d'une affirmation erronée.
