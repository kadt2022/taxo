// Minia pendant qu'elle travaille (TAXO-UX-02) : ses etapes reelles, puis sa reponse au fil de l'eau.
// Le texte diffuse est provisoire : les faits cites et la reponse validee n'arrivent qu'a la fin.
import type {ServerEvent} from './sse';

type Stage = {stage:string; state:'running'|'done'; label:string; count:number|null};
export type MiniaLive<T=unknown> = {stages:Stage[]; text:string; result:T|null; failure:string};

export const startMinia=<T,>():MiniaLive<T>=>({stages:[], text:'', result:null, failure:''});

export function reduceMinia<T>(live:MiniaLive<T>, event:ServerEvent):MiniaLive<T>{
  const data=event.data as Record<string, any>;
  if(event.type==='minia.stage'){
    const known=live.stages.some(item=>item.stage===data.stage);
    return {...live, stages:known?live.stages.map(item=>item.stage===data.stage?data as Stage:item):[...live.stages, data as Stage]};
  }
  if(event.type==='minia.delta')return {...live, text:live.text+data.text};
  if(event.type==='minia.completed')return {...live, result:data as T};
  // Un echec efface le texte provisoire : une reponse coupee ou declinee n'est jamais montree a moitie.
  if(event.type==='minia.failed')return {...live, text:'', failure:data.message};
  return live;
}

/** Libelle d'une etape terminee, avec ce qu'elle a trouve quand c'est utile. */
export function stageText(stage:Stage){
  if(stage.stage==='facts'&&stage.state==='done'&&stage.count!==null)
    return `${stage.label} : ${stage.count} fait${stage.count>1?'s':''}`;
  return stage.label;
}

/** Suit une question a Minia jusqu'a sa reponse (ou son echec). */
export async function ask<T>(open:()=>Promise<AsyncIterable<ServerEvent>>, update:(change:(live:MiniaLive<T>)=>MiniaLive<T>)=>void){
  update(()=>startMinia<T>());
  for await(const event of await open())update(live=>reduceMinia(live, event));
}

export const askButton=(busy:boolean, idle:string)=>busy?'● Minia travaille…':idle;

export function MiniaProgress({live}:Readonly<{live:MiniaLive}>){
  return <section className="minia-progress" aria-label="Minia travaille" aria-live="polite">
    <p className="progress-title">Minia examine les faits Taxo…</p>
    <ol>{live.stages.map(stage=><li key={stage.stage} className={`step step-${stage.state}`}>
      <span className="step-mark" aria-hidden="true">{stage.state==='done'?'✓':'●'}</span>
      <span className="step-label">{stageText(stage)}{stage.state==='running'&&'…'}</span>
    </li>)}</ol>
    {live.text&&<blockquote className="minia-draft"><span className="badge">en cours d’écriture</span>{live.text}</blockquote>}
    {live.failure&&<p role="alert" className="error">{live.failure}</p>}
  </section>;
}

export const questionInit=(body:unknown):RequestInit=>({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
