# Banc TAXO-POC-01 — questions

Douze questions, dans cet ordre, identiques pour les deux bras. Pour chacune : une conclusion, puis
les preuves (fichier et lignes). Si tu ne peux pas conclure, dis-le et dis pourquoi.

Certaines de ces questions n'ont pas de réponse dans le code. Répondre « hors périmètre » ou
« indécidable statiquement » est alors la bonne réponse, et deviner coûte plus cher que se taire.

---

**Q1.** Quelle protection s'applique à `GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/users` ?
Donne la chaîne complète, du contrôleur jusqu'au composant qui décide.

**Q2.** Quels rôles cette route exige-t-elle ?

**Q3.** Le filtre `OrgBoundaryFilter` s'applique-t-il à cette route ?

**Q4.** `POST /api/v1/auth/login` est-elle protégée par le même mécanisme d'autorisation que la
route de Q1 ?

**Q5.** Toutes les routes `/api/v1/**` passent-elles par `PolicyEvaluator` ?

**Q6.** La règle `/api/orgs/**` de `SecurityConfig.java` capture-t-elle la route de Q1 ?

**Q7.** Quelle protection s'applique à `GET /api/v1/orgs/{orgCode}/spaces/{spaceCode}/roles` ?

**Q8.** Quelle protection s'applique à `GET /api/v1/me/spaces` ?

**Q9.** Quelle protection s'applique à `GET /api/health` ?

**Q10.** Quelle protection s'applique à `GET /api/public/info` ?

**Q11.** Quelle protection s'applique à `GET /api/dashboard` ?

**Q12.** Combien d'applications déployables ce dépôt contient-il, et laquelle sert les routes
`/api/v1/**` ?
