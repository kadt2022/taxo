// La page Explorer (TAXO-01J § 9) : choisir une ancre, voir ce qui la relie au reste sur plusieurs niveaux, développer,
// voir la suite, recentrer, consulter les preuves, et voir ce qui n'est pas montré. Elle ne parle qu'au protocole ;
// aucune règle ici : elle enchaîne les modules purs et transmet les choix.
import {useEffect, useMemo, useReducer, useRef, useState} from 'react';
import {day, sideLabel} from '../comparison';
import {href, go, type Route} from '../nav';
import {useChoices} from '../pages';
import {AnchorSearch} from './AnchorSearch';
import {CalendarIcon, CallsIcon, ChainIcon, ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon, GearIcon, ListIcon, StackIcon} from './icons';
import {Boundaries} from './Boundaries';
import {CodeTile} from './CodeTile';
import {CallsView} from './CallsView';
import {ChainView} from './ChainView';
import {linksOf, type View} from './graph';
import {LayerView} from './LayerView';
import {LinkPanel} from './LinkPanel';
import {ListView} from './ListView';
import {FULL_VALUES, windowAddress, type Full} from './OpenWindow';
import {CopyReference, NodeActions, OpenInEditor, type NodeCommands} from './NodeActions';
import {describe, openTile, queryOf, sourceOf, type Described, type Query, type Source, type TileDemand} from './protocol';
import {defaultRelations, relationChoices, type RelationChoice} from './relations';
import {naming, nodeMarks, scopeText, toneOf, typeText, viewText} from './sentences';
import {NamingContext, useNaming} from './Naming';
import {Settings} from './Settings';
import {INITIAL, NO_TRAIL, PRESETS, addressOf, canGoBack, canGoForward, reduce, settingsOf, visit, type Action, type Selected,
  type Settings as Chosen} from './state';

type Request=<T>(path:string, init?:RequestInit)=>Promise<T>;
const ACTIONS={open:'Ouverture de la vue…', expand:'Développement…', more:'Lecture de la suite…'};

/** Ce que l'analyse annonce, lu une fois par analyse. */
function useDescribed(query:Query, analysis:string){
  const [described,setDescribed]=useState<{analysis:string; value:Described}|null>(null), [error,setError]=useState('');
  useEffect(()=>{
    const controller=new AbortController();
    setError('');
    describe(query, controller.signal).then(value=>setDescribed({analysis, value}),
      reason=>{if((reason as Error).name!=='AbortError')setError((reason as Error).message);});
    return ()=>controller.abort();
  },[query, analysis]);
  return {described:described?.analysis===analysis?described.value:null, error};
}

