# Manifeste Taxo

*Révisé le 2026-09-17.*

*Ce document applique à Taxo la discipline que Taxo impose au logiciel : ce qui est construit est dit construit, ce qui est visé est dit visé, ce qui est inconnu est dit inconnu, et toute promesse importante doit pouvoir être mise à l'épreuve.*

---

## 1. Taxo en une phrase

> **Taxo est un utilitaire de vérité logicielle : il transforme le code source en faits logiciels vérifiables, reproductibles, rattachés à leurs preuves, à leur périmètre et à un état précis du logiciel.**

Taxo n'est pas un agent plus intelligent.

Taxo est la couche qui permet à un humain, une CI ou un agent IA de répondre à une question plus exigeante :

> **Qu'est-ce qui est réellement établi sur ce logiciel, pourquoi puis-je le croire, et jusqu'où cette réponse reste-t-elle vraie ?**

---

## 2. La conviction

Le code est la source primaire. Il n'est pas une mémoire.

Un humain qui arrive sur un logiciel de dix mille fichiers l'explore par échantillons. Un agent fait la même chose plus vite, mais avec un défaut supplémentaire : **il ne sait pas précisément ce qu'il n'a pas lu**.

Il peut trouver quelques classes, quelques routes, quelques configurations, puis transformer naturellement cet échantillon en récit global.

Le problème n'est donc pas seulement l'hallucination.

Le problème est plus profond :

> **L'agent ne sait pas toujours distinguer “je n'ai rien trouvé” de “je n'ai pas tout regardé”.**

Plus l'IA produit du code rapidement, plus cet écart devient dangereux.

La question centrale de Taxo est donc :

> **Comment savoir, sans tout relire, ce qui est vrai dans un logiciel — et savoir également ce qu'on ne sait pas ?**

Trois formules servent de boussole :

- Les agents savent lire le code. **Taxo construit ce qui peut être tenu pour vrai dans le code.**
- Taxo n'est pas un autre copilote. **Taxo est une mémoire vérifiable du logiciel.**
- **Toute connaissance importante doit pouvoir être remontée jusqu'à ses preuves et à son périmètre.**

---

## 3. La catégorie et le terrain où Taxo doit gagner

Taxo ne cherche pas à être :

- le meilleur `grep` ;
- le meilleur moteur de recherche sémantique ;
- un autre agent de développement ;
- un juge qui produit des notes opaques.

Les rôles sont différents :

```text
Recherche de code
→ "où regarder ?"

Agent de développement
→ "comment travailler ?"

Taxo
→ "qu'est-ce qui est établi ?"
```

Taxo est donc une **couche de vérification** du logiciel.

Cette couche devient particulièrement utile là où une erreur coûte cher :

- IAM ;
- autorisation ;
- authentification ;
- sécurité ;
- conformité ;
- audit ;
- changements sensibles.

Personne ne devrait signer une conclusion de sécurité sur :

> « probablement protégé ».

La cible est une réponse de ce type :

```text
PROTECTED_BY ...
status: INFERRED
premises: ...
evidence: ...
snapshot: ...
coverage: ...
```

Taxo doit cependant rester utile sans LLM. Le LLM est un consommateur possible, jamais la source de vérité.

---

## 4. Le contrat de confiance

### 4.1 Les natures de faits

Taxo distingue :

- `ASSERTION` : quelque chose est affirmé ;
- `ABSENCE` : quelque chose a été recherché dans un périmètre adéquat et n'a pas été trouvé ;
- `COVERAGE` : ce qui a été analysé, reconnu, non interprété, exclu ou impossible à lire.

### 4.2 Les statuts de connaissance

Taxo distingue :

- `OBSERVED` : constaté directement ;
- `INFERRED` : déduit à partir d'autres faits ;
- `HUMAN_VALIDATED` : validé explicitement par une personne.

Ces statuts ne sont pas des scores de confiance.

### 4.3 La preuve et les prémisses

Une assertion observée porte une preuve.

Une inférence cite ses prémisses.

Une absence n'est jamais prouvée par un simple extrait : elle dépend de la couverture du périmètre.

### 4.4 La provenance et l'instantané

Tout fait porte son producteur :

- évaluateur ;
- projection ;
- personne.

L'évaluateur est versionné, afin de ne pas confondre « le code a changé » avec « Taxo détecte mieux ».

Un fait est établi sur un commit déterminé, jamais sur « le projet » de manière abstraite.

### 4.5 Les types de couverture

Le contrat de couverture distingue :

```text
ANALYSED
RECOGNIZED
NOT_INTERPRETED
OUT_OF_SCOPE
READ_ERROR
```

Ces valeurs appartiennent au contrat des `COVERAGE`.

`UNKNOWN` n'est **pas** un type de couverture.

`UNKNOWN` appartient à la couche d'interrogation : c'est la réponse à utiliser lorsqu'aucun fait ni aucune capacité d'évaluateur ne permet de répondre légitimement à la question.

Exemple :

