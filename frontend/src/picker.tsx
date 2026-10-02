// Choisir les deux analyses a comparer (TAXO-01F, tranche C). Taxo compare deux analyses, pas deux commits :
// le commit decrit une analyse et sert a la retrouver. La recherche filtre une liste ; elle ne compare rien.
import {useEffect, useState} from 'react';
import {EVALUATORS, label} from './vocabulary';
import {day, sameCommit, sideLabel, type Side} from './comparison';

type Request=<T>(path:string)=>Promise<T>;
export type RecordedCommit={sha:string; subject?:string|null; authored_at?:string|null; author?:string|null};
export type Choice=Side & {commit:RecordedCommit|null; fact_count:number; failed:string[]};

export const TEXT_FILTERS=[
  {id:'message', label:'Message du commit'},
  {id:'author', label:'Auteur du commit'},
  {id:'sha', label:'Commit (identifiant)'},
] as const;
export const DAY_FILTERS=[
  {id:'analysis', label:'Date de l’analyse'},
  {id:'commit', label:'Date du commit'},
] as const;
export type Search={text:string; field:typeof TEXT_FILTERS[number]['id']; from:string; to:string;
  dayOf:typeof DAY_FILTERS[number]['id']};
export const NO_SEARCH:Search={text:'', field:'message', from:'', to:'', dayOf:'analysis'};
const SHOWN=30;

/** Le jour local d'un instant, `AAAA-MM-JJ`, pour le comparer aux bornes saisies. */
export function localDay(value:string){
  const moment=new Date(value);
  if(Number.isNaN(moment.getTime()))return value.slice(0, 10);
  return `${moment.getFullYear()}-${String(moment.getMonth()+1).padStart(2, '0')}-${String(moment.getDate()).padStart(2, '0')}`;
}

/** Le jour d'un commit, sans heure : « 1 oct. 2026 ». */
export const commitDay=(value:string)=>{const moment=new Date(value);return Number.isNaN(moment.getTime())?value
  :moment.toLocaleDateString('fr-FR', {day:'numeric', month:'short', year:'numeric'});};

/** Une analyse repond-elle a la recherche ? Texte sans casse ; dates incluses. */
export function matches(choice:Choice, search:Search){
  const wanted=search.text.trim().toLowerCase();
  const field={message:choice.commit?.subject, author:choice.commit?.author,
    sha:choice.commit?.sha??choice.snapshot?.commit}[search.field]??'';
  if(wanted&&!(search.field==='sha'?field.toLowerCase().startsWith(wanted):field.toLowerCase().includes(wanted)))return false;
  if(!search.from&&!search.to)return true;
  const moment=search.dayOf==='analysis'?choice.created_at:choice.commit?.authored_at;
  if(!moment)return false;
  const at=localDay(moment);
  return (!search.from||at>=search.from)&&(!search.to||at<=search.to);
}

/** Ce qu'une analyse a lu, assez pour la reconnaitre : le commit tel qu'elle l'a enregistre. */
export function ChoiceCard({choice}:Readonly<{choice:Choice}>){
  const commit=choice.commit, tree=choice.snapshot?.mode==='WORKING_TREE';
  return <span className="choice-card">
    <strong className="choice-when">Analyse du {day(choice.created_at)}</strong>
    <span className="choice-code">{tree?<>{sideLabel(choice)}{commit&&<> · sur <code>{commit.sha.slice(0, 7)}</code></>}</>
      :commit?<><code>{commit.sha.slice(0, 7)}</code>{commit.author&&<> · {commit.author}</>}{commit.authored_at&&<> · {commitDay(commit.authored_at)}</>}</>
        :sideLabel(choice)}</span>
    {commit?.subject&&<span className="choice-message">« {commit.subject} »</span>}
    <span className="choice-facts">{choice.fact_count.toLocaleString('fr-CA')} faits
      {choice.failed.length>0&&<span className="choice-failed"> · en échec : {choice.failed.map(id=>label(EVALUATORS, id)).join(', ')}</span>}</span>
  </span>;
}

