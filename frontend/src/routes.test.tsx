import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {applicationName, chainName, filterRoutes, loadRoutes, RoutesPanel, RoutesView, proofText, protectionText, RouteDetail, RoutesTable, ruleText, shortSymbol, type RouteRow, type RoutesResult} from './routes';

const admin:RouteRow={endpoint:'endpoint:GET /api/admin/users', verb:'GET', path:'/api/admin/users', state:'PROTECTED',
  handlers:[{subject:'endpoint:GET /api/admin/users', relation:'HANDLED_BY', object:'symbol:java:com.example.adp.test.controller.TestController#adminUsers(Authentication)',
    status:'OBSERVED', evidence:[{path:'TestController.java', line_start:48, line_end:48}]}],
  applications:[{subject:'endpoint:GET /api/admin/users', relation:'SERVED_BY', status:'INFERRED',
    object:'application:example-adp-test/src/main/java/com/example/adp/test/AdpTestApplication.java#AdpTestApplication',
    derivation:{premises:['BUILT_FROM : application:… -> module:example-adp-test'], rule:'spring-boot.application-loads-controller', counter_examples_checked:[], known_gaps:[]}}],
  matched:[{subject:'endpoint:GET /api/admin/users', relation:'MATCHED_BY', object:'route-pattern:/**', status:'INFERRED',
    qualifiers:{filter_chain:'symbol:java:com.example.adp.test.config.TestSecurityConfig#securityFilterChain(HttpSecurity)'},
    derivation:{premises:['SERVED_BY : …'], rule:'spring-security.first-matching-pattern',
      counter_examples_checked:['SecurityConfig : non chargée (hors du classpath)'], known_gaps:[]}}],
  rules:[{subject:'route-pattern:/**', relation:'AUTHORIZED_BY', object:'symbol:java:com.example.adp.test.config.TestSecurityConfig#adpAuthorizationManager()', status:'OBSERVED'}],
  protections:[{subject:'endpoint:GET /api/admin/users', relation:'PROTECTED_BY', status:'INFERRED',
    object:'symbol:java:com.example.adp.test.config.TestSecurityConfig#adpAuthorizationManager()'}],
  gaps:[]};
const debug:RouteRow={...admin, endpoint:'endpoint:GET /debug/secure/secret', path:'/debug/secure/secret', state:'NOT_INTERPRETED',
  applications:[], matched:[], rules:[], protections:[],
  gaps:[{subject:'endpoint:GET /debug/secure/secret', type:'NOT_INTERPRETED', evaluator:'taxo.spring-boot', reason:'servie peut-être par DemoApplication (condition @Profile : chargement non établi)'}]};
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

describe('chargement et affichage de la page', ()=>{
  const result={routes:[admin, debug, open], unestablished:[{subject:'symbol:java:x.Generated', type:'NOT_INTERPRETED',
    evaluator:'taxo.spring-api', reason:'Routes héritées non interprétées'}]};
  const view=(props:Partial<Parameters<typeof RoutesView>[0]>)=>renderToStaticMarkup(<RoutesView result={null} error=""
    text="" filter="ALL" selected="" onText={()=>{}} onFilter={()=>{}} onSelect={()=>{}} {...props}/>);
  it('charge les routes de l’analyse choisie, et ignore une réponse devenue sans objet', async ()=>{
    const got:RoutesResult[]=[], errors:string[]=[], paths:string[]=[];
    const request=async <T,>(path:string)=>{paths.push(path);return result as T;};
    loadRoutes(request, '/projects/p', 's1', {onResult:value=>got.push(value), onError:message=>errors.push(message)});
    const stop=loadRoutes(request, '/projects/p', 's2', {onResult:value=>got.push(value), onError:message=>errors.push(message)});
    stop();
    await Promise.resolve();await Promise.resolve();
    expect(paths).toEqual(['/projects/p/scans/s1/routes', '/projects/p/scans/s2/routes']);
    expect(got).toEqual([result]);
    const failing=async <T,>():Promise<T>=>{throw new Error('Analyse introuvable.');};
    loadRoutes(failing, '/projects/p', 's3', {onResult:value=>got.push(value), onError:message=>errors.push(message)});
    await Promise.resolve();await Promise.resolve();
    expect(errors).toEqual(['Analyse introuvable.']);
  });
  it('dit qu’elle charge, puis montre l’erreur telle quelle', ()=>{
    expect(view({})).toContain('Chargement des routes');
    expect(view({error:'Analyse introuvable.'})).toContain('Analyse introuvable.');
  });
  it('filtre, compte et détaille la route choisie', ()=>{
    const html=view({result, text:'admin', selected:'endpoint:GET /api/admin/users'});
    expect(html).toContain('1 sur 3 routes');
    expect(html).toContain('Traitée par');
    expect(html).toContain('Des routes peuvent manquer (1)');
    expect(html).toContain('Routes héritées non interprétées');
  });
  it('dit qu’aucune route n’est établie plutôt que d’afficher un tableau vide', ()=>{
    expect(view({result:{routes:[], unestablished:[]}})).toContain('Aucune route HTTP établie');
  });
});

describe('réserves', ()=>{
  it('montre les limites connues d’une déduction et signale une route protégée avec réserve', ()=>{
    const reserved:RouteRow={...admin, protections:[{...admin.protections[0], derivation:{premises:['MATCHED_BY : …'],
      rule:'spring-security.route-authorization-applies', counter_examples_checked:[], known_gaps:['la décision du gestionnaire n’est pas lue']}}],
      gaps:[{subject:admin.endpoint, type:'NOT_INTERPRETED', evaluator:'taxo.spring-security', reason:'sécurité de méthode non interprétée (@PreAuthorize)'}]};
    const detail=renderToStaticMarkup(<RouteDetail row={reserved}/>);
    expect(detail).toContain('Limites connues');
    expect(detail).toContain('sécurité de méthode non interprétée');
    expect(renderToStaticMarkup(<RoutesTable routes={[reserved]} selected="" onSelect={()=>{}}/>)).toContain('avec réserve');
  });
  it('commence par charger, sans rien affirmer', ()=>{
    const pending=()=>new Promise<never>(()=>{});
    const html=renderToStaticMarkup(<RoutesPanel base="/projects/p" scanId="s1" request={pending}/>);
    expect(html).toContain('Chargement des routes');
    expect(html).not.toContain('<table');
  });
});
