// Les pages du portail (TAXO-UI-05) : Overview est un tableau de bord, chaque fonction a sa page. Rien n'est calcule ici
// que le portail ne lise deja : les analyses, leurs resumes et leurs faits, tels que l'API les rend.
import {useEffect, useState, type FormEvent} from 'react';
import {ComparisonView, day, proof, sentence, Phrase, sideLabel, type ComparedFact, type Side} from './comparison';
import {AnalysisDetails} from './details';
import {href, go, type Route} from './nav';
import {AnalysisLimits, evaluationsOf, gapsOf, ProjectOverview, technologiesOf, type RouteCounts, type Scan} from './overview';
import {ChoiceCard, ComparePicker, matches, NO_SEARCH, SearchFields, Source, type Choice, type Search} from './picker';
import {EVALUATORS, STATUSES, label} from './vocabulary';

type Request=<T>(path:string)=>Promise<T>;
type Project={id:string; name:string; path?:string};

/** Ce que la comparaison dit d'une analyse : son instantane, tel que le resume de l'analyse le rapporte. */
export function sideOf(scan:Scan):Side{
  return {id:scan.id, created_at:scan.created_at, snapshot:scan.evaluation_summary?.snapshot??scan.snapshot??null};
}

const MARKS:Record<string,string>={SUCCESS:'✓', PARTIAL:'◐', FAILED:'✕'};
const facts=(scan:Scan)=>evaluationsOf(scan).reduce((sum, item)=>sum+(item.fact_count??0), 0);

/** Les analyses du projet decrites par ce qu'elles ont enregistre ; relues quand une analyse s'ajoute. */
export function useChoices(base:string, request:Request, revision:string){
  const [choices,setChoices]=useState<Choice[]|null>(null), [error,setError]=useState('');
  useEffect(()=>{
    let active=true;
    setError('');
    request<Choice[]>(`${base}/comparisons/analyses`).then(value=>{if(active)setChoices(value);})
      .catch(reason=>{if(active)setError((reason as Error).message);});
    return ()=>{active=false;};
  },[base, revision]);
  return {choices, error};
}

/** Une autre analyse que la plus recente est affichee : chaque page le dit, et propose d'y revenir. */
export function DisplayedNote({scan, latest, onLatest}:Readonly<{scan:Scan; latest?:Scan; onLatest:()=>void}>){
  if(!latest||latest.id===scan.id)return null;
  return <output className="displayed-note"><span>Vous consultez une analyse antérieure — <strong>{day(scan.created_at)}</strong></span>
    <button type="button" className="ghost" onClick={onLatest}>Revenir à la dernière analyse</button></output>;
}

/** La premiere analyse du projet n'est pas encore enregistree : les pages qui lisent ses faits attendent sa fin. */
export function PendingPage(){
  return <section className="page"><PageHead title="Analyse en cours" intro="Cette page sera disponible à la fin de la première analyse du projet : elle lit des faits qui ne sont pas encore enregistrés."/>
    <a className="ghost" href={href('overview')}>← Suivre l’analyse dans Overview</a></section>;
}

/** Une adresse qui ne mene a aucune page. */
export function NotFoundPage(){
  return <section className="page"><PageHead title="Page introuvable" intro="Cette adresse ne correspond à aucune page de Taxo."/>
    <a className="ghost" href={href('overview')}>← Revenir à Overview</a></section>;
}

function PageHead({title, intro}:Readonly<{title:string; intro:string}>){
  return <div className="page-intro"><h1>{title}</h1><p>{intro}</p></div>;
}

