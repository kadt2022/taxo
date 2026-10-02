// L'application (TAXO-UI-05) : une page par fonction, choisie par l'adresse. Sortie de main.tsx pour etre testee.
import {useEffect, useState, type FormEvent, type ReactNode} from 'react';
import {type MiniaStatus} from './minia';
import {AnalysisLimits, overviewCards, panelKey, routeCounts, technologiesOf, type Scan} from './overview';
import {BrandMark, ProjectPicker, ResultsNav, TopMenu, navItemsOf, since, type Project} from './shell';
import {href, go, parse, useRoute, withProject} from './nav';
import {AnalysesPage, AnalysisPage, ArchitecturePage, ComparisonsPage, DataPage, DisplayedNote, NotFoundPage, OverviewPage, PendingPage, TechnologiesPage} from './pages';
import {AskTaxo} from './query';
import {loadRoutes, RoutesExplorer, type RoutesResult} from './routes';
import {apiUrl} from './api';
import {openStream} from './sse';
import {AnalysisProgress, Working, analyzeProject, liveScan, pendingEvaluators, type Run} from './analysis';

export async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch(apiUrl(path), init);
  if (!response.ok) {
    const body = await response.json().catch(()=>null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `La requête a échoué (${response.status}).`);
  }
  return response.json();
}

