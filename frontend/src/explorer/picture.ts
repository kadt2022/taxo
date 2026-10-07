// L'image d'un diagramme des vues Appels et Chaîne : la mise en page de `chain.ts` redessinée en un SVG autonome, que le
// navigateur convertit en PNG. Pur : une chaîne de caractères, sans React ni réseau. Les couleurs sont celles du thème
// affiché, lues par l'appelant ; les textes viennent de la mise en page et des décorations reçues, rien n'est ajouté.
import type {Arrow, Box, ChainLayout} from './chain';

export type Palette={surface:string; text:string; muted:string; line:string; frontier:string; frontierSoft:string;
  cut:string; border:string};
/** Ce que l'écran ajoute à une boîte de nœud : son stéréotype et sa teinte. */
export type Decoration={stereo:string; tone:string};

const FONT='Inter, system-ui, -apple-system, Segoe UI, sans-serif', MONO='ui-monospace, SFMono-Regular, Menlo, monospace';
const LINE=18, HEADER=24;

export const escape=(text:string)=>text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const texts=(lines:string[], x:number, y:number, attributes:string)=>lines.map((said, index)=>
  `<text x="${x}" y="${y+index*LINE}" ${attributes}>${escape(said)}</text>`).join('');
/** La largeur approchée d'une étiquette : le SVG n'a pas de mise en page de texte. */
const width=(said:string, size:number)=>Math.ceil(said.length*size*0.56);

export function picture(layout:ChainLayout, palette:Palette, decorate:(box:Box)=>Decoration,
  label:(arrow:Arrow)=>{verb:string; marks:string[]}):string{
  const p=palette, parts:string[]=[];
  parts.push(`<rect width="${layout.width}" height="${layout.height}" fill="${p.surface}"/>`);
  parts.push(`<defs><marker id="flow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">`
    +`<path d="M0 0L10 5L0 10z" fill="${p.line}"/></marker>`
    +`<marker id="side" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto-start-reverse">`
    +`<path d="M1 1L11 6L1 11z" fill="${p.surface}" stroke="${p.line}" stroke-width="1.5"/></marker></defs>`);
  for(const tie of layout.ties)parts.push(`<path d="${tie.path}" fill="none" stroke="${tie.box.kind==='note'?p.frontier:p.border}"`
    +` stroke-width="1.4" stroke-dasharray="2 4"/>`);
  for(const arrow of layout.arrows){
    const side=arrow.form==='SIDE';
    parts.push(`<path d="${arrow.path}" fill="none" stroke="${p.line}" stroke-width="2"${side?' stroke-dasharray="6 4"':''}`
      +`${arrow.link.revisit?' opacity="0.7"':''} marker-end="url(#${side?'side':'flow'})"/>`);
  }
  for(const box of layout.boxes)parts.push(shape(box, p, decorate));
  for(const arrow of layout.arrows){
    const {verb, marks}=label(arrow), {x, y}=arrow.label;
    const wide=width(verb, 12)+marks.length*20+18;
    let mark=x+9+width(verb, 12)+6;
    parts.push(`<rect x="${x}" y="${y}" width="${wide}" height="22" rx="11" fill="${p.surface}" stroke="${p.border}"/>`
      +`<text x="${x+9}" y="${y+15}" font-family="${FONT}" font-size="12" font-weight="650" fill="${p.text}">${escape(verb)}</text>`
      +marks.map(said=>{
        const at=mark;mark+=20;
        return `<rect x="${at}" y="${y+3}" width="16" height="16" rx="5" fill="none" stroke="${p.text}" stroke-width="1.2"/>`
          +`<text x="${at+8}" y="${y+15}" text-anchor="middle" font-family="${FONT}" font-size="10" font-weight="800" fill="${p.text}">${escape(said)}</text>`;
      }).join(''));
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${layout.width}" height="${layout.height}" viewBox="0 0 ${layout.width} ${layout.height}">${parts.join('')}</svg>`;
}

function shape(box:Box, p:Palette, decorate:(box:Box)=>Decoration){
  const {x, y, width:w, height:h}=box;
  if(box.kind==='node'){
    const {stereo, tone}=decorate(box), r=12, context=box.context??[], member=box.member??[];
    const head=`M${x} ${y+HEADER}V${y+r}Q${x} ${y} ${x+r} ${y}H${x+w-r}Q${x+w} ${y} ${x+w} ${y+r}V${y+HEADER}Z`;
    // Les lignes de base : 13 sous le haut de chaque ligne de texte ; le trait du membre suit la dernière ligne de nom.
    const top=y+HEADER+7, nameTop=top+13, contextTop=nameTop+box.lines.length*LINE;
    const memberTop=top+(box.lines.length+context.length)*LINE+4;
    return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${p.surface}"/>`
      +`<path d="${head}" fill="${tone}" fill-opacity="0.16"/>`
      +`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="none" stroke="${tone}" stroke-width="${box.anchor?3:2}"/>`
      +`<text x="${x+14}" y="${y+16}" font-family="${FONT}" font-size="11.5" font-style="italic" font-weight="650" fill="${tone}">${escape(stereo)}</text>`
      +texts(box.lines, x+14, nameTop, `font-family="${FONT}" font-size="14" font-weight="650" fill="${p.text}"`)
      +texts(context, x+14, contextTop, `font-family="${FONT}" font-size="11.5" fill="${p.muted}"`)
      +(member.length?`<path d="M${x} ${memberTop}H${x+w}" stroke="${tone}" stroke-opacity="0.3"/>`
        +texts(member, x+14, memberTop+5+13, `font-family="${MONO}" font-size="12.5" fill="${p.text}"`):'');
  }
  if(box.kind==='note')return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" fill="${p.frontierSoft}" stroke="${p.frontier}" stroke-width="1.5"/>`
    +`<text x="${x+12}" y="${y+16}" font-family="${FONT}" font-size="11" font-weight="750" letter-spacing="0.6" fill="${p.frontier}">FRONTIÈRE · TAXO NE SAIT PAS</text>`
    +texts(box.lines, x+12, y+HEADER+13, `font-family="${FONT}" font-size="12.5" fill="${p.text}"`);
  const round=box.kind==='cut'?h/2:10, dash=box.kind==='revisit'?'2 3':'5 4';
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${round}" fill="${box.kind==='cut'?p.cut:p.surface}" stroke="${p.border}"`
    +` stroke-width="1.5" stroke-dasharray="${dash}"/>`
    +texts(box.lines, x+(box.kind==='cut'?18:12), y+7+13, `font-family="${FONT}" font-size="12.5" fill="${p.muted}"${box.kind==='revisit'?' font-style="italic"':''}`);
}
