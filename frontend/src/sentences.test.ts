import {describe, expect, it} from 'vitest';
import {entity, name, plain, premise, relation, requirement, subjectOf} from './sentences';
import {ORIGINS, VALIDITIES, label} from './vocabulary';

const said=(text:string)=>plain(premise(text));

describe('rendu humain typé des faits', ()=>{
  it('dit l’origine et la validité sans prétendre à une confirmation humaine', ()=>{
    expect(`${label(ORIGINS, 'INFERRED')} · ${label(VALIDITIES, 'VALID')}`).toBe('Déduit par Taxo · Valide');
    expect(label(ORIGINS, 'HUMAN_VALIDATED')).toBe('Validé par une personne');
    expect(label(VALIDITIES, 'REVALIDATION_REQUIRED')).toBe('À revérifier');
    expect(label(VALIDITIES, 'STALE')).toBe('Périmé');
  });

  it('nomme une entité par son type', ()=>{
    expect(name(entity('symbol:java:com.acme.web.OrderController#get()'))).toBe('OrderController.get()');
    expect(name(entity('symbol:java:com.acme.security.ShopSecurity'))).toBe('ShopSecurity');
    expect(name(entity('application:shop/src/ShopApplication.java#ShopApplication'))).toBe('ShopApplication');
    expect(name(entity('repository:p1'), {id:'p1', name:'Boutique'})).toBe('Boutique');
    expect(name(entity('commit:0123456789abcdef'))).toBe('0123456789ab');
  });

  it('choisit la phrase selon la relation et le type des deux côtés', ()=>{
    expect(said('HANDLED_BY : endpoint:GET /orders -> symbol:java:com.acme.web.OrderController#get()'))
      .toBe('La requête GET /orders est traitée par OrderController.get().');
    expect(said('SERVED_BY : endpoint:GET /orders -> application:shop/ShopApplication.java#ShopApplication'))
      .toBe('La route GET /orders est exposée par l’application ShopApplication.');
    expect(said('MATCHED_BY : endpoint:GET /orders -> /**')).toBe('La route GET /orders correspond au motif /**.');
    expect(said('BUILT_FROM : application:shop/ShopApplication.java#ShopApplication -> module:shop-app'))
      .toBe('L’application ShopApplication est construite à partir du module shop-app.');
    expect(said('DEPENDS_ON : module:web -> module:security (implementation)'))
      .toBe('Le module web dépend du module security (implementation).');
    expect(said('AUTHORIZED_BY : /admin/** -> hasRole("ADMIN")')).toBe('Le motif /admin/** exige le rôle ADMIN.');
    // Des types inattendus pour la relation : une phrase neutre, rien de deviné.
    expect(plain(relation('HANDLED_BY', entity('module:web'), entity('file:a.java'))))
      .toBe('Le module web est traité par le fichier a.java.');
    expect(plain(relation('UNKNOWN_REL', entity('thing:x'), entity('y')))).toBe('thing:x UNKNOWN_REL y.');
  });

  it('dit ce qu’exige une règle Spring Security connue, et montre les autres telles quelles', ()=>{
    expect(said('ligne 14 : /** -> authenticated()')).toBe('La règle /** exige que l’utilisateur soit authentifié (ligne 14).');
    expect(said('ligne 14 : /** -> hasRole("USER")')).toBe('La règle /** exige le rôle USER (ligne 14).');
    expect(said('ligne 9 : GET /public/** -> permitAll()')).toBe('La règle GET /public/** est ouverte à tous (ligne 9).');
    expect(said('ligne 3 : règle non lue (expression dynamique)'))
      .toBe('La règle de la ligne 3 n’a pas pu être lue (expression dynamique).');
    const rendered=(expression:string)=>plain(requirement(expression));
    expect(rendered('hasAnyRole("A", "B")')).toBe('exige l’un des rôles A, B');
    expect(rendered("hasAuthority('read')")).toBe('exige l’autorisation read');
    expect(rendered('hasAnyAuthority("r", "w")')).toBe('exige l’une des autorisations r, w');
    expect(rendered('denyAll()')).toBe('refuse tout accès');
    expect(rendered('anonymous()')).toBe('n’admet que les utilisateurs anonymes');
    expect(rendered('fullyAuthenticated()')).toBe('exige une authentification complète');
    expect(rendered('hasRole("A") and hasRole("B")')).toBe('applique hasRole("A") and hasRole("B")');
    expect(rendered('hasRole()')).toBe('applique hasRole()');
    expect(rendered('hasAuthority("a", "b")')).toBe('applique hasAuthority("a", "b")');
  });

  it('dit le chargement d’une configuration, et laisse toute autre forme telle quelle', ()=>{
    expect(said('application:shop/ShopApplication.java#ShopApplication charge symbol:java:com.acme.security.ShopSecurity#chain(HttpSecurity)'))
      .toBe('L’application ShopApplication charge la configuration de sécurité ShopSecurity.chain(HttpSecurity).');
    expect(said('@SpringBootApplication com.acme.Shop')).toBe('@SpringBootApplication com.acme.Shop');
    expect(said('constructor : a -> b')).toBe('constructor : a -> b');
  });

  it('donne à chaque type d’entité son groupe nominal', ()=>{
    const say=(canonical:string, subject:string, object:string)=>plain(relation(canonical, entity(subject), entity(object),
      {id:'p1', name:'Boutique'}));
    expect(say('PROTECTED_BY', 'endpoint:GET /a', 'policy-rule:hasRole("USER")')).toBe('La route GET /a exige le rôle USER.');
    expect(say('PERMITS_ALL', 'endpoint:GET /a', 'policy-rule:permitAll()')).toBe('La route GET /a est ouverte à tous.');
    expect(say('WRITTEN_IN', 'file:A.java', 'language:Java')).toBe('Le fichier A.java est écrit en Java.');
    expect(say('HAS_COMMIT', 'repository:p1', 'commit:0123456789abcdef')).toBe('Le dépôt Boutique contient le commit 0123456789ab.');
    expect(say('CHILD_OF', 'commit:aaaa', 'commit:bbbb')).toBe('Le commit aaaa suit le commit bbbb.');
    expect(say('USES_TECHNOLOGY', 'repository:other', 'technology:Spring')).toBe('Le dépôt other utilise la technologie Spring.');
    expect(say('AUTHORED_BY', 'commit:aaaa', 'person:dev@example.invalid')).toBe('Le commit aaaa a pour auteur dev@example.invalid.');
    expect(say('IMPLEMENTS', 'symbol:java:a.B', 'symbol:java:a.C')).toBe('La classe B implémente l’interface C.');
    expect(say('IMPLEMENTS', 'symbol:java:a.B#run()', 'symbol:java:a.C#run()')).toBe('La méthode B.run() implémente la méthode C.run().');
    expect(say('TYPED_AS', 'symbol:java:a.B#service', 'symbol:java:a.Service')).toBe('Le champ B.service est déclaré du type Service.');
    expect(say('TYPED_AS', 'symbol:java:a.B#run(Order)/order', 'symbol:java:a.Order'))
      .toBe('La variable B.run(Order)/order est déclarée du type Order.');
    expect(say('CONTAINS', 'symbol:java:a.B#run(Order)', 'symbol:java:a.B#run(Order)/order#2'))
      .toBe('La méthode B.run(Order) contient la variable B.run(Order)/order#2.');
    expect(say('TYPED_AS', 'module:a', 'technology:Java')).toBe('Le module a est de type la technologie Java.');
    expect(say('EXTENDS', 'symbol:java:a.B', 'symbol:java:a.Base')).toBe('La classe B étend la classe Base.');
    expect(say('CONTAINS', 'file:a/B.java', 'symbol:java:a.B')).toBe('Le fichier a/B.java contient la classe B.');
    expect(say('CONTAINS', 'route-pattern:/**', 'policy-rule:x')).toBe('Le motif /** contient la règle x.');
  });

  it('titre un changement par son sujet seul', ()=>{
    expect(plain(subjectOf('endpoint:GET /orders'))).toBe('La route GET /orders');
    expect(plain(subjectOf('weird'))).toBe('weird');
  });
});