/** Le portail : la coque (barre du haut, menu vertical) et la page de l'adresse. L'historique Git est fourni par main.tsx. */
export function App({history}:Readonly<{history:(projectId:string, minia:MiniaStatus|null)=>ReactNode}>){
  const route=useRoute();
  const [projects,setProjects]=useState<Project[]>([]), [selected,setSelected]=useState('');
  const [minia,setMinia]=useState<MiniaStatus|null>(null);
  useEffect(()=>{request<MiniaStatus>('/minia/status').then(setMinia).catch(()=>setMinia(null));},[]);
  const [scans,setScans]=useState<Scan[]>([]), [scanId,setScanId]=useState('');
  const [name,setName]=useState(''), [path,setPath]=useState(''), [error,setError]=useState('');
  const [busy,setBusy]=useState(false), [loading,setLoading]=useState(true);
  // L'analyse affichee : la plus recente par defaut, ou celle choisie dans la page Analyses.
  const scan=scans.find(s=>s.id===scanId) ?? scans[0];
  // Le projet fait partie de l'adresse : une page rechargee ou copiee rouvre le meme projet.
  useEffect(()=>{request<Project[]>('/projects').then(p=>{const wanted=parse(window.location.hash).params.get('projet');
    setProjects(p);setSelected(p.find(item=>item.id===wanted)?.id??p[0]?.id??'');}).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[]);
  useEffect(()=>{if(selected)withProject(selected);},[selected, route]);
  useEffect(()=>{
    let active=true;
    setScans([]);setScanId('');
    if(selected){setLoading(true);request<Scan[]>(`/projects/${selected}/scans`).then(s=>{if(active)setScans(s);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});}
    return ()=>{active=false;};
  },[selected]);
  async function add(event:FormEvent){
    event.preventDefault();setBusy(true);setError('');
    try{const p=await request<Project>('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,path})});setProjects(past=>[...past,p]);setSelected(p.id);setName('');setPath('');setAdding(false);setPickerOpen(false);go(href('overview'));}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const [run,setRun]=useState<Run|null>(null);
  const [pickerOpen,setPickerOpen]=useState(false), [adding,setAdding]=useState(false);
  function analyze(){
    return analyzeProject(selected,{request, open:(url,last)=>openStream(url,last?{headers:{'Last-Event-ID':last}}:undefined), setRun, setError, setBusy, addScan:s=>{setScans(past=>[s,...past]);setScanId(s.id);}});
  }
  const running=run?.status==='running';
  const shown=running?liveScan(scan,run):scan;
  const base=`/projects/${selected}`;
  // Les routes de l'analyse affichee, lues une seule fois : les pages Routes, Securite et Non interpretees les partagent avec Overview.
  const [routes,setRoutes]=useState<{scanId:string; result:RoutesResult|null; error:string}|null>(null);
  useEffect(()=>{
    if(!selected||!scan||running){return undefined;}
    setRoutes({scanId:scan.id, result:null, error:''});
    return loadRoutes(request, base, scan.id, {onResult:result=>setRoutes({scanId:scan.id, result, error:''}),
      onError:message=>setRoutes({scanId:scan.id, result:null, error:message})});
  },[base, scan?.id, running]);
  const mine=routes&&routes.scanId===shown?.id?routes:null;
  const counts=mine?.result?routeCounts(mine.result):undefined;
  const legacyCards=shown?overviewCards(shown, counts):[];
  const countOf=(id:string)=>{const card=legacyCards.find(item=>item.id===id);return card&&card.state==='known'?card.value:undefined;};
  const navItems=shown?navItemsOf(technologiesOf(shown).length, countOf, counts, scans.length):navItemsOf(0, ()=>undefined);
  const project=projects.find(item=>item.id===selected);
  const latest=scans[0];
  const showLatest=()=>setScanId('');
  const show=(id:string)=>{setScanId(id);go(href('overview'));};
  const revision=`${selected}:${scans.length}:${latest?.id??''}`;
  function page(){
    if(!selected)return null;
    switch(route.page){
    case 'analyses':return route.id?<AnalysisPage base={base} request={request} revision={revision} scan={scans.find(item=>item.id===route.id)}
      displayed={scan?.id} onShow={show}/>:<AnalysesPage base={base} request={request} revision={revision} displayed={scan?.id}/>;
    case 'comparaisons':return <ComparisonsPage base={base} request={request} route={route} project={project}/>;
    case 'historique':return history(selected, minia);
    case 'donnees':return <DataPage/>;
    case 'introuvable':return <NotFoundPage/>;
    default:
      if(scan&&shown)return scanPage(shown);
      // Premiere analyse en cours : seule Overview la suit ; les autres pages attendent une analyse enregistree.
      if(shown&&route.page==='overview')return <OverviewPage scan={shown} pending={pendingEvaluators(run!)} canAnalyze={false} onAnalyze={analyze}/>;
      return shown?<PendingPage/>:welcome();
    }
  }
  function scanPage(current:Scan){
    const note=<DisplayedNote scan={current} latest={latest} onLatest={showLatest}/>;
    const routesOf=(filter:string, title?:string, intro?:string)=><>{note}<RoutesExplorer key={`${current.id}:${filter}`} result={mine?.result??null}
      error={mine?.error??''} initialFilter={filter} title={title} intro={intro}/></>;
    switch(route.page){
    case 'interroger':return <AskTaxo key={panelKey('ask',selected)} base={base} request={request} minia={minia}/>;
    case 'technologies':return <>{note}<TechnologiesPage scan={current}/></>;
    case 'routes':return routesOf('ALL');
    case 'securite':return routesOf('PROTECTED', 'Sécurité des routes', 'Règles de protection observées par Taxo : pour chaque route, la règle qui la capture, ce qu’elle exige, et la preuve dans le code. Ce n’est pas encore une analyse de sécurité complète : seules les routes HTTP et leurs règles sont lues.');
    case 'non-interpretees':return routesOf('GAPS', 'Non interprétées', 'Les routes dont Taxo ne sait pas établir la protection, avec la zone qu’il n’a pas su interpréter. Une route listée ici n’est ni protégée ni ouverte : Taxo n’en dit rien.');
    case 'architecture':return <>{note}<ArchitecturePage base={base} request={request} scanId={current.id} project={project}/></>;
    case 'limites':return <>{note}<AnalysisLimits scan={current}/></>;
    default:return <>{note}<OverviewPage scan={current} latest={latest} pending={running?pendingEvaluators(run):undefined} routes={counts}
      canAnalyze={!busy&&!loading} onAnalyze={analyze}/></>;
    }
  }
  function welcome(){
    if(running)return null;
    return <section className="welcome"><div className="glyph">⌘</div><h2>Prêt pour la première analyse</h2><p>Lancez l’analyse globale : Taxo vous montrera ce qu’il comprend de votre projet, et ce qu’il ne sait pas encore déterminer.</p><p className="muted">Java · TypeScript · Python · React · Spring Boot</p></section>;
  }
  return <div className="layout">
    <header className="page-head"><div className="head-start"><a className="top-brand" href={href('overview')}><BrandMark/><span>Taxo</span></a>
      <TopMenu canAnalyze={!!selected&&!busy&&!loading} analyze={analyze} latest={scanId&&scanId!==latest?.id?showLatest:undefined}
      addProject={()=>{setPickerOpen(true);setAdding(true);}}/></div>
      <div className="head-actions"><ProjectPicker projects={projects} selected={selected} busy={busy} loading={loading} open={pickerOpen||projects.length===0&&!loading} setOpen={open=>{setPickerOpen(open);if(!open)setAdding(false);}}
        adding={adding||projects.length===0} setAdding={setAdding} onSelect={id=>{setError('');setSelected(id);setPickerOpen(false);setAdding(false);go(href('overview'));}} status={shown?since(shown.created_at):''}
        name={name} setName={setName} path={path} setPath={setPath} onSubmit={add}/><button type="button" className="primary" disabled={!selected||busy||loading} onClick={analyze}>{busy?<Working text="Analyse en cours"/>:<>{"Lancer l’analyse globale"}<svg className="btn-arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></>}</button></div></header>
    <aside><a className="brand" href={href('overview')}><BrandMark/>Taxo<span>EXPLORATEUR LOGICIEL</span></a>
    {selected&&<ResultsNav items={navItems} current={route.page}/>}
    <p className="aside-note">Analyse locale · v0.1<br/>Vos fichiers restent sur votre machine.</p></aside>
    <main>
    {error&&<div role="alert" className="error">{error}</div>}
    {run&&run.status!=='done'&&<AnalysisProgress run={run}/>}
    {loading?<output>Chargement…</output>:page()}
    </main>
  </div>;
}
