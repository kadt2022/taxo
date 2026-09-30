// Coque de l'application : barre de menus, sélecteur de projet et menu vertical des résultats (TAXO-UI-04).
// Sorti de main.tsx pour être testé ; les effets prennent leur document et leur observateur en paramètre.
import {useEffect, useRef, useState, type FormEvent} from 'react';
import {type RouteCounts, type Scan} from './overview';

export type Project = {id:string; name:string; path:string};
export type MenuItem = {label:string; href?:string; disabled?:boolean; run?:()=>void};
export type NavItem = {id:string; to?:string; label:string; count?:string; icon?:string; apart?:boolean; muted?:boolean};

export const SECTIONS:MenuItem[]=[['technologies','Technologies'],['routes','Routes'],['limites','Limites'],['details','Détails techniques'],['historique','Historique']]
  .map(([id,label])=>({label, href:`#${id}`}));

export const ICON_PATHS:Record<string,string>={'vue-ensemble':'M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z',
  technologies:'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5', routes:'M8 7l-5 5 5 5M16 7l5 5-5 5', details:'M4 6h16M4 12h16M4 18h10',
  limites:'M12 3l10 18H2zM12 10v5M12 18v.5', historique:'M12 7v5l3 2M3 12a9 9 0 1 0 3-6.7M3 4v5h5', securite:'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z',
  donnees:'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  nonint:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8v5M12 16v.5'};

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

/** Les entrées du menu vertical : un compte seulement quand Taxo en a un, « Données » grisée tant qu'aucun analyseur ne la nourrit. */
export function resultItemsOf(technologies:number, counts:(id:string)=>string|undefined, routes?:RouteCounts):NavItem[]{
  return [{id:'technologies', label:'Technologies', count:technologies?String(technologies):undefined},
    {id:'routes', label:'Routes', count:counts('api')}, {id:'details', label:'Architecture', count:counts('architecture')},
    {id:'securite', to:'routes', label:'Sécurité', count:routes?String(routes.PROTECTED):undefined},
    {id:'donnees', label:'Données et stockage', muted:true}, {id:'historique', label:'Historique Git', count:counts('git')},
    {id:'limites', label:'Limites', apart:true},
    {id:'non-interpretees', to:'routes', label:'Non interprétées', icon:'nonint', count:routes?String(routes.NOT_INTERPRETED):undefined}];
}

type Listener = Pick<Document,'addEventListener'|'removeEventListener'>;

/** Referme un panneau au clic ailleurs ou sur Échap ; renvoie la fonction qui retire les écouteurs. */
export function closeOnOutside(box:{contains(node:Node):boolean}|null, close:()=>void, doc:Listener=document){
  const away=(event:Event)=>{if(!box?.contains(event.target as Node))close();};
  const escape=(event:Event)=>{if((event as KeyboardEvent).key==='Escape')close();};
  doc.addEventListener('mousedown',away);doc.addEventListener('keydown',escape);
  return()=>{doc.removeEventListener('mousedown',away);doc.removeEventListener('keydown',escape);};
}

type Watcher = {observe(node:Element):void; disconnect():void};

/** Suit la section visible : l'entrée du menu dont la cible est la première à l'écran devient la courante. */
export function watchSections(items:readonly NavItem[], setCurrent:(id:string)=>void,
  make:(callback:(entries:{target:{id:string}; isIntersecting:boolean}[])=>void)=>Watcher=callback=>new IntersectionObserver(callback,{rootMargin:'-10% 0px -70% 0px'}),
  find:(id:string)=>Element|null=id=>document.getElementById(id)){
  const seen=new Map<string,boolean>();
  const observer=make(entries=>{
    for(const entry of entries)seen.set(entry.target.id, entry.isIntersecting);
    const first=items.find(item=>seen.get(item.to??item.id));
    if(first)setCurrent(first.id);
  });
  for(const item of items){const node=find(item.to??item.id);if(node)observer.observe(node);}
  return()=>observer.disconnect();
}

type TopMenuProps = {canAnalyze:boolean; analyze:()=>void; addProject:()=>void; initialOpen?:string|null};

/** Barre de menus façon application : Overview, Fichier, Analyse, Affichage, Aide. Un seul menu ouvert à la fois ; Échap ou un clic
 * ailleurs le referme, et le survol change de menu une fois la barre activée. */
export function TopMenu({canAnalyze, analyze, addProject, initialOpen=null}:Readonly<TopMenuProps>){
  const [open,setOpen]=useState<string|null>(initialOpen);
  const bar=useRef<HTMLElement>(null);
  const menus:[string,MenuItem[]][]=[
    ['Fichier',[{label:'Ajouter un projet…', run:addProject}]],
    ['Analyse',[{label:'Lancer l’analyse globale', disabled:!canAnalyze, run:analyze}]],
    ['Affichage',SECTIONS],
    ['Aide',[{label:'Taxo · version 0.1', disabled:true},{label:'Analyse locale : vos fichiers restent sur votre machine', disabled:true}]]];
  useEffect(()=>open?closeOnOutside(bar.current,()=>setOpen(null)):undefined,[open]);
  return <nav className="top-menu" ref={bar} aria-label="Menus"><a className="menu-link" href="#vue-ensemble" aria-current="page" onClick={()=>setOpen(null)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS['vue-ensemble']}/></svg>Overview</a>{menus.map(([name,items])=><div className="menu" key={name}>
    <button type="button" aria-haspopup="menu" aria-expanded={open===name} onClick={()=>setOpen(open===name?null:name)} onMouseEnter={()=>open&&setOpen(name)}>{name}</button>
    {open===name&&<div className="menu-list" role="menu">{items.map(item=>item.href
      ?<a key={item.label} role="menuitem" href={item.href} onClick={()=>setOpen(null)}>{item.label}</a>
      :<button type="button" key={item.label} role="menuitem" disabled={item.disabled} onClick={()=>{setOpen(null);item.run?.();}}>{item.label}</button>)}</div>}
  </div>)}</nav>;
}

/** Menu vertical des résultats : une entrée par section, avec son compte quand Taxo en a un, et l'entrée courante suit le défilement. */
export function ResultsNav({items}:Readonly<{items:readonly NavItem[]}>){
  const [current,setCurrent]=useState('');
  useEffect(()=>watchSections(items,setCurrent),[items]);
  return <nav className="results-nav" aria-label="Résultats">{items.map(item=>{
    const inside=<><svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS[item.icon??item.id]??ICON_PATHS.details}/></svg>
      <span className="results-label">{item.label}</span>{item.count&&<span className="results-count">{item.count}</span>}</>;
    return item.muted
      ?<span key={item.id} className={`results-item muted${item.apart?' apart':''}`} title="Pas encore analysé">{inside}</span>
      :<a key={item.id} href={`#${item.to??item.id}`} className={item.apart?'apart':undefined} aria-current={current===item.id?'true':undefined} onClick={()=>setCurrent(item.id)}>{inside}</a>;})}</nav>;
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
