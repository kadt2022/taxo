// Vue d'ensemble d'un projet analyse (TAXO-UI-01, TAXO-UI-03) : ce que Taxo a compris du logiciel, pas comment il
// l'a compris. Chaque carte vient des donnees de l'analyse ; ce que Taxo ne sait pas encore determiner est dit
// « non analyse », jamais presente comme un resultat. Des comptes, jamais un pourcentage : aucun score n'est invente.
import {COVERAGE, EVALUATORS, label, reference} from './vocabulary';
import type {RouteState, RoutesResult} from './routes';

export type SnapshotReference = {repository:string; commit:string; mode:'COMMIT'|'WORKING_TREE'; dirty?:boolean; content_fingerprint?:string};
export type EvaluationSummary = {
  execution_id:string; evaluator_id:string; producer_version:string; status:string;
  started_at:string; finished_at:string; duration_seconds:number;
  fact_count:number; coverage_count:number; warning_count:number; warnings?:string[];
  relations:Record<string,number>;
  coverage:{coverage_type:string; count:number; subjects:string[]}[];
  snapshot:SnapshotReference;
};
export type Scan = {id:string; created_at:string; files_count?:number; commit?:string|null; snapshot?:SnapshotReference|null;
  facts?:{technology:string; file:string; method:string}[]; warnings?:string[];
  evaluation_summary?:EvaluationSummary; evaluations?:EvaluationSummary[]};

export type CardState = 'known'|'partial'|'failed'|'unknown';
/** Une part d'une repartition : chaque part est un compte de faits, jamais une estimation. */
export type Segment = {label:string; count:number; tone:'ok'|'info'|'warn'|'muted'};
/** Une carte : un chiffre et son unite, quelques lignes, une repartition eventuelle, un lien vers le detail. */
export type Card = {id:string; title:string; state:CardState; value:string; unit?:string; lines:string[]; bar?:Segment[];
  link?:{href:string; label:string}};
type Body = Omit<Card,'id'|'title'>;

// Carte -> evaluateur qui la nourrit : pendant une nouvelle analyse, une carte reste marquee tant que
// son evaluateur n'a pas termine.
export const CARD_SOURCES:Record<string,string[]>={project:['taxo.inventory', 'taxo.git'],
  architecture:['taxo.structure', 'taxo.spring-boot'], api:['taxo.spring-api'], security:['taxo.spring-security']};

/** Toutes les executions de l'analyse ; une analyse ancienne n'a que le resume de l'inventaire. */
export function evaluationsOf(scan:Scan):EvaluationSummary[]{
  if(scan.evaluations?.length)return scan.evaluations;
  return scan.evaluation_summary?[scan.evaluation_summary]:[];
}

export function technologiesOf(scan:Scan){
  return [...new Set((scan.facts??[]).map(fact=>fact.technology))];
}

const count=(value:number)=>value.toLocaleString('fr-CA');
/** « 1 module », « 3 modules » : le nombre et son nom, accordé. */
const counted=(value:number, one:string, many:string)=>`${count(value)} ${value>1?many:one}`;
/** Le nom seul, accordé au nombre : il accompagne le grand chiffre d'une carte. */
const noun=(value:number, one:string, many:string)=>value>1?many:one;
const SHOWN=4;
/** Les premieres technologies, puis combien d'autres : la liste complete est dans la section Technologies. */
export const shortList=(items:string[])=>items.length>SHOWN?`${items.slice(0,SHOWN).join(' · ')} · +${items.length-SHOWN} autres`:items.join(' · ');

const UNKNOWN=(line:string):Body=>({value:'Non analysé', state:'unknown', lines:[line]});
const FAILED=(line:string):Body=>({value:'Non analysé', state:'failed', lines:[line]});
const stateOf=(summary:EvaluationSummary|undefined):CardState=>summary?.status==='PARTIAL'?'partial':'known';
const UNREAD=new Set(['NOT_INTERPRETED', 'READ_ERROR']);

