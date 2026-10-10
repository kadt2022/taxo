# TAXO-MIP-SOURCE-01 — Lecture progressive du code Java à travers la Maille

**Statut :** récit accepté par le responsable du produit le 10 octobre 2026 ; à implémenter après
[TAXO-MINIA-SEC-01](TAXO-MINIA-SEC-01-fiabilisation-et-confidentialite.md).  
**Priorité :** haute.  
**Dépendance :** confidentialité et fiabilisation de Minia (TAXO-MINIA-SEC-01), qui doit être terminé avant.  
**Référence :** architecture MIP (`ARCHITECTURE.md` § 12, où `get_source` est réservée) et rapport du banc
`student-course-demo`.

## 1. Problème

Taxo connaît déjà des relations entre méthodes et permet leur exploration grâce à l'onglet Appels et à la vue
Chaîne.

Cependant, Minia reçoit essentiellement les faits de la Maille, sans pouvoir consulter à la demande le véritable
corps des méthodes Java.

Cette limitation peut empêcher le modèle de comprendre les conditions, les vérifications, les traitements et les
vulnérabilités éventuelles.

## 2. Vision du responsable du produit

Le LLM doit disposer de deux sources complémentaires :

1. Les faits déterministes produits et vérifiés par Taxo.
2. Le véritable code Java des méthodes nécessaires pour répondre à la question.

L'arbre d'appels est un instrument de navigation destiné aussi au LLM, et non simplement une représentation
graphique pour les humains.

Le LLM ne reçoit jamais l'intégralité du dépôt par défaut.

Il parcourt progressivement la Maille et demande uniquement le code dont il a besoin.

## 3. Fonctionnement attendu

Exemple : « Un utilisateur STUDENT peut-il accéder à GET /api/students ? »

1. Taxo retrouve la route et le contrôleur.
2. Minia reçoit les faits `HANDLED_BY`, les preuves et les frontières.
3. Minia demande le code Java de la méthode concernée.
4. Taxo transmet, si cela est autorisé, la déclaration, les annotations et le corps exact de la méthode.
5. Minia constate la présence éventuelle de `@PreAuthorize`.
6. Si nécessaire, elle demande à Taxo les relations de sécurité ou la configuration pertinente.
7. Taxo vérifie les affirmations vérifiables ; les autres restent des interprétations.
8. Minia répond en distinguant clairement les observations, les faits confirmés et les inconnues.

## 4. Exigences fonctionnelles

### E1 — Réutiliser la Maille existante

S'appuyer sur :

- `find_references` pour retrouver les symboles ;
- `get_neighborhood` pour naviguer entre les relations ;
- `CALLS`, `HANDLED_BY` et les autres relations du catalogue ;
- les Tuiles MIP et leurs frontières ;
- `verify_claim` pour vérifier les affirmations structurées.

Aucun second graphe ni second moteur de navigation.

### E2 — Implémenter `get_source`

Compléter la capacité `get_source`, déjà réservée dans l'architecture.

La lecture doit :

- accepter une référence canonique de méthode résolue par Taxo ;
- identifier exactement la méthode, y compris les surcharges ;
- fournir uniquement son code pertinent, ses annotations et ses lignes ;
- associer un chemin, une version de source et une empreinte vérifiable ;
- utiliser le même instantané que les faits de la Maille ;
- refuser les références ambiguës, périmées, interdites ou non disponibles ;
- signaler explicitement toute troncature ou tout contenu masqué.

Le code transmis est une donnée documentaire, jamais automatiquement un fait Taxo.

### E3 — Parcours principal : Appels

Minia explore les relations d'appels pertinentes à partir d'une ancre.

Elle peut :

- lire une méthode ;
- découvrir ses appels ;
- sélectionner les méthodes suivantes ;
- continuer jusqu'à disposer des informations nécessaires.

Une méthode qui appelle six autres méthodes ne provoque pas automatiquement la transmission de leurs six corps.

### E4 — Parcours complémentaire : Chaîne

Permettre une consultation ciblée d'autres relations nécessaires, notamment les protections de sécurité et les
implémentations.

Toute demande doit préciser les relations, la direction et les limites.

Aucune exploration libre et illimitée de la Chaîne générale.

La proposition de deux modes d'exploration reste une évolution distincte, à décider après stabilisation.

### E5 — Confidentialité

Respecter les protections du récit TAXO-MINIA-SEC-01.

- Double consentement spécifique à `get_source`, indépendant de celui de `get_diff`.
- Lecture seule.
- Aucun accès arbitraire au système de fichiers.
- Pas de transmission des secrets ou données interdites.
- Refus explicite si un extrait ne peut être divulgué de façon suffisamment sûre.
- Même politique pour les modèles locaux et distants, avec autorisation spécifique avant transmission vers un
  fournisseur distant.

### E6 — Maîtrise des coûts

Taxo contrôle la profondeur, le nombre de méthodes, le volume de code et le budget de l'échange.

Minia ne doit pas consulter une méthode déjà obtenue inutilement.

Les outils doivent exposer les refus, les budgets consommés et les opérations réellement réalisées.

## 5. Tests d'acceptation

- Navigation contrôlée sur une chaîne Controller → Service → Repository.
- Lecture ciblée de corps Java et d'annotations.
- Reconnaissance des surcharges et de la bonne version du code.
- Test de refus sur source confidentielle ou non autorisée.
- Test d'arrêt sur profondeur, budget et nombre d'opérations.
- Test de non-fuite vers les fournisseurs LLM.
- Vérification que les interprétations du code ne deviennent pas automatiquement des faits certifiés.
- Rejeu des 18 questions du banc, trois fois chacune, avec le même modèle et le même instantané.
- Mesure du temps, des opérations, des octets, des tokens lorsque disponibles et des résultats avant/après.

La simulation actuelle des tuiles choisies manuellement ne suffit pas : Minia doit démontrer qu'elle retrouve
elle-même les bonnes méthodes depuis la Maille.

## 6. Livraison

Procéder par PR cohérentes :

- **PR A** : extraction Java ciblée et contrat de `get_source`.
- **PR B** : raccordement aux capacités MIP existantes et intégration à Minia.
- **PR C** : tests de bout en bout, mesures et corrections nécessaires.

Les changements incompatibles de contrat, les élargissements de périmètre et toute fusion nécessitent
l'autorisation du responsable du produit.

## 7. Résultat recherché

Minia doit pouvoir comprendre une application Java en utilisant la Maille comme carte de navigation, les faits
Taxo comme preuves et le véritable code des méthodes comme matière d'analyse.

Taxo guide, contrôle et vérifie. Minia explore et interprète. Le code reste protégé.
