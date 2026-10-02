// Vue d'ensemble d'un projet analyse (TAXO-UI-01, TAXO-UI-03) : ce que Taxo a compris du logiciel, pas comment il
// l'a compris. Chaque carte vient des donnees de l'analyse ; ce que Taxo ne sait pas encore determiner est dit
// « non analyse », jamais presente comme un resultat. Des comptes, jamais un pourcentage : aucun score n'est invente.
import {href} from './nav';
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

export type CardState = 'known'|'failed'|'unknown';
/** Une part d'une repartition : chaque part est un compte de faits, jamais une estimation. */
export type Segment = {label:string; count:number; tone:'ok'|'info'|'warn'|'muted'};
/** Une carte : un chiffre et son unite, quelques lignes, une repartition eventuelle, un lien vers le detail. */
export type Card = {id:string; title:string; state:CardState; value:string; unit?:string; lines:string[]; bar?:Segment[];
  link?:{href:string; label:string}};
type Body = Omit<Card,'id'|'title'>;

// Carte -> evaluateur qui la nourrit : pendant une nouvelle analyse, une carte reste marquee tant que
// son evaluateur n'a pas termine.
export const CARD_SOURCES:Record<string,string[]>={project:['taxo.inventory'], git:['taxo.git'],
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
const UNREAD=new Set(['NOT_INTERPRETED', 'READ_ERROR']);

/** Le projet : ce que l'inventaire a effectivement parcouru. Les autres domaines ont leur propre carte. */
function project(scan:Scan, inventory:EvaluationSummary|undefined):Body{
  if(inventory?.status==='FAILED')return FAILED('L’inventaire du projet a échoué : voir les détails de l’analyse.');
  const files=scan.files_count??0;
  const technologies=technologiesOf(scan);
  return {value:count(files), unit:noun(files, 'fichier analysé', 'fichiers analysés'), state:'known',
    lines:technologies.length?[counted(technologies.length, 'technologie reconnue', 'technologies reconnues')]:[],
    link:{href:href('technologies'), label:'Voir les technologies'}};
}

/** Git est une capacité de premier rang : son historique n'est pas caché dans la carte Projet. */
function gitCard(git:EvaluationSummary|undefined):Body{
  if(!git)return UNKNOWN('Cette analyse n’a pas lu l’historique Git.');
  if(git.status==='FAILED')return FAILED('La lecture de l’historique Git a échoué : voir les détails de l’analyse.');
  const commits=git.relations.HAS_COMMIT??0;
  return {value:count(commits), unit:noun(commits, 'commit lu', 'commits lus'), state:'known', lines:[],
    link:{href:href('historique'), label:'Voir l’historique'}};
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
function api(spring:EvaluationSummary|undefined, _routes:RouteCounts|undefined):Body{
  if(!spring)return UNKNOWN('Cette analyse n’a pas cherché les routes.');
  if(spring.status==='FAILED')return FAILED('La recherche des routes a échoué : voir les détails de l’analyse.');
  const total=spring.relations.HANDLED_BY??0;
  return {value:count(total), unit:noun(total, 'route relevée', 'routes relevées'), state:'known', lines:[],
    link:{href:href('routes'), label:'Explorer les routes'}};
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
  return {value:count(modules), unit:noun(modules, 'module détecté', 'modules détectés'), state:'known',
    lines:lines.slice(0,2), link:{href:href('architecture'), label:'Explorer l’architecture'}};
}

/** Ce que Taxo etablit de la protection des routes ; sans le detail par route, il ne compte que les regles lues. */
function security(spring:EvaluationSummary|undefined, routes:RouteCounts|undefined):Body{
  if(!spring)return UNKNOWN('Cette analyse n’a pas lu la sécurité.');
  if(spring.status==='FAILED')return FAILED('La lecture de la sécurité a échoué : voir les détails de l’analyse.');
  const link={href:href('securite'), label:'Explorer la sécurité'};
  if(!routes){
    const rules=(spring.relations.AUTHORIZED_BY??0)+(spring.relations.PERMITS_ALL??0);
    return {value:count(rules), unit:noun(rules, 'règle de sécurité lue', 'règles de sécurité lues'), state:'known', link, lines:[]};
  }
  const total=routes.PROTECTED+routes.PERMITS_ALL+routes.NOT_INTERPRETED+routes.NO_CONCLUSION;
  const established=routes.PROTECTED+routes.PERMITS_ALL;
  return {value:count(total), unit:noun(total, 'route examinée', 'routes examinées'), state:'known', link,
    lines:[counted(established, 'statut de sécurité établi', 'statuts de sécurité établis')]};
}

/** Les zones que Taxo n'a pas su lire ou interpreter, par analyseur : ce qu'il ne sait pas, dit en clair. */
export type Gap = {evaluator:string; type:string; count:number; subjects:string[]};
export function gapsOf(scan:Scan):Gap[]{
  return evaluationsOf(scan).flatMap(item=>item.coverage.filter(group=>UNREAD.has(group.coverage_type)&&group.count>0)
    .map(group=>({evaluator:item.evaluator_id, type:group.coverage_type, count:group.count, subjects:group.subjects})))
    .sort((a,b)=>b.count-a.count||a.evaluator.localeCompare(b.evaluator));
}

/** Les cartes de la vue d'ensemble, toujours dans le meme ordre. */
export function overviewCards(scan:Scan, routes?:RouteCounts):Card[]{
  const evaluations=evaluationsOf(scan);
  const find=(id:string)=>evaluations.find(item=>item.evaluator_id===id);
  const structure=find('taxo.structure'), boot=find('taxo.spring-boot');
  return [
    {id:'project', title:'Projet', ...project(scan, find('taxo.inventory'))},
    {id:'git', title:'Git', ...gitCard(find('taxo.git'))},
    {id:'api', title:'API', ...api(find('taxo.spring-api'), routes)},
    {id:'architecture', title:'Architecture', ...architecture(structure, boot)},
    {id:'security', title:'Sécurité', ...security(find('taxo.spring-security'), routes)},
    {id:'data', title:'Données', ...UNKNOWN('Aucun analyseur de données n’est encore branché.')},
  ];
}

/** Cle d'un panneau propre a un projet : unique parmi ses voisins, sinon React duplique le panneau a chaque changement. */
export const panelKey=(panel:string, projectId:string)=>`${panel}:${projectId}`;

// Icones au trait, purement decoratives : le titre de la carte porte le sens.
const ICONS:Record<string,string>={
  technologies:'M4 7h16M4 12h16M4 17h10',
  project:'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  history:'M12 8v4l3 2M3 12a9 9 0 1 0 3-6.7M3 4v4h4',
  git:'M7 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM17 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 7v5a5 5 0 0 0 5 5h3M17 3v14',
  architecture:'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  api:'M8 8l-4 4 4 4M16 8l4 4-4 4M13 6l-2 12',
  security:'M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z',
  data:'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  limits:'M12 9v4M12 17h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'};

export function CardIcon({id}:Readonly<{id:string}>){
  return <svg className="card-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[id]??ICONS.project}/></svg>;
}

const BADGES:Record<CardState,string|null>={known:null, failed:'Échec', unknown:null};

/** Une repartition en barre, avec sa legende : les parts vides restent dans la legende, pas dans la barre. */
export function CardBar({segments}:Readonly<{segments:Segment[]}>){
  const total=segments.reduce((sum,item)=>sum+item.count,0);
  return <div className="card-split">
    {total>0&&<div className="card-bar" aria-hidden="true">{segments.filter(item=>item.count).map(item=>
      <span key={item.label} className={`tone-${item.tone}`} style={{flexGrow:item.count}}/>)}</div>}
    <ul>{segments.map(item=><li key={item.label}><span className={`dot tone-${item.tone}`} aria-hidden="true"/>{count(item.count)} {item.label}</li>)}</ul>
  </div>;
}

export function ProjectOverview({scan, pending, routes}:Readonly<{scan:Scan; pending?:string[]; routes?:RouteCounts}>){
  const refreshing=pending!==undefined;
  const stale=(id:string)=>refreshing&&(CARD_SOURCES[id]??[]).some(source=>pending.includes(source));
  const gaps=gapsOf(scan);
  const gapCount=gaps.reduce((sum,gap)=>sum+gap.count,0);
  const analysers=new Set(gaps.map(gap=>gap.evaluator)).size;
  return <section className={`overview${refreshing?' is-refreshing':''}`} id="vue-ensemble" aria-label="Vue d’ensemble" aria-busy={refreshing}>
    {refreshing&&<output className="refresh-note">Nouvelle analyse en cours…</output>}
    <div className="cards">
      {overviewCards(scan, routes).map(card=><article key={card.id} className={`card card-${card.state}${stale(card.id)?' card-stale':''}`} aria-label={card.title}>
        <h3><CardIcon id={card.id}/>{card.title}{BADGES[card.state]&&<span className="badge">{BADGES[card.state]}</span>}</h3>
        <strong className="card-value">{card.value}</strong>
        {card.unit&&<span className="card-unit">{card.unit}</span>}
        {card.lines.map(line=><p key={line}>{line}</p>)}
        {card.link&&<span className="card-fill" aria-hidden="true"/>}
        {card.link&&<a className="card-link" href={card.link.href}>{card.link.label} <span aria-hidden="true">→</span></a>}
      </article>)}
    </div>
    {evaluationsOf(scan).length>0&&<div className={`overview-limits${gapCount?' has-limits':''}`}>
      <div><strong>{gapCount?counted(gapCount, 'limite signalée', 'limites signalées'):'Aucune limite signalée'}</strong>
        <span>{gapCount?` · ${counted(analysers, 'analyseur concerné', 'analyseurs concernés')}`:' dans les périmètres parcourus'}</span></div>
      <a href={href('limites')}>Voir les limites <span aria-hidden="true">→</span></a>
    </div>}
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
