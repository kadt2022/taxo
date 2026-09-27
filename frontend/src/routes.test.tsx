import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {applicationName, chainName, filterRoutes, proofText, protectionText, RouteDetail, RoutesTable, ruleText, shortSymbol, type RouteRow} from './routes';

const admin:RouteRow={endpoint:'endpoint:GET /api/admin/users', verb:'GET', path:'/api/admin/users', state:'PROTECTED',
  handlers:[{subject:'endpoint:GET /api/admin/users', relation:'HANDLED_BY', object:'symbol:java:com.takibo.adp.test.controller.TestController#adminUsers(Authentication)',
    status:'OBSERVED', evidence:[{path:'TestController.java', line_start:48, line_end:48}]}],
  applications:[{subject:'endpoint:GET /api/admin/users', relation:'SERVED_BY', status:'INFERRED',
    object:'application:takibo-adp-test/src/main/java/com/takibo/adp/test/AdpTestApplication.java#AdpTestApplication',
    derivation:{premises:['BUILT_FROM : application:… -> module:takibo-adp-test'], rule:'spring-boot.application-loads-controller', counter_examples_checked:[], known_gaps:[]}}],
  matched:[{subject:'endpoint:GET /api/admin/users', relation:'MATCHED_BY', object:'route-pattern:/**', status:'INFERRED',
    qualifiers:{filter_chain:'symbol:java:com.takibo.adp.test.config.TestSecurityConfig#securityFilterChain(HttpSecurity)'},
    derivation:{premises:['SERVED_BY : …'], rule:'spring-security.first-matching-pattern',
      counter_examples_checked:['SecurityConfig : non chargée (hors du classpath)'], known_gaps:[]}}],
  rules:[{subject:'route-pattern:/**', relation:'AUTHORIZED_BY', object:'symbol:java:com.takibo.adp.test.config.TestSecurityConfig#adpAuthorizationManager()', status:'OBSERVED'}],
  protections:[{subject:'endpoint:GET /api/admin/users', relation:'PROTECTED_BY', status:'INFERRED',
    object:'symbol:java:com.takibo.adp.test.config.TestSecurityConfig#adpAuthorizationManager()'}],
  gaps:[]};
const debug:RouteRow={...admin, endpoint:'endpoint:GET /debug/secure/secret', path:'/debug/secure/secret', state:'NOT_INTERPRETED',
  applications:[], matched:[], rules:[], protections:[],
  gaps:[{subject:'endpoint:GET /debug/secure/secret', type:'NOT_INTERPRETED', evaluator:'taxo.spring-boot', reason:'servie peut-être par TakiboIamBootApplication (condition @Profile : chargement non établi)'}]};
const open:RouteRow={...admin, endpoint:'endpoint:GET /api/health', path:'/api/health', state:'PERMITS_ALL', protections:[],
  rules:[{subject:'route-pattern:/api/health', relation:'PERMITS_ALL', status:'OBSERVED'}]};

describe('lecture des faits d’une route', ()=>{
  it('dit les références en clair, sans rien ajouter', ()=>{
    expect(shortSymbol(admin.handlers[0].object)).toBe('TestController#adminUsers(Authentication)');
    expect(applicationName(admin.applications[0].object)).toBe('AdpTestApplication');
    expect(ruleText(admin.rules[0])).toBe('/** → TestSecurityConfig#adpAuthorizationManager()');
    expect(ruleText(open.rules[0])).toBe('/api/health → permitAll()');
    expect(protectionText(admin.protections[0])).toBe('TestSecurityConfig#adpAuthorizationManager()');
    expect(protectionText({subject:'x', relation:'PROTECTED_BY', object:'policy-rule:hasRole("ADMIN")'})).toBe('hasRole("ADMIN")');
    expect(chainName(admin.matched[0])).toBe('TestSecurityConfig#securityFilterChain(HttpSecurity)');
    expect(chainName(admin.handlers[0])).toBe('');
    expect(proofText({path:'A.java', line_start:3, line_end:5})).toBe('A.java:3-5');
    expect(proofText({path:'build.gradle'})).toBe('build.gradle');
  });
  it('filtre par chemin, verbe et état établi', ()=>{
    const rows=[admin, debug, open];
    expect(filterRoutes(rows, 'admin', 'ALL')).toEqual([admin]);
    expect(filterRoutes(rows, 'get /debug', 'ALL')).toEqual([debug]);
    expect(filterRoutes(rows, '', 'PROTECTED')).toEqual([admin]);
    expect(filterRoutes(rows, '', 'PERMITS_ALL')).toEqual([open]);
    expect(filterRoutes(rows, '', 'GAPS')).toEqual([debug]);
  });
});

describe('page Routes', ()=>{
  it('montre la chaîne de preuve d’une route, avec ses preuves et ses prémisses', ()=>{
    const html=renderToStaticMarkup(<RouteDetail row={admin}/>);
    expect(html).toContain('AdpTestApplication');
    expect(html).toContain('TestController.java:48');
    expect(html).toContain('SecurityConfig : non chargée (hors du classpath)');
    expect(html).toContain('Protégée');
    expect(html).not.toMatch(/Minia|probablement/);
  });
  it('dit exactement pourquoi une route n’est pas interprétée', ()=>{
    const html=renderToStaticMarkup(<RouteDetail row={debug}/>);
    expect(html).toContain('Non interprétée');
    expect(html).toContain('condition @Profile');
    expect(html).toContain('Applications Spring Boot');
  });
  it('résume chaque route en une ligne du tableau', ()=>{
    const html=renderToStaticMarkup(<RoutesTable routes={[admin, debug]} selected="" onSelect={()=>{}}/>);
    expect(html).toContain('GET /api/admin/users');
    expect(html).toContain('/** → TestSecurityConfig#adpAuthorizationManager()');
    expect(html.match(/<tr/g)?.length).toBe(3);
  });
});