function SearchFields({search, onChange, side}:Readonly<{search:Search; onChange:(next:Search)=>void; side:string}>){
  const set=(change:Partial<Search>)=>onChange({...search, ...change});
  return <div className="choice-search">
    <div className="choice-row">
      <select aria-label={`Critère de recherche ${side}`} value={search.field} onChange={event=>set({field:event.target.value as Search['field']})}>
        {TEXT_FILTERS.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select>
      <input type="search" aria-label={`Rechercher une analyse ${side}`} placeholder="Rechercher…" value={search.text}
        onChange={event=>set({text:event.target.value})}/>
    </div>
    <div className="choice-row">
      <select aria-label={`Date filtrée ${side}`} value={search.dayOf} onChange={event=>set({dayOf:event.target.value as Search['dayOf']})}>
        {DAY_FILTERS.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select>
      <span className="choice-dates"><label>du<input type="date" value={search.from} onChange={event=>set({from:event.target.value})}/></label>
        <label>au<input type="date" value={search.to} onChange={event=>set({to:event.target.value})}/></label></span>
    </div>
  </div>;
}

function Column({letter, title, choices, chosen, other, onChoose}:Readonly<{letter:'A'|'B'; title:string; choices:Choice[];
  chosen:string; other:string; onChoose:(id:string)=>void}>){
  const [search,setSearch]=useState<Search>(NO_SEARCH), [open,setOpen]=useState(!chosen), [more,setMore]=useState(SHOWN);
  const found=choices.filter(choice=>matches(choice, search));
  const selected=choices.find(choice=>choice.id===chosen);
  return <section className={`choice-column side-${letter.toLowerCase()}`} aria-label={`Analyse ${letter}`}>
    <header><b className="side-letter" aria-hidden="true">{letter}</b><div><span className="eyebrow">Analyse {letter}</span><strong>{title}</strong></div></header>
    {selected&&!open?<div className="choice-selected"><ChoiceCard choice={selected}/>
      <button type="button" className="link" onClick={()=>setOpen(true)}>Choisir une autre analyse</button></div>
      :<>
        <SearchFields search={search} onChange={next=>{setSearch(next);setMore(SHOWN);}} side={letter}/>
        <p className="choice-count">{found.length} analyse{found.length>1?'s':''} sur {choices.length}</p>
        <ul className="choice-list">{found.slice(0, more).map(choice=><li key={choice.id}>
          <button type="button" className={choice.id===chosen?'selected':''} aria-pressed={choice.id===chosen} disabled={choice.id===other}
            onClick={()=>{onChoose(choice.id);setOpen(false);}}>
            <ChoiceCard choice={choice}/>{choice.id===other&&<span className="choice-taken">déjà choisie en {letter==='A'?'B':'A'}</span>}</button></li>)}</ul>
        {found.length>more&&<button type="button" className="ghost more" onClick={()=>setMore(more+SHOWN)}>Afficher plus</button>}
        {found.length===0&&<p className="muted">Aucune analyse ne répond à cette recherche.</p>}
      </>}
  </section>;
}

/** Le comparateur : choisir A, puis B, puis comparer. A peut arriver deja fixee (« Comparer avec… »). */
export function ComparePicker({base, request, initial, onCompare, onClose}:Readonly<{base:string; request:Request;
  initial?:{before?:string; after?:string}; onCompare:(before:string, after:string)=>void; onClose:()=>void}>){
  const [choices,setChoices]=useState<Choice[]|null>(null), [error,setError]=useState('');
  const [before,setBefore]=useState(initial?.before??''), [after,setAfter]=useState(initial?.after??'');
  useEffect(()=>{
    let active=true;
    request<Choice[]>(`${base}/comparisons/analyses`).then(value=>{if(active)setChoices(value);})
      .catch(reason=>{if(active)setError((reason as Error).message);});
    return ()=>{active=false;};
  },[base]);
  const left=choices?.find(choice=>choice.id===before), right=choices?.find(choice=>choice.id===after);
  return <section className="comparison picker" aria-label="Choisir deux analyses">
    <div className="comparison-bar"><button type="button" className="link back" onClick={onClose}>← Vue d’ensemble</button>
      <span className="eyebrow">Comparer deux analyses Taxo</span></div>
    <p className="muted picker-intro">Choisissez deux analyses du projet. Taxo compare ce qu’il a enregistré pour chacune, sans relire le dépôt ;
      le commit sert à les reconnaître.</p>
    {error&&<div role="alert" className="error">{error}</div>}
    {!choices&&!error&&<output>Chargement des analyses…</output>}
    {choices&&(choices.length<2?<p className="comparison-empty">Une seule analyse complète : relancez l’analyse pour pouvoir comparer.</p>:<>
      <div className="choice-columns">
        <Column letter="A" title="Point de départ" choices={choices} chosen={before} other={after} onChoose={setBefore}/>
        <span className="comparison-arrow" aria-hidden="true">→</span>
        <Column letter="B" title="Point d’arrivée" choices={choices} chosen={after} other={before} onChoose={setAfter}/>
      </div>
      {sameCommit(left, right)&&<p className="comparison-note">Deux analyses du même commit : le code est le même, seul ce que Taxo en dit peut différer.</p>}
      <div className="picker-actions"><button type="button" className="primary" disabled={!left||!right} onClick={()=>onCompare(before, after)}>Comparer →</button></div>
    </>)}
  </section>;
}
