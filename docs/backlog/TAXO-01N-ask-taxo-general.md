# TAXO-01N / MIP-01 — Interaction générale de la Maille

**Statut :** récit accepté par le responsable du produit le 9 octobre 2026, dans cette version ajustée (voir § 12).  
**Nature :** évolution bornée de TAXO V2 ; aucune implémentation ni fusion autorisée par ce document.  
**Origine :** consolidation du récit proposé « TAXO-01N — Ask Taxo général » et du noyau déjà discuté du **Maille Interaction Protocol (MIP) 0.1**.  
**Responsable de réalisation proposé :** agent de développement, sous gouvernance habituelle de l'équipe.  
**Références de l'existant :** `taxo-query/1`, `describe`, `find_references`, `get_neighborhood`, `verify_claim`, Explorer de la Maille, Tuiles et `neighborhood/2` ; la disponibilité exacte des champs et des adaptateurs reste à constater dans le code avant chaque PR.

> **Décision proposée.** Nous ne développons pas d'abord un « Ask Taxo général », puis un second protocole MIP. Nous réalisons **un noyau MIP 0.1 utilisable sans LLM**, puis raccordons **Ask Taxo et Minia** à ce même noyau. Un seul moteur de faits, une seule autorité de vérification, plusieurs consommateurs. L'autorisation finale d'un changement de contrat ou d'une fusion appartient au responsable du produit.

## 1. Problème à résoudre

La Maille contient déjà des faits structurels et historiques, des relations typées, leurs preuves, leur provenance et des limites d'analyse. Pourtant, l'entrée « Interroger Taxo » privilégie les sélections de commits. Les questions « qui appelle `OwnerRepository.findById` ? », « que contient `api` ? » ou « quelles routes sont servies par `VetController` ? » ne sont pas correctement acheminées vers les connaissances correspondantes.

Sur la révision `fa16f73` citée par le récit TAXO-01N, cinq obstacles ont été identifiés :

1. Le bouton « Sélectionner » reconnaît les derniers commits, un commit ou une période ; une autre question reste une sélection `GLOBAL`.
2. La projection sélectionnée ne porte, pour les sélections historiques, que sur les faits `taxo.git`.
3. En exploration Minia, les huit arguments à plat de `STEP_SCHEMA` excluent notamment `prefix`, `root`, `steps` et `depth`, nécessaires à `find_references` et `get_neighborhood`.
4. Le repli en mode paquet est centré sur les commits et aboutit à `NEEDS_SELECTION` pour une question générale.
5. Le panneau ne montre que des exemples historiques.

**Problème plus profond :** l'interaction avec une Maille vérifiable n'est pas encore formalisée en contrat générique, utilisable par TAXO seul comme par Minia ou un autre consommateur, **sans recopier les règles du moteur**.

## 2. Résultat attendu

À l'issue de ce récit :

- **TAXO seul** accepte une requête MIP structurée ciblant une référence de la Maille, et retourne une **Tuile bornée**, avec faits, preuves, provenance, couverture et frontières. Aucun fournisseur LLM n'est requis.
- **Minia** peut retrouver une référence avec les opérations déjà décrites par TAXO, demander une exploration bornée et expliquer ses résultats sans transformer une hypothèse en fait.
- **Ask Taxo** propose une entrée commune pour questions historiques et structurelles. Lorsque la référence est reconnaissable sans modèle, l'utilisateur peut consulter la Tuile ou accéder à l'Explorer ; l'interprétation en langage naturel avancé reste facultative et relève de Minia.
- **Le contrat MIP 0.1** est utilisable depuis un client indépendant de Minia, tout en conservant les protections d'accès et les budgets de TAXO.
- **Les questions historiques existantes ne régressent pas.**

Le livrable est un **protocole de lecture et de consultation de connaissance**, non un agent autonome et non un nouveau moteur d'analyse.

## 3. Doctrine et vocabulaire non négociables

### 3.1. Les trois objets

- **Maille :** connaissance locale qualifiée du projet, graphe de faits et de relations assortis de provenance, de preuves et de limites.
- **Tuile :** portion bornée de cette Maille, issue d'un instantané déterminé ; elle transporte les faits **et** les conditions dans lesquelles ils ont été obtenus.
- **MIP — Maille Interaction Protocol :** contrat sémantique de consultation de Tuiles et de leurs frontières. Il est indépendant d'un LLM et du transport ; HTTP est un premier adaptateur, MCP pourrait devenir un autre adaptateur, sans devenir le MIP lui-même.

