// Ce que l'explorateur dit (TAXO-01J § 9) : chaque frontière, chaque marque, la portée de la vue. Pur. Des comptes,
// jamais de pourcentage ; jamais « complet » : une vue montre ce que ses pas atteignent, pas tout le logiciel. Un type
// ou une relation que le portail ne connaît pas s'affiche par son nom brut.
import {COVERAGE, EVALUATORS, STATUS_MARKS, TONES, TYPES, VERBS, label, reference} from '../vocabulary';
import type {Boundary, Count, Direction, NotSent} from './protocol';
import type {Link, View, ViewNode} from './graph';

const plural=(count:number, word:string)=>`${count} ${word}${count>1?'s':''}`;

export const DIRECTIONS:Record<Direction|'BOTH', string>={OUTGOING:'sortant', INCOMING:'entrant', BOTH:'les deux sens'};

/** Pourquoi un nœud n'est pas développé, ou pourquoi son adjacence est coupée. */
const SELECTION:Record<string, string>={DEPTH:'Non développé : profondeur demandée atteinte',
  NOT_REACHED:'Non développé : la vue s’est arrêtée avant lui', NODES:'Suite disponible : limite de nœuds atteinte',
  EDGES:'Suite disponible : limite de liens atteinte', WORK:'Suite disponible : limite de lectures atteinte',
  BYTES:'Suite disponible : taille de réponse atteinte', FANOUT:'Suite disponible : limite de liens par nœud atteinte'};

/** Un décompte qualifié : « au moins 1 », « 12 », ou rien quand Taxo ne le sait pas. */
export function countText(count:Count){
  if(count.kind==='UNKNOWN')return '';
  return count.kind==='AT_LEAST'?`au moins ${count.value}`:String(count.value);
}

/** Une relation dite comme un verbe ; son nom brut si le portail ne la connaît pas. */
export const verb=(relation:string)=>label(VERBS, relation);
/** Une référence lisible, son type compris ; brute si son type est inconnu. Le dépôt est nommé par son projet. */
export type Naming=(value:string)=>string;
export const naming=(project?:{id:string; name:string}):Naming=>value=>reference(value, project)??value;
export const nodeName=naming();
/** Le type d'une référence (`route`, `module`, …), ou son préfixe brut. */
export function nodeType(value:string){
  const at=value.indexOf(':');
  return at<0?'':value.slice(0, at);
}

/** Un décompte connu, entre parenthèses ; rien quand Taxo ne le sait pas. */
const counted=(count:Count)=>{
  const said=countText(count);
  return said?` (${said})`:'';
};

/** Le pas d'une coupure : sa relation, et son sens s'il est dit. */
function stepText(boundary:Boundary){
  if(!boundary.relation)return '';
  const side=boundary.direction?`, ${DIRECTIONS[boundary.direction]}`:'';
  return ` · ${verb(boundary.relation)}${side}`;
}

/** Une coupure de sélection en une phrase, avec son décompte s'il est connu. */
export function selectionText(boundary:Boundary){
  const said=SELECTION[boundary.reason]??`Non développé (${boundary.reason})`;
  return `${said}${counted(boundary.count)}${stepText(boundary)}`;
}

/** Ce que Taxo ne sait pas, ou ne peut pas savoir : jamais levé par un budget. */
export function knowledgeText(boundary:Boundary){
  const relation=boundary.relation?verb(boundary.relation):'';
  switch(boundary.reason){
  case 'NO_ANALYZER':return `Aucun analyseur exécuté ne produit « ${relation} » : Taxo n’en dit rien, ni présence ni absence.`;
  case 'ANALYSIS_INCOMPLETE':return `${label(EVALUATORS, boundary.producer??'')} n’a pas tout lu dans cette analyse.`;
  case 'NOT_ANALYSED':return `Pour « ${relation} », des langages présents ne sont lus par aucun analyseur : ${(boundary.languages??[]).join(', ')}.`;
  case 'LANGUAGES_UNKNOWN':return `Pour « ${relation} », les langages présents ne sont pas connus : des fichiers ont pu échapper à l’analyse.`;
  case 'LOCAL_COVERAGE_NOT_READ':return 'Trop de nœuds pour situer les zones non lues : elles restent dites pour l’analyse entière.';
  default:{
    const where=boundary.subject?nodeName(boundary.subject):'';
    const by=boundary.producer?` par ${label(EVALUATORS, boundary.producer)}`:'';
    return `Zone non lue${by} : ${where} (${label(COVERAGE, boundary.reason)}).`;
  }
  }
}

/** Où en est la vue, toutes Tuiles réunies : ce qu'elle montre, et combien de nœuds restent coupés. */
export function viewText(view:Pick<View, 'nodes'|'elements'|'selection'>){
  const shown=`${plural(view.elements.length, 'élément')}, ${plural(view.nodes.length, 'nœud')}.`;
  const cut=view.nodes.filter(node=>view.selection[node.reference]).length;
  return cut?`${shown} ${plural(cut, 'nœud')} à développer ou à poursuivre.`
    :`${shown} Aucune coupure : tout ce que les pas suivis atteignent depuis cette ancre est montré.`;
}

