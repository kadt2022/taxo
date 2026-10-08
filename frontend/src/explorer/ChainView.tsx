// La vue Chaîne (TAXO-UI-06) : la vue lue de haut en bas, en notation inspirée d'UML. Une boîte par nœud, teintée par
// son type et coiffée de son stéréotype ; une flèche nommée par lien, pleine dans la chaîne, en pointillé à triangle
// creux à côté ; la frontière en note, la coupure en pastille. Le SVG ne fait que tracer : nœuds, étiquettes et
// frontières sont de vrais boutons posés sur le tracé. La mise en page est calculée par `chain.ts`.
import {useId, useMemo, useRef, useState} from 'react';
import {FORMS, TONE_NAMES, label} from '../vocabulary';
import {chain, type Box, type ChainText, type Form} from './chain';
import {picture, type Palette} from './picture';
import {fileName, savePicture} from './savePicture';
import type {Link, View} from './graph';
import type {Selected} from './state';
import {compartments, factText, knowledgeText, linkMarks, nodeMarks, selectionText, toneOf, typeText, verb} from './sentences';
import {useNaming} from './Naming';
import type {NodeCommands} from './NodeActions';

const classes=(...names:(string|false|undefined)[])=>names.filter(Boolean).join(' ');
const formOf=(relation:string):Form=>FORMS[relation]??'CHAIN';

export function ChainView({view, links, selected, onSelect, commands, busy, viewName='Chaîne'}:Readonly<{view:View; links:Link[];
  selected:Selected; onSelect:(selected:Selected)=>void; commands:NodeCommands; busy:boolean; viewName?:string}>){
  const id=useId(), named=useNaming();
  const text:ChainText=useMemo(()=>({name:value=>compartments(value, named), note:knowledgeText,
    cut:boundary=>`${selectionText(boundary)} · ${boundary.continuation?'voir la suite':'développer'} ›`,
    revisit:(link, target)=>`↺ ${verb(link.relation)} ${named(target)}, montré ailleurs dans la vue`,
    leaf:value=>value===undefined?'aucun objet : ce fait n’en a pas':value}), [named]);
  const drawn=useMemo(()=>chain(view, links, formOf, text), [view, links, text]);
  const nodes=new Map(view.nodes.map(node=>[node.reference, node]));
  const chosenLink=(link?:Link)=>!!link&&selected?.kind==='link'&&selected.identity===link.identity;
  const tones=[...new Set(drawn.boxes.filter(box=>box.kind==='node').map(box=>toneOf(box.reference!)))];
  const forms=new Set(drawn.arrows.map(item=>item.form));
  const kinds=new Set(drawn.boxes.map(box=>box.kind));
  const marks=[...new Set(drawn.arrows.flatMap(item=>linkMarks(item.link)))];
  const frame=useRef<HTMLDivElement>(null), [saving,setSaving]=useState(false), [failure,setFailure]=useState('');
  const save=async()=>{
    const style=getComputedStyle(frame.current!), read=(name:string)=>style.getPropertyValue(name).trim();
    const palette:Palette={surface:read('--surface')||'#ffffff', text:read('--text')||'#142b25', muted:read('--muted')||'#6a7a71',
      line:read('--chain-line')||'#6f8f80', frontier:read('--tone-frontier')||'#c47a12', frontierSoft:read('--warn-soft')||'#fdf3e1',
      cut:read('--surface-3')||'#eef1eb', border:read('--border-strong')||'#cfd8cc'};
    const svg=picture(drawn, palette, box=>({stereo:`«${typeText(box.reference!)}»${box.anchor?' · ancre':''}`,
      tone:read(`--tone-${toneOf(box.reference!)}`)||palette.line}), item=>({verb:verb(item.link.relation), marks:linkMarks(item.link)}));
    setSaving(true);setFailure('');
    try{await savePicture(svg, drawn.width, drawn.height, fileName('taxo', viewName, named(view.anchor)));}
    catch{setFailure('L’image n’a pas pu être créée par ce navigateur.');}
    finally{setSaving(false);}
  };
  return <div className="chain">
    <div className="chain-tools">
      <button type="button" className="ghost" onClick={()=>{void save();}} disabled={saving}>{saving?'Création de l’image…':'Exporter en image (PNG)'}</button>
      {failure&&<span role="alert" className="error">{failure}</span>}</div>
    <div className="explorer-layers chain-scroll" ref={frame}><div className="explorer-canvas" style={{width:drawn.width, height:drawn.height}}>
      <svg width={drawn.width} height={drawn.height} aria-hidden="true">
        <defs>
          <marker id={`${id}-flow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
            <path className="chain-head" d="M0 0L10 5L0 10z"/></marker>
          <marker id={`${id}-side`} viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto-start-reverse">
            <path className="chain-hollow" d="M1 1L11 6L1 11z"/></marker>
        </defs>
        {drawn.ties.map(tie=><path key={`tie:${tie.box.key}`} d={tie.path} className={`chain-tie ${tie.box.kind}`}/>)}
        {drawn.arrows.map(item=><path key={item.link.identity} d={item.path}
          markerEnd={`url(#${id}-${item.form==='SIDE'?'side':'flow'})`}
          className={classes('chain-arrow', item.form==='SIDE'&&'side', item.link.revisit&&'revisit', chosenLink(item.link)&&'chosen')}/>)}
      </svg>
      {drawn.arrows.map(item=>{
        const {link}=item, count=link.elements.length;
        return <button type="button" key={`label:${link.identity}`} className={classes('chain-label', item.form==='SIDE'&&'side')}
          style={{left:item.label.x, top:item.label.y}} aria-pressed={chosenLink(link)}
          aria-label={`${factText(link, named)}, ${count} occurrence${count>1?'s':''}`}
          onClick={()=>onSelect({kind:'link', identity:link.identity})}>
          {verb(link.relation)}{linkMarks(link).map(mark=><span key={mark} className={`chain-status status-${mark}`}>{mark}</span>)}
          {count>1&&<span className="chain-count">×{count}</span>}</button>;
      })}
      {drawn.boxes.map(box=><Shape key={box.key} box={box} view={view} nodes={nodes} selected={selected} onSelect={onSelect} commands={commands}
        busy={busy} viewName={viewName}/>)}
    </div></div>
    <details className="chain-legend" open><summary>Légende</summary>
      <ul>
        {tones.map(tone=><li key={tone}><span className={`chain-swatch tone-${tone}`}/>{label(TONE_NAMES, tone)}</li>)}
        {forms.has('CHAIN')&&<li><svg className="chain-key" viewBox="0 0 40 12" aria-hidden="true"><path className="chain-arrow" d="M2 6H32"/>
          <path className="chain-head" d="M30 1L39 6L30 11z"/></svg>relation de la chaîne, nommée sur sa flèche</li>}
        {forms.has('SIDE')&&<li><svg className="chain-key" viewBox="0 0 40 12" aria-hidden="true"><path className="chain-arrow side" d="M2 6H29"/>
          <path className="chain-hollow" d="M29 1L39 6L29 11z"/></svg>à côté de la chaîne, comme une réalisation UML</li>}
        {kinds.has('note')&&<li><span className="chain-swatch note"/>frontière : ce que Taxo ne sait pas</li>}
        {kinds.has('cut')&&<li><span className="chain-swatch cut"/>coupure de la vue : la suite se reprend</li>}
        {kinds.has('leaf')&&<li><span className="chain-swatch leaf"/>valeur ou aucun objet : pas un nœud</li>}
        {marks.map(mark=><li key={mark}><span className={`chain-status status-${mark}`}>{mark}</span>{MARK_NAMES[mark]??mark}</li>)}
      </ul>
    </details>
  </div>;
}

