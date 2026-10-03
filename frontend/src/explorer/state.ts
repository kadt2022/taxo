// L'état de navigation de l'explorateur (TAXO-01J § 9) : l'adresse, la vue, la demande en cours, le parcours précédent
// et suivant. Réducteur pur : une réponse qui n'est pas celle de la demande en cours est ignorée, sans exception.
import {merge, viewOf, type View} from './graph';
import type {Budget, Direction, Tile} from './protocol';

export const PRESETS={compact:{max_nodes:30, max_edges:60, max_work:100, max_fanout:10},
  standard:{max_nodes:60, max_edges:120, max_work:300, max_fanout:20},
  large:{max_nodes:200, max_edges:400, max_work:2000, max_fanout:50}} satisfies Record<string, Budget>;
export type Preset=keyof typeof PRESETS;
export const PRESET_NAMES:Record<Preset, string>={compact:'Compact', standard:'Standard', large:'Large'};
export const MAX_DEPTH=4;
/** Le protocole suit au plus 16 relations à la fois. */
export const MAX_RELATIONS=16;

/** Ce que l'adresse dit : l'analyse, l'ancre, les relations suivies, le sens, la profondeur, le budget. */
export type Settings={analysis?:string; root?:string; relations:string[]; direction:Direction|'BOTH'; depth:number;
  preset:Preset};
const SIDES=new Set(['OUTGOING', 'INCOMING', 'BOTH']);

export function settingsOf(params:URLSearchParams):Settings{
  const depth=Number.parseInt(params.get('profondeur')??'', 10);
  const direction=params.get('sens')??'';
  const preset=params.get('budget')??'';
  const relations=[...new Set((params.get('pas')??'').split(',').map(item=>item.trim()).filter(Boolean))];
  return {analysis:params.get('analyse')||undefined, root:params.get('racine')||undefined, relations,
    direction:SIDES.has(direction)?direction as Settings['direction']:'BOTH',
    depth:depth>=1&&depth<=MAX_DEPTH?depth:2, preset:preset in PRESETS?preset as Preset:'standard'};
}

/** Les paramètres d'adresse d'un réglage ; les valeurs par défaut sont omises. */
export function addressOf(settings:Settings):Record<string, string|undefined>{
  return {analyse:settings.analysis, racine:settings.root, pas:settings.relations.join(',')||undefined,
    sens:settings.direction==='BOTH'?undefined:settings.direction, profondeur:settings.depth===2?undefined:String(settings.depth),
    budget:settings.preset==='standard'?undefined:settings.preset};
}

/** Ce qui est sélectionné : un lien (par son identité) ou un nœud (par sa référence). */
export type Selected={kind:'link'; identity:string}|{kind:'node'; reference:string}|null;
export type Pending={id:number; action:'open'|'expand'|'more'; node?:string};
export type ExplorerState={view:View|null; pending:Pending|null; error:string; selected:Selected};
export type Action={type:'start'; pending:Pending}|{type:'loaded'; id:number; tile:Tile}|{type:'failed'; id:number; message:string}
  |{type:'cancel'}|{type:'select'; selected:Selected};

export const INITIAL:ExplorerState={view:null, pending:null, error:'', selected:null};

export function reduce(state:ExplorerState, action:Action):ExplorerState{
  switch(action.type){
  case 'start':
    // Ouvrir une nouvelle ancre efface la vue ; développer la garde.
    return action.pending.action==='open'?{...INITIAL, pending:action.pending}:{...state, pending:action.pending, error:''};
  case 'loaded':{
    const pending=state.pending;
    if(pending?.id!==action.id)return state;
    const view=pending.action==='open'||!state.view?viewOf(action.tile):merge(state.view, action.tile, pending.node);
    return {...state, view, pending:null};
  }
  case 'failed':
    return state.pending?.id===action.id?{...state, pending:null, error:action.message}:state;
  case 'cancel':
    return {...state, pending:null};
  case 'select':
    return {...state, selected:action.selected};
  }
}

/** Le parcours des ancres visitées, précédent et suivant compris, suivi sur l'adresse. */
export type Trail={entries:string[]; position:number};
export const NO_TRAIL:Trail={entries:[], position:-1};

/** L'adresse visitée : un pas en arrière ou en avant si c'est la voisine, sinon une nouvelle entrée qui efface la suite. */
export function visit(trail:Trail, address:string):Trail{
  const {entries, position}=trail;
  if(entries[position]===address)return trail;
  if(position>0&&entries[position-1]===address)return {entries, position:position-1};
  if(entries[position+1]===address)return {entries, position:position+1};
  return {entries:[...entries.slice(0, position+1), address], position:position+1};
}
export const canGoBack=(trail:Trail)=>trail.position>0;
export const canGoForward=(trail:Trail)=>trail.position<trail.entries.length-1;
