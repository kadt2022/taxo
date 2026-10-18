// Le code d'un nœud choisi (récit « Explorer — tuile de code »). Aucune règle de graphe : ce module lit ce que Taxo a servi
// (`get_source`) et en fait des lignes numérotées, bornées, dont celles de la méthode choisie sont désignées.
import type {SourcePiece} from './protocol';
import {highlight, languageOf, type Token} from './highlight';
import {compartments, nodeType} from './sentences';

/** Au plus ce nombre de lignes à l'écran : plus long, la fenêtre suit la méthode choisie. */
export const MAX_SHOWN=120;
const CONTEXT_BEFORE=4;

export type Kind='type'|'method'|'field'|'none';

/** Ce que le code d'une référence peut être : un type, une méthode ou un constructeur (paramètres entre parenthèses) ; un
 * champ n'a pas de code propre, et seule une référence de symbole en a. Le découpage est celui de `compartments`. */
export function kindOf(reference:string):Kind{
  if(nodeType(reference)!=='symbol')return 'none';
  const {member}=compartments(reference);
  if(member===undefined)return 'type';
  return member.includes('(')?'method':'field';
}

/** Le type qui déclare un membre : sa référence sans la partie après `#`. */
export function ownerOf(reference:string){
  const at=reference.indexOf('#');
  return at<0?reference:reference.slice(0, at);
}

export type Line={number:number; text:string; tokens:Token[]; selected:boolean};
export type Tile={path:string; lines:Line[]; first:number; last:number; total:number; truncated:boolean; selected:boolean;
  from:'type'|'method'};

const linesOf=(piece:SourcePiece)=>{
  const text=piece.text.endsWith('\n')?piece.text.slice(0, -1):piece.text;
  return text.split('\n').map((value, index)=>({number:piece.line_start+index, text:value}));
};

/** La tuile à montrer : le type qui contient la méthode, la méthode surlignée, quand le type en couvre toute la plage ;
 * sinon la méthode seule, surlignée tout entière. Sans méthode, le type seul, rien de surligné. Bornée à `MAX_SHOWN`
 * lignes, autour de la sélection. */
export function tileOf(piece:SourcePiece, owner?:SourcePiece|null):Tile{
  const selects=!!owner||piece.reference.includes('(');
  const base=owner&&owner.line_start<=piece.line_start&&owner.line_start+linesOf(owner).length-1>=piece.line_end?owner:piece;
  const all=linesOf(base);
  // Coloré sur toute la pièce, avant d'être borné : un commentaire qui s'ouvre plus haut colore encore la fenêtre.
  const colored=highlight(all.map(line=>line.text), languageOf(base.path));
  const marked=selects?{from:piece.line_start, to:piece.line_end}:null;
  const lines=all.map((line, index)=>({...line, tokens:colored[index], selected:!!marked&&line.number>=marked.from&&line.number<=marked.to}));
  const window=lines.length>MAX_SHOWN?slice(lines, marked?.from):lines;
  return {path:base.path, lines:window, first:window[0].number, last:window[window.length-1].number, total:all.length,
    truncated:base.truncated, selected:!!marked, from:base===owner||!selects?'type':'method'};
}

/** Une fenêtre de `MAX_SHOWN` lignes qui commence un peu avant la ligne choisie (ou en tête, sans ligne choisie). */
function slice(lines:Line[], from?:number){
  const at=from===undefined?0:Math.max(0, lines.findIndex(line=>line.number===from)-CONTEXT_BEFORE);
  const start=Math.min(at, lines.length-MAX_SHOWN);
  return lines.slice(start, start+MAX_SHOWN);
}

const NOT_SENT:Record<string, string>={CONFIDENTIAL:'le fichier est confidentiel', GENERATED:'le fichier est généré',
  BINARY:'le fichier est binaire', TOO_LARGE:'le fichier est trop gros', NOT_A_REGULAR_FILE:'ce n’est ni un fichier ordinaire ni un symbole lisible',
  CHANGED:'le fichier a changé depuis l’analyse : le code lu ne serait plus celui qu’elle a décrit',
  NOT_DECLARED:'la déclaration n’est pas retrouvée à la ligne de la preuve', LIMIT:'la limite de lecture est atteinte'};

/** Pourquoi Taxo n'a pas transmis le code, dit comme lui. */
export const notSentText=(reason:string)=>`Taxo n’a pas transmis ce code : ${NOT_SENT[reason]??reason}.`;

/** Le motif d'un refus de Taxo, avec ce qui le lève quand c'est le réglage du serveur. */
export function refusalText(code:string, message:string){
  return code==='NO_CONSENT'
    ?`${message} Sur le serveur, le réglage TAXO_SOURCE_READING=symbol l’autorise ; il vaut off par défaut.`
    :message;
}
