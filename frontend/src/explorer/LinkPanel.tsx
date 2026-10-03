// Le détail d'un lien (TAXO-01J § 9, tranche E) : sujet, relation, objet, puis chaque occurrence avec son statut, son
// analyseur, sa dérivation et ses preuves, résumées dans la Tuile ou chargées par sa poignée. Aucun contenu de fichier.
import {useState} from 'react';
import {DerivationView, proofText} from '../exploration';
import {EVALUATORS, ORIGINS, VALIDITIES, label} from '../vocabulary';
import type {Link, ViewElement} from './graph';
import {evidenceOf, type Location, type Query} from './protocol';
import {verb} from './sentences';
import {useNaming} from './Naming';

export function LinkPanel({link, query, onClose}:Readonly<{link:Link; query:Query; onClose:()=>void}>){
  const named=useNaming();
  return <section className="explorer-panel" aria-label="Détail du lien">
    <div className="explorer-panel-head"><h3>{named(link.subject)} <span className="explorer-verb">{verb(link.relation)}</span> {named(link.object)}</h3>
      <button type="button" className="link" onClick={onClose}>Fermer</button></div>
    <dl className="explorer-triple">
      <div><dt>Sujet</dt><dd><code>{link.subject}</code></dd></div>
      <div><dt>Relation</dt><dd><code>{link.relation}</code></dd></div>
      <div><dt>Objet</dt><dd><code>{link.object}</code></dd></div>
    </dl>
    <h4>{link.elements.length} occurrence{link.elements.length>1?'s':''}</h4>
    <ol className="explorer-occurrences">{link.elements.map(element=><li key={element.occurrence}>
      <Occurrence element={element} query={query}/></li>)}</ol>
  </section>;
}

function Occurrence({element, query}:Readonly<{element:ViewElement; query:Query}>){
  const {fact}=element, producer=fact.produced_by;
  return <article aria-label={`Occurrence ${element.ref}`}>
    <p><strong>{label(ORIGINS, fact.status??'')}</strong>{fact.validity&&<> · {label(VALIDITIES, fact.validity)}</>}
      {producer?.producer_id&&<> · {label(EVALUATORS, producer.producer_id)} <span className="muted">{producer.producer_version}</span></>}
      {element.revisit&&<span className="count-pill">revisite</span>}</p>
    {fact.status==='INFERRED'&&fact.derivation&&<DerivationView derivation={fact.derivation}/>}
    <Proofs element={element} query={query}/>
  </article>;
}

type Loaded={state:'idle'|'loading'|'done'|'error'; locations:Location[]; error:string};

/** Les preuves d'une occurrence : celles résumées dans la Tuile, sinon chargées à la demande par sa poignée. */
function Proofs({element, query}:Readonly<{element:ViewElement; query:Query}>){
  const [loaded,setLoaded]=useState<Loaded>({state:'idle', locations:[], error:''});
  if(element.evidence_count===0)return <p className="muted">Aucune preuve enregistrée pour cette occurrence.</p>;
  const summarized=Array.isArray(element.evidence)?element.evidence:null;
  const shown=summarized??(loaded.state==='done'?loaded.locations:null);
  async function load(){
    setLoaded({state:'loading', locations:[], error:''});
    try{setLoaded({state:'done', locations:(await evidenceOf(query, element.occurrence)).map(proof=>proof.location), error:''});}
    catch(error){setLoaded({state:'error', locations:[], error:(error as Error).message});}
  }
  if(shown)return <ul className="proofs" aria-label="Preuves">{shown.map((location, index)=><li key={`${index}:${proofText(location)}`}>
    <code>{proofText(location)}</code></li>)}</ul>;
  return <div className="explorer-proofs-pending">
    <button type="button" className="ghost" disabled={loaded.state==='loading'} onClick={load}>
      {loaded.state==='loading'?'Chargement des preuves…':`Charger les preuves (${element.evidence_count})`}</button>
    {loaded.state==='error'&&<p role="alert" className="error">{loaded.error}</p>}
  </div>;
}
