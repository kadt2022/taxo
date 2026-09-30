# TAXO-01E — Mémoire versionnée des faits

Statut : rédigé le 2026-09-30. Priorité active du plan ([PLAN](PLAN.md)), avant la comparaison
persistée (01F) et la suite des Tuiles.

Source de vérité : [ARCHITECTURE § 5.2, § 5.5, § 8 et § 15](../ARCHITECTURE.md). En cas de divergence,
le document cible prévaut.

Dépend de : contrat du fait v1, identité canonique, stockage des faits par analyse, première tranche de
`get_neighborhood`, tous livrés. Validation : fixtures synthétiques, jamais Taxo jugeant Taxo.

## Pourquoi maintenant

La dette est connue et assumée dans le code. `scans/infrastructure/sqlalchemy/fact_store.py` le dit :

```text
Ce n'est pas la memoire versionnee de TAXO-01E : les faits restent attaches a l'analyse qui les a produits.
```

Aujourd'hui, `add()` écrit une ligne complète par fait et par analyse : le JSON contractuel entier,
preuves et provenance comprises, plus deux clés d'ordre en texte, deux empreintes et deux rangs. Les
index d'adjacence de la première Tuile sont eux aussi rangés par `scan_id`.

```text
analyse A ─► copie du fait X
analyse B ─► copie du fait X
analyse C ─► copie du fait X
```

Sur une base locale réelle, la migration 003 a repris 849 814 occurrences réparties en 36 analyses.
Ce chiffre est constaté. **La part d'identités réellement répétées entre analyses ne l'est pas** : le
taux de déduplication est un résultat à mesurer par ce récit, pas une hypothèse d'acceptation.

Ce récit ne crée pas de concept. Il termine une décision déjà inscrite au contrat : **identité ≠
occurrence** (ARCHITECTURE § 5.2). Son utilité se démontre ensuite par 01F : comparer deux analyses
sans relire le dépôt.

## Ce qui existe et est réutilisé, pas reconstruit

| Besoin | Existant |
| --- | --- |
| Identité canonique | `app/facts/domain/identity.py` : `canonical_identity`, domaine `taxo-fact-identity/v1`, NFC, RFC 8785, SHA-256 |
| Champs d'identité par nature | ARCHITECTURE § 5.2 (assertion, absence, couverture avec identifiant du producteur) |
| Clés d'ordre du voisinage | `app/scans/domain/fact_order.py` : `adjacency_keys` (référence, identité, empreinte d'occurrence) |
| Port de stockage | `AnalysisFacts` (`scans/application/ports.py`) : `add`, `query`, `revision`, `has_reference`, `neighbor` |
| Consommateurs du port | analyse globale, lecture filtrée HTTP, page Routes, protocole `taxo-query/1`, projection Git, `get_neighborhood` |
| Leçons de migration | 003 : reprise idempotente, lots, progression visible |

## Constat qui oriente le modèle

Une occurrence ne diffère pas seulement par son statut ou sa preuve. D'après le contrat (§ 5.5) :

- chaque preuve porte `repository` et `commit`, ceux de l'instantané ;
- chaque fait porte `snapshot` et `produced_by`, dont `execution_id` pour un évaluateur.

Le même fait analysé sur deux commits a donc deux JSON différents, même si rien n'a bougé dans le code.
Séparer la seule identité ne ferait gagner que les champs d'identité. Un gain réel suppose aussi de
ranger **au niveau de l'analyse** ce qui y est constant (instantané, exécutions des producteurs) et de
reconstruire le fait contractuel à la lecture. Cette reconstruction devient la garantie centrale du récit.

## Modèle cible (décidé)

```text
FACT_IDENTITY                          ANALYSIS (existant : scans, à compléter)
─────────────────────                  ─────────────────────────────
identity_hash  PK                      analysis_id
kind                                   snapshot (repository, commit, mode…)
subject, relation, object                      │ 1
qualifiers / pattern / scope / method          │ N
coverage_type, producer_id (couverture)        ▼
        1                              PRODUCER_EXECUTION
        │ N                            ─────────────────────────────
        ▼                              analysis_id, execution_id
FACT_OCCURRENCE ──────────────────────►producer_type (EVALUATOR | PROJECTION)
occurrence_id                          producer_id, producer_version
analysis_id, identity_hash             catalog_id?, catalog_version?
status, validity
producteur : exécution (EVALUATOR, PROJECTION)
          ou producer_id + validation (HUMAN)
derivation / reason
subject_hash, object_hash
outgoing_rank, incoming_rank     ← le rang appartient à l'occurrence dans une analyse
        │ 1
        │ N
        ▼
EVIDENCE (propre à l'occurrence)
path, line_start, line_end, symbol, method, content_hash | object
```

Les noms exacts de tables et de colonnes sont fixés dans 01E-A ; ce schéma dit ce qui dépend de quoi.

### Décisions

