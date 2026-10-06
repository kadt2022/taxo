# TAXO-UI-06 — Vue Chaîne : lire une route en notation UML Taxo

Statut : **direction validée le 2026-10-06, récit à relire avant implémentation**. Révisé le même jour :
couleurs par type et panneau de code, demandés après la première lecture. Commencé avant TAXO-01K à la
demande du 2026-10-06 : PR 1 (vue Chaîne, couleurs, légende) livrée par la PR de la branche
`claude/project-thread-40sfm7`.  
Date : 2026-10-06.  
Source de vérité : [ARCHITECTURE § 2, § 3 et § 9](../ARCHITECTURE.md), [TAXO-01J § 9](TAXO-01J-navigation-multiniveau-et-explorateur.md).  
Dépend de : explorateur de la Maille (TAXO-01J, livré). N'a d'intérêt complet qu'avec les appels Java
(TAXO-01K, proposition #88) : avant eux, la chaîne s'arrête au contrôleur. La chaîne cible suppose 01K tel
que proposé, qui étend `CALLS` au-delà du premier fragment de l'ARCHITECTURE § 14 (receveur champ typé,
comme `courseService.getCourses()`) et produit `IMPLEMENTS` au niveau des méthodes (sa PR C). Si 01K est
réduit, la vue montre moins de flèches, jamais d'autres.  
Ne dépend pas de Minia. Ne touche pas la MIP.

## Constat

La vue « Couches » de l'explorateur (`frontend/src/explorer/LayerView.tsx`, `layout.ts`) est fidèle mais
difficile à lire pour suivre une route :

- une flèche ne dit pas sa relation : il faut la choisir pour savoir si elle « appelle » ou « est protégée
  par » ;
- par défaut, jusqu'à seize relations sont suivies ensemble : sécurité, modules et appels se mélangent ;
- les colonnes rangent les nœuds par distance à l'ancre, pas dans le sens de lecture ; les courbes se
  croisent et les revisites reviennent en arc ;
- les noms sont coupés à la largeur de la boîte ;
- la frontière vit dans un panneau à part, loin de l'endroit du dessin où Taxo s'arrête.

## Intention

En tant que personne qui explore une route, je lis de haut en bas ce qui la traite, ce que cela appelle, et
où Taxo s'arrête, avec une notation inspirée d'UML : une boîte par nœud, une flèche nommée par relation,
la réalisation UML pour « implémente », une note UML pour la frontière. Chaque type a sa couleur, et quand
je choisis une méthode, son code apparaît à droite, à côté du diagramme.

La beauté fait partie de la valeur : une vue soignée se lit plus vite et donne envie d'explorer. Elle reste
honnête : une couleur ne dit jamais plus que ce que la Maille sait.

Cible, sur `student-course-demo` une fois TAXO-01K livré :

```mermaid
flowchart TD
    R["«route»<br/><b>GET /api/courses</b>"]
    C["«symbole»<br/>CourseController#getCourses()"]
    S["«symbole»<br/>CourseService#getCourses()"]
    I["«symbole»<br/>CourseServiceImpl#getCourses()"]
    F>"FRONTIÈRE · Taxo voit courseRepository.findAll(),<br/>la déclaration n'est pas dans les sources analysées"]
    R -- "est traité par · O" --> C
    C -- "appelle · D" --> S
    I -. "implémente · D" .-> S
    I -. "appel non établi" .-> F
```

La vue Chaîne est une **troisième forme** de l'explorateur, à côté de « Couches » et « Liste ». Elle ne
remplace ni ne retire rien. Elle dessine la Tuile déjà reçue : c'est une projection, jamais une seconde
source de vérité.

## Pourquoi pas un diagramme de séquence UML

