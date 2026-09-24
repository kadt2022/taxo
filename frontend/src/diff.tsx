// Diff d'un fichier (TAXO-HIST-02) et faits Taxo relies a ses lignes (TAXO-HIST-03).
import {lineLabel, markedLines, type LinkLines} from './links';

export type FactChange = {change:'INTRODUCED'|'REMOVED'|'MODIFIED'; kind:string; subject:string; relation:string|null; status:string; before:string|null; after:string|null};
export type DiffLine = {number:number; text:string; eol:'LF'|'CRLF'|'NONE'};
type DiffRow = {kind:'equal'|'changed'|'added'|'removed'; before:DiffLine|null; after:DiffLine|null};
export type FileDiff = {path:string; old_path:string|null; status:string; commit:string; parent:string|null; displayable:boolean;
  reason:string|null; before:{path:string; size:number}|null; after:{path:string; size:number}|null;
  hunks:{before_start:number; after_start:number; rows:DiffRow[]}[]};
export type LinkedFact = FactChange & {evaluator_id:string; precision:'LINE'|'FILE'; lines:LinkLines};
export type DiffFacts = {path:string; commit:string; parent:string|null; facts:LinkedFact[]; not_comparable:string[]};
const DIFF_REASONS:Record<string,string>={
  CONFIDENTIAL:'Fichier confidentiel : Taxo le nomme, mais n’affiche jamais son contenu.',
  BINARY:'Fichier binaire : il n’y a pas de diff texte à afficher.',
  TOO_LARGE:'Fichier trop volumineux (plus de 1 Mo) : son contenu n’est pas affiché.',
  NOT_A_REGULAR_FILE:'Lien symbolique ou sous-module : son contenu n’est pas affiché.',
};

// Une fin de ligne differente reste visible : LF, la plus courante, n'est pas signalee.
const EOL_MARKS:Record<DiffLine['eol'],string>={LF:'',CRLF:'␍␊',NONE:'sans fin de ligne'};
function DiffCode({line,changed}:Readonly<{line:DiffLine|null; changed:boolean}>){
  const mark=line&&changed?EOL_MARKS[line.eol]:'';
  return <><code>{line?.text??''}</code>{mark===''?null:<span className="eol">{mark}</span>}</>;
}

function LinkedFacts({links}:Readonly<{links:DiffFacts}>){
  return <section className="linked-facts" aria-label="Faits touchés par ce fichier">
    <h3>Faits Taxo touchés par ce fichier</h3>
    {links.not_comparable.length>0&&<p role="alert" className="error">Comparaison impossible pour {links.not_comparable.join(', ')} : ses faits ne sont pas reliés.</p>}
    {links.facts.length?<ul>{links.facts.map(f=><li key={f.evaluator_id+f.change+f.subject+f.relation+(f.before??'')+(f.after??'')}>
      <strong>{CHANGE_LABELS[f.change]}</strong> <code>{f.subject}</code> {f.relation??f.kind}
      {f.before===null&&f.after===null?null:<> : <code>{f.before??'∅'}</code> → <code>{f.after??'∅'}</code></>}
      <span className={f.precision==='LINE'?'precision line':'precision'}>{lineLabel(f.lines)}</span>
      <span className="muted"> · {f.evaluator_id} · {f.status}</span>
    </li>)}</ul>:<p className="muted">Aucun fait changé par ce commit n’a sa preuve dans ce fichier.</p>}
    <footer>Le lien passe par les preuves des faits, jamais par une lecture du texte. Seuls les faits que les évaluateurs savent produire sont reliés.</footer>
  </section>;
}

export function DiffView({diff,links}:Readonly<{diff:FileDiff; links:DiffFacts|null}>){
  const marked=markedLines(links?.facts??[]);
  const number=(line:DiffLine|null,side:'before'|'after')=>line&&marked[side].has(line.number)?<td className="number linked" title="Ligne reliée à un fait Taxo">◆ {line.number}</td>:<td className="number">{line?.number??''}</td>;
  const side=(label:string,value:FileDiff['before'],ref:string|null)=>value?`${label} — ${value.path}${ref?' @ '+ref.slice(0,7):''}`:`${label} — (aucun fichier)`;
  return <section className="diff-view" aria-label="Diff du fichier">
    <p className="eyebrow">DIFF — CE QUE GIT MONTRE</p>
    <h2><code>{diff.old_path?`${diff.old_path} → ${diff.path}`:diff.path}</code></h2>
    {!diff.displayable?<p className="muted">{DIFF_REASONS[diff.reason??'']??'Contenu non disponible.'}</p>
    :diff.hunks.length===0?<p className="muted">Aucune ligne modifiée : seul le nom ou le mode du fichier a changé.</p>
    :<div className="table-wrap"><table className="diff">
      <colgroup><col className="number-col"/><col/><col className="number-col"/><col/></colgroup>
      <thead><tr><th colSpan={2}>{side('AVANT',diff.before,diff.parent)}</th><th colSpan={2}>{side('APRÈS',diff.after,diff.commit)}</th></tr></thead>
      {diff.hunks.map(h=><tbody key={`${h.before_start}-${h.after_start}`}>
        <tr className="hunk"><td colSpan={4}>@@ ligne {h.before_start} → ligne {h.after_start}</td></tr>
        {h.rows.map(r=><tr key={`${r.before?.number??'-'}-${r.after?.number??'-'}`} className={'diff-'+r.kind}>
          {number(r.before,'before')}<td className={r.before&&r.kind!=='equal'?'removed':''}><DiffCode line={r.before} changed={r.kind!=='equal'}/></td>
          {number(r.after,'after')}<td className={r.after&&r.kind!=='equal'?'added':''}><DiffCode line={r.after} changed={r.kind!=='equal'}/></td>
        </tr>)}
      </tbody>)}
    </table></div>}
    {links&&<LinkedFacts links={links}/>}
  </section>;
}
export const CHANGE_LABELS:Record<FactChange['change'],string>={INTRODUCED:'Ajouté',REMOVED:'Retiré',MODIFIED:'Modifié'};
