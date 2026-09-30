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
export type Card = {id:string; title:string; value:string; detail:string; state:CardState; link?:{href:string; label:string}};

// Carte -> evaluateur qui la nourrit : pendant une nouvelle analyse, une carte reste marquee tant que
// son evaluateur n'a pas termine.
export const CARD_SOURCES:Record<string,string>={technologies:'taxo.inventory', project:'taxo.inventory', history:'taxo.git',
  architecture:'taxo.structure', api:'taxo.spring-api', security:'taxo.spring-security'};

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
const SHOWN=4;
/** Les premieres technologies, puis combien d'autres : la liste complete est dans la section Technologies. */
export const shortList=(items:string[])=>items.length>SHOWN?`${items.slice(0,SHOWN).join(' · ')} · +${items.length-SHOWN} autres`:items.join(' · ');
const NOT_YET=(what:string):Omit<Card,'id'|'title'>=>({value:'Non analysé', state:'unknown',
  detail:`Taxo ne sait pas encore identifier ${what}. Rien n’est affirmé à ce sujet.`});

function history(git:EvaluationSummary|undefined):Omit<Card,'id'|'title'>{
  if(!git)return {value:'Non analysé', state:'unknown', detail:'Cette analyse n’a pas lu l’historique Git : relancez l’analyse globale.'};
  if(git.status==='FAILED')return {value:'Non analysé', state:'failed', detail:'La lecture de l’historique Git a échoué : voir les détails de l’analyse.'};
  const commits=counted(git.relations.HAS_COMMIT??0, 'commit analysé', 'commits analysés');
  if(git.status==='PARTIAL')return {value:commits, state:'partial', detail:'Historique Git lu en partie : une partie n’a pas été analysée par Taxo.'};
  return {value:commits, state:'known', detail:'Historique Git disponible : consultez-le dans la section Historique.'};
}

const UNREAD=new Set(['NOT_INTERPRETED', 'READ_ERROR']);

/** Les modules et ce qui s'en construit, lus dans les fichiers de build (TAXO-E1) et les applications Spring Boot. */
function architecture(structure:EvaluationSummary|undefined, boot:EvaluationSummary|undefined):Omit<Card,'id'|'title'>{
  if(!structure)return {value:'Non analysé', state:'unknown', detail:'Cette analyse n’a pas lu la structure du dépôt : relancez l’analyse globale.'};
  if(structure.status==='FAILED')return {value:'Non analysé', state:'failed', detail:'La lecture de la structure a échoué : voir les détails de l’analyse.'};
  const modules=structure.relations.CONTAINS??0;
  const parts=[counted(structure.relations.DEPENDS_ON??0, 'dépendance entre modules', 'dépendances entre modules')];
  if(boot&&boot.status!=='FAILED')parts.push(counted(boot.relations.BUILT_FROM??0, 'application Spring Boot', 'applications Spring Boot'));
  const services=structure.relations.BUILT_FROM??0;
  if(services)parts.push(counted(services, 'service compose construit', 'services compose construits'));
  const value=modules?counted(modules, 'module', 'modules'):'Aucun module déclaré';
  const detail=`${parts.join(' · ')}. Lu dans les fichiers de build, sans rien exécuter.`;
  const unread=structure.coverage.some(group=>UNREAD.has(group.coverage_type)&&group.count>0);
  return {value, detail, state:structure.status==='PARTIAL'?'partial':'known',
    ...(unread?{link:{href:'#limites', label:'Voir ce qui n’a pas été lu'}}:{})};
}

export type RouteCounts = Record<RouteState, number>;
/** Les routes par etat etabli : chaque etat vient d'un fait, jamais d'une supposition. */
export function routeCounts(result:RoutesResult):RouteCounts{
  const counts:RouteCounts={PROTECTED:0, PERMITS_ALL:0, NOT_INTERPRETED:0, NO_CONCLUSION:0};
  for(const row of result.routes)counts[row.state]+=1;
  return counts;
}

