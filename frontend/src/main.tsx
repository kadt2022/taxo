import {useEffect, useRef, useState, type FormEvent} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {diffFactsPath, linksFor} from './links';
import {CHANGE_LABELS, DiffView, type DiffFacts, type FactChange, type FileDiff} from './diff';
import {MiniaChoice, MiniaView, SourceConsent, sourceConsent, withProvider, type MiniaAnswer, type MiniaStatus} from './minia';
import {ConsultForm} from './consult';
import {impactSource, notComparable, type ImpactOrigin} from './history';
import {panelKey} from './overview';
import {EVALUATORS, label} from './vocabulary';
import {openStream} from './sse';
import {App, request} from './app';
import {ask as askMinia, askButton, createStop, MiniaProgress, questionInit, startMinia, type MiniaLive, type MiniaStop} from './minia-live';

type Commit = {sha:string; parents:string[]; author:string; authored_at:string; subject:string};
type ChangedFile = {path:string; status:string; old_path:string|null; additions:number|null; deletions:number|null; confidential:boolean};
type CommitDetail = {commit:Commit; parent:string|null; files:ChangedFile[]};
type Evaluation = {evaluator_id:string; producer_version:string; comparable:boolean; failures:string[]; changes:FactChange[]; unchanged_count:number; not_interpreted_before:string[]; not_interpreted_after:string[]};
type Impact = ImpactOrigin&{commit:Commit; parent:string|null; evaluations:Evaluation[]};
const FILE_LABELS:Record<string,string>={ADDED:'Ajouté',MODIFIED:'Modifié',DELETED:'Supprimé',RENAMED:'Renommé',COPIED:'Copié',TYPE_CHANGED:'Type modifié'};

