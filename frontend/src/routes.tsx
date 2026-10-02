// Routes (TAXO-UI-02) : ce que Taxo prouve de chaque route, lu dans ses seuls faits. Aucune phrase de Minia :
// un etat n'est affiche que si un fait le porte, et une route non interpretee dit exactement pourquoi.
import {useState} from 'react';
import {typed} from './consult';
import {EVALUATORS, label} from './vocabulary';
import type {Derivation} from './query';

export type Proof = {path?:string; line_start?:number; line_end?:number; method?:string};
export type RouteFact = {subject:string; relation:string; object?:string; status?:string;
  qualifiers?:Record<string,unknown>; evidence?:Proof[]; derivation?:Derivation;
  produced_by?:{producer_id:string}};
export type Gap = {subject:string; type:string; reason:string; evaluator:string};
export type RouteState = 'PROTECTED'|'PERMITS_ALL'|'NOT_INTERPRETED'|'NO_CONCLUSION';
export type RouteRow = {endpoint:string; verb:string; path:string; state:RouteState; handlers:RouteFact[];
  applications:RouteFact[]; matched:RouteFact[]; rules:RouteFact[]; protections:RouteFact[]; gaps:Gap[]};
export type RoutesResult = {routes:RouteRow[]; unestablished:Gap[]};
type Run = <T>(path:string, init?:RequestInit)=>Promise<T>;

/** Ce que dit chaque etat : il vient d'un fait, jamais d'une supposition. */
export const STATES:Record<RouteState,string>={PROTECTED:'Protégée', PERMITS_ALL:'Règle permitAll()',
  NOT_INTERPRETED:'Non interprétée', NO_CONCLUSION:'Sans conclusion'};
export const FILTERS:Record<string,string>={ALL:'Toutes les routes', PROTECTED:'Protégées (PROTECTED_BY)',
  PERMITS_ALL:'Capturées par permitAll()', GAPS:'Avec une zone non interprétée', NO_CONCLUSION:'Sans conclusion'};

/** `symbol:java:com.acme.web.OrderController#get()` devient `OrderController#get()`. */
export function shortSymbol(value?:string){
  if(!value)return '';
  const key=value.replace(/^symbol:java:/, '');
  const [type, member]=key.split('#');
  const name=type.split('.').pop()??type;
  return member?`${name}#${member}`:name;
}

/** `application:mod/src/main/java/.../ShopApplication.java#ShopApplication` devient `ShopApplication`. */
export function applicationName(value?:string){
  if(!value)return '';
  return value.includes('#')?value.slice(value.lastIndexOf('#')+1):value.replace(/^application:/, '');
}

/** La regle telle qu'ecrite : son motif, puis permitAll() ou ce qui autorise. */
export function ruleText(rule:RouteFact){
  const pattern=rule.subject.replace(/^route-pattern:/, '');
  if(rule.relation==='PERMITS_ALL')return `${pattern} → permitAll()`;
  const object=rule.object??'';
  return `${pattern} → ${object.startsWith('symbol:')?shortSymbol(object):object}`;
}

export function protectionText(fact:RouteFact){
  const object=fact.object??'';
  if(object.startsWith('policy-rule:'))return object.slice('policy-rule:'.length);
  return object.startsWith('symbol:')?shortSymbol(object):object;
}

/** La chaine de filtres qui porte un fait, par sa methode ; vide si le fait n'en nomme pas. */
export function chainName(fact:RouteFact){
  const chain=fact.qualifiers?.filter_chain;
  return typeof chain==='string'?shortSymbol(chain):'';
}

export function proofText(proof:Proof){
  if(!proof.path)return '';
  if(proof.line_start===undefined)return proof.path;
  return proof.line_end&&proof.line_end!==proof.line_start?`${proof.path}:${proof.line_start}-${proof.line_end}`:`${proof.path}:${proof.line_start}`;
}

