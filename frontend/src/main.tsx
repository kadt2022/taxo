import {useEffect, useState, type FormEvent} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type Project = {id:string; name:string; path:string};
type SnapshotReference = {repository:string; commit:string; mode:'COMMIT'|'WORKING_TREE'; dirty?:boolean; content_fingerprint?:string};
type EvaluationSummary = {
  execution_id:string; evaluator_id:string; producer_version:string; status:string;
  started_at:string; finished_at:string; duration_seconds:number;
  fact_count:number; coverage_count:number; warning_count:number;
  relations:Record<string,number>;
  coverage:{coverage_type:string; count:number; subjects:string[]}[];
  snapshot:SnapshotReference;
};
type Scan = {id:string; created_at:string; files_count?:number; commit?:string|null; snapshot?:SnapshotReference|null; facts?:{technology:string; file:string; method:string}[]; warnings?:string[]; evaluation_summary?:EvaluationSummary};
function sourceLabel(scan:Scan):string {
  const snapshot=scan.snapshot===undefined?scan.evaluation_summary?.snapshot:scan.snapshot;
  if(snapshot===undefined){
    const head=scan.commit?' · HEAD '+scan.commit.slice(0,12):' · aucun commit identifié';
    return 'Source : fichiers de travail'+head+'. Les modifications non commitées sont incluses.';
  }
  if(snapshot===null) return 'Source : dossier non versionné par Git.';
  const commit=snapshot.commit.slice(0,12);
  if(snapshot.mode==='COMMIT') return 'Source : commit '+commit+', contenu lu dans Git.';
  const changes=snapshot.dirty?', modifications non commitées incluses':'';
  return 'Source : dossier de travail au commit '+commit+changes+'.';
}

function EvaluationPanel({summary}:{summary:EvaluationSummary}){
  const relations=Object.entries(summary.relations);
  const duration=new Intl.NumberFormat('fr-CA',{minimumFractionDigits:1,maximumFractionDigits:1}).format(summary.duration_seconds)+' s';
  const date=(value:string)=>new Date(value).toLocaleString('fr-CA');
  const subject=(value:string)=>value.startsWith('repository:')?'repository':value.replace(/^file:/,'');
  return <section className="evaluation" aria-label="État de l'analyse">
    <p className="eyebrow">ÉTAT DE L'ANALYSE</p>
    <div className="evaluation-metrics">
      <div><strong className={'status status-'+summary.status.toLowerCase()}>{summary.status}</strong><span>Statut</span></div>
      <div><strong>{duration}</strong><span>Durée</span></div>
      <div><strong>{summary.fact_count.toLocaleString('fr-CA')}</strong><span>Faits</span></div>
      <div><strong>{summary.coverage_count.toLocaleString('fr-CA')}</strong><span>Couverture</span></div>
      <div><strong>{summary.warning_count.toLocaleString('fr-CA')}</strong><span>Avertissements</span></div>
    </div>
    <div className="evaluation-details">
      <section><h2>Exécution</h2><dl>
        <div><dt>Évaluateur</dt><dd>{summary.evaluator_id}</dd></div>
        <div><dt>Version</dt><dd>{summary.producer_version}</dd></div>
        <div><dt>Execution ID</dt><dd><code>{summary.execution_id}</code></dd></div>
        <div><dt>Commit</dt><dd><code title={summary.snapshot.commit}>{summary.snapshot.commit.slice(0,12)}…</code></dd></div>
        <div><dt>Début</dt><dd>{date(summary.started_at)}</dd></div>
        <div><dt>Fin</dt><dd>{date(summary.finished_at)}</dd></div>
      </dl></section>
      <section><h2>Couverture</h2>
        {summary.coverage.length?<div className="table-wrap"><table><thead><tr><th>Type</th><th>Zones</th><th>Nombre</th></tr></thead><tbody>
          {summary.coverage.map(group=><tr key={group.coverage_type}><td>{group.coverage_type}</td><td>{group.subjects.map(value=><code className="coverage-subject" key={value}>{subject(value)}</code>)}{group.count>group.subjects.length&&<span className="muted">+ {group.count-group.subjects.length} autres</span>}</td><td>{group.count.toLocaleString('fr-CA')}</td></tr>)}
        </tbody></table></div>:<p className="muted">Aucune couverture détaillée disponible.</p>}
      </section>
      <section><h2>Faits par relation</h2>
        {relations.length?<div className="table-wrap"><table><thead><tr><th>Relation</th><th>Nombre</th></tr></thead><tbody>
          {relations.map(([relation,count])=><tr key={relation}><td>{relation}</td><td>{count.toLocaleString('fr-CA')}</td></tr>)}
        </tbody></table></div>:<p className="muted">Aucun fait produit.</p>}
      </section>
    </div>
  </section>;
}

