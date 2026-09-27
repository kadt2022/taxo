# Banc TAXO-POC-05 — questions

*Telles que chaque bras les reçoit, dans cet ordre. Dépôt TAKIBO, commit `6d9b214`.*

1. **Isolation.** Un utilisateur authentifié, dont le token est situé dans le space A d'une
   organisation, peut-il retirer un rôle à un utilisateur du space B de la même organisation, par
   `DELETE /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users/{userId}/roles/{roleCode}` ?
   Où cela se décide-t-il ?
2. **Règle d'URL.** Quelle règle de sécurité HTTP s'applique à
   `GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users`, et quelle méthode traite cette route ?
3. **Rôles.** Quels rôles faut-il pour que la politique d'autorisation accepte cette même route
   (question 2) ?
4. **Autre application.** Qui protège `GET /api/admin/users`, et comment ?
5. **Applications.** Combien d'applications Spring Boot ce dépôt contient-il, et laquelle sert les
   routes `/api/v1/**` ?
6. **Commit.** Que change le commit `f18ff9c` pour la sécurité des routes HTTP ?
7. **Debug.** `GET /debug/secure/secret` est-il accessible en production ?
8. **Données.** Quels comptes détiennent aujourd'hui le rôle `R_ORG_OWNER` dans une organisation
   donnée ?
