// La vue Chaîne (TAXO-UI-06, E3) : la même vue que les couches, lue de haut en bas. Une ligne par boîte ; chaque
// lien de chaîne pose son extrémité découverte une ligne plus bas, en retrait ; un lien de côté la pose dans la colonne
// de droite, comme une réalisation UML. Les frontières sont des boîtes accrochées sous leur nœud. Pur : des nombres, des
// lignes de texte et des chemins. La forme des relations et les phrases sont reçues : rien ici ne nomme une relation.
import type {Boundary} from './protocol';
import type {Link, View} from './graph';

export type Form='CHAIN'|'SIDE';
export type ChainGeometry={margin:number; width:number; indent:number; gap:number; sideGap:number; header:number;
  line:number; pad:number; chars:number};
export const CHAIN_GEOMETRY:ChainGeometry={margin:24, width:300, indent:44, gap:44, sideGap:150, header:24, line:18,
  pad:14, chars:34};

/** Une boîte : un nœud, une feuille (aucun objet ou une valeur), une frontière de connaissance (`note`), une coupure de
 * sélection (`cut`), ou un lien vers un nœud déjà dessiné (`revisit`). */
export type Box={key:string; kind:'node'|'leaf'|'note'|'cut'|'revisit'; column:'main'|'side'; depth:number;
  x:number; y:number; width:number; height:number; lines:string[]; reference?:string; link?:Link; value?:string;
  boundary?:Boundary; anchor?:boolean};
/** Une flèche, toujours du sujet vers l'objet, même quand l'objet est au-dessus. `label` est le coin de son étiquette. */
export type Arrow={link:Link; form:Form; from:Box; to:Box; path:string; label:{x:number; y:number}};
/** Le trait qui accroche une frontière, une coupure ou une revisite à son nœud. */
export type Tie={box:Box; path:string};
export type ChainLayout={boxes:Box[]; arrows:Arrow[]; ties:Tie[]; width:number; height:number};

export type ChainText={name:(reference:string)=>string; note:(boundary:Boundary)=>string; cut:(boundary:Boundary)=>string;
  revisit:(link:Link, target:string)=>string; leaf:(value:string|undefined)=>string};

/** Un texte en lignes d'au plus `chars` caractères, coupées après une ponctuation ou une espace quand c'est possible :
 * aucun découpage selon le sens de la référence, et rien n'est perdu. */