Un diagramme de séquence affirme un ordre d'exécution et le corps qui s'exécute. Taxo ne le sait pas :
`CALLS` désigne une déclaration appelée, sans ordre ni dispatch, et `DISPATCHES_TO` est hors périmètre
(TAXO-01K, décisions 1 et 4). La vue Chaîne garde l'allure verticale qui rend la séquence lisible, sans
prétendre à un ordre ni à une exécution.

## Notation (normative pour ce récit)

| Élément | Dessin | Ce qu'il porte |
| --- | --- | --- |
| Nœud | boîte, en-tête teinté de la couleur de son type (E7), le type entre « » (stéréotype UML) | le nom lisible de `naming()`, **en entier**, passé à la ligne, jamais coupé |
| Ancre | boîte au contour accentué, en haut | la référence choisie |
| Relation de chaîne | flèche pleine verticale, sujet au-dessus, objet en dessous | son verbe (`VERBS`), un badge de statut, `×N` s'il y a plusieurs occurrences |
| Relation de côté | flèche en pointillé à triangle creux (réalisation UML), horizontale | son verbe, son badge ; l'autre extrémité est posée dans la colonne de côté, sur la ligne du nœud qu'elle touche |
| Revisite | pastille « ↺ déjà montré : *nom* » sous le nœud | aucun arc de retour ; un clic choisit le nœud déjà dessiné |
| Frontière de connaissance locale | note UML (coin replié), ton d'avertissement, accrochée sous son nœud | la phrase de `knowledgeText`, la raison, et la localisation du site quand la frontière la porte (diagnostic de couverture de TAXO-01K) ; aucun lien de preuve, une frontière n'a pas de poignée d'occurrence |
| Coupure de sélection | pastille grise sous son nœud | la phrase de `selectionText` et les actions existantes (développer, voir la suite) |

Badge de statut : **O** `OBSERVED`, **D** `INFERRED`, **V** `HUMAN_VALIDATED` ; un statut inconnu
s'affiche par son nom brut. Les frontières sans nœud (portée `ANALYSIS`) et les frontières de contexte
restent dans le panneau « Ce que la vue ne montre pas », inchangé.

Le sens d'une flèche est toujours celui du fait, sujet vers objet, comme dans la vue Couches.

## Exigences

### E1 — Forme des relations : une donnée du vocabulaire, pas une règle de l'explorateur

Le test d'architecture de l'explorateur interdit d'y nommer une relation ; il reste vrai. La forme de
chaque relation est une table du vocabulaire du portail (`frontend/src/vocabulary.ts`), à côté de
`VERBS` :

```text
FORMS : relation → CHAÎNE | CÔTÉ
HANDLED_BY → CHAÎNE, CALLS → CHAÎNE, IMPLEMENTS → CÔTÉ
```

Une relation absente de la table est de forme `CHAÎNE`. L'explorateur reçoit la table en entrée ; il ne
connaît aucune relation par son nom. Aucun mot Spring, contrôleur, service ou repository n'apparaît dans
la table, l'explorateur ou le moteur : ces mots ne viennent que des noms de classes du projet lu.

### E2 — Parcours « Appels depuis une route »

Un parcours prédéfini, déclaré dans le vocabulaire du portail, comme pas `(relation, sens)` :

```text
HANDLED_BY sortant, CALLS sortant, IMPLEMENTS entrant
```

Le moteur `neighborhood/2` accepte déjà `steps` (ARCHITECTURE § 9) ; seul `protocol.ts` apprend à les
envoyer, à côté de `follow` + `direction`. **Ce pas ne change ni le moteur, ni le protocole serveur, ni la
Maille.** Le parcours n'est proposé que si l'analyse annonce au moins une de ses relations
(`describe`) ; une relation sans producteur reste dite comme aujourd'hui (`NO_PRODUCER`).

Le parcours reste un réglage : la personne peut toujours choisir ses relations et son sens. La vue Chaîne
s'affiche pour tout réglage ; si un pas de chaîne est entrant, ses nœuds sont posés sous le nœud qui les a
fait découvrir, et la flèche monte : elle garde toujours le sens du fait.

