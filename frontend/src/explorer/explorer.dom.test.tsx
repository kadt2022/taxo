// @vitest-environment happy-dom
// L'explorateur dans le portail (TAXO-01J § 9) : un faux serveur du protocole rend des Tuiles écrites à la main, en forme
// compacte, comme `neighborhood/2`. La vue de référence est la liste.
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it} from 'vitest';
import {useRoute} from '../nav';
import {ExplorerPage} from './Explorer';
import type {Boundary, CompactTile, Element as Item, Tile} from './protocol';
import {depthCut, edgesCut, element, tile} from './__fixtures__/tiles';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

const ROUTE='endpoint:GET /orders', HANDLER='symbol:java:A#get()', PATTERN='route-pattern:/**', RULE='policy-rule:authenticated()';
const CALLED='symbol:java:B#run()', ABSENT='endpoint:GET /nowhere', REPOSITORY='repository:p';
const gap:Boundary={nature:'KNOWLEDGE', scope:'NODE', node:HANDLER, subject:'file:A.java', reason:'NOT_INTERPRETED',
  producer:'taxo.spring-api', count:{kind:'UNKNOWN'}};
const noAnalyzer:Boundary={nature:'CONTEXT', node:ROUTE, relation:'PROTECTED_BY', reason:'NO_ANALYZER', count:{kind:'UNKNOWN'}};

const TILES:Record<string, Tile>={
  [ROUTE]:tile({root:ROUTE, stop:'DEPTH', items:[
    element(ROUTE, HANDLER, {relation:'HANDLED_BY', evidence:[{path:'A.java', line_start:9, method:'java.spring.request-mapping'}]}),
    element(ROUTE, PATTERN, {relation:'MATCHED_BY', evidence:null, count:2}),
    element(REPOSITORY, ROUTE, {relation:'CONTAINS', direction:'INCOMING'}),
    element(ROUTE, undefined, {relation:'PERMITS_ALL'}), element(ROUTE, 'authenticated()', {relation:'AUTHORIZED_BY'})],
  nodes:[[ROUTE, 0, false], [HANDLER, 1, false], [PATTERN, 1, false], [REPOSITORY, 1, false]],
  frontier:[depthCut(HANDLER), edgesCut(PATTERN, 'reprise-P'), depthCut(REPOSITORY), gap, noAnalyzer]}),
  [HANDLER]:tile({root:HANDLER, items:[element(HANDLER, CALLED, {relation:'CALLS'})], nodes:[[HANDLER, 0, true], [CALLED, 1, false]],
    frontier:[depthCut(CALLED)]}),
  [PATTERN]:tile({root:PATTERN, items:[element(PATTERN, RULE, {relation:'AUTHORIZED_BY'})], nodes:[[PATTERN, 0, true], [RULE, 1, false]],
    frontier:[depthCut(RULE)]}),
  [ABSENT]:tile({root:ABSENT, known:false, stop:'ROOT_UNKNOWN'}),
};
const REFERENCES=[ROUTE, 'endpoint:GET /admin', 'endpoint:GET /orders/{id}'];

/** La forme compacte d'une Tuile écrite à la main : l'encodage du contrat, écrit ici, sans le code testé. */
function compact(full:Tile):CompactTile{
  const steps=[...new Map(full.items.map(item=>[`${item.via.relation}|${item.via.direction}`,
    {relation:item.via.relation, direction:item.via.direction}])).values()];
  const commons:string[]=[];
  const common=(fact:Item['fact'])=>{
    const {subject:_s, relation:_r, object:_o, qualifiers:_q, derivation:_d, ...shared}=fact;
    const key=JSON.stringify(shared);
    if(!commons.includes(key))commons.push(key);
    return commons.indexOf(key);
  };
  const items=full.items.map(({fact, via, ...item})=>({...item, common:common(fact),
    fact:{subject:fact.subject, relation:fact.relation, object:fact.object},
    via:{from:full.nodes.indexOf(via.from), step:steps.findIndex(step=>step.relation===via.relation&&step.direction===via.direction)}}));
  return {...full, parameters:{...full.parameters, steps}, node_details:full.node_details.map(({reference:_, ...node})=>node),
    items, shared:{common:commons.map(key=>JSON.parse(key))}};
}

type Call={operation:string; arguments:Record<string, unknown>};
let calls:Call[], paths:string[], held:Map<string, ()=>void>, holding:Set<string>;

