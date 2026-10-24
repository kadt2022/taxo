// Ouvrir une partie de l'Explorer dans sa propre fenêtre (le code d'une classe, ou le schéma), en grand. La fenêtre est la même page
// du portail, à une adresse qui dit quoi montrer (`plein=code` ou `plein=schema`) : elle relit le projet, l'analyse et le nœud depuis
// cette adresse, et ne partage aucun état avec la fenêtre d'origine.
import {useState} from 'react';
import {href, type Route} from '../nav';
import {ExpandIcon} from './icons';

export type Full='code'|'schema';
export const FULL_VALUES:readonly string[]=['code', 'schema'];
const FEATURES='popup=yes,width=1360,height=900';

/** L'adresse absolue de l'Explorer dans une fenêtre : tout ce que la page courante porte, plus ce qu'il faut montrer. */
export function windowAddress(route:Pick<Route, 'params'>, place:Pick<Location, 'origin'|'pathname'>, extra:Record<string, string>){
  const kept=Object.fromEntries(route.params);
  return `${place.origin}${place.pathname}${href('explorer', undefined, {...kept, ...extra})}`;
}

/** Le bouton « Agrandir » : ouvre l'adresse dans une nouvelle fenêtre ; un navigateur qui la bloque est dit, jamais ignoré. */
export function OpenWindow({address, label, title, text, className}:Readonly<{address:string; label:string; title:string; text?:string;
  className?:string}>){
  const [blocked,setBlocked]=useState(false);
  const open=()=>setBlocked(globalThis.open(address, '_blank', FEATURES)===null);
  return <>
    <button type="button" className={className} aria-label={label} title={title} onClick={open}><ExpandIcon/>{text}</button>
    {blocked&&<span role="alert" className="error">Le navigateur a bloqué la nouvelle fenêtre : autorisez-la pour ce site.</span>}
  </>;
}
