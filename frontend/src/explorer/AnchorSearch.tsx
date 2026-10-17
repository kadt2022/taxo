// Choisir le point de départ (TAXO-01J § 9) : les références de l'analyse qui commencent par la saisie, par
// `find_references`. La demande part après une courte pause ; seule la dernière compte ; la page suivante sur demande.
import {useEffect, useId, useRef, useState, type ReactNode} from 'react';
import {findReferences, type Query, type ReferencePage} from './protocol';
import {searchOf} from './relations';
import {useNaming} from './Naming';
import {SearchIcon, LayersIcon} from './icons';

export const PAUSE=250;

type Found={page:ReferencePage; type?:string; prefix:string};

/** `lead` et `tail` : les cartes posées avant et après le point de départ et le type, sur la même rangée (l'analyse explorée,
 * les réglages du parcours). */
export function AnchorSearch({query, types, onPick, lead, tail}:Readonly<{query:Query; types:string[]; onPick:(reference:string)=>void;
  lead?:ReactNode; tail?:ReactNode}>){
  const id=useId(), named=useNaming();
  const [text,setText]=useState(''), [type,setType]=useState('');
  const [found,setFound]=useState<Found|null>(null), [error,setError]=useState(''), [more,setMore]=useState(false);
  const latest=useRef(0);
  useEffect(()=>{
    const wanted=searchOf(text, type, types);
    const token=++latest.current;
    setError('');
    if(!wanted.prefix.trim()){setFound(null);return undefined;}
    const controller=new AbortController();
    const timer=setTimeout(()=>{
      findReferences(query, wanted.prefix, wanted.type, null, controller.signal).then(page=>{
        if(token===latest.current)setFound({page, ...wanted});
      }, reason=>{if(token===latest.current&&(reason as Error).name!=='AbortError'){setFound(null);setError((reason as Error).message);}});
    }, PAUSE);
    return ()=>{clearTimeout(timer);controller.abort();};
  },[text, type, query, types]);
  async function next(){
    if(!found?.page.next)return;
    const token=latest.current;
    setMore(true);
    try{
      const page=await findReferences(query, found.prefix, found.type, found.page.next);
      if(token===latest.current)setFound({...found, page:{items:[...found.page.items, ...page.items], next:page.next}});
    }catch(reason){if(token===latest.current)setError((reason as Error).message);}
    finally{setMore(false);}
  }
  return <section className="explorer-search" aria-label="Choisir le point de départ">
    <div className="explorer-search-fields">
      {lead}
      <label className="explorer-card" htmlFor={`${id}-text`}>Point de départ<span className="explorer-input"><SearchIcon/>
        <input id={`${id}-text`} value={text} maxLength={200} autoComplete="off"
          placeholder="Début d’une référence : GET /orders, OrderController…" onChange={event=>setText(event.target.value)}/></span></label>
      <label className="explorer-card" htmlFor={`${id}-type`}>Type<span className="explorer-input"><LayersIcon/>
        <select id={`${id}-type`} value={type} onChange={event=>setType(event.target.value)}>
          <option value="">Tous les types</option>{types.map(item=><option key={item} value={item}>{item}</option>)}</select></span></label>
      {tail}
    </div>
    {error&&<p role="alert" className="error">{error}</p>}
    {found&&(found.page.items.length?<ul className="explorer-suggestions" aria-label="Références trouvées">
      {found.page.items.map(item=><li key={item.reference}><button type="button" className="link" onClick={()=>onPick(item.reference)}>
        <span className="explorer-type">{item.type}</span> {named(item.reference)}</button></li>)}</ul>
      :<p className="muted">Aucune référence de cette analyse ne commence par « {found.prefix} »{found.type?` parmi le type ${found.type}`:''}.</p>)}
    {found?.page.next&&<button type="button" className="ghost" disabled={more} onClick={next}>{more?'Chargement…':'Références suivantes'}</button>}
  </section>;
}