### E3 — Mise en page pure

Un module pur `frontend/src/explorer/chain.ts` (ni React, ni réseau, comme `layout.ts`) calcule la mise en
page depuis la vue, ses liens et la table des formes :

- la chaîne est l'arbre couvrant des liens `CHAÎNE` depuis l'ancre, chaque nœud posé à sa première
  découverte (`discovered_by`), une ligne par niveau de chaîne ;
- les frères sont rangés par première ligne de preuve quand la Tuile la porte, sinon dans l'ordre de la
  Tuile ; l'ordre est déterministe et n'affirme aucun ordre d'exécution ;
- un lien `CÔTÉ` pose son autre extrémité dans la colonne de côté, sur la ligne du nœud de chaîne qu'il
  touche ; si cette extrémité est déjà dessinée, c'est une revisite ;
- un lien dont l'extrémité n'est pas un nœud (aucun objet, comme `PERMITS_ALL`, ou une valeur littérale)
  mène à une **feuille**, comme dans la vue Couches : petite boîte en pointillé, « aucun objet » ou la
  valeur, posée sous son sujet pour un lien `CHAÎNE`, dans la colonne de côté pour un lien `CÔTÉ` ; elle
  n'est jamais développée ni recentrée, et l'export Mermaid l'écrit aussi : aucun fait de la vue n'est omis ;
- les tracés sont des segments droits ; aucun lien ne croise une boîte ;
- la hauteur d'une boîte suit la longueur de son nom, passé à la ligne après la ponctuation (`.`, `#`,
  `/`, `:`), sans découpage sémantique de la référence.

### E4 — La frontière dans le dessin

Une frontière de connaissance locale (`KNOWLEDGE`, portée `NODE`) devient une note accrochée sous son
nœud. Une coupure de sélection devient une pastille avec ses actions. Rien n'est dessiné pour combler une
frontière : un appel non établi s'arrête sur la note, aucune cible n'est devinée. La phrase de la raison
vient de `sentences.ts` ; les raisons fermées de TAXO-01K y reçoivent leur traduction avec la PR C de
TAXO-01K, pas ici.

### E5 — Interaction et accessibilité

Comme la vue Couches : nœuds, flèches, notes et pastilles sont de vrais boutons posés sur le tracé ; le
SVG ne fait que tracer. Choisir une flèche ouvre le panneau de preuves existant (`LinkPanel`) ; choisir
un nœud ouvre le panneau du nœud. Les libellés accessibles reprennent `factText` et les marques du nœud.
Lisible en thème clair et sombre.

### E6 — Export Mermaid

Un bouton « Copier en Mermaid » copie la chaîne affichée en texte `flowchart TD`, produit par une
fonction pure (`chain.ts` ou `mermaid.ts`) depuis la même mise en page : mêmes nœuds, mêmes verbes,
mêmes badges, mêmes notes. Les guillemets et chevrons des références sont échappés. L'export ne
contient que ce que la vue montre ; ses coupures y sont écrites.

### E7 — Une couleur par type, avec sa légende

Chaque type de référence a sa couleur : l'en-tête et le liseré de la boîte en prennent la teinte, le corps
reste clair pour que le nom se lise. Première palette, à ajuster sur l'essai réel :

| Type | Teinte | Usage |
| --- | --- | --- |
| route (`endpoint`) | bleu | point d'entrée HTTP |
| symbole (`symbol`) | vert Taxo | méthode, classe ou interface du code |
| module | violet | module de construction |
| fichier | sable | fichier du dépôt |
| application | sarcelle | application construite |
| règle de sécurité, motif de routes | rose | `policy-rule`, `route-pattern` |
| commit, personne | ardoise | historique |
| frontière de connaissance | orange | note « Taxo ne sait pas » |
| coupure de sélection | gris | pastille « voir la suite » |