/** Ce que Taxo etablit de la protection des routes ; sans le detail par route, il ne compte que les regles lues. */
function security(spring:EvaluationSummary|undefined, routes:RouteCounts|undefined):Omit<Card,'id'|'title'>{
  if(!spring)return {value:'Non analysé', state:'unknown', detail:'Cette analyse n’a pas lu la sécurité : relancez l’analyse globale.'};
  if(spring.status==='FAILED')return {value:'Non analysé', state:'failed', detail:'La lecture de la sécurité a échoué : voir les détails de l’analyse.'};
  const state=spring.status==='PARTIAL'?'partial':'known';
  const link={href:'#routes', label:'Voir la protection de chaque route'};
  if(!routes){
    const rules=(spring.relations.AUTHORIZED_BY??0)+(spring.relations.PERMITS_ALL??0);
    return {value:rules?counted(rules, 'règle de sécurité lue', 'règles de sécurité lues'):'Aucune règle de sécurité lue', state, link,
      detail:'Le détail par route est dans la section Routes.'};
  }
  const value=counted(routes.PROTECTED, 'route protégée', 'routes protégées');
  const detail=[counted(routes.PERMITS_ALL, 'ouverte à tous (permitAll)', 'ouvertes à tous (permitAll)'),
    counted(routes.NOT_INTERPRETED, 'non interprétée', 'non interprétées'), counted(routes.NO_CONCLUSION, 'sans conclusion', 'sans conclusion')]
    .join(' · ');
  return {value, state, link, detail:`${detail}. Une route n’est dite protégée que si un fait le prouve.`};
}

/** Les zones que Taxo n'a pas su lire ou interpreter, par analyseur : ce qu'il ne sait pas, dit en clair. */
export type Gap = {evaluator:string; type:string; count:number; subjects:string[]};
export function gapsOf(scan:Scan):Gap[]{
  return evaluationsOf(scan).flatMap(item=>item.coverage.filter(group=>UNREAD.has(group.coverage_type)&&group.count>0)
    .map(group=>({evaluator:item.evaluator_id, type:group.coverage_type, count:group.count, subjects:group.subjects})))
    .sort((a,b)=>b.count-a.count||a.evaluator.localeCompare(b.evaluator));
}

function limits(scan:Scan):Omit<Card,'id'|'title'>{
  if(!evaluationsOf(scan).length)return {value:'Non analysé', state:'unknown', detail:'Cette analyse ne détaille pas sa couverture : relancez l’analyse globale.'};
  const total=gapsOf(scan).reduce((sum,gap)=>sum+gap.count,0);
  if(!total)return {value:'Aucune zone non interprétée', state:'known', detail:'Tout ce que les analyseurs ont parcouru a été lu. Cela ne couvre que ce qu’ils savent analyser.'};
  return {value:counted(total, 'zone non interprétée', 'zones non interprétées'), state:'known',
    link:{href:'#limites', label:'Voir chaque zone'}, detail:'Chacune est dite avec l’analyseur concerné. Rien n’y est deviné.'};
}

/** Les routes relevees par l'evaluateur Spring API (TAXO-04) : une route est un endpoint et la methode qui le traite. */
function api(spring:EvaluationSummary|undefined):Omit<Card,'id'|'title'>{
  if(!spring)return {value:'Non analysé', state:'unknown', detail:'Cette analyse n’a pas cherché les routes : relancez l’analyse globale.'};
  if(spring.status==='FAILED')return {value:'Non analysé', state:'failed', detail:'La recherche des routes a échoué : voir les détails de l’analyse.'};
  const routes=spring.relations.HANDLED_BY??0;
  const plural=routes>1?'s':'';
  let value='Aucune route Spring';
  if(routes)value=`${count(routes)} route${plural} Spring relevée${plural}`;
  if(spring.status==='PARTIAL')return {value, state:'partial',
    detail:'Certaines routes n’ont pas pu être interprétées : voir les points à vérifier. Rien n’est deviné.'};
  return {value, state:'known', detail:routes?'Contrôleurs Spring MVC, chaque route prouvée à la ligne (tests exclus).'
    :'Aucune route Spring MVC trouvée dans les sources Java (tests exclus).'};
}

