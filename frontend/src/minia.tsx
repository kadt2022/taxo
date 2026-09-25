// Reponse de Minia (TAXO-MINIA-01) : les faits de Taxo, l'interpretation de Minia et ce qui reste inconnu,
// toujours separes. Les faits affiches sont ceux de Taxo, jamais du texte du modele.
import {CHANGE_LABELS, type FactChange} from './diff';
import {EVALUATORS, VERBS, label, reference} from './vocabulary';

type Evidence = {path:string; line_start?:number; line_end?:number};
export type CitedFact = FactChange & {ref:string; evaluator_id:string; evidence_before:Evidence[]; evidence_after:Evidence[]};
type GitFile = {status:string; path:string; old_path:string|null};
export type GitCommit = {sha:string; parent:string|null; author:string; authored_at:string; subject:string; files:GitFile[]};
export type MiniaAnswer = {status:'ANSWERED'|'TAXO_KNOWS_NOTHING'; question:string; commit:string; parent:string|null;
  project:{id:string; name:string}; git:GitCommit; files_not_sent:number;
  model:{configured:boolean; provider:string|null; model:string|null}; facts:CitedFact[]; answer:string; unknown:string;
  not_interpreted:string[]; failures:string[]; facts_not_sent:number; rejected_citations:string[]};

/** Localisation d'une preuve : chemin, puis lignes quand elles sont connues. */
export function place(evidence:Evidence){
  if(evidence.line_start===undefined)return evidence.path;
  return evidence.line_end!==undefined&&evidence.line_end!==evidence.line_start
    ?`${evidence.path}:${evidence.line_start}-${evidence.line_end}`:`${evidence.path}:${evidence.line_start}`;
}

const FILE_STATUS:Record<string,string>={ADDED:'ajouté',MODIFIED:'modifié',DELETED:'supprimé',RENAMED:'renommé',COPIED:'copié',TYPE_CHANGED:'type modifié'};

/** Le depot est designe par le nom du projet, pas par son identifiant interne. */
export function named(value:string|null, project:MiniaAnswer['project']){
  return value===`repository:${project.id}`?`dépôt ${project.name}`:value;
}

/** Un fichier du commit, tel que Git le decrit ; un renommage montre l'ancien et le nouveau chemin. */
export function gitFile(file:GitFile){
  const status=FILE_STATUS[file.status]??file.status;
  return file.old_path?`${file.old_path} → ${file.path} (${status})`:`${file.path} (${status})`;
}

/** Le fait dit en une phrase : sujet, ce que la relation affirme, et la valeur avant ou apres le commit. */
export function sentence(fact:CitedFact, project:MiniaAnswer['project']){
  const who=reference(fact.subject,project), verb=fact.relation?label(VERBS,fact.relation):fact.kind.toLowerCase();
  const before=reference(fact.before,project), after=reference(fact.after,project);
  if(before!==null&&after!==null)return `${who} ${verb} : ${before} → ${after}`;
  const value=after??before;
  return value===null?`${who} ${verb}`:`${who} ${verb} ${value}`;
}

/** Tout ce qui limite la reponse : le texte de Minia, puis les limites que Taxo connait lui-meme. */
export function gaps(answer:MiniaAnswer){
  const items=answer.unknown?[answer.unknown]:[];
  if(answer.not_interpreted.length)items.push(`Non analysé par Taxo : ${answer.not_interpreted.join(', ')}.`);
  if(answer.failures.length)items.push(`Analyses en échec : ${answer.failures.join(' ; ')}.`);
  if(answer.files_not_sent)items.push(`${answer.files_not_sent} fichiers du commit n’ont pas été transmis à Minia (limite de taille).`);
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
        <h3>Ce que Taxo sait</h3>
        <dl className="minia-commit">
          <div><dt>Commit</dt><dd><code>{answer.git.sha.slice(0,12)}</code> · {answer.git.author} · {new Date(answer.git.authored_at).toLocaleString('fr-CA')}</dd></div>
          <div><dt>Message</dt><dd>{answer.git.subject}</dd></div>
          <div><dt>Fichiers</dt><dd>{answer.git.files.length?<ul>{answer.git.files.map(f=><li key={f.path}>{gitFile(f)}</li>)}</ul>:'aucun'}</dd></div>
        </dl>
        {answer.facts.length?<ul>{answer.facts.map(f=><li key={f.ref}>
          <strong>{CHANGE_LABELS[f.change]}</strong> {sentence(f,answer.project)}
          <details className="proof"><summary>Preuve</summary>
            <code>{named(f.subject,answer.project)}</code> {f.relation??f.kind}
            {f.before===null&&f.after===null?null:<> : <code>{named(f.before,answer.project)??'∅'}</code> → <code>{named(f.after,answer.project)??'∅'}</code></>}
            <span className="muted"> · {f.status} · {label(EVALUATORS,f.evaluator_id)} ({f.evaluator_id})</span>
            {[...f.evidence_before,...f.evidence_after].map(e=><span className="evidence" key={place(e)}>{place(e)}</span>)}
          </details>
        </li>)}</ul>:<p className="muted">Aucun fait de Taxo n’appuie cette réponse.</p>}
      </article>
      <article className="minia-block interpretation">
        <h3>Ce que Minia en déduit <span className="badge">non vérifié</span></h3>
        <p>{answer.answer||'Minia ne propose aucune interprétation.'}</p>
      </article>
      <article className="minia-block unknown">
        <h3>Ce que Taxo ne sait pas</h3>
        {limits.length?<ul>{limits.map(item=><li key={item}>{item}</li>)}</ul>:<p className="muted">Aucune limite signalée.</p>}
      </article>
    </div>
    <footer>Minia ne lit ni le dépôt ni le code : elle ne reçoit que ce que Git sait du commit (sans contenu), les faits de Taxo, leurs preuves et la couverture. Sa réponse n’est jamais enregistrée comme un fait.</footer>
  </section>;
}
