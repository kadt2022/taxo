import {useEffect, useRef, useState, type FormEvent} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {diffFactsPath, linksFor} from './links';
import {CHANGE_LABELS, DiffView, type DiffFacts, type FactChange, type FileDiff} from './diff';
import {MiniaView, type MiniaAnswer} from './minia';
import {ConsultForm} from './consult';
import {ProjectNav, ProjectOverview, technologiesOf, type Scan} from './overview';
import {AnalysisDetails} from './details';
import {EVALUATORS, label} from './vocabulary';
import {AskTaxo} from './query';
import {apiUrl} from './api';
import {openStream} from './sse';
import {AnalysisProgress, analyzeProject, liveScan, pendingEvaluators, type Run} from './analysis';
import {ask as askMinia, askButton, MiniaProgress, questionInit, startMinia, type MiniaLive} from './minia-live';

type Project = {id:string; name:string; path:string};
type Commit = {sha:string; parents:string[]; author:string; authored_at:string; subject:string};
type ChangedFile = {path:string; status:string; old_path:string|null; additions:number|null; deletions:number|null; confidential:boolean};
type CommitDetail = {commit:Commit; parent:string|null; files:ChangedFile[]};
type Evaluation = {evaluator_id:string; producer_version:string; comparable:boolean; failures:string[]; changes:FactChange[]; unchanged_count:number; not_interpreted_before:string[]; not_interpreted_after:string[]};
type Impact = {commit:Commit; parent:string|null; evaluations:Evaluation[]};
const FILE_LABELS:Record<string,string>={ADDED:'Ajouté',MODIFIED:'Modifié',DELETED:'Supprimé',RENAMED:'Renommé',COPIED:'Copié',TYPE_CHANGED:'Type modifié'};

