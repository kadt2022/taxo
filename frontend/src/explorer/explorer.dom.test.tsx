// @vitest-environment happy-dom
// L'explorateur dans le portail (TAXO-01J § 9) : un faux serveur du protocole rend des Tuiles écrites à la main, en forme
// compacte, comme `neighborhood/2`. La vue de référence est la liste.
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useRoute} from '../nav';
import {ExplorerPage} from './Explorer';
import {resetGraphTheme} from './graphTheme';
import type {Boundary, CompactTile, Element as Item, Tile} from './protocol';
import {depthCut, edgesCut, element, tile} from './__fixtures__/tiles';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

const ROUTE='endpoint:GET /orders', HANDLER='symbol:java:A#get()', PATTERN='route-pattern:/**', RULE='policy-rule:authenticated()';
const CALLED='symbol:java:B#run()', ABSENT='endpoint:GET /nowhere', REPOSITORY='repository:p';
const gap:Boundary={nature:'KNOWLEDGE', scope:'NODE', node:HANDLER, subject:'file:A.java', reason:'NOT_INTERPRETED',
  producer:'taxo.spring-api', count:{kind:'UNKNOWN'}};
const classified:Boundary={nature:'KNOWLEDGE', scope:'NODE', node:HANDLER, subject:HANDLER, reason:'NOT_INTERPRETED',
  producer:'taxo.java-calls', count:{kind:'UNKNOWN'}, causes:['OVERLOAD_AMBIGUOUS', 'TARGET_TYPE_OUTSIDE_SNAPSHOT'],
  categories:[{category:'UNKNOWN', count:{kind:'AT_LEAST', value:1}}, {category:'AMBIGUOUS', count:{kind:'AT_LEAST', value:1}},
    {category:'UNSUPPORTED', count:{kind:'AT_LEAST', value:0}}, {category:'OUT_OF_SCOPE', count:{kind:'AT_LEAST', value:0}}]};
const noAnalyzer:Boundary={nature:'CONTEXT', node:ROUTE, relation:'PROTECTED_BY', reason:'NO_ANALYZER', count:{kind:'UNKNOWN'}};

