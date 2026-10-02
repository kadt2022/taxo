import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {diffFactsPath, linksFor} from './links';
import {CHANGE_LABELS, DiffView, type DiffFacts, type FactChange, type FileDiff} from './diff';
import {MiniaChoice, MiniaView, SourceConsent, sourceConsent, withProvider, type MiniaAnswer, type MiniaStatus} from './minia';
import {ConsultForm} from './consult';
import {AnalysisLimits, overviewCards, panelKey, ProjectOverview, routeCounts, technologiesOf, type RouteCounts, type Scan} from './overview';
import {AnalysisDetails} from './details';
import {CompareLauncher, ComparisonView, type Side} from './comparison';
import {ComparePicker} from './picker';
import {ProjectPicker, ResultsNav, TopMenu, resultItemsOf, since, type Project} from './shell';
import {EVALUATORS, label} from './vocabulary';
import {AskTaxo} from './query';
import {RoutesPanel} from './routes';
import {apiUrl} from './api';
import {openStream} from './sse';
import {AnalysisProgress, Working, analyzeProject, liveScan, pendingEvaluators, type Run} from './analysis';
import {ask as askMinia, askButton, createStop, MiniaProgress, questionInit, startMinia, type MiniaLive, type MiniaStop} from './minia-live';

type Commit = {sha:string; parents:string[]; author:string; authored_at:string; subject:string};
type ChangedFile = {path:string; status:string; old_path:string|null; additions:number|null; deletions:number|null; confidential:boolean};
type CommitDetail = {commit:Commit; parent:string|null; files:ChangedFile[]};
type Evaluation = {evaluator_id:string; producer_version:string; comparable:boolean; failures:string[]; changes:FactChange[]; unchanged_count:number; not_interpreted_before:string[]; not_interpreted_after:string[]};
type Impact = {commit:Commit; parent:string|null; evaluations:Evaluation[]};
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
/** Ce que la comparaison dit d'une analyse : son instantane, tel que le resume de l'analyse le rapporte. */
function sideOf(scan:Scan):Side{
  return {id:scan.id, created_at:scan.created_at, snapshot:scan.evaluation_summary?.snapshot??scan.snapshot??null};
}

