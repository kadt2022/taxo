// Vue d'ensemble d'un projet analyse (TAXO-UI-01) : ce que Taxo a compris du logiciel, pas comment il l'a compris.
// Chaque carte vient des donnees de l'analyse ; ce que Taxo ne sait pas encore determiner est dit « non analyse »,
// jamais presente comme un resultat.
export type SnapshotReference = {repository:string; commit:string; mode:'COMMIT'|'WORKING_TREE'; dirty?:boolean; content_fingerprint?:string};
export type EvaluationSummary = {
  execution_id:string; evaluator_id:string; producer_version:string; status:string;
  started_at:string; finished_at:string; duration_seconds:number;
  fact_count:number; coverage_count:number; warning_count:number;
  relations:Record<string,number>;
  coverage:{coverage_type:string; count:number; subjects:string[]}[];
  snapshot:SnapshotReference;
};
export type Scan = {id:string; created_at:string; files_count?:number; commit?:string|null; snapshot?:SnapshotReference|null;
  facts?:{technology:string; file:string; method:string}[]; warnings?:string[];
  evaluation_summary?:EvaluationSummary; evaluations?:EvaluationSummary[]};

export type CardState = 'known'|'partial'|'failed'|'unknown';
export type Card = {id:string; title:string; value:string; detail:string; state:CardState};

/** Toutes les executions de l'analyse ; une analyse ancienne n'a que le resume de l'inventaire. */
export function evaluationsOf(scan:Scan):EvaluationSummary[]{
  if(scan.evaluations?.length)return scan.evaluations;
  return scan.evaluation_summary?[scan.evaluation_summary]:[];
}

export function technologiesOf(scan:Scan){
  return [...new Set((scan.facts??[]).map(fact=>fact.technology))];
}

const count=(value:number)=>value.toLocaleString('fr-CA');
const SHOWN=4;
/** Les premieres technologies, puis combien d'autres : la liste complete est dans la section Technologies. */
export const shortList=(items:string[])=>items.length>SHOWN?`${items.slice(0,SHOWN).join(' · ')} · +${items.length-SHOWN} autres`:items.join(' · ');
const NOT_YET=(what:string):Omit<Card,'id'|'title'>=>({value:'Non analysé', state:'unknown',
  detail:`Taxo ne sait pas encore identifier ${what}. Rien n’est affirmé à ce sujet.`});

function history(git:EvaluationSummary|undefined):Omit<Card,'id'|'title'>{
  if(!git)return {value:'Non analysé', state:'unknown', detail:'Cette analyse n’a pas lu l’historique Git : relancez l’analyse globale.'};
  if(git.status==='FAILED')return {value:'Non analysé', state:'failed', detail:'La lecture de l’historique Git a échoué : voir les détails de l’analyse.'};
  const commits=`${count(git.relations.HAS_COMMIT??0)} commits analysés`;
  if(git.status==='PARTIAL')return {value:commits, state:'partial', detail:'Historique Git lu en partie : une partie n’a pas été analysée par Taxo.'};
  return {value:commits, state:'known', detail:'Historique Git disponible : consultez-le dans la section Historique.'};
}

function source(scan:Scan){
  const snapshot=scan.snapshot??scan.evaluation_summary?.snapshot;
  if(!snapshot)return 'Fichiers du dossier analysé.';
  const commit=snapshot.commit.slice(0,12);
  if(snapshot.mode==='COMMIT')return `Contenu du commit ${commit}.`;
  return `Dossier de travail au commit ${commit}${snapshot.dirty?', modifications non commitées incluses':''}.`;
}

/** Les cartes de la vue d'ensemble, toujours dans le meme ordre. */
export function overviewCards(scan:Scan):Card[]{
  const evaluations=evaluationsOf(scan);
  const inventory=evaluations.find(item=>item.evaluator_id==='taxo.inventory');
  const git=evaluations.find(item=>item.evaluator_id==='taxo.git');
  const technologies=technologiesOf(scan);
  return [
    {id:'technologies', title:'Technologies', state:'known',
      value:technologies.length?shortList(technologies):'Aucune technologie reconnue',
      detail:technologies.length?'Reconnues par les noms de fichiers et les dépendances déclarées.':'Aucun fichier ni aucune dépendance déclarée ne correspond à une technologie que Taxo connaît.'},
    {id:'project', title:'Projet', state:inventory?.status==='PARTIAL'?'partial':'known',
      value:`${count(scan.files_count??0)} fichiers analysés`, detail:source(scan)},
    {id:'history', title:'Historique', ...history(git)},
    {id:'architecture', title:'Architecture', ...NOT_YET('les modules du projet')},
    {id:'api', title:'API', ...NOT_YET('les routes exposées')},
    {id:'security', title:'Sécurité', ...NOT_YET('les règles de sécurité')},
  ];
}

/** Resultat de l'analyse, dit en une phrase ; les avertissements deviennent des points a verifier. */
export function outcome(scan:Scan){
  const evaluations=evaluationsOf(scan);
  const points=evaluations.reduce((total,item)=>total+item.warning_count,0)+new Set(scan.warnings??[]).size;
  const state=evaluations.some(item=>item.status==='FAILED')?'Analyse terminée, une partie a échoué'
    :evaluations.some(item=>item.status==='PARTIAL')?'Analyse terminée, en partie':'Analyse terminée';
  return points?`${state} · ${count(points)} point${points>1?'s':''} à vérifier`:state;
}

/** Sections proposees : seulement celles qui correspondent a une capacite reelle de Taxo. */
export function sections(scan:Scan|undefined){
  const items=[{id:'vue-ensemble', label:'Vue d’ensemble'}, {id:'technologies', label:'Technologies'}];
  return [...(scan?items:[]), {id:'historique', label:'Historique'}];
}

export function ProjectNav({scan}:Readonly<{scan:Scan|undefined}>){
  return <nav className="project-nav" aria-label="Sections du projet">
    {sections(scan).map(item=><a key={item.id} href={`#${item.id}`}>{item.label}</a>)}
  </nav>;
}

const BADGES:Record<CardState,string|null>={known:null, partial:'En partie', failed:'Échec', unknown:'Non analysé'};

export function ProjectOverview({scan}:Readonly<{scan:Scan}>){
  return <section className="overview" id="vue-ensemble" aria-label="Vue d’ensemble">
    <p className="outcome" role="status">{outcome(scan)}</p>
    <h2>Vue d’ensemble</h2>
    <div className="cards">
      {overviewCards(scan).map(card=><article key={card.id} className={`card card-${card.state}`} aria-label={card.title}>
        <h3>{card.title}{BADGES[card.state]&&card.value!==BADGES[card.state]&&<span className="badge">{BADGES[card.state]}</span>}</h3>
        <strong>{card.value}</strong>
        <p>{card.detail}</p>
      </article>)}
    </div>
  </section>;
}
