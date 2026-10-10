# TAXO-MINIA-SEC-01 — Fiabilisation des réponses et protection des informations confidentielles

**Statut :** récit accepté par le responsable du produit le 10 octobre 2026 ; implémentation à venir en PR limitées.  
**Priorité :** critique.  
**Référence :** rapport du banc `student-course-demo`, 18 tests du 10 octobre 2026. Le rapport et ses 18
questions ne sont pas encore dans le dépôt : ils y seront ajoutés avec la PR de mesure, sans donnée personnelle.  
**Source de vérité :** `ARCHITECTURE.md` § 12.4 (verdicts), § 12.5 (transparence) et § 12.6 (sécurité et consentement).  
**Bloque :** [TAXO-MIP-SOURCE-01](TAXO-MIP-SOURCE-01-lecture-du-code-par-la-maille.md) (lecture du code des méthodes).

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
