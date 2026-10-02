// Le resultat d'une comparaison par domaine (TAXO-01F, tranche D). Le serveur compte chaque categorie par relation,
// evaluateur par evaluateur ; ce module ne fait que ranger ces comptes dans un domaine et les dire en phrases. Il ne
// compare rien, n'additionne pas deux evaluateurs, et n'invente ni pourcentage ni impact.
import type {ComparisonSummary, EvaluatorEntry} from './comparison';
import {EVALUATORS, label} from './vocabulary';

export const DOMAINS=[
  {id:'api', label:'API', icon:'⇄'},
  {id:'securite', label:'Sécurité', icon:'⛨'},
  {id:'architecture', label:'Architecture', icon:'▦'},
  {id:'technologies', label:'Technologies', icon:'◈'},
  {id:'fichiers', label:'Fichiers', icon:'▤'},
  {id:'git', label:'Git', icon:'⎇'},
  {id:'autres', label:'Autres faits', icon:'…'},
] as const;
export type DomainId=typeof DOMAINS[number]['id'];

/** Le domaine de chaque relation ; `CONTAINS` depend de qui la produit (un module du depot, ou un fichier). */
const BY_RELATION:Record<string, DomainId>={HANDLED_BY:'api', SERVED_BY:'api',
  PROTECTED_BY:'securite', PERMITS_ALL:'securite', AUTHORIZED_BY:'securite', MATCHED_BY:'securite',
  DEPENDS_ON:'architecture', BUILT_FROM:'architecture',
  USES_TECHNOLOGY:'technologies', DECLARED_BY:'technologies', WRITTEN_IN:'fichiers', CONTAINS:'fichiers',
  HAS_COMMIT:'git', AUTHORED_BY:'git', CHILD_OF:'git', CHANGES:'git'};
/** Les domaines que chaque evaluateur peut renseigner : un domaine sans evaluateur compare est « non analyse ». */
const BY_EVALUATOR:Record<string, DomainId[]>={'taxo.spring-api':['api'], 'taxo.spring-boot':['api', 'architecture'],
  'taxo.spring-security':['securite'], 'taxo.structure':['architecture'], 'taxo.inventory':['technologies', 'fichiers'],
  'taxo.git':['git']};

export function domainOf(evaluator:string, relation:string):DomainId{
  if(relation==='CONTAINS'&&evaluator==='taxo.structure')return 'architecture';
  return BY_RELATION[relation]??BY_EVALUATOR[evaluator]?.[0]??'autres';
}
const domainsOf=(evaluator:string)=>BY_EVALUATOR[evaluator]??['autres'];

/** Ce que compte une relation : un nom, son pluriel, son genre. */
type Noun={one:string; many:string; feminine?:boolean};
const NOUNS:Record<string, Noun>={
  'taxo.structure|CONTAINS':{one:'module du dépôt', many:'modules du dépôt'},
  CONTAINS:{one:'fichier', many:'fichiers'},
  WRITTEN_IN:{one:'identification de langage', many:'identifications de langage', feminine:true},
  USES_TECHNOLOGY:{one:'technologie', many:'technologies', feminine:true},
  DECLARED_BY:{one:'déclaration de technologie', many:'déclarations de technologie', feminine:true},
  HAS_COMMIT:{one:'commit', many:'commits'},
  AUTHORED_BY:{one:'auteur de commit', many:'auteurs de commit'},
  CHILD_OF:{one:'lien entre commits', many:'liens entre commits'},
  CHANGES:{one:'modification de fichier', many:'modifications de fichier', feminine:true},
  HANDLED_BY:{one:'route', many:'routes', feminine:true},
  SERVED_BY:{one:'rattachement de route à une application', many:'rattachements de route à une application'},
  PROTECTED_BY:{one:'protection de route', many:'protections de route', feminine:true},
  PERMITS_ALL:{one:'route ouverte à tous', many:'routes ouvertes à tous', feminine:true},
  AUTHORIZED_BY:{one:'règle de sécurité', many:'règles de sécurité', feminine:true},
  MATCHED_BY:{one:'correspondance de route à un motif', many:'correspondances de route à un motif', feminine:true},
  DEPENDS_ON:{one:'dépendance entre modules', many:'dépendances entre modules', feminine:true},
  BUILT_FROM:{one:'composition d’application', many:'compositions d’application', feminine:true},
};
const nounOf=(evaluator:string, relation:string):Noun=>NOUNS[`${evaluator}|${relation}`]??NOUNS[relation]
  ??{one:`fait « ${relation} »`, many:`faits « ${relation} »`};

