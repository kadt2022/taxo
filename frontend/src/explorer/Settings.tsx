// Régler le parcours (TAXO-01J § 9) : les relations annoncées par l'analyse, par domaine ; le sens ; la profondeur ;
// un budget nommé, résolu en budgets explicites et affichés. Un réglage appliqué devient l'adresse de la vue.
import {useId, useState, type FormEvent} from 'react';
import {DOMAINS} from '../domains';
import {label, RELATIONS} from '../vocabulary';
import type {RelationChoice} from './relations';
import {DIRECTIONS} from './sentences';
import {MAX_DEPTH, MAX_RELATIONS, PRESETS, PRESET_NAMES, type Preset, type Settings as Chosen} from './state';

const SIDES=['BOTH', 'OUTGOING', 'INCOMING'] as const;
const BUDGET_NAMES={max_nodes:'nœuds', max_edges:'liens', max_work:'lectures', max_fanout:'liens par nœud'};

export function budgetText(preset:Preset){
  return Object.entries(PRESETS[preset]).map(([name, value])=>`${value} ${BUDGET_NAMES[name as keyof typeof BUDGET_NAMES]}`).join(' · ');
}

export function Settings({choices, settings, relations, onApply}:Readonly<{choices:RelationChoice[]; settings:Chosen;
  relations:string[]; onApply:(settings:Chosen)=>void}>){
  const id=useId();
  const [draft,setDraft]=useState<Chosen>({...settings, relations});
  const full=draft.relations.length>=MAX_RELATIONS;
  const toggle=(relation:string, on:boolean)=>setDraft({...draft,
    relations:on?[...draft.relations, relation]:draft.relations.filter(item=>item!==relation)});
  function submit(event:FormEvent){
    event.preventDefault();
    onApply(draft);
  }
  return <form className="explorer-settings" onSubmit={submit} aria-label="Réglages du parcours">
    <fieldset><legend>Relations suivies <span className="muted">({draft.relations.length} sur {MAX_RELATIONS} au plus)</span></legend>
      {DOMAINS.map(domain=>{
        const offered=choices.filter(choice=>choice.domain===domain.id);
        if(!offered.length)return null;
        return <div key={domain.id} className="explorer-domain"><h4>{domain.label}</h4>{offered.map(choice=>{
          const checked=draft.relations.includes(choice.relation);
          return <label key={choice.relation} className={choice.available?undefined:'muted'} title={choice.reason}>
            <input type="checkbox" checked={checked} disabled={!choice.available||(full&&!checked)}
              onChange={event=>toggle(choice.relation, event.target.checked)}/>
            {label(RELATIONS, choice.relation)} <code>{choice.relation}</code> <span className="count-pill">{choice.count}</span>
            {choice.reason&&<span className="explorer-reason">{choice.reason}</span>}
          </label>;
        })}</div>;
      })}
    </fieldset>
    <div className="explorer-settings-row">
      <fieldset><legend>Sens</legend>{SIDES.map(side=><label key={side}><input type="radio" name={`${id}-side`} checked={draft.direction===side}
        onChange={()=>setDraft({...draft, direction:side})}/>{DIRECTIONS[side]}</label>)}</fieldset>
      <label htmlFor={`${id}-depth`}>Profondeur<select id={`${id}-depth`} value={draft.depth}
        onChange={event=>setDraft({...draft, depth:Number(event.target.value)})}>
        {Array.from({length:MAX_DEPTH}, (_, index)=>index+1).map(depth=><option key={depth} value={depth}>{depth}</option>)}</select></label>
      <label htmlFor={`${id}-budget`}>Budget<select id={`${id}-budget`} value={draft.preset}
        onChange={event=>setDraft({...draft, preset:event.target.value as Preset})}>
        {(Object.keys(PRESETS) as Preset[]).map(preset=><option key={preset} value={preset}>{PRESET_NAMES[preset]}</option>)}</select>
        <span className="muted">{budgetText(draft.preset)}</span></label>
    </div>
    <button type="submit" className="primary" disabled={!draft.relations.length}>Appliquer</button>
  </form>;
}
