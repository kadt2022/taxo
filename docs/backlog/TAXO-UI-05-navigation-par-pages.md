# TAXO-UI-05 — Une page par fonction : Overview devient un tableau de bord

Statut : rédigé le 2026-10-02. Passe avant la tranche D de [TAXO-01F](TAXO-01F-comparaison-persistee.md) :
le résultat d'une comparaison doit d'abord avoir sa place.

Portée : portail seulement. Aucun moteur, aucune API, aucune donnée ne change.

## Constat

Le portail est une longue page : vue d'ensemble, comparateur, technologies, limites, détails, routes,
« Interroger Taxo » et historique sont empilés. Le menu vertical ne fait que défiler vers des ancres, et
la barre du haut répète une partie de cette navigation. Le comparateur est déjà presque une application
incrustée au milieu du tableau de bord. La tranche D de 01F l'agrandirait encore, au mauvais endroit.

## Intention

En tant qu'utilisateur, j'ouvre Taxo sur un tableau de bord qui résume le projet, puis chaque fonction a
sa page : je vais aux analyses, je compare, j'explore les routes ou la sécurité, et l'adresse dit où je
suis.

## Menu vertical

```text
[ Projet : Boutique  ⌄ ]

Overview

Analyses
Comparaisons
Interroger Taxo

Technologies
Routes
Architecture
Sécurité
Données et stockage

Historique Git

Limites
Non interprétées
```

Chaque entrée ouvre une page ; l'entrée de la page affichée est marquée. Les comptes restent ceux de
l'analyse affichée. « Interroger Taxo », qui existe déjà, devient une page plutôt qu'un bloc du tableau
de bord.

## Pages

| Adresse | Page | Contenu |
| --- | --- | --- |
| `#/` | Overview | les six cartes (Projet, Git, API, Architecture, Sécurité, Données), la ligne des limites, l'analyse affichée (date, commit, « Voir l'analyse »), et deux actions : lancer une analyse, comparer deux analyses |
| `#/projets` | Projets | les projets connus, leur dossier, le projet actif marqué ; « Ouvrir » en fait le projet actif, « Ajouter un projet » en enregistre un nouveau (`?ajouter=1` ouvre le formulaire) |
| `#/analyses` | Analyses | en tête, le poste de lancement : analyser le projet actif, la dernière analyse, puis la progression par étapes réelles pendant l'analyse (une piste, un segment par étape annoncée par le serveur, l'étape en cours et le compte des étapes terminées ; aucun pourcentage). Puis toutes les analyses terminées, la date d'abord puis le contexte Git ; recherche ; pour chacune « Ouvrir » et « Comparer avec… » |
| `#/analyses/<id>` | Une analyse | date, commit (identifiant, auteur, message), faits, analyseurs et leur état, zones inconnues, détails techniques ; « Afficher cette analyse » et « Comparer cette analyse avec… » |
| `#/comparaisons` | Comparaisons | le comparateur (tranche C de 01F) ; `?a=` fixe A |
| `#/comparaisons?a=<A>&b=<B>` | Résultat | la comparaison A → B (tranche B, puis D) ; « Changer les analyses », « Inverser le sens » |
| `#/technologies` | Technologies | technologies reconnues et fichiers justificatifs |
| `#/routes` | Routes | les routes, filtres, preuves |
| `#/architecture` | Architecture | modules, dépendances entre modules, applications, dits en phrases avec leur preuve |
| `#/securite` | Sécurité des routes | les règles de protection observées par Taxo, route par route ; la page dit qu'elle n'est pas encore une analyse de sécurité complète |
| `#/donnees` | Données et stockage | « Non analysé » tant qu'aucun analyseur n'est branché |
| `#/historique` | Historique Git | l'historique consulté sur demande |
| `#/limites` | Limites | les zones non lues ou non interprétées, par analyseur |
| `#/non-interpretees` | Non interprétées | les routes dont Taxo ne sait pas établir la protection |
| `#/interroger` | Interroger Taxo | la question posée aux faits de l'analyse |
| toute autre adresse | Page introuvable | une page d'état et un lien vers Overview, jamais un écran vide |

- **Le projet fait partie de l'adresse** (`?projet=<id>`) : une page rechargée ou copiée rouvre le même
  projet ; un projet inconnu ramène au premier.
- **Première analyse en cours** : seule Overview la suit ; les pages qui lisent des faits enregistrés
  disent qu'elles attendent sa fin.
- **Historique Git et Analyses restent distincts** : l'un dit ce qui est arrivé au code, l'autre ce que
  Taxo a observé et quand. Une analyse renvoie à son commit.
- **L'analyse affichée** : les pages de domaine montrent l'analyse affichée, la plus récente par défaut.
  « Afficher cette analyse » en change. Une autre que la plus récente est signalée en haut de chaque page
  de domaine : « Vous consultez une analyse antérieure — 30 sept. 2026, 19:04:12 », avec « Revenir à la
  dernière analyse ». Ce choix suit la navigation d'une page à l'autre.
- **Chaque carte d'Overview** suit la même forme : domaine, information principale, court résumé,
  « Explorer → » vers sa page, y compris quand Taxo n'a rien analysé pour ce domaine : la page dit
  pourquoi. Overview ne contient jamais la version complète d'une fonction.

## Barre du haut

Réservée à l'identité de Taxo et aux commandes globales : ni sélecteur de projet, ni bouton d'analyse permanent.

```text
[T] Taxo     Fichier     Analyse     Affichage     Aide
```

- **Fichier** : ouvrir un projet, ajouter un projet (vers la page Projets).
- **Analyse** : un panneau de commande, pas une liste.
  - Nouvelle analyse : ce qu'elle fait, le projet actif, et « Lancer l'analyse globale » (« Lancer la
    première analyse » si le projet n'en a aucune ; « Analyse en cours… » pendant une analyse).
  - Dernière analyse : sa date, ce qu'elle a lu, « Voir l'analyse ».
  - Toutes les analyses, Comparer deux analyses.
  - Sans projet actif : « Sélectionnez d'abord un projet », et « Choisir un projet ».
- **Affichage** : revenir à la dernière analyse, choisir l'analyse affichée.
- **Aide** : version, analyse locale.

**Sélecteur de projet**, en tête du menu vertical, au-dessus d'Overview : le projet actif (pastille à son
initiale, nom, âge de la dernière analyse) et une flèche. Au clic, il se déplie : tous les projets avec
l'actif coché, une recherche à partir de six projets, « Ajouter un projet » sur place, « Gérer les
projets » vers la page Projets. Échap ou un clic ailleurs le referme.

Trois rôles distincts : **Projets**, sur quoi je travaille ; **Analyse** (barre du haut), quelle analyse je
lance ; **Analyses** (menu vertical), ce que Taxo possède déjà. Le projet actif reste visible, discret,
dans le sélecteur de projet, en tête du menu vertical.

## Critères d'acceptation

1. Chaque adresse du tableau ouvre sa page, y compris après un rechargement ; le bouton Précédent du
   navigateur revient à la page d'avant. Une adresse inconnue ou une analyse supprimée donne une page
   d'état.
2. Une comparaison a sa propre adresse : la copier et la rouvrir montre la même comparaison.
3. Overview ne contient ni comparateur, ni liste de technologies, ni tableau de routes, ni historique.
4. Le menu vertical marque la page affichée ; la barre du haut ne contient plus de lien de navigation.
5. Aucun moteur ni aucune API ne change ; les tests existants des panneaux restent valides.
