# Banc TAXO-POC-05 — quatre bras : Taxo aide-t-il, gêne-t-il, ou vérifie-t-il ?

*Préparé le 2026-09-27. Rien n'a été exécuté.*

Ce banc mesure une seule chose : **à quel endroit Taxo sert, s'il sert**. Trois résultats sont
acceptables d'avance, et le troisième n'est pas un échec du banc :

| Résultat | Conséquence |
| --- | --- |
| Taxo + Minia > Minia | la piste agent (TAXO-01I, appels, `get_source`) est ouverte |
| Taxo + Minia ≈ Minia | on regarde la preuve, la reproductibilité et le coût, pas l'exactitude |
| Taxo + Minia < Minia | Taxo sort du chemin de raisonnement ; le bras D dit s'il garde le rôle de vérificateur |

| Fichier | Contenu | Qui l'écrit |
| --- | --- | --- |
| [PROTOCOLE.md](PROTOCOLE.md) | bras, gel, consignes, déroulé | préparé ; à signer avant la première exécution |
| [QUESTIONS.md](QUESTIONS.md) | les huit questions, telles que les bras les reçoivent | préparé |
| [GRILLE.md](GRILLE.md) | barème et mesures | préparé |
| [VERITES-DE-REFERENCE.md](VERITES-DE-REFERENCE.md) | les réponses attendues, avec preuves | **brouillon** : établi à la main dans le code, sans Taxo ; chaque vérité doit être validée par le propriétaire de TAKIBO |
| `RESULTATS.md` | les mesures | écrit après la campagne, jamais avant |

Aucun bras n'a accès à ce dossier.
