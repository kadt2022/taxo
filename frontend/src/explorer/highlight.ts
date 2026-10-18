// La coloration du code d'une tuile, à la manière d'un éditeur : mots-clés, types, annotations, chaînes, commentaires, nombres,
// appels. Un analyseur lexical léger, sans dépendance : il ne comprend pas le langage, il le colore, et un texte qu'il ne
// reconnaît pas reste de la couleur du texte. Aucune règle de graphe ici.

export type Kind='keyword'|'type'|'string'|'comment'|'number'|'annotation'|'method'|'constant'|'plain';
export type Token={text:string; kind:Kind};

const KEYWORDS=new Set(['abstract', 'assert', 'boolean', 'break', 'byte', 'case', 'catch', 'char', 'class', 'const', 'continue',
  'default', 'do', 'double', 'else', 'enum', 'extends', 'final', 'finally', 'float', 'for', 'goto', 'if', 'implements', 'import',
  'instanceof', 'int', 'interface', 'long', 'native', 'new', 'package', 'private', 'protected', 'public', 'return', 'short',
  'static', 'strictfp', 'super', 'switch', 'synchronized', 'this', 'throw', 'throws', 'transient', 'try', 'void', 'volatile',
  'while', 'true', 'false', 'null', 'var', 'record', 'sealed', 'permits', 'yield']);

/** Le langage d'une pièce de code, lu dans l'extension de son fichier ; vide quand le portail ne sait pas le colorer. */
export function languageOf(path:string){
  return /\.java$/i.test(path)?'java':'';
}

const NUMBER=/^(?:0[xX][0-9a-fA-F_]+[lL]?|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?[lLfFdD]?)/;
const WORD=/^[A-Za-z_$][\w$]*/;
const ANNOTATION=/^@[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*/;

type State={block:boolean; text:boolean};

/** La fin d'un texte entre guillemets ou d'une apostrophe : l'indice qui suit le délimiteur fermant, ou la fin de la ligne. */
function quoted(line:string, from:number, delimiter:string){
  for(let at=from+1; at<line.length; at++){
    if(line[at]==='\\'){at++;continue;}
    if(line[at]===delimiter)return at+1;
  }
  return line.length;
}

/** Le mot lu à `at` : un mot-clé, un appel (suivi d'une parenthèse), un type ou une constante (majuscules), sinon du texte. */
function wordKind(word:string, rest:string):Kind{
  if(KEYWORDS.has(word))return 'keyword';
  if(rest.trimStart().startsWith('('))return 'method';
  if(word.length>1&&/^[A-Z][A-Z0-9_]*$/.test(word))return 'constant';
  return /^[A-Z]/.test(word)?'type':'plain';
}

function lineTokens(line:string, state:State):Token[]{
  const tokens:Token[]=[];
  const push=(text:string, kind:Kind)=>{
    if(!text)return;
    const last=tokens[tokens.length-1];
    if(last?.kind===kind&&kind==='plain')last.text+=text;
    else tokens.push({text, kind});
  };
  let at=0;
  while(at<line.length){
    const rest=line.slice(at);
    if(state.block||state.text){
      const close=rest.indexOf(state.block?'*/':'"""');
      const end=close<0?line.length:at+close+(state.block?2:3);
      push(line.slice(at, end), state.block?'comment':'string');
      if(close>=0){state.block=false;state.text=false;}
      at=end;
    }else if(rest.startsWith('//')){push(rest, 'comment');at=line.length;}
    else if(rest.startsWith('/*')){
      const close=rest.indexOf('*/', 2);
      const end=close<0?line.length:at+close+2;
      push(line.slice(at, end), 'comment');
      state.block=close<0;
      at=end;
    }else if(rest.startsWith('"""')){state.text=true;push('"""', 'string');at+=3;}
    else if(rest[0]==='"'||rest[0]==='\''){const end=quoted(line, at, rest[0]);push(line.slice(at, end), 'string');at=end;}
    else if(ANNOTATION.test(rest)){const found=ANNOTATION.exec(rest)![0];push(found, 'annotation');at+=found.length;}
    else if(/^\d/.test(rest)&&NUMBER.test(rest)){const found=NUMBER.exec(rest)![0];push(found, 'number');at+=found.length;}
    else if(WORD.test(rest)){const found=WORD.exec(rest)![0];push(found, wordKind(found, rest.slice(found.length)));at+=found.length;}
    else{push(rest[0], 'plain');at++;}
  }
  return tokens;
}

/** Les éléments colorés de chaque ligne ; un commentaire ou un texte sur plusieurs lignes se poursuit d'une ligne à l'autre. Un
 * langage inconnu rend chaque ligne en un seul élément de texte. */
export function highlight(lines:string[], language:string):Token[][]{
  if(language!=='java')return lines.map(text=>text?[{text, kind:'plain'}]:[]);
  const state:State={block:false, text:false};
  return lines.map(line=>lineTokens(line, state));
}
