// Interroger Taxo (TAXO-QUERY-01) : la requete choisit parmi les faits deja produits par l'analyse globale ;
// Minia n'explique que cette selection. Les faits affiches sont ceux de Taxo, avec leur provenance.
import {useState, type FormEvent} from 'react';
import {typed} from './consult';

type Request = {kind:'GLOBAL'|'LATEST'|'COMMIT'|'PERIOD'; text:string; count:number|null; commit:string|null; since:string|null; until:string|null};
type SelectedCommit = {sha:string; authored_at?:string; subject?:string};
export type GitFact = {subject:string; relation:string; object:string; qualifiers?:Record<string,unknown>;
  produced_by?:{producer_id:string; producer_version:string}; evidence?:{object?:string; commit:string}[]};
export type Selection = {status:string; request:Request; analysis:{id:string; created_at:string};
  total_commits:number|null; commits:SelectedCommit[]; facts:GitFact[]; not_interpreted:string[]};
export type SelectionAnswer = {status:'ANSWERED'|'TAXO_KNOWS_NOTHING'|'NEEDS_SELECTION'; question:string; request:Request;
  model:{provider:string|null; model:string|null}; commits:SelectedCommit[]; facts:(GitFact&{ref:string})[];
  answer:string; unknown:string; not_interpreted:string[]; facts_not_sent:number; rejected_citations:string[]};
type Run = <T>(path:string, init?:RequestInit)=>Promise<T>;

/** La selection demandee, dite en clair. */
export function describe(request:Request){
  const period=request.since&&request.until?` du ${request.since} au ${request.until}`
    :request.since?` depuis le ${request.since}`:request.until?` jusqu’au ${request.until}`:'';
  if(request.kind==='LATEST')return `${request.count} dernier${request.count===1?'':'s'} commit${request.count===1?'':'s'}${period}`;
  if(request.kind==='COMMIT')return `commit ${request.commit}`;
  if(request.kind==='PERIOD')return `commits${period}`;
  return 'analyse globale du projet';
}

const STATUS:Record<string,string>={
  GLOBAL:'Requête globale : aucune sélection de commits. Les faits du projet sont ceux de l’analyse globale.',
  NOT_FOUND:'Aucun commit de l’historique analysé ne commence par cet identifiant.',
  AMBIGUOUS:'Plusieurs commits commencent par cet identifiant : donnez-en davantage de caractères.',
  NO_GIT_FACTS:'La dernière analyse globale ne contient pas de faits Git : relancez-la.'};

/** Message de la selection ; null quand des commits ont ete trouves. */
export function outcome(result:Selection){
  if(result.status==='SELECTED')return result.commits.length?null:'Aucun commit ne correspond à cette sélection.';
  return STATUS[result.status]??result.status;
}

/** Un fait Git en une ligne : sujet, relation, objet et qualificatifs utiles. */
export function factLine(fact:GitFact){
  const change=fact.qualifiers?.change, old=fact.qualifiers?.old_path;
  const detail=[change, old?`depuis ${old}`:null].filter(Boolean).join(', ');
  return `${fact.subject} ${fact.relation} ${fact.object}${detail?` (${detail})`:''}`;
}

const short=(sha:string)=>sha.slice(0,12);
/** Date lisible ; une valeur illisible est montree telle quelle. */
export const when=(value?:string)=>{const moment=new Date(value??'');return Number.isNaN(moment.getTime())?value??'':moment.toLocaleString('fr-CA');};

export function SelectionView({result}:Readonly<{result:Selection}>){
  const message=outcome(result);
  return <section className="selection" aria-label="Sélection de Taxo">
    <p className="eyebrow">REQUÊTE · {describe(result.request)}</p>
    {message&&<p className="empty">{message}</p>}
    {result.commits.length>0&&<div className="table-wrap"><table><thead><tr><th>Commit</th><th>Date</th><th>Message</th></tr></thead><tbody>
      {result.commits.map(c=><tr key={c.sha}><td><code>{short(c.sha)}</code></td><td>{when(c.authored_at)}</td><td>{c.subject??''}</td></tr>)}
    </tbody></table></div>}
    <p className="muted">{result.facts.length} faits sélectionnés{result.total_commits===null?'':` parmi un historique de ${result.total_commits} commits`} · analyse du {when(result.analysis.created_at)}.</p>
    {result.not_interpreted.length>0&&<p className="muted">Non interprété par Taxo : {result.not_interpreted.join(', ')}.</p>}
  </section>;
}

