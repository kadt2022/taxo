// Minia interroge Taxo (MINIA-09, ADR 0009) : chaque affirmation de Minia est affichee avec le verdict de Taxo,
// chaque interpretation comme non verifiee ; la trajectoire (operations demandees) reste visible.
import {factLine, type GitFact} from './query';
import {reference, VERBS, label} from './vocabulary';

type ProtocolError = {code:string; message:string};
type NotSent = {what:string; count?:number; reason:string};
export type TrajectoryStep = {operation:string; arguments:Record<string,string>; outcome:'OK'|'ERROR'; bytes:number;
  items?:number; not_sent?:NotSent[]; verdict?:string; reason?:string|null; error?:ProtocolError;
  // Champs du tour que l'operation ne lit pas : ignores par Taxo, et dits (MINIA-09c).
  ignored?:string[]};
type Claim = {subject:string; relation:string; object?:string};
type Location = {path?:string; line_start?:number; line_end?:number; object?:string; method?:string};
type Proof = {ref:string; fact:string; location:Location};
export type Statement =
  | {type:'interpretation'|'unknown'; text:string}
  | {type:'claim'; text:string; claim:Claim; verdict:string|null; reason?:string|null; error?:ProtocolError;
      facts?:{ref:string; fact:GitFact; evidence_count:number}[]; evidence?:Proof[]};

const VERDICTS:Record<string,string>={CONFIRMED:'Confirmée par Taxo', REFUTED:'Contredite par Taxo', NOT_PROVEN:'Non prouvée'};
const REASONS:Record<string,string>={NOT_FOUND_IN_ANALYSED_SCOPE:'Taxo a cherché là où il analyse et n’a rien établi',
  NOT_INTERPRETED:'Taxo a vu cette zone sans savoir la lire', NOT_ANALYSED:'aucun analyseur de Taxo ne couvre encore cette dimension'};
const OPERATIONS:Record<string,string>={describe:'Ce que Taxo sait servir', find_facts:'Recherche de faits',
  get_evidence:'Preuves d’un fait', get_coverage:'Couverture', get_commit:'Commit', get_diff:'Diff d’un fichier',
  verify_claim:'Vérification d’une affirmation'};

/** Le verdict de Taxo en clair ; une affirmation que Taxo n'a pas pu verifier le dit. */
export function verdictText(statement:Extract<Statement,{type:'claim'}>){
  if(statement.verdict===null)return `Non vérifiable : ${statement.error?.message??'Taxo n’a pas pu la vérifier.'}`;
  const text=VERDICTS[statement.verdict]??statement.verdict;
  return statement.reason?`${text} : ${REASONS[statement.reason]??statement.reason}`:text;
}

/** L'affirmation structuree, telle que Taxo l'a verifiee. */
export const claimText=(claim:Claim)=>
  [reference(claim.subject), label(VERBS,claim.relation), claim.object?reference(claim.object):null].filter(Boolean).join(' ');

/** Une etape de la trajectoire en une ligne : l'operation, ses arguments, l'issue. */
export function stepText(step:TrajectoryStep){
  const name=OPERATIONS[step.operation]??step.operation;
  const args=Object.entries(step.arguments).map(([key,value])=>`${key} ${value}`).join(', ');
  const outcome=step.outcome==='ERROR'?`refusé (${step.error?.code})`
    :step.verdict?(VERDICTS[step.verdict]??step.verdict)
    :`${step.items??0} résultat${(step.items??0)>1?'s':''}`;
  const cut=(step.not_sent??[]).reduce((total,item)=>total+(item.count??1),0);
  const ignored=step.ignored?.length?` · ignorés : ${step.ignored.join(', ')}`:'';
  return `${name}${args?` (${args})`:''} → ${outcome}${cut?`, ${cut} non transmis`:''} · ${step.bytes} octets${ignored}`;
}

/** Ou se trouve une preuve : fichier et lignes, ou objet Git ; la methode d'extraction entre parentheses. */
export function proofText(location:Location){
  const where=location.path?(location.line_start===undefined?location.path
    :`${location.path}:${location.line_start}${location.line_end!==undefined&&location.line_end!==location.line_start?`-${location.line_end}`:''}`)
    :location.object?reference(location.object):'emplacement non précisé';
  return location.method?`${where} (${location.method})`:where;
}

const verdictClass=(verdict:string|null)=>`verdict verdict-${(verdict??'none').toLowerCase().replaceAll('_','-')}`;

export function Trajectory({steps}:Readonly<{steps:TrajectoryStep[]}>){
  if(!steps.length)return null;
  return <details className="trajectory"><summary>Chemin de Minia : {steps.length} opération{steps.length>1?'s':''} demandée{steps.length>1?'s':''} à Taxo</summary>
    <ol>{steps.map((step,index)=><li key={index} className={step.outcome==='ERROR'?'refused':undefined}>{stepText(step)}</li>)}</ol>
  </details>;
}

export function Statements({statements}:Readonly<{statements:Statement[]}>){
  const claims=statements.filter((item):item is Extract<Statement,{type:'claim'}>=>item.type==='claim');
  const interpretations=statements.filter(item=>item.type==='interpretation');
  const unknowns=statements.filter(item=>item.type==='unknown');
  return <div className="minia-blocks">
    <article className="minia-block fact">
      <h3>Affirmations vérifiées par Taxo</h3>
      {claims.length?<ul>{claims.map((item,index)=><li key={index}>
        <span className={verdictClass(item.verdict)}>{verdictText(item)}</span> {item.text}
        <details className="proof"><summary>Ce que Taxo a vérifié</summary>{claimText(item.claim)}
          {item.facts?.length?<ul>{item.facts.map(f=><li key={f.ref}>{factLine(f.fact)}
            {(item.evidence??[]).filter(proof=>proof.fact===f.ref).map(proof=><span className="evidence" key={proof.ref}>{proofText(proof.location)}</span>)}
          </li>)}</ul>:null}
        </details></li>)}</ul>:<p className="muted">Minia n’a fait aucune affirmation à vérifier.</p>}
    </article>
    <article className="minia-block interpretation">
      <h3>Ce que Minia en déduit <span className="badge">non vérifié</span></h3>
      {interpretations.length?<ul>{interpretations.map((item,index)=><li key={index}>{item.text}</li>)}</ul>
        :<p className="muted">Minia ne propose aucune interprétation.</p>}
    </article>
    <article className="minia-block unknown">
      <h3>Ce que Taxo ne sait pas</h3>
      {unknowns.length?<ul>{unknowns.map((item,index)=><li key={index}>{item.text}</li>)}</ul>:<p className="muted">Aucune limite signalée.</p>}
    </article>
  </div>;
}
