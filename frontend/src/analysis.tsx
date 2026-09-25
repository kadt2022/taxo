// Suivre une analyse pendant qu'elle travaille (TAXO-UX-02) : chaque etape affichee correspond a un evenement
// reel du serveur ; aucune barre ni pourcentage n'est invente. Les resultats d'un evaluateur remplacent les
// anciens des qu'il termine, sans attendre la fin de l'analyse.
import type {ServerEvent} from './sse';
import type {EvaluationSummary, Scan} from './overview';
import {EVALUATORS, label} from './vocabulary';

export type StepState = 'pending'|'running'|'done'|'failed';
export type Step = {id:string; label:string; state:StepState; detail:string};
export type Run = {status:'running'|'done'|'failed'; steps:Step[]; summaries:EvaluationSummary[];
  result:Partial<Scan>|null; scan:Scan|null; message:string};

const PREPARE='preparation', CONSOLIDATE='consolidation';

export function startRun():Run{
  return {status:'running', steps:[{id:PREPARE, label:'Préparation du projet', state:'running', detail:''}],
    summaries:[], result:null, scan:null, message:''};
}

const withStep=(run:Run, id:string, change:Partial<Step>):Run=>
  ({...run, steps:run.steps.map(step=>step.id===id?{...step, ...change}:step)});

/** Progression dite en clair : « Commits lus : 500 », « Fichiers lus : 250 / 320 ». */
export function progressText(data:{message:string; completed:number|null; total:number|null}){
  if(data.completed===null)return data.message;
  const done=data.completed.toLocaleString('fr-CA');
  return data.total===null?`${data.message} : ${done}`:`${data.message} : ${done} / ${data.total.toLocaleString('fr-CA')}`;
}

type Data = Record<string, any>;

export function reduce(run:Run, event:ServerEvent):Run{
  const data=event.data as Data;
  switch(event.type){
    case 'analysis.started':
      return {...run, steps:[run.steps[0],
        ...(data.evaluators as string[]).map(id=>({id, label:label(EVALUATORS,id), state:'pending' as StepState, detail:''})),
        {id:CONSOLIDATE, label:'Consolidation des résultats', state:'pending', detail:''}]};
    case 'snapshot.ready':
      return withStep(run, PREPARE, {state:'done', detail:`Commit ${String(data.commit).slice(0,12)}`});
    case 'evaluator.started':
      return withStep(run, data.evaluator, {state:'running'});
    case 'evaluator.progress':
      return withStep(run, data.evaluator, {detail:progressText(data as never)});
    case 'evaluator.completed':
      return {...withStep(run, data.evaluator, {state:'done'}), summaries:[...run.summaries, data.summary],
        result:data.result?{...run.result, ...data.result}:run.result};
    case 'evaluator.failed':
      return {...withStep(run, data.evaluator, {state:'failed', detail:'Analyse incomplète — voir le détail'}),
        summaries:[...run.summaries, data.summary]};
    case 'analysis.consolidating':
      return withStep(run, CONSOLIDATE, {state:'running'});
    case 'analysis.completed':
      return {...withStep(run, CONSOLIDATE, {state:'done'}), status:'done', scan:data.scan};
    case 'analysis.failed':
      return {...run, status:'failed', message:data.message,
        steps:run.steps.map(step=>step.state==='running'?{...step, state:'failed'}:step)};
    default:
      return run;
  }
}

/** Ce que l'ecran montre pendant l'analyse : l'ancienne analyse, completee par ce que la nouvelle a deja produit. */
export function liveScan(previous:Scan|undefined, run:Run):Scan|undefined{
  if(!previous&&!run.summaries.length)return undefined;
  const base:Scan=previous??{id:'en-cours', created_at:''};
  const fresh=new Set(run.summaries.map(item=>item.evaluator_id));
  const kept=(base.evaluations??(base.evaluation_summary?[base.evaluation_summary]:[])).filter(item=>!fresh.has(item.evaluator_id));
  return {...base, ...(run.result??{}), evaluations:[...run.summaries, ...kept]};
}