function HistoryPanel({projectId}:Readonly<{projectId:string}>){
  const [commits,setCommits]=useState<Commit[]>([]), [detail,setDetail]=useState<CommitDetail|null>(null);
  const [impact,setImpact]=useState<Impact|null>(null),  [fileDiff,setFileDiff]=useState<FileDiff|null>(null), [links,setLinks]=useState<DiffFacts|null>(null), [question,setQuestion]=useState(''), [live,setLive]=useState<MiniaLive<MiniaAnswer>|null>(null), [consulted,setConsulted]=useState(false), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const base=`/projects/${projectId}/history/commits`;
  // Seule la derniere demande peut modifier l'ecran : une reponse arrivee trop tard est ignoree.
  const latest=useRef(0);
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
    setBusy(true);setError('');setLive(null);
    try{await askMinia<MiniaAnswer>(()=>openStream(`/api${base}/${sha}/ask/stream`,questionInit({question,parent})),change=>{if(token===latest.current)setLive(l=>change(l??startMinia()));});}
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
      {commits.map(c=><tr key={c.sha} className={detail?.commit.sha===c.sha?'current':''}><td><button className="link" disabled={busy} onClick={()=>open(c.sha)}><code>{c.sha.slice(0,7)}</code></button>{c.parents.length>1&&<span className="muted"> fusion</span>}</td><td>{c.subject}</td><td>{c.author}</td><td>{date(c.authored_at)}</td></tr>)}
    </tbody></table></div>:consulted&&!error&&<p className="empty">Aucun commit dans ce dépôt.</p>}
    {detail&&<section className="commit-detail" aria-label="Fiche du commit">
      <h2>Commit <code>{detail.commit.sha.slice(0,12)}</code></h2>
      <dl>
        <div><dt>Message</dt><dd>{detail.commit.subject}</dd></div>
        <div><dt>Auteur</dt><dd>{detail.commit.author} · {date(detail.commit.authored_at)}</dd></div>
        <div><dt>Comparé à</dt><dd>{detail.parent?<code>{detail.parent.slice(0,12)}</code>:'aucun parent : commit racine'}{detail.commit.parents.length>1&&' (premier parent d’une fusion)'}</dd></div>
      </dl>
      <div className="table-wrap"><table><thead><tr><th>Fichier</th><th>Changement</th><th>+ / −</th></tr></thead><tbody>
        {detail.files.map(f=><tr key={f.path}><td><button className="link" disabled={busy} onClick={()=>compare(detail.commit.sha,f.path,detail.parent)} aria-pressed={fileDiff?.path===f.path&&fileDiff.commit===detail.commit.sha}><code>{f.old_path?`${f.old_path} → ${f.path}`:f.path}</code></button>{f.confidential&&<span className="muted"> · confidentiel, contenu jamais affiché</span>}</td><td>{FILE_LABELS[f.status]??f.status}</td><td>{f.additions===null?'binaire':`+${f.additions} / −${f.deletions}`}</td></tr>)}
      </tbody></table></div>
      {fileDiff&&fileDiff.commit===detail.commit.sha&&<>
        <DiffView diff={fileDiff} links={linksFor(links,fileDiff)}/>
        <button className="secondary relate" disabled={busy} onClick={()=>relate(fileDiff)}>Relier ce diff aux faits Taxo</button>
      </>}
      <button className="primary" disabled={busy} onClick={()=>understand(detail.commit.sha)}>{busy?'Analyse en cours…':'Ce que Taxo comprend de ce commit'}</button>
      <form className="ask-minia" onSubmit={e=>ask(e,detail.commit.sha,detail.parent)}>
        <label htmlFor="minia-question">Demander à Minia</label>
        <textarea id="minia-question" rows={2} maxLength={1000} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Que change ce commit, et est-ce risqué ?"/>
        <button type="submit" className="secondary" disabled={busy||!question.trim()}>{askButton(busy&&live!==null&&!live.result,'Demander à Minia')}</button>
      </form>
      {live?.result?.commit===detail.commit.sha?<MiniaView answer={live.result}/>:live&&!live.result&&<MiniaProgress live={live}/>}
    </section>}
    {impact&&impact.commit.sha===detail?.commit.sha&&<section className="impact" aria-label="Impact compris par Taxo">
      {impact.evaluations.map(e=><div key={e.evaluator_id}>
        <h2>Impact selon {label(EVALUATORS,e.evaluator_id)} <span className="muted">{e.evaluator_id} v{e.producer_version}</span></h2>
        {!e.comparable?<p role="alert" className="error">Comparaison impossible : l’analyse a échoué ({e.failures.join(' ; ')}). Taxo n’affiche aucun changement plutôt que d’en inventer.</p>:e.changes.length?<div className="table-wrap"><table><thead><tr><th>Changement</th><th>Sujet</th><th>Relation</th><th>Avant</th><th>Après</th><th>Statut</th></tr></thead><tbody>
          {e.changes.map(c=><tr key={c.change+c.subject+c.relation+(c.before??'')+(c.after??'')}><td>{CHANGE_LABELS[c.change]}</td><td><code>{c.subject}</code></td><td>{c.relation??c.kind}</td><td><code>{c.before??''}</code></td><td><code>{c.after??''}</code></td><td>{c.status}</td></tr>)}
        </tbody></table></div>:<p className="muted">Aucun fait changé parmi ceux que cet évaluateur sait produire.</p>}
        {e.comparable&&<footer>{e.unchanged_count.toLocaleString('fr-CA')} faits inchangés. {gaps('avant le commit',e.not_interpreted_before)} {gaps('après le commit',e.not_interpreted_after)} Seuls les faits que cet évaluateur sait produire sont comparés : l’absence de changement ici ne prouve pas l’absence de changement ailleurs.</footer>}
      </div>)}
    </section>}
  </section>;
}

