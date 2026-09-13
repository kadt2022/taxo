# ADR 0001 : Taxo est une mémoire logicielle vérifiable

Date : 2026-09-12
Statut : Proposé

## Contexte

La vision initiale décrivait Taxo comme une plateforme de documentation automatique, construite par
17 évaluateurs développés dans un ordre séquentiel (Inventory, Structure, Dependencies, Git, API...).

Le 2026-09-12, une démonstration « nouvel arrivant sur TAKIBO » a été vérifiée à la main par un agent
de code disposant d'outils de recherche. Constats :

- l'agent a produit en quelques minutes des réponses justes, avec fichiers et lignes ;
- il a aussi affirmé une absence fausse (« pas de `@PreAuthorize` ») sans l'avoir cherchée ;
- il a présenté comme vérifiés des faits tirés de notes antérieures ;
- rien ne garantissait qu'il avait cherché partout, qu'il referait la même analyse le lendemain,
  ni que ses preuves survivraient à la conversation.

Parallèlement, la documentation générée depuis un dépôt est devenue une commodité (wikis générés,
agents de code). Un produit positionné sur « générer de la documentation » est comparable à des
outils gratuits.

## Décision

### 1. Positionnement

> Les agents savent lire le code. Taxo sait ce qui est vrai dans le code.
>
> Taxo n'est pas un agent plus intelligent. C'est la mémoire vérifiable qui manque aux agents.
>
> Chaque réponse peut être remontée jusqu'au commit et au code qui la prouvent.

Principe fondateur :

> Un agent peut découvrir une vérité. Taxo doit pouvoir garantir comment elle a été découverte, à
> quelle version elle appartient, jusqu'où elle est complète, et pourquoi elle est considérée comme
> vraie.

Le produit fondamental est :

```text
Sources versionnées
      ↓
Évaluateurs déterministes
      ↓
Faits vérifiés (ADR 0002)
      ↓
Mémoire logicielle versionnée
      ↓
Projections : documentation, diagrammes, dérive, impact, PR, MCP / Ask Taxo
```

Les agents (Claude, Copilot, Codex...) se placent au-dessus, via MCP ou API. Ils raisonnent ; Taxo
établit et conserve les faits sur lesquels ils raisonnent.

### 2. Trois familles, pas une liste d'évaluateurs

| Famille | Ce qu'elle lit | Ce qu'elle produit |
| --- | --- | --- |
| **Source** | le monde extérieur à Taxo | un matériau versionné et adressable |
| **Évaluateur** | une ou plusieurs sources | des faits `OBSERVED`, et la couverture de son analyse |
| **Projection** | uniquement des faits | des vues (docs, diagrammes, commentaires de PR) ou des faits `INFERRED` |

```text
SOURCES                  ÉVALUATEURS            PROJECTIONS
Repository (au commit)   Inventory              Documentation
Git (historique)         Structure              Diagrammes
Connaissances humaines   Dependencies           Documentation Drift
Runtime (plus tard)      API                    Impact Analysis
Outils externes (Sonar)  Security               PR Bot
                         Data                   MCP / Ask Taxo
                         Configuration          Business Flows
                         Frontend               Release notes
                         Tests
                         CI/CD
                         Deployment
                         Documentation (inventaire des documents existants)
```

Reclassements par rapport à la vision initiale :

- **Git & Evolution** devient une source transversale : presque tous les faits s'y rattachent.
- **Architecture & Diagrams** et **Business Flows** deviennent des projections.
- **Documentation Drift** est une projection qui compare deux ensembles de faits. L'inventaire des
  documents présents dans le dépôt reste, lui, un évaluateur.
- **Code Quality** consomme une source externe (Sonar) ; ce n'est pas un analyseur de Taxo.
- **Runtime Verification** combine une source (le runtime) et une projection (la dérive).

### 3. Propriétés garanties

- **Couverture déclarée.** Taxo ne promet pas d'avoir tout trouvé : aucun analyseur statique ne le
  peut. Il promet de dire ce qu'il a cherché, avec quelle version de son catalogue de détection, et
  ce qu'il n'a pas su interpréter.
- **Versionné.** Tout fait est rattaché à un instantané (dépôt et commit) *et* à la version de
  l'évaluateur qui l'a produit.
- **Persistant.** Une preuve établie aujourd'hui reste consultable et réutilisable plus tard, par
  une personne ou un agent.
- **Prouvable.** Tout fait porte un statut (`OBSERVED`, `INFERRED`, `HUMAN_VALIDATED`) et sa
  provenance.

### 4. Règles

1. Aucun fait sans statut ni provenance.
2. Une absence est toujours bornée : périmètre et méthode de recherche sont obligatoires.
3. Ce qui n'est pas interprété est déclaré comme tel. Ce n'est jamais passé sous silence, ni
   converti en « absent ».
4. L'analyse de référence porte sur un **commit**, pas sur le dossier de travail. L'analyse du
   dossier de travail reste possible, mais elle est explicitement marquée.
5. Pas de pourcentage de confiance sans méthode de calcul documentée.
6. **Un faux positif de sécurité est un défaut produit majeur.** Dans le doute, Taxo répond « non
   interprété », jamais « non protégé ».
7. Un analyseur est écrit dans le langage le mieux adapté à ce qu'il analyse (un analyseur Java peut
   être un composant JVM). Le contrat du fait est la seule frontière commune.
8. Un LLM ne produit jamais de fait `OBSERVED`.

### 5. Développement guidé par la valeur démontrée

L'ordre de développement suit la démonstration de valeur, pas la cartographie complète du produit.
Voir `docs/backlog/PLAN.md`.

### 6. TAKIBO comme banc d'essai de référence

Le développement se fait sur de petits projets contrôlés. La valeur se valide sur TAKIBO, qui
contient les cas difficiles : sécurité maison (`PolicyEvaluator`), OAuth2, multi-tenant, plusieurs
modules, migrations, tests et un historique Git réel.

## Conséquences

- Les 17 récits d'évaluateurs deviennent une **carte des capacités futures**, pas un backlog.
- `scanner.py` devient l'évaluateur Inventory et produit des faits au format de l'ADR 0002. Le JSON
  libre stocké dans `scans.result` est remplacé.
- Au début, Taxo répondra souvent « non interprété ». C'est le prix de la crédibilité, et une
  information utile en soi.
- Le choix de la technologie d'analyse Java doit être tranché au début du récit Spring API, pas après.

## Alternatives rejetées

- **Plateforme de documentation automatique** : banalisée, et directement concurrencée par des
  outils gratuits.
- **Agent conversationnel sur le code** : ni reproductible, ni exhaustif sur un périmètre déclaré,
  sans mémoire entre deux sessions.
- **Knowledge Graph d'abord** : on choisirait le stockage avant d'avoir fixé la signification. Le
  graphe sera la conséquence de faits reliables.
- **Ordre séquentiel des 17 évaluateurs** : environ un an de fondations avant la première
  démonstration convaincante.
