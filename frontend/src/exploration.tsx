// Minia interroge Taxo (MINIA-09, ARCHITECTURE § 12) : chaque affirmation de Minia est affichee avec le verdict de Taxo,
// chaque interpretation comme non verifiee ; la trajectoire (operations demandees) reste visible.
import {factLine, type Derivation, type GitFact} from './query';
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
      facts?:{ref:string; fact:GitFact; evidence_count:number}[]; evidence?:Proof[]; limits?:Limit[];
      not_sent?:{what:string; count:number; reason:string}[]};
/** Ce que Taxo n'a pas su lire sur le sujet ou l'objet d'une affirmation (TAXO-MINIA-SEC-01) : le verdict n'en dit rien. */
export type Limit = {subject:string; type:string; producer:string|null; reason:string|null};

const VERDICTS:Record<string,string>={CONFIRMED:'Confirmée par Taxo', REFUTED:'Contredite par Taxo', NOT_PROVEN:'Non prouvée'};
const REASONS:Record<string,string>={NOT_FOUND_IN_ANALYSED_SCOPE:'Taxo a cherché là où il analyse et n’a rien établi',
  NOT_INTERPRETED:'Taxo a vu cette zone sans savoir la lire', NOT_ANALYSED:'aucun analyseur de Taxo ne couvre encore cette dimension'};
const OPERATIONS:Record<string,string>={describe:'Ce que Taxo sait servir', find_facts:'Recherche de faits',
  get_evidence:'Preuves d’un fait', get_coverage:'Couverture', get_commit:'Commit', get_diff:'Diff d’un fichier',
  verify_claim:'Vérification d’une affirmation'};

/** Le verdict de Taxo en clair ; une affirmation que Taxo n'a pas pu verifier le dit. */
export function verdictText(statement:Extract<Statement,{type:'claim'}>){
  if(statement.verdict===null)return `Non vérifiable : ${statement.error?.message??'Taxo n’a pas pu la vérifier.'}`;
  const inferred=statement.verdict==='CONFIRMED'&&statement.facts?.some(item=>item.fact.status==='INFERRED');
  // Une confirmation qui repose sur une deduction de Taxo le dit : elle n'a pas la force d'une observation.
  const base=inferred?'Confirmée par Taxo, par déduction':VERDICTS[statement.verdict]??statement.verdict;
  // Une confirmation ne couvre pas ce que Taxo n'a pas su lire : elle le dit, au lieu de paraitre complete.
  const text=limited(statement)?`${base}, avec limites`:base;
  return statement.reason?`${text} : ${REASONS[statement.reason]??statement.reason}`:text;
}

/** Les limites qu'une reponse n'a pas pu transmettre faute de place : elles existent, Taxo les compte. */
const unsentLimits=(statement:Extract<Statement,{type:'claim'}>)=>
  statement.not_sent?.filter(item=>item.what==='limits').reduce((total,item)=>total+item.count,0)??0;

/** Une confirmation qui ne couvre pas tout : des limites jointes, ou comptees sans place pour les dire. */
const limited=(statement:Extract<Statement,{type:'claim'}>)=>
  statement.verdict==='CONFIRMED'&&(Boolean(statement.limits?.length)||unsentLimits(statement)>0);

const unsentText=(count:number)=>count>1?`Taxo connaît ${count} autres limites, non transmises faute de place.`
  :'Taxo connaît une autre limite, non transmise faute de place.';

const UNREAD:Record<string,string>={NOT_INTERPRETED:'zone non interprétée', READ_ERROR:'fichier illisible'};

/** Une limite en une phrase : ce qui n'a pas ete lu, et ou ; sans raison, son type le dit. */
export const limitText=(limit:Limit)=>`${limit.reason??UNREAD[limit.type]??limit.type} (${reference(limit.subject)})`;

/** Une deduction de Taxo, premisse par premisse (ARCHITECTURE § 12) : ce qui la fonde, et ce qu'elle ne sait pas. */
export function DerivationView({derivation}:Readonly<{derivation:Derivation}>){
  return <div className="derivation">
    <p>Déduit par Taxo, règle <code>{derivation.rule}</code>, à partir de :</p>
    <ul>{derivation.premises.map(item=><li key={`p:${item}`}>{item}</li>)}</ul>
    {derivation.counter_examples_checked.length?<><p>Écarté :</p>
      <ul>{derivation.counter_examples_checked.map(item=><li key={`c:${item}`}>{item}</li>)}</ul></>:null}
    {derivation.known_gaps.length?<><p>Limites connues :</p>
      <ul>{derivation.known_gaps.map(item=><li key={`g:${item}`}>{item}</li>)}</ul></>:null}
  </div>;
}

/** L'affirmation structuree, telle que Taxo l'a verifiee. */
export const claimText=(claim:Claim)=>
  [reference(claim.subject), label(VERBS,claim.relation), claim.object?reference(claim.object):null].filter(Boolean).join(' ');

/** L'affirmation dite par Taxo, en une phrase : c'est elle, et elle seule, qui porte le verdict (MINIA-11). */
export function claimSentence(claim:Claim){
  const text=claimText(claim);
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
}

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