async function answer(path:string, init?:RequestInit):Promise<unknown>{
  paths.push(path);
  if(path.endsWith('/comparisons/analyses'))return [{id:'scan-1', created_at:'2026-10-03T10:00:00Z', snapshot:{commit:'a'.repeat(40)}}];
  const {requests:[call]}=JSON.parse(init!.body as string) as {requests:Call[]};
  calls.push(call);
  const reply=(value:object)=>({responses:[{outcome:'OK', ...value}]});
  switch(call.operation){
  case 'describe':return reply({items:[
    {kind:'analyzer', analyzer:'taxo.spring-api', status:'SUCCESS', relations:['HANDLED_BY', 'MATCHED_BY']},
    {kind:'analyzer', analyzer:'taxo.data', status:'UNSUPPORTED', relations:['READS']},
    {kind:'relation', relation:'HANDLED_BY', count:2, subject_types:['endpoint'], object_types:['symbol']},
    {kind:'relation', relation:'MATCHED_BY', count:1, subject_types:['endpoint'], object_types:['route-pattern']}]});
  case 'find_references':{
    const prefix=String(call.arguments.prefix);
    const found=REFERENCES.filter(item=>item.slice(item.indexOf(':')+1).toLowerCase().startsWith(prefix.toLowerCase()));
    const start=call.arguments.after?2:0;
    return reply({items:found.slice(start, start+2).map(reference=>({reference, type:'endpoint'})), next:start===0&&found.length>2?'page-2':null});
  }
  case 'get_evidence':return reply({evidence:[{ref:'E1', fact:'F1', location:{path:'security/Shop.java', line_start:12}},
    {ref:'E2', fact:'F1', location:{path:'admin/Admin.java', line_start:4}}]});
  case 'get_neighborhood':{
    const response=reply(compact(TILES[String(call.arguments.root)]));
    const at=String(call.arguments.root);
    if(holding.has(at))return new Promise(resolve=>held.set(at, ()=>resolve(response)));
    return response;
  }
  default:throw new Error(`inattendu : ${call.operation}`);
  }
}

function Harness(){
  const route=useRoute();
  return <ExplorerPage base="/projects/p" request={answer as never} scanId="scan-1" route={route} revision="r"
    project={{id:'p', name:'Boutique'}}/>;
}

let host:HTMLElement, root:Root;
beforeEach(()=>{calls=[];paths=[];held=new Map();holding=new Set();host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();globalThis.location.hash='';});

const wait=(ms=0)=>act(async()=>{await new Promise(resolve=>setTimeout(resolve, ms));});
const click=async(node:Element|null|undefined)=>{
  expect(node, 'élément introuvable').toBeTruthy();
  await act(()=>{node!.dispatchEvent(new MouseEvent('click', {bubbles:true}));});
  await wait();
};
const named=(label:string|RegExp)=>Array.from(host.querySelectorAll('button')).find(item=>{
  const name=item.getAttribute('aria-label')??item.textContent??'';
  return typeof label==='string'?name===label:label.test(name);
});
async function type(input:HTMLInputElement, value:string){
  await act(async()=>{
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value);
    input.dispatchEvent(new Event('input', {bubbles:true}));
  });
}
async function open(hash:string){
  globalThis.location.hash=hash;
  await act(async()=>{root.render(<Harness/>);});
  await wait();await wait();
}
async function go(hash:string){
  await act(async()=>{globalThis.location.hash=hash;globalThis.dispatchEvent(new HashChangeEvent('hashchange'));});
  await wait();await wait();
}
const tiles=()=>calls.filter(call=>call.operation==='get_neighborhood').map(call=>call.arguments);
const list=async()=>{await click(named('Liste'));return host.querySelector('.explorer-list') as HTMLElement;};