export function ExplorerPage({base, request, scanId, route, revision, project}:Readonly<{base:string; request:Request; scanId:string;
  route:Route; revision:string; project?:{id:string; name:string}}>){
  const settings=settingsOf(route.params);
  const analysis=settings.analysis??scanId;
  const query=useMemo(()=>queryOf(request, base, analysis), [request, base, analysis]);
  const source=useMemo(()=>sourceOf(request, base, analysis), [request, base, analysis]);
  const {described, error:describeError}=useDescribed(query, analysis);
  const choices=useMemo(()=>described?relationChoices(described):[], [described]);
  const relations=settings.relations.length?settings.relations:defaultRelations(choices);
  const [state,dispatch]=useReducer(reduce, INITIAL);
  const [shape,setShape]=useState<Shape>('chaine');
  const counter=useRef(0), running=useRef<AbortController|null>(null);
  const address=href('explorer', undefined, addressOf(settings));
  const [trail,setTrail]=useState(NO_TRAIL);
  useEffect(()=>setTrail(past=>visit(past, address)), [address]);
  const demand=(root:string, depth:number, continuation?:string):TileDemand=>({root, relations, direction:settings.direction, depth,
    budget:PRESETS[settings.preset], continuation});

  function run(action:'open'|'expand'|'more', wanted:TileDemand, node?:string){
    running.current?.abort();
    const controller=new AbortController();
    running.current=controller;
    const id=++counter.current;
    dispatch({type:'start', pending:{id, action, node}});
    openTile(query, wanted, controller.signal).then(tile=>dispatch({type:'loaded', id, tile}),
      reason=>{if((reason as Error).name!=='AbortError')dispatch({type:'failed', id, message:(reason as Error).message});});
  }
  // Une fenêtre à part (`plein=code` ou `plein=schema`) ne montre que le code d'une classe, ou le schéma, en grand.
  const asked=route.params.get('plein')??'';
  const full=FULL_VALUES.includes(asked)?asked as Full:undefined;
  // La fenêtre rouvre le même projet et la même analyse que la page : jamais ceux que le portail choisirait par défaut.
  const addressFor=(extra:Record<string, string>)=>windowAddress(route, globalThis.location,
    {...(project?{projet:project.id}:{}), analyse:analysis, ...extra});
  const opening=JSON.stringify([analysis, settings.root, relations, settings.direction, settings.depth, settings.preset]);
  useEffect(()=>{
    if(settings.root&&described&&relations.length&&full!=='code')run('open', demand(settings.root, settings.depth));
    return ()=>running.current?.abort();
  },[opening, described]);

  const navigate=(changed:Partial<Chosen>)=>go(href('explorer', undefined, addressOf({...settings, analysis, ...changed})));
  const commands:NodeCommands={
    expand:node=>run('expand', demand(node, Math.max(1, state.view?.selection[node]?.remaining_depth??0)), node),
    more:node=>{
      const boundary=state.view?.selection[node];
      if(boundary?.continuation)run('more', demand(node, Math.max(1, boundary.remaining_depth??0), boundary.continuation), node);
    },
    recenter:node=>navigate({root:node}),
  };
  const cancel=()=>{running.current?.abort();dispatch({type:'cancel'});};
  const busy=state.pending!==null;
  const named=useMemo(()=>naming(project), [project]);
  if(full)return <NamingContext.Provider value={named}><Windowed full={full} node={route.params.get('noeud')||undefined} appels={route.params.get('forme')==='appels'}
    source={source} view={state.view} selected={state.selected} dispatch={dispatch} commands={commands} busy={busy} choices={choices}
    followed={relations} hasRoot={!!settings.root} errors={[describeError, state.error].filter(Boolean)}/></NamingContext.Provider>;
  return <NamingContext.Provider value={named}><section className="page explorer" aria-label="Explorer">
    <div className="page-intro explorer-head">
      <div><h1>Explorer</h1><p>Choisissez un point de départ : Taxo montre ce qui le relie au reste, niveau par niveau, avec la preuve de chaque lien et ce qu’il ne montre pas.</p></div>
      <nav aria-label="Parcours des ancres" className="explorer-trail">
        <button type="button" className="ghost" disabled={!canGoBack(trail)} onClick={()=>globalThis.history.back()}>← Précédent</button>
        <button type="button" className="ghost" disabled={!canGoForward(trail)} onClick={()=>globalThis.history.forward()}>Suivant →</button>
      </nav>
    </div>
    {describeError&&<p role="alert" className="error">{describeError}</p>}
    <AnchorSearch query={query} types={described?.types??NO_TYPES} onPick={root=>navigate({root})}
      lead={<AnalysisChoice base={base} request={request} revision={revision} value={analysis} onChange={value=>navigate({analysis:value, root:undefined})}/>}
      tail={described&&<details className="explorer-settings-box explorer-card"><summary><GearIcon/><span>Réglages du parcours</span><ChevronDownIcon/></summary>
        <Settings key={opening} choices={choices} settings={settings} relations={relations} onApply={chosen=>navigate(chosen)}/></details>}/>
    {settings.root&&<p className="explorer-scope">{scopeText(relations, settings.direction, settings.depth)}</p>}
    {busy&&<output className="explorer-pending">{ACTIONS[state.pending!.action]} <button type="button" className="link" onClick={cancel}>Annuler</button></output>}
    {state.error&&<p role="alert" className="error">{state.error}</p>}
    {!settings.root&&<p className="muted">Aucun point de départ : recherchez une référence, ou ouvrez l’explorateur depuis une route, un module, un fichier ou un commit.</p>}
    {described&&settings.root&&!relations.length&&<p className="muted">Cette analyse n’a aucun fait à parcourir : aucune relation à suivre.</p>}
    {state.view&&<Body view={state.view} selected={state.selected} dispatch={dispatch} commands={commands} busy={busy} query={query} source={source}
      addressFor={addressFor} shape={shape} onShape={setShape} choices={choices} followed={relations}
      onReload={()=>run('open', demand(settings.root!, settings.depth))}/>}
  </section></NamingContext.Provider>;
}

const NO_TYPES:string[]=[];

type WindowProps={full:Full; node?:string; appels:boolean; source:Source; view:View|null; selected:Selected; dispatch:(action:Action)=>void;
  commands:NodeCommands; busy:boolean; choices:RelationChoice[]; followed:string[]; hasRoot:boolean; errors:string[]};

