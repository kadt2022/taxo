// La vue en liste (TAXO-01J § 9) : la même vue que les couches, au clavier et pour les lecteurs d'écran. C'est la vue
// de référence des tests. Un niveau par section ; sous chaque nœud, ses marques, ses actions et les liens qu'il a fait
// découvrir, chacun avec son nombre d'occurrences.
import type {Link, View} from './graph';
import {linksAt} from './graph';
import {NodeActions, type NodeCommands} from './NodeActions';
import {factText, nodeMarks, nodeType, verb} from './sentences';
import {useNaming} from './Naming';

export function ListView({view, links, commands, busy, onSelect}:Readonly<{view:View; links:Link[]; commands:NodeCommands;
  busy:boolean; onSelect:(identity:string)=>void}>){
  const named=useNaming();
  const levels=[...new Set(view.nodes.map(node=>node.level))].sort((a, b)=>a-b);
  return <div className="explorer-list">{levels.map(level=><section key={level} aria-label={`Niveau ${level}`}>
    <h3>{level===0?'Ancre':`Niveau ${level}`}</h3>
    <ul>{view.nodes.filter(node=>node.level===level).map(node=>{
      const marks=nodeMarks(node, view.selection[node.reference], view.knowledge);
      const found=linksAt(links, node.reference).from;
      return <li key={node.reference} aria-label={named(node.reference)}>
        <p className="explorer-node-line"><span className="explorer-type">{nodeType(node.reference)||'référence'}</span>
          <strong>{named(node.reference)}</strong>
          {marks.map(mark=><span key={mark} className="explorer-mark">{mark}</span>)}
          <NodeActions reference={node.reference} boundary={view.selection[node.reference]} commands={commands} busy={busy}
            anchor={node.reference===view.anchor}/></p>
        {found.length>0&&<ul className="explorer-links">{found.map(link=>{
          const far=link.subject===node.reference?link.object:link.subject;
          const outgoing=link.subject===node.reference;
          const count=link.elements.length;
          const said=outgoing?`${verb(link.relation)} ${named(far)}`:`${named(far)} ${verb(link.relation)} ce nœud`;
          return <li key={link.identity}><button type="button" className="link" onClick={()=>onSelect(link.identity)}
            aria-label={`${factText(link, named)}, ${count} occurrence${count>1?'s':''}${link.revisit?', revisite':''}`}>
            {outgoing?'→':'←'} {said}</button>
            {count>1&&<span className="count-pill">×{count}</span>}{link.revisit&&<span className="explorer-mark">revisite</span>}</li>;
        })}</ul>}
      </li>;
    })}</ul>
  </section>)}</div>;
}
