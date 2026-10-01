// Comparer deux analyses (TAXO-01F, tranche B). Le portail lit les deux reponses de l'API telles quelles :
// aucune comparaison n'est calculee ici. Des comptes, jamais de pourcentage ; aucun impact suppose.
import {type ReactNode, useEffect, useRef, useState} from 'react';
import {EVALUATORS, VERBS, label, reference} from './vocabulary';

type Request=<T>(path:string)=>Promise<T>;
export type Side={id:string; created_at:string; snapshot?:{commit?:string; mode?:string; content_fingerprint?:string}|null};
export type EvaluatorEntry={evaluator_id:string; comparable:boolean; reason?:string; message?:string;
  versions:{before:string[]; after:string[]}; counts?:Record<string,number>};
export type ComparisonSummary={before:Side; after:Side; evaluators:EvaluatorEntry[]; totals:Record<string,number>;
  unknown:{before:number; after:number}};
export type Evidence={path?:string; line_start?:number; line_end?:number; symbol?:string; object?:string; method?:string;
  content_hash?:string};
type Project={id:string; name:string};
export type ComparedFact={kind:string; subject?:string; relation?:string; object?:string; status:string; validity:string;
  evidence?:Evidence[]; derivation?:{rule:string; premises:string[]}};
export type ChangesPage={items:{before:ComparedFact[]; after:ComparedFact[]}[]; next:string|null};

export const CATEGORIES=[
  {id:'ADDED', sign:'+', label:'Ajoutés', tone:'ok'},
  {id:'REMOVED', sign:'−', label:'Disparus', tone:'warn'},
  {id:'MODIFIED', sign:'~', label:'Modifiés', tone:'info'},
  {id:'EVIDENCE_CHANGED', sign:'↗', label:'Preuves déplacées', tone:'info'},
  {id:'STATUS_CHANGED', sign:'•', label:'Statut changé', tone:'info'},
  {id:'OCCURRENCE_COUNT_CHANGED', sign:'#', label:'Apparitions changées', tone:'muted'},
  {id:'OCCURRENCES_CHANGED', sign:'≠', label:'Contenu changé', tone:'muted'},
] as const;
type Category=typeof CATEGORIES[number]['id'];

/** Ce qu'une analyse a lu : un commit, ou des fichiers non commites et leur empreinte. */
export function sideLabel(side:Side){
  const snapshot=side.snapshot??{};
  if(snapshot.mode==='WORKING_TREE')return `Fichiers non commités · empreinte ${(snapshot.content_fingerprint??'').replace('sha256:','').slice(0,10)}…`;
  return snapshot.commit?`commit ${snapshot.commit.slice(0,10)}`:'instantané inconnu';
}

export const day=(value:string)=>{const moment=new Date(value);return Number.isNaN(moment.getTime())?value:moment.toLocaleString('fr-CA');};

/** Le fait dit en clair : sujet, verbe, objet ; le depot par le nom du projet. */
export function statement(fact:ComparedFact, project?:Project){
  const said=(value?:string)=>reference(value??null, project);
  if(fact.kind!=='ASSERTION')return [said(fact.subject), fact.kind.toLowerCase()].filter(Boolean).join(' · ');
  return [said(fact.subject), label(VERBS, fact.relation??''), said(fact.object)].filter(Boolean).join(' ');
}

/** Une preuve et l'empreinte du contenu cite : un fichier modifie aux memes lignes reste visible. */
export function proofWithContent(evidence:Evidence){
  const content=evidence.content_hash?.replace('sha256:','').slice(0,8);
  return content?`${proof(evidence)} · contenu ${content}`:proof(evidence);
}

/** Ou se trouve une preuve : fichier et lignes, ou objet Git. */
export function proof(evidence:Evidence){
  if(evidence.object)return reference(evidence.object);
  if(!evidence.path)return evidence.method??'preuve';
  if(!evidence.line_start)return evidence.path;
  return evidence.line_end&&evidence.line_end!==evidence.line_start
    ?`${evidence.path}:${evidence.line_start}-${evidence.line_end}`:`${evidence.path}:${evidence.line_start}`;
}

const proofs=(facts:ComparedFact[], show:(evidence:Evidence)=>string|null=proof)=>
  facts.flatMap(fact=>(fact.evidence??[]).map(show)).filter(Boolean);

const keyOf=(value:unknown)=>JSON.stringify(value);
const apparitions=(facts:ComparedFact[])=>`${facts.length} apparition${facts.length>1?'s':''}`;
const joined=(values:(string|null)[])=>values.filter(Boolean).join(' · ')||'—';