/** Une partie de l'Explorer dans sa propre fenêtre : le code de la classe, ou le schéma, en grand, et rien d'autre. */
function Windowed({full, node, appels, source, view, selected, dispatch, commands, busy, choices, followed, hasRoot, errors}:Readonly<WindowProps>){
  const named=useNaming();
  const name=node?named(node):'';
  useEffect(()=>{document.title=`Taxo · ${full==='code'?'code':'schéma'}${name?` · ${name}`:''}`;},[full, name]);
  if(full==='code')return <section className="plein plein-code" aria-label="Code en grand">
    {node?<CodeTile reference={node} source={source} large/>:<p className="muted">Aucun nœud désigné : ouvrez cette fenêtre depuis la tuile de code.</p>}</section>;
  return <section className="plein plein-schema" aria-label="Schéma en grand">
    {errors.map(message=><p key={message} role="alert" className="error">{message}</p>)}
    {busy&&<output className="explorer-pending">Ouverture de la vue…</output>}
    {!hasRoot&&<p className="muted">Aucun point de départ : ouvrez cette fenêtre depuis le schéma.</p>}
    {view&&<SchemaWindow view={view} selected={selected} dispatch={dispatch} commands={commands} busy={busy} appels={appels} choices={choices}
      followed={followed}/>}
  </section>;
}

function SchemaWindow({view, selected, dispatch, commands, busy, appels, choices, followed}:Readonly<Pick<WindowProps, 'selected'|'dispatch'|'commands'|'busy'
  |'appels'|'choices'|'followed'> & {view:View}>){
  const named=useNaming();
  const links=useMemo(()=>linksOf(view), [view]);
  if(!view.known)return <output className="explorer-empty">« {named(view.anchor)} » n’apparaît dans aucun fait de cette analyse.</output>;
  const select=(value:Selected)=>dispatch({type:'select', selected:value});
  return appels?<CallsView view={view} links={links} selected={selected} onSelect={select} commands={commands} busy={busy} choices={choices}
    followed={followed} windowed/>:<ChainView view={view} links={links} selected={selected} onSelect={select} commands={commands} busy={busy} windowed/>;
}

type Shape='appels'|'chaine'|'couches'|'liste';
type BodyProps={view:View; selected:Selected; dispatch:(action:Action)=>void; commands:NodeCommands; busy:boolean; query:Query; source:Source;
  addressFor:(extra:Record<string, string>)=>string; shape:Shape; onShape:(shape:Shape)=>void; onReload:()=>void; choices:RelationChoice[]; followed:string[]};