async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch('/api'+path, init);
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
  async function analyze(){
    setBusy(true);setError('');
    try{const s=await request<Scan>(`/projects/${selected}/scans`,{method:'POST'});setScans(past=>[s,...past]);setScanId(s.id);}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const legacyFacts=scan?.facts??[];
  const technologies=[...new Set(legacyFacts.map(f=>f.technology))];
  return <div className="layout">
    <aside><a className="brand" href="/">▥ Taxo<span>EXPLORATEUR LOGICIEL</span></a><h2>Projets <span>{projects.length}</span></h2>
    <nav aria-label="Projets">{projects.map(p=><button disabled={busy} aria-current={selected===p.id?'page':undefined} className={selected===p.id?'selected':''} key={p.id} onClick={()=>{setError('');setSelected(p.id);}}>{p.name}<span>↗</span></button>)}</nav>
    <form onSubmit={add}><h2>Ajouter un projet</h2><label>Nom<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder="Mon application"/></label><label>Dossier local<input required value={path} onChange={e=>setPath(e.target.value)} placeholder="D:\MonProjet"/></label><button className="secondary" disabled={busy||loading}>Enregistrer le projet</button></form>
    <p className="aside-note">Analyse locale · v0.1<br/>Vos fichiers restent sur votre machine.</p></aside>
    <main><header><div><p className="eyebrow">INVENTAIRE / TECHNOLOGIES</p><h1>{project?.name??'Votre logiciel, à découvert.'}</h1><p className="path">{project?.path??'Ajoutez un dossier pour découvrir les technologies de votre projet.'}</p></div><button className="primary" disabled={!selected||busy||loading} onClick={analyze}>{busy?'Opération en cours…':'↻ Lancer une analyse'}</button></header>
    {error&&<div role="alert" className="error">{error}</div>}
    {loading?<p role="status">Chargement…</p>:scan?<>
      {scan.evaluation_summary&&<EvaluationPanel summary={scan.evaluation_summary}/>}
      <section className="metrics" aria-label="Résumé"><article><span>Technologies détectées</span><strong>{technologies.length}</strong></article><article><span>Fichiers parcourus</span><strong>{(scan.files_count??0).toLocaleString('fr')}</strong></article><article><span>Analyses conservées</span><strong>{scans.length}</strong></article></section>
      <section className="results"><div className="section-heading"><div><h2>Les preuves dans votre code</h2><p>Détection par noms de fichiers et dépendances déclarées.</p></div><label>Historique<select value={scan.id} onChange={e=>setScanId(e.target.value)}>{scans.map(s=><option key={s.id} value={s.id}>{new Date(s.created_at).toLocaleString('fr-CA')}</option>)}</select></label></div>
      <div className="tags">{technologies.map(t=><span key={t}>{t}</span>)}</div>
      {legacyFacts.length?<div className="table-wrap"><table><thead><tr><th>Technologie</th><th>Fichier justificatif</th><th>Détection</th></tr></thead><tbody>{legacyFacts.map(f=><tr key={f.technology+f.file}><td>{f.technology}</td><td><code>{f.file}</code></td><td>{f.method==='manifest'?'Manifeste':'Nom de fichier'}</td></tr>)}</tbody></table></div>:<p className="empty">Aucune technologie reconnue dans ce dossier.</p>}
      <footer>{sourceLabel(scan)}</footer>
      {(scan.warnings??[]).map((w,i)=><p className="error" key={i}>{w}</p>)}</section>
    </>:<section className="welcome"><div className="glyph">⌘</div><h2>{selected?'Prêt pour la première analyse':'Commencez avec un projet local'}</h2><p>{selected?'Lancez une analyse pour obtenir un inventaire accompagné de ses sources.':'Enregistrez un dossier dans le panneau de gauche, puis lancez son analyse.'}</p><p className="muted">Java · TypeScript · Python · React · Spring Boot</p></section>}
    <p className="scope">Cette première version identifie les technologies. L’extraction des API, des permissions et des relations métier n’est pas encore intégrée.</p></main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