Règles :

- la table type → couleur est une donnée du vocabulaire du portail (`vocabulary.ts`), comme `FORMS` ; les
  couleurs sont des jetons CSS (`--type-route`, `--type-symbol`, …) définis pour le thème clair et le
  thème sombre, avec un contraste lisible du texte sur l'en-tête dans les deux ;
- un type inconnu prend une teinte neutre et s'affiche par son nom brut ;
- l'orange est réservé aux frontières de connaissance : aucun type ne le porte ;
- la couleur n'est jamais seule à porter le sens : le stéréotype écrit dans l'en-tête dit aussi le type
  (accessibilité, impression) ;
- une légende repliable sous le diagramme ne montre que les types et les marques présents dans la vue ;
- les badges de statut ont leur propre code : **O** vert, **D** bleu, **V** violet ;
- la nuance classe, interface ou méthode n'est dessinée que si le producteur du symbole la fournit dans la
  Maille (par exemple une nature de déclaration portée par TAXO-01K) ; l'explorateur ne la devine jamais à
  partir du nom. Sans elle, tous les symboles ont la même teinte.

La même palette sert ensuite la vue Couches, pour que les deux formes se ressemblent.

### E8 — Le code de la méthode, à droite

Choisir un nœud ouvre, dans la colonne de droite déjà occupée par les panneaux de l'explorateur, un panneau
« Code » : le chemin du fichier, les lignes, et le code coloré syntaxiquement, les lignes de la preuve
surlignées. Choisir une flèche ouvre son panneau de preuves, où chaque localisation propose « Voir le
code » : pour un `CALLS`, la ligne du site d'appel est surlignée dans la méthode appelante.

Le code est lu par l'opération réservée `get_source` de `taxo-query/1` (ARCHITECTURE § 12.3), qui est
implémentée par ce récit avec ses règles déjà écrites :

- **code d'un symbole, jamais un fichier entier** : les lignes d'une preuve qui localise ce symbole
  (`symbol` égal au nœud), plafonnées (200 lignes, 16 Ko) ; au-delà, le début est montré et la coupure
  est dite ;
- lu **à l'instantané de l'analyse** (son commit), par la capacité `snapshots`, jamais dans la copie de
  travail du moment ;
- montré **seulement si** l'empreinte des lignes recalculée est égale au `content_hash` de la preuve
  (§ 5.5) ; sinon, Taxo dit que le code ne correspond plus à la preuve, et n'affiche rien ;
- **son propre double consentement** (§ 12.6) : un réglage serveur, désactivé par défaut, et l'accord de
  la requête, donné par le clic sur « Voir le code ». L'accord du diff ne l'autorise jamais. Réglage
  désactivé : le panneau le dit, avec le nom du réglage ;
- jamais lus : les fichiers confidentiels, binaires, liens, sous-modules, trop gros ou générés (§ 12.6, 3) ;
- rien n'est conservé : le code n'entre ni dans la Maille, ni dans un fait, ni dans un cache ; il n'est
  jamais transmis à Minia par l'explorateur.

Sans preuve qui localise le nœud, le panneau dit « Taxo n'a pas de preuve qui situe ce nœud dans le code »
et ne cherche pas ailleurs (aucune recherche par nom de fichier ou de classe). La coloration syntaxique
est faite dans le navigateur par une bibliothèque générique, choisie selon l'extension du fichier, sans
règle propre à Java dans l'explorateur.

`get_source` est servi comme les autres opérations : table explicite, `describe` ne le propose que s'il
est servable. `protocol.ts` reste le seul module de l'explorateur à parler au serveur.

## Tests

- `chain.test.ts`, sur des vues synthétiques écrites à la main : chaîne simple, deux frères, lien de
  côté, revisite sans arc, note de frontière locale, coupure de sélection, feuille sans objet et feuille valeur (dessinées et exportées), relation inconnue de forme
  `CHAÎNE`, pas de chaîne entrant, nom très long passé à la ligne.