function source(scan:Scan){
  const snapshot=scan.snapshot??scan.evaluation_summary?.snapshot;
  if(!snapshot)return 'Fichiers du dossier analysé.';
  const commit=snapshot.commit.slice(0,12);
  if(snapshot.mode==='COMMIT')return `Contenu du commit ${commit}.`;
  return `Dossier de travail au commit ${commit}${snapshot.dirty?', modifications non commitées incluses':''}.`;
}

/** Un lien vers la section qui detaille la carte, seulement si Taxo y a quelque chose a montrer. */
const linked=(card:Omit<Card,'id'|'title'>, href:string, text:string)=>
  card.state==='known'||card.state==='partial'?{...card, link:{href, label:text}}:card;

/** Les cartes de la vue d'ensemble, toujours dans le meme ordre. */
export function overviewCards(scan:Scan, routes?:RouteCounts):Card[]{
  const evaluations=evaluationsOf(scan);
  const find=(id:string)=>evaluations.find(item=>item.evaluator_id===id);
  const inventory=find('taxo.inventory'), git=find('taxo.git'), spring=find('taxo.spring-api');
  const technologies=technologiesOf(scan);
  return [
    {id:'technologies', title:'Technologies', state:'known',
      value:technologies.length?shortList(technologies):'Aucune technologie reconnue',
      detail:technologies.length?'Reconnues par les noms de fichiers et les dépendances déclarées.':'Aucun fichier ni aucune dépendance déclarée ne correspond à une technologie que Taxo connaît.'},
    {id:'project', title:'Projet', state:inventory?.status==='PARTIAL'?'partial':'known',
      value:`${count(scan.files_count??0)} fichiers analysés`, detail:source(scan)},
    {id:'history', title:'Historique', ...linked(history(git), '#historique', 'Consulter les commits')},
    {id:'architecture', title:'Architecture', ...architecture(find('taxo.structure'), find('taxo.spring-boot'))},
    {id:'api', title:'API', ...linked(api(spring), '#routes', 'Voir les routes')},
    {id:'security', title:'Sécurité', ...security(find('taxo.spring-security'), routes)},
    {id:'data', title:'Données', ...NOT_YET('les entités ni les bases de données')},
    {id:'limits', title:'Limites de l’analyse', ...limits(scan)},
  ];
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

const BADGES:Record<CardState,string|null>={known:null, partial:'En partie', failed:'Échec', unknown:'Non analysé'};

export function ProjectOverview({scan, pending, routes}:Readonly<{scan:Scan; pending?:string[]; routes?:RouteCounts}>){
  const refreshing=pending!==undefined;
  const stale=(id:string)=>refreshing&&pending.includes(CARD_SOURCES[id]);
  return <section className={`overview${refreshing?' is-refreshing':''}`} id="vue-ensemble" aria-label="Vue d’ensemble" aria-busy={refreshing}>
    {refreshing?<p className="outcome outcome-running" role="status">Nouvelle analyse en cours…</p>
      :<p className={`outcome outcome-${outcomeState(scan)}`} role="status">{outcome(scan)}</p>}
    <h2>Vue d’ensemble</h2>
    <div className="cards">
      {overviewCards(scan, routes).map(card=><article key={card.id} className={`card card-${card.state}${stale(card.id)?' card-stale':''}`} aria-label={card.title}>
        <h3><CardIcon id={card.id}/>{card.title}{BADGES[card.state]&&card.value!==BADGES[card.state]&&<span className="badge">{BADGES[card.state]}</span>}</h3>
        <strong>{card.value}</strong>
        <p>{card.detail}</p>
        {card.link&&<a className="card-link" href={card.link.href}>{card.link.label} →</a>}
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