/** Tout ce que dit une occurrence, tel quel : le fait, son statut, sa justification, ses preuves. Rien n'est compare ici. */
function said(facts:ComparedFact[], project?:Project){
  return facts.map(fact=><div key={keyOf(fact)} className="said">
    <span>{statement(fact, project)}</span>
    <span>{fact.status} · {fact.validity}</span>
    {fact.derivation&&<ul className="premises">{fact.derivation.premises.map(premise=><li key={premise}>{premise}</li>)}</ul>}
    {(fact.evidence??[]).length>0&&<span>{joined(proofs([fact], proofWithContent))}</span>}
  </div>);
}

/** Ce que montre chaque colonne Avant / Apres, selon la categorie. */
const SIDES:Partial<Record<Category, (facts:ComparedFact[], project?:Project)=>ReactNode>>={
  MODIFIED:(facts, project)=>reference(facts[0]?.object??null, project),
  EVIDENCE_CHANGED:facts=>joined(proofs(facts, proofWithContent)),
  STATUS_CHANGED:facts=>joined(facts.map(fact=>`${fact.status} · ${fact.validity}`)),
  OCCURRENCE_COUNT_CHANGED:apparitions,
  OCCURRENCES_CHANGED:said,
};

function heading(category:Category, fact:ComparedFact, project?:Project){
  return category==='MODIFIED'?`${reference(fact.subject??null, project)} ${label(VERBS, fact.relation??'')}`:statement(fact, project);
}

export function ChangeItem({category, item, project}:Readonly<{category:Category; item:ChangesPage['items'][number]; project?:Project}>){
  const facts=item.before.length?item.before:item.after;
  const side=SIDES[category];
  if(!side)return <li><p className="change-fact">{statement(facts[0], project)}</p>
    {proofs(facts).length>0&&<p className="change-proof">{joined(proofs(facts))}</p>}</li>;
  return <li><p className="change-fact">{heading(category, facts[0], project)}</p>
    <dl className="change-sides"><div><dt>Avant</dt><dd>{side(item.before, project)}</dd></div>
      <div><dt>Après</dt><dd>{side(item.after, project)}</dd></div></dl></li>;
}

function EvaluatorChanges({base, request, summary, category, entry, project}:Readonly<{base:string; request:Request; summary:ComparisonSummary;
  category:Category; entry:EvaluatorEntry; project?:Project}>){
  const [items,setItems]=useState<ChangesPage['items']>([]), [next,setNext]=useState<string|null>(null);
  const [loading,setLoading]=useState(true), [error,setError]=useState('');
  // Une reponse arrivee apres un changement de categorie ne doit jamais remplir la nouvelle liste.
  const generation=useRef(0);
  function load(cursor:string|null){
    const mine=cursor===null?++generation.current:generation.current;
    const query=new URLSearchParams({before:summary.before.id, after:summary.after.id, evaluator:entry.evaluator_id, category, limit:'20'});
    if(cursor)query.set('cursor', cursor);
    setLoading(true);setError('');
    request<ChangesPage>(`${base}/comparisons/changes?${query}`)
      .then(page=>{
        if(mine!==generation.current){return;}
        setItems(past=>cursor?[...past,...page.items]:page.items);
        setNext(page.next);
      })
      .catch(reason=>{if(mine===generation.current)setError((reason as Error).message);})
      .finally(()=>{if(mine===generation.current)setLoading(false);});
  }
  useEffect(()=>{setItems([]);setNext(null);load(null);},[category, entry.evaluator_id, summary.before.id, summary.after.id]);
  return <section className="change-group"><h4>{label(EVALUATORS, entry.evaluator_id)} <span>{entry.counts?.[category]}</span></h4>
    {error&&<p role="alert" className="error">{error}</p>}
    <ul className="change-list">{items.map(item=><ChangeItem key={keyOf(item)} category={category} item={item} project={project}/>)}</ul>
    {loading&&<output className="muted">Chargement…</output>}
    {!loading&&next&&<button type="button" className="link more" onClick={()=>load(next)}>Afficher la suite</button>}
  </section>;
}