const MARK_NAMES:Record<string, string>={O:'observé dans le code', D:'déduit par Taxo', V:'validé par une personne'};

function Shape({box, view, nodes, selected, onSelect, commands, busy, viewName}:Readonly<{box:Box; view:View;
  nodes:Map<string, View['nodes'][number]>; selected:Selected; onSelect:(selected:Selected)=>void; commands:NodeCommands; busy:boolean;
  viewName:string}>){
  const named=useNaming();
  const style={left:box.x, top:box.y, width:box.width, height:box.height};
  const lines=box.lines.map((said, index)=><span key={index} className="chain-line">{said}</span>);
  if(box.kind==='node'){
    const reference=box.reference!, node=nodes.get(reference)!;
    const marks=nodeMarks(node, view.selection[reference], view.knowledge);
    return <button type="button" title={reference} style={style} aria-pressed={selected?.kind==='node'&&selected.reference===reference}
      className={classes('chain-node', `tone-${toneOf(reference)}`, box.anchor&&'anchor')}
      aria-label={[named(reference), ...marks].join(', ')} onClick={()=>onSelect({kind:'node', reference})}>
      <span className="chain-stereo">«{typeText(reference)}»{box.anchor&&' · ancre'}</span>
      <span className="chain-name">{lines}</span>
      {box.context!.length>0&&<span className="chain-context">{box.context!.map((said, index)=><span key={index} className="chain-line">{said}</span>)}</span>}
      {box.member!.length>0&&<span className="chain-member">{box.member!.map((said, index)=><span key={index} className="chain-line">{said}</span>)}</span>}
      </button>;
  }
  if(box.kind==='note')return <div role="note" className="chain-note" style={style}>
    <span className="chain-note-title">Frontière · Taxo ne sait pas</span>{lines}</div>;
  if(box.kind==='cut'){
    const reference=box.reference!, more=!!box.boundary?.continuation;
    return <button type="button" className="chain-cut" style={style} disabled={busy}
      aria-label={`${more?'Voir la suite de':'Développer'} ${named(reference)}, depuis la vue ${viewName}`}
      onClick={()=>(more?commands.more:commands.expand)(reference)}>{lines}</button>;
  }
  const link=box.link!, chosen=selected?.kind==='link'&&selected.identity===link.identity;
  if(box.kind==='leaf')return <button type="button" className="chain-leaf" style={style} aria-pressed={chosen}
    aria-label={box.value===undefined?'Aucun objet : ce fait n’en a pas':`Valeur ${box.value}, pas un nœud`}
    onClick={()=>onSelect({kind:'link', identity:link.identity})}>{lines}</button>;
  const target=box.reference!;
  return <button type="button" className="chain-revisit" style={style} aria-pressed={selected?.kind==='node'&&selected.reference===target}
    aria-label={`${factText(link, named)}, montré ailleurs : choisir ${named(target)}`}
    onClick={()=>onSelect({kind:'node', reference:target})}>{lines}</button>;
}