1. **Preuves propres à chaque occurrence**, jamais partagées entre analyses dans 01E. Une preuve peut
   se déplacer (ligne 87 → 91) sans que l'identité change : 01F en aura besoin pour signaler
   `EVIDENCE_CHANGED`. `repository` et `commit` ne sont pas stockés par preuve ; le validateur
   garantit qu'ils sont ceux de l'instantané, et la lecture les restitue depuis l'analyse. Aucune
   déduplication des preuves avant mesure.
2. **Provenance par `PRODUCER_EXECUTION`**, générique pour `EVALUATOR` et `PROJECTION`, repérée par
   `execution_id`. Le schéma n'impose pas « une exécution par évaluateur et par analyse » : c'est vrai
   dans `RunScan` aujourd'hui, ce n'est pas une règle de la mémoire. Un fait `EVALUATOR` ou
   `PROJECTION` dont `produced_by` (type, identifiant, version, `execution_id`, catalogue) ne
   correspond à aucune exécution connue de l'analyse est **refusé à l'écriture** : ni réparé, ni gardé
   comme provenance orpheline. C'est une intégrité de mémoire, pas une interprétation.

   **Enregistrement préalable.** Le contexte d'analyse et les `PRODUCER_EXECUTION` sont enregistrés
   indépendamment des occurrences, **avant** l'écriture des faits, par un port ou cas d'usage distinct,
   depuis l'`EvaluatorExecution` (qui porte le catalogue, contrairement à `summary()`).
   `AnalysisFacts.add()` garde sa signature et ne fabrique **jamais** une exécution à partir du
   `produced_by` d'un fait : ce serait vérifier un fait contre lui-même.

   ```text
   RunEvaluator ─► EvaluatorExecution ─┬─► enregistrer PRODUCER_EXECUTION
                                       └─► AnalysisFacts.add(...)
                                              └─ vérifie produced_by contre l'exécution enregistrée
   ```
3. **`HUMAN` sans exécution.** Le contrat ne lui donne ni `execution_id`, ni version, ni catalogue :
   l'occurrence porte directement `producer_id` et `validation`. Aucune fausse exécution d'évaluateur.