/** Filtre par chemin ou verbe (texte libre), puis par etat etabli. */
export function filterRoutes(routes:RouteRow[], text:string, filter:string){
  const words=text.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return routes.filter(row=>{
    const target=`${row.verb} ${row.path}`.toLowerCase();
    if(!words.every(word=>target.includes(word)))return false;
    if(filter==='GAPS')return row.gaps.length>0;
    return filter==='ALL'||row.state===filter;
  });
}

function Facts({title, facts, render}:Readonly<{title:string; facts:RouteFact[]; render:(fact:RouteFact)=>string}>){
  if(!facts.length)return null;
  return <div className="route-facts"><h4>{title}</h4>
    {facts.map(fact=><div key={`${fact.relation}${fact.subject}${fact.object}`} className="route-fact">
      <p><strong>{render(fact)}</strong> <span className="muted">{fact.relation} · {fact.status==='INFERRED'?'déduit':'observé'}</span></p>
      {fact.evidence?.length?<ul className="proofs">{fact.evidence.map(proof=><li key={proofText(proof)+proof.method}><code>{proofText(proof)}</code></li>)}</ul>:null}
      {fact.derivation&&<details><summary>Prémisses</summary><ul>{fact.derivation.premises.map(item=><li key={item}>{item}</li>)}</ul>
        {fact.derivation.counter_examples_checked.length>0&&<><p className="muted">Écarté</p><ul>{fact.derivation.counter_examples_checked.map(item=><li key={item}>{item}</li>)}</ul></>}
        {fact.derivation.known_gaps.length>0&&<><p className="muted">Limites connues</p><ul>{fact.derivation.known_gaps.map(item=><li key={item}>{item}</li>)}</ul></>}
      </details>}
    </div>)}
  </div>;
}

export function RouteDetail({row}:Readonly<{row:RouteRow}>){
  return <section className="route-detail" aria-label={`Route ${row.verb} ${row.path}`}>
    <h3><code>{row.verb} {row.path}</code> <span className={`state state-${row.state.toLowerCase()}`}>{STATES[row.state]}</span></h3>
    <Facts title="Traitée par" facts={row.handlers} render={fact=>shortSymbol(fact.object)}/>
    <Facts title="Servie par" facts={row.applications} render={fact=>applicationName(fact.object)}/>
    <Facts title="Règle qui la capture" facts={row.matched} render={fact=>`${(fact.object??'').replace(/^route-pattern:/, '')} · chaîne ${chainName(fact)}`}/>
    <Facts title="Règle écrite" facts={row.rules} render={ruleText}/>
    <Facts title="Protection" facts={row.protections} render={protectionText}/>
    {row.gaps.length>0&&<div className="route-facts"><h4>Ce que Taxo ne sait pas</h4><ul>
      {row.gaps.map(gap=><li key={gap.evaluator+gap.reason}><strong>{label(EVALUATORS, gap.evaluator)}</strong> : {gap.reason||'raison non conservée par cette analyse'}</li>)}
    </ul></div>}
  </section>;
}

export function RoutesTable({routes, selected, onSelect}:Readonly<{routes:RouteRow[]; selected:string; onSelect:(endpoint:string)=>void}>){
  return <div className="table-wrap"><table><thead><tr><th>Route</th><th>Traitée par</th><th>Application</th><th>Règle</th><th>Protection</th><th>État</th></tr></thead>
    <tbody>{routes.map(row=><tr key={row.endpoint} aria-selected={selected===row.endpoint}>
      <td><button type="button" className="link" onClick={()=>onSelect(row.endpoint)}><code>{row.verb} {row.path}</code></button></td>
      <td>{row.handlers.map(fact=>shortSymbol(fact.object)).join(', ')}</td>
      <td>{row.applications.map(fact=>applicationName(fact.object)).join(', ')||<span className="muted">—</span>}</td>
      <td>{row.rules.map(ruleText).join(', ')||<span className="muted">—</span>}</td>
      <td>{row.protections.map(protectionText).join(', ')||<span className="muted">—</span>}</td>
      <td><span className={`state state-${row.state.toLowerCase()}`}>{STATES[row.state]}</span>{row.gaps.length>0&&row.state!=='NOT_INTERPRETED'&&<div className="muted">avec réserve</div>}</td>
    </tr>)}</tbody></table></div>;
}

