// Le thème du cadre du graphe : sombre ou clair, au choix de la personne. Il part du thème de l'appareil, puis se souvient de
// son choix dans ce navigateur (une commodité : sans stockage, il suit l'appareil). Partagé par le cadre et l'encadré de
// limites qui le suit, pour qu'ils changent ensemble.
import {useSyncExternalStore} from 'react';

export type GraphTheme='dark'|'light';
const KEY='taxo.explorer.graph-theme';
const listeners=new Set<()=>void>();

function device():GraphTheme{
  return typeof globalThis.matchMedia==='function'&&globalThis.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
}
function remembered():GraphTheme|null{
  try{
    const value=globalThis.localStorage?.getItem(KEY);
    return value==='dark'||value==='light'?value:null;
  }catch{return null;}
}
let chosen:GraphTheme|null=null;
const current=():GraphTheme=>chosen??remembered()??device();

export function setGraphTheme(theme:GraphTheme){
  chosen=theme;
  try{globalThis.localStorage?.setItem(KEY, theme);}catch{/* le choix vaut pour cette page seulement */}
  listeners.forEach(listener=>listener());
}

/** Le thème du cadre, et de quoi le basculer. */
export function useGraphTheme(){
  const theme=useSyncExternalStore(listener=>{listeners.add(listener);return ()=>{listeners.delete(listener);};}, current, ()=>'light' as GraphTheme);
  return {theme, toggle:()=>setGraphTheme(theme==='dark'?'light':'dark')};
}

/** Pour les tests : oublier le choix, retourner au thème de l'appareil. */
export function resetGraphTheme(){
  chosen=null;
  try{globalThis.localStorage?.removeItem(KEY);}catch{/* rien à oublier */}
  listeners.forEach(listener=>listener());
}