export function SelectionAnswerView({answer}:Readonly<{answer:SelectionAnswer}>){
  const limits=[answer.unknown, answer.facts_not_sent?`${answer.facts_not_sent} faits n’ont pas été transmis à Minia (limite de taille).`:'',
    answer.rejected_citations.length?`Références inventées par Minia et écartées : ${answer.rejected_citations.join(', ')}.`:''].filter(Boolean);
  return <section className="minia" aria-label="Réponse de Minia">
    <p className="eyebrow">MINIA{answer.model.model?` · ${answer.model.provider} ${answer.model.model}`:''} · {describe(answer.request)}</p>
    <p className="minia-question">{answer.question}</p>
    <div className="minia-blocks">
      <article className="minia-block fact">
        <h3>Fait Taxo</h3>
        {answer.facts.length?<ul>{answer.facts.map(f=><li key={f.ref}>{factLine(f)}<span className="muted"> · {f.produced_by?.producer_id}</span></li>)}</ul>
          :<p className="muted">Aucun fait de Taxo n’appuie cette réponse.</p>}
      </article>
      <article className="minia-block interpretation">
        <h3>Interprétation Minia <span className="badge">non vérifiée</span></h3>
        <p>{answer.answer||'Minia ne propose aucune interprétation.'}</p>
      </article>
      <article className="minia-block unknown">
        <h3>Inconnu / non interprété</h3>
        {limits.length?<ul>{limits.map(item=><li key={item}>{item}</li>)}</ul>:<p className="muted">Aucune limite signalée.</p>}
      </article>
    </div>
  </section>;
}

export const queryPath=(base:string, text:string)=>`${base}/query?${new URLSearchParams({q:text})}`;
export const askInit=(text:string):RequestInit=>({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:text})});

type Setters<T> = {setBusy:(value:boolean)=>void; setError:(value:string)=>void; setValue:(value:T)=>void};

/** Suit une demande : occupe pendant l'appel, puis la valeur ou le message d'erreur. */
export async function track<T>(pending:()=>Promise<T>, {setBusy, setError, setValue}:Setters<T>){
  setBusy(true);setError('');
  try{setValue(await pending());}
  catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
}

/** Soumission du formulaire : la page ne se recharge pas, l'action choisie est lancee. */
export const submitWith=(action:()=>unknown)=>(event:Pick<FormEvent,'preventDefault'>)=>{event.preventDefault();return action();};

type PanelSetters = {setBusy:(value:boolean)=>void; setError:(value:string)=>void;
  setResult:(value:Selection)=>void; setAnswer:(value:SelectionAnswer|null)=>void};

/** Les deux actions du panneau : selectionner des faits, ou demander a Minia d'expliquer la selection. */
export function actions(base:string, text:string, request:Run, set:PanelSetters){
  const common={setBusy:set.setBusy, setError:set.setError};
  return {
    select:()=>track(()=>request<Selection>(queryPath(base,text)), {...common, setValue:(value:Selection)=>{set.setResult(value);set.setAnswer(null);}}),
    explain:()=>track(()=>request<SelectionAnswer>(`${base}/ask`,askInit(text)), {...common, setValue:set.setAnswer}),
  };
}

export function AskTaxo({base, request}:Readonly<{base:string; request:Run}>){
  const [text,setText]=useState(''), [busy,setBusy]=useState(false), [error,setError]=useState('');
  const [result,setResult]=useState<Selection|null>(null), [answer,setAnswer]=useState<SelectionAnswer|null>(null);
  const {select,explain}=actions(base,text,request,{setBusy,setError,setResult,setAnswer});
  return <section className="results ask-taxo" aria-label="Interroger Taxo">
    <div className="section-heading"><div><h2>Interroger Taxo</h2><p>Taxo sélectionne parmi les faits de la dernière analyse globale : « les 3 derniers commits », « le commit 5b9022b », « depuis 2026-09-01 ».</p></div></div>
    <form onSubmit={submitWith(select)}>
      <label htmlFor="taxo-query">Votre requête</label>
      <input id="taxo-query" required maxLength={1000} value={text} onChange={typed(setText)} placeholder="les 3 derniers commits"/>
      <div className="actions"><button type="submit" className="secondary" disabled={busy}>Sélectionner</button>
        <button type="button" className="secondary" disabled={busy||!text.trim()} onClick={explain}>Demander à Minia</button></div>
    </form>
    {error&&<div role="alert" className="error">{error}</div>}
    {answer?<SelectionAnswerView answer={answer}/>:result&&<SelectionView result={result}/>}
  </section>;
}
