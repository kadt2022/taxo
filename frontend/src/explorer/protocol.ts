// Le contrat de l'explorateur avec Taxo (TAXO-01J § 8) : construire les demandes du protocole et lire ses
// réponses. Aucun état d'écran, aucune règle de parcours : le moteur décide, ce module transporte et relit.
import type {Derivation} from '../query';

export const ENGINE='neighborhood/2';
/** Le plafond d'une opération du protocole : la Tuile s'y arrête, et le dit. */
export const MAX_BYTES=32_000;

export type Direction='OUTGOING'|'INCOMING';
export type Step={relation:string; direction:Direction};
export type Count={kind:'UNKNOWN'}|{kind:'AT_LEAST'|'EXACT'; value:number};
export type Location={path?:string; line_start?:number; line_end?:number; symbol?:string; method?:string; object?:string};
export type Producer={producer_type?:string; producer_id?:string; producer_version?:string; execution_id?:string;
  catalog_id?:string; catalog_version?:string};
export type Fact={kind?:string; subject:string; relation:string; object?:string; status?:string; validity?:string;
  qualifiers?:Record<string, unknown>; produced_by?:Producer; derivation?:Derivation; snapshot?:Record<string, string>;
  contract_version?:number};
/** Un élément : une occurrence d'un fait, dans son orientation réelle, et le chemin qui l'a atteinte. */
export type Element={ref:string; fact:Fact; evidence_count:number; identity:string; occurrence:string;
  via:{from:string; relation:string; direction:Direction}; level:number; revisit:boolean; evidence?:Location[]|null};
export type NodeDetail={reference:string; level:number; known:boolean; expanded:boolean; parents:number;
  discovered_by:number|null};
export type Boundary={nature:'SELECTION'|'KNOWLEDGE'|'CONTEXT'; scope?:'ANALYSIS'|'NODE'; node?:string; relation?:string;
  direction?:Direction; reason:string; count:Count; remaining_depth?:number; continuation?:string; producer?:string|null;
  subject?:string; languages?:string[]; causes?:string[]};
export type NotSent={what:string; count?:number; reason:string};
export type Tile={anchor:{reference:string; known:boolean}; parameters:{root:string; steps:Step[]; depth:number};
  facts_revision:number; nodes:string[]; node_details:NodeDetail[]; items:Element[]; frontier:Boundary[];
  stop_reason:string; continuation:string|null; not_sent:NotSent[]; bytes:number};
/** Une Tuile en forme compacte : les champs communs une fois, des renvois par indice. */
export type CompactTile=Omit<Tile, 'items'|'node_details'> & {shared:{common:Partial<Fact>[]};
  node_details:Omit<NodeDetail, 'reference'>[];
  items:(Omit<Element, 'fact'|'via'> & {fact:Partial<Fact>; common:number; via:{from:number; step:number}})[]};
export type Reference={reference:string; type:string};
export type ReferencePage={items:Reference[]; next:string|null};
export type Proof={ref:string; fact:string; location:Location};
export type Described={relations:{relation:string; count:number}[]; analyzers:{analyzer:string; status:string;
  relations:string[]}[]; types:string[]};
export type Budget={max_nodes:number; max_edges:number; max_work:number; max_fanout:number};
export type TileDemand={root:string; relations:string[]; direction:Direction|'BOTH'; depth:number; budget:Budget;
  continuation?:string};

/** Un refus de Taxo : son code et son motif, dits tels quels. */
export class Refusal extends Error{
  constructor(readonly code:string, message:string){super(message);}
}

type Envelope={outcome:'OK'|'ERROR'; error?:{code:string; message:string}};
export type Post=<T>(path:string, init:RequestInit)=>Promise<T>;
export type Query=<T>(operation:string, args:Record<string, unknown>, signal?:AbortSignal)=>Promise<T>;

// Les opérations qui nomment leur analyse dans leurs arguments ; les autres la tiennent de l'échange.
const NAMED=new Set(['get_neighborhood', 'find_references']);

/** Un échange du protocole par demande, sur l'analyse choisie : la réponse `OK`, ou le refus de Taxo. */
export function queryOf(post:Post, base:string, analysis:string):Query{
  return async<T,>(operation:string, args:Record<string, unknown>, signal?:AbortSignal)=>{
    const named=NAMED.has(operation)?{analysis, ...args}:args;
    const body={analysis, requests:[{operation, max_bytes:MAX_BYTES, arguments:named}]};
    const answer=await post<{responses:(Envelope&T)[]}>(`${base}/taxo-query`, {method:'POST', signal,
      headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const [response]=answer.responses;
    if(response.outcome==='ERROR')throw new Refusal(response.error?.code??'ERROR', response.error?.message??'Refusé par Taxo.');
    return response;
  };
}

/** Les arguments d'une Tuile : toujours `neighborhood/2`, preuves résumées, forme compacte. */
export function tileArguments(demand:TileDemand){
  return {engine:ENGINE, root:demand.root, follow:demand.relations, direction:demand.direction, depth:demand.depth,
    ...demand.budget, evidence:'SUMMARY', form:'COMPACT', ...(demand.continuation?{continuation:demand.continuation}:{})};
}

/** La forme complète d'une Tuile compacte, d'après le contrat : rien n'est inventé, tout est renvoyé. */
export function expandTile(tile:CompactTile):Tile{
  const {shared, ...rest}=tile;
  const steps=tile.parameters.steps;
  return {...rest,
    node_details:tile.node_details.map((node, index)=>({reference:tile.nodes[index], ...node})),
    items:tile.items.map(({common, via, fact, ...item})=>({...item, fact:{...fact, ...shared.common[common]} as Fact,
      via:{from:tile.nodes[via.from], ...steps[via.step]}}))};
}

export async function openTile(query:Query, demand:TileDemand, signal?:AbortSignal){
  return expandTile(await query<CompactTile>('get_neighborhood', tileArguments(demand), signal));
}

/** Les références de l'analyse qui commencent par `prefix` : une page, dans l'ordre de leur clé. */
export function findReferences(query:Query, prefix:string, type?:string, after?:string|null, signal?:AbortSignal){
  return query<ReferencePage>('find_references', {prefix, ...(type?{type}:{}), ...(after?{after}:{}), limit:20}, signal);
}

/** Les preuves complètes d'une occurrence, par sa poignée, dans un autre échange que la Tuile. */
export async function evidenceOf(query:Query, occurrence:string, signal?:AbortSignal){
  return (await query<{evidence:Proof[]}>('get_evidence', {occurrence}, signal)).evidence;
}

type DescribeItem={kind:string; relation?:string; count?:number; analyzer?:string; status?:string; relations?:string[];
  subject_types?:string[]; object_types?:string[]};

/** Ce que l'analyse annonce : ses relations présentes, chaque analyseur avec ce qu'il sait produire, et les types de
 * références de ses relations. */
export async function describe(query:Query, signal?:AbortSignal):Promise<Described>{
  const items=(await query<{items:DescribeItem[]}>('describe', {}, signal)).items;
  const relations=items.filter(item=>item.kind==='relation');
  const types=new Set(relations.flatMap(item=>[...item.subject_types??[], ...item.object_types??[]]));
  return {relations:relations.map(item=>({relation:item.relation!, count:item.count??0})),
    analyzers:items.filter(item=>item.kind==='analyzer').map(item=>({analyzer:item.analyzer!, status:item.status??'',
      relations:item.relations??[]})), types:[...types].sort((a, b)=>a.localeCompare(b))};
}
