// Comparer deux analyses (TAXO-01F, tranche B). Le portail lit les deux reponses de l'API telles quelles :
// aucune comparaison n'est calculee ici. Des comptes, jamais de pourcentage ; aucun impact suppose.
import {type ReactNode, useEffect, useRef, useState} from 'react';
import {type Sentence, entity, plain, premise, relation, subjectOf} from './sentences';
import {EVALUATORS, ORIGINS, VALIDITIES, label, reference} from './vocabulary';

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
  evidence?:Evidence[]; derivation?:{rule:string; premises:string[]};
  produced_by?:{producer_id?:string; producer_version?:string}};
export type ChangesPage={items:{before:ComparedFact[]; after:ComparedFact[]}[]; next:string|null};

export const CATEGORIES=[
  {id:'ADDED', sign:'+', label:'Ajoutés', tone:'ok', hint:'Présents dans B, absents de A.'},
  {id:'REMOVED', sign:'−', label:'Disparus', tone:'warn', hint:'Présents dans A, absents de B.'},
  {id:'MODIFIED', sign:'~', label:'Modifiés', tone:'info', hint:'Même sujet et même relation, autre objet.'},
  {id:'EVIDENCE_CHANGED', sign:'↗', label:'Preuves déplacées', tone:'info', hint:'Même fait ; sa preuve a changé de place ou de contenu.'},
  {id:'STATUS_CHANGED', sign:'•', label:'Statut changé', tone:'info', hint:'Même fait ; statut ou validité différent.'},
  {id:'OCCURRENCE_COUNT_CHANGED', sign:'#', label:'Apparitions changées', tone:'muted', hint:'Même fait, relevé un nombre de fois différent.'},
  {id:'OCCURRENCES_CHANGED', sign:'≠', label:'Contenu changé', tone:'muted', hint:'Même fait ; ce que disent ses apparitions a changé.'},
] as const;
type Category=typeof CATEGORIES[number]['id'];

/** Ce qu'une analyse a lu : un commit, ou des fichiers non commites et leur empreinte. */
export function sideLabel(side:Side){
  const snapshot=side.snapshot??{};
  if(snapshot.mode==='WORKING_TREE')return `Modifications non commitées · empreinte ${(snapshot.content_fingerprint??'').replace('sha256:','').slice(0,10)}…`;
  return snapshot.commit?`commit ${snapshot.commit.slice(0,10)}`:'instantané inconnu';
}

/** Deux analyses du meme commit : seul ce que Taxo en dit peut differer. */
export function sameCommit(left?:Side|null, right?:Side|null){
  const before=left?.snapshot, after=right?.snapshot;
  return !!before?.commit&&before.mode!=='WORKING_TREE'&&after?.mode!=='WORKING_TREE'&&before.commit===after?.commit;
}

