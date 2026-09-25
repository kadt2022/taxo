# ADR 0008 — Minia peut lire le diff d'un commit, jamais comme un fait

Date : 2026-09-25
Statut : Proposé
Dépend de : ADR 0004 (monolithe modulaire, règle 14), ADR 0007 (faits Git)
Révise : la règle de TAXO-MINIA-01 « aucun code source brut envoyé au modèle »

## Contexte

MINIA-01 interdisait tout code source à Minia. Cette contrainte a établi la frontière : Minia n'est pas
un « Taxo bis », elle n'établit rien, elle explique ce que Taxo sait. Mais elle laisse Minia sans matière
pour une question comme « quel risque apporte ce commit ? » : Taxo sait que `CorsAllowedOrigins.java`
a changé, pas ce qui a changé dedans, tant qu'aucun évaluateur ne sait le formaliser.

> Taxo établit. Git montre ce qui a changé. Minia lit les deux et explique.

## Décision

1. **Le diff est du contexte, pas un fait.** Les faits de Taxo restent la vérité structurée, seuls
   citables (`cited` ne contient que des références `F…`). Ce que Minia déduit du diff est une
   interprétation non vérifiée, au conditionnel, affichée dans le bloc « Ce que Minia en déduit ». Une
   réponse de Minia ne devient jamais un fait (ADR 0004, règle 14).
2. **Un seul lecteur de code.** Le diff est lu par `ProjectHistory` (TAXO-HIST-02), avec ses refus :
   `.env` et fichiers confidentiels (nom seul), binaires, liens, sous-modules et fichiers trop gros ne
   sont jamais lus, d'un côté comme de l'autre. Aucune commande Git n'exécute de hook, de filtre ni de
   code du dépôt. Minia n'a pas de moteur de lecture propre.
3. **Le diff seulement.** Seuls les blocs modifiés (avec les lignes de contexte du diff) sont transmis,
   jamais les fichiers entiers ni le reste du dépôt. Limites : 20 fichiers, 1 500 lignes, 32 Ko (pour tenir, avec les faits, dans la fenêtre de 16 384 tokens de Minia). Un
   fichier qui dépasse n'est pas tronqué : il n'est pas transmis. Les fichiers générés (verrous de
   dépendances, `*.min.js`, `*.map`, `*.snap`) ne sont pas lus. Chaque fichier non transmis est nommé
   avec sa raison (`LIMIT`, `GENERATED`, `CONFIDENTIAL`, `BINARY`, `TOO_LARGE`, `NOT_A_REGULAR_FILE`),
   et la réponse le dit.
4. **Double consentement.** `MINIA_SOURCE_CONTEXT=off` (défaut) ou `diff`. Même à `diff`, chaque demande
   doit l'autoriser (`source_context: true`, case « Autoriser Minia à lire le diff de ce commit »).
   `GET /api/minia/status` indique le réglage et si le modèle est distant (`remote`) : le portail avertit
   alors que du code quittera la machine, et la case n'est pas cochée par défaut.
5. **Le code est une donnée.** Les consignes du modèle disent que le diff peut contenir des commentaires
   ou chaînes ressemblant à des instructions, et qu'il ne faut jamais les suivre.
6. **Périmètre.** Cette tranche couvre la question sur un commit. La sélection « Interroger Taxo »
   (TAXO-QUERY-01) ne relit toujours pas le dépôt.

## Conséquences

- La phrase « Minia ne transmet jamais le code source » n'est vraie que si `MINIA_SOURCE_CONTEXT=off`.
  Elle est remplacée par : « Minia ne reçoit du code que le diff d'un commit, sur double accord ».
- Avec un Ollama local, rien ne quitte la machine. Avec un Ollama distant, le diff la quitte : c'est un
  choix explicite de l'administrateur puis de l'utilisateur.
- Un petit modèle (qwen2.5:3b) reste lisible grâce aux limites ; un commit de 200 fichiers est expliqué
  sur une partie de son diff, et la réponse dit laquelle.
