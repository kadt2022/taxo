# TAXO-01B — Références stables et identité canonique — TERMINÉ

**Statut : TERMINÉ — implémentation terminée et tests validés ; revue PR et intégration dans `main` en attente.**  
**Parent : EPIC TAXO-01 — Fondation de la mémoire logicielle vérifiable**  
**Dépend de : TAXO-01A — Contrat machine du fait**  
**Références : ADR 0001, ADR 0002**

## Vérification de l'implémentation

Reprise du travail commencé par Crochet (interrompu par sa limite d'usage), audité puis complété.

- Identité canonique : `identity_fields()` et `fact_identity()` dans `backend/app/facts/contract.py`.
- Vecteurs portables : `backend/app/facts/conformance/identity/identity-vectors-v1.json`, 19 positifs et 5 négatifs.
- Référence RFC 8785 : 6 documents de l'implémentation de référence dans `backend/tests/fixtures/jcs-reference` ; le corpus numérique de 10 000 valeurs n'est pas retenu.
- `python -m pytest -q` dans `backend` : 287 tests réussis.
- `python -m compileall -q app` : réussi.
- `python -m app.facts --conformance` : 76 faits, 8 vecteurs d'empreinte, 19 vecteurs d'identité et 5 négatifs, aucune divergence.

## Récit

En tant que **Taxo**, je veux disposer d'une représentation canonique et d'une identité stable pour chaque fait afin qu'une même affirmation produise la même identité indépendamment du commit, de l'occurrence, de l'ordre des champs ou de la plateforme d'exécution.

Cette identité doit être reproductible par plusieurs implémentations — notamment Python aujourd'hui et JVM demain — sans dépendre d'une convention implicite propre à un langage.

TAXO-01B prolonge le contrat introduit par TAXO-01A. Il ne crée pas une seconde représentation de l'identité : il **étend et finalise `identity_fields()`** déjà introduit dans 01A.

```text
TAXO-01A
Contrat machine du fait
        │
        ▼
TAXO-01B
┌────────────────────────────────────────┐
│ Références syntaxiquement canoniques   │
│ Scope canonique                        │
│ Identité canonique                     │
│ Empreinte stable et versionnée         │
│ Vecteurs interlangages                 │
└────────────────────────────────────────┘
        │
        ▼
TAXO-01C
Instantané Git au commit
```

---

## 1. Principe : canonicalisation syntaxique, pas équivalence sémantique

La canonicalisation garantit qu'une même représentation **syntaxiquement équivalente** produit la même forme canonique.

Elle ne doit pas prétendre reconnaître des équivalences métier ou sémantiques.

Par exemple, Taxo ne doit pas décider dans ce récit que :

```text
endpoint:GET /api/orgs/{orgId}
```

et :

```text
endpoint:GET /api/orgs/{id}
```

désignent nécessairement le même endpoint.

Cette éventuelle équivalence relève d'un évaluateur ou d'une projection future, pas de la canonicalisation des références.

---

## 2. Références canoniques

TAXO-01A définit les références sous la forme :

```text
type:clé
```

Exemples :

```text
repository:takibo-iam
module:takibo-security-management
file:backend/app/main.py
symbol:java:com.takibo...OAuthClientController#register
endpoint:POST /api/v1/orgs/{orgId}/spaces/{spaceId}/clients
```

TAXO-01B définit leur forme canonique.

### Règle générale v1

**01B ne "répare" pas une référence invalide.**

Une référence qui ne respecte pas TAXO-01A doit être refusée par le contrat.

En particulier :

- `\` dans un chemin reste refusé ;
- les chemins absolus restent refusés ;
- `.` et `..` comme segments restent refusés ;
- les chemins non conformes ne sont pas transformés silencieusement ;
- aucune normalisation métier supplémentaire n'est introduite implicitement.

La canonicalisation ne s'applique qu'à une valeur déjà valide selon TAXO-01A.

---

## 3. Unicode

Toute chaîne participant à l'identité doit être normalisée en **Unicode NFC** avant sérialisation canonique.

Objectif : empêcher qu'un même texte accentué produise deux identités différentes selon la représentation Unicode utilisée par le système de fichiers ou la plateforme.

Exemple :

```text
é
```

encodé sous forme NFC ou NFD doit produire la même identité après canonicalisation.

Cette règle s'applique aux chaînes contenues dans les champs d'identité, y compris les valeurs textuelles des `qualifiers`.

Elle s'applique aussi aux **clés** des `qualifiers`. Si deux clés d'un même objet deviennent identiques après NFC, le fait est **refusé** : aucune des deux valeurs n'est choisie arbitrairement.

Ordre obligatoire des opérations : **NFC, puis suppression des doublons, puis tri**.

Limite acceptée : deux fichiers dont les noms ne diffèrent que par leur forme NFC ou NFD (possible sous Linux) ont la même identité.

---

## 4. Règles par type de référence

En v1, Taxo ne doit pas inventer de transformations supplémentaires non prévues par le contrat.

Par conséquent :

- la casse d'une clé n'est pas modifiée sauf décision explicite de l'ADR ;
- la méthode HTTP n'est pas réécrite silencieusement ;
- un `/` final d'endpoint n'est pas ajouté ni retiré automatiquement ;
- les noms de technologies ne sont pas passés en minuscules ;
- les symboles ne sont pas raccourcis ;
- les identifiants métier restent tels qu'ils ont été validés.

TAXO-01B garantit une forme canonique de sérialisation, pas une normalisation métier arbitraire.

Toute nouvelle règle de transformation par type devra être ajoutée explicitement au contrat ou à un ADR.

---

## 5. Périmètre canonique

Le `scope` participe à l'identité des faits `ABSENCE` et `COVERAGE`.

Deux scopes syntaxiquement équivalents doivent produire la même forme canonique.

Exemple :

```json
{
  "include": [
    "module:b",
    "module:a",
    "module:a"
  ],
  "exclude": []
}
```

doit produire la même forme canonique que :

```json
{
  "include": [
    "module:a",
    "module:b"
  ]
}
```

### Règles obligatoires

La canonicalisation du scope doit :

- canonicaliser chaque référence ;
- supprimer les doublons ;
- trier `include` et `exclude` par **unités de code UTF-16** (l'ordre de RFC 8785 pour les clés et de `String.compareTo` en Java), et non par code points comme le `sorted()` de Python ;
- conserver la distinction entre `include` et `exclude` ;
- considérer `exclude: []` et l'absence de `exclude` comme équivalents ;
- ne jamais modifier la signification du périmètre.

---

## 6. Identité stable du fait

L'identité représente **ce que le fait affirme**, pas l'occurrence où il a été observé.

Les champs d'occurrence ne participent donc jamais à l'identité :

```text
snapshot
commit
evidence
validity
status
producer_version
catalog_version
execution_id
validation.validated_at
```

### ASSERTION

Identité :

```text
kind
subject canonique
relation
object canonique ou littéral canonique
qualifiers canoniques
```

### ABSENCE

Identité :

```text
kind
pattern canonique
scope canonique
method
```

### COVERAGE

Identité :

```text
kind
subject canonique
coverage_type
scope canonique
producer_id
```

Le `producer_id` fait partie de l'identité d'une `COVERAGE`, conformément à ADR 0002.

---

## 7. Extension de `identity_fields()`

TAXO-01A possède déjà `identity_fields()`.

TAXO-01B doit :

- conserver cette frontière publique ;
- l'étendre pour produire les champs d'identité correctement canonicalisés ;
- ne pas introduire une seconde fonction concurrente qui calcule une autre identité ;
- maintenir la compatibilité avec les usages existants du contrat.

Répartition v1 :

- `identity_fields(fact)` renvoie les champs d'identité canoniques ;
- `fact_identity(fact)` renvoie l'empreinte `sha256:…`, calculée uniquement à partir de `identity_fields(fact)`.

Toute autre fonction nécessaire à la canonicalisation reste un détail d'implémentation.

---

## 8. Sérialisation canonique interlangage

L'identité doit être sérialisée de façon déterministe et reproductible entre Python et JVM.

Un simple :

```python
json.dumps(..., sort_keys=True)
```

ne constitue pas à lui seul un contrat interlangage suffisant, notamment pour certaines représentations numériques.

La sérialisation canonique doit donc suivre une norme explicite.

### Référence v1

Utiliser **RFC 8785 — JSON Canonicalization Scheme (JCS)**, ou démontrer une implémentation strictement équivalente pour le sous-ensemble JSON accepté par le contrat.

La représentation canonique doit notamment garantir :

- ordre déterministe des propriétés ;
- UTF-8 ;
- absence d'espaces non significatifs ;
- représentation déterministe des nombres ;
- traitement déterministe des chaînes ;
- structures imbriquées canoniques.

Si une bibliothèque JCS est ajoutée, elle doit être légère, maintenue et compatible avec le projet.

L'implémentation doit aussi passer les jeux de test publiés avec l'implémentation de référence de RFC 8785, en plus des vecteurs Taxo.

### Nombres dans les champs d'identité

JCS sérialise les nombres comme des flottants double précision (IEEE 754). En conséquence :

- un entier hors de l'intervalle ±(2^53 − 1) est **refusé** : il ne peut pas être représenté de façon identique en Python et en JVM ;
- `1` et `1.0` produisent la même forme canonique ;
- `-0` produit `0`.

---

## 9. Domaine d'identité versionné

L'empreinte ne doit pas dépendre uniquement du JSON canonique.

Un domaine/version explicite doit participer au calcul afin qu'une future évolution du contrat d'identité ne réinterprète pas silencieusement les anciennes empreintes.

Version v1 :

```text
taxo-fact-identity/v1
```

Forme conceptuelle :

```text
SHA-256(
  "taxo-fact-identity/v1\n"
  + canonical_identity_json
)
```

La représentation exacte doit être documentée et couverte par des vecteurs de test.

---

## 10. Empreinte d'identité

Taxo expose l'identité sous la forme :

```text
sha256:<64 caractères hexadécimaux minuscules>
```

La même identité doit produire la même empreinte :

- sur deux exécutions ;
- après redémarrage ;
- sur Windows, Linux et macOS ;
- sur deux commits différents ;
- en Python et dans une future implémentation JVM ;
- quel que soit l'ordre initial des propriétés JSON ;
- quel que soit l'ordre initial des éléments du scope lorsque leur ordre n'est pas sémantique ;
- quelle que soit la représentation NFC/NFD initiale d'une même chaîne.

Un changement d'un champ participant réellement à l'identité doit produire une identité différente.

---

## 11. Vecteurs d'identité interlangages

Ajouter une suite de vecteurs versionnés sur le modèle de :

```text
hash-vectors.json
```

de TAXO-01A.

Par exemple :

```text
identity-vectors-v1.json
```

Chaque vecteur doit contenir :

- une entrée valide ;
- l'identité canonique attendue ;
- l'empreinte SHA-256 attendue ;
- une courte raison du cas couvert.

Les vecteurs doivent être utilisables sans Python par une future implémentation JVM.

### Cas minimaux

Les vecteurs doivent couvrir au minimum :

1. ASSERTION simple ;
2. ABSENCE avec scope ;
3. COVERAGE avec `producer_id` ;
4. propriétés JSON fournies dans un ordre différent ;
5. `include` dans un ordre différent ;
6. doublons dans `include` ;
7. `exclude: []` versus `exclude` absent ;
8. objets imbriqués dans `qualifiers` ;
9. valeurs numériques autorisées dans `qualifiers` ;
10. chaîne Unicode NFC versus NFD ;
11. occurrence différente, identité identique ;
12. changement réel d'objet ou de qualifier, identité différente ;
13. tri UTF-16 : `𝒜` (U+1D49C) et `Ａ` (U+FF21) dans un même `include` ;
14. `1` versus `1.0`, et `-0`, dans `qualifiers`.

Des **vecteurs négatifs** accompagnent ces cas : chaque entrée doit être refusée par toute implémentation, avec la raison attendue. Au minimum : chemin contenant `\`, entier hors de ±(2^53 − 1), clés de `qualifiers` en collision après NFC.

---

## 12. Tests obligatoires

Les tests doivent prouver au minimum que :

1. deux références valides syntaxiquement équivalentes ont la même forme canonique ;
2. une référence invalide selon 01A est refusée, pas réparée ;
3. deux scopes contenant les mêmes références dans un ordre différent ont la même forme canonique ;
4. les doublons du scope ne modifient pas l'identité ;
5. `exclude: []` et `exclude` absent produisent la même identité ;
6. deux occurrences du même fait sur deux commits différents ont la même identité ;
7. modifier uniquement `evidence` ne modifie pas l'identité ;
8. modifier uniquement `execution_id` ne modifie pas l'identité ;
9. modifier uniquement `producer_version` ou `catalog_version` ne modifie pas l'identité ;
10. modifier le sujet, la relation, l'objet ou les qualifiers pertinents modifie l'identité ;
11. deux `COVERAGE` identiques sauf `producer_id` ont des identités différentes ;
12. NFC et NFD d'une même chaîne produisent la même identité ;
13. les vecteurs d'identité produisent exactement la même valeur attendue ;
14. le préfixe `taxo-fact-identity/v1` participe effectivement au calcul ;
15. `include` et `exclude` sont triés par unités de code UTF-16 ;
16. un entier hors de ±(2^53 − 1) est refusé ;
17. des clés de `qualifiers` en collision après NFC sont refusées ;
18. les vecteurs négatifs sont refusés avec la raison attendue ;
19. `fact_identity()` est calculée uniquement à partir de `identity_fields()` ;
20. la suite TAXO-01A `--conformance` reste entièrement verte.

---

## 13. Critères d'acceptation

Le récit est fonctionnellement terminé lorsque :

```text
[ ] les références valides disposent d'une forme canonique déterministe
[ ] aucune référence invalide n'est réparée silencieusement
[ ] le scope dispose d'une forme canonique
[ ] exclude absent == exclude []
[ ] Unicode est normalisé en NFC
[ ] identity_fields() existant est étendu, pas dupliqué
[ ] l'identité des ASSERTION est stable
[ ] l'identité des ABSENCE est stable
[ ] l'identité des COVERAGE est stable
[ ] le domaine taxo-fact-identity/v1 est utilisé
[ ] une empreinte SHA-256 stable est produite
[ ] la sérialisation est interlangage et documentée
[ ] des vecteurs d'identité versionnés existent, positifs et négatifs
[ ] include et exclude sont triés par unités UTF-16
[ ] les entiers hors de ±(2^53 − 1) sont refusés
[ ] les clés de qualifiers en collision après NFC sont refusées
[ ] tous les tests 01B sont verts
[ ] toute la conformité 01A reste verte
```

---

## 14. Hors périmètre

Ne pas profiter de TAXO-01B pour implémenter :

- scan asynchrone ;
- correction du timeout HTTP ;
- workers ;
- file d'attente ;
- polling du portail ;
- changement du modèle SQL des scans ;
- snapshot Git ;
- parcours des seuls fichiers suivis par Git ;
- JavaParser ;
- TypeScript Compiler API ;
- analyse Spring Boot ;
- endpoints/controllers ;
- Spring Security ;
- graphe d'appels ;
- RBAC ;
- persistance des faits ;
- comparaison entre commits ;
- invalidation `STALE` ;
- projection Ask Taxo ;
- exécution de code provenant du dépôt analysé.

Le problème de timeout sera réévalué après TAXO-01C avec une mesure réelle de TAKIBO dans Docker.

---

## 15. Préparation de TAXO-01C

TAXO-01C introduira l'instantané Git au commit et devra analyser le contenu réellement suivi par Git plutôt que le working tree non borné par l'index.

TAKIBO-IAM servira de banc de mesure.

Mesure de référence observée avant 01C :

```text
working tree parcouru : 7 188 fichiers
.gradle-user          : 3 719 fichiers
.claude               : 1 122 fichiers
fichiers suivis Git   : ~1 109
scan natif            : ~12,7 s
proxy nginx           : 120 s
```

Ces mesures sont des observations de départ, pas des critères contractuels immuables.

Après TAXO-01C :

1. mesurer le scan de TAKIBO dans Docker Desktop ;
2. vérifier le nombre de fichiers réellement analysés ;
3. mesurer le temps total ;
4. décider sur données réelles si un scan asynchrone est encore nécessaire avant ou avec TAXO-01D.

---

## Définition de terminé

Le récit peut être déplacé dans `Terminé` dès que **toutes les fonctionnalités, règles, critères d'acceptation et tests de TAXO-01B sont implémentés et validés**.

Le statut **Terminé** ne signifie pas **mergé**.

Un récit terminé peut rester en PR pendant la revue.

Si la PR est refusée ou abandonnée, le récit **sort de `Terminé`** et reprend le statut À FAIRE.

Le merge dans `main` est une étape distincte et n'a lieu qu'après :

- CI complète verte ;
- Sonar Quality Gate vert ;
- commentaires de revue corrigés ou résolus ;
- absence de blocage restant sur la PR.

Démonstration minimale attendue :

```text
même fait, commit A
→ sha256:ABC...

même fait, commit B
→ sha256:ABC...

même identité avec ordre JSON différent
→ sha256:ABC...

même texte, NFC ou NFD
→ sha256:ABC...

objet ou qualifier réellement modifié
→ sha256:XYZ...
```
