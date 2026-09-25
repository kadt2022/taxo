// Vue d'ensemble d'un projet analyse (TAXO-UI-01) : ce que Taxo a compris du logiciel, pas comment il l'a compris.
// Chaque carte vient des donnees de l'analyse ; ce que Taxo ne sait pas encore determiner est dit « non analyse »,
// jamais presente comme un resultat.
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
export type Card = {id:string; title:string; value:string; detail:string; state:CardState};

// Carte -> evaluateur qui la nourrit : pendant une nouvelle analyse, une carte reste marquee tant que
// son evaluateur n'a pas termine.
export const CARD_SOURCES:Record<string,string>={technologies:'taxo.inventory', project:'taxo.inventory', history:'taxo.git'};

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
  const items=[{id:'vue-ensemble', label:'Vue d’ensemble'}, {id:'technologies', label:'Technologies'}];
  return [...(scan?items:[]), {id:'historique', label:'Historique'}];
}

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
  security:'M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z'};

export function CardIcon({id}:Readonly<{id:string}>){
  return <svg className="card-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[id]??ICONS.project}/></svg>;
}

const BADGES:Record<CardState,string|null>={known:null, partial:'En partie', failed:'Échec', unknown:'Non analysé'};

export function ProjectOverview({scan, pending}:Readonly<{scan:Scan; pending?:string[]}>){
  const refreshing=pending!==undefined;
  const stale=(id:string)=>refreshing&&pending.includes(CARD_SOURCES[id]);
  return <section className={`overview${refreshing?' is-refreshing':''}`} id="vue-ensemble" aria-label="Vue d’ensemble" aria-busy={refreshing}>
    {refreshing?<p className="outcome outcome-running" role="status">Nouvelle analyse en cours…</p>
      :<p className={`outcome outcome-${outcomeState(scan)}`} role="status">{outcome(scan)}</p>}
    <h2>Vue d’ensemble</h2>
    <div className="cards">
      {overviewCards(scan).map(card=><article key={card.id} className={`card card-${card.state}${stale(card.id)?' card-stale':''}`} aria-label={card.title}>
        <h3><CardIcon id={card.id}/>{card.title}{BADGES[card.state]&&card.value!==BADGES[card.state]&&<span className="badge">{BADGES[card.state]}</span>}</h3>
        <strong>{card.value}</strong>
        <p>{card.detail}</p>
      </article>)}
    </div>
  </section>;
}
