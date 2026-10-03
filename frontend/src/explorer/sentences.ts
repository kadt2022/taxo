// Ce que l'explorateur dit (TAXO-01J § 9) : chaque frontière, chaque marque, la portée de la vue. Pur. Des comptes,
// jamais de pourcentage ; jamais « complet » : une vue montre ce que ses pas atteignent, pas tout le logiciel. Un type
// ou une relation que le portail ne connaît pas s'affiche par son nom brut.
import {COVERAGE, EVALUATORS, VERBS, label, reference} from '../vocabulary';
import type {Boundary, Count, Direction, NotSent} from './protocol';
import type {View, ViewNode} from './graph';

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

/** Une coupure de sélection en une phrase, avec son décompte s'il est connu. */
export function selectionText(boundary:Boundary){
  const said=SELECTION[boundary.reason]??`Non développé (${boundary.reason})`;
  const count=countText(boundary.count);
  const step=boundary.relation?` · ${verb(boundary.relation)}${boundary.direction?`, ${DIRECTIONS[boundary.direction]}`:''}`:'';
  return `${said}${count?` (${count})`:''}${step}`;
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
    const count=countText(selection.count);
    marks.push(selection.continuation?`suite disponible${count?` (${count})`:''}`:'non développé');
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
  if(entry.what==='local_coverage')return `Au moins ${plural(count, 'zone non lue')} sans place pour être ${count>1?'situées':'située'} sur un nœud : ce que Taxo n’a pas lu reste dit pour l’analyse entière.`;
  return `${count} ${entry.what} non transmis (${entry.reason}).`;
}