const verdictClass=(statement:Extract<Statement,{type:'claim'}>)=>limited(statement)
  ?'verdict verdict-limited':`verdict verdict-${(statement.verdict??'none').toLowerCase().replaceAll('_','-')}`;

export function Trajectory({steps}:Readonly<{steps:TrajectoryStep[]}>){
  if(!steps.length)return null;
  return <details className="trajectory"><summary>Chemin de Minia : {steps.length} opération{steps.length>1?'s':''} demandée{steps.length>1?'s':''} à Taxo</summary>
    <ol>{steps.map((step,index)=><li key={index} className={step.outcome==='ERROR'?'refused':undefined}>{stepText(step)}</li>)}</ol>
  </details>;
}

/** Les enonces de Minia, separes selon qui en repond (MINIA-11).
 * - Vert : seulement les affirmations structurees que Taxo a verifiees, dites par Taxo. La phrase de Minia n'y
 *   figure jamais : un verdict ne couvre que ce qui a ete verifie, pas une formulation qui irait au-dela.
 * - Bleu : tout ce que Minia ecrit, non verifie : ses interpretations, sa formulation de chaque affirmation, et
 *   ce qu'elle dit ne pas savoir.
 * - Jaune : seulement ce que Taxo constate lui-meme (`limits`). */
export function Statements({statements, limits=[]}:Readonly<{statements:Statement[]; limits?:string[]}>){
  const all=statements.filter((item):item is Extract<Statement,{type:'claim'}>=>item.type==='claim');
  // Seule une affirmation a laquelle Taxo a rendu un verdict entre en vert ; une affirmation qu'il n'a pas pu
  // verifier (mal formee, au-dela de la limite) reste un texte de Minia, sans reformulation par Taxo.
  const claims=all.filter(item=>item.verdict!==null);
  const unchecked=all.filter(item=>item.verdict===null);
  const interpretations=statements.filter(item=>item.type==='interpretation');
  const worded=claims.filter(item=>item.text.trim());
  const unknowns=statements.filter(item=>item.type==='unknown');
  const said=interpretations.length+worded.length+unchecked.length+unknowns.length;
  return <div className="minia-blocks">
    <article className="minia-block fact">
      <h3>Affirmations vérifiées par Taxo</h3>
      {claims.length?<ul>{claims.map((item,index)=><li key={index}>
        <span className={verdictClass(item)}>{verdictText(item)}</span> {claimSentence(item.claim)}
        {item.limits?.length?<ul className="claim-limits">{item.limits.map(limit=><li key={`${limit.subject}:${limit.reason}`}>
          Taxo n’a pas lu : {limitText(limit)}</li>)}</ul>:null}
        {unsentLimits(item)?<p className="claim-limits">{unsentText(unsentLimits(item))}</p>:null}
        <details className="proof"><summary>Ce que Taxo a vérifié</summary>
          <dl className="verified-claim">
            <div><dt>subject</dt><dd><code>{item.claim.subject}</code></dd></div>
            <div><dt>relation</dt><dd><code>{item.claim.relation}</code></dd></div>
            <div><dt>object</dt><dd><code>{item.claim.object??'—'}</code></dd></div>
            <div><dt>verdict</dt><dd><code>{item.verdict??'—'}</code>{item.reason?<> · <code>{item.reason}</code></>:null}</dd></div>
          </dl>
          {item.facts?.length?<ul>{item.facts.map(f=><li key={f.ref}>{factLine(f.fact)}
            {(item.evidence??[]).filter(proof=>proof.fact===f.ref).map(proof=><span className="evidence" key={proof.ref}>{proofText(proof.location)}</span>)}
            {f.fact.status==='INFERRED'&&f.fact.derivation?<DerivationView derivation={f.fact.derivation}/>:null}
          </li>)}</ul>:<p className="muted">Aucune preuve : Taxo n’a établi aucun fait pour cette affirmation.</p>}
        </details></li>)}</ul>:<p className="muted">Minia n’a fait aucune affirmation à vérifier.</p>}
    </article>
    <article className="minia-block interpretation">
      <h3>Ce que Minia en déduit <span className="badge">non vérifié</span></h3>
      {said?<ul>
        {interpretations.map(item=><li key={`i:${item.text}`}>{item.text}</li>)}
        {worded.map(item=><li key={`c:${item.text}:${claimText(item.claim)}`}>Minia : « {item.text} » <span className="muted">(sa formulation ;
          Taxo n’a vérifié que : {claimSentence(item.claim)})</span></li>)}
        {unchecked.map(item=><li key={`n:${item.text}:${claimText(item.claim)}`}>Minia : « {item.text||'(affirmation sans texte)'} » <span className="muted">
          ({verdictText(item)})</span></li>)}
        {unknowns.map(item=><li key={`u:${item.text}`}><em>Minia dit ne pas savoir :</em> {item.text}</li>)}
      </ul>:<p className="muted">Minia ne propose aucune interprétation.</p>}
    </article>
    <article className="minia-block unknown">
      <h3>Ce que Taxo ne sait pas</h3>
      {limits.length?<ul>{limits.map(item=><li key={item}>{item}</li>)}</ul>:<p className="muted">Aucune limite signalée par Taxo.</p>}
    </article>
  </div>;
}
