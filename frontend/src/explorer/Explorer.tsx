// La page Explorer (TAXO-01J § 9) : choisir une ancre, voir ce qui la relie au reste sur plusieurs niveaux, développer,
// voir la suite, recentrer, consulter les preuves, et voir ce qui n'est pas montré. Elle ne parle qu'au protocole ;
// aucune règle ici : elle enchaîne les modules purs et transmet les choix.
import {useEffect, useMemo, useReducer, useRef, useState} from 'react';
import {day, sideLabel} from '../comparison';
import {href, go, type Route} from '../nav';
import {useChoices} from '../pages';
import {AnchorSearch} from './AnchorSearch';
import {Boundaries} from './Boundaries';
import {linksOf, type View} from './graph';
import {LayerView} from './LayerView';
import {LinkPanel} from './LinkPanel';
import {ListView} from './ListView';
import {NodeActions, type NodeCommands} from './NodeActions';
import {describe, openTile, queryOf, type Described, type Query, type TileDemand} from './protocol';
import {defaultRelations, relationChoices} from './relations';
import {naming, nodeMarks, scopeText, viewText} from './sentences';
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
  const {described, error:describeError}=useDescribed(query, analysis);
  const choices=useMemo(()=>described?relationChoices(described):[], [described]);
  const relations=settings.relations.length?settings.relations:defaultRelations(choices);
  const [state,dispatch]=useReducer(reduce, INITIAL);
  const [shape,setShape]=useState<Shape>('couches');
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
  const opening=JSON.stringify([analysis, settings.root, relations, settings.direction, settings.depth, settings.preset]);
  useEffect(()=>{
    if(settings.root&&described&&relations.length)run('open', demand(settings.root, settings.depth));
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
  return <NamingContext.Provider value={named}><section className="page explorer" aria-label="Explorer">
    <div className="page-intro"><h1>Explorer</h1><p>Choisissez un point de départ : Taxo montre ce qui le relie au reste, niveau par niveau, avec la preuve de chaque lien et ce qu’il ne montre pas.</p></div>
    <div className="explorer-toolbar">
      <AnalysisChoice base={base} request={request} revision={revision} value={analysis} onChange={value=>navigate({analysis:value, root:undefined})}/>
      <nav aria-label="Parcours des ancres" className="explorer-trail">
        <button type="button" className="ghost" disabled={!canGoBack(trail)} onClick={()=>globalThis.history.back()}>← Précédent</button>
        <button type="button" className="ghost" disabled={!canGoForward(trail)} onClick={()=>globalThis.history.forward()}>Suivant →</button>
      </nav>
    </div>
    {describeError&&<p role="alert" className="error">{describeError}</p>}
    <AnchorSearch query={query} types={described?.types??NO_TYPES} onPick={root=>navigate({root})}/>
    {described&&<details className="explorer-settings-box"><summary>Réglages du parcours</summary>
      <Settings key={opening} choices={choices} settings={settings} relations={relations} onApply={chosen=>navigate(chosen)}/></details>}
    {settings.root&&<p className="explorer-scope">{scopeText(relations, settings.direction, settings.depth)}</p>}
    {busy&&<output className="explorer-pending">{ACTIONS[state.pending!.action]} <button type="button" className="link" onClick={cancel}>Annuler</button></output>}
    {state.error&&<p role="alert" className="error">{state.error}</p>}
    {!settings.root&&<p className="muted">Aucun point de départ : recherchez une référence, ou ouvrez l’explorateur depuis une route, un module, un fichier ou un commit.</p>}
    {described&&settings.root&&!relations.length&&<p className="muted">Cette analyse n’a aucun fait à parcourir : aucune relation à suivre.</p>}
    {state.view&&<Body view={state.view} selected={state.selected} dispatch={dispatch} commands={commands} busy={busy} query={query}
      shape={shape} onShape={setShape}
      onReload={()=>run('open', demand(settings.root!, settings.depth))}/>}
  </section></NamingContext.Provider>;
}

const NO_TYPES:string[]=[];

type Shape='couches'|'liste';
type BodyProps={view:View; selected:Selected; dispatch:(action:Action)=>void; commands:NodeCommands; busy:boolean; query:Query;
  shape:Shape; onShape:(shape:Shape)=>void; onReload:()=>void};

/** La vue reçue : son état vide s'il y en a un, sinon les couches ou la liste, le détail choisi et les frontières. */
function Body({view, selected, dispatch, commands, busy, query, shape, onShape, onReload}:Readonly<BodyProps>){
  const named=useNaming();
  const links=useMemo(()=>linksOf(view), [view]);
  if(!view.known)return <output className="explorer-empty">« {named(view.anchor)} » n’apparaît dans aucun fait de cette analyse : Taxo n’en sait rien ici, ni présence ni absence de liens.</output>;
  const link=selected?.kind==='link'?links.find(item=>item.identity===selected.identity):undefined;
  const node=selected?.kind==='node'?view.nodes.find(item=>item.reference===selected.reference):undefined;
  const select=(value:Selected)=>dispatch({type:'select', selected:value});
  return <>
    {view.stale&&<p role="alert" className="error">Les faits de cette analyse ont changé depuis l’ouverture de la vue : la réponse reçue n’y a pas été mêlée.{' '}
      <button type="button" className="link" onClick={onReload}>Recharger la vue</button></p>}
    <p className="explorer-stop">{viewText(view)}</p>
    {view.elements.length===0&&<output className="explorer-empty">Aucun lien pour les relations suivies depuis cette ancre, dans ce que l’analyse a enregistré. Ce que Taxo ne sait pas est dit plus bas.</output>}
    <fieldset className="explorer-tabs"><legend className="explorer-hidden">Forme de la vue</legend>
      <button type="button" aria-pressed={shape==='couches'} onClick={()=>onShape('couches')}>Couches</button>
      <button type="button" aria-pressed={shape==='liste'} onClick={()=>onShape('liste')}>Liste</button></fieldset>
    <div className="explorer-body">
      {shape==='couches'?<LayerView view={view} links={links} selected={selected} onSelect={select}/>
        :<ListView view={view} links={links} commands={commands} busy={busy} onSelect={identity=>select({kind:'link', identity})}/>}
      <div className="explorer-side">
        {link&&<LinkPanel key={link.identity} link={link} query={query} onClose={()=>select(null)}/>}
        {node&&<section className="explorer-panel" aria-label="Nœud choisi"><h3>{named(node.reference)}</h3><code>{node.reference}</code>
          <p className="muted">Niveau {node.level}{nodeMarks(node, view.selection[node.reference], view.knowledge).map(mark=>` · ${mark}`).join('')}</p>
          <NodeActions reference={node.reference} boundary={view.selection[node.reference]} commands={commands} busy={busy} anchor={node.reference===view.anchor}/></section>}
        <Boundaries view={view} commands={commands} busy={busy}/>
      </div>
    </div>
  </>;
}

/** L'analyse explorée : la plus récente par défaut, changeable. */
function AnalysisChoice({base, request, revision, value, onChange}:Readonly<{base:string; request:Request; revision:string; value:string;
  onChange:(value:string)=>void}>){
  const {choices}=useChoices(base, request, revision);
  return <label className="explorer-analysis">Analyse<select value={value} onChange={event=>onChange(event.target.value)}>
    {(choices??[]).map(choice=><option key={choice.id} value={choice.id}>{day(choice.created_at)} · {sideLabel(choice)}</option>)}
    {!(choices??[]).some(choice=>choice.id===value)&&<option value={value}>Analyse {value.slice(0, 8)}</option>}
  </select></label>;
}