### 3.2. Autorité

1. Minia ou un consommateur formule une **intention de lecture**, jamais un fait faisant autorité.
2. TAXO valide cette intention, le périmètre, les droits et les budgets avant de consulter la Maille.
3. TAXO construit une Tuile à partir des faits réellement disponibles dans **une analyse fixée**.
4. Les affirmations interprétatives sont **proposées** par le consommateur ; seule la vérification par TAXO peut les rendre **confirmées dans le périmètre de la Maille**.
5. `OBSERVED`, `INFERRED`, `NOT_INTERPRETED`, `OUT_OF_SCOPE`, « non analysé » et « non prouvé » ne sont pas interchangeables. Les catégories de frontière TAXO-01M (`UNKNOWN`, `AMBIGUOUS`, `UNSUPPORTED`, `OUT_OF_SCOPE`) restent distinctes des erreurs de protocole.
6. Une recherche vide **n'est pas** une preuve d'absence dans le code. Une confirmation par TAXO n'est pas une garantie exhaustive du comportement à l'exécution.

### 3.3. Un seul moteur

`MIP 0.1 → adaptateur → capacités existantes de taxo-query/1 → Maille`.

**Interdit dans ce récit :** deuxième stockage des faits, deuxième moteur de graphe, duplication des règles de vérité dans le portail ou dans Minia, ou conversion silencieuse de données de la Maille en instructions destinées au modèle.

## 4. Contrat MIP 0.1 à figer en PR A

### 4.1. Entrée sémantique

Deux expressions initiales et **seulement deux** :

- `EXPAND` : demander une exploration bornée autour d'une référence de la Maille ; le voisinage et les relations traversées proviennent exclusivement du moteur existant.
- `PROJECT` : demander une projection bornée des faits disponibles à partir d'une référence et des choix de projection **effectivement servis** par le moteur. Elle ne crée ni Arbre, ni nouvelle inférence.

**Servi en MIP 0.1 : `EXPAND` seulement.** `PROJECT` fait partie du vocabulaire du contrat, mais aucune règle de projection servie n'est encore écrite : MIP 0.1 la **refuse explicitement** par une erreur de protocole (code existant, à confirmer en PR A), jamais par une Tuile vide. Elle sera servie quand une règle de projection aura été écrite, testée et acceptée.

**Ce que `EXPAND` doit recevoir pour être déterministe :**

- **Projet et analyse.** Une référence canonique (`symbol:java:…`) n'est pas propre à un projet ; la requête est donc toujours adressée à un projet, comme `taxo-query/1` (`/api/projects/{project_id}/taxo-query`), et porte un champ facultatif `analysis`. Sans lui, TAXO fixe la dernière analyse à l'ouverture et la rend dans la Tuile ; le consommateur la renvoie ensuite à chaque étape (recherche, Tuile, vérification) pour rester sur le même instantané (critère 4). Les droits du projet s'appliquent avant toute lecture.
- **Relations et sens.** `get_neighborhood` refuse une demande sans relations ni sens ; `EXPAND` les porte donc explicitement : `relations` (types de relation à suivre, ceux que `describe` annonce) et `direction` (`OUTGOING`, `INCOMING` ou `BOTH`). « Qui appelle X ? » est `relations: ["CALLS"]`, `direction: "INCOMING"` ; « qu'appelle X ? » est le même avec `OUTGOING`. Aucun défaut caché : un champ manquant est une erreur de protocole. La correspondance exacte avec `steps` / `follow` du moteur est relevée en PR A.

Le point d'entrée HTTP initial proposé est `POST /api/projects/{project_id}/mip/query`, à côté de `taxo-query`. Ce chemin est un **adaptateur de transport**, pas un second protocole (ARCHITECTURE § 12.3) : une requête MIP devient exactement une opération `taxo-query/1` (`get_neighborhood`), dont la validation, les budgets et les codes d'erreur s'appliquent tels quels. La sémantique MIP doit rester testable directement au niveau applicatif sans serveur HTTP.

`EXPAND` couvre les trois formes de la même opération (ARCHITECTURE § 9.5) : la première Tuile autour d'une référence (TILE) ; l'extension depuis un nœud de frontière arrêté par la profondeur ou non atteint (`DEPTH`, `NOT_REACHED`), qui n'a pas de jeton et se demande comme une nouvelle Tuile centrée sur ce nœud, avec sa profondeur restante (TAXO-01J) ; la reprise d'une adjacence coupée par un budget, avec le jeton `continuation` de sa frontière. Un seul nom, la même opération.