/** Un instant lisible : « 1 oct. 2026, 19:02:08 ». Les secondes distinguent deux analyses faites dans la meme minute. */
export const day=(value:string)=>{const moment=new Date(value);return Number.isNaN(moment.getTime())?value
  :moment.toLocaleString('fr-FR', {day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit'});};

/** Le fait dit en clair, par le rendu type de sa relation ; le depot par le nom du projet. */
export function sentence(fact:ComparedFact, project?:Project):Sentence{
  if(fact.kind!=='ASSERTION'||!fact.relation||!fact.subject||!fact.object)
    return [[reference(fact.subject??null, project), fact.kind.toLowerCase()].filter(Boolean).join(' · ')];
  return relation(fact.relation, entity(fact.subject), entity(fact.object), project);
}

export const statement=(fact:ComparedFact, project?:Project)=>plain(sentence(fact, project));

/** Une phrase rendue : les noms (route, methode, motif, role) restent visibles tels quels. */
export function Phrase({value}:Readonly<{value:Sentence}>){
  return <span className="phrase">{value.map((item, index)=>typeof item==='string'?item
    :<code key={`${index}:${item.code}`}>{item.code}</code>)}</span>;
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

/** Le statut d'un fait dit en clair ; les termes du contrat restent dans les details techniques. */
export const state=(fact:ComparedFact)=>`${label(ORIGINS, fact.status)} · ${label(VALIDITIES, fact.validity)}`;

/** Ce que le moteur a enregistre, tel quel, pour qui veut verifier. */
function Technical({fact}:Readonly<{fact:ComparedFact}>){
  return <details className="technical"><summary>Voir les détails techniques</summary>
    <dl>
      <dt>Type</dt><dd>{fact.kind}{fact.relation?` · ${fact.relation}`:''}</dd>
      <dt>Origine</dt><dd>{fact.status}</dd>
      <dt>Validité</dt><dd>{fact.validity}</dd>
      {fact.subject&&<><dt>Sujet</dt><dd>{fact.subject}</dd></>}
      {fact.object&&<><dt>Objet</dt><dd>{fact.object}</dd></>}
      {fact.derivation&&<><dt>Règle</dt><dd>{fact.derivation.rule}</dd>
        <dt>Prémisses</dt><dd><ul>{fact.derivation.premises.map(item=><li key={item}>{item}</li>)}</ul></dd></>}
      {fact.produced_by?.producer_id&&<><dt>Analyseur</dt>
        <dd>{fact.produced_by.producer_id}{fact.produced_by.producer_version?` ${fact.produced_by.producer_version}`:''}</dd></>}
    </dl></details>;
}

/** Tout ce que dit une occurrence, tel quel : le fait, son statut, sa justification, ses preuves. Rien n'est compare ici. */
function said(facts:ComparedFact[], project?:Project){
  return facts.map(fact=><div key={keyOf(fact)} className="said">
    <span className="said-fact"><Phrase value={sentence(fact, project)}/></span>
    <span className="state">{state(fact)}</span>
    {fact.derivation&&<><span className="said-label">Pourquoi Taxo arrive à cette conclusion</span>
      <ul className="premises">{fact.derivation.premises.map(item=><li key={item}><Phrase value={premise(item, project)}/></li>)}</ul></>}
    {(fact.evidence??[]).length>0&&<><span className="said-label">Preuves dans le code</span>
      <span className="proof">{joined(proofs([fact], proofWithContent))}</span></>}
    <Technical fact={fact}/>
  </div>);
}

/** Ce que montre chaque colonne Avant / Apres, selon la categorie. */
const SIDES:Partial<Record<Category, (facts:ComparedFact[], project?:Project)=>ReactNode>>={
  MODIFIED:(facts, project)=>facts.length?<Phrase value={sentence(facts[0], project)}/>:'—',
  EVIDENCE_CHANGED:facts=>joined(proofs(facts, proofWithContent)),
  STATUS_CHANGED:facts=>joined(facts.map(state)),
  OCCURRENCE_COUNT_CHANGED:apparitions,
  OCCURRENCES_CHANGED:said,
};

function heading(category:Category, fact:ComparedFact, project?:Project):Sentence{
  return category==='MODIFIED'&&fact.subject?subjectOf(fact.subject, project):sentence(fact, project);
}

export function ChangeItem({category, item, project}:Readonly<{category:Category; item:ChangesPage['items'][number]; project?:Project}>){
  const facts=item.before.length?item.before:item.after;
  const side=SIDES[category];
  const sign=CATEGORIES.find(entry=>entry.id===category);
  if(!side)return <li className={`change-row cat-${sign?.tone}`}><span className="change-sign" aria-hidden="true">{sign?.sign}</span>
    <div><p className="change-fact"><Phrase value={sentence(facts[0], project)}/></p>
      {proofs(facts).length>0&&<p className="change-proof"><span className="proof">{joined(proofs(facts))}</span></p>}</div></li>;
  return <li className="change-pair"><p className="change-fact"><Phrase value={heading(category, facts[0], project)}/></p>
    <dl className="change-sides"><div className="side-before"><dt><b>A</b>Avant</dt><dd>{side(item.before, project)}</dd></div>
      <div className="side-after"><dt><b>B</b>Après</dt><dd>{side(item.after, project)}</dd></div></dl></li>;
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
  return <section className="change-group"><h4>{label(EVALUATORS, entry.evaluator_id)} <span className="count-pill">{entry.counts?.[category]}</span></h4>
    {error&&<p role="alert" className="error">{error}</p>}
    <ul className="change-list">{items.map(item=><ChangeItem key={keyOf(item)} category={category} item={item} project={project}/>)}</ul>
    {loading&&<output className="muted">Chargement…</output>}
    {!loading&&next&&<button type="button" className="ghost more" onClick={()=>load(next)}>Afficher la suite</button>}
  </section>;
}

export function ComparisonView({base, request, before, after, onClose, onSwap, onChange, project}:Readonly<{base:string; request:Request;
  before:string; after:string; onClose:()=>void; onSwap:()=>void; onChange?:()=>void; project?:Project}>){
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
    <div className="comparison-bar"><button type="button" className="link back" onClick={onClose}>← Vue d’ensemble</button>
      {onChange?<button type="button" className="ghost" onClick={onChange}>Changer les analyses</button>
        :<span className="eyebrow">Comparaison de deux analyses</span>}</div>
    {error&&<div role="alert" className="error">{error}</div>}
    {!summary&&!error&&<output className="comparison-wait">Comparaison en cours…</output>}
    <div className="comparison-head">
      {summary?<><SideCard letter="A" title="Avant" side={summary.before}/>
        <span className="comparison-arrow" aria-hidden="true">→</span>
        <SideCard letter="B" title="Après" side={summary.after}/></>:<div className="side-card placeholder"/>}
      <button type="button" className="ghost swap" onClick={onSwap}><span aria-hidden="true">⇄</span> Inverser le sens</button>
    </div>
    {summary&&<>
      <nav className="change-counts" aria-label="Changements">{CATEGORIES.map(item=>{
        const count=summary.totals[item.id]??0;
        return <button type="button" key={item.id} className={`change-count cat-${item.tone}${category===item.id?' selected':''}`}
          disabled={count===0} aria-pressed={category===item.id} onClick={()=>setCategory(item.id)}>
          <span className="sign" aria-hidden="true">{item.sign}</span><strong>{count}</strong><span>{item.label}</span></button>;})}
      </nav>
      {sameCommit(summary.before, summary.after)&&<p className="comparison-note">Deux analyses du même commit : le code est le même,
        seul ce que Taxo en dit peut différer.</p>}
      <ul className="comparison-facts">
        <li><strong>{summary.totals.UNCHANGED}</strong> faits inchangés</li>
        <li>Calculé depuis les faits enregistrés des deux analyses : le dépôt n’est pas relu.</li>
        <li>Zones inconnues <span className="count-pill">A : {summary.unknown.before} · B : {summary.unknown.after}</span></li>
      </ul>
      {refused.length>0&&<div className="comparison-note warn"><h3>Non comparables</h3><ul>{refused.map(entry=><li key={entry.evaluator_id}>
        <strong>{label(EVALUATORS, entry.evaluator_id)}</strong><span>{entry.message}</span></li>)}</ul></div>}
      {versions.length>0&&<div className="comparison-note"><h3>Versions de producteur</h3><ul>{versions.map(entry=><li key={entry.evaluator_id}>
        <strong>{label(EVALUATORS, entry.evaluator_id)}</strong>
        <span>{entry.versions.before.join(', ')} → {entry.versions.after.join(', ')} · provenance, pas un changement du logiciel</span></li>)}</ul></div>}
      {chosen?<div className={`change-detail cat-${chosen.tone}`}>
        <div className="change-detail-head"><span className="change-sign" aria-hidden="true">{chosen.sign}</span>
          <div><h3>{chosen.label} <span className="count-pill">{summary.totals[chosen.id]}</span></h3><p>{chosen.hint}</p></div></div>
        {summary.evaluators.filter(entry=>entry.comparable&&(entry.counts?.[chosen.id]??0)>0).map(entry=>
          <EvaluatorChanges key={entry.evaluator_id} base={base} request={request} summary={summary} category={chosen.id} entry={entry}
            project={project}/>)}
      </div>:<p className="comparison-empty">Choisissez un compte ci-dessus pour voir les faits concernés, preuves à l’appui.</p>}
    </>}
  </section>;
}

/** Une analyse comparee : sa lettre, ce qu'elle a lu et quand. */
function SideCard({letter, title, side}:Readonly<{letter:string; title:string; side:Side}>){
  return <div className={`side-card side-${letter.toLowerCase()}`}><b className="side-letter" aria-hidden="true">{letter}</b>
    <div><span className="eyebrow">Analyse {letter} · {title}</span><code>{sideLabel(side)}</code><span className="side-date">{day(side.created_at)}</span></div></div>;
}

/** Depuis la vue d'ensemble : comparer l'analyse affichee avec une autre, ou choisir librement les deux. */
export function CompareLauncher({current, count, onPick}:Readonly<{current:Side; count:number; onPick:(fixed?:string)=>void}>){
  return <section className="compare-launch" aria-label="Comparer">
    <div className="compare-intro"><strong>Comparer deux analyses</strong>
      <span className="muted">Ce qui a changé entre deux analyses Taxo, preuves à l’appui, sans relire le dépôt.</span></div>
    <div className="compare-flow">
      <div className="compare-current"><span className="eyebrow">Analyse affichée</span><code>{sideLabel(current)}</code><span className="side-date">{day(current.created_at)}</span></div>
      {count>1?<div className="compare-buttons">
        <button type="button" className="primary" onClick={()=>onPick(current.id)}>Comparer avec… →</button>
        <button type="button" className="ghost" onClick={()=>onPick()}>Choisir deux analyses</button></div>
        :<p className="muted">Une seule analyse complète : relancez l’analyse pour pouvoir comparer.</p>}
    </div>
  </section>;
}
