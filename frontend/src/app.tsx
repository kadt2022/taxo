// L'application (TAXO-UI-05) : une page par fonction, choisie par l'adresse. Sortie de main.tsx pour etre testee.
import {useEffect, useState, type ReactNode} from 'react';
import {type MiniaStatus} from './minia';
import {AnalysisLimits, overviewCards, panelKey, routeCounts, technologiesOf, type Scan} from './overview';
import {BrandMark, ResultsNav, TopMenu, navItemsOf, since, type Project} from './shell';
import {AnalysisCommand, LaunchCard} from './commands';
import {ProjectSwitcher} from './switcher';
import {href, go, parse, useRoute, withProject} from './nav';
import {AnalysesPage, AnalysisPage, ArchitecturePage, ComparisonsPage, DataPage, DisplayedNote, NotFoundPage, OverviewPage, PendingPage, ProjectsPage, TechnologiesPage} from './pages';
import {AskTaxo} from './query';
import {loadRoutes, RoutesExplorer, type RoutesResult} from './routes';
import {isUnknown, readNothing, readingOf, unreadBy, useCoverage} from './reading';
import {apiUrl} from './api';
import {openStream} from './sse';
import {AnalysisProgress, analyzeProject, liveScan, pendingEvaluators, type Run} from './analysis';
import {ExplorerPage} from './explorer/Explorer';

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
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false), [loading,setLoading]=useState(true);
  const [run,setRun]=useState<Run|null>(null);
  // L'analyse affichee : la plus recente par defaut, ou celle choisie dans la page Analyses.
  const scan=scans.find(s=>s.id===scanId) ?? scans[0];
  // Le projet fait partie de l'adresse : une page rechargee ou copiee rouvre le meme projet.
  useEffect(()=>{request<Project[]>('/projects').then(p=>{const wanted=parse(window.location.hash).params.get('projet');
    setProjects(p);setSelected(p.find(item=>item.id===wanted)?.id??p[0]?.id??'');}).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[]);
  useEffect(()=>{if(selected)withProject(selected);},[selected, route]);
  useEffect(()=>{
    let active=true;
    // Une analyse appartient a son projet : en changer efface sa progression, son echec et sa relance.
    setScans([]);setScanId('');setRun(null);
    if(selected){setLoading(true);request<Scan[]>(`/projects/${selected}/scans`).then(s=>{if(active)setScans(s);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});}
    return ()=>{active=false;};
  },[selected]);
  /** Ajouter un projet en fait le projet actif ; renvoie faux si l'API le refuse, l'erreur restant affichee. */
  async function add(name:string, path:string){
    setBusy(true);setError('');
    try{const p=await request<Project>('/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,path})});setProjects(past=>[...past,p]);setSelected(p.id);go(href('overview'));return true;}
    catch(e){setError((e as Error).message);return false;}finally{setBusy(false);}
  }
  const open=(id:string)=>{setError('');setSelected(id);go(href('overview'));};
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
  // Ce que chaque analyseur a lu, pour l'analyse affichee (TAXO-COV-01) : une limite, jamais une absence.
  const coverage=useCoverage(request, base, selected?scan?.id:undefined, shown?.id, running);
  const counts=mine?.result?routeCounts(mine.result):undefined;
  const legacyCards=shown?overviewCards(shown, counts, coverage):[];
  const countOf=(id:string)=>{const card=legacyCards.find(item=>item.id===id);return card&&card.state==='known'?card.value:undefined;};
  // Sécurité et Non interprétées comptent les routes examinées par la sécurité : rien si elle n'a rien lu.
  const examined=isUnknown(coverage)||readNothing(readingOf(coverage, 'taxo.spring-security'), coverage)?undefined:counts;
  const navItems=shown?navItemsOf(technologiesOf(shown).length, countOf, examined, scans.length):navItemsOf(0, ()=>undefined);
  const project=projects.find(item=>item.id===selected);
  const latest=scans[0];
  const showLatest=()=>setScanId('');
  const show=(id:string)=>{setScanId(id);go(href('overview'));};
  const revision=`${selected}:${scans.length}:${latest?.id??''}`;
  function page(){
    const projectsPage=<ProjectsPage projects={projects} selected={selected} busy={busy} adding={route.params.get('ajouter')==='1'} onOpen={open} onAdd={add}/>;
    if(!selected||route.page==='projets')return projectsPage;
    switch(route.page){
    case 'analyses':return route.id?<AnalysisPage base={base} request={request} revision={revision} scan={scans.find(item=>item.id===route.id)}
      displayed={scan?.id} onShow={show}/>:<AnalysesPage base={base} request={request} revision={revision} displayed={scan?.id}
      launch={<LaunchCard project={project} latest={latest} count={scans.length} run={run} canAnalyze={!busy&&!loading} onAnalyze={analyze}/>}/>;
    case 'comparaisons':return <ComparisonsPage base={base} request={request} route={route} project={project}/>;
    case 'historique':return history(selected, minia);
    case 'donnees':return <DataPage/>;
    case 'introuvable':return <NotFoundPage/>;
    default:
      if(scan&&shown)return scanPage(shown);
      // Premiere analyse en cours : seule Overview la suit ; les autres pages attendent une analyse enregistree.
      if(shown&&route.page==='overview')return <OverviewPage scan={shown} pending={pendingEvaluators(run!)}/>;
      return shown?<PendingPage/>:welcome();
    }
  }
  function scanPage(current:Scan){
    const note=<DisplayedNote scan={current} latest={latest} onLatest={showLatest}/>;
    // Routes et Sécurité disent ce que leur analyseur n'a pas lu.
    const routesOf=(filter:string, title?:string, intro?:string)=><>{note}<RoutesExplorer key={`${current.id}:${filter}`} result={mine?.result??null}
      error={mine?.error??''} initialFilter={filter} title={title} intro={intro}
      unread={unreadBy(coverage, [filter==='ALL'?'taxo.spring-api':'taxo.spring-security'])} unknown={isUnknown(coverage)}/></>;
    switch(route.page){
    case 'interroger':return <AskTaxo key={panelKey('ask',selected)} base={base} request={request} minia={minia}/>;
    case 'explorer':return <ExplorerPage key={selected} base={base} request={request} scanId={current.id} route={route} revision={revision} project={project}/>;
    case 'technologies':return <>{note}<TechnologiesPage scan={current}/></>;
    case 'routes':return routesOf('ALL');
    case 'securite':return routesOf('PROTECTED', 'Sécurité des routes', 'Règles de protection observées par Taxo : pour chaque route, la règle qui la capture, ce qu’elle exige, et la preuve dans le code. Ce n’est pas encore une analyse de sécurité complète : seules les routes HTTP et leurs règles sont lues.');
    case 'non-interpretees':return routesOf('GAPS', 'Non interprétées', 'Les routes dont Taxo ne sait pas établir la protection, avec la zone qu’il n’a pas su interpréter. Une route listée ici n’est ni protégée ni ouverte : Taxo n’en dit rien.');
    case 'architecture':return <>{note}<ArchitecturePage base={base} request={request} scanId={current.id} project={project}/></>;
    case 'limites':return <>{note}<AnalysisLimits scan={current} coverage={coverage}/></>;
    default:return <>{note}<OverviewPage scan={current} latest={latest} pending={running?pendingEvaluators(run):undefined} routes={counts} coverage={coverage}/></>;
    }
  }
  function welcome(){
    if(running)return null;
    return <section className="welcome"><div className="glyph">⌘</div><h2>Prêt pour la première analyse</h2><p>Taxo vous montrera ce qu’il comprend de votre projet, et ce qu’il ne sait pas encore déterminer.</p>
      <button type="button" className="primary" disabled={busy} onClick={analyze}>Lancer la première analyse</button><p className="muted">Java · TypeScript · Python · React · Spring Boot</p></section>;
  }
  return <div className="layout">
    <header className="page-head"><div className="head-start"><a className="top-brand" href={href('overview')}><BrandMark/><span className="top-brand-text"><strong>Taxo</strong><small>Software Intelligence</small></span></a>
      <TopMenu running={running} latest={scanId&&scanId!==latest?.id?showLatest:undefined} analysis={close=><AnalysisCommand project={project}
        latest={latest} running={running} canAnalyze={!!selected&&!busy&&!loading} onAnalyze={analyze} onClose={close}/>}/></div></header>
    <aside>
    {!loading&&<ProjectSwitcher key={projects.length} projects={projects} selected={selected} status={shown?since(shown.created_at):''} busy={busy}
      onOpen={open} onAdd={add}/>}
    {selected&&<ResultsNav items={navItems} current={route.page}/>}
    <p className="aside-note">Analyse locale · v0.1<br/>Vos fichiers restent sur votre machine.</p></aside>
    <main>
    {error&&<div role="alert" className="error">{error}</div>}
    {run&&run.status!=='done'&&!(route.page==='analyses'&&!route.id)&&<AnalysisProgress run={run}/>}
    {loading?<output>Chargement…</output>:page()}
    </main>
  </div>;
}