/** La vue reçue : son état vide s'il y en a un, sinon les appels, la chaîne, les couches ou la liste, le détail choisi et les frontières. */
function Body({view, selected, dispatch, commands, busy, query, source, addressFor, shape, onShape, onReload, choices, followed}:Readonly<BodyProps>){
  const named=useNaming();
  const links=useMemo(()=>linksOf(view), [view]);
  // Le panneau latéral est replié en languette (avec le nombre de coupures et de lacunes) ; choisir un nœud ou un lien le
  // rouvre : preuves et détails restent accessibles.
  const [side,setSide]=useState(false);
  useEffect(()=>{if(selected)setSide(true);},[selected]);
  const gaps=view.nodes.filter(item=>view.selection[item.reference]).length+view.knowledge.length;
  if(!view.known)return <output className="explorer-empty">« {named(view.anchor)} » n’apparaît dans aucun fait de cette analyse : Taxo n’en sait rien ici, ni présence ni absence de liens.</output>;
  const link=selected?.kind==='link'?links.find(item=>item.identity===selected.identity):undefined;
  const node=selected?.kind==='node'?view.nodes.find(item=>item.reference===selected.reference):undefined;
  const select=(value:Selected)=>dispatch({type:'select', selected:value});
  return <>
    {view.stale&&<p role="alert" className="error">Les faits de cette analyse ont changé depuis l’ouverture de la vue : la réponse reçue n’y a pas été mêlée.{' '}
      <button type="button" className="link" onClick={onReload}>Recharger la vue</button></p>}
    {view.elements.length===0&&<output className="explorer-empty">Aucun lien pour les relations suivies depuis cette ancre, dans ce que l’analyse a enregistré. Ce que Taxo ne sait pas est dit plus bas.</output>}
    <div className="explorer-bar">
      <fieldset className="explorer-tabs"><legend className="explorer-hidden">Forme de la vue</legend>
        <button type="button" aria-pressed={shape==='appels'} onClick={()=>onShape('appels')}><CallsIcon/>Appels</button>
        <button type="button" aria-pressed={shape==='chaine'} onClick={()=>onShape('chaine')}><ChainIcon/>Chaîne</button>
        <button type="button" aria-pressed={shape==='couches'} onClick={()=>onShape('couches')}><StackIcon/>Couches</button>
        <button type="button" aria-pressed={shape==='liste'} onClick={()=>onShape('liste')}><ListIcon/>Liste</button></fieldset>
      <p className="explorer-stop">{viewText(view)}</p>
    </div>
    <div className={side?'explorer-body':'explorer-body closed'}>
      {shape==='appels'&&<CallsView view={view} links={links} selected={selected} onSelect={select}
        commands={commands} busy={busy} choices={choices} followed={followed} windowAddress={addressFor({plein:'schema', forme:'appels'})}/>}
      {shape==='chaine'&&<ChainView view={view} links={links} selected={selected} onSelect={select}
        commands={commands} busy={busy} windowAddress={addressFor({plein:'schema', forme:'chaine'})}/>}
      {shape==='couches'&&<LayerView view={view} links={links} selected={selected} onSelect={select}/>}
      {shape==='liste'&&<ListView view={view} links={links} commands={commands} busy={busy} onSelect={identity=>select({kind:'link', identity})}/>}
      {!side&&<button type="button" className="explorer-side-tab" aria-expanded="false" aria-controls="explorer-side"
        aria-label={`Ce que la vue ne montre pas : ${gaps} point${gaps>1?'s':''}`} onClick={()=>setSide(true)}>
        <ChevronLeftIcon/><span className="explorer-side-label">Ce que la vue ne montre pas</span><span className="count-pill">{gaps}</span></button>}
      <div className="explorer-side" id="explorer-side" hidden={!side}>
        <button type="button" className="ghost explorer-side-close" aria-expanded="true" aria-controls="explorer-side"
          onClick={()=>setSide(false)}>Masquer le panneau<ChevronRightIcon/></button>
        {link&&<LinkPanel key={link.identity} link={link} query={query} onClose={()=>select(null)}/>}
        {/* Le code d'abord, à la place la plus haute du panneau ; ce qui identifie le nœud et ses actions viennent dessous. */}
        {node&&<section className="explorer-panel node-panel" aria-label="Nœud choisi">
          <CodeTile key={node.reference} reference={node.reference} source={source} windowAddress={addressFor({plein:'code', noeud:node.reference})}/>
          <div className="node-identity">
            <span className={`type-pill tone-${toneOf(node.reference)}`}>{typeText(node.reference)}</span>
            <h3>{named(node.reference)}</h3><code>{node.reference}</code>
            <p className="muted">Niveau {node.level}{nodeMarks(node, view.selection[node.reference], view.knowledge).map(mark=>` · ${mark}`).join('')}</p>
            <div className="node-panel-actions">
              <OpenInEditor/>
              <NodeActions reference={node.reference} boundary={view.selection[node.reference]} commands={commands} busy={busy} anchor={node.reference===view.anchor}/>
              <CopyReference reference={node.reference}/></div></div></section>}
        {/* Avec un nœud choisi, ce que la vue ne montre pas se replie sous sa tuile : rien n'en est retiré. */}
        <details className="explorer-gaps" key={node?'node':'none'} open={!node}>
          <summary>Ce que la vue ne montre pas <span className="count-pill">{gaps}</span></summary>
          <Boundaries view={view} commands={commands} busy={busy}/></details>
      </div>
    </div>
  </>;
}

/** L'analyse explorée : la plus récente par défaut, changeable. */
function AnalysisChoice({base, request, revision, value, onChange}:Readonly<{base:string; request:Request; revision:string; value:string;
  onChange:(value:string)=>void}>){
  const {choices}=useChoices(base, request, revision);
  return <label className="explorer-analysis explorer-card">Analyse<span className="explorer-input"><CalendarIcon/>
    <select value={value} onChange={event=>onChange(event.target.value)}>
    {(choices??[]).map(choice=><option key={choice.id} value={choice.id}>{day(choice.created_at)} · {sideLabel(choice)}</option>)}
    {!(choices??[]).some(choice=>choice.id===value)&&<option value={value}>Analyse {value.slice(0, 8)}</option>}
  </select></span></label>;
}
