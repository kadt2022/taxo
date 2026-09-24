import {useEffect, useRef, useState, type FormEvent} from 'react';
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

function EvaluationPanel({summary}:Readonly<{summary:EvaluationSummary}>){
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

type Commit = {sha:string; parents:string[]; author:string; authored_at:string; subject:string};
type ChangedFile = {path:string; status:string; old_path:string|null; additions:number|null; deletions:number|null; confidential:boolean};
type CommitDetail = {commit:Commit; parent:string|null; files:ChangedFile[]};
type FactChange = {change:'INTRODUCED'|'REMOVED'|'MODIFIED'; kind:string; subject:string; relation:string|null; status:string; before:string|null; after:string|null};
type Evaluation = {evaluator_id:string; producer_version:string; comparable:boolean; failures:string[]; changes:FactChange[]; unchanged_count:number; not_interpreted_before:string[]; not_interpreted_after:string[]};
type Impact = {commit:Commit; parent:string|null; evaluations:Evaluation[]};
type DiffLine = {number:number; text:string; eol:'LF'|'CRLF'|'NONE'};
type DiffRow = {kind:'equal'|'changed'|'added'|'removed'; before:DiffLine|null; after:DiffLine|null};
type FileDiff = {path:string; old_path:string|null; status:string; commit:string; parent:string|null; displayable:boolean;
  reason:string|null; before:{path:string; size:number}|null; after:{path:string; size:number}|null;
  hunks:{before_start:number; after_start:number; rows:DiffRow[]}[]};
type LinkedFact = FactChange & {evaluator_id:string; precision:'LINE'|'FILE'; lines:{before:number[]; after:number[]}};
type DiffFacts = {path:string; commit:string; parent:string|null; facts:LinkedFact[]; not_comparable:string[]};
const DIFF_REASONS:Record<string,string>={
  CONFIDENTIAL:'Fichier confidentiel : Taxo le nomme, mais n’affiche jamais son contenu.',
  BINARY:'Fichier binaire : il n’y a pas de diff texte à afficher.',
  TOO_LARGE:'Fichier trop volumineux (plus de 1 Mo) : son contenu n’est pas affiché.',
  NOT_A_REGULAR_FILE:'Lien symbolique ou sous-module : son contenu n’est pas affiché.',
};

// Une fin de ligne differente reste visible : LF, la plus courante, n'est pas signalee.
const EOL_MARKS:Record<DiffLine['eol'],string>={LF:'',CRLF:'␍␊',NONE:'sans fin de ligne'};
function DiffCode({line,changed}:Readonly<{line:DiffLine|null; changed:boolean}>){
  const mark=line&&changed?EOL_MARKS[line.eol]:'';
  return <><code>{line?.text??''}</code>{mark===''?null:<span className="eol">{mark}</span>}</>;
}

function lineLabel(lines:LinkedFact['lines']){
  const parts=[lines.before.length&&`avant ${lines.before.join(', ')}`,lines.after.length&&`après ${lines.after.join(', ')}`].filter(Boolean);
  return parts.length?`ligne ${parts.join(' · ')}`:'fichier : aucune ligne modifiée ne porte sa preuve';
}
function LinkedFacts({links}:Readonly<{links:DiffFacts}>){
  return <section className="linked-facts" aria-label="Faits touchés par ce fichier">
    <h3>Faits Taxo touchés par ce fichier</h3>
    {links.not_comparable.length>0&&<p role="alert" className="error">Comparaison impossible pour {links.not_comparable.join(', ')} : ses faits ne sont pas reliés.</p>}
    {links.facts.length?<ul>{links.facts.map(f=><li key={f.evaluator_id+f.change+f.subject+f.relation+(f.before??'')+(f.after??'')}>
      <strong>{CHANGE_LABELS[f.change]}</strong> <code>{f.subject}</code> {f.relation??f.kind}
      {f.before===null&&f.after===null?null:<> : <code>{f.before??'∅'}</code> → <code>{f.after??'∅'}</code></>}
      <span className={f.precision==='LINE'?'precision line':'precision'}>{lineLabel(f.lines)}</span>
      <span className="muted"> · {f.evaluator_id} · {f.status}</span>
    </li>)}</ul>:<p className="muted">Aucun fait changé par ce commit n’a sa preuve dans ce fichier.</p>}
    <footer>Le lien passe par les preuves des faits, jamais par une lecture du texte. Seuls les faits que les évaluateurs savent produire sont reliés.</footer>
  </section>;
}

function DiffView({diff,links}:Readonly<{diff:FileDiff; links:DiffFacts|null}>){
  const marked={before:new Set(links?.facts.flatMap(f=>f.lines.before)),after:new Set(links?.facts.flatMap(f=>f.lines.after))};
  const number=(line:DiffLine|null,side:'before'|'after')=>line&&marked[side].has(line.number)?<td className="number linked" title="Ligne reliée à un fait Taxo">◆ {line.number}</td>:<td className="number">{line?.number??''}</td>;
  const side=(label:string,value:FileDiff['before'],ref:string|null)=>value?`${label} — ${value.path}${ref?' @ '+ref.slice(0,7):''}`:`${label} — (aucun fichier)`;
  return <section className="diff-view" aria-label="Diff du fichier">
    <p className="eyebrow">DIFF — CE QUE GIT MONTRE</p>
    <h2><code>{diff.old_path?`${diff.old_path} → ${diff.path}`:diff.path}</code></h2>
    {!diff.displayable?<p className="muted">{DIFF_REASONS[diff.reason??'']??'Contenu non disponible.'}</p>
    :diff.hunks.length===0?<p className="muted">Aucune ligne modifiée : seul le nom ou le mode du fichier a changé.</p>
    :<div className="table-wrap"><table className="diff">
      <colgroup><col className="number-col"/><col/><col className="number-col"/><col/></colgroup>
      <thead><tr><th colSpan={2}>{side('AVANT',diff.before,diff.parent)}</th><th colSpan={2}>{side('APRÈS',diff.after,diff.commit)}</th></tr></thead>
      {diff.hunks.map(h=><tbody key={`${h.before_start}-${h.after_start}`}>
        <tr className="hunk"><td colSpan={4}>@@ ligne {h.before_start} → ligne {h.after_start}</td></tr>
        {h.rows.map(r=><tr key={`${r.before?.number??'-'}-${r.after?.number??'-'}`} className={'diff-'+r.kind}>
          {number(r.before,'before')}<td className={r.before&&r.kind!=='equal'?'removed':''}><DiffCode line={r.before} changed={r.kind!=='equal'}/></td>
          {number(r.after,'after')}<td className={r.after&&r.kind!=='equal'?'added':''}><DiffCode line={r.after} changed={r.kind!=='equal'}/></td>
        </tr>)}
      </tbody>)}
    </table></div>}
    {links&&<LinkedFacts links={links}/>}
  </section>;
}
const CHANGE_LABELS:Record<FactChange['change'],string>={INTRODUCED:'Ajouté',REMOVED:'Retiré',MODIFIED:'Modifié'};
const FILE_LABELS:Record<string,string>={ADDED:'Ajouté',MODIFIED:'Modifié',DELETED:'Supprimé',RENAMED:'Renommé',COPIED:'Copié',TYPE_CHANGED:'Type modifié'};

function HistoryPanel({projectId}:Readonly<{projectId:string}>){
  const [commits,setCommits]=useState<Commit[]>([]), [detail,setDetail]=useState<CommitDetail|null>(null);
  const [impact,setImpact]=useState<Impact|null>(null),  [fileDiff,setFileDiff]=useState<FileDiff|null>(null), [links,setLinks]=useState<DiffFacts|null>(null), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const base=`/projects/${projectId}/history/commits`;
  // Seule la derniere demande peut modifier l'ecran : une reponse arrivee trop tard est ignoree.
  const latest=useRef(0);
  useEffect(()=>{
    let active=true;
    setCommits([]);setDetail(null);setImpact(null);setFileDiff(null);setLinks(null);setError('');
    request<Commit[]>(`${base}?limit=10`).then(c=>{if(active)setCommits(c);}).catch(e=>{if(active)setError(e.message);});
    return ()=>{active=false;};
  },[base]);
  async function load<T>(path:string, apply:(value:T)=>void){
    const token=++latest.current;
    setBusy(true);setError('');
    try{const value=await request<T>(path);if(token===latest.current)apply(value);}
    catch(e){if(token===latest.current)setError((e as Error).message);}
    finally{if(token===latest.current)setBusy(false);}
  }
  function open(sha:string){setImpact(null);setFileDiff(null);setLinks(null);return load<CommitDetail>(`${base}/${sha}`,setDetail);}
  function compare(sha:string,path:string,parent:string|null){
    const query=new URLSearchParams({path});if(parent)query.set('parent',parent);
    setLinks(null);
    return load<FileDiff>(`${base}/${sha}/diff?${query}`,setFileDiff);
  }
  function relate(diff:FileDiff){
    const query=new URLSearchParams({path:diff.path});if(diff.parent)query.set('parent',diff.parent);
    return load<DiffFacts>(`${base}/${diff.commit}/diff/facts?${query}`,setLinks);
  }
  function understand(sha:string){return load<Impact>(`${base}/${sha}/impact`,setImpact);}
  const date=(value:string)=>new Date(value).toLocaleString('fr-CA');
  // Les deux cotes comptent : une zone non lue avant le commit rend la comparaison incomplete aussi.
  const gaps=(side:string,zones:string[])=>zones.length?`Zones non interprétées ${side} : ${zones.join(', ')}.`:`Aucune zone non interprétée ${side}.`;
  return <section className="results history" aria-label="Historique Git">
    <div className="section-heading"><div><h2>Historique Git</h2><p>Les 10 derniers commits, lus directement dans Git, et ce que Taxo comprend de chacun.</p></div></div>
    {error&&<div role="alert" className="error">{error}</div>}
    {commits.length?<div className="table-wrap"><table><thead><tr><th>Commit</th><th>Message</th><th>Auteur</th><th>Date</th></tr></thead><tbody>
      {commits.map(c=><tr key={c.sha} className={detail?.commit.sha===c.sha?'current':''}><td><button className="link" disabled={busy} onClick={()=>open(c.sha)}><code>{c.sha.slice(0,7)}</code></button>{c.parents.length>1&&<span className="muted"> fusion</span>}</td><td>{c.subject}</td><td>{c.author}</td><td>{date(c.authored_at)}</td></tr>)}
    </tbody></table></div>:!error&&<p className="empty">Aucun commit dans ce dépôt.</p>}
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
        <DiffView diff={fileDiff} links={links&&links.commit===fileDiff.commit&&links.path===fileDiff.path?links:null}/>
        <button className="secondary relate" disabled={busy} onClick={()=>relate(fileDiff)}>Relier ce diff aux faits Taxo</button>
      </>}
      <button className="primary" disabled={busy} onClick={()=>understand(detail.commit.sha)}>{busy?'Analyse en cours…':'Ce que Taxo comprend de ce commit'}</button>
    </section>}
    {impact&&impact.commit.sha===detail?.commit.sha&&<section className="impact" aria-label="Impact compris par Taxo">
      {impact.evaluations.map(e=><div key={e.evaluator_id}>
        <h2>Impact selon {e.evaluator_id} <span className="muted">v{e.producer_version}</span></h2>
        {!e.comparable?<p role="alert" className="error">Comparaison impossible : l’analyse a échoué ({e.failures.join(' ; ')}). Taxo n’affiche aucun changement plutôt que d’en inventer.</p>:e.changes.length?<div className="table-wrap"><table><thead><tr><th>Changement</th><th>Sujet</th><th>Relation</th><th>Avant</th><th>Après</th><th>Statut</th></tr></thead><tbody>
          {e.changes.map(c=><tr key={c.change+c.subject+c.relation+(c.before??'')+(c.after??'')}><td>{CHANGE_LABELS[c.change]}</td><td><code>{c.subject}</code></td><td>{c.relation??c.kind}</td><td><code>{c.before??''}</code></td><td><code>{c.after??''}</code></td><td>{c.status}</td></tr>)}
        </tbody></table></div>:<p className="muted">Aucun fait changé parmi ceux que cet évaluateur sait produire.</p>}
        {e.comparable&&<footer>{e.unchanged_count.toLocaleString('fr-CA')} faits inchangés. {gaps('avant le commit',e.not_interpreted_before)} {gaps('après le commit',e.not_interpreted_after)} Seuls les faits que cet évaluateur sait produire sont comparés : l’absence de changement ici ne prouve pas l’absence de changement ailleurs.</footer>}
      </div>)}
    </section>}
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
      {[...new Set(scan.warnings??[])].map(w=><p className="error" key={w}>{w}</p>)}</section>
    </>:<section className="welcome"><div className="glyph">⌘</div><h2>{selected?'Prêt pour la première analyse':'Commencez avec un projet local'}</h2><p>{selected?'Lancez une analyse pour obtenir un inventaire accompagné de ses sources.':'Enregistrez un dossier dans le panneau de gauche, puis lancez son analyse.'}</p><p className="muted">Java · TypeScript · Python · React · Spring Boot</p></section>}
    {selected&&!loading&&<HistoryPanel key={selected} projectId={selected}/>}
    <p className="scope">Cette première version identifie les technologies. L’extraction des API, des permissions et des relations métier n’est pas encore intégrée.</p></main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