/** Le projet : ses fichiers, ses modules et applications, son historique, ses technologies. */
function project(scan:Scan, inventory:EvaluationSummary|undefined, structure:EvaluationSummary|undefined,
  boot:EvaluationSummary|undefined, git:EvaluationSummary|undefined):Body{
  const files=scan.files_count??0;
  const lines:string[]=[];
  if(structure&&structure.status!=='FAILED'){
    const parts=[counted(structure.relations.CONTAINS??0, 'module', 'modules')];
    if(boot&&boot.status!=='FAILED')parts.unshift(counted(boot.relations.BUILT_FROM??0, 'application', 'applications'));
    lines.push(parts.join(' · '));
  }
  if(git?.status==='FAILED')lines.push('Historique Git : lecture échouée');
  else if(git)lines.push(counted(git.relations.HAS_COMMIT??0, 'commit', 'commits'));
  const technologies=technologiesOf(scan);
  if(technologies.length)lines.push(shortList(technologies));
  return {value:count(files), unit:`${noun(files, 'fichier analysé', 'fichiers analysés')}`, state:stateOf(inventory), lines,
    ...(git&&git.status!=='FAILED'?{link:{href:'#historique', label:'Voir l’historique'}}:{})};
}

/** Les routes par etat etabli, et ce qui les rend incompletes : tout vient des faits de la page Routes. */
export type RouteCounts = Record<RouteState, number> & {reserved:number; missing:number};
export function routeCounts(result:RoutesResult):RouteCounts{
  const counts:RouteCounts={PROTECTED:0, PERMITS_ALL:0, NOT_INTERPRETED:0, NO_CONCLUSION:0, reserved:0, missing:result.unestablished.length};
  for(const row of result.routes){
    counts[row.state]+=1;
    if(row.gaps.length)counts.reserved+=1;
  }
  return counts;
}

/** Les routes relevees par l'evaluateur Spring API (TAXO-04) : une route est un endpoint et la methode qui le traite. */
function api(spring:EvaluationSummary|undefined, routes:RouteCounts|undefined):Body{
  if(!spring)return UNKNOWN('Cette analyse n’a pas cherché les routes : relancez l’analyse globale.');
  if(spring.status==='FAILED')return FAILED('La recherche des routes a échoué : voir les détails de l’analyse.');
  const total=spring.relations.HANDLED_BY??0;
  const body:Body={value:count(total), unit:noun(total, 'route', 'routes'), state:stateOf(spring),
    lines:[total?'Contrôleurs Spring MVC, chaque route prouvée à la ligne.':'Aucune route Spring MVC dans les sources Java.'],
    link:{href:'#routes', label:'Explorer les routes'}};
  if(!routes||!total)return body;
  const bar:Segment[]=[{label:noun(total-routes.reserved, 'établie', 'établies'), count:total-routes.reserved, tone:'ok'},
    {label:'avec réserve', count:routes.reserved, tone:'warn'}];
  if(routes.missing)bar.push({label:noun(routes.missing, 'peut manquer', 'peuvent manquer'), count:routes.missing, tone:'muted'});
  return {...body, bar, lines:[]};
}

/** Les modules et ce qui s'en construit, lus dans les fichiers de build (TAXO-E1) et les applications Spring Boot. */
function architecture(structure:EvaluationSummary|undefined, boot:EvaluationSummary|undefined):Body{
  if(!structure)return UNKNOWN('Cette analyse n’a pas lu la structure du dépôt : relancez l’analyse globale.');
  if(structure.status==='FAILED')return FAILED('La lecture de la structure a échoué : voir les détails de l’analyse.');
  const modules=structure.relations.CONTAINS??0;
  const lines=[counted(structure.relations.DEPENDS_ON??0, 'dépendance', 'dépendances')];
  if(boot&&boot.status!=='FAILED')lines.push(counted(boot.relations.BUILT_FROM??0, 'application Spring Boot', 'applications Spring Boot'));
  const services=structure.relations.BUILT_FROM??0;
  if(services)lines.push(counted(services, 'service compose', 'services compose'));
  lines.push('Lu dans les fichiers de build, sans rien exécuter.');
  return {value:count(modules), unit:noun(modules, 'module', 'modules'), state:stateOf(structure), lines,
    link:{href:'#details', label:'Voir le détail'}};
}

