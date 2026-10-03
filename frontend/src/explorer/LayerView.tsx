// La vue en couches (TAXO-01J § 9) : une colonne par niveau, les liens en SVG, orientés dans le sens réel du fait.
// Les revisites en pointillé vers le nœud existant ; un lien de plusieurs occurrences porte leur nombre. Le SVG ne fait
// que tracer : les nœuds et les liens se choisissent par de vrais boutons, posés sur le tracé. La mise en page est
// calculée par `layout.ts`.
import {useId, useMemo} from 'react';
import type {Link, View} from './graph';
import {GEOMETRY, layout} from './layout';
import type {Selected} from './state';
import {factText, nodeMarks} from './sentences';
import {useNaming} from './Naming';

const classes=(...names:(string|false)[])=>names.filter(Boolean).join(' ');

export function LayerView({view, links, selected, onSelect}:Readonly<{view:View; links:Link[]; selected:Selected;
  onSelect:(selected:Selected)=>void}>){
  const arrow=useId(), named=useNaming();
  const placed=useMemo(()=>layout(view, links), [view, links]);
  const levels=[...new Set([...placed.nodes, ...placed.leaves].map(node=>node.level))];
  const nodes=new Map(view.nodes.map(node=>[node.reference, node]));
  return <div className="explorer-layers"><div className="explorer-canvas" style={{width:placed.width, height:placed.height}}>
    <svg width={placed.width} height={placed.height} aria-hidden="true">
      <defs><marker id={arrow} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0 0L10 5L0 10z"/></marker></defs>
      {placed.edges.map(edge=><path key={edge.link.identity} d={edge.path} markerEnd={`url(#${arrow})`}
        className={classes('explorer-edge', edge.dashed&&'revisit', selected?.kind==='link'&&selected.identity===edge.link.identity&&'chosen')}/>)}
    </svg>
    {levels.map(level=><span key={level} className="explorer-column" style={{left:GEOMETRY.margin+level*GEOMETRY.column}}>
      {level===0?'Ancre':`Niveau ${level}`}</span>)}
    {placed.edges.map(edge=>{
      const chosen=selected?.kind==='link'&&selected.identity===edge.link.identity;
      return <button type="button" key={edge.link.identity} className={classes('explorer-edge-handle', edge.dashed&&'revisit')}
        style={{left:edge.label.x, top:edge.label.y}} aria-pressed={chosen}
        aria-label={`${factText(edge.link, named)}, ${edge.count} occurrence${edge.count>1?'s':''}${edge.dashed?', revisite':''}`}
        onClick={()=>onSelect({kind:'link', identity:edge.link.identity})}>{edge.count>1?`×${edge.count}`:''}</button>;
    })}
    {placed.leaves.map(leaf=><button type="button" key={leaf.reference} className="explorer-node explorer-value"
      style={{left:leaf.x, top:leaf.y, width:GEOMETRY.width, height:GEOMETRY.height}}
      aria-pressed={selected?.kind==='link'&&selected.identity===leaf.reference}
      aria-label={leaf.value===undefined?'Aucun objet : ce fait n’en a pas':`Valeur ${leaf.value}, pas un nœud`}
      onClick={()=>onSelect({kind:'link', identity:leaf.reference})}>
      <span className="explorer-node-name">{leaf.value??'aucun objet'}</span>
      <span className="explorer-node-mark">{leaf.value===undefined?'ce fait n’a pas d’objet':'valeur, pas un nœud'}</span>
    </button>)}
    {placed.nodes.map(node=>{
      const marks=nodeMarks(nodes.get(node.reference)!, view.selection[node.reference], view.knowledge);
      const chosen=selected?.kind==='node'&&selected.reference===node.reference;
      const name=named(node.reference);
      return <button type="button" key={node.reference} title={node.reference} aria-pressed={chosen}
        className={classes('explorer-node', marks.length>0&&'marked', node.reference===view.anchor&&'anchor')}
        style={{left:node.x, top:node.y, width:GEOMETRY.width, height:GEOMETRY.height}}
        aria-label={[name, ...marks].join(', ')} onClick={()=>onSelect({kind:'node', reference:node.reference})}>
        <span className="explorer-node-name">{name}</span>
        {marks.length>0&&<span className="explorer-node-mark">{marks.join(' · ')}</span>}
      </button>;
    })}
  </div></div>;
}