```text
UNKNOWN

Aucun évaluateur actif ne déclare actuellement
la capacité d'établir les outils MCP exposés.
```

Règle absolue :

> **L'absence de fait n'est jamais, à elle seule, une preuve d'absence.**

---

## 5. Réfutabilité, fait cher et validité sémantique

### Réfutabilité

Toute promesse importante de Taxo doit pouvoir être mise en défaut.

Une connaissance doit pouvoir être :

- vérifiée ;
- contredite ;
- déclarée hors périmètre ;
- déclarée inconnue.

Une fonctionnalité dont on ne sait pas énoncer les conditions d'échec n'appartient pas au cœur factuel de Taxo.

### Le fait cher

Taxo ne doit pas devenir une usine extrêmement rigoureuse pour reproduire ce qu'une commande shell fournit déjà parfaitement.

Le critère interne est volontairement brutal :

> **Trois lignes de shell donnent-elles le même résultat avec la même signification ?**

Si oui, la garantie Taxo a encore peu de valeur.

Si non, elle peut devenir décisive.

Taxo privilégie donc les connaissances qui exigent de relier plusieurs observations et dont l'exhaustivité, l'absence ou la provenance sont difficiles à garantir.

### Validité sémantique

Un fait peut respecter parfaitement le schéma tout en disant quelque chose de faux ou de trompeur.

> **Le contrat protège la forme. Les tests sémantiques protègent le sens.**

Par exemple, `DECLARED_BY` ne doit pas mélanger silencieusement une technologie réellement déclarée dans un manifeste et une technologie simplement reconnue par extension de fichier.

---

## 6. Exemple de fait cher : l'autorisation dans TAKIBO

Le premier jalon de preuve n'est pas un exemple inventé.

Il s'appuie sur une route réelle déjà vérifiée :

```text
GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users
→ ReadableUserQueryController#list
→ SecurityConfig.java:85
```

La cible n'est pas une chaîne simplifiée, mais un ensemble de faits liés :

```text
endpoint:GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users

├─ HANDLED_BY
│  → symbol:ReadableUserQueryController#list
│  OBSERVED
│
├─ MATCHED_BY
│  → route-pattern:...
│  INFERRED
│
└─ PROTECTED_BY
   → symbol:PolicyBasedAuthorizationManager
   INFERRED
   premises:
     MATCHED_BY + AUTHORIZED_BY

route-pattern:...
└─ AUTHORIZED_BY
   → symbol:PolicyBasedAuthorizationManager
   OBSERVED

symbol:PolicyBasedAuthorizationManager
└─ CALLS
   → symbol:PolicyEvaluator
   OBSERVED
```

La valeur de Taxo n'est pas seulement de trouver les classes.

Elle est d'établir :

- les relations ;
- les prémisses ;
- les preuves ;
- le commit ;
- la couverture ;
- les limites.

---

## 7. Les évaluateurs sont la partie difficile

Le moteur d'exécution, la base, l'API et le frontend sont nécessaires.

Mais le produit difficile est ici :

```text
code réel
   ↓
évaluateur précis
   ↓
fait sémantiquement correct
   ↓
preuve
   ↓
couverture honnête
```

Un évaluateur Taxo doit déclarer :

- ses capacités ;
- son catalogue de relations ;
- son périmètre ;
- sa version ;
- ses dépendances ;
- ses sorties ;
- ses conditions d'échec ;
- ce qu'il ne sait pas établir.

Il n'existe pas d'évaluateur universel.

Le moteur peut être générique.

Les analyseurs restent spécialisés par langage, framework ou domaine lorsque la précision l'exige.

---

## 8. Taxo doit être un utilitaire interrogeable

Une mémoire que personne n'interroge n'est pas encore un produit utile.

Taxo doit donc être consommable par plusieurs interfaces :

```text
CLI
API
console web
CI/CD
MCP
```

La console est une vue sur Taxo.

Elle n'est pas Taxo lui-même.

L'expérience cible doit rester simple :

```bash
taxo scan .
```

Puis :

```bash
taxo query "routes protected by PolicyEvaluator"
```

Puis :

```bash
taxo diff <commit-a> <commit-b>
```

Pour les agents, le premier MCP reste volontairement petit :

```text
taxo.find_facts
taxo.get_evidence
taxo.get_coverage
```

Puis :

```text
taxo.diff_facts
```

Le flux cible :

```text
Codex / Claude / Gemini
        ↓
       MCP
        ↓
       Taxo
        ↓
Facts + Evidence + Coverage
```

Le LLM peut traduire une question ou reformuler une réponse.

Il ne crée pas les faits manquants.

Si Taxo répond `UNKNOWN`, le LLM ne transforme pas `UNKNOWN` en récit plausible.

---

## 9. La dimension temporelle

Un logiciel n'est pas seulement un état.

C'est une succession d'états.

Git fournit déjà une donnée structurée, déterministe et relativement peu coûteuse à analyser. Taxo doit en profiter.

La mémoire distingue :

```text
Fact identity
→ la connaissance elle-même

Fact occurrence
→ le moment où elle a été observée
```