- Export Mermaid : texte attendu écrit à la main, échappement des caractères spéciaux.
- `protocol.test.ts` : une demande par pas envoie `steps`, une demande sans pas reste inchangée à l'octet.
- `explorer.dom.test.tsx` : l'onglet « Chaîne » s'affiche, choisir une flèche ouvre la preuve, la
  pastille de coupure développe le nœud.
- Couleurs : un type connu prend son jeton, un type inconnu la teinte neutre, la légende ne liste que
  les types présents ; contraste vérifié dans les deux thèmes.
- `get_source` (backend) : extrait d'un symbole à l'instantané de l'analyse ; refus sans consentement de
  la requête, refus réglage désactivé, refus quand l'empreinte diffère, refus d'un fichier confidentiel,
  plafond de lignes dit, aucun fichier entier ; la demande ne modifie aucune table.
- Panneau Code (DOM) : lignes de la preuve surlignées, message quand le réglage est désactivé, message
  quand aucune preuve ne localise le nœud.
- `architecture.test.ts` inchangé et vert : aucune relation ni type nommé dans l'explorateur.

## Critères d'acceptation

1. Sur `student-course-demo`, la route `GET /api/courses` se lit de haut en bas dans l'onglet Chaîne,
   chaque flèche portant son verbe et son badge.
2. Avant TAXO-01K, la chaîne montre la route, le contrôleur, puis ce que Taxo ne sait pas : rien n'est
   inventé au-delà.
3. Après TAXO-01K, « implémente » est dessiné sur le côté et l'appel vers `findAll()` s'arrête sur une
   note de frontière lisible.
4. Chaque type de la vue a sa couleur et sa légende, lisibles en thème clair et sombre.
5. Choisir `CourseController#getCourses()` montre son code à droite, lignes de la preuve surlignées, quand
   le réglage serveur l'autorise ; un code qui ne correspond plus à la preuve n'est jamais montré.
6. La vue Liste est inchangée ; la vue Couches ne change que par la palette des types.
7. Aucun changement du moteur de voisinage, du contrat des faits, de la Maille, de Minia ni de la MIP. Le
   protocole ne gagne que l'opération réservée `get_source`, selon § 12.3 et § 12.6.
8. Tests verts : backend `pytest -q`, frontend `npm ci && npm test && npm run build`.

## Découpage proposé

- **PR 1 — Vue Chaîne.** Table des formes, palette des types et légende, `chain.ts`, onglet Chaîne, notes
  et pastilles, tests. Utilisable dès maintenant avec `HANDLED_BY`.
- **PR 2 — Parcours et export.** Envoi de `steps` par `protocol.ts`, parcours « Appels depuis une
  route », export Mermaid, essai sur `student-course-demo` après TAXO-01K avec une capture publiée dans
  ce récit.
- **PR 3 — Le code à droite.** Opération `get_source` (backend, consentement, empreinte, plafonds), panneau
  Code et coloration syntaxique dans l'explorateur, tests.

## Hors périmètre

- Tout ordre d'exécution, diagramme de séquence ou `DISPATCHES_TO`.
- Toute lecture de code hors d'une preuve, tout fichier entier, toute édition du code depuis le portail.
- Un nom court de symbole fourni par le serveur (classe et méthode séparées) : il demanderait une
  donnée nouvelle portée par le producteur ; l'explorateur ne découpe jamais une référence lui-même. À
  proposer séparément si le nom complet passé à la ligne ne suffit pas.
- Toute relation propre à Spring ou JPA, tout rôle « contrôleur », « service » ou « repository ».
- La MIP, Minia, l'Arbre et la Forêt.

## Maquette

Maquette de la proposition, couleurs et panneau de code compris (page privée du projet) :
<https://claude.ai/artifact/3Sh56uyqqsv18k3xmLARPF>
