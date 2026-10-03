// Ce que la vue ne montre pas, et pourquoi (TAXO-01J § 9, tranche E) : les coupures de sélection, qui se reprennent,
// à part de ce que Taxo ne sait pas (connaissance) ou ne peut pas savoir ici (contexte). Un budget ne lève jamais une
// zone non lue.
import type {Boundary} from './protocol';
import {omitted, type View} from './graph';
import {knowledgeText, notSentText, selectionText} from './sentences';
import {useNaming} from './Naming';
import {NodeActions, type NodeCommands} from './NodeActions';

export function Boundaries({view, commands, busy}:Readonly<{view:View; commands:NodeCommands; busy:boolean}>){
  const named=useNaming();
  const cuts=view.nodes.map(node=>[node.reference, view.selection[node.reference]] as const)
    .filter((entry):entry is readonly [string, Boundary]=>!!entry[1]);
  const knowledge=view.knowledge.filter(entry=>entry.nature==='KNOWLEDGE');
  const context=view.knowledge.filter(entry=>entry.nature==='CONTEXT');
  const notSent=omitted(view);
  return <section className="explorer-boundaries" aria-label="Ce que la vue ne montre pas">
    <h3>Ce que la vue ne montre pas</h3>
    <h4>Coupures de la vue <span className="count-pill">{cuts.length}</span></h4>
    {cuts.length?<ul>{cuts.map(([reference, boundary])=><li key={reference}>
      <strong>{named(reference)}</strong> — {selectionText(boundary)}
      <NodeActions reference={reference} boundary={boundary} commands={commands} busy={busy}/></li>)}</ul>
      :<p className="muted">Aucune : chaque nœud de la vue est développé pour les pas suivis.</p>}
    {notSent.length>0&&<ul className="explorer-not-sent">{notSent.map(entry=><li key={entry.what}>{notSentText(entry)}</li>)}</ul>}
    <h4>Ce que Taxo ne sait pas <span className="count-pill">{knowledge.length}</span></h4>
    {knowledge.length?<ul>{knowledge.map(entry=><li key={JSON.stringify(entry)}>{entry.node&&entry.scope==='NODE'?<><strong>{named(entry.node)}</strong> — </>:null}
      {knowledgeText(entry)}</li>)}</ul>:<p className="muted">Aucune lacune signalée par Taxo pour les relations suivies.</p>}
    <h4>Ce que Taxo ne peut pas savoir ici <span className="count-pill">{context.length}</span></h4>
    {context.length?<ul>{context.map(entry=><li key={JSON.stringify(entry)}>{knowledgeText(entry)}</li>)}</ul>
      :<p className="muted">Chaque relation suivie a un analyseur exécuté.</p>}
  </section>;
}
