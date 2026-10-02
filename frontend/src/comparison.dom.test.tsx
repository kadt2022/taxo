// @vitest-environment happy-dom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ComparisonView, type ChangesPage, type ComparisonSummary} from './comparison';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

let host:HTMLElement, root:Root;
beforeEach(()=>{host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();});

const flush=()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve, 0));});
const click=(node:Element|null|undefined)=>act(()=>{node?.dispatchEvent(new MouseEvent('click',{bubbles:true}));});
const button=(text:string)=>Array.from(host.querySelectorAll('button')).find(item=>item.textContent?.includes(text));

const fact=(object:string, line=1)=>({kind:'ASSERTION', subject:'endpoint:GET /orders', relation:'PROTECTED_BY', object,
  status:'OBSERVED', validity:'VALID', evidence:[{path:'Security.java', line_start:line, line_end:line}]});
const SUMMARY:ComparisonSummary={
  before:{id:'a', created_at:'2026-09-30T10:00:00Z', snapshot:{commit:'1a2b3c4d5e6f', mode:'COMMIT'}},
  after:{id:'b', created_at:'2026-10-01T10:00:00Z', snapshot:{commit:'3c4d5e6f7a8b', mode:'COMMIT'}},
  evaluators:[
    {evaluator_id:'taxo.spring-security', comparable:true, versions:{before:['0.3.0'], after:['0.4.0']},
     counts:{ADDED:0, REMOVED:0, MODIFIED:3, EVIDENCE_CHANGED:1, STATUS_CHANGED:0, OCCURRENCE_COUNT_CHANGED:0, OCCURRENCES_CHANGED:0, UNCHANGED:9}},
    {evaluator_id:'taxo.structure', comparable:false, reason:'CATALOG_CHANGED', versions:{before:['1'], after:['2']},
     message:'Catalogue différent. Cause possible : évolution du producteur, pas du logiciel.'}],
  totals:{ADDED:0, REMOVED:0, MODIFIED:3, EVIDENCE_CHANGED:1, STATUS_CHANGED:0, OCCURRENCE_COUNT_CHANGED:0, OCCURRENCES_CHANGED:0, UNCHANGED:9},
  unknown:{before:5, after:3}};

function api(pages:Record<string, ChangesPage|Promise<ChangesPage>>){
  const calls:string[]=[];
  const request=vi.fn((path:string)=>{
    calls.push(path);
    if(!path.includes('/changes'))return Promise.resolve(SUMMARY);
    const query=new URLSearchParams(path.split('?')[1]);
    const key=`${query.get('category')}:${query.get('cursor')??''}`;
    return Promise.resolve(pages[key]??{items:[], next:null});
  });
  return {request:request as unknown as <T>(path:string)=>Promise<T>, calls};
}

async function open(request:<T>(path:string)=>Promise<T>, onClose=vi.fn(), onSwap=vi.fn()){
  await act(async()=>{root.render(<ComparisonView base="/projects/p" request={request} before="a" after="b" onClose={onClose} onSwap={onSwap}
    project={{id:'p', name:'Boutique'}}/>);});
  await flush();
}

describe('écran de comparaison', ()=>{
  it('montre les comptes, les non comparables, les versions et les zones inconnues, sans pourcentage', async()=>{
    const {request, calls}=api({});
    await open(request);
    expect(calls[0]).toBe('/projects/p/comparisons?before=a&after=b');
    const text=host.textContent??'';
    expect(text).toContain('commit 1a2b3c4d5e');
    expect(text).toContain('9 faits inchangés');
    expect(text).toContain('Catalogue différent. Cause possible : évolution du producteur');
    expect(text).toContain('0.3.0 → 0.4.0 · provenance, pas un changement du logiciel');
    expect(text).toContain('A : 5 · B : 3');
    expect(text).not.toContain('%');
    expect((button('Ajoutés') as HTMLButtonElement).disabled).toBe(true);
  });

  it('ouvre une catégorie, puis la page suivante avec son curseur', async()=>{
    const {request, calls}=api({
      'MODIFIED:':{items:[{before:[fact('policy-rule:authenticated()')], after:[fact('policy-rule:hasRole("USER")')]}], next:'k1'},
      'MODIFIED:k1':{items:[{before:[fact('policy-rule:a()')], after:[fact('policy-rule:b()')]}], next:null}});
    await open(request);
    await click(button('Modifiés'));
    await flush();
    expect(host.textContent).toContain('La route GET /orders exige que l’utilisateur soit authentifié.');
    expect(host.textContent).toContain('La route GET /orders exige le rôle USER.');
    await click(button('Afficher la suite'));
    await flush();
    expect(calls.at(-1)).toContain('cursor=k1');
    expect(host.querySelectorAll('.change-list li')).toHaveLength(2);
    expect(button('Afficher la suite')).toBeUndefined();
  });

  it('ignore une page arrivée après un changement de catégorie', async()=>{
    let late:(page:ChangesPage)=>void=()=>undefined;
    const slow=new Promise<ChangesPage>(resolve=>{late=resolve;});
    const {request}=api({'MODIFIED:':slow, 'EVIDENCE_CHANGED:':{items:[{before:[fact('policy-rule:x()', 3)], after:[fact('policy-rule:x()', 9)]}], next:null}});
    await open(request);
    await click(button('Modifiés'));
    await click(button('Preuves déplacées'));
    await flush();
    await act(async()=>{late({items:[{before:[fact('policy-rule:old()')], after:[fact('policy-rule:new()')]}], next:'late'});});
    await flush();
    expect(host.textContent).toContain('Security.java:3');
    expect(host.textContent).not.toContain('old()');
    expect(button('Afficher la suite')).toBeUndefined();
  });

  it('dit l’erreur de l’API et rend la main', async()=>{
    const failing=vi.fn(()=>Promise.reject(new Error('Analyse introuvable pour ce projet, ou interrompue.')));
    const onClose=vi.fn(), onSwap=vi.fn();
    await open(failing as unknown as <T>(path:string)=>Promise<T>, onClose, onSwap);
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('Analyse introuvable');
    await click(button('Inverser le sens'));
    await click(button('Vue d’ensemble'));
    expect(onSwap).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('dit l’erreur d’une liste sans effacer les comptes', async()=>{
    const request=vi.fn((path:string)=>path.includes('/changes')?Promise.reject(new Error('Catégorie inconnue')):Promise.resolve(SUMMARY));
    await open(request as unknown as <T>(path:string)=>Promise<T>);
    await click(button('Modifiés'));
    await flush();
    expect(host.querySelector('.change-group [role="alert"]')?.textContent).toBe('Catégorie inconnue');
    expect(host.textContent).toContain('Modifiés');
  });
});

describe('même commit des deux côtés', ()=>{
  it('le dit sur l’écran de résultat, et propose de changer les analyses', async()=>{
    const same={...SUMMARY, after:{...SUMMARY.after, snapshot:{commit:'1a2b3c4d5e6f', mode:'COMMIT'}}};
    const request=vi.fn(()=>Promise.resolve(same)) as unknown as <T>(path:string)=>Promise<T>;
    const onChange=vi.fn();
    await act(async()=>{root.render(<ComparisonView base="/projects/p" request={request} before="a" after="b" onClose={vi.fn()}
      onSwap={vi.fn()} onChange={onChange}/>);});
    await flush();
    expect(host.textContent).toContain('Deux analyses du même commit');
    await click(button('Changer les analyses'));
    expect(onChange).toHaveBeenCalledOnce();
  });
});
