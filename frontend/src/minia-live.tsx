// Minia pendant qu'elle travaille (TAXO-UX-02) : ses etapes reelles, puis sa reponse au fil de l'eau.
// Le texte diffuse est provisoire : les faits cites et la reponse validee n'arrivent qu'a la fin.
import type {ServerEvent} from './sse';
import {stepText, type TrajectoryStep} from './exploration';
import {apiUrl} from './api';

type Stage = {stage:string; state:'running'|'done'; label:string; count:number|null};
// `trajectory` : les operations que Minia demande a Taxo, au fur et a mesure (MINIA-09).
// `requestId` : l'identifiant qui permet d'arreter la demande ; `stopped` : arretee par l'utilisateur (TAXO-UX-03).
export type MiniaLive<T=unknown> = {stages:Stage[]; text:string; result:T|null; failure:string; trajectory:TrajectoryStep[];
  requestId?:string; stopped:boolean};

export const startMinia=<T,>():MiniaLive<T>=>({stages:[], text:'', result:null, failure:'', trajectory:[], stopped:false});
export const STOPPED='Analyse arrêtée par l’utilisateur.';

export function reduceMinia<T>(live:MiniaLive<T>, event:ServerEvent):MiniaLive<T>{
  const data=event.data as Record<string, any>;
  if(event.type==='minia.stage'){
    const known=live.stages.some(item=>item.stage===data.stage);
    return {...live, stages:known?live.stages.map(item=>item.stage===data.stage?data as Stage:item):[...live.stages, data as Stage]};
  }
  if(event.type==='minia.started')return {...live, requestId:data.request_id};
  if(event.type==='minia.delta')return {...live, text:live.text+data.text};
  // Un arret n'est pas une erreur : la trajectoire reste, le brouillon s'efface, aucune reponse n'arrive.
  if(event.type==='minia.cancelled')return stoppedMinia(live);
  if(event.type==='minia.operation')return {...live, trajectory:[...live.trajectory, data as TrajectoryStep]};
  if(event.type==='minia.completed')return {...live, result:data as T};
  // Un echec efface le texte provisoire : une reponse coupee ou declinee n'est jamais montree a moitie.
  if(event.type==='minia.failed')return {...live, text:'', failure:data.message};
  return live;
}

export const stoppedMinia=<T,>(live:MiniaLive<T>):MiniaLive<T>=>({...live, text:'', stopped:true});

/** Demande au serveur d'arreter la demande : plus aucun tour, l'appel au fournisseur est coupe. */
export async function cancelMinia(requestId:string, fetcher:typeof fetch=fetch){
  try{await fetcher(apiUrl(`/api/minia/requests/${requestId}/cancel`), {method:'POST'});}
  catch{/* la connexion coupee suffit a arreter la demande cote serveur */}
}

/** Le moyen d'arreter une demande : couper le flux (AbortController) et prevenir le serveur. */
export function createStop(fetcher:typeof fetch=fetch){
  const controller=new AbortController();
  return {signal:controller.signal, stop:(requestId?:string)=>{
    if(requestId)void cancelMinia(requestId, fetcher);
    controller.abort();
  }};
}
export type MiniaStop = ReturnType<typeof createStop>;

/** Libelle d'une etape terminee, avec ce qu'elle a trouve quand c'est utile. */
export function stageText(stage:Stage){
  if(stage.stage==='facts'&&stage.state==='done'&&stage.count!==null)
    return `${stage.label} : ${stage.count} fait${stage.count>1?'s':''}`;
  if(stage.stage==='exploration'&&stage.count)return `${stage.label} : ${stage.count} opération${stage.count>1?'s':''}`;
  if(stage.stage==='verification'&&stage.count!==null)return `${stage.label} : ${stage.count} affirmation${stage.count>1?'s':''}`;
  return stage.label;
}

/** Suit une question a Minia jusqu'a sa reponse (ou son echec). */
export async function ask<T>(open:()=>Promise<AsyncIterable<ServerEvent>>, update:(change:(live:MiniaLive<T>)=>MiniaLive<T>)=>void){
  update(()=>startMinia<T>());
  try{
    for await(const event of await open())update(live=>reduceMinia(live, event));
  }catch(e){
    // L'utilisateur a arrete la demande : ce n'est pas une erreur a afficher.
    if((e as Error).name==='AbortError'){update(stoppedMinia);return;}
    throw e;
  }
}

export const askButton=(busy:boolean, idle:string)=>busy?'● Minia travaille…':idle;

/** `onStop` : le bouton Arreter, propose tant que Minia travaille (TAXO-UX-03). */
export function MiniaProgress({live, onStop}:Readonly<{live:MiniaLive; onStop?:()=>void}>){
  const working=!live.stopped&&!live.failure;
  return <section className={`minia-progress${live.stopped?' stopped':''}`} aria-label="Minia travaille" aria-live="polite">
    <div className="progress-heading">
      <p className="progress-title">{live.stopped?STOPPED:'Minia examine les faits Taxo…'}</p>
      {working&&onStop&&<button type="button" className="secondary stop" onClick={onStop}>Arrêter</button>}
    </div>
    <ol>{live.stages.map(stage=><li key={stage.stage} className={`step step-${live.stopped&&stage.state==='running'?'stopped':stage.state}`}>
      <span className="step-mark" aria-hidden="true">{stage.state==='done'?'✓':'●'}</span>
      <span className="step-label">{stageText(stage)}{stage.state==='running'&&!live.stopped&&'…'}</span>
    </li>)}</ol>
    {live.trajectory.length>0&&<ol className="trajectory live">{live.trajectory.map((step,index)=><li key={index}>{stepText(step)}</li>)}</ol>}
    {live.text&&<blockquote className="minia-draft"><span className="badge">en cours d’écriture</span>{live.text}</blockquote>}
    {live.failure&&<p role="alert" className="error">{live.failure}</p>}
  </section>;
}

export const questionInit=(body:unknown):RequestInit=>({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
