// @vitest-environment happy-dom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {App} from './app';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

const snapshot=(commit:string)=>({repository:'r', commit:commit.repeat(40), mode:'COMMIT' as const});
const evaluation=(id:string, status='SUCCESS')=>({execution_id:`e-${id}`, evaluator_id:id, producer_version:'0.1.0', status,
  started_at:'', finished_at:'', duration_seconds:1, fact_count:10, coverage_count:0, warning_count:0, relations:{}, coverage:[],
  snapshot:snapshot('a')});
const SCANS=[
  {id:'new', created_at:'2026-10-02T10:00:00Z', snapshot:snapshot('b'), facts:[{technology:'Java', file:'pom.xml', method:'manifest'}],
   evaluations:[evaluation('taxo.inventory'), evaluation('taxo.structure')]},
  {id:'old', created_at:'2026-10-01T10:00:00Z', snapshot:snapshot('a'), facts:[], evaluations:[evaluation('taxo.inventory', 'FAILED')]}];
const CHOICES=SCANS.map(scan=>({id:scan.id, created_at:scan.created_at, snapshot:scan.snapshot, fact_count:20, failed:[],
  commit:{sha:scan.snapshot.commit, subject:`message ${scan.id}`, author:'Amina', authored_at:scan.created_at}}));
const ROUTES={routes:[{endpoint:'endpoint:GET /orders', verb:'GET', path:'/orders', state:'PROTECTED', handlers:[], applications:[],
  matched:[], rules:[], protections:[], gaps:[]}], unestablished:[]};
const STRUCTURE=[{kind:'ASSERTION', subject:'repository:p', relation:'CONTAINS', object:'module:web', status:'OBSERVED', validity:'VALID',
  evidence:[{path:'settings.gradle', line_start:1, line_end:1}]},
  {kind:'ASSERTION', subject:'module:app', relation:'DEPENDS_ON', object:'module:web', status:'OBSERVED', validity:'VALID', evidence:[]}];
const SUMMARY={before:CHOICES[1], after:CHOICES[0], evaluators:[], totals:{UNCHANGED:3}, unknown:{before:0, after:0}};

let failing:string[]=[], empty=false, streamed=false, unread=false;
// Ce que chaque analyseur a lu (TAXO-COV-01) : par defaut tout ; `unread` simule un depot sans Java.
const COVERAGE=()=>({languages:unread?['Python']:['Java'], complete:true, evaluators:[
  {evaluator_id:'taxo.spring-api', status:unread?'UNSUPPORTED':'SUCCESS', contract:'KNOWN', reads:['Java'], unread:unread?['Python']:[]},
  {evaluator_id:'taxo.spring-security', status:unread?'UNSUPPORTED':'SUCCESS', contract:'KNOWN', reads:['Java'], unread:unread?['Python']:[]}]});
// Le flux d'une analyse qui échoue après avoir annoncé ses étapes, tel que le serveur l'émet.
const FAILED_RUN=['event: analysis.started\ndata: {"evaluators":["taxo.git"]}\n\n', 'event: evaluator.started\ndata: {"evaluator":"taxo.git"}\n\n',
  'event: analysis.failed\ndata: {"message":"Dépôt illisible."}\n\n'].join('');
function answer(path:string){
  if(failing.some(part=>path.includes(part)))return {failed:true};
  if(empty&&/\/projects\/[pq]\/scans$/.test(path))return [];
  if(path.endsWith('/minia/status'))return {providers:[]};
  if(path.endsWith('/api/projects'))return [{id:'p', name:'Boutique', path:'/boutique'}, {id:'q', name:'Atelier', path:'/atelier'}];
  if(/\/projects\/[pq]\/scans$/.test(path))return SCANS;
  if(path.includes('/routes'))return ROUTES;
  if(path.endsWith('/coverage'))return COVERAGE();
  if(path.endsWith('/comparisons/analyses'))return CHOICES;
  if(path.includes('/facts?evaluator=taxo.structure'))return STRUCTURE;
  if(path.includes('/comparisons?'))return SUMMARY;
  if(path.endsWith('/analyses'))return {failed:true};
  throw new Error(`inattendu : ${path}`);
}

let host:HTMLElement, root:Root;
beforeEach(()=>{
  failing=[];empty=false;streamed=false;unread=false;
  vi.stubGlobal('fetch', vi.fn(async(url:URL, init?:RequestInit)=>{
    if(streamed&&init?.method==='POST'&&url.toString().endsWith('/analyses'))return {ok:true, json:async()=>({events:'/projects/p/analyses/j/events'})};
    if(streamed&&url.toString().endsWith('/analyses/j/events'))return {ok:true, body:new Response(FAILED_RUN).body};
    if(init?.method==='POST'&&url.toString().endsWith('/api/projects'))return {ok:true, json:async()=>({id:'r', name:'Nouveau', path:'/nouveau'})};
    const value=answer(url.toString());
    return 'failed' in value?{ok:false, status:500, json:async()=>({detail:'Panne simulée.'})}:{ok:true, json:async()=>value};}));
  host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();window.location.hash='';});