/** Ce que Taxo etablit de la protection des routes ; sans le detail par route, il ne compte que les regles lues. */
function security(spring:EvaluationSummary|undefined, routes:RouteCounts|undefined):Body{
  if(!spring)return UNKNOWN('Cette analyse n’a pas lu la sécurité : relancez l’analyse globale.');
  if(spring.status==='FAILED')return FAILED('La lecture de la sécurité a échoué : voir les détails de l’analyse.');
  const link={href:'#routes', label:'Explorer la sécurité'};
  if(!routes){
    const rules=(spring.relations.AUTHORIZED_BY??0)+(spring.relations.PERMITS_ALL??0);
    return {value:count(rules), unit:noun(rules, 'règle de sécurité lue', 'règles de sécurité lues'), state:stateOf(spring), link,
      lines:['Le détail par route est dans la section Routes.']};
  }
  return {value:count(routes.PROTECTED), unit:noun(routes.PROTECTED, 'route protégée', 'routes protégées'), state:stateOf(spring), link,
    // La barre et sa legende disent deja chaque etat.
    lines:[],
    bar:[{label:noun(routes.PROTECTED, 'protégée', 'protégées'), count:routes.PROTECTED, tone:'ok'},
      {label:'permitAll()', count:routes.PERMITS_ALL, tone:'info'},
      {label:noun(routes.NOT_INTERPRETED, 'non interprétée', 'non interprétées'), count:routes.NOT_INTERPRETED, tone:'warn'},
      {label:'sans conclusion', count:routes.NO_CONCLUSION, tone:'muted'}]};
}

/** Les zones que Taxo n'a pas su lire ou interpreter, par analyseur : ce qu'il ne sait pas, dit en clair. */
export type Gap = {evaluator:string; type:string; count:number; subjects:string[]};
export function gapsOf(scan:Scan):Gap[]{
  return evaluationsOf(scan).flatMap(item=>item.coverage.filter(group=>UNREAD.has(group.coverage_type)&&group.count>0)
    .map(group=>({evaluator:item.evaluator_id, type:group.coverage_type, count:group.count, subjects:group.subjects})))
    .sort((a,b)=>b.count-a.count||a.evaluator.localeCompare(b.evaluator));
}

function limits(scan:Scan):Body{
  if(!evaluationsOf(scan).length)return UNKNOWN('Cette analyse ne détaille pas sa couverture : relancez l’analyse globale.');
  const gaps=gapsOf(scan);
  const total=gaps.reduce((sum,gap)=>sum+gap.count,0);
  const analysers=new Set(gaps.map(gap=>gap.evaluator)).size;
  return {value:count(total), unit:noun(total, 'zone non interprétée', 'zones non interprétées'), state:'known',
    lines:[total?`chez ${counted(analysers, 'analyseur', 'analyseurs')}, chacune avec sa raison.`
      :'Tout ce que les analyseurs ont parcouru a été lu. Cela ne couvre que ce qu’ils savent analyser.'],
    link:{href:'#limites', label:'Voir les limites'}};
}

/** Les cartes de la vue d'ensemble, toujours dans le meme ordre. */
export function overviewCards(scan:Scan, routes?:RouteCounts):Card[]{
  const evaluations=evaluationsOf(scan);
  const find=(id:string)=>evaluations.find(item=>item.evaluator_id===id);
  const structure=find('taxo.structure'), boot=find('taxo.spring-boot');
  return [
    {id:'project', title:'Projet', ...project(scan, find('taxo.inventory'), structure, boot, find('taxo.git'))},
    {id:'api', title:'API', ...api(find('taxo.spring-api'), routes)},
    {id:'architecture', title:'Architecture', ...architecture(structure, boot)},
    {id:'security', title:'Sécurité', ...security(find('taxo.spring-security'), routes)},
    {id:'data', title:'Données', ...UNKNOWN('Taxo ne sait pas encore identifier les entités ni les bases de données. Rien n’est affirmé à ce sujet.')},
    {id:'limits', title:'Limites', ...limits(scan)},
  ];
}