**Exemple de requête (noms relevés sur le protocole existant en PR A, voir `docs/MIP-0.1.md`) :**

```json
{
  "target": {
    "reference": "symbol:java:com.example.demo.service.CourseService#register(String)"
  },
  "expression": "EXPAND",
  "analysis": "<analyse rendue par find_references>",
  "relations": ["CALLS"],
  "direction": "INCOMING",
  "bounds": {
    "max_nodes": 50,
    "max_facts": 100,
    "depth": 2
  }
}
```

Les limites demandées sont plafonnées par celles du serveur, jamais l'inverse. Les champs non reconnus, les types incorrects et les valeurs hors bornes sont traités explicitement. **Le récit ne fixe pas de valeurs de plafond de production arbitraires** : la PR A réutilise les plafonds existants et publie la correspondance vérifiée.

L'identité passée au MIP est une **référence résolue** de TAXO. La reconnaissance d'un nom issu d'une question (« `findById` ») est une étape séparée ; le MIP ne devine pas la référence.

### 4.1 bis. Retrouver une référence par son nom

Cette étape séparée existe déjà : `find_references`. Mais elle compare un **préfixe de la clé entière** (`neighborhood/domain/references.py`, `reference_index.search`) ; une clé Java commence par le paquet (`com.example.web.VetController…`), donc le nom seul (`VetController`, `OwnerRepository.findById`) ne la trouve pas. Sans correction, les exemples mêmes de ce récit échouent.

Extension additive de `find_references`, sans changer `taxo-query/1` pour les clients actuels :

- Champ facultatif `match` : `KEY` (défaut, comportement actuel inchangé) ou `NAME`.
- En `NAME`, la clé et le préfixe demandé sont d'abord **normalisés** : chaque séparateur d'un jeu fixe et neutre (`.`, `/`, `#`, `:`, `$`) devient un même séparateur canonique. Le préfixe normalisé est ensuite comparé au début de **chaque suffixe de la clé qui commence à un segment**. `OwnerRepository.findById` trouve `…OwnerRepository#findById(…)`, et `VetController` trouve `…web.VetController`. Aucune règle propre à un langage, aucune recherche de segments isolés (qui serait ambiguë).
- Une référence trouvée par plusieurs de ses segments n'est rendue **qu'une fois** : la déduplication par référence, stable, précède la limite de page et la reprise.
- La reprise est liée au mode (`match`) en plus de l'analyse, de la génération, du préfixe et du type ; elle est refusée si le mode change entre deux pages.
- Servi par un index borné (une entrée par début de segment) à côté de l'index actuel, avec migration testée. Une analyse antérieure sans cet index le dit (`NOT_AVAILABLE`) au lieu de rendre une liste vide.
- Plusieurs résultats restent plusieurs candidates : c'est le consommateur, ou l'utilisateur, qui choisit, jamais le moteur (§ 4.3).

**Tests :** les deux exemples exacts ci-dessus, une clé aux segments répétés (rendue une seule fois), un changement de mode refusé à la reprise, une analyse sans index (`NOT_AVAILABLE`), le mode `KEY` inchangé.

### 4.2. Sortie : Tuile et frontière

La réponse expose, avec le nommage concret validé par tests :

| Information obligatoire | Invariant |
| --- | --- |
| `analysis` / instantané | Identifiant de l'analyse utilisée ; aucune dérive entre recherche, Tuile et vérification. |
| `root` / centre | Référence effectivement résolue, sans substitution silencieuse. |
| `nodes` / références | Références retournées et leurs identités typées si disponibles. |
| `facts` | Relations établies dans la Maille, avec le statut porté par le fait, sans perte : `OBSERVED`, `INFERRED` ou `HUMAN_VALIDATED` (avec ses métadonnées de validation). |
| `evidence` / provenance | Identifiants ou références de preuves accessibles selon les droits ; pas de « citation » sans preuve existante. |
| `coverage` | Ce qui a été analysé, selon quel périmètre / évaluateur lorsque cette information existe. |
| `frontier` | Les limites et zones inconnues, ambiguës, non supportées ou hors périmètre, sans les convertir en absences factuelles. |
| `bounds` et troncature | Budgets effectifs appliqués, indicateur de résultats non envoyés et information de continuation si supportée. |

