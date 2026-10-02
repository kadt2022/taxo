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

let failing:string[]=[], empty=false;
function answer(path:string){
  if(failing.some(part=>path.includes(part)))return {failed:true};
  if(empty&&/\/projects\/[pq]\/scans$/.test(path))return [];
  if(path.endsWith('/minia/status'))return {providers:[]};
  if(path.endsWith('/api/projects'))return [{id:'p', name:'Boutique', path:'/boutique'}, {id:'q', name:'Atelier', path:'/atelier'}];
  if(/\/projects\/[pq]\/scans$/.test(path))return SCANS;
  if(path.includes('/routes'))return ROUTES;
  if(path.endsWith('/comparisons/analyses'))return CHOICES;
  if(path.includes('/facts?evaluator=taxo.structure'))return STRUCTURE;
  if(path.includes('/comparisons?'))return SUMMARY;
  throw new Error(`inattendu : ${path}`);
}

let host:HTMLElement, root:Root;
beforeEach(()=>{
  failing=[];empty=false;
  vi.stubGlobal('fetch', vi.fn(async(url:URL)=>{const value=answer(url.toString());
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
    expect(host.querySelector('.picker-current strong')?.textContent).toBe('Atelier');
    await visit('#/routes');
    expect(window.location.hash).toBe('#/routes?projet=q');
  });

  it('ouvre le premier projet quand l’adresse n’en nomme aucun connu, et l’y inscrit', async()=>{
    await open('#/limites?projet=disparu');
    expect(host.querySelector('.picker-current strong')?.textContent).toBe('Boutique');
    expect(window.location.hash).toBe('#/limites?projet=p');
  });
});