describe('l’explorateur', ()=>{
  it('choisit une ancre par recherche : une seule demande, la dernière saisie, puis la suite sur demande', async()=>{
    await open('#/explorer');
    const input=host.querySelector('input') as HTMLInputElement;
    await type(input, 'G');await type(input, 'GE');await type(input, 'GET /');
    await wait(300);
    expect(calls.filter(call=>call.operation==='find_references').map(call=>call.arguments.prefix)).toEqual(['GET /']);
    await click(named('Références suivantes'));
    expect(host.querySelectorAll('.explorer-suggestions li')).toHaveLength(3);
    await click(named(/route GET \/orders$/));
    expect(decodeURIComponent(globalThis.location.hash)).toContain(`racine=${ROUTE}`.replaceAll(' ', '+'));
    expect(tiles()[0]).toMatchObject({engine:'neighborhood/2', root:ROUTE, follow:['HANDLED_BY', 'MATCHED_BY'], direction:'BOTH',
      depth:2, evidence:'SUMMARY', form:'COMPACT', max_nodes:60});
  });

  it('dit une ancre inconnue sans graphe vide trompeur', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ABSENT)}`);
    expect(host.textContent).toContain('n’apparaît dans aucun fait de cette analyse');
    expect(host.querySelector('.explorer-list, .explorer-layers')).toBeNull();
  });

  it('montre chaque nœud par niveau, le dépôt par le nom du projet, et les liens dans leur sens réel', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    const shown=await list();
    expect(Array.from(shown.querySelectorAll('section')).map(section=>section.getAttribute('aria-label'))).toEqual(['Niveau 0', 'Niveau 1']);
    expect(shown.textContent).toContain('dépôt Boutique');
    expect(named(/^route GET \/orders est traité par symbole java:A#get\(\), 1 occurrence$/)).toBeTruthy();
    expect(named(/^dépôt Boutique contient route GET \/orders, 1 occurrence$/), 'un fait lu en entrant garde son sens').toBeTruthy();
    expect(named(/^route GET \/orders est ouvert à tous, 1 occurrence$/), 'un fait sans objet').toBeTruthy();
    expect(named(/^route GET \/orders est autorisé par authenticated\(\), 1 occurrence$/), 'une valeur littérale').toBeTruthy();
    await click(named('Couches'));
    expect(named('Aucun objet : ce fait n’en a pas')).toBeTruthy();
    expect(named('Valeur authenticated(), pas un nœud')).toBeTruthy();
  });

  it('développe un nœud et voit la suite d’une adjacence coupée, sans recharger le reste', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await list();
    await click(named('Développer symbole java:A#get()'));
    expect(tiles()[1]).toMatchObject({root:HANDLER, depth:1});
    expect(tiles()[1]).not.toHaveProperty('continuation');
    await click(named('Voir la suite de routes /**'));
    expect(tiles()[2]).toMatchObject({root:PATTERN, depth:1, continuation:'reprise-P'});
    const shown=host.querySelector('.explorer-list') as HTMLElement;
    expect(Array.from(shown.querySelectorAll('section')).map(section=>section.getAttribute('aria-label'))).toEqual(['Niveau 0', 'Niveau 1', 'Niveau 2']);
    expect(shown.textContent).toContain('symbole java:B#run()');
    expect(shown.textContent).toContain('règle authenticated()');
    expect(named('Développer symbole java:A#get()')).toBeUndefined();
  });

  it('recentre, puis revient en arrière et en avant', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await list();
    await click(named('Recentrer sur symbole java:A#get()'));
    expect(decodeURIComponent(globalThis.location.hash)).toContain(`racine=${HANDLER}`);
    await go(globalThis.location.hash);
    expect(tiles().at(-1)).toMatchObject({root:HANDLER});
    expect((named('← Précédent') as HTMLButtonElement).disabled).toBe(false);
    await go(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    expect((named('Suivant →') as HTMLButtonElement).disabled).toBe(false);
  });

  it('ouvre chaque occurrence d’un lien : sa preuve résumée, ou chargée par sa poignée', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await list();
    await click(named(/est traité par symbole/));
    const panel=()=>host.querySelector('[aria-label="Détail du lien"]') as HTMLElement;
    expect(panel().textContent).toContain('A.java:9 (java.spring.request-mapping)');
    expect(panel().textContent).toContain('Observé dans le code');
    await click(named(/correspond à routes/));
    await click(named('Charger les preuves (2)'));
    expect(calls.at(-1)).toEqual({operation:'get_evidence', max_bytes:32000, arguments:{occurrence:`o:${ROUTE}|MATCHED_BY|${PATTERN}|fixture`}});
    expect(panel().textContent).toContain('security/Shop.java:12');
    expect(panel().textContent).toContain('admin/Admin.java:4');
  });

  it('dit à part ce que Taxo ne sait pas et ce qu’il ne peut pas savoir ; un développement ne l’efface pas', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await list();
    const boundaries=()=>host.querySelector('[aria-label="Ce que la vue ne montre pas"]') as HTMLElement;
    expect(boundaries().textContent).toContain('Zone non lue par Endpoints Spring : A.java (Non analysé par Taxo).');
    expect(boundaries().textContent).toContain('Aucun analyseur exécuté ne produit « est protégé par »');
    expect(host.querySelector('.explorer-list')!.textContent).toContain('zone non lue');
    await click(named('Développer symbole java:A#get()'));
    expect(boundaries().textContent).toContain('Zone non lue par Endpoints Spring');
    expect(boundaries().textContent).not.toMatch(/%|complet/i);
  });

  it('ignore une réponse arrivée trop tard, même pendant la demande suivante', async()=>{
    holding=new Set([ROUTE, ABSENT]);
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await go(`#/explorer?racine=${encodeURIComponent(ABSENT)}`);
    await act(async()=>{held.get(ROUTE)!();});
    await wait();
    expect(host.querySelector('.explorer-list, .explorer-layers'), 'la Tuile de l’ancre précédente n’est jamais montrée').toBeNull();
    expect(host.textContent).toContain('Ouverture de la vue…');
    await act(async()=>{held.get(ABSENT)!();});
    await wait();
    expect(host.textContent).toContain('n’apparaît dans aucun fait');
  });

  it('montre désactivée, avec sa raison, une relation qu’aucun analyseur exécuté ne produit', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    const settings=host.querySelector('.explorer-settings') as HTMLElement;
    const reads=Array.from(settings.querySelectorAll('label')).find(item=>item.textContent?.includes('READS'))!;
    expect(reads.querySelector('input')!.disabled).toBe(true);
    expect(reads.textContent).toContain('Aucun analyseur exécuté dans cette analyse ne la produit');
  });

  it('n’appelle jamais Minia : seulement le protocole et la liste des analyses', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await list();
    await click(named(/correspond à routes/));
    await click(named('Charger les preuves (2)'));
    expect(paths.every(path=>path==='/projects/p/taxo-query'||path==='/projects/p/comparisons/analyses')).toBe(true);
    expect(new Set(calls.map(call=>call.operation))).toEqual(new Set(['describe', 'get_neighborhood', 'get_evidence']));
  });
});