La Tuile est **autodescriptive** : ses champs permettent à un consommateur de distinguer une conclusion appuyée, une lacune de couverture et un résultat tronqué. Les noms de champs dans le tableau expriment les **exigences sémantiques** : le schéma JSON définitif est à relever/figer en PR A sur les structures existantes, sans renommer gratuitement le domaine de la Maille.

**Continuation :** si le moteur fournit un mécanisme de reprise, l'adaptateur l'expose sans l'inventer ; si ce mécanisme manque pour une expression, la Tuile indique honnêtement `truncated` et la limite. Le récit ne présume pas qu'un curseur fonctionnel existe dans tous les chemins d'exécution.

### 4.3. Résultats et erreurs

- **Référence absente :** indiquer l'absence de correspondance **dans l'analyse interrogée**, sans déclarer que le symbole n'existe pas dans le dépôt.
- **Plusieurs références :** `AMBIGUOUS` et candidates accessibles ; aucun choix automatique opaque.
- **Relation non interprétée :** frontière explicite, jamais relation fabriquée.
- **Analyseur non disponible / périmètre exclu :** distinguer `UNSUPPORTED` de `OUT_OF_SCOPE`, conformément aux conventions existantes.
- **Requête invalide :** erreur de protocole explicite (par exemple `INVALID_ARGUMENT` si c'est le code existant approprié), **pas** une frontière de connaissance ; une correction puis une nouvelle requête sont possibles.
- **Erreur d'autorisation, d'accès ou de budget :** réponse contrôlée sans fuite de détails ni contournement des garde-fous.

Le registre des catégories établi par TAXO-01M reste l'autorité. **Aucune nouvelle catégorie n'est créée par simple commodité d'interface.**

### 4.4. Sécurité et consommation externe

- MIP est **lecture seule** dans ce récit ; aucune écriture dans le dépôt, aucun lancement d'analyse, aucun accès arbitraire au système de fichiers.
- La disponibilité de `POST /api/projects/{project_id}/mip/query` **n'autorise pas** une exposition publique sans authentification/autorisation. Les droits de lecture d'un projet, la validation d'identité et les budgets s'appliquent avant la consultation des données ; par défaut, ne pas élargir la surface réseau existante.
- Toute lecture de diff ou de code source suit les consentements et restrictions **déjà en vigueur** ; MIP 0.1 n'ajoute pas `get_source`.
- Les contenus provenant du dépôt sont des **données non fiables**, jamais des instructions de protocole ou de système pour Minia.
- Les journaux ne doivent pas conserver par défaut les réponses, les contenus potentiellement sensibles ou les secrets. Annulation et quotas existants ne sont pas affaiblis.

## 5. Intégration d'Ask Taxo et de Minia

### 5.1. Une entrée utilisateur, deux capacités complémentaires

**Sans Minia :**

- Les sélections de commits existantes continuent de fonctionner comme avant.
- Une référence explicitement identifiée peut ouvrir directement une Tuile MIP et/ou l'Explorer centré sur cette référence.
- Une question vague sans référence exploitable n'entraîne pas d'interprétation probabiliste cachée ; TAXO explique comment préciser le symbole ou utiliser Minia.

**Avec Minia :**

- Minia découvre les opérations autorisées avec `describe` ; elle trouve une référence par `find_references`, puis demande une Tuile via le service MIP / l'adaptateur existant.
- Minia ne relit pas le dépôt et ne produit aucun fait de la Maille. Elle peut formuler des interprétations signalées comme telles.
- L'expérience reste une seule entrée « Interroger Taxo », avec exemples pour commits, structures, appels, routes, technologies et dépendances.

**Aucune obligation d'interprétation linguistique générale sans LLM** n'est ajoutée. La consultation directe d'une référence structurée n'est pas un deuxième moteur de langage naturel.

### 5.2. Correction de l'exploration

Remplacer le verrou des huit arguments à plat (`subject`, `relation`, `object`, `nature`, `fact`, `scope`, `commit`, `path`) par un **champ de transport stable `arguments`**, encodant un objet JSON pour conserver la compatibilité avec les fournisseurs qui attendent un schéma de tour plat.

- Décoder l'objet, limiter sa taille, refuser les erreurs JSON et les types incohérents.
- Transmettre tous les champs de l'objet : un champ que l'opération ne déclare pas est **refusé** par sa validation existante (`INVALID_ARGUMENT`), jamais ignoré, car une faute de frappe sur un filtre facultatif rendrait sinon une requête plus large qui semblerait réussir. Minia corrige l'appel au tour suivant.
- Laisser le moteur TAXO valider les arguments et les droits de l'opération ; aucun assouplissement du protocole `taxo-query/1`.
- Préserver les garde-fous d'exploration actuels : **8 opérations choisies, 10 affirmations vérifiées et budgets d'octets**.
- Garder les non-régressions sur les questions de commits.

**État :** le champ `arguments` est livré par la PR #108 (en revue, non fusionnée) : objet JSON écrit en chaîne, types JSON conservés, refus explicite de ce qui n'est pas un objet, garde-fous 8/10 inchangés, questions de commits non régressées, et un essai scénarisé « trouver un élément par son nom puis lire son voisinage » (`describe` → `find_references` → `get_neighborhood` → affirmation `CONTAINS` confirmée). Le moteur valide déjà chaque argument (`INVALID_ARGUMENT`). Restent pour la PR B : la limite de taille de l'objet et des tests qui prouvent le refus d'un champ non déclaré pour chaque opération.

### 5.3. Repli paquet sans invention

Lorsqu'un fournisseur ne peut pas explorer ou lorsqu'une exploration échoue :

1. Rechercher **déterministement** des ancres explicites dans la question ; privilégier une identité canonique ou une référence complète.
2. Tester les ambiguïtés et les faux positifs de la recherche littérale : un préfixe `findById` ne garantit pas de retrouver une référence canonique commençant par `method:...`.
3. Pour une ancre unique, obtenir une Tuile bornée et fournir son contexte au modèle ; le repli n'ouvre jamais toute la Maille.
4. Sans ancre ou avec ambiguïté, répondre `unknown` de façon utile, sans sélection de commits imposée ni choix arbitraire.
5. Une formulation produite par le modèle en mode paquet **n'est pas confirmée par le seul fait qu'elle cite correctement une référence**. Les faits peuvent être affichés tels quels ; une affirmation interprétative doit être vérifiée par TAXO ou rester explicitement non prouvée.

Le mécanisme existant `verify_claim` reste l'autorité des **verdicts** dans MIP 0.1. La création de nouvelles commandes MIP `CLAIM`, `CHECK`, `NEED` ou `VERDICT` n'est **pas** requise par ce récit ; une éventuelle extension ultérieure devra être décidée séparément.

## 6. Découpage en PR autonomes

### PR A — MIP 0.1 : contrat et service de lecture

**Livrer :** spécification versionnée du contrat sémantique, validateur d'entrée, adaptateur applicatif réutilisant le moteur existant, premier adaptateur HTTP `POST /api/projects/{project_id}/mip/query` contrôlé par les mêmes droits et limites, réponses en Tuiles bornées avec couverture/frontières/instantané ; aucun LLM requis.

**Avant de coder, le développeur doit documenter :** les chemins réels du moteur et de la Tuile, le schéma effectif de `neighborhood/2`, les structures de `frontier`/`coverage`, l'existence et les limites réelles de la continuation, les champs pouvant être mappés sans perte. Les écarts substantiels sont soumis au responsable du produit avant un changement de contrat.

**Tests :** requête valide, identité inconnue, ambiguïté, type/périmètre refusé, profondeur et budgets, troncature, provenance, même analyse du début à la fin, absence de LLM, droits d'accès et non-exposition involontaire. `taxo-query/1` reste inchangé et vert.

### PR A2 — Recherche par nom

**Livrer :** l'extension `match: NAME` de `find_references` décrite au § 4.1 bis, avec son index et sa migration. Indépendante de la PR A ; nécessaire à la PR B (repli), à la PR C (référence reconnue) et à la démonstration.

### PR B — Minia : exploration générale et repli paquet

**Livrer :** fin du transport d'arguments génériques et contrôlés (la base est la PR #108, § 5.2), recherche de références, appel au service MIP pour obtenir la Tuile, repli déterministe non limité à Git, vérification explicite des affirmations dans tous les modes.

**Tests :** fournisseur scénarisé « qui appelle X ? » : recherche → Tuile → `CALLS` → `verify_claim` ; cas `AMBIGUOUS`, aucun symbole, frontière non interprétée, modèle local incapable d'explorer, argument invalide, consigne hostile dans des données, budget dépassé, arrêt de demande, non-régression Git. Aucun résultat inventé.

### PR C — Portail : Interroger Taxo / Explorer

**Livrer :** interface unique avec exemples historiques et structurels, consultation directe d'une Tuile lorsqu'une référence est reconnue, mode Minia facultatif, liens vers l'Explorer centrés sur les références, présentation intelligible des faits et des frontières.

**Tests :** parcours utilisateur sans Minia, avec Minia, commits inchangés, ambiguïté, aucune preuve, Tuile tronquée, lien de référence valide, erreurs lisibles, accessibilité élémentaire. Aucun type Java ou relation Spring codé en dur dans la logique de présentation ; les capacités proviennent des descriptions du système.

### PR D — Mesures, robustesse et clôture

**Livrer :** banque de questions avec vérité indépendante établie à la main sur les fixtures `bibliotheque` et `spring-petclinic`, résultats par fournisseur et en mode TAXO seul, mesures de latence et limites publiées.

**Mesurer au minimum :** répondu, confirmé, non prouvé, inconnu/ambigu, repli, erreur ; temps total, temps fournisseur, nombre de tours LLM, opérations TAXO, taille des Tuiles, troncature, couverture et nombre d'affirmations réellement vérifiées.

**Clôture :** comparaison avant/après sur questions Git et structure, limites connues, compatibilité de l'API, synthèse de tests et documentation de prise en main du premier client MIP sans LLM.

## 7. Critères d'acceptation transversaux

1. Un client **sans Minia** appelle MIP 0.1 et reçoit une Tuile valide d'une analyse identifiée, sans modèle configuré.
2. `EXPAND` a une sémantique déterministe, documentée et testée ; `PROJECT`, non servie en 0.1, est refusée honnêtement par une erreur de protocole.
3. Une Tuile contient ou signale explicitement ses preuves, sa couverture, ses frontières et sa troncature ; aucune lacune ne se transforme en fait.
4. Recherche, construction de Tuile et validation des affirmations portent sur **le même instantané**.
5. Une référence ambiguë ne donne pas lieu à un choix implicite ; une référence introuvable ne prouve pas l'inexistence de l'élément. `VetController` et `OwnerRepository.findById` sont retrouvés par leur nom (§ 4.1 bis).
6. Tous les champs envoyés aux opérations TAXO passent leurs validations existantes ; `taxo-query/1` n'est ni modifié ni contourné silencieusement.
7. Une affirmation affichée comme **confirmée** a un verdict de TAXO ; une interprétation de Minia reste identifiée, y compris en mode paquet.
8. Les questions historiques conservent leur comportement et leurs résultats attendus.
9. Le consommateur ne peut ni dépasser les budgets et autorisations, ni déclencher une lecture de source/diff interdite, ni écrire au dépôt.
10. Les résultats qualitatifs **et** de performance sont publiés, même si certains fournisseurs donnent des réponses médiocres.

## 8. Hors périmètre explicite

- Nouvel évaluateur ou nouvelle relation (lambdas Java, Python, Spring Batch, etc.).
- Nouveau moteur de graphe, nouvelle base, duplication de la Maille, réanalyse automatique et relecture de dépôt par Minia.
- Recherche sémantique, embeddings, moteur NLP déterministe général, conversations persistantes.
- Collaboration multi-LLM, Taxo Lab, consensus de modèles, nouvelles commandes MIP de dialogue ou d'écriture.
- `get_source`, activation des opérations réservées (`find_callers` et autres), modification des autorisations de diff.
- Arbre (étape suivante du PLAN), mise en service publique non sécurisée, framework MCP ou autre transport supplémentaire.
- Décisions de doctrine, refonte massive du protocole `taxo-query/1` et modifications irréversibles sans accord du responsable du produit.

## 9. Risques identifiés et traitement

| Risque | Mesure exigée |
| --- | --- |
| Construire deux moteurs parallèles | MIP comme adaptateur sur les primitives existantes ; tests de parité sur faits et frontières. |
| Appels LLM séquentiels coûteux | Préparation locale déterministe de Tuiles, repli à faible nombre de tours, télémétrie par tour. |
| Recherche de références insuffisante | Vérifier préfixes canoniques, identités courtes, homonymes et ambiguïtés avant d'annoncer le succès. |
| Faux sentiment de preuve | Distinguer citation, fait, vérification de l'affirmation et interprétation ; ne pas déduire de l'absence de réponse une absence de code. |
| Glissement entre analyses | Figer l'identifiant d'analyse à l'ouverture et le réutiliser dans toutes les étapes. |
| Fuite de code ou de secrets | Aucun nouvel accès source ; authentification, autorisation et budgets inchangés ou renforcés. |
| Dérapage de V2 | Pas d'extensions hors périmètre ; des PR bornées, chacune vérifiable. |

## 10. Gouvernance, ordre et condition de démarrage

- **D'abord :** faire relire et valider ce récit par le responsable du produit. Ce texte constitue une proposition de contrat, pas une approbation rétroactive de modifications de l'API.
- **Avant chaque PR :** annoncer le plan (fichiers, comportements modifiés, tests, non-touchés), identifier les écarts éventuels à la doctrine, puis rester dans le périmètre autorisé.
- **Ordre :** A → A2 → B → C → D (A2 peut avancer en parallèle de A) ; pas de dépendance artificielle sur des travaux futurs V3. Les quatre tranches sont testables et revues séparément.
- **Traçabilité :** récit `.md`, branche nommée d'après le récit, commits propres, tests obligatoires, CI verte ; aucun fichier généré suivi sans justification.
- **Décisions majeures :** toute modification du contrat/protocole, des droits, des limites de sécurité ou du périmètre doit recevoir l'accord préalable du responsable du produit.
- **Fusions :** jamais sans accord explicite du responsable du produit, même si CI et revues sont vertes ; aucun silence ne vaut approbation.
- **Clôture :** déplacer le récit parmi les récits terminés après vérification des critères et décision explicite du responsable du produit.

## 11. Démonstration finale demandée

Sur une fixture connue :

1. Sans LLM, un client MIP demande `EXPAND` sur une méthode connue et reçoit une Tuile bornée, ses `CALLS` et ses preuves, avec un identifiant d'analyse.
2. Une demande ambiguë affiche des candidates et ne choisit personne arbitrairement.
3. Une frontière `NOT_INTERPRETED`/`OUT_OF_SCOPE` est montrée honnêtement, sans fait fabriqué.
4. Avec Minia, « Qui appelle cette méthode ? » fait retrouver la référence, consulter la Tuile et vérifier chaque affirmation affichée comme confirmée.
5. Avec un petit modèle ou en repli, la réponse utilise au plus une génération d'interprétation sur un contexte borné lorsque possible ; les limites de vérification restent visibles.
6. Les anciennes questions sur les trois derniers commits donnent les mêmes résultats attendus qu'avant.
7. Le tableau de mesures montre temps, appels, couverture, vérification et échecs réels.

### Définition de terminé

**MIP 0.1 est livré lorsque TAXO peut transporter une Tuile bornée, vérifiable et honnête à un consommateur sans LLM, puis offrir cette même connaissance à Minia et Ask Taxo sans reconstruire le moteur ni affaiblir ses garanties.**

---

**Note de cadrage :** les invariants du MIP rappelés ici proviennent des décisions d'équipe déjà discutées ; le **format JSON exact et le mapping exhaustif des champs de Tuiles** sont des éléments **à figer** ; les règles de `PROJECT` attendent une décision ultérieure sur le code existant en PR A. Le présent récit ne les présente pas comme des API déjà livrées.

## 12. Ajustements à l'acceptation (9 octobre 2026)

Ce texte remplace une première version de TAXO-01N, centrée sur Ask Taxo. Il a été accepté avec ces ajustements :

1. **`EXPAND` seul servi en MIP 0.1** ; `PROJECT` est refusée tant qu'aucune règle de projection servie n'existe (§ 4.1).
2. **Recherche par nom ajoutée** (§ 4.1 bis, PR A2) : sans elle, les exemples du récit ne sont pas atteignables.
3. **La correction de l'exploration (§ 5.2) est la PR #108**, déjà proposée.
4. **`run_plan` abandonné.** La première version prévoyait une opération `run_plan` (exécution locale d'un plan borné d'opérations, en un seul tour). Elle n'est plus dans ce récit : `EXPAND` porte l'exploration bornée côté TAXO, et un nouveau plan d'opérations serait un second langage de requête. Elle pourra revenir comme décision séparée si les mesures de la PR D montrent que le nombre de tours LLM reste le goulot.
5. Le nom filaire ne change pas : `taxo-query/1` reste la première version filaire sous le MIP.
