# TAXO-MINIA-SEC-01 — Fiabilisation des réponses et protection des informations confidentielles

**Statut :** **terminé le 11 octobre 2026.** Récit accepté le 10 octobre 2026 ; E3 (#118), E1 (#119) et E2 (#120)
fusionnées le 10 octobre ; E4 (#126) et le banc rejouable (#127) livrés le 11 octobre. Bilan ci-dessous (« Clôture »).  
**Priorité :** critique.  
**Référence :** rapport du banc `student-course-demo`, 18 tests du 10 octobre 2026. Le rapport et ses 18
questions ne sont pas dans le dépôt : le banc a été reconstitué (#127), réponses attendues établies à la main.
Le 11 octobre, le responsable du produit a décidé que son rejeu contre un vrai modèle ne conditionne pas la
clôture : il le fera lui-même pour apprécier le travail ; un écart constaté donnera un nouveau récit.  
**Source de vérité :** `ARCHITECTURE.md` § 12.4 (verdicts), § 12.5 (transparence) et § 12.6 (sécurité et consentement).  
**Bloquait :** [TAXO-MIP-SOURCE-01](TAXO-MIP-SOURCE-01-lecture-du-code-par-la-maille.md) (lecture du code des méthodes).

## 1. Problème

Le banc d'essai révèle trois défauts principaux :

1. Minia produit parfois des affirmations incorrectes, notamment sur les contrôles de sécurité Spring.
2. Certaines conclusions reçoivent le verdict `CONFIRMED` alors que les faits Taxo ne prouvent qu'une partie
   de l'affirmation.
3. Des informations personnelles ou confidentielles peuvent être transmises inutilement aux fournisseurs de
   LLM, notamment les auteurs et messages de commits.

Les tests 9, 11 et 18 révèlent des erreurs importantes concernant `@PreAuthorize`, `@EnableMethodSecurity` et
les règles de sécurité.

## 2. Objectif

Garantir que Minia ne présente aucune interprétation comme un fait confirmé sans preuve correspondante et ne
transmet aucune donnée interdite au LLM.

Taxo reste l'autorité des faits, de leur vérification et de la divulgation des informations.

## 3. Exigences fonctionnelles

### E1 — Fiabiliser les verdicts

- Un verdict `CONFIRMED` doit correspondre exactement à une affirmation structurée que Taxo sait vérifier.
- Une relation `CALLS` ne prouve pas l'absence d'un contrôle de sécurité.
- Une absence de fait n'est jamais assimilée à une absence dans le code.
- Les relations `CONTAINS`, `HANDLED_BY` et autres relations doivent conserver leur sens.
- Les interprétations et les inconnues ne doivent pas être présentées comme des faits vérifiés.
- Les échecs d'exploration ou de repli doivent être signalés sans prétendre que Taxo ne connaît aucun fait.

### E2 — Compléter les faits de sécurité

Examiner les capacités existantes des analyseurs avant toute extension.

Couvrir de manière déterministe, lorsque les sources permettent de l'établir :

- `@PreAuthorize` et les expressions de rôles ;
- `@EnableMethodSecurity` ;
- la configuration CSRF ;
- les protections de routes et leur articulation avec la sécurité des méthodes.

Ne pas inventer de nouvelle relation sans contrat, preuve et tests.

### E3 — Confidentialité

Créer une représentation contrôlée des données destinées aux LLM, distincte des informations locales
conservées par Taxo.

- Masquer par défaut les noms et courriels des auteurs de commits.
- Filtrer les messages de commits et leurs trailers, notamment `Co-Authored-By`.
- Détecter et protéger les secrets, identifiants et données personnelles.
- Utiliser `******` ou un pseudonyme temporaire lorsque la relation entre plusieurs identités doit rester
  compréhensible.
- Conserver localement les valeurs originales.
- Permettre à Taxo de répondre directement, par une fonction déterministe, aux questions comme « Qui est
  l'auteur du commit ? », sans transmettre l'identité au LLM.
- Refuser toute transmission dont la confidentialité ne peut être suffisamment garantie.

Le masquage intervient avant l'appel au fournisseur, dans une couche centralisée, et non uniquement dans les
instructions du modèle.

### E4 — Transparence

- Distinguer faits confirmés, interprétations et informations inconnues.
- Rendre visibles les refus et limites, sans divulguer les valeurs sensibles.
- Ne pas enregistrer les contenus confidentiels dans les journaux ou trajectoires.

## 4. Tests d'acceptation

- Rejouer les 18 questions du banc, trois fois chacune.
- Corriger les conclusions fausses des tests 9, 11 et 18.
- Vérifier les régressions sur les chaînes d'appels déjà correctes.
- Tester les réponses en cas d'absence de fait ou d'échec d'exploration.
- Capturer les charges réellement envoyées aux fournisseurs et vérifier l'absence de noms, courriels, secrets
  et données interdites.
- Vérifier qu'un mot de passe masqué ne supprime pas le constat de sécurité « mot de passe codé en dur ».

**Critère de réussite :** aucun verdict de sécurité incorrect déclaré `CONFIRMED` dans le banc de référence ;
aucun contenu explicitement interdit dans les transmissions de test.

## 5. Livraison

Travail sur une branche dédiée, en PR limitées et testées, avec CI obligatoire.

Découpage proposé, chaque PR testable seule :

- **PR docs** : ce récit et TAXO-MIP-SOURCE-01, plan mis à jour.
- **PR E3** : couche centralisée de masquage avant tout appel à un fournisseur, et réponse déterministe aux
  questions d'identité.
- **PR E1** : verdicts exacts et signalement des échecs d'exploration ou de repli.
- **PR E2** : faits de sécurité, après constat des capacités existantes des analyseurs.
- **PR E4 et mesure** : transparence dans le portail, capture des charges envoyées, rejeu du banc.

L'ordre peut changer selon les dépendances constatées dans le code ; tout changement est tracé dans la PR.

Aucune modification lourde de contrat ni aucune fusion sans l'accord explicite du responsable du produit.

Ce récit doit être terminé avant d'autoriser la nouvelle lecture de code du récit TAXO-MIP-SOURCE-01.

## Clôture

Ce qui est démontré, et par quoi :

- **Verdicts (E1)** : un `CONFIRMED` porte sur l'affirmation entière ; ses limites (couverture non lue, échec
  d'exploration ou repli) sont rendues (#119).
- **Faits de sécurité (E2, tests 9, 11 et 18)** : au commit `01163f1` de `student-course-demo`, Taxo produit
  `PROTECTED_BY hasAnyRole('ADMIN','TEACHER')` sur `GET /api/students` et `POST /api/enrollments`, en plus de
  `authenticated()`, et `ANNOTATED_WITH EnableMethodSecurity` sur `SecurityConfig` ; `csrf.disable()` est un fait
  `CONFIGURES` (#120). Les 32 triplets de sécurité établis à la main sont la vérité du banc (#127).
- **Confidentialité (E3)** : une seule couche protège chaque message avant tout fournisseur (#118). Les tests
  capturent les charges réellement envoyées, y compris sur le chemin des Tuiles : aucun nom, courriel, ligne
  de fin de commit ni secret ; un mot de passe écrit en dur reste visible comme tel, valeur masquée (#126, #127).
- **Transparence (E4)** : observations, interprétations et inconnues restent séparées ; chaque refus de Taxo est
  dit avec sa raison ; le journal d'accès ne garde que les noms de paramètres ; la trajectoire ne garde ni secret
  ni réponse brute (#126).
- **Banc** : `backend/scripts/minia_bench.py` rejoue les 18 questions, trois fois chacune, et mesure exactitude,
  fausses confirmations de sécurité, opérations, appels, octets, temps et fuites dans les charges (#127).

Limite : le rejeu contre un vrai modèle n'a pas été exécuté dans le cadre du récit, par décision du responsable
du produit (voir le statut). [TAXO-MIP-SOURCE-01](TAXO-MIP-SOURCE-01-lecture-du-code-par-la-maille.md),
débloqué, a été terminé avec [TAXO-MIP-ADT-01](TAXO-MIP-ADT-01-adaptive-tile.md) le même jour.