const TILES:Record<string, Tile>={
  [ROUTE]:tile({root:ROUTE, stop:'DEPTH', items:[
    element(ROUTE, HANDLER, {relation:'HANDLED_BY', evidence:[{path:'A.java', line_start:9, method:'java.spring.request-mapping'}]}),
    element(ROUTE, PATTERN, {relation:'MATCHED_BY', evidence:null, count:2}),
    element(REPOSITORY, ROUTE, {relation:'CONTAINS', direction:'INCOMING'}),
    element(ROUTE, undefined, {relation:'PERMITS_ALL'}), element(ROUTE, 'authenticated()', {relation:'AUTHORIZED_BY'})],
  nodes:[[ROUTE, 0, false], [HANDLER, 1, false], [PATTERN, 1, false], [REPOSITORY, 1, false]],
  frontier:[depthCut(HANDLER), edgesCut(PATTERN, 'reprise-P'), depthCut(REPOSITORY), gap, classified, noAnalyzer]}),
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
let calls:Call[], consents:unknown[], paths:string[], held:Map<string, ()=>void>, holding:Set<string>, source:Record<string, object>;

const CLASS_LINES=['public class A {', '  private int x;', '  public String get() {', '    return B.run();', '  }', '}'];
const piece=(reference:string, from:number, lines:string[])=>({kind:'source', reference, path:'src/A.java', line_start:from,
  line_end:from+lines.length-1, truncated:false, declared:{line_start:from, line_end:from+lines.length-1}, text:`${lines.join('\n')}\n`});

async function answer(path:string, init?:RequestInit):Promise<unknown>{
  paths.push(path);
  if(path.endsWith('/comparisons/analyses'))return [{id:'scan-1', created_at:'2026-10-03T10:00:00Z', snapshot:{commit:'a'.repeat(40)}}];
  const {requests:[call], consent}=JSON.parse(init!.body as string) as {requests:Call[]; consent?:unknown};
  calls.push(call);
  consents.push(consent);
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
  case 'get_source':{
    const found=source[String(call.arguments.reference)];
    const error=found&&'error' in found?found.error:{code:'NOT_AVAILABLE', message:'Aucune déclaration écrite de ce symbole dans cette analyse.'};
    return found&&!('error' in found)?reply(found):{responses:[{outcome:'ERROR', error}]};
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
beforeEach(()=>{resetGraphTheme();calls=[];consents=[];source={};paths=[];held=new Map();holding=new Set();host=document.createElement('div');document.body.append(host);root=createRoot(host);});
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

  it('s’ouvre sur la vue Chaîne : boîtes teintées par type, flèches nommées, frontière et coupure dans le dessin', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    expect(named('Chaîne')?.getAttribute('aria-pressed')).toBe('true');
    const drawn=host.querySelector('.chain') as HTMLElement;
    const anchor=drawn.querySelector('.chain-node.anchor') as HTMLElement;
    expect(anchor.classList.contains('tone-route')).toBe(true);
    expect(anchor.textContent).toBe('«route» · ancreGET /orders');
    const method=drawn.querySelector('.chain-node.tone-symbol') as HTMLElement;
    expect(method.querySelector('.chain-name')?.textContent, 'la classe, puis la méthode sous un trait').toBe('A');
    expect(method.querySelector('.chain-member')?.textContent).toBe('get()');
    expect(drawn.querySelector('[role=note]')?.textContent).toContain('Frontière · Taxo ne sait pas');
    expect(drawn.querySelectorAll('.chain-cut').length).toBeGreaterThan(0);
    expect(drawn.querySelectorAll('.chain-leaf')).toHaveLength(2);
    expect(Array.from(drawn.querySelectorAll('.chain-legend li')).map(item=>item.textContent)).toContain('route');
    await click(named(/^route GET \/orders est traité par symbole java:A#get\(\), 1 occurrence$/));
    expect(host.querySelector('[aria-label="Détail du lien"]')).toBeTruthy();
    await click(named(/^symbole java:A#get\(\)/));
    expect(host.querySelector('[aria-label="Nœud choisi"]')?.textContent).toContain('symbol:java:A#get()');
    await click(named('Développer symbole java:A#get(), depuis la vue Chaîne'));
    expect(tiles()[1], 'la pastille de coupure reprend le parcours').toMatchObject({root:HANDLER, depth:1});
    await click(named('Voir la suite de routes /**, depuis la vue Chaîne'));
    expect(tiles()[2]).toMatchObject({root:PATTERN, continuation:'reprise-P'});
  });

  it('a une vue Appels distincte : seulement l’axe d’exécution, ses coupures, et ce qui n’est pas analysé', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    expect(Array.from(host.querySelectorAll('.explorer-tabs button')).map(item=>item.textContent)).toEqual(['Appels', 'Chaîne', 'Couches', 'Liste']);
    expect(named('Chaîne')?.getAttribute('aria-pressed'), 'Chaîne reste la vue de voisinage par défaut').toBe('true');
    await click(named('Appels'));
    const shown=host.querySelector('.calls') as HTMLElement;
    expect(shown.querySelector('.calls-question')?.textContent).toContain('route GET /orders');
    expect(Array.from(shown.querySelectorAll('.chain-node')).map(item=>item.getAttribute('title'))).toEqual([ROUTE, HANDLER]);
    expect(Array.from(shown.querySelectorAll('.chain-label')).map(item=>item.textContent)).toEqual(['est traité parO']);
    expect(shown.textContent, 'aucun type déduit par l’interface').not.toMatch(/méthode/);
    expect(named('Exporter en image (PNG)'), 'chaque vue dessinée s’exporte en image').toBeTruthy();
    expect(shown.querySelector('[aria-label="Où s’arrête la vue Appels"]')?.textContent).toContain('« appelle » : non analysé');
    await click(named('Développer symbole java:A#get(), depuis la vue Appels'));
    expect(tiles()[1]).toMatchObject({root:HANDLER});
    const after=host.querySelector('.calls') as HTMLElement;
    expect(Array.from(after.querySelectorAll('.chain-label')).map(item=>item.textContent)).toEqual(['est traité parO', 'appelleO']);
    expect(after.querySelectorAll('.chain-node')).toHaveLength(3);
  });

  it('exporte le diagramme en PNG, ou dit pourquoi le navigateur n’a pas pu', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    vi.spyOn(HTMLImageElement.prototype, 'decode').mockResolvedValue(undefined);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(()=>undefined);
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(callback=>callback(new Blob(['png'])));
    const names:string[]=[];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this:HTMLAnchorElement){names.push(this.download);});
    const context=vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({scale:()=>undefined, drawImage:()=>undefined} as never);
    await click(named('Exporter en image (PNG)'));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve, 0));});
    expect(names).toEqual(['taxo-chaine-route-get-orders.png']);
    context.mockReturnValue(null);
    await click(named('Exporter en image (PNG)'));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve, 0));});
    expect(host.querySelector('.chain-tools [role=alert]')?.textContent).toBe('L’image n’a pas pu être créée par ce navigateur.');
    vi.restoreAllMocks();
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

  it('montre les sites d’une zone non lue par catégorie, sans les confondre avec un zéro exact', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await list();
    const pills=Array.from(host.querySelectorAll('.explorer-categories .category-pill'), pill=>pill.textContent);
    expect(pills).toEqual(['cible inconnue · au moins 1', 'plusieurs cibles possibles · au moins 1',
      'forme non prise en charge · au moins 0', 'hors du périmètre analysé · au moins 0']);
    expect(host.querySelector('.category-out_of_scope')).not.toBeNull();
    expect(host.querySelector('[aria-label="Ce que la vue ne montre pas"]')!.textContent).toContain('plusieurs déclarations possibles');
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

  it('range l’analyse, le point de départ, le type et les réglages en cartes sur une même rangée', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    const row=host.querySelector('.explorer-search-fields') as HTMLElement;
    const cells=Array.from(row.children);
    expect(cells.map(item=>item.className.includes('explorer-card')), 'quatre cartes').toEqual([true, true, true, true]);
    expect(cells[0].textContent, 'l’analyse ouvre la rangée').toMatch(/^Analyse/);
    expect(cells[3].matches('details.explorer-settings-box'), 'les réglages ferment la rangée').toBe(true);
    expect(row.querySelectorAll(':scope > label')).toHaveLength(3);
    expect(row.querySelectorAll('.explorer-input .icon').length, 'une icône par champ').toBe(3);
    expect(host.querySelector('.explorer-head nav[aria-label="Parcours des ancres"]')?.querySelectorAll('button')).toHaveLength(2);
  });

  it('a des onglets à icônes, dont le texte reste Appels, Chaîne, Couches et Liste', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    const tabs=Array.from(host.querySelectorAll('.explorer-tabs button'));
    expect(tabs.map(item=>item.textContent)).toEqual(['Appels', 'Chaîne', 'Couches', 'Liste']);
    expect(tabs.every(item=>item.querySelector('svg.icon'))).toBe(true);
    expect(host.querySelector('.explorer-bar .explorer-stop')?.textContent, 'les compteurs partagent la ligne des onglets').toMatch(/nœuds?/);
  });

  it('replie le panneau latéral en languette, sans rien retirer, et le rouvre quand on choisit un nœud', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    const panel=()=>host.querySelector('#explorer-side') as HTMLElement;
    const tab=()=>host.querySelector('.explorer-side-tab') as HTMLElement|null;
    expect(panel().hidden, 'replié au départ').toBe(true);
    expect(tab()?.getAttribute('aria-expanded')).toBe('false');
    expect(tab()?.getAttribute('aria-label'), 'la languette dit combien de points la vue ne montre pas').toMatch(/^Ce que la vue ne montre pas : \d+ points?$/);
    expect(host.querySelector('.explorer-body.closed'), 'le graphe prend la largeur').not.toBeNull();
    expect(panel().textContent, 'rien n’est retiré du panneau').toContain('Ce que la vue ne montre pas');
    await click(tab());
    expect(panel().hidden).toBe(false);
    expect(tab(), 'la languette cède la place au panneau').toBeNull();
    expect(host.querySelector('.explorer-body.closed')).toBeNull();
    await click(named('Masquer le panneau'));
    expect(panel().hidden).toBe(true);
    await click(host.querySelector('.chain-node'));
    expect(panel().hidden, 'choisir un nœud rouvre le panneau : le détail reste accessible').toBe(false);
    expect(host.querySelector('[aria-label="Nœud choisi"]')).not.toBeNull();
  });

  it('range export, zoom et légende dans une barre d’outils au sommet du cadre du graphe', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    const bar=host.querySelector('.chain-frame .chain-tools[role=toolbar]') as HTMLElement;
    expect(bar.getAttribute('aria-label')).toBe('Commandes du graphe');
    for(const name of ['Zoom avant', 'Zoom arrière', 'Ajuster à la largeur', 'Recentrer sur l’ancre', 'Agrandir la zone', 'Exporter en image (PNG)'])
      expect(bar.contains(named(name)??null), name).toBe(true);
    const legend=host.querySelector('.chain-tools fieldset.chain-legend') as HTMLElement;
    expect(legend.querySelector('legend')?.textContent, 'la légende a son nom').toBe('Légende');
    expect(Array.from(legend.querySelectorAll('li')).map(item=>item.textContent)).toContain('route');
    expect(legend.querySelector('details.chain-notation summary')?.textContent, 'la notation reste à un clic').toBe('Notation');
  });

  it('zoome le dessin sans jamais le recalculer : les dimensions et les nœuds restent ceux du moteur', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    const canvas=()=>host.querySelector('.explorer-canvas') as HTMLElement;
    const zoomed=()=>host.querySelector('.chain-zoomed') as HTMLElement;
    const drawn={width:canvas().style.width, height:canvas().style.height};
    const nodes=Array.from(host.querySelectorAll('.chain-node')).map(item=>item.getAttribute('title'));
    await click(named('Zoom avant'));
    expect(canvas().style.transform).toBe('scale(1.25)');
    expect(parseFloat(zoomed().style.width)).toBeCloseTo(parseFloat(drawn.width)*1.25, 1);
    await click(named('Zoom arrière'));await click(named('Zoom arrière'));
    expect(canvas().style.transform).toBe('scale(0.8)');
    expect({width:canvas().style.width, height:canvas().style.height}, 'le dessin calculé est inchangé').toEqual(drawn);
    expect(Array.from(host.querySelectorAll('.chain-node')).map(item=>item.getAttribute('title')), 'mêmes nœuds').toEqual(nodes);
    for(let step=0;step<8;step++)await click(named('Zoom arrière'));
    expect(named('Zoom arrière')!.hasAttribute('disabled'), 'borné vers le bas').toBe(true);
    for(let step=0;step<12;step++)await click(named('Zoom avant'));
    expect(named('Zoom avant')!.hasAttribute('disabled'), 'borné vers le haut').toBe(true);
    await click(named('Ajuster à la largeur'));
    expect(canvas().style.transform===''||/^scale\(/.test(canvas().style.transform), 'ajuster remet le zoom à l’échelle de la zone').toBe(true);
  });

  it('bascule le cadre du graphe entre sombre et clair, avec l’encadré de limites, et se souvient du choix', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await click(named('Appels'));
    const frame=()=>host.querySelector('.chain-frame') as HTMLElement;
    const limits=()=>host.querySelector('.calls-limits') as HTMLElement;
    expect(frame().dataset.theme, 'part du thème de l’appareil (clair ici)').toBe('light');
    expect(named('Passer le graphe en sombre')).toBeTruthy();
    await click(named('Passer le graphe en sombre'));
    expect(frame().dataset.theme).toBe('dark');
    expect(limits().dataset.theme, 'l’encadré de limites change avec le cadre').toBe('dark');
    expect(named('Passer le graphe en clair'), 'le bouton propose l’autre fond').toBeTruthy();
    expect(globalThis.localStorage.getItem('taxo.explorer.graph-theme')).toBe('dark');
    await click(named('Chaîne'));
    expect(frame().dataset.theme, 'le choix suit d’une vue à l’autre').toBe('dark');
    await click(named('Passer le graphe en clair'));
    expect(frame().dataset.theme).toBe('light');
    expect(globalThis.localStorage.getItem('taxo.explorer.graph-theme')).toBe('light');
  });

  it('lève la hauteur maximale à la demande, et la rétablit', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    const zone=()=>host.querySelector('.chain-scroll') as HTMLElement;
    expect(zone().classList.contains('grown')).toBe(false);
    await click(named('Agrandir la zone'));
    expect(zone().classList.contains('grown')).toBe(true);
    expect(named('Réduire la zone')?.getAttribute('aria-pressed')).toBe('true');
    await click(named('Réduire la zone'));
    expect(zone().classList.contains('grown')).toBe(false);
  });

  it('n’appelle jamais Minia : seulement le protocole et la liste des analyses', async()=>{
    await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
    await list();
    await click(named(/correspond à routes/));
    await click(named('Charger les preuves (2)'));
    expect(paths.every(path=>path==='/projects/p/taxo-query'||path==='/projects/p/comparisons/analyses')).toBe(true);
    expect(new Set(calls.map(call=>call.operation))).toEqual(new Set(['describe', 'get_neighborhood', 'get_evidence']));
  });

  describe('la tuile de code du nœud choisi', ()=>{
    const picked=async()=>{
      await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
      await click(named(/^symbole java:A#get\(\)/));
      await wait();
      return host.querySelector('[aria-label="Nœud choisi"]') as HTMLElement;
    };
    const serving=()=>{
      source={'symbol:java:A':{reference:'symbol:java:A', commit:'c', path:'src/A.java', items:[piece('symbol:java:A', 1, CLASS_LINES)]},
        [HANDLER]:{reference:HANDLER, commit:'c', path:'src/A.java', items:[piece(HANDLER, 3, CLASS_LINES.slice(2, 5))]}};
    };

    it('montre le code du type, la méthode choisie surlignée, avec le chemin et le type du nœud', async()=>{
      serving();
      const panel=await picked();
      const reads=calls.filter(call=>call.operation==='get_source');
      expect(reads.map(call=>String(call.arguments.reference)).sort((a, b)=>a.localeCompare(b)), 'la méthode et son type').toEqual(['symbol:java:A', HANDLER]);
      expect(consents.filter(Boolean), 'chaque lecture de code porte son consentement, et seule elle').toEqual([{source:true}, {source:true}]);
      expect(panel.querySelector('.type-pill')?.textContent).toBe('symbole');
      const tile=panel.querySelector('[aria-label="Tuile de code"]') as HTMLElement;
      expect(tile.querySelector('.code-head code')?.textContent).toBe('src/A.java');
      expect(Array.from(tile.querySelectorAll('.code-number')).map(item=>item.textContent)).toEqual(['1', '2', '3', '4', '5', '6']);
      expect(Array.from(tile.querySelectorAll('.code-line.selected .code-number')).map(item=>item.textContent)).toEqual(['3', '4', '5']);
      expect(tile.textContent).toContain('méthode sélectionnée');
      expect(tile.textContent).toContain('return B.run();');
    });

    it('garde les actions du nœud, copie la référence, et replie ce que la vue ne montre pas sous la tuile', async()=>{
      serving();
      const written:string[]=[];
      Object.defineProperty(globalThis.navigator, 'clipboard', {configurable:true, value:{writeText:async(text:string)=>{written.push(text);}}});
      const panel=await picked();
      expect(Array.from(panel.querySelectorAll('button')).map(item=>item.textContent)).toEqual(expect.arrayContaining(['Développer', 'Recentrer', 'Copier la référence']));
      await click(named(`Copier la référence ${HANDLER}`));
      expect(written).toEqual([HANDLER]);
      expect(panel.textContent).toContain('Référence copiée.');
      const gaps=host.querySelector('details.explorer-gaps') as HTMLDetailsElement;
      expect(gaps.open, 'replié avec un nœud choisi').toBe(false);
      expect(gaps.querySelector('[aria-label="Ce que la vue ne montre pas"]'), 'rien n’est retiré').not.toBeNull();
    });

    it('dit le refus de Taxo tel quel, sans code inventé ni tuile vide', async()=>{
      const panel=await picked();
      expect(panel.querySelector('[aria-label="Tuile de code"]')).toBeNull();
      expect(panel.querySelector('[role=alert]')?.textContent).toContain('Aucune déclaration écrite de ce symbole');
    });

    it('garde la méthode seule si son type est illisible, et dit ce que Taxo n’a pas transmis', async()=>{
      source={[HANDLER]:{reference:HANDLER, commit:'c', path:'src/A.java', items:[piece(HANDLER, 3, CLASS_LINES.slice(2, 5))]}};
      const panel=await picked();
      const lines=Array.from(panel.querySelectorAll('.code-line')) as HTMLElement[];
      expect(lines, 'le type refusé n’empêche pas la méthode').toHaveLength(3);
      expect(lines.every(line=>line.classList.contains('selected'))).toBe(true);
    });

    it('dit pourquoi Taxo n’a pas transmis le code', async()=>{
      source={[HANDLER]:{reference:HANDLER, commit:'c', path:'src/A.java', items:[], not_sent:[{what:'source', reason:'CONFIDENTIAL'}]}};
      const panel=await picked();
      expect(panel.textContent).toContain('le fichier est confidentiel');
      expect(panel.querySelector('.code-line')).toBeNull();
    });

    it('dit quand la copie échoue, sans la supposer faite', async()=>{
      serving();
      Object.defineProperty(globalThis.navigator, 'clipboard', {configurable:true, value:{writeText:async()=>{throw new Error('refusé');}}});
      const panel=await picked();
      await click(named(`Copier la référence ${HANDLER}`));
      expect(panel.textContent).toContain('Copie impossible');
      expect(panel.textContent).not.toContain('Référence copiée.');
    });

    it('dit quand le consentement manque, et ce qui le lève sur le serveur', async()=>{
      source={[HANDLER]:{error:{code:'NO_CONSENT', message:'La lecture du code n’a pas été autorisée pour cet échange.'}}};
      const panel=await picked();
      expect(panel.querySelector('[role=alert]')?.textContent).toContain('TAXO_SOURCE_READING=symbol');
    });

    it('dit un code coupé par Taxo, et un affichage borné autour de la méthode', async()=>{
      const body=Array.from({length:200}, (_, index)=>`  line ${index+1};`);
      source={'symbol:java:A':{reference:'symbol:java:A', commit:'c', path:'src/A.java', items:[{...piece('symbol:java:A', 1, body), truncated:true}]},
        [HANDLER]:{reference:HANDLER, commit:'c', path:'src/A.java', items:[piece(HANDLER, 150, body.slice(149, 153))]}};
      const panel=await picked();
      expect(panel.querySelectorAll('.code-line')).toHaveLength(120);
      expect(panel.textContent).toContain('Taxo a coupé le code à la limite de lecture');
      expect(panel.textContent).toContain('Affichage borné à 120 lignes');
      expect(panel.querySelector('.code-head .count-pill')?.textContent).toMatch(/^lignes \d+–\d+ sur 200$/);
      expect(panel.querySelector('.code-line.selected')?.textContent).toContain('150');
    });

    it('ne demande aucun code pour un nœud qui n’est pas un symbole, et le dit', async()=>{
      await open(`#/explorer?racine=${encodeURIComponent(ROUTE)}`);
      await click(host.querySelector('.chain-node.anchor'));
      await wait();
      expect(calls.filter(call=>call.operation==='get_source')).toHaveLength(0);
      expect(host.querySelector('[aria-label="Nœud choisi"]')?.textContent).toContain('n’a pas de code propre');
    });
  });
});
