// Formulaire de consultation de l'historique Git (TAXO-EVAL-01) : rien n'est lu sans un nombre explicite.
import {useState, type FormEvent} from 'react';
import {consultRequest, MAX_COMMITS} from './history';

type Handlers = {onConsult:(path:string)=>unknown; onError:(message:string)=>void};

/** Valide la saisie : une adresse a consulter, ou le message qui explique le refus. */
export function submitConsult(event:Pick<FormEvent,'preventDefault'>, base:string, value:string, {onConsult, onError}:Handlers){
  event.preventDefault();
  const request=consultRequest(base,value);
  return 'error' in request?onError(request.error):onConsult(request.path);
}

/** Recopie la saisie telle quelle : c'est submitConsult qui la valide. */
export const typed=(set:(value:string)=>void)=>(event:{target:{value:string}})=>set(event.target.value);

export function ConsultForm({base, busy, onConsult, onError}:Readonly<{base:string; busy:boolean} & Handlers>){
  const [count,setCount]=useState('');
  return <form className="consult" onSubmit={e=>submitConsult(e,base,count,{onConsult,onError})}>
    <label htmlFor="commit-count">Derniers commits</label>
    <input id="commit-count" type="number" min={1} max={MAX_COMMITS} required value={count} onChange={typed(setCount)} placeholder="nombre"/>
    <button type="submit" className="secondary" disabled={busy}>Afficher</button>
  </form>;
}
