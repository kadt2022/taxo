import {describe, expect, it} from 'vitest';
import {ORIGINS, VALIDITIES, label, named, premise} from './vocabulary';

describe('lecture humaine des faits', ()=>{
  it('dit l’origine et la validité sans prétendre à une confirmation humaine', ()=>{
    expect(label(ORIGINS, 'INFERRED')).toBe('Déduit par Taxo');
    expect(label(ORIGINS, 'HUMAN_VALIDATED')).toBe('Validé par une personne');
    expect(label(VALIDITIES, 'VALID')).toBe('À jour');
    expect(label(VALIDITIES, 'INCONNU')).toBe('INCONNU');
  });

  it('nomme court un symbole et une application', ()=>{
    expect(named('symbol:java:com.acme.web.OrderController#get()')).toBe('OrderController.get()');
    expect(named('symbol:java:com.acme.security.ShopSecurity')).toBe('ShopSecurity');
    expect(named('application:shop-app/src/main/java/com/acme/shop/ShopApplication.java#ShopApplication')).toBe('application ShopApplication');
    expect(named('repository:p1', {id:'p1', name:'Boutique'})).toBe('dépôt Boutique');
  });

  it('dit chaque forme de prémisse en clair, et toute autre forme telle quelle', ()=>{
    expect(premise('HANDLED_BY : endpoint:GET /orders -> symbol:java:com.acme.web.OrderController#get()'))
      .toBe('route GET /orders est traité par OrderController.get()');
    expect(premise('DEPENDS_ON : module:web -> module:security (implementation)'))
      .toBe('module web dépend de module security (implementation)');
    expect(premise('ligne 14 : /** -> hasRole("USER")')).toBe('Règle de sécurité, ligne 14 : /** → hasRole("USER")');
    expect(premise('application:shop/ShopApplication.java#ShopApplication charge symbol:java:com.acme.security.ShopSecurity#chain(HttpSecurity)'))
      .toBe('application ShopApplication charge ShopSecurity.chain(HttpSecurity)');
    expect(premise('constructor : a -> b')).toBe('constructor : a -> b');
    expect(premise('une phrase libre')).toBe('une phrase libre');
  });
});