const agreed=(participle:string, noun:Noun, count:number)=>`${participle}${noun.feminine?'e':''}${count>1?'s':''}`;
/** La fin de phrase de chaque categorie ; les signaux disent ce qui a change sur un fait reste le meme. */
const TAILS:Record<string, (noun:Noun, count:number)=>string>={
  ADDED:(noun, count)=>agreed('ajouté', noun, count),
  REMOVED:(noun, count)=>agreed('disparu', noun, count),
  MODIFIED:(noun, count)=>agreed('modifié', noun, count),
  EVIDENCE_CHANGED:()=>'dont la preuve a changé de place',
  STATUS_CHANGED:()=>'dont le statut a changé',
  OCCURRENCE_COUNT_CHANGED:(noun, count)=>`${agreed('relevé', noun, count)} un nombre de fois différent`,
  OCCURRENCES_CHANGED:()=>'dont les apparitions disent autre chose',
};
export const ORDER=Object.keys(TAILS);

/** « 4 routes ajoutées », « 1 règle de sécurité modifiée ». */
export function phrase(evaluator:string, relation:string, category:string, count:number){
  const noun=nounOf(evaluator, relation);
  return `${count.toLocaleString('fr-FR')} ${count>1?noun.many:noun.one} ${(TAILS[category]??(()=>category))(noun, count)}`;
}

/** Une ligne d'un domaine : un compte du serveur, pour un evaluateur, une relation et une categorie. */
export type Line={key:string; evaluator:string; relation:string; category:string; count:number; text:string; source?:string};
export type DomainResult={id:DomainId; label:string; icon:string; state:'changed'|'unchanged'|'refused'|'absent';
  lines:Line[]; reasons:{evaluator:string; message:string}[]};

/** Les comptes du serveur, ranges par domaine ; un domaine sans evaluateur compare le dit, sans rien supposer. */
export function byDomain(summary:Pick<ComparisonSummary, 'evaluators'>):DomainResult[]{
  const lines=new Map<DomainId, Line[]>(), compared=new Set<DomainId>(), refused=new Map<DomainId, EvaluatorEntry[]>();
  for(const entry of summary.evaluators){
    if(!entry.comparable){
      for(const id of domainsOf(entry.evaluator_id))refused.set(id, [...refused.get(id)??[], entry]);
      continue;
    }
    for(const id of domainsOf(entry.evaluator_id))compared.add(id);
    for(const [relation, counts] of Object.entries(entry.relations??{})){
      const id=domainOf(entry.evaluator_id, relation);
      compared.add(id);
      for(const category of ORDER){
        const count=counts[category]??0;
        if(!count)continue;
        lines.set(id, [...lines.get(id)??[], {key:`${entry.evaluator_id}|${relation}|${category}`, evaluator:entry.evaluator_id,
          relation, category, count, text:phrase(entry.evaluator_id, relation, category, count)}]);
      }
    }
  }
  return DOMAINS.map(domain=>{
    const found=(lines.get(domain.id)??[]).sort((left, right)=>ORDER.indexOf(left.category)-ORDER.indexOf(right.category)
      ||left.text.localeCompare(right.text, 'fr'));
    // Deux evaluateurs qui disent la meme phrase ne sont jamais additionnes : chacun est nomme.
    const shown=found.map(line=>found.some(other=>other!==line&&other.text===line.text)
      ?{...line, source:label(EVALUATORS, line.evaluator)}:line);
    const reasons=(refused.get(domain.id)??[]).map(entry=>({evaluator:label(EVALUATORS, entry.evaluator_id), message:entry.message??''}));
    let state:DomainResult['state']='absent';
    if(shown.length)state='changed';
    else if(compared.has(domain.id))state='unchanged';
    else if(reasons.length)state='refused';
    return {...domain, state, lines:shown, reasons};
  }).filter(domain=>domain.id!=='autres'||domain.state==='changed'||domain.state==='refused');
}