/** Overview : un tableau de bord. Les cartes, les limites et l'analyse affichee ; lancer une analyse est une commande du menu Analyse. */
export function OverviewPage({scan, latest, pending, routes}:Readonly<{scan:Scan; latest?:Scan; pending?:string[]; routes?:RouteCounts}>){
  return <>
    <ProjectOverview scan={scan} pending={pending} routes={routes}/>
    <section className="overview-shown" aria-label="Analyse affichée">
      <div><span className="eyebrow">{latest&&latest.id!==scan.id?'Analyse affichée':'Dernière analyse'}</span>
        <strong>{day(scan.created_at)}</strong><code>{sideLabel(sideOf(scan))}</code></div>
      <div className="overview-actions">
        <a className="ghost" href={href('analyses', scan.id)}>Voir l’analyse</a>
        <a className="primary" href={href('comparaisons')}>Comparer deux analyses →</a>
      </div>
    </section>
  </>;
}

/** Analyses : ce que Taxo a observe, et quand. Chaque analyse s'ouvre ou se compare. */
export function AnalysesPage({base, request, revision, displayed}:Readonly<{base:string; request:Request; revision:string; displayed?:string}>){
  const {choices, error}=useChoices(base, request, revision);
  const [search,setSearch]=useState<Search>(NO_SEARCH);
  const found=choices?.filter(choice=>matches(choice, search))??[];
  return <section className="page analyses-page" aria-label="Analyses">
    <PageHead title="Analyses" intro="Ce que Taxo a observé, et quand : chaque analyse terminée, reconnue par sa date puis par le code qu’elle a lu."/>
    {error&&<div role="alert" className="error">{error}</div>}
    {!choices&&!error&&<output>Chargement des analyses…</output>}
    {choices&&<>
      <SearchFields search={search} onChange={setSearch} side="des analyses"/>
      <p className="choice-count">{found.length} analyse{found.length>1?'s':''} sur {choices.length}</p>
      <ul className="analysis-list">{found.map(choice=><li key={choice.id} className={choice.id===displayed?'displayed':undefined}>
        <ChoiceCard choice={choice}/>
        <div className="analysis-actions">{choice.id===displayed&&<span className="count-pill">Affichée</span>}
          <a className="ghost" href={href('analyses', choice.id)}>Ouvrir</a>
          <a className="ghost" href={href('comparaisons', 'choix', {a:choice.id})}>Comparer avec…</a></div>
      </li>)}</ul>
      {found.length===0&&<p className="muted">Aucune analyse ne répond à cette recherche.</p>}
    </>}
  </section>;
}

/** Une analyse : ce qu'elle a lu, ce qu'elle a produit, et ce qu'elle n'a pas su lire. */
export function AnalysisPage({base, request, revision, scan, displayed, onShow}:Readonly<{base:string; request:Request; revision:string;
  scan?:Scan; displayed?:string; onShow:(id:string)=>void}>){
  const {choices}=useChoices(base, request, revision);
  if(!scan)return <section className="page"><PageHead title="Analyse introuvable" intro="Cette analyse n’existe pas dans ce projet, ou elle a été interrompue."/>
    <a className="ghost" href={href('analyses')}>← Toutes les analyses</a></section>;
  const choice=choices?.find(item=>item.id===scan.id);
  const unknown=gapsOf(scan).reduce((sum, gap)=>sum+gap.count, 0);
  return <section className="page analysis-page" aria-label="Analyse">
    <a className="link back" href={href('analyses')}>← Toutes les analyses</a>
    <div className="analysis-head"><div><span className="eyebrow">Analyse</span><h1>{day(scan.created_at)}</h1></div>
      <div className="analysis-actions">
        <button type="button" className="ghost" disabled={scan.id===displayed} onClick={()=>onShow(scan.id)}>{scan.id===displayed?'Analyse affichée':'Afficher cette analyse'}</button>
        <a className="primary" href={href('comparaisons', 'choix', {a:scan.id})}>Comparer cette analyse avec… →</a></div></div>
    <dl className="analysis-facts">
      <div><dt>Code analysé</dt><dd>{choice?<Source choice={choice}/>:sideLabel(sideOf(scan))}</dd></div>
      <div><dt>Faits</dt><dd>{facts(scan).toLocaleString('fr-CA')}</dd></div>
      <div><dt>Zones inconnues</dt><dd>{unknown.toLocaleString('fr-CA')}</dd></div>
      <div><dt>Analyseurs</dt><dd><ul className="analysers">{evaluationsOf(scan).map(item=><li key={item.execution_id}>
        <span className={`analyser-state state-${item.status.toLowerCase()}`} aria-hidden="true">{MARKS[item.status]??'•'}</span>
        <span>{label(EVALUATORS, item.evaluator_id)} <span className="muted">{item.producer_version} · {label(STATUSES, item.status).toLowerCase()}</span></span></li>)}</ul></dd></div>
    </dl>
    <AnalysisLimits scan={scan}/>
    <AnalysisDetails scan={scan}/>
  </section>;
}