/** Evaluateurs dont les resultats affiches viennent encore de l'analyse precedente. */
export function pendingEvaluators(run:Run){
  return run.steps.filter(step=>step.id!==PREPARE&&step.id!==CONSOLIDATE&&step.state!=='done'&&step.state!=='failed').map(step=>step.id);
}

type Open = (url:string, lastEventId?:string)=>Promise<AsyncIterable<ServerEvent>|Iterable<ServerEvent>>;
const TERMINAL=new Set(['analysis.completed','analysis.failed']);
export const RECONNECTIONS=5;
export const LOST='Connexion perdue avec Taxo : l’analyse continue sur le serveur, relancez la page pour voir son résultat.';
const pause=(ms:number)=>new Promise(resolve=>setTimeout(resolve, ms));

/** Lance une analyse et suit ses evenements jusqu'a la fin, en reprenant apres le dernier recu si le flux se coupe. */
export async function follow(start:()=>Promise<{events:string}>, open:Open, onEvent:(event:ServerEvent)=>void,
  wait:(ms:number)=>Promise<unknown>=pause){
  const {events}=await start();
  let last:string|undefined, failures=0;
  for(;;){
    try{
      for await(const event of await open(events, last)){
        if(event.id){last=event.id;failures=0;}
        onEvent(event);
        if(TERMINAL.has(event.type))return;
      }
    }
    catch{/* coupure : on reprend apres le dernier evenement recu */}
    if(++failures>RECONNECTIONS)throw new Error(LOST);
    await wait(500*failures);
  }
}

const MARKS:Record<StepState,string>={pending:'○', running:'●', done:'✓', failed:'!'};

/** Texte suivi de points animes en CSS : le texte reste immobile, seul le span des points change. Un seul
 * element, pour que l'espacement d'un parent flex ne separe pas le texte de ses points. */
export const Working=({text}:Readonly<{text:string}>)=><span>{text}<span className="animated-dots" aria-hidden="true"/></span>;

export function AnalysisProgress({run}:Readonly<{run:Run}>){
  const evaluators=run.steps.filter(step=>step.id!==PREPARE&&step.id!==CONSOLIDATE);
  const finished=evaluators.filter(step=>step.state==='done'||step.state==='failed').length;
  const title=run.status==='running'?<Working text="Analyse en cours"/>:run.status==='done'?'Analyse terminée':'Analyse interrompue';
  return <section className={`progress progress-${run.status}`} aria-label="Progression de l’analyse" aria-live="polite">
    <p className="progress-title">{title}</p>
    <ol>{run.steps.map(step=><li key={step.id} className={`step step-${step.state}`}>
      <span className="step-mark" aria-hidden="true">{MARKS[step.state]}</span>
      <span className="step-label">{step.label}{step.state==='running'&&'…'}</span>
      {step.detail&&<span className="step-detail">{step.detail}</span>}
    </li>)}</ol>
    {run.message&&<p role="alert" className="error">{run.message}</p>}
    {evaluators.length>0&&<p className="muted">{finished} / {evaluators.length} analyses terminées</p>}
  </section>;
}

type Launch = {request:<T>(path:string, init?:RequestInit)=>Promise<T>; open:Open; setRun:(change:(run:Run|null)=>Run|null)=>void;
  addScan:(scan:Scan)=>void; setError:(message:string)=>void; setBusy:(busy:boolean)=>void};

/** Lance l'analyse globale d'un projet et fait vivre l'ecran avec ses evenements. */
export async function analyzeProject(projectId:string, {request, open, setRun, addScan, setError, setBusy}:Launch){
  setBusy(true);setError('');setRun(()=>startRun());
  try{
    await follow(()=>request<{events:string}>(`/projects/${projectId}/analyses`,{method:'POST'}), open, event=>{
      setRun(run=>run&&reduce(run, event));
      if(event.type==='analysis.completed')addScan((event.data as {scan:Scan}).scan);
    });
  }
  catch(e){
    const message=(e as Error).message;
    // Un lancement refuse n'a rien a montrer ; une analyse perdue de vue garde ses etapes, marquees interrompues.
    setRun(run=>run&&run.steps.length>1?reduce(run, {type:'analysis.failed', data:{message}}):null);
    if(message!==LOST)setError(message);
  }
  finally{setBusy(false);}
}
