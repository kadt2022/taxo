// Des Tuiles écrites à la main pour les tests de l'explorateur : la vérité est dans le test, jamais calculée par le
// code testé.
import type {Boundary, Direction, Element, Tile} from '../protocol';

type Options={relation?:string; direction?:Direction; level?:number; revisit?:boolean; occurrence?:string; identity?:string;
  producer?:string; evidence?:Element['evidence']; status?:string; count?:number};

/** Un élément : `from` est le nœud d'où il a été lu ; le fait garde son orientation réelle. */
export function element(subject:string, object:string, options:Options={}):Element{
  const {relation='DEPENDS_ON', direction='OUTGOING', level=1, revisit=false, producer='fixture'}=options;
  return {ref:'F1', fact:{kind:'ASSERTION', subject, relation, object, status:options.status??'OBSERVED', validity:'VALID',
      produced_by:{producer_id:producer, producer_version:'1.0.0'}},
    evidence_count:options.count??1, identity:options.identity??`i:${subject}|${relation}|${object}`,
    occurrence:options.occurrence??`o:${subject}|${relation}|${object}|${producer}`,
    via:{from:direction==='OUTGOING'?subject:object, relation, direction}, level, revisit, evidence:options.evidence};
}

type Shape={root?:string; items?:Element[]; nodes?:[string, number, boolean][]; frontier?:Boundary[]; stop?:string;
  revision?:number; known?:boolean; depth?:number};

export function tile({root='module:a', items=[], nodes, frontier=[], stop='ADJACENCY_COMPLETE', revision=1, known=true,
  depth=2}:Shape={}):Tile{
  const details=(nodes??[[root, 0, true]]).map(([reference, level, expanded], index)=>({reference, level, known:known||index>0,
    expanded, parents:0, discovered_by:null}));
  return {anchor:{reference:root, known}, parameters:{root, steps:[{relation:'DEPENDS_ON', direction:'OUTGOING'}], depth},
    facts_revision:revision, nodes:details.map(node=>node.reference), node_details:details, items, frontier,
    stop_reason:stop, continuation:null, not_sent:[], bytes:0};
}

export const depthCut=(node:string, remaining=0):Boundary=>({nature:'SELECTION', node, reason:'DEPTH', count:{kind:'UNKNOWN'},
  remaining_depth:remaining});
export const edgesCut=(node:string, token:string):Boundary=>({nature:'SELECTION', node, relation:'DEPENDS_ON',
  direction:'OUTGOING', reason:'EDGES', count:{kind:'AT_LEAST', value:1}, remaining_depth:1, continuation:token});