export function ComparisonView({base, request, before, after, onClose, onSwap, project}:Readonly<{base:string; request:Request; before:string;
  after:string; onClose:()=>void; onSwap:()=>void; project?:Project}>){
  const [summary,setSummary]=useState<ComparisonSummary|null>(null), [error,setError]=useState('');
  const [category,setCategory]=useState<Category|null>(null);
  useEffect(()=>{
    let active=true;
    setSummary(null);setError('');setCategory(null);
    request<ComparisonSummary>(`${base}/comparisons?${new URLSearchParams({before, after})}`)
      .then(value=>{if(active)setSummary(value);}).catch(reason=>{if(active)setError((reason as Error).message);});
    return ()=>{active=false;};
  },[base, before, after]);
  const refused=summary?.evaluators.filter(entry=>!entry.comparable)??[];
  const versions=summary?.evaluators.filter(entry=>entry.comparable&&entry.versions.before.join()!==entry.versions.after.join())??[];
  const chosen=CATEGORIES.find(item=>item.id===category);
  return <section className="comparison" id="comparaison" aria-label="Comparaison de deux analyses">
    <div className="comparison-bar"><button type="button" className="link" onClick={onClose}>← Vue d’ensemble</button>
      <button type="button" className="ghost" onClick={onSwap}>Inverser le sens</button></div>
    {error&&<div role="alert" className="error">{error}</div>}
    {!summary&&!error&&<output>Comparaison en cours…</output>}
    {summary&&<>
      <header className="comparison-head">
        <div><span className="eyebrow">Analyse A</span><strong>{sideLabel(summary.before)}</strong><span>{day(summary.before.created_at)}</span></div>
        <span className="comparison-arrow" aria-hidden="true">→</span>
        <div><span className="eyebrow">Analyse B</span><strong>{sideLabel(summary.after)}</strong><span>{day(summary.after.created_at)}</span></div>
      </header>
      <p className="muted">Calculé depuis les faits enregistrés des deux analyses : le dépôt n’est pas relu. {summary.totals.UNCHANGED} faits inchangés.</p>
      <div className="comparison-body">
        <nav className="change-counts" aria-label="Changements">{CATEGORIES.map(item=>{
          const count=summary.totals[item.id]??0;
          return <button type="button" key={item.id} className={`change-count tone-text-${item.tone}${category===item.id?' selected':''}`}
            disabled={count===0} aria-pressed={category===item.id} onClick={()=>setCategory(item.id)}>
            <span className="sign" aria-hidden="true">{item.sign}</span><strong>{count}</strong><span>{item.label}</span></button>;})}
        </nav>
        <aside className="comparison-notes">
          {refused.length>0&&<div><h3>Non comparables</h3><ul>{refused.map(entry=><li key={entry.evaluator_id}><strong>{label(EVALUATORS, entry.evaluator_id)}</strong>
            <span>{entry.message}</span></li>)}</ul></div>}
          {versions.length>0&&<div><h3>Versions de producteur</h3><ul>{versions.map(entry=><li key={entry.evaluator_id}><strong>{label(EVALUATORS, entry.evaluator_id)}</strong>
            <span>{entry.versions.before.join(', ')} → {entry.versions.after.join(', ')} · provenance, pas un changement du logiciel</span></li>)}</ul></div>}
          <div><h3>Zones inconnues</h3><p>A : {summary.unknown.before} · B : {summary.unknown.after}</p></div>
        </aside>
      </div>
      {chosen?<div className="change-detail"><h3>{chosen.label}</h3>
        {summary.evaluators.filter(entry=>entry.comparable&&(entry.counts?.[chosen.id]??0)>0).map(entry=>
          <EvaluatorChanges key={entry.evaluator_id} base={base} request={request} summary={summary} category={chosen.id} entry={entry}
            project={project}/>)}
      </div>:<p className="muted">Choisissez un compte pour voir les faits concernés.</p>}
    </>}
  </section>;
}

/** Lancer une comparaison depuis la vue d'ensemble : l'analyse affichee et une autre analyse du projet. */
export function CompareLauncher({current, others, onCompare}:Readonly<{current:Side; others:Side[]; onCompare:(other:string)=>void}>){
  const [other,setOther]=useState(others[0]?.id??'');
  useEffect(()=>{setOther(others[0]?.id??'');},[others]);
  return <section className="compare-launch" aria-label="Comparer">
    <div><span className="eyebrow">Analyse affichée</span><strong>{sideLabel(current)}</strong><span className="muted">{day(current.created_at)}</span></div>
    {others.length?<form onSubmit={event=>{event.preventDefault();onCompare(other);}}>
      <label>Comparer avec<select value={other} onChange={event=>setOther(event.target.value)}>
        {others.map(side=><option key={side.id} value={side.id}>{day(side.created_at)} · {sideLabel(side)}</option>)}</select></label>
      <button type="submit" className="ghost">Comparer</button></form>
      :<p className="muted">Une seule analyse complète : relancez l’analyse pour pouvoir comparer.</p>}
  </section>;
}
