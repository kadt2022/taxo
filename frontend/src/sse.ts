// Flux d'evenements serveur (TAXO-UX-02), lus avec fetch : le meme lecteur sert au GET d'une analyse et au
// POST d'une question a Minia (EventSource ne sait pas envoyer de corps).
export type ServerEvent<T=unknown> = {id?:string; type:string; data:T};

/** Decoupe un texte SSE en evenements complets ; rend aussi le reste, encore incomplet. */
export function parseEvents(buffer:string):{events:ServerEvent[]; rest:string}{
  const blocks=buffer.replace(/\r\n/g,'\n').split('\n\n');
  const rest=blocks.pop()??'';
  const events:ServerEvent[]=[];
  for(const block of blocks){
    const fields:Record<string,string>={};
    for(const line of block.split('\n')){
      if(!line||line.startsWith(':'))continue;
      const at=line.indexOf(':');
      const key=at<0?line:line.slice(0,at), value=at<0?'':line.slice(at+1).replace(/^ /,'');
      fields[key]=key==='data'&&fields.data!==undefined?`${fields.data}\n${value}`:value;
    }
    if(fields.data!==undefined)events.push({id:fields.id, type:fields.event??'message', data:JSON.parse(fields.data)});
  }
  return {events, rest};
}

/** Evenements d'une reponse en flux, au fur et a mesure qu'ils arrivent. */
export async function* readEvents(body:ReadableStream<Uint8Array>):AsyncGenerator<ServerEvent>{
  const reader=body.getReader(), decoder=new TextDecoder();
  let buffer='';
  for(;;){
    const {done, value}=await reader.read();
    buffer+=done?decoder.decode():decoder.decode(value,{stream:true});
    const parsed=parseEvents(done?`${buffer}\n\n`:buffer);
    buffer=parsed.rest;
    yield* parsed.events;
    if(done)return;
  }
}

/** Ouvre un flux ; une reponse en erreur leve son message, comme les autres appels du portail. */
export async function openStream(url:string, init?:RequestInit, fetcher:typeof fetch=fetch){
  const response=await fetcher(url, init);
  if(!response.ok||!response.body){
    const body=await response.json().catch(()=>null);
    throw new Error(typeof body?.detail==='string'?body.detail:`La requête a échoué (${response.status}).`);
  }
  return readEvents(response.body);
}
