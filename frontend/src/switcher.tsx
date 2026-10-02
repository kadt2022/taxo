// Le selecteur de projet (TAXO-UI-05) : en tete du menu vertical, au-dessus d'Overview. Le projet actif, puis, au clic, tous les
// projets, une recherche, l'ajout d'un projet sur place et la page de gestion. La selection reprend le mecanisme existant.
import {useEffect, useRef, useState, type FormEvent} from 'react';
import {href} from './nav';
import {closeOnOutside, type Project} from './shell';

/** Une teinte stable par projet : la meme initiale ne donne pas la meme pastille a deux projets differents. */
export function hue(id:string){
  let value=0;
  for(const char of id)value=(value*31+char.charCodeAt(0))%360;
  return value;
}

/** Le dernier dossier du chemin : assez pour reconnaitre un projet, sans le chemin entier. */
export const folderOf=(path?:string)=>path?.replace(/[\\/]+$/, '').split(/[\\/]/).pop()??'';

function Monogram({project}:Readonly<{project?:Project}>){
  const style=project?{background:`hsl(${hue(project.id)} 42% 34%)`}:undefined;
  return <span className="monogram" style={style} aria-hidden="true">{project?.name.trim().charAt(0).toUpperCase()||'+'}</span>;
}

const SEARCH_FROM=6;

type Props={projects:Project[]; selected:string; status:string; busy:boolean; onOpen:(id:string)=>void;
  onAdd:(name:string, path:string)=>Promise<boolean>; initialOpen?:boolean};

export function ProjectSwitcher({projects, selected, status, busy, onOpen, onAdd, initialOpen=false}:Readonly<Props>){
  const [open,setOpen]=useState(initialOpen), [adding,setAdding]=useState(false);
  const [query,setQuery]=useState(''), [name,setName]=useState(''), [path,setPath]=useState('');
  const box=useRef<HTMLDivElement>(null);
  const close=()=>{setOpen(false);setAdding(false);setQuery('');};
  useEffect(()=>open?closeOnOutside(box.current, close):undefined,[open]);
  const current=projects.find(item=>item.id===selected);
  const wanted=query.trim().toLowerCase();
  const shown=projects.filter(item=>!wanted||item.name.toLowerCase().includes(wanted)||(item.path??'').toLowerCase().includes(wanted));
  async function submit(event:FormEvent){
    event.preventDefault();
    if(await onAdd(name, path)){setName('');setPath('');close();}
  }
  return <div className={`switcher${open?' is-open':''}`} ref={box}>
    <button type="button" className="switcher-current" aria-haspopup="listbox" aria-expanded={open} onClick={()=>open?close():setOpen(true)}>
      <Monogram project={current}/>
      <span className="switcher-text"><span className="switcher-eyebrow">Projet</span>
        <strong>{current?.name??'Choisir un projet'}</strong>{current&&status&&<small title={`Dernière analyse ${status}`}><i aria-hidden="true"/>{status}</small>}</span>
      <svg className="switcher-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
    </button>
    {open&&<div className="switcher-panel">
      <div className="switcher-head"><span>Projets</span><span className="switcher-count">{projects.length}</span></div>
      {projects.length>=SEARCH_FROM&&<input className="switcher-search" type="search" aria-label="Rechercher un projet" placeholder="Rechercher un projet…"
        value={query} onChange={event=>setQuery(event.target.value)} autoFocus/>}
      {projects.length>0&&<div className="switcher-list" role="listbox" aria-label="Projets">{shown.map(item=>
        <button type="button" role="option" key={item.id} aria-selected={item.id===selected} disabled={busy}
          onClick={()=>{close();if(item.id!==selected)onOpen(item.id);}}>
          <Monogram project={item}/><span className="switcher-text"><strong>{item.name}</strong>{folderOf(item.path).toLowerCase()!==item.name.toLowerCase()&&<small>{folderOf(item.path)}</small>}</span>
          {item.id===selected&&<svg className="switcher-check" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>}
        </button>)}
        {shown.length===0&&<p className="switcher-empty">Aucun projet ne répond à « {query} ».</p>}</div>}
      {adding?<form className="switcher-form" onSubmit={submit}>
        <label>Nom<input required autoFocus maxLength={120} value={name} onChange={event=>setName(event.target.value)} placeholder="Mon application"/></label>
        <label>Dossier local<input required value={path} onChange={event=>setPath(event.target.value)} placeholder="D:\MonProjet"/></label>
        <div className="switcher-form-actions"><button type="submit" className="switcher-save" disabled={busy}>Enregistrer</button>
          {projects.length>0&&<button type="button" className="link" onClick={()=>setAdding(false)}>Annuler</button>}</div>
      </form>:<button type="button" className="switcher-add" onClick={()=>setAdding(true)}><span aria-hidden="true">+</span>Ajouter un projet</button>}
      {projects.length>0&&<a className="switcher-manage" href={href('projets')} onClick={close}>Gérer les projets <span aria-hidden="true">→</span></a>}
    </div>}
  </div>;
}