4. **Pas de clés d'ordre en texte.** `outgoing_key` et `incoming_key` ne sont pas persistées. Restent
   persistés : `subject_hash`, `object_hash`, `outgoing_rank`, `incoming_rank`. La clé canonique
   (référence, `identity_hash`, empreinte d'occurrence) est une valeur de calcul, recalculée de façon
   déterministe à l'ingestion ou à la réindexation. Le coût du reclassement est mesuré.

## Invariants (normatifs)

1. **Restitution exacte.** Pour toute analyse, `query` rend des faits égaux (égalité JSON) à ceux
   soumis à `add`, dans le même ordre. Aucun champ inventé, perdu ou normalisé autrement.
2. **Aucun changement observable de `get_neighborhood`** pour une même analyse : mêmes nœuds, faits,
   ordre, preuves, frontières, consommation de budget et motif d'arrêt ; mêmes comportements de
   pagination et de reprise. `facts_revision` et le jeton de continuation peuvent changer de
   représentation ou de version, à sémantique égale. Une continuation d'une version antérieure est
   refusée par une erreur explicite, jamais réinterprétée.
3. **Port inchangé.** `add`, `query`, `revision`, `has_reference`, `neighbor` gardent leur signature et
   leur sens. Le voisinage ignore s'il lit `analysis_facts` ou identités et occurrences.
4. **Une occurrence appartient à une seule analyse.** Aucune fusion entre analyses : une comparaison
   nomme toujours ses deux côtés (ARCHITECTURE § 8).
5. **Identité figée.** La fonction `taxo-fact-identity/v1` ne change pas ; la modifier serait une
   nouvelle version d'identité, hors de ce récit.
6. **Ce que reçoit le stockage est conservé.** Si une analyse soumet deux fois la même identité (deux
   producteurs, deux preuves), les deux occurrences restent distinctes. Juger ce cas n'est pas le rôle
   du stockage.
7. **SQLite et PostgreSQL**, comme toute la chaîne actuelle.
8. **Aucune donnée d'un projet analysé** dans le dépôt, les fixtures ou les mesures publiées : des
   comptes et des tailles seulement.

## Tranches

Chaque tranche est une PR. Tant que 01E-C n'est pas livrée, l'application continue d'utiliser le
stockage actuel ; la nouvelle implémentation du port existe à côté et n'est pas branchée.

### 01E-A — Identité persistée et occurrence

- Commence par le contrat de stockage et le modèle SQL, pas par la migration des données existantes.
- Tables d'identité, d'occurrence, de preuve, de contexte d'analyse et d'exécution ; nouvelle
  implémentation du port pour `add` et `query`.
- Port ou cas d'usage distinct qui enregistre les `PRODUCER_EXECUTION` d'une analyse avant ses faits.
- Les filtres de `query` (nature, sujet, relation, objet) comparent la graphie soumise, comme
  `analysis_facts` : changer de stockage ne change pas le sens de `query`. Rendre les recherches de
  références canoniques (NFC) serait une décision du contrat de requête, prise à part.
- Chaque fait est restitué avec sa graphie : `1` et `1.0` ont la même identité mais sont rendus tels
  que soumis, quel que soit l'ordre d'insertion.
- Une **suite de contrat du port** unique, exécutée sur l'implémentation actuelle et la nouvelle.

Critères :

- même fait dans deux analyses : une identité, deux occurrences ;
- réanalyse du même instantané : aucune nouvelle identité ; chaque nouvelle analyse ou exécution
  conserve sa propre occurrence, avec sa provenance ;
- preuve déplacée (ligne 87 → 91) : même identité, occurrences distinctes, chacune avec sa preuve ;
- nouvelle version de producteur : même identité, occurrences distinctes par leur `produced_by` ;
- `INFERRED` puis `HUMAN_VALIDATED` au niveau du stockage : même identité, statuts distincts ;
- fait `EVALUATOR` ou `PROJECTION` sans exécution enregistrée au préalable dans l'analyse, ou dont un
  champ de `produced_by` (version, catalogue…) diffère de cette exécution : refusé, rien n'est écrit ;
- `add()` appelé avant l'enregistrement de l'exécution : refusé, aucune exécution créée ;
- fait `HUMAN` : conservé sans exécution, avec son `producer_id` et sa `validation` ;
- aucune preuve stockée avec `repository` ou `commit` ; la restitution les reprend de l'instantané ;
- deux écritures concurrentes d'une même nouvelle identité : une seule identité, aucune erreur ;
- restitution exacte sur tous les cas valides de la suite de conformité du contrat et sur des analyses
  synthétiques complètes (inventaire, Git, Java, sécurité, structure, applications).

### 01E-B — Lecture et voisinage sans régression

- `neighbor`, `has_reference`, `revision` et les rangs sur le nouveau modèle.
- `revision` reste une génération croissante propre à l'analyse, lue par un index de taille fixe.
- Rangs recalculés à l'ingestion depuis la clé canonique, sans la persister.

Critères :

- sur des fixtures synthétiques, `get_neighborhood` donne, entre les deux implémentations et pour
  chaque direction, priorité, budget et page de reprise, les mêmes nœuds, faits, ordre, preuves,
  frontières, consommation et motif d'arrêt ; seules `facts_revision` et la représentation du jeton
  de continuation peuvent différer ;
- coût du classement mesuré sur une analyse synthétique volumineuse ;
- aucun chargement complet d'une adjacence : un voisin est lu par l'index, comme aujourd'hui ;
- une continuation émise avant une nouvelle écriture dans l'analyse reste refusée comme aujourd'hui.

### 01E-C — Migration des données, bascule et mesure du gain

- Migration 004 : crée le nouveau stockage, reprend `analysis_facts` par lots, calcule les identités
  avec une copie figée de la fonction v1 (comme 003), reste reprenable après interruption et affiche
  sa progression.
- Exécutions des anciennes analyses : `scans.result` n'a pas le catalogue. La migration les
  reconstitue, seul cas où la provenance des faits sert de source : `execution_id`, évaluateur et
  version doivent concorder avec le résumé de l'analyse, et tous les faits d'une même exécution doivent
  porter le même catalogue. Sinon, arrêt.
- Vérification : pour chaque analyse, mêmes comptes et restitution exacte ; provenance cohérente
  avec les exécutions. Au premier écart, la migration s'arrête et n'a rien détruit.
- **`analysis_facts` est conservée** par 004. Le code bascule sur la nouvelle mémoire ; l'ancienne
  table reste une voie de comparaison et de récupération, au prix d'un surcoût disque temporaire.
- Le retrait de `analysis_facts` est une migration 005 séparée, plus tard, hors de ce récit.

Critères :

- une analyse faite avant la migration donne, après, les mêmes faits, les mêmes pages et le même
  voisinage ;
- migration interrompue puis relancée : même résultat qu'une migration d'un seul trait ;
- donnée ancienne incohérente (provenance sans exécution) : arrêt avant toute destruction, cas nommé ;
- mesure publiée dans la PR, sur une fixture synthétique et sur la base locale (comptes seulement) :

```text
                      avant                après
occurrences           N                    N
identités distinctes  (inconnu)            Y
ratio N / Y           —                    …
taille du nouveau stockage (tables, index)  …
taille de analysis_facts (tables, index)    … (conservée jusqu'à 005)
durée de migration    —                    …
```

Le résultat est publié tel quel, même s'il est décevant. Le gain sur le fichier lui-même n'apparaît
qu'après 005 (et `VACUUM` sous SQLite) ; 01E-C mesure le nouveau stockage seul.

## Hors périmètre

- Comparaison depuis les faits enregistrés, `EVIDENCE_CHANGED`, changement de statut : 01F, juste après.
- Moteur de validité (`STALE`, `REVALIDATION_REQUIRED`) et saisie de validations humaines.
- Retrait de `analysis_facts` (migration 005, après bascule vérifiée).
- Suppression ou purge d'analyses, identités orphelines.
- Cache et projections persistées.
- Résumés de `scans.result`.
