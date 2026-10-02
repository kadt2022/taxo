// Coque de l'application : barre de menus, sélecteur de projet et menu vertical des résultats (TAXO-UI-04).
// Sorti de main.tsx pour être testé ; les effets prennent leur document et leur observateur en paramètre.
import {useEffect, useRef, useState, type FormEvent} from 'react';
import {type RouteCounts, type Scan} from './overview';
import {href, type Page} from './nav';

export type Project = {id:string; name:string; path:string};
export type MenuItem = {label:string; href?:string; disabled?:boolean; run?:()=>void};
export type NavItem = {id:Page; label:string; count?:string; apart?:boolean; muted?:boolean};

export const ICON_PATHS:Record<string,string>={overview:'M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z',
  analyses:'M9 4h6M9 3h6v3H9zM6 5H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1M8 12h8M8 16h5',
  comparaisons:'M4 7h11M12 4l3 3-3 3M20 17H9M12 14l-3 3 3 3', interroger:'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2zM9 9h6M9 13h4',
  architecture:'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  technologies:'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5', routes:'M8 7l-5 5 5 5M16 7l5 5-5 5', details:'M4 6h16M4 12h16M4 18h10',
  limites:'M12 3l10 18H2zM12 10v5M12 18v.5', historique:'M12 7v5l3 2M3 12a9 9 0 1 0 3-6.7M3 4v5h5', securite:'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z',
  donnees:'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  'non-interpretees':'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8v5M12 16v.5'};

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
    {id:'interroger', label:'Interroger Taxo'},
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

type TopMenuProps = {canAnalyze:boolean; analyze:()=>void; addProject:()=>void; latest?:()=>void; initialOpen?:string|null};

/** Barre de menus façon application, réservée aux commandes globales : Fichier, Analyse, Affichage, Aide. La navigation est dans le
 * menu vertical. Un seul menu ouvert à la fois ; Échap ou un clic ailleurs le referme, et le survol change de menu une fois la barre
 * activée. */
export function TopMenu({canAnalyze, analyze, addProject, latest, initialOpen=null}:Readonly<TopMenuProps>){
  const [open,setOpen]=useState<string|null>(initialOpen);
  const bar=useRef<HTMLElement>(null);
  const menus:[string,MenuItem[]][]=[
    ['Fichier',[{label:'Ajouter un projet…', run:addProject}]],
    ['Analyse',[{label:'Lancer l’analyse globale', disabled:!canAnalyze, run:analyze}, {label:'Comparer deux analyses…', href:href('comparaisons')}]],
    ['Affichage',[{label:'Revenir à la dernière analyse', disabled:!latest, run:latest}, {label:'Choisir l’analyse affichée…', href:href('analyses')}]],
    ['Aide',[{label:'Taxo · version 0.1', disabled:true},{label:'Analyse locale : vos fichiers restent sur votre machine', disabled:true}]]];
  useEffect(()=>open?closeOnOutside(bar.current,()=>setOpen(null)):undefined,[open]);
  return <nav className="top-menu" ref={bar} aria-label="Menus">{menus.map(([name,items])=><div className="menu" key={name}>
    <button type="button" aria-haspopup="menu" aria-expanded={open===name} onClick={()=>setOpen(open===name?null:name)} onMouseEnter={()=>open&&setOpen(name)}>{name}</button>
    {open===name&&<div className="menu-list" role="menu">{items.map(item=>item.href
      ?<a key={item.label} role="menuitem" href={item.href} onClick={()=>setOpen(null)}>{item.label}</a>
      :<button type="button" key={item.label} role="menuitem" disabled={item.disabled} onClick={()=>{setOpen(null);item.run?.();}}>{item.label}</button>)}</div>}
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

export type PickerProps = {projects:Project[]; selected:string; busy:boolean; loading:boolean; open:boolean; setOpen:(open:boolean)=>void;
  adding:boolean; setAdding:(adding:boolean)=>void; onSelect:(id:string)=>void; status:string;
  name:string; setName:(value:string)=>void; path:string; setPath:(value:string)=>void; onSubmit:(event:FormEvent)=>void};

/** Sélecteur de projet de la barre du haut : le projet courant, l'état de son analyse, la liste des projets et l'ajout d'un projet. */
export function ProjectPicker(props:Readonly<PickerProps>){
  const {projects, selected, busy, loading, open, setOpen, adding, setAdding, onSelect, status}=props;
  const box=useRef<HTMLDivElement>(null);
  useEffect(()=>open?closeOnOutside(box.current,()=>setOpen(false)):undefined,[open,setOpen]);
  const current=projects.find(project=>project.id===selected);
  return <div className="picker" ref={box}>
    <button type="button" className="picker-current" aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(!open)}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
      <strong>{current?.name??'Choisir un projet'}</strong>
      {status&&<span className="picker-status"><i aria-hidden="true"/>{status}</span>}
      <span className="picker-chevron" aria-hidden="true">⌄</span>
    </button>
    {open&&<div className="picker-panel">
      <p className="picker-title">Projets <span>{projects.length}</span></p>
      <div role="listbox" aria-label="Projets">{projects.map(project=><button type="button" role="option" aria-selected={selected===project.id} disabled={busy} key={project.id}
        onClick={()=>onSelect(project.id)}>{project.name}</button>)}</div>
      {adding
        ?<form onSubmit={props.onSubmit}>
          <label>Nom<input required autoFocus maxLength={120} value={props.name} onChange={event=>props.setName(event.target.value)} placeholder="Mon application"/></label>
          <label>Dossier local<input required value={props.path} onChange={event=>props.setPath(event.target.value)} placeholder="D:\MonProjet"/></label>
          <button type="submit" className="picker-save" disabled={busy||loading}>Enregistrer le projet</button>
        </form>
        :<button type="button" className="picker-add" onClick={()=>setAdding(true)}><span aria-hidden="true">+</span>Ajouter un projet</button>}
    </div>}
  </div>;
}