function HistoryPanel({projectId, minia}:Readonly<{projectId:string; minia:MiniaStatus|null}>){
  const [commits,setCommits]=useState<Commit[]>([]), [detail,setDetail]=useState<CommitDetail|null>(null);
  const [impact,setImpact]=useState<Impact|null>(null),  [fileDiff,setFileDiff]=useState<FileDiff|null>(null), [links,setLinks]=useState<DiffFacts|null>(null), [question,setQuestion]=useState(''), [live,setLive]=useState<MiniaLive<MiniaAnswer>|null>(null), [consulted,setConsulted]=useState(false), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const base=`/projects/${projectId}/history/commits`;
  const [provider,setProvider]=useState(''), [source,setSource]=useState(false);
  const chosen=withProvider(minia,provider);
  // Un fournisseur distant decoche l'accord pour le diff ; un fournisseur local le coche.
  useEffect(()=>{setSource(sourceConsent(chosen)?.checked??false);},[chosen?.provider,chosen?.source_context]);
  // Seule la derniere demande peut modifier l'ecran : une reponse arrivee trop tard est ignoree.
  const latest=useRef(0);
  // Le moyen d'arreter la demande a Minia en cours (TAXO-UX-03).
  const stopper=useRef<MiniaStop|null>(null);
  // Changer de projet ou quitter le panneau arrete la demande a Minia en cours.
  useEffect(()=>()=>{stopper.current?.stop();stopper.current=null;},[base]);
  // Changer de projet efface la consultation : l'historique ne s'affiche que sur demande explicite.
  useEffect(()=>{
    setCommits([]);setConsulted(false);setDetail(null);setImpact(null);setFileDiff(null);setLinks(null);setLive(null);setError('');
  },[base]);
  async function load<T>(path:string, apply:(value:T)=>void, init?:RequestInit){
    const token=++latest.current;
    setBusy(true);setError('');
    try{const value=await request<T>(path,init);if(token===latest.current)apply(value);}
    catch(e){if(token===latest.current)setError((e as Error).message);}
    finally{if(token===latest.current)setBusy(false);}
  }
  function consult(path:string){
    setDetail(null);setImpact(null);setFileDiff(null);setLinks(null);setLive(null);
    return load<Commit[]>(path,c=>{setCommits(c);setConsulted(true);});
  }
  function open(sha:string){setImpact(null);setFileDiff(null);setLinks(null);setLive(null);return load<CommitDetail>(`${base}/${sha}`,setDetail);}
  function compare(sha:string,path:string,parent:string|null){
    const query=new URLSearchParams({path});if(parent)query.set('parent',parent);
    setLinks(null);
    return load<FileDiff>(`${base}/${sha}/diff?${query}`,setFileDiff);
  }
  function relate(diff:FileDiff){
    return load<DiffFacts>(diffFactsPath(base,diff),setLinks);
  }
  async function ask(event:FormEvent, sha:string, parent:string|null){
    event.preventDefault();
    const token=++latest.current;
    stopper.current?.stop();
    const run=createStop();
    stopper.current=run;
    setBusy(true);setError('');setLive(null);
    try{await askMinia<MiniaAnswer>(()=>openStream(`/api${base}/${sha}/ask/stream`,{...questionInit({question,parent,source_context:source&&sourceConsent(chosen)!==null,provider:provider||undefined}), signal:run.signal}),change=>{if(token===latest.current)setLive(l=>change(l??startMinia()));},run);}
    catch(e){if(token===latest.current)setError((e as Error).message);}
    finally{if(token===latest.current)setBusy(false);}
  }
  function understand(sha:string){return load<Impact>(`${base}/${sha}/impact`,setImpact);}
  const date=(value:string)=>new Date(value).toLocaleString('fr-CA');
  // Les deux cotes comptent : une zone non lue avant le commit rend la comparaison incomplete aussi.
  const gaps=(side:string,zones:string[])=>zones.length?`Zones non interprétées ${side} : ${zones.join(', ')}.`:`Aucune zone non interprétée ${side}.`;
  return <section className="results history" id="historique" aria-label="Historique">
    <div className="section-heading"><div><h2>Historique</h2><p>Les commits du dépôt Git, consultés sur demande : indiquez combien en afficher.</p></div>
      <ConsultForm base={base} busy={busy} onConsult={consult} onError={setError}/></div>
    {error&&<div role="alert" className="error">{error}</div>}
    {commits.length?<div className="table-wrap"><table><thead><tr><th>Commit</th><th>Message</th><th>Auteur</th><th>Date</th></tr></thead><tbody>
      {commits.map(c=><tr key={c.sha} className={detail?.commit.sha===c.sha?'current':''}><td><button type="button" className="link" disabled={busy} onClick={()=>open(c.sha)}><code>{c.sha.slice(0,7)}</code></button>{c.parents.length>1&&<span className="muted"> fusion</span>}</td><td>{c.subject}</td><td>{c.author}</td><td>{date(c.authored_at)}</td></tr>)}
    </tbody></table></div>:consulted&&!error&&<p className="empty">Aucun commit dans ce dépôt.</p>}
    {detail&&<section className="commit-detail" aria-label="Fiche du commit">
      <h2>Commit <code>{detail.commit.sha.slice(0,12)}</code></h2>
      <dl>
        <div><dt>Message</dt><dd>{detail.commit.subject}</dd></div>
        <div><dt>Auteur</dt><dd>{detail.commit.author} · {date(detail.commit.authored_at)}</dd></div>
        <div><dt>Comparé à</dt><dd>{detail.parent?<code>{detail.parent.slice(0,12)}</code>:'aucun parent : commit racine'}{detail.commit.parents.length>1&&' (premier parent d’une fusion)'}</dd></div>
      </dl>
      <div className="table-wrap"><table><thead><tr><th>Fichier</th><th>Changement</th><th>+ / −</th></tr></thead><tbody>
        {detail.files.map(f=><tr key={f.path}><td><button type="button" className="link" disabled={busy} onClick={()=>compare(detail.commit.sha,f.path,detail.parent)} aria-pressed={fileDiff?.path===f.path&&fileDiff.commit===detail.commit.sha}><code>{f.old_path?`${f.old_path} → ${f.path}`:f.path}</code></button>{f.confidential&&<span className="muted"> · confidentiel, contenu jamais affiché</span>}</td><td>{FILE_LABELS[f.status]??f.status}</td><td>{f.additions===null?'binaire':`+${f.additions} / −${f.deletions}`}</td></tr>)}
      </tbody></table></div>
      {fileDiff&&fileDiff.commit===detail.commit.sha&&<>
        <DiffView diff={fileDiff} links={linksFor(links,fileDiff)}/>
        <button type="button" className="secondary relate" disabled={busy} onClick={()=>relate(fileDiff)}>Relier ce diff aux faits Taxo</button>
      </>}
      <button type="button" className="primary" disabled={busy} onClick={()=>understand(detail.commit.sha)}>{busy?'Analyse en cours…':'Ce que Taxo comprend de ce commit'}</button>
      <form className="ask-minia" onSubmit={e=>ask(e,detail.commit.sha,detail.parent)}>
        <label htmlFor="minia-question">Demander à Minia</label>
        <textarea id="minia-question" rows={2} maxLength={1000} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Que change ce commit, et est-ce risqué ?"/>
        <MiniaChoice id="minia-provider" status={minia} value={provider} onChange={setProvider}/>
        <SourceConsent status={chosen} checked={source} onChange={setSource}/>
        <button type="submit" className="secondary" disabled={busy||!question.trim()}>{askButton(busy&&live!==null&&!live.result,'Demander à Minia')}</button>
      </form>
      {live?.result?.commit===detail.commit.sha?<MiniaView answer={live.result}/>:live&&!live.result&&<MiniaProgress live={live} onStop={()=>stopper.current?.stop()}/>}
    </section>}
    {impact&&impact.commit.sha===detail?.commit.sha&&<section className="impact" aria-label="Impact compris par Taxo">
      <p className="muted">{impactSource(impact)}</p>
      {impact.evaluations.map(e=><div key={e.evaluator_id}>
        <h2>Impact selon {label(EVALUATORS,e.evaluator_id)} <span className="muted">{e.evaluator_id} v{e.producer_version}</span></h2>
        {!e.comparable?<p role="alert" className="error">{notComparable(e.failures)}</p>:e.changes.length?<div className="table-wrap"><table><thead><tr><th>Changement</th><th>Sujet</th><th>Relation</th><th>Avant</th><th>Après</th><th>Statut</th></tr></thead><tbody>
          {e.changes.map(c=><tr key={c.change+c.subject+c.relation+(c.before??'')+(c.after??'')}><td>{CHANGE_LABELS[c.change]}</td><td><code>{c.subject}</code></td><td>{c.relation??c.kind}</td><td><code>{c.before??''}</code></td><td><code>{c.after??''}</code></td><td>{c.status}</td></tr>)}
        </tbody></table></div>:<p className="muted">Aucun fait changé parmi ceux que cet évaluateur sait produire.</p>}
        {e.comparable&&<footer>{e.unchanged_count.toLocaleString('fr-CA')} faits inchangés. {gaps('avant le commit',e.not_interpreted_before)} {gaps('après le commit',e.not_interpreted_after)} Seuls les faits que cet évaluateur sait produire sont comparés : l’absence de changement ici ne prouve pas l’absence de changement ailleurs.</footer>}
      </div>)}
    </section>}
  </section>;
}

createRoot(document.getElementById('root')!).render(<App history={(projectId, minia)=><HistoryPanel key={panelKey('history',projectId)} projectId={projectId} minia={minia}/>}/>);