/** Comparaisons : choisir A et B, puis le resultat, chacun a son adresse. */
export function ComparisonsPage({base, request, route, project}:Readonly<{base:string; request:Request; route:Route; project?:Project}>){
  const a=route.params.get('a')??undefined, b=route.params.get('b')??undefined;
  if(a&&b&&route.id!=='choix')return <ComparisonView base={base} request={request} before={a} after={b} project={project}
    onClose={()=>go(href('overview'))} onSwap={()=>go(href('comparaisons', undefined, {a:b, b:a}))}
    onChange={()=>go(href('comparaisons', 'choix', {a, b}))}/>;
  return <ComparePicker key={`${a}:${b}`} base={base} request={request} initial={{before:a, after:b}}
    onClose={()=>go(href('overview'))} onCompare={(before, after)=>go(href('comparaisons', undefined, {a:before, b:after}))}/>;
}

/** Technologies : ce que les noms de fichiers et les dependances declarees revelent. */
export function TechnologiesPage({scan}:Readonly<{scan:Scan}>){
  const technologies=technologiesOf(scan), evidence=scan.facts??[];
  return <section className="results" aria-label="Technologies">
    <div className="section-heading"><div><h2>Technologies</h2><p>Reconnues par les noms de fichiers et les dépendances déclarées ; une dépendance déclarée ne prouve pas qu’elle est utilisée.</p></div></div>
    {technologies.length?<div className="tags">{technologies.map(item=><span key={item}>{item}</span>)}</div>:<p className="empty">Aucune technologie reconnue dans ce dossier.</p>}
    {evidence.length>0&&<details className="evidence-files"><summary>Fichiers justificatifs ({evidence.length})</summary><div className="table-wrap"><table>
      <thead><tr><th>Technologie</th><th>Fichier justificatif</th><th>Détection</th></tr></thead><tbody>{evidence.map(item=><tr key={item.technology+item.file}>
        <td>{item.technology}</td><td><code>{item.file}</code></td><td>{item.method==='manifest'?'Manifeste':'Nom de fichier'}</td></tr>)}</tbody></table></div></details>}
  </section>;
}

const GROUPS=[
  {relation:'CONTAINS', title:'Modules', empty:'Aucun module reconnu.'},
  {relation:'DEPENDS_ON', title:'Dépendances entre modules', empty:'Aucune dépendance déclarée entre modules.'},
  {relation:'BUILT_FROM', title:'Applications', empty:'Aucune application reconnue.'},
] as const;