async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch(apiUrl(path), init);
  if (!response.ok) {
    const body = await response.json().catch(()=>null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `La requête a échoué (${response.status}).`);
  }
  return response.json();
}
function App(){
  const [projects,setProjects]=useState<Project[]>([]), [selected,setSelected]=useState('');
  const [scans,setScans]=useState<Scan[]>([]), [scanId,setScanId]=useState('');
  const [name,setName]=useState(''), [path,setPath]=useState(''), [error,setError]=useState('');
  const [busy,setBusy]=useState(false), [loading,setLoading]=useState(true);
  const project=projects.find(p=>p.id===selected);
  const scan=scans.find(s=>s.id===scanId) ?? scans[0];
  useEffect(()=>{request<Project[]>('/projects').then(p=>{setProjects(p);setSelected(p[0]?.id??'');}).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[]);
  useEffect(()=>{
    let active=true;
    setScans([]);setScanId('');
    if(selected){setLoading(true);request<Scan[]>(`/projects/${selected}/scans`).then(s=>{if(active)setScans(s);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});}
    return ()=>{active=false;};
  },[selected]);
  async function add(event:FormEvent){
    event.preventDefault();setBusy(true);setError('');
    try{const p=await request<Project>('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,path})});setProjects(past=>[...past,p]);setSelected(p.id);setName('');setPath('');}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const [run,setRun]=useState<Run|null>(null);
  function analyze(){
    return analyzeProject(selected,{request, open:(url,last)=>openStream(url,last?{headers:{'Last-Event-ID':last}}:undefined), setRun, setError, setBusy, addScan:s=>{setScans(past=>[s,...past]);setScanId(s.id);}});
  }
  const running=run?.status==='running';
  const shown=running?liveScan(scan,run):scan;
  const legacyFacts=shown?.facts??[];
  const technologies=shown?technologiesOf(shown):[];
  return <div className="layout">
    <aside><a className="brand" href="/"><svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="3" y="3" width="26" height="26" rx="7"/><path d="M10 11h12M16 11v11"/></svg>Taxo<span>EXPLORATEUR LOGICIEL</span></a><h2>Projets <span>{projects.length}</span></h2>
    <nav aria-label="Projets">{projects.map(p=><button disabled={busy} aria-current={selected===p.id?'page':undefined} className={selected===p.id?'selected':''} key={p.id} onClick={()=>{setError('');setSelected(p.id);}}>{p.name}<span>↗</span></button>)}</nav>
    <details className="add-project" open={projects.length===0||undefined}><summary>Ajouter un projet</summary><form onSubmit={add}><label>Nom<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder="Mon application"/></label><label>Dossier local<input required value={path} onChange={e=>setPath(e.target.value)} placeholder="D:\MonProjet"/></label><button className="secondary" disabled={busy||loading}>Enregistrer le projet</button></form></details>
    <p className="aside-note">Analyse locale · v0.1<br/>Vos fichiers restent sur votre machine.</p></aside>
    <main><header><div><p className="eyebrow">PROJET</p><h1>{project?.name??'Votre logiciel, à découvert.'}</h1><p className="path">{project?.path??'Ajoutez un dossier pour découvrir les technologies de votre projet.'}</p></div><button className="primary" disabled={!selected||busy||loading} onClick={analyze}>{busy?'Analyse en cours…':'Lancer l’analyse globale'}</button></header>
    {selected&&!loading&&<ProjectNav scan={scan}/>}
    {error&&<div role="alert" className="error">{error}</div>}
    {run&&run.status!=='done'&&<AnalysisProgress run={run}/>}
    {loading?<p role="status">Chargement…</p>:shown?<>
      <ProjectOverview scan={shown} pending={running?pendingEvaluators(run):undefined}/>
      <section className="results" id="technologies"><div className="section-heading"><div><h2>Technologies</h2><p>Reconnues par les noms de fichiers et les dépendances déclarées ; une dépendance déclarée ne prouve pas qu’elle est utilisée.</p></div><label>Analyse du<select value={shown.id} onChange={e=>setScanId(e.target.value)}>{scans.map(s=><option key={s.id} value={s.id}>{new Date(s.created_at).toLocaleString('fr-CA')}</option>)}</select></label></div>
      {technologies.length?<div className="tags">{technologies.map(t=><span key={t}>{t}</span>)}</div>:<p className="empty">Aucune technologie reconnue dans ce dossier.</p>}
      {legacyFacts.length>0&&<details className="evidence-files"><summary>Fichiers justificatifs ({legacyFacts.length})</summary><div className="table-wrap"><table><thead><tr><th>Technologie</th><th>Fichier justificatif</th><th>Détection</th></tr></thead><tbody>{legacyFacts.map(f=><tr key={f.technology+f.file}><td>{f.technology}</td><td><code>{f.file}</code></td><td>{f.method==='manifest'?'Manifeste':'Nom de fichier'}</td></tr>)}</tbody></table></div></details>}
      </section>
      <AnalysisDetails scan={shown}/>
    </>:!running&&<section className="welcome"><div className="glyph">⌘</div><h2>{selected?'Prêt pour la première analyse':'Commencez avec un projet local'}</h2><p>{selected?'Lancez l’analyse globale : Taxo vous montrera ce qu’il comprend de votre projet, et ce qu’il ne sait pas encore déterminer.':'Enregistrez un dossier dans le panneau de gauche, puis lancez son analyse.'}</p><p className="muted">Java · TypeScript · Python · React · Spring Boot</p></section>}
    {selected&&!loading&&scan&&<AskTaxo key={selected} base={`/projects/${selected}`} request={request}/>}
    {selected&&!loading&&<HistoryPanel key={selected} projectId={selected}/>}
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