/** L'instantane analyse, dit en clair : commit et moment de l'analyse. */
export function analysedAt(scan:Scan){
  const snapshot=scan.snapshot??scan.evaluation_summary?.snapshot;
  return {commit:snapshot?.commit.slice(0,12)??'', working:snapshot?.mode==='WORKING_TREE',
    date:scan.created_at?new Date(scan.created_at).toLocaleString('fr-CA', {dateStyle:'medium', timeStyle:'short'}):''};
}

/** Resultat de l'analyse, dit en une phrase ; les avertissements deviennent des points a verifier. */
export function outcome(scan:Scan){
  const evaluations=evaluationsOf(scan);
  // Un avertissement de l'inventaire figure aussi dans scan.warnings : les resumes font foi, l'ancien champ sert de repli.
  const points=evaluations.length?evaluations.reduce((total,item)=>total+item.warning_count,0):new Set(scan.warnings??[]).size;
  const state=evaluations.some(item=>item.status==='FAILED')?'Analyse terminée, une partie a échoué'
    :evaluations.some(item=>item.status==='PARTIAL')?'Analyse terminée, en partie':'Analyse terminée';
  return points?`${state} · ${count(points)} point${points>1?'s':''} à vérifier`:state;
}

/** Tonalite du resultat : succes, partiel ou echec, pour la pastille qui l'accompagne. */
export function outcomeState(scan:Scan){
  const statuses=evaluationsOf(scan).map(item=>item.status);
  return statuses.includes('FAILED')?'failed':statuses.includes('PARTIAL')?'partial':'ok';
}

/** Sections proposees : seulement celles qui correspondent a une capacite reelle de Taxo. */
export function sections(scan:Scan|undefined){
  const items=[{id:'vue-ensemble', label:'Vue d’ensemble'}, {id:'technologies', label:'Technologies'}, {id:'limites', label:'Limites'},
    {id:'routes', label:'Routes'}];
  return [...(scan?items:[]), {id:'historique', label:'Historique'}];
}

/** Cle d'un panneau propre a un projet : unique parmi ses voisins, sinon React duplique le panneau a chaque changement. */
export const panelKey=(panel:string, projectId:string)=>`${panel}:${projectId}`;

export function ProjectNav({scan}:Readonly<{scan:Scan|undefined}>){
  return <nav className="project-nav" aria-label="Sections du projet">
    {sections(scan).map(item=><a key={item.id} href={`#${item.id}`}>{item.label}</a>)}
  </nav>;
}