/** Architecture : modules, dependances et applications, dits en phrases avec leur preuve, depuis les faits de la structure. */
export function ArchitecturePage({base, request, scanId, project}:Readonly<{base:string; request:Request; scanId:string; project?:Project}>){
  const [found,setFound]=useState<ComparedFact[]|null>(null), [error,setError]=useState('');
  useEffect(()=>{
    let active=true;
    setFound(null);setError('');
    request<ComparedFact[]>(`${base}/scans/${scanId}/facts?evaluator=taxo.structure`).then(value=>{if(active)setFound(value);})
      .catch(reason=>{if(active)setError((reason as Error).message);});
    return ()=>{active=false;};
  },[base, scanId]);
  return <section className="results architecture" aria-label="Architecture">
    <div className="section-heading"><div><h2>Architecture</h2><p>Ce que déclarent les fichiers de build : les modules du dépôt, leurs dépendances et les applications qu’ils construisent. Chaque phrase vient d’un fait, avec sa preuve.</p></div></div>
    {error&&<div role="alert" className="error">{error}</div>}
    {!found&&!error&&<output>Chargement de l’architecture…</output>}
    {found&&GROUPS.map(group=>{
      const items=found.filter(fact=>fact.relation===group.relation);
      return <div className="architecture-group" key={group.relation}><h3>{group.title} <span className="count-pill">{items.length}</span></h3>
        {items.length?<ul className="change-list">{items.map(fact=><li key={`${fact.subject}|${fact.object}`}>
          <p className="change-fact"><Phrase value={sentence(fact, project)}/></p>
          {fact.evidence?.[0]&&<p className="change-proof"><span className="proof">{proof(fact.evidence[0])}</span></p>}</li>)}</ul>
          :<p className="muted">{group.empty}</p>}</div>;})}
  </section>;
}

export function DataPage(){
  return <section className="results" aria-label="Données et stockage">
    <div className="section-heading"><div><h2>Données et stockage</h2><p>Bases de données, schémas, entités et accès aux données.</p></div></div>
    <p className="empty">Non analysé : aucun analyseur de données n’est encore branché. Taxo n’en dit donc rien, ni présence ni absence.</p>
  </section>;
}

/** Projets : sur quoi je travaille. Le projet actif est marque ; un autre s'ouvre, un nouveau s'ajoute. */
export function ProjectsPage({projects, selected, busy, adding, onOpen, onAdd}:Readonly<{projects:Project[]; selected:string; busy:boolean;
  adding:boolean; onOpen:(id:string)=>void; onAdd:(name:string, path:string)=>Promise<boolean>}>){
  const [open,setOpen]=useState(adding), [name,setName]=useState(''), [path,setPath]=useState('');
  useEffect(()=>{if(adding)setOpen(true);},[adding]);
  const form=open||projects.length===0;
  async function submit(event:FormEvent){
    event.preventDefault();
    if(await onAdd(name, path)){setName('');setPath('');setOpen(false);}
  }
  return <section className="page projects-page" aria-label="Projets">
    <PageHead title="Projets" intro="Sur quoi je travaille : les dossiers locaux que Taxo connaît. Ouvrir un projet en fait le projet actif de toutes les pages."/>
    {projects.length>0&&<ul className="project-list">{projects.map(item=><li key={item.id} className={item.id===selected?'active':undefined}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
      <div><strong>{item.name}</strong>{item.path&&<code>{item.path}</code>}</div>
      {item.id===selected?<span className="count-pill">Projet actif</span>
        :<button type="button" className="ghost" disabled={busy} onClick={()=>onOpen(item.id)}>Ouvrir</button>}
    </li>)}</ul>}
    {form?<form className="project-form" onSubmit={submit}>
      <h2>{projects.length?'Ajouter un projet':'Commencez avec un projet local'}</h2>
      <label>Nom<input required autoFocus maxLength={120} value={name} onChange={event=>setName(event.target.value)} placeholder="Mon application"/></label>
      <label>Dossier local<input required value={path} onChange={event=>setPath(event.target.value)} placeholder="D:\MonProjet"/></label>
      <div className="project-form-actions"><button type="submit" className="primary" disabled={busy}>Enregistrer le projet</button>
        {projects.length>0&&<button type="button" className="link" onClick={()=>setOpen(false)}>Annuler</button>}</div>
    </form>:<button type="button" className="ghost project-add" onClick={()=>setOpen(true)}><span aria-hidden="true">+</span> Ajouter un projet</button>}
  </section>;
}

/** Le projet actif, discret, en haut du menu vertical : il mene a la page Projets. */
export function ActiveProject({project, status}:Readonly<{project?:Project; status:string}>){
  return <a className="active-project" href={href('projets')}><span>Projet actif</span>
    <strong>{project?.name??'Aucun projet'}</strong>{status&&<small>Dernière analyse {status}</small>}</a>;
}
