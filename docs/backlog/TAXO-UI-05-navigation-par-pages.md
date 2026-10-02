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
| `#/analyses` | Analyses | toutes les analyses complètes, la date d'abord puis le contexte Git ; recherche ; pour chacune « Ouvrir » et « Comparer avec… » |
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

Réservée aux commandes globales ; la navigation est dans le menu vertical.

- **Fichier** : ajouter un projet.
- **Analyse** : lancer l'analyse globale, comparer deux analyses.
- **Affichage** : revenir à la dernière analyse, choisir l'analyse affichée.
- **Aide** : version, analyse locale.

## Critères d'acceptation

1. Chaque adresse du tableau ouvre sa page, y compris après un rechargement ; le bouton Précédent du
   navigateur revient à la page d'avant. Une adresse inconnue ou une analyse supprimée donne une page
   d'état.
2. Une comparaison a sa propre adresse : la copier et la rouvrir montre la même comparaison.
3. Overview ne contient ni comparateur, ni liste de technologies, ni tableau de routes, ni historique.
4. Le menu vertical marque la page affichée ; la barre du haut ne contient plus de lien de navigation.
5. Aucun moteur ni aucune API ne change ; les tests existants des panneaux restent valides.
