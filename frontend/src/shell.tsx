// Coque de l'application : barre de menus, sélecteur de projet et menu vertical des résultats (TAXO-UI-04).
// Sorti de main.tsx pour être testé ; les effets prennent leur document et leur observateur en paramètre.
import {useEffect, useId, useRef, useState, type ReactNode} from 'react';
import {type RouteCounts, type Scan} from './overview';
import {href, type Page} from './nav';

export type Project = {id:string; name:string; path:string};
export type MenuItem = {label:string; href?:string; disabled?:boolean; run?:()=>void};
export type NavItem = {id:Page; label:string; count?:string; apart?:boolean; muted?:boolean};

export const ICON_PATHS:Record<string,string>={overview:'M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z',
  projets:'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  analyses:'M9 4h6M9 3h6v3H9zM6 5H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1M8 12h8M8 16h5',
  comparaisons:'M4 7h11M12 4l3 3-3 3M20 17H9M12 14l-3 3 3 3',
  explorer:'M7 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM21 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM21 19a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM7 11l10-5M7 13l10 5', interroger:'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2zM9 9h6M9 13h4',
  architecture:'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  technologies:'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5', routes:'M8 7l-5 5 5 5M16 7l5 5-5 5', details:'M4 6h16M4 12h16M4 18h10',
  limites:'M12 3l10 18H2zM12 10v5M12 18v.5', historique:'M12 7v5l3 2M3 12a9 9 0 1 0 3-6.7M3 4v5h5', securite:'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z',
  donnees:'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  'non-interpretees':'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8v5M12 16v.5'};

/** Icônes des menus globaux, au même trait que celles du menu vertical : une feuille, une courbe d'activité, une mise en page,
 * un point d'interrogation. */
export const MENU_ICONS:Record<string,string>={Fichier:'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h4',
  Analyse:'M3 12h4l3-7 4 14 3-7h4', Affichage:'M4 4h16v16H4zM4 9h16M9 9v11',
  Aide:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.6 9.2a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.5M12 17h.01'};

/** Le logo de Taxo : un réseau de faits, six nœuds reliés autour d'un centre. Dessiné, pas une image. */
export function BrandMark(){
  const id=useId();
  return <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
    <defs><linearGradient id={id} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#8fd0ff"/><stop offset="1" stopColor="#2f7df6"/></linearGradient></defs>
    <g className="brand-links">
      <path d="M16 5L25.53 10.5L25.53 21.5L16 27L6.47 21.5L6.47 10.5Z"/>
      <path d="M16 16L16 5M16 16L25.53 10.5M16 16L25.53 21.5M16 16L16 27M16 16L6.47 21.5M16 16L6.47 10.5"/>
      <path className="brand-depth" d="M16 5L25.53 21.5L6.47 21.5Z"/>
    </g>
    <g className="brand-nodes" fill={`url(#${id})`}>
      <circle cx="16" cy="5" r="2.6"/><circle cx="25.53" cy="10.5" r="2.6"/><circle cx="25.53" cy="21.5" r="2.6"/>
      <circle cx="16" cy="27" r="2.6"/><circle cx="6.47" cy="21.5" r="2.6"/><circle cx="6.47" cy="10.5" r="2.6"/>
      <circle cx="16" cy="16" r="3.6"/>
    </g>
  </svg>;
}

/** Les 7 premiers caractères du commit analysé, ou rien si l'analyse n'en porte pas. */
export function commitOf(scan:Scan){
  const sha=scan.snapshot?.commit??scan.commit;
  return typeof sha==='string'?sha.slice(0,7):'';
}

/** « il y a 12 min » : l'âge d'une analyse, en unités entières. */
export function since(iso?:string, now:number=Date.now()){
  if(typeof iso!=='string')return '';
  const minutes=Math.max(0,Math.round((now-new Date(iso).getTime())/60000));
  if(Number.isNaN(minutes))return '';
  if(minutes<1)return 'à l’instant';
  if(minutes<60)return `il y a ${minutes} min`;
  const hours=Math.round(minutes/60);
  return hours<24?`il y a ${hours} h`:`il y a ${Math.round(hours/24)} j`;
}

/** Le menu vertical : une entrée par page, groupées ; un compte seulement quand Taxo en a un. « Données » reste grisée tant
 * qu'aucun analyseur ne la nourrit, mais sa page dit pourquoi. */
export function navItemsOf(technologies:number, counts:(id:string)=>string|undefined, routes?:RouteCounts, analyses?:number):NavItem[]{
  return [{id:'overview', label:'Overview'},
    {id:'analyses', label:'Analyses', count:analyses?String(analyses):undefined, apart:true}, {id:'comparaisons', label:'Comparaisons'},
    {id:'explorer', label:'Explorer'}, {id:'interroger', label:'Interroger Taxo'},
    {id:'technologies', label:'Technologies', count:technologies?String(technologies):undefined, apart:true},
    {id:'routes', label:'Routes', count:counts('api')}, {id:'architecture', label:'Architecture', count:counts('architecture')},
    {id:'securite', label:'Sécurité', count:routes?String(routes.PROTECTED):undefined},
    {id:'donnees', label:'Données et stockage', muted:true},
    {id:'historique', label:'Historique Git', count:counts('git'), apart:true},
    {id:'limites', label:'Limites', apart:true},
    {id:'non-interpretees', label:'Non interprétées', count:routes?String(routes.NOT_INTERPRETED):undefined}];
}

type Listener = Pick<Document,'addEventListener'|'removeEventListener'>;

/** Referme un panneau au clic ailleurs ou sur Échap ; renvoie la fonction qui retire les écouteurs. */
export function closeOnOutside(box:{contains(node:Node):boolean}|null, close:()=>void, doc:Listener=document){
  const away=(event:Event)=>{if(!box?.contains(event.target as Node))close();};
  const escape=(event:Event)=>{if((event as KeyboardEvent).key==='Escape')close();};
  doc.addEventListener('mousedown',away);doc.addEventListener('keydown',escape);
  return()=>{doc.removeEventListener('mousedown',away);doc.removeEventListener('keydown',escape);};
}

type TopMenuProps = {analysis:(close:()=>void)=>ReactNode; running?:boolean; latest?:()=>void; initialOpen?:string|null};

/** Barre de menus façon application, réservée aux commandes globales : Fichier, Analyse, Affichage, Aide. La navigation est dans le
 * menu vertical. Analyse ouvre un panneau de commande ; les autres menus, une liste. Un seul menu ouvert à la fois ; Échap ou un clic
 * ailleurs le referme, et le survol change de menu une fois la barre activée. */
export function TopMenu({analysis, running=false, latest, initialOpen=null}:Readonly<TopMenuProps>){
  const [open,setOpen]=useState<string|null>(initialOpen);
  const bar=useRef<HTMLElement>(null);
  const close=()=>setOpen(null);
  const menus:[string,MenuItem[]|null][]=[
    ['Fichier',[{label:'Ouvrir un projet…', href:href('projets')}, {label:'Ajouter un projet…', href:href('projets', undefined, {ajouter:'1'})}]],
    ['Analyse',null],
    ['Affichage',[{label:'Revenir à la dernière analyse', disabled:!latest, run:latest}, {label:'Choisir l’analyse affichée…', href:href('analyses')}]],
    ['Aide',[{label:'Taxo · version 0.1', disabled:true},{label:'Analyse locale : vos fichiers restent sur votre machine', disabled:true}]]];
  useEffect(()=>open?closeOnOutside(bar.current,close):undefined,[open]);
  return <nav className="top-menu" ref={bar} aria-label="Menus">{menus.map(([name,items])=><div className="menu" key={name}>
    <button type="button" aria-haspopup={items?'menu':'dialog'} aria-expanded={open===name} className={!items&&running?'is-running':undefined}
      onClick={()=>setOpen(open===name?null:name)} onMouseEnter={()=>open&&setOpen(name)}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={MENU_ICONS[name]}/></svg><span className="menu-label">{name}</span></button>
    {open===name&&(items?<div className="menu-list" role="menu">{items.map(item=>item.href
      ?<a key={item.label} role="menuitem" href={item.href} onClick={close}>{item.label}</a>
      :<button type="button" key={item.label} role="menuitem" disabled={item.disabled} onClick={()=>{close();item.run?.();}}>{item.label}</button>)}</div>
      :<div className="menu-panel" role="dialog" aria-label={name}>{analysis(close)}</div>)}
  </div>)}</nav>;
}

/** Menu vertical : une entrée par page, la page affichée marquée. */
export function ResultsNav({items, current}:Readonly<{items:readonly NavItem[]; current:Page}>){
  return <nav className="results-nav" aria-label="Pages">{items.map(item=>
    <a key={item.id} href={href(item.id)} className={[item.apart&&'apart', item.muted&&'muted'].filter(Boolean).join(' ')||undefined}
      aria-current={current===item.id?'page':undefined} title={item.muted?'Pas encore analysé':undefined}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS[item.id]??ICON_PATHS.overview}/></svg>
      <span className="results-label">{item.label}</span>{item.count&&<span className="results-count">{item.count}</span>}</a>)}</nav>;
}