type Loaded = {onResult:(value:RoutesResult)=>void; onError:(message:string)=>void};

/** Charge les routes d'une analyse ; rend de quoi ignorer une reponse arrivee apres un changement d'analyse. */
export function loadRoutes(request:Run, base:string, scanId:string, {onResult, onError}:Loaded){
  let active=true;
  request<RoutesResult>(`${base}/scans/${scanId}/routes`).then(value=>{if(active)onResult(value);})
    .catch(e=>{if(active)onError((e as Error).message);});
  return ()=>{active=false;};
}

type ViewProps = {result:RoutesResult|null; error:string; text:string; filter:string; selected:string;
  onText:(value:string)=>void; onFilter:(value:string)=>void; onSelect:(endpoint:string)=>void; title?:string; intro?:string;
  unread?:string[]};

const INTRO='Ce que Taxo prouve de chaque route HTTP : qui la traite, quelle application la sert, quelle règle la capture et ce qui la protège. Tout vient des faits, avec leurs preuves ; rien n’est rédigé par Minia.';

/** Les langages presents que l'analyseur de la page n'a pas lus (TAXO-COV-01) : rien n'y est trouve ni exclu. */
function Unread({unread, empty}:Readonly<{unread:string[]; empty:boolean}>){
  const list=unread.join(', ');
  return <p className={empty?'empty':'routes-unread'}>{empty?`Aucune route établie dans ce que Taxo a lu. Non analysé : ${list}`
    :`Non analysé : ${list}`} — une route écrite dans {unread.length>1?'ces langages':'ce langage'} n’est ni trouvée ni exclue.</p>;
}

export function RoutesView({result, error, text, filter, selected, onText, onFilter, onSelect, title='Routes', intro=INTRO,
  unread=[]}:Readonly<ViewProps>){
  const shown=result?filterRoutes(result.routes, text, filter):[];
  const row=result?.routes.find(item=>item.endpoint===selected);
  return <section className="results routes" aria-label={title}>
    <div className="section-heading"><div><h2>{title}</h2><p>{intro}</p></div></div>
    {error&&<div role="alert" className="error">{error}</div>}
    {!result&&!error&&<output>Chargement des routes…</output>}
    {result&&<>
      <div className="filters">
        <label>Chemin ou verbe<input value={text} onChange={typed(onText)} placeholder="GET /api/admin"/></label>
        <label>État<select value={filter} onChange={typed(onFilter)}>{Object.entries(FILTERS).map(([key, value])=><option key={key} value={key}>{value}</option>)}</select></label>
        <p className="muted">{shown.length} sur {result.routes.length} routes</p>
      </div>
      {unread.length>0&&<Unread unread={unread} empty={result.routes.length===0}/>}
      {result.routes.length===0?unread.length===0&&<p className="empty">Aucune route HTTP établie par cette analyse.</p>
        :<RoutesTable routes={shown} selected={selected} onSelect={onSelect}/>}
      {row&&<RouteDetail row={row}/>}
      {result.unestablished.length>0&&<details className="analysis-details"><summary>Des routes peuvent manquer ({result.unestablished.length})</summary><ul>
        {result.unestablished.map(gap=><li key={gap.subject}><code>{gap.subject}</code> : {gap.reason||'raison non conservée par cette analyse'}</li>)}
      </ul></details>}
    </>}
  </section>;
}

/** Une page de routes (Routes, Sécurité, Non interprétées) : les routes de l'analyse affichée, lues une seule fois par le portail,
 * avec le filtre propre à la page. */
export function RoutesExplorer({result, error, initialFilter='ALL', title, intro, unread}:Readonly<{result:RoutesResult|null; error:string;
  initialFilter?:string; title?:string; intro?:string; unread?:string[]}>){
  const [text,setText]=useState(''), [filter,setFilter]=useState(initialFilter), [selected,setSelected]=useState('');
  return <RoutesView result={result} error={error} text={text} filter={filter} selected={selected} onText={setText} onFilter={setFilter}
    onSelect={setSelected} title={title} intro={intro} unread={unread}/>;
}