/** Les marques d'un nœud : sa coupure, ses zones non lues, les pas sans analyseur s'il est l'ancre. */
export function nodeMarks(node:ViewNode, selection:Boundary|undefined, knowledge:Boundary[]){
  const marks:string[]=[];
  if(!node.known)marks.push('inconnu de cette analyse');
  if(selection){
    marks.push(selection.continuation?`suite disponible${counted(selection.count)}`:'non développé');
  }
  if(knowledge.some(entry=>entry.scope==='NODE'&&entry.node===node.reference))marks.push('zone non lue');
  if(knowledge.some(entry=>entry.nature==='CONTEXT'&&entry.node===node.reference))marks.push('aucun analyseur pour un pas');
  return marks;
}

/** La portée de la vue, rappelée en tête : ce qui est montré, et d'où. */
export function scopeText(relations:string[], direction:Direction|'BOTH', depth:number){
  const followed=relations.length?relations.map(verb).join(', '):'aucune relation';
  return `Faits enregistrés de cette analyse · relations suivies : ${followed} · ${DIRECTIONS[direction]} · profondeur ${depth}.`;
}

/** Un élément dit en clair : sujet, verbe, objet. */
export const factText=(fact:{subject:string; relation:string; object?:string}, named:Naming=nodeName)=>
  [named(fact.subject), verb(fact.relation), endName(fact.object, named)].filter(Boolean).join(' ');

/** L'extrémité d'un fait : une référence nommée, une valeur littérale telle quelle, ou rien quand il n'a pas d'objet. */
export const endName=(value:string|undefined, named:Naming=nodeName)=>value===undefined?'':named(value);


/** Ce qu'une Tuile n'a pas transmis faute de place, et où le retrouver. */
export function notSentText(entry:NotSent){
  const count=entry.count??1;
  if(entry.what==='evidence_summary')return `Preuves résumées non transmises pour ${plural(count, 'élément')} : chacune se charge depuis son lien.`;
  if(entry.what==='local_coverage'){
    const zones=count>1?`${count} zones non lues sans place pour être situées`:'1 zone non lue sans place pour être située';
    return `Au moins ${zones} sur un nœud : ce que Taxo n’a pas lu reste dit pour l’analyse entière.`;
  }
  return `${count} ${entry.what} non transmis (${entry.reason}).`;
}

/** Le type d'une référence dit comme un stéréotype UML (TAXO-UI-06) : « route », « symbole »… ; brut s'il est inconnu. */
export function typeText(value:string){
  const type=nodeType(value);
  return TYPES[type]||type||'référence';
}

/** La teinte du type d'une référence (TAXO-UI-06, E7) ; neutre pour un type que le portail ne connaît pas. */
export const toneOf=(value:string)=>TONES[nodeType(value)]??'neutral';

/** Le nom d'une boîte en compartiments UML, lu dans sa clé selon le contrat des références (ARCHITECTURE § 5.3), pour
 * que le nom se lise en gras et son emplacement en gris, de la même façon dans chaque boîte :
 * - un symbole (`<langage>:<propriétaire>#<membre>`) : le propriétaire par son dernier segment, son espace de noms à
 *   part, puis le membre tel qu'écrit, paramètres compris ;
 * - une application (`<descripteur>#<nom>`) : son nom, son descripteur à part ;
 * - un fichier ou un dossier : son dernier segment, son dossier parent à part.
 * Une autre référence, ou une clé hors de ces formes, garde son nom entier. */
export function compartments(value:string, named:Naming=nodeName):{owner:string; context?:string; member?:string}{
  const at=value.indexOf(':'), type=value.slice(0, at), key=value.slice(at+1);
  const apart=(owner:string, context:string)=>({owner, ...(context?{context}:{})});
  if(type==='application'&&key.includes('#'))return apart(key.slice(key.lastIndexOf('#')+1), key.slice(0, key.lastIndexOf('#')));
  if((type==='file'||type==='directory')&&key.includes('/'))return apart(key.slice(key.lastIndexOf('/')+1), key.slice(0, key.lastIndexOf('/')));
  const language=key.indexOf(':');
  if(type!=='symbol'||language<0)return {owner:bareName(value, named)};
  const qualified=key.slice(language+1), hash=qualified.indexOf('#');
  const owner=hash<0?qualified:qualified.slice(0, hash), dot=owner.lastIndexOf('.');
  return {...apart(owner.slice(dot+1), dot>0?owner.slice(0, dot):''), ...(hash<0?{}:{member:qualified.slice(hash+1)})};
}

/** Le nom d'une référence sans son type, que l'en-tête de sa boîte dit déjà. */
export function bareName(value:string, named:Naming=nodeName){
  const said=named(value), word=TYPES[nodeType(value)];
  return word&&said.startsWith(`${word} `)?said.slice(word.length+1):said;
}

/** Le statut d'un fait en une lettre (O, D, V), brut s'il est inconnu. */
export const statusMark=(status:string|undefined)=>status?label(STATUS_MARKS, status):'';

/** Chaque statut distinct des occurrences d'un lien, dans leur ordre : un lien ×N dont les occurrences diffèrent les
 * montre tous, jamais le seul premier. */
export const linkMarks=(link:Link)=>[...new Set(link.elements.map(element=>statusMark(element.fact.status)).filter(Boolean))];
