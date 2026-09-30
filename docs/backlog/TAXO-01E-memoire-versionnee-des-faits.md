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

## Modèle cible (conceptuel)

```text
FACT_IDENTITY                          ANALYSIS_CONTEXT (existant : scans, à compléter)
─────────────────────                  ─────────────────────────────
identity_hash  PK                      analysis_id
kind                                   snapshot (repository, commit, mode…)
subject, relation, object              executions des producteurs
qualifiers / pattern / scope / method    (producer_id, version, catalog, execution_id)
coverage_type, producer_id (couverture)
        1                                      1
        │ N                                    │ N
        ▼                                      ▼
FACT_OCCURRENCE ─────────────────────────────────
occurrence_id
analysis_id, identity_hash
status, validity
producer (renvoi vers l'exécution de l'analyse)
derivation / validation / reason
outgoing_rank, incoming_rank     ← le rang appartient à l'occurrence dans une analyse
        │ 1
        │ N
        ▼
EVIDENCE (propre à l'occurrence)
path, line_start, line_end, symbol, method, content_hash | object
```

- Le **rang** de parcours appartient à l'occurrence dans une analyse, jamais à l'identité globale.
- `repository` et `commit` des preuves sont ceux de l'instantané (§ 5.5) : ils sont restitués depuis
  l'analyse, pas répétés par preuve.
- Les noms de tables et colonnes sont à fixer dans 01E-A ; ce schéma dit ce qui dépend de quoi.

## Invariants (normatifs)

1. **Restitution exacte.** Pour toute analyse, `query` rend des faits égaux (égalité JSON) à ceux
   soumis à `add`, dans le même ordre. Aucun champ inventé, perdu ou normalisé autrement.
2. **Aucun changement observable de `get_neighborhood`** pour une même analyse : même ordre, mêmes faits,
   mêmes preuves, mêmes frontières, mêmes continuations. Seule exception admise : une nouvelle version
   de continuation si la représentation l'impose. Une ancienne continuation est alors refusée par une
   erreur explicite, jamais réinterprétée.
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

- Tables d'identité, d'occurrence, de preuve et de contexte d'analyse ; nouvelle implémentation du port
  pour `add` et `query`.
- Une **suite de contrat du port** unique, exécutée sur l'implémentation actuelle et la nouvelle.

Critères :

- même fait dans deux analyses : une identité, deux occurrences ;
- réexécution sur le même instantané : aucune nouvelle identité, de nouvelles occurrences ;
- preuve déplacée (ligne 87 → 91) : même identité, occurrences distinctes, chacune avec sa preuve ;
- nouvelle version de producteur : même identité, occurrences distinctes par leur `produced_by` ;
- `INFERRED` puis `HUMAN_VALIDATED` au niveau du stockage : même identité, statuts distincts ;
- deux écritures concurrentes d'une même nouvelle identité : une seule identité, aucune erreur ;
- restitution exacte sur tous les cas valides de la suite de conformité du contrat et sur des analyses
  synthétiques complètes (inventaire, Git, Java, sécurité, structure, applications).

### 01E-B — Lecture et voisinage sans régression

- `neighbor`, `has_reference`, `revision` et les rangs sur le nouveau modèle.
- `revision` reste une génération croissante propre à l'analyse, lue par un index de taille fixe.
- Les clés d'ordre ne sont conservées que si la mesure le justifie : elles sont reconstructibles.

Critères :

- sur des fixtures synthétiques, `get_neighborhood` donne des réponses identiques octet pour octet
  entre les deux implémentations, pour chaque direction, priorité, budget et page de reprise ;
- aucun chargement complet d'une adjacence : un voisin est lu par l'index, comme aujourd'hui ;
- une continuation émise avant une nouvelle écriture dans l'analyse reste refusée comme aujourd'hui.

### 01E-C — Migration des données et mesure du gain

- Migration 004 : reprend `analysis_facts` par lots, calcule les identités avec une copie figée de
  la fonction v1 (comme 003), reste reprenable après interruption et affiche sa progression.
- Vérification avant suppression : pour chaque analyse, mêmes comptes et restitution exacte. En cas
  d'écart, la migration s'arrête sans rien supprimer.
- Branchement de la nouvelle implémentation, retrait de `analysis_facts`.

Critères :

- une analyse faite avant la migration donne, après, les mêmes faits, les mêmes pages et le même
  voisinage ;
- migration interrompue puis relancée : même résultat qu'une migration d'un seul trait ;
- mesure publiée dans la PR, sur une fixture synthétique et sur la base locale (comptes seulement) :

```text
                      avant                après
occurrences           N                    N
identités distinctes  (inconnu)            Y
ratio N / Y           —                    …
taille des tables     …                    …
taille des index      …                    …
taille du fichier     …                    … (après VACUUM pour SQLite)
durée de migration    —                    …
```

Le résultat est publié tel quel, même s'il est décevant. Sous SQLite, la place libérée ne revient au
fichier qu'après `VACUUM` ; l'exécuter automatiquement ou non est à décider dans cette tranche.

## Hors périmètre

- Comparaison depuis les faits enregistrés, `EVIDENCE_CHANGED`, changement de statut : 01F, juste après.
- Moteur de validité (`STALE`, `REVALIDATION_REQUIRED`) et saisie de validations humaines.
- Suppression ou purge d'analyses, identités orphelines.
- Cache et projections persistées.
- Résumés de `scans.result`.

## Questions à trancher dans 01E-A, avant le code

1. Preuves : propres à chaque occurrence (simple) ou partagées entre analyses quand elles sont
   identiques hors instantané (gain plus grand, lecture plus complexe) ? Recommandation : propres à
   l'occurrence ; le partage ne vient que si la mesure de 01E-C le justifie.
2. Exécutions des producteurs : une ligne par analyse et par évaluateur, renvoyée par chaque
   occurrence ? Un fait dont le `produced_by` ne correspondrait à aucune exécution de l'analyse est-il
   refusé ou conservé tel quel ?
3. Faits produits par une projection ou une personne : leur `produced_by` n'a pas d'exécution
   d'évaluateur ; où vivent-ils ?
4. Clés d'ordre en texte : les garder, ou recalculer les rangs à l'ingestion seulement ?
