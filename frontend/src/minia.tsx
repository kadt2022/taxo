// Reponse de Minia (TAXO-MINIA-01) : les faits de Taxo, l'interpretation de Minia et ce qui reste inconnu,
// toujours separes. Les faits affiches sont ceux de Taxo, jamais du texte du modele.
import type {FactChange} from './diff';

type Evidence = {path:string; line_start?:number; line_end?:number};
export type CitedFact = FactChange & {ref:string; evaluator_id:string; evidence_before:Evidence[]; evidence_after:Evidence[]};
export type MiniaAnswer = {status:'ANSWERED'|'TAXO_KNOWS_NOTHING'; question:string; commit:string; parent:string|null;
  model:{configured:boolean; provider:string|null; model:string|null}; facts:CitedFact[]; answer:string; unknown:string;
  not_interpreted:string[]; failures:string[]; facts_not_sent:number; rejected_citations:string[]};

/** Localisation d'une preuve : chemin, puis lignes quand elles sont connues. */
export function place(evidence:Evidence){
  if(evidence.line_start===undefined)return evidence.path;
  return evidence.line_end!==undefined&&evidence.line_end!==evidence.line_start
    ?`${evidence.path}:${evidence.line_start}-${evidence.line_end}`:`${evidence.path}:${evidence.line_start}`;
}

/** Tout ce qui limite la reponse : le texte de Minia, puis les limites que Taxo connait lui-meme. */
export function gaps(answer:MiniaAnswer){
  const items=answer.unknown?[answer.unknown]:[];
  if(answer.not_interpreted.length)items.push(`Zones non interprétées par Taxo : ${answer.not_interpreted.join(', ')}.`);
  if(answer.failures.length)items.push(`Évaluateurs en échec : ${answer.failures.join(' ; ')}.`);
  if(answer.facts_not_sent)items.push(`${answer.facts_not_sent} faits n’ont pas été transmis à Minia (limite de taille).`);
  if(answer.rejected_citations.length)items.push(`Références inventées par Minia et écartées : ${answer.rejected_citations.join(', ')}.`);
  return items;
}

export function MiniaView({answer}:Readonly<{answer:MiniaAnswer}>){
  const limits=gaps(answer);
  return <section className="minia" aria-label="Réponse de Minia">
    <p className="eyebrow">MINIA{answer.model.model?` · ${answer.model.provider} ${answer.model.model}`:''}</p>
    <p className="minia-question">{answer.question}</p>
    <div className="minia-blocks">
      <article className="minia-block fact">
        <h3>Fait Taxo</h3>
        {answer.facts.length?<ul>{answer.facts.map(f=><li key={f.ref}>
          <code>{f.subject}</code> {f.relation??f.kind}
          {f.before===null&&f.after===null?null:<> : <code>{f.before??'∅'}</code> → <code>{f.after??'∅'}</code></>}
          <span className="muted"> · {f.status} · {f.evaluator_id}</span>
          {[...f.evidence_before,...f.evidence_after].map(e=><span className="evidence" key={place(e)}>{place(e)}</span>)}
        </li>)}</ul>:<p className="muted">Aucun fait de Taxo n’appuie cette réponse.</p>}
      </article>
      <article className="minia-block interpretation">
        <h3>Interprétation Minia <span className="badge">non vérifiée</span></h3>
        <p>{answer.answer||'Minia ne propose aucune interprétation.'}</p>
      </article>
      <article className="minia-block unknown">
        <h3>Inconnu / non interprété</h3>
        {limits.length?<ul>{limits.map(item=><li key={item}>{item}</li>)}</ul>:<p className="muted">Aucune limite signalée.</p>}
      </article>
    </div>
    <footer>Minia ne lit ni le dépôt ni le code : elle ne reçoit que les faits de Taxo, leurs preuves et la couverture. Sa réponse n’est jamais enregistrée comme un fait.</footer>
  </section>;
}
