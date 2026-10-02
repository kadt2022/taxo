// Une page par fonction (TAXO-UI-05) : l'adresse `#/page[/id][?a=…&b=…]` dit ou l'on est. Le hash suffit : le
// portail reste un fichier statique, un rechargement rouvre la meme page, et Precedent revient a la page d'avant.
import {useEffect, useState} from 'react';

export const PAGES=['overview', 'analyses', 'comparaisons', 'interroger', 'technologies', 'routes', 'architecture', 'securite',
  'donnees', 'historique', 'limites', 'non-interpretees'] as const;
export type Page=typeof PAGES[number];
export type Route={page:Page; id?:string; params:URLSearchParams};

/** Une adresse lue ; une page inconnue ramene a Overview plutot qu'a une page vide. */
export function parse(hash:string):Route{
  const raw=hash.replace(/^#\/?/, '');
  const at=raw.indexOf('?');
  const path=at<0?raw:raw.slice(0, at), params=new URLSearchParams(at<0?'':raw.slice(at+1));
  const [name, id]=path.split('/').filter(Boolean).map(part=>decodeURIComponent(part));
  const page=(PAGES as readonly string[]).includes(name)?name as Page:'overview';
  return {page, id:page==='overview'?undefined:id, params};
}

/** L'adresse d'une page, de l'element qu'elle montre, et de ses parametres. */
export function href(page:Page, id?:string, params?:Record<string, string|undefined>){
  const query=new URLSearchParams(Object.entries(params??{}).filter((entry):entry is [string, string]=>!!entry[1]));
  const path=page==='overview'?'#/':`#/${page}${id?`/${encodeURIComponent(id)}`:''}`;
  const search=query.toString();
  return search?`${path}?${search}`:path;
}

export function go(target:string, place:Pick<Location, 'hash'>=window.location){
  place.hash=target;
}

type Hashed=Pick<Window, 'addEventListener'|'removeEventListener'> & {location:Pick<Location, 'hash'>};

/** La page affichee, suivie a chaque changement d'adresse. */
export function useRoute(view:Hashed=window):Route{
  const [route,setRoute]=useState(()=>parse(view.location.hash));
  useEffect(()=>{
    const follow=()=>setRoute(parse(view.location.hash));
    view.addEventListener('hashchange', follow);
    return ()=>view.removeEventListener('hashchange', follow);
  },[view]);
  return route;
}