export function wrap(text:string, chars:number):string[]{
  const tokens=text.match(/[^\s.#/:(),]*[\s.#/:(),]?/g)!.filter(Boolean);
  const lines:string[]=[];
  let current='';
  for(let token of tokens){
    while(token.length>chars){
      if(current){lines.push(current.trimEnd());current='';}
      lines.push(token.slice(0, chars));token=token.slice(chars);
    }
    if((current+token).trimEnd().length>chars&&current){lines.push(current.trimEnd());current='';}
    current+=token;
  }
  if(current.trim()||!lines.length)lines.push(current.trimEnd());
  return lines;
}

const near=(link:Link)=>link.elements[0].via.from;
const far=(link:Link)=>link.elements[0].far;

export function chain(view:View, links:Link[], form:(relation:string)=>Form, text:ChainText,
  geometry:ChainGeometry=CHAIN_GEOMETRY):ChainLayout{
  const {width, gap, header, line, pad, chars}=geometry;
  const boxes:Box[]=[], placed=new Map<string, Box>(), cursor={main:geometry.margin, side:geometry.margin};
  const pending:{link:Link; from:Box; to:Box}[]=[], ties:{owner:Box; box:Box}[]=[];
  const out=new Map<string, Link[]>();
  for(const link of links)out.set(near(link), [...out.get(near(link))??[], link]);
  const used=new Set<string>();

  const put=(box:Omit<Box, 'x'|'y'>, top?:number):Box=>{
    const y=Math.max(cursor[box.column], top??0);
    const made={...box, x:0, y};
    cursor[box.column]=y+box.height+gap;
    boxes.push(made);
    return made;
  };
  const lines=(value:string)=>wrap(value, chars);
  const notes=(reference:string)=>view.knowledge.filter(entry=>entry.scope==='NODE'&&entry.node===reference);

  function visit(reference:string, depth:number, column:'main'|'side', top?:number):Box{
    const name=lines(text.name(reference));
    const box=put({key:reference, kind:'node', column, depth, width, height:header+name.length*line+pad, lines:name,
      reference, anchor:reference===view.anchor}, top);
    placed.set(reference, box);
    const own=(out.get(reference)??[]).filter(link=>!used.has(link.identity));
    for(const link of own)used.add(link.identity);
    // À côté d'abord : la réalisation se lit sur la ligne de son nœud.
    let sideTop=box.y;
    for(const link of own.filter(item=>form(item.relation)==='SIDE')){
      const end=column==='main'?place(link, 0, 'side', sideTop, box):place(link, depth, column, sideTop, box);
      if(end)sideTop=end.y+end.height+gap/2;
    }
    for(const link of own.filter(item=>form(item.relation)==='CHAIN'))place(link, depth+1, column, undefined, box);
    for(const boundary of notes(reference)){
      const said=lines(text.note(boundary));
      ties.push({owner:box, box:put({key:`note:${reference}:${boundary.reason}:${boundary.subject??''}`, kind:'note', column,
        depth:depth+1, width, height:header+said.length*line+pad, lines:said, boundary})});
    }
    const cut=view.selection[reference];
    if(cut){
      const said=lines(text.cut(cut));
      ties.push({owner:box, box:put({key:`cut:${reference}`, kind:'cut', column, depth:depth+1, width,
        height:said.length*line+pad+6, lines:said, boundary:cut, reference})});
    }
    return box;
  }

  /** L'extrémité découverte d'un lien : une feuille, une revisite, ou un nœud visité à son tour. */
  function place(link:Link, depth:number, column:'main'|'side', top:number|undefined, owner:Box):Box|null{
    const end=far(link);
    if(end===null){
      const said=lines(text.leaf(link.object));
      const leaf=put({key:`leaf:${link.identity}`, kind:'leaf', column, depth, width, height:said.length*line+pad,
        lines:said, link, value:link.object}, top);
      pending.push({link, from:link.subject===owner.reference?owner:leaf, to:link.subject===owner.reference?leaf:owner});
      return leaf;
    }
    const known=placed.get(end);
    if(known){
      const said=lines(text.revisit(link, end));
      const chip=put({key:`revisit:${link.identity}`, kind:'revisit', column:owner.column, depth:owner.depth+1, width,
        height:said.length*line+pad, lines:said, link});
      ties.push({owner, box:chip});
      return null;
    }
    const box=visit(end, depth, column, top);
    pending.push({link, from:placed.get(link.subject)!, to:placed.get(link.object!)!});
    return box;
  }

  visit(view.anchor, 0, 'main');
  // Rien n'est omis : un nœud que l'ancre n'atteint pas dans cette vue est posé à part, avec ses liens.
  for(const node of view.nodes)if(!placed.has(node.reference))visit(node.reference, 0, 'main');

  const mainRight=Math.max(0, ...boxes.filter(box=>box.column==='main').map(box=>box.depth*geometry.indent+box.width));
  const sideLeft=geometry.margin+mainRight+geometry.sideGap;
  for(const box of boxes)box.x=(box.column==='main'?geometry.margin:sideLeft)+box.depth*geometry.indent;
  const order=new Map(links.map((link, index)=>[link.identity, index]));
  pending.sort((a, b)=>order.get(a.link.identity)!-order.get(b.link.identity)!);
  const arrows=pending.map(({link, from, to})=>arrow(link, form(link.relation), from, to, geometry, geometry.margin+mainRight));
  const right=Math.max(...boxes.map(box=>box.x+box.width));
  const bottom=Math.max(...boxes.map(box=>box.y+box.height));
  return {boxes, arrows, ties:ties.map(({owner, box})=>({box, path:tie(owner, box)})), width:right+geometry.margin,
    height:bottom+geometry.margin};
}

const point=(x:number, y:number)=>`${Math.round(x)} ${Math.round(y)}`;
const middle=(box:Box)=>box.y+Math.min(box.height/2, 20);

/** Le tracé d'une flèche. Dans la chaîne : un tronc qui descend (ou monte) depuis le nœud du dessus, puis entre dans
 * la boîte du dessous par la gauche. À côté : de la boîte de droite vers le bord droit du nœud, par un couloir. */
function arrow(link:Link, form:Form, from:Box, to:Box, geometry:ChainGeometry, mainRight:number):Arrow{
  if(from.column!==to.column){
    const [left, right]=from.x<to.x?[from, to]:[to, from];
    const lane=mainRight+24;
    const leftEnd=left.x+left.width;
    const route=[point(right.x, middle(right)), `H${Math.round(lane)}`, `V${Math.round(middle(left))}`, `H${Math.round(leftEnd)}`];
    const path=from===right?`M${route.join(' ')}`:`M${point(leftEnd, middle(left))} H${Math.round(lane)} V${Math.round(middle(right))} H${Math.round(right.x)}`;
    return {link, form, from, to, path, label:{x:lane+10, y:middle(right)-26}};
  }
  const [top, bottom]=from.y<to.y?[from, to]:[to, from];
  const trunk=top.x+geometry.indent/2;
  const down=`M${point(trunk, top.y+top.height)} V${Math.round(middle(bottom))} H${Math.round(bottom.x)}`;
  const up=`M${point(bottom.x, middle(bottom))} H${Math.round(trunk)} V${Math.round(top.y+top.height)}`;
  return {link, form, from, to, path:from===top?down:up, label:{x:bottom.x+8, y:bottom.y-geometry.gap/2-11}};
}

function tie(owner:Box, box:Box){
  const trunk=owner.x+16;
  return `M${point(trunk, owner.y+owner.height)} V${Math.round(middle(box))} H${Math.round(box.x)}`;
}