// Icones au trait, purement decoratives : le titre de la carte porte le sens.
const ICONS:Record<string,string>={
  technologies:'M4 7h16M4 12h16M4 17h10',
  project:'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  history:'M12 8v4l3 2M3 12a9 9 0 1 0 3-6.7M3 4v4h4',
  architecture:'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  api:'M8 8l-4 4 4 4M16 8l4 4-4 4M13 6l-2 12',
  security:'M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z',
  data:'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  limits:'M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'};

export function CardIcon({id}:Readonly<{id:string}>){
  return <svg className="card-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[id]??ICONS.project}/></svg>;
}

const BADGES:Record<CardState,string|null>={known:null, partial:'En partie', failed:'Échec', unknown:null};

/** Une repartition en barre, avec sa legende : les parts vides restent dans la legende, pas dans la barre. */
export function CardBar({segments}:Readonly<{segments:Segment[]}>){
  const total=segments.reduce((sum,item)=>sum+item.count,0);
  return <div className="card-split">
    {total>0&&<div className="card-bar" aria-hidden="true">{segments.filter(item=>item.count).map(item=>
      <span key={item.label} className={`tone-${item.tone}`} style={{flexGrow:item.count}}/>)}</div>}
    <ul>{segments.map(item=><li key={item.label}><span className={`dot tone-${item.tone}`} aria-hidden="true"/>{count(item.count)} {item.label}</li>)}</ul>
  </div>;
}

export function ProjectOverview({scan, pending, routes, project}:Readonly<{scan:Scan; pending?:string[]; routes?:RouteCounts;
  project?:{name:string}}>){
  const refreshing=pending!==undefined;
  const stale=(id:string)=>refreshing&&(CARD_SOURCES[id]??[]).some(source=>pending.includes(source));
  const at=analysedAt(scan);
  return <section className={`overview${refreshing?' is-refreshing':''}`} id="vue-ensemble" aria-label="Vue d’ensemble" aria-busy={refreshing}>
    <div className="overview-head">
      <div>
        <h2>Vue d’ensemble</h2>
        <p>Ce que Taxo a établi sur ce logiciel, preuves à l’appui, et ce qu’il ne sait pas encore.</p>
        {refreshing?<p className="outcome outcome-running" role="status">Nouvelle analyse en cours…</p>
          :<p className={`outcome outcome-${outcomeState(scan)}`} role="status">{outcome(scan)}</p>}
      </div>
      <dl className="overview-meta">
        <div><dt>Dépôt</dt><dd>{project?.name??(scan.snapshot?.repository??'')}</dd></div>
        <div><dt>Commit</dt><dd><code>{at.commit||'—'}</code>{at.working&&<span className="muted"> · dossier de travail</span>}</dd></div>
        <div><dt>Analyse</dt><dd>{at.date||'—'}</dd></div>
      </dl>
    </div>
    <div className="cards">
      {overviewCards(scan, routes).map(card=><article key={card.id} className={`card card-${card.state}${stale(card.id)?' card-stale':''}`} aria-label={card.title}>
        <h3><CardIcon id={card.id}/>{card.title}{BADGES[card.state]&&<span className="badge">{BADGES[card.state]}</span>}</h3>
        <strong className="card-value">{card.value}</strong>
        {card.unit&&<span className="card-unit">{card.unit}</span>}
        {card.bar&&<CardBar segments={card.bar}/>}
        {card.lines.map(line=><p key={line}>{line}</p>)}
        {card.link&&<span className="card-fill" aria-hidden="true"/>}
        {card.link&&<a className="card-link" href={card.link.href}>{card.link.label} <span aria-hidden="true">→</span></a>}
      </article>)}
    </div>
  </section>;
}

/** Ce que Taxo ne sait pas encore, par analyseur, avec des exemples : la liste complete est dans les details. */
export function AnalysisLimits({scan}:Readonly<{scan:Scan}>){
  const gaps=gapsOf(scan);
  return <section className="results limits" id="limites" aria-label="Limites de l’analyse">
    <div className="section-heading"><div><h2>Limites de l’analyse</h2><p>Les zones que Taxo n’a pas su lire ou interpréter, par analyseur. Une zone listée ici n’est ni absente ni sûre : Taxo n’en dit rien.</p></div></div>
    {gaps.length?<div className="table-wrap"><table><thead><tr><th>Analyseur</th><th>Nature</th><th>Nombre</th><th>Exemples</th></tr></thead><tbody>
      {gaps.map(gap=><tr key={gap.evaluator+gap.type}><td>{label(EVALUATORS,gap.evaluator)}</td><td>{label(COVERAGE,gap.type)}</td><td>{count(gap.count)}</td>
        <td>{gap.subjects.map(value=><code className="coverage-subject" key={value}>{reference(value)}</code>)}{gap.count>gap.subjects.length&&<span className="muted">+ {count(gap.count-gap.subjects.length)} autres</span>}</td></tr>)}
    </tbody></table></div>:<p className="empty">{evaluationsOf(scan).length?'Aucune zone non interprétée parmi ce que les analyseurs savent lire.':'Cette analyse ne détaille pas sa couverture.'}</p>}
  </section>;
}