function App(){
  const [projects,setProjects]=useState<Project[]>([]), [selected,setSelected]=useState('');
  const [minia,setMinia]=useState<MiniaStatus|null>(null);
  useEffect(()=>{request<MiniaStatus>('/minia/status').then(setMinia).catch(()=>setMinia(null));},[]);
  const [scans,setScans]=useState<Scan[]>([]), [scanId,setScanId]=useState('');
  const [name,setName]=useState(''), [path,setPath]=useState(''), [error,setError]=useState('');
  const [busy,setBusy]=useState(false), [loading,setLoading]=useState(true);
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
    try{const p=await request<Project>('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,path})});setProjects(past=>[...past,p]);setSelected(p.id);setName('');setPath('');setAdding(false);setPickerOpen(false);}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const [run,setRun]=useState<Run|null>(null);
  // Comparaison de deux analyses completes (TAXO-01F) : choisies dans le comparateur, A au depart, B a l'arrivee.
  const [comparing,setComparing]=useState<{before:string; after:string}|null>(null);
  const [choosing,setChoosing]=useState<{before?:string; after?:string}|null>(null);
  useEffect(()=>{setComparing(null);setChoosing(null);},[selected]);
  const elsewhere=!!comparing||!!choosing;
  const [pickerOpen,setPickerOpen]=useState(false), [adding,setAdding]=useState(false);
  // Les routes de l'analyse affichee, lues une fois par la section Routes et resumees dans la vue d'ensemble.
  const [routes,setRoutes]=useState<{scanId:string; counts:RouteCounts}|null>(null);
  const routesLoaded=useCallback((id:string, value:Parameters<typeof routeCounts>[0])=>setRoutes({scanId:id, counts:routeCounts(value)}),[]);
  function analyze(){
    return analyzeProject(selected,{request, open:(url,last)=>openStream(url,last?{headers:{'Last-Event-ID':last}}:undefined), setRun, setError, setBusy, addScan:s=>{setScans(past=>[s,...past]);setScanId(s.id);}});
  }
  const running=run?.status==='running';
  const shown=running?liveScan(scan,run):scan;
  const legacyFacts=shown?.facts??[];
  const technologies=shown?technologiesOf(shown):[];
  const cards=shown?overviewCards(shown, routes?.scanId===shown.id?routes.counts:undefined):[];
  const countOf=(id:string)=>{const card=cards.find(item=>item.id===id);return card&&card.state==='known'?card.value:undefined;};
  const protectedRoutes=routes&&routes.scanId===shown?.id?routes.counts:undefined;
  const resultItems=shown?resultItemsOf(technologies.length, countOf, protectedRoutes):[];
  return <div className="layout">
    <header className="page-head"><TopMenu canAnalyze={!!selected&&!busy&&!loading} analyze={analyze} addProject={()=>{setPickerOpen(true);setAdding(true);}}/>
      <div className="head-actions"><ProjectPicker projects={projects} selected={selected} busy={busy} loading={loading} open={pickerOpen||projects.length===0&&!loading} setOpen={open=>{setPickerOpen(open);if(!open)setAdding(false);}}
        adding={adding||projects.length===0} setAdding={setAdding} onSelect={id=>{setError('');setSelected(id);setPickerOpen(false);setAdding(false);}} status={shown?since(shown.created_at):''}
        name={name} setName={setName} path={path} setPath={setPath} onSubmit={add}/><button type="button" className="primary" disabled={!selected||busy||loading} onClick={analyze}>{busy?<Working text="Analyse en cours"/>:<>{"Lancer l’analyse globale"}<svg className="btn-arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></>}</button></div></header>
    <aside><a className="brand" href="/"><svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="3" y="3" width="26" height="26" rx="7"/><path d="M10 11h12M16 11v11"/></svg>Taxo<span>EXPLORATEUR LOGICIEL</span></a>
    {resultItems.length>0&&<ResultsNav items={resultItems}/>}
    <p className="aside-note">Analyse locale · v0.1<br/>Vos fichiers restent sur votre machine.</p></aside>
    <main>
    {error&&<div role="alert" className="error">{error}</div>}
    {run&&run.status!=='done'&&<AnalysisProgress run={run}/>}
    {choosing&&selected&&<ComparePicker base={`/projects/${selected}`} request={request} initial={choosing}
      onClose={()=>setChoosing(null)} onCompare={(before, after)=>{setChoosing(null);setComparing({before, after});}}/>}
    {comparing&&selected&&<ComparisonView base={`/projects/${selected}`} request={request} before={comparing.before} after={comparing.after}
      onClose={()=>setComparing(null)} onSwap={()=>setComparing({before:comparing.after, after:comparing.before})}
      onChange={()=>{setChoosing(comparing);setComparing(null);}} project={projects.find(item=>item.id===selected)}/>}
    {!elsewhere&&loading&&<output>Chargement…</output>}
    {!elsewhere&&!loading&&(shown?<>
      <ProjectOverview scan={shown} pending={running?pendingEvaluators(run):undefined} routes={routes?.scanId===shown.id?routes.counts:undefined}/>
      {!running&&<CompareLauncher current={sideOf(shown)} count={scans.length} onPick={fixed=>setChoosing(fixed?{before:fixed}:{})}/>}
      <section className="results" id="technologies"><div className="section-heading"><div><h2>Technologies</h2><p>Reconnues par les noms de fichiers et les dépendances déclarées ; une dépendance déclarée ne prouve pas qu’elle est utilisée.</p></div><label>Analyse du<select value={shown.id} onChange={e=>setScanId(e.target.value)}>{scans.map(s=><option key={s.id} value={s.id}>{new Date(s.created_at).toLocaleString('fr-CA')}</option>)}</select></label></div>
      {technologies.length?<div className="tags">{technologies.map(t=><span key={t}>{t}</span>)}</div>:<p className="empty">Aucune technologie reconnue dans ce dossier.</p>}
      {legacyFacts.length>0&&<details className="evidence-files"><summary>Fichiers justificatifs ({legacyFacts.length})</summary><div className="table-wrap"><table><thead><tr><th>Technologie</th><th>Fichier justificatif</th><th>Détection</th></tr></thead><tbody>{legacyFacts.map(f=><tr key={f.technology+f.file}><td>{f.technology}</td><td><code>{f.file}</code></td><td>{f.method==='manifest'?'Manifeste':'Nom de fichier'}</td></tr>)}</tbody></table></div></details>}
      </section>
      <AnalysisLimits scan={shown}/>
      <AnalysisDetails scan={shown}/>
      {!running&&<RoutesPanel key={panelKey('routes',selected)} base={`/projects/${selected}`} scanId={shown.id} request={request} onLoaded={routesLoaded}/>}
    </>:!running&&<section className="welcome"><div className="glyph">⌘</div><h2>{selected?'Prêt pour la première analyse':'Commencez avec un projet local'}</h2><p>{selected?'Lancez l’analyse globale : Taxo vous montrera ce qu’il comprend de votre projet, et ce qu’il ne sait pas encore déterminer.':'Enregistrez un dossier dans le panneau de gauche, puis lancez son analyse.'}</p><p className="muted">Java · TypeScript · Python · React · Spring Boot</p></section>)}
    {!elsewhere&&selected&&!loading&&scan&&<AskTaxo key={panelKey('ask',selected)} base={`/projects/${selected}`} request={request} minia={minia}/>}
    {!elsewhere&&selected&&!loading&&<HistoryPanel key={panelKey('history',selected)} projectId={selected} minia={minia}/>}
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
