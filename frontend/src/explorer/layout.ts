// La mise en couches de la vue (TAXO-01J § 9) : une colonne par niveau, les nœuds dans l'ordre de la vue, chaque lien
// tracé du sujet vers l'objet, dans le sens réel du fait, même découvert en entrant. Pur : des nombres et des chemins.
import type {Link, View} from './graph';

export type Geometry={column:number; row:number; width:number; height:number; margin:number};
export const GEOMETRY:Geometry={column:280, row:60, width:210, height:40, margin:20};
export type Placed={reference:string; level:number; row:number; x:number; y:number};
/** L'extrémité d'un lien qui n'est pas un nœud (une valeur littérale, ou aucun objet) : dessinée à part, jamais un nœud
 * qu'on développe ou recentre. `reference` est l'identité de son lien. */
export type Leaf=Placed & {value?:string};
/** Un lien placé : `lane` le sépare des autres liens entre les deux mêmes nœuds. */
export type Edge={link:Link; from:Placed; to:Placed; lane:number; lanes:number; dashed:boolean; count:number;
  path:string; label:{x:number; y:number}};
export type Layout={nodes:Placed[]; leaves:Leaf[]; edges:Edge[]; width:number; height:number};

export function layout(view:View, links:Link[], geometry:Geometry=GEOMETRY):Layout{
  const rows=new Map<number, number>(), placed=new Map<string, Placed>(), leaves:Leaf[]=[];
  const at=(reference:string, level:number):Placed=>{
    const row=rows.get(level)??0;
    rows.set(level, row+1);
    return {reference, level, row, x:geometry.margin+level*geometry.column, y:geometry.margin+row*geometry.row};
  };
  for(const node of view.nodes)placed.set(node.reference, at(node.reference, node.level));
  // Un lien dont l'objet n'est pas un nœud de la vue mène à une feuille, à la colonne suivante de son sujet.
  const ends=new Map<string, Placed>();
  for(const link of links){
    const from=placed.get(link.subject);
    if(!from||(link.object!==undefined&&placed.has(link.object)))continue;
    const leaf={...at(link.identity, from.level+1), value:link.object};
    leaves.push(leaf);ends.set(link.identity, leaf);
  }
  const target=(link:Link)=>ends.get(link.identity)??(link.object===undefined?undefined:placed.get(link.object));
  const pairs=new Map<string, number>(), counts=new Map<string, number>();
  const key=(link:Link)=>[link.subject, target(link)?.reference??''].sort((a, b)=>a.localeCompare(b)).join('\u0000');
  for(const link of links)counts.set(key(link), (counts.get(key(link))??0)+1);
  const edges:Edge[]=[];
  for(const link of links){
    const from=placed.get(link.subject), to=target(link);
    if(!from||!to)continue;
    const lane=pairs.get(key(link))??0;
    pairs.set(key(link), lane+1);
    const lanes=counts.get(key(link))!;
    const {path, label}=route(from, to, lane-(lanes-1)/2, geometry);
    edges.push({link, from, to, lane, lanes, dashed:link.revisit, count:link.elements.length, path, label});
  }
  const levels=Math.max(0, ...view.nodes.map(node=>node.level), ...leaves.map(leaf=>leaf.level));
  const tallest=Math.max(1, ...rows.values());
  return {nodes:[...placed.values()], leaves, edges, width:2*geometry.margin+levels*geometry.column+geometry.width+60,
    height:2*geometry.margin+(tallest-1)*geometry.row+geometry.height+30};
}

const point=(x:number, y:number)=>`${Math.round(x)} ${Math.round(y)}`;

/** Le tracé d'un lien : vers la droite d'une colonne à la suivante ; en arc sinon (même colonne, retour, boucle).
 * `shift` écarte les liens parallèles les uns des autres. */
export function route(from:Placed, to:Placed, shift:number, geometry:Geometry=GEOMETRY){
  const {width, height}=geometry, spread=14*shift;
  if(from.reference===to.reference){
    const x=from.x+width, y=from.y+height/2, reach=30+Math.abs(spread);
    return {path:`M${point(x, y-8)} C${point(x+reach, y-reach)} ${point(x+reach, y+reach)} ${point(x, y+8)}`,
      label:{x:x+reach*0.75, y}};
  }
  const forward=to.x>from.x;
  const start={x:from.x+width, y:from.y+height/2+spread/2};
  const end={x:forward?to.x:to.x+width, y:to.y+height/2+spread/2};
  const bend=forward?(end.x-start.x)/2:50+Math.abs(spread)*2;
  const first={x:start.x+bend, y:start.y+spread}, second={x:forward?end.x-bend:end.x+bend, y:end.y+spread};
  return {path:`M${point(start.x, start.y)} C${point(first.x, first.y)} ${point(second.x, second.y)} ${point(end.x, end.y)}`,
    label:{x:(start.x+3*first.x+3*second.x+end.x)/8, y:(start.y+3*first.y+3*second.y+end.y)/8}};
}