const flush=()=>act(async()=>{for(let turn=0;turn<5;turn+=1)await new Promise(resolve=>setTimeout(resolve, 0));});
async function open(hash:string){
  window.location.hash=hash;
  await act(async()=>{root.render(<App history={projectId=><p>Historique de {projectId}</p>}/>);});
  await flush();
}
async function visit(hash:string){
  await act(async()=>{window.location.hash=hash;window.dispatchEvent(new Event('hashchange'));});
  await flush();
}
const text=()=>host.textContent??'';
const current=()=>host.querySelector('.results-nav [aria-current="page"]')?.textContent;

describe('une page par fonction', ()=>{
  it('ouvre Overview en tableau de bord : cartes, analyse affichée, actions, et rien d’autre', async()=>{
    await open('#/');
    expect(current()).toContain('Overview');
    // La marque Taxo ouvre la barre du haut et mène à Overview, avant les menus globaux.
    const head=host.querySelector('.page-head .head-start');
    expect(head?.firstElementChild?.matches('a.top-brand[href="#/"]')).toBe(true);
    expect(head?.querySelector('.top-brand-text strong')?.textContent).toBe('Taxo');
    expect(head?.querySelector('.top-brand-text small')?.textContent).toBe('Software Intelligence');
    // Le lien garde un nom pour les lecteurs d'écran : le texte n'est jamais retiré, seulement masqué visuellement sur petit écran.
    expect(head?.querySelector('a.top-brand')?.textContent).toContain('Taxo');
    expect(head?.querySelector('.top-brand + .top-menu')).not.toBeNull();
    // Une seule marque : la barre latérale ne la répète pas.
    expect(host.querySelectorAll('.brand-mark')).toHaveLength(1);
    expect(text()).not.toContain('EXPLORATEUR');
    expect(host.querySelector('.overview .cards')).not.toBeNull();
    expect(text()).toContain('Dernière analyse');
    expect(host.querySelector('.overview-actions a[href="#/comparaisons"]')?.textContent).toContain('Comparer deux analyses');
    expect(host.querySelector('a[href="#/analyses/new"]')?.textContent).toBe('Voir l’analyse');
    for(const absent of ['.tags', '.routes table', '.choice-columns', '.history', '.limits', '.analysis-details', '.ask-taxo'])expect(host.querySelector(absent)).toBeNull();
    // Chaque carte mene a sa page, meme quand Taxo n'a rien analyse pour elle.
    expect(Array.from(host.querySelectorAll('.card-link')).map(link=>link.getAttribute('href')))
      .toEqual(['#/technologies', '#/historique', '#/routes', '#/architecture', '#/securite', '#/donnees']);
    expect(host.querySelector('.results-nav a[href="#/securite"] .results-count')?.textContent).toBe('1');
    expect(host.querySelector('.results-nav a[href="#/routes"] .results-count')).toBeNull();
  });

  it('liste les analyses, ouvre l’une d’elles, l’affiche, puis revient à la dernière', async()=>{
    await open('#/analyses');
    expect(current()).toContain('Analyses');
    expect(host.querySelectorAll('.analysis-list > li')).toHaveLength(2);
    // La page Analyses s'ouvre sur son poste de lancement.
    expect(host.querySelector('.analyses-page .launch .launch-button')?.textContent).toBe('Lancer l’analyse globale');
    expect(host.querySelector('.launch')?.textContent).toContain('Analyser Boutique maintenant');
    expect(host.querySelector('a[href="#/comparaisons/choix?a=old"]')).not.toBeNull();
    await visit('#/analyses/old');
    expect(text()).toContain('message old');
    expect(host.querySelector('.state-failed')).not.toBeNull();
    const show=Array.from(host.querySelectorAll('button')).find(item=>item.textContent==='Afficher cette analyse');
    await act(async()=>{show?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    await flush();
    expect(window.location.hash).toBe('#/?projet=p');
    expect(text()).toContain('Vous consultez une analyse antérieure');
    // L'analyse affichee suit la navigation d'une page a l'autre, et chaque page le rappelle.
    for(const hash of ['#/routes', '#/architecture', '#/securite', '#/technologies', '#/limites']){
      await visit(hash);
      expect(host.querySelector('.displayed-note')?.textContent, hash).toContain('Vous consultez une analyse antérieure');
    }
    const back=Array.from(host.querySelectorAll('button')).find(item=>item.textContent==='Revenir à la dernière analyse');
    await act(async()=>{back?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    expect(host.querySelector('.displayed-note')).toBeNull();
    await visit('#/analyses/inconnue');
    expect(text()).toContain('Analyse introuvable');
    await visit('#/nulle-part');
    expect(host.querySelector('main h1')?.textContent).toBe('Page introuvable');
    expect(host.querySelector('main a[href="#/"]')).not.toBeNull();
  });

  it('donne à une comparaison sa propre adresse, et au comparateur la sienne', async()=>{
    await open('#/comparaisons?a=old&b=new');
    expect(current()).toContain('Comparaisons');
    expect(text()).toContain('3 faits inchangés');
    await visit('#/comparaisons/choix?a=old');
    expect(host.querySelector('.choice-columns')).not.toBeNull();
    expect(host.querySelector('[aria-label="Analyse A"] .choice-selected')?.textContent).toContain('message old');
  });

  it('montre chaque domaine sur sa page', async()=>{
    await open('#/technologies');
    expect(host.querySelector('.tags')?.textContent).toBe('Java');
    await visit('#/architecture');
    expect(text()).toContain('Le dépôt Boutique contient le module web.');
    expect(text()).toContain('Le module app dépend du module web.');
    expect(text()).toContain('Aucune application reconnue.');
    await visit('#/securite');
    expect(host.querySelector('.routes h2')?.textContent).toBe('Sécurité des routes');
    expect(text()).toContain('Ce n’est pas encore une analyse de sécurité complète');
    expect((host.querySelector('.routes select') as HTMLSelectElement).value).toBe('PROTECTED');
    await visit('#/non-interpretees');
    expect((host.querySelector('.routes select') as HTMLSelectElement).value).toBe('GAPS');
    await visit('#/routes');
    expect(host.querySelector('.routes h2')?.textContent).toBe('Routes');
    await visit('#/limites');
    expect(host.querySelector('.limits')).not.toBeNull();
    await visit('#/donnees');
    expect(text()).toContain('aucun analyseur de données');
    await visit('#/historique');
    expect(text()).toContain('Historique de p');
    await visit('#/interroger');
    expect(current()).toContain('Interroger Taxo');
  });

  it('inverse le sens et rouvre le comparateur depuis le résultat', async()=>{
    await open('#/comparaisons?a=old&b=new');
    const click=async(label:string)=>{const target=Array.from(host.querySelectorAll('button')).find(item=>item.textContent?.includes(label));
      await act(async()=>{target?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});await flush();};
    await click('Inverser le sens');
    expect(window.location.hash).toBe('#/comparaisons?a=new&b=old&projet=p');
    await click('Changer les analyses');
    expect(window.location.hash).toBe('#/comparaisons/choix?a=new&b=old&projet=p');
    await click('Vue d’ensemble');
    expect(window.location.hash).toBe('#/?projet=p');
  });

  it('accueille un projet sans analyse, et dit les erreurs de l’API sans casser la page', async()=>{
    empty=true;
    await open('#/');
    expect(text()).toContain('Prêt pour la première analyse');
    act(()=>root.unmount());root=createRoot(host);empty=false;
    failing=['/routes', 'facts?evaluator', '/comparisons/analyses'];
    await open('#/routes');
    expect(host.querySelector('[role="alert"]')?.textContent).toBe('Panne simulée.');
    await visit('#/architecture');
    expect(host.querySelector('[role="alert"]')?.textContent).toBe('Panne simulée.');
    await visit('#/analyses');
    expect(host.querySelector('[role="alert"]')?.textContent).toBe('Panne simulée.');
  });

  it('garde le projet dans l’adresse : une comparaison rouverte rouvre son projet', async()=>{
    await open('#/comparaisons?a=old&b=new&projet=q');
    const calls=(vi.mocked(fetch).mock.calls as unknown as [URL][]).map(([url])=>url.toString());
    expect(calls.some(url=>url.includes('/projects/q/comparisons?'))).toBe(true);
    expect(calls.some(url=>url.includes('/projects/p/comparisons?'))).toBe(false);
    expect(host.querySelector('.switcher-current strong')?.textContent).toBe('Atelier');
    await visit('#/routes');
    expect(window.location.hash).toBe('#/routes?projet=q');
  });

  it('ouvre le premier projet quand l’adresse n’en nomme aucun connu, et l’y inscrit', async()=>{
    await open('#/limites?projet=disparu');
    expect(host.querySelector('.switcher-current strong')?.textContent).toBe('Boutique');
    expect(window.location.hash).toBe('#/limites?projet=p');
  });

  it('Projets : le projet actif marqué, un autre s’ouvre, un nouveau s’ajoute et devient actif', async()=>{
    await open('#/projets');
    expect(host.querySelector('aside > .switcher')).not.toBeNull();
    expect(host.querySelector('.results-nav a[href="#/projets"]')).toBeNull();
    expect(host.querySelector('.page-head .picker')).toBeNull();
    const items=Array.from(host.querySelectorAll('.project-list li'));
    expect(items.map(item=>item.querySelector('strong')?.textContent)).toEqual(['Boutique', 'Atelier']);
    expect(items[0].textContent).toContain('Projet actif');
    expect(items[0].querySelector('code')?.textContent).toBe('/boutique');
    await act(async()=>{items[1].querySelector('button')?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    await flush();
    expect(window.location.hash).toBe('#/?projet=q');
    expect(host.querySelector('.switcher-current strong')?.textContent).toBe('Atelier');
    await visit('#/projets?ajouter=1');
    const [name, path]=Array.from(host.querySelectorAll('.project-form input')) as HTMLInputElement[];
    const type=async(input:HTMLInputElement, value:string)=>act(async()=>{
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value);
      input.dispatchEvent(new Event('input', {bubbles:true}));});
    await type(name, 'Nouveau');await type(path, '/nouveau');
    await act(async()=>{host.querySelector('.project-form')?.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));});
    await flush();
    expect(host.querySelector('.switcher-current strong')?.textContent).toBe('Nouveau');
  });

  it('Analyse : un panneau de commande pour le projet actif, la dernière analyse et les analyses existantes', async()=>{
    await open('#/');
    expect(host.querySelector('.page-head .primary')).toBeNull();
    const menu=Array.from(host.querySelectorAll('.top-menu button')).find(item=>item.textContent==='Analyse');
    await act(async()=>{menu?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    const panel=host.querySelector('.menu-panel');
    expect(panel?.textContent).toContain('Boutique');
    expect(panel?.querySelector('.command-main')?.textContent).toBe('Lancer l’analyse globale');
    expect(panel?.querySelector('a[href="#/analyses/new"]')?.textContent).toBe('Voir l’analyse');
    expect(Array.from(panel?.querySelectorAll('.command-links a')??[]).map(link=>link.getAttribute('href'))).toEqual(['#/analyses', '#/comparaisons']);
    await act(async()=>{panel?.querySelector('.command-main')?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    await flush();
    expect(host.querySelector('.menu-panel')).toBeNull();
    const calls=(vi.mocked(fetch).mock.calls as unknown as [URL, RequestInit?][]).filter(([, init])=>init?.method==='POST').map(([url])=>url.toString());
    expect(calls.some(url=>url.endsWith('/projects/p/analyses'))).toBe(true);
  });

  it('sans analyse : la première se lance depuis l’accueil comme depuis le menu', async()=>{
    empty=true;
    await open('#/');
    expect(host.querySelector('.welcome .primary')?.textContent).toBe('Lancer la première analyse');
    const menu=Array.from(host.querySelectorAll('.top-menu button')).find(item=>item.textContent==='Analyse');
    await act(async()=>{menu?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    expect(host.querySelector('.menu-panel')?.textContent).toContain('Aucune analyse pour ce projet.');
    expect(host.querySelector('.menu-panel .command-main')?.textContent).toBe('Lancer la première analyse');
  });

  it('une analyse interrompue reste à son projet : en changer efface son échec', async()=>{
    streamed=true;
    await open('#/analyses');
    await act(async()=>{host.querySelector('.launch-button')?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    await flush();
    expect(host.querySelector('.launch.is-failed')?.textContent).toContain('Dépôt illisible.');
    await act(async()=>{host.querySelector('.switcher-current')?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    const other=Array.from(host.querySelectorAll('.switcher [role="option"]')).find(item=>item.textContent?.includes('Atelier'));
    await act(async()=>{other?.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
    await flush();
    await visit('#/analyses');
    expect(host.querySelector('.switcher-current strong')?.textContent).toBe('Atelier');
    expect(host.querySelector('.launch.is-failed')).toBeNull();
    expect(host.textContent).not.toContain('Dépôt illisible.');
  });

  it('un dépôt que la sécurité n’a pas lu : ni compte au menu, ni « aucune route » (TAXO-COV-01)', async()=>{
    unread=true;
    await open('#/');
    expect(host.querySelector('.results-nav a[href="#/securite"] .results-count')).toBeNull();
    expect(host.querySelector('.results-nav a[href="#/non-interpretees"] .results-count')).toBeNull();
    expect(host.querySelector('[aria-label="API"] .card-value')?.textContent).toBe('Non analysé');
    expect(host.querySelector('.overview-limits strong')?.textContent).toBe('Non analysé : Python');
    await visit('#/routes');
    expect(text()).toContain('Non analysé : Python — une route écrite dans ce langage n’est ni trouvée ni exclue.');
    await visit('#/limites');
    expect(host.querySelector('.unread-languages')?.textContent).toContain('Endpoints Spring');
  });
});

