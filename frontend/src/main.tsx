import {useEffect, useState, type FormEvent} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type Project = {id:string; name:string; path:string};
type Scan = {id:string; created_at:string; files_count:number; commit:string|null; snapshot?:{repository:string; commit:string; mode:'COMMIT'|'WORKING_TREE'; dirty?:boolean; content_fingerprint?:string}|null; facts:{technology:string; file:string; method:string}[]; warnings:string[]};
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
  const technologies=[...new Set(scan?.facts.map(f=>f.technology)??[])];
  return <div className="layout">
    <aside><a className="brand" href="/">▥ Taxo<span>EXPLORATEUR LOGICIEL</span></a><h2>Projets <span>{projects.length}</span></h2>
    <nav aria-label="Projets">{projects.map(p=><button disabled={busy} aria-current={selected===p.id?'page':undefined} className={selected===p.id?'selected':''} key={p.id} onClick={()=>{setError('');setSelected(p.id);}}>{p.name}<span>↗</span></button>)}</nav>
    <form onSubmit={add}><h2>Ajouter un projet</h2><label>Nom<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder="Mon application"/></label><label>Dossier local<input required value={path} onChange={e=>setPath(e.target.value)} placeholder="D:\MonProjet"/></label><button className="secondary" disabled={busy||loading}>Enregistrer le projet</button></form>
    <p className="aside-note">Analyse locale · v0.1<br/>Vos fichiers restent sur votre machine.</p></aside>
    <main><header><div><p className="eyebrow">INVENTAIRE / TECHNOLOGIES</p><h1>{project?.name??'Votre logiciel, à découvert.'}</h1><p className="path">{project?.path??'Ajoutez un dossier pour découvrir les technologies de votre projet.'}</p></div><button className="primary" disabled={!selected||busy||loading} onClick={analyze}>{busy?'Opération en cours…':'↻ Lancer une analyse'}</button></header>
    {error&&<div role="alert" className="error">{error}</div>}
    {loading?<p role="status">Chargement…</p>:scan?<>
      <section className="metrics" aria-label="Résumé"><article><span>Technologies détectées</span><strong>{technologies.length}</strong></article><article><span>Fichiers parcourus</span><strong>{scan.files_count.toLocaleString('fr')}</strong></article><article><span>Analyses conservées</span><strong>{scans.length}</strong></article></section>
      <section className="results"><div className="section-heading"><div><h2>Les preuves dans votre code</h2><p>Détection par noms de fichiers et dépendances déclarées.</p></div><label>Historique<select value={scan.id} onChange={e=>setScanId(e.target.value)}>{scans.map(s=><option key={s.id} value={s.id}>{new Date(s.created_at).toLocaleString('fr-CA')}</option>)}</select></label></div>
      <div className="tags">{technologies.map(t=><span key={t}>{t}</span>)}</div>
      {scan.facts.length?<div className="table-wrap"><table><thead><tr><th>Technologie</th><th>Fichier justificatif</th><th>Détection</th></tr></thead><tbody>{scan.facts.map(f=><tr key={f.technology+f.file}><td>{f.technology}</td><td><code>{f.file}</code></td><td>{f.method==='manifest'?'Manifeste':'Nom de fichier'}</td></tr>)}</tbody></table></div>:<p className="empty">Aucune technologie reconnue dans ce dossier.</p>}
      <footer>{scan.snapshot===undefined?`Source : fichiers de travail${scan.commit?` · HEAD ${scan.commit.slice(0,12)}`:' · aucun commit identifié'}. Les modifications non commitées sont incluses.`:scan.snapshot===null?'Source : dossier non versionné par Git.':scan.snapshot.mode==='COMMIT'?`Source : commit ${scan.snapshot.commit.slice(0,12)}, contenu lu dans Git.`:`Source : dossier de travail au commit ${scan.snapshot.commit.slice(0,12)}${scan.snapshot.dirty?', modifications non commitées incluses':''}.`}</footer>
      {scan.warnings.map((w,i)=><p className="error" key={i}>{w}</p>)}</section>
    </>:<section className="welcome"><div className="glyph">⌘</div><h2>{selected?'Prêt pour la première analyse':'Commencez avec un projet local'}</h2><p>{selected?'Lancez une analyse pour obtenir un inventaire accompagné de ses sources.':'Enregistrez un dossier dans le panneau de gauche, puis lancez son analyse.'}</p><p className="muted">Java · TypeScript · Python · React · Spring Boot</p></section>}
    <p className="scope">Cette première version identifie les technologies. L’extraction des API, des permissions et des relations métier n’est pas encore intégrée.</p></main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
