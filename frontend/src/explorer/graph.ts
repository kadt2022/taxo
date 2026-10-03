// La vue de l'explorateur (TAXO-01J § 9) : les Tuiles reçues, fusionnées. Pur : ni React, ni réseau.
// Un nœud une fois, par sa référence ; un élément une fois, par sa poignée d'occurrence ; un lien regroupe, pour
// l'affichage seulement, les éléments d'une même identité, sans en perdre un.
import type {Boundary, Element, NotSent, Tile} from './protocol';

export type ViewNode={reference:string; level:number; known:boolean; expanded:boolean};
/** Un élément dans la vue : `level` et `revisit` y sont recalculés, la vue pouvant réunir plusieurs Tuiles. */
export type ViewElement=Element & {far:string};
export type Link={identity:string; subject:string; relation:string; object:string; elements:ViewElement[];
  revisit:boolean};
export type View={anchor:string; known:boolean; revision:number; nodes:ViewNode[]; elements:ViewElement[];
  /** La coupure de sélection en cours de chaque nœud non développé : la plus récente, avec sa reprise. */
  selection:Record<string, Boundary>; knowledge:Boundary[]; notSent:NotSent[];
  /** Une Tuile d'une autre génération de faits est arrivée : elle n'a pas été mêlée à la vue. */
  stale:boolean};

/** L'extrémité qu'un élément atteint : l'objet en sortant, le sujet en entrant. */
export const farEnd=(element:Element)=>element.via.direction==='OUTGOING'?element.fact.object:element.fact.subject;

/** La vue d'une première Tuile. */
export function viewOf(tile:Tile):View{
  return merge({anchor:tile.anchor.reference, known:tile.anchor.known, revision:tile.facts_revision, nodes:[], elements:[],
    selection:{}, knowledge:[], notSent:[], stale:false}, tile);
}

/** La vue enrichie d'une Tuile ouverte depuis `at` (développer, voir la suite), ou d'une première Tuile. Les niveaux
 * de la Tuile sont décalés du niveau de `at` dans la vue ; fusionner deux fois la même Tuile ne change rien. */
export function merge(view:View, tile:Tile, at?:string):View{
  if(tile.facts_revision!==view.revision)return {...view, stale:true};
  const offset=at===undefined?0:(view.nodes.find(node=>node.reference===at)?.level??0);
  const nodes=new Map(view.nodes.map(node=>[node.reference, node]));
  for(const detail of tile.node_details){
    const level=offset+detail.level, known=nodes.get(detail.reference);
    nodes.set(detail.reference, known?{...known, level:Math.min(known.level, level), known:known.known||detail.known,
      expanded:known.expanded||detail.expanded}:{reference:detail.reference, level, known:detail.known, expanded:detail.expanded});
  }
  const elements=[...view.elements], seen=new Set(elements.map(element=>element.occurrence));
  // Une revisite : l'extrémité atteinte était déjà dans la vue. Recalculé ici : un nœud nouveau pour une Tuile ne
  // l'est pas forcément pour la vue.
  const present=new Set([...view.nodes.map(node=>node.reference), at??tile.anchor.reference]);
  for(const item of tile.items){
    if(seen.has(item.occurrence))continue;
    const far=farEnd(item);
    elements.push({...item, level:offset+item.level, revisit:present.has(far), far});
    seen.add(item.occurrence);present.add(far);
  }
  return {...view, nodes:[...nodes.values()], elements, selection:selectionOf(view, tile, nodes, at),
    knowledge:knowledgeOf(view.knowledge, tile.frontier), notSent:tile.not_sent};
}

function selectionOf(view:View, tile:Tile, nodes:Map<string, ViewNode>, at?:string){
  const selection={...view.selection};
  if(at!==undefined)delete selection[at];
  for(const node of nodes.values())if(node.expanded)delete selection[node.reference];
  for(const boundary of tile.frontier){
    if(boundary.nature==='SELECTION'&&boundary.node&&!nodes.get(boundary.node)?.expanded)selection[boundary.node]=boundary;
  }
  return selection;
}

/** Ce que Taxo ne sait pas, ou ne peut pas savoir, réuni sans doublon : un budget ne l'efface jamais. */
function knowledgeOf(known:Boundary[], frontier:Boundary[]){
  const keys=new Set(known.map(entry=>JSON.stringify(entry))), all=[...known];
  for(const entry of frontier){
    const key=JSON.stringify(entry);
    if(entry.nature==='SELECTION'||keys.has(key))continue;
    keys.add(key);all.push(entry);
  }
  return all;
}

/** Les liens de la vue : les éléments d'une même identité regroupés, dans l'ordre de leur premier élément. Un lien est
 * une revisite si chacun de ses éléments en est une. */
export function linksOf(view:View):Link[]{
  const links=new Map<string, Link>();
  for(const element of view.elements){
    const link=links.get(element.identity);
    if(link){link.elements.push(element);link.revisit=link.revisit&&element.revisit;continue;}
    const {subject, relation, object}=element.fact;
    links.set(element.identity, {identity:element.identity, subject, relation, object, elements:[element], revisit:element.revisit});
  }
  return [...links.values()];
}

/** Les liens qu'un nœud a dans la vue, de son côté : ceux qu'il a fait découvrir, puis ceux qui l'atteignent. */
export function linksAt(links:Link[], reference:string){
  return {from:links.filter(link=>link.elements.some(element=>element.via.from===reference)),
    to:links.filter(link=>link.elements.some(element=>element.far===reference&&element.via.from!==reference))};
}