Cette séparation permet de dépasser le diff textuel.

Un `git diff` dit :

```text
+ 12 lignes
- 8 lignes
```

Taxo doit pouvoir dire :

```text
commit A
endpoint:X
PROTECTED_BY PolicyEvaluator

commit B
endpoint:X
PROTECTED_BY NewAuthorizationManager

changement de vérité
→ mécanisme d'autorisation modifié
```

Puis vient l'enquête :

- quel commit a introduit ce changement ?
- qui l'a modifié ensuite ?
- quelle justification explicite existe ?

Taxo n'invente jamais le `WHY`.

S'il n'existe aucune justification explicite :

```text
Aucune justification explicite trouvée.
Voici les changements observés.
```

---

## 10. Performance : faire moins avant de faire plus vite

Taxo doit être rapide, mais la vitesse brute n'est pas sa proposition centrale.

La priorité est :

1. ne pas refaire ce qui n'a pas changé ;
2. réutiliser les blobs et empreintes Git ;
3. conserver les résultats d'analyse stables ;
4. exécuter les évaluateurs indépendants en parallèle ;
5. paralléliser ensuite les travaux CPU lourds.

L'objectif n'est pas :

> « Python doit battre `git ls-files`. »

L'objectif est :

> **Le premier scan exploite correctement la machine ; les suivants recalculent presque uniquement ce qui a changé.**

Le parallélisme ne doit jamais détruire le déterminisme.

---

## 11. Où nous en sommes

*État au 2026-09-19.*

### Construit

- contrat du fait, identité canonique, suite de conformité ;
- snapshots Git par commit, lecture déterministe du dépôt ;
- exécution d'évaluateurs : identité, version, catalogue, statuts, couverture déclarée séparée ;
- Evidence, provenance, Coverage ;
- Inventory v0 ;
- résumé d'exécution borné dans la console.

Les récits 01A, 01B, 01C, ARCH-01 et 01D sont fusionnés. 01E, 01F, 01G et 01I sont rédigés et non
ouverts. Le vocabulaire Fait / Tuile / Maille / Contexte est figé par l'ADR 0005, et le lot TILES
est rédigé sans être ouvert : il suppose les faits de TAXO-04 et TAXO-05.

### Limites mesurées

Les premières simulations ont montré que :

- Taxo répond parfaitement aux questions de dénombrement et d'ancrage qu'il sait réellement traiter ;
- les faits complets ne sont pas encore une mémoire persistée exploitable ;
- l'Inventory produit principalement des faits peu chers ;
- les données déjà lues peuvent encore être réduites ou jetées ;
- l'agent peut inventer silencieusement lorsqu'une capacité manque ;
- la frontière des capacités doit donc devenir explicitement interrogeable.

### Jalon immédiat

**TAXO-POC-01.** Une route réelle du banc doit être établie jusqu'à son évaluateur de politique,
contre une vérité de référence écrite avant tout évaluateur, avec :

- faits observés ;
- faits inférés ;
- prémisses ;
- preuves ;
- snapshot ;
- couverture ;
- limites.

### Trajectoire après preuve

Si ce premier fait cher est démontré :

```text
mémoire persistante minimale
        ↓
MCP minimal
        ↓
benchmark reproductible
        ↓
historique Git / lineage
        ↓
diff de faits
        ↓
évaluateurs Spring / Security étendus
```

La plateforme vient après la confiance.

---

## 12. Comment nous saurons que nous avons tort

Taxo ne progresse plus simplement parce que « le récit suivant porte le numéro suivant ».

Chaque jalon est confronté à des questions réelles.

Méthode :

```text
récit terminé
     ↓
6 à 10 questions réelles
     ↓
qu'est-ce que Taxo sait ?
qu'est-ce qu'il ne sait pas ?
qu'est-ce que l'agent invente encore ?
     ↓
backlog réordonné
```

Le benchmark compare :

```text
agent seul
vs
même agent + Taxo
```

Avec :

- même projet ;
- même commit ;
- même modèle ;
- plusieurs exécutions.

On mesure :

- exactitude ;
- complétude ;
- fausses absences ;
- validité des preuves ;
- stabilité ;
- temps ;
- tokens.

La vérité de référence est écrite avant l'évaluateur.

Le jeu contient volontairement des questions dont la bonne réponse est :

```text
UNKNOWN
OUT_OF_SCOPE
NOT_INTERPRETED
```

Si Taxo n'améliore pas significativement les réponses sur les connaissances qu'il prétend garantir, la thèse est revue.

S'il les améliore, alors Evidence, Coverage et déterminisme cessent d'être une belle forme : ils deviennent la garantie d'un contenu réellement utile.

---

## Conclusion

Le manifeste explique pourquoi quelqu'un devrait s'en soucier.

Le contrat explique pourquoi quelqu'un devrait nous croire.

La mesure décide si nous avons raison.

> **Taxo ne promet pas de tout comprendre.  
> Taxo promet de ne pas confondre ce qu'il sait, ce qu'il déduit et ce qu'il ignore.**
