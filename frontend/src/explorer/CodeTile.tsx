// La tuile de code d'un nœud choisi (récit « Explorer — tuile de code ») : le code du type, de la méthode ou du constructeur,
// lu à la demande par Taxo au commit de l'analyse ; la méthode choisie est surlignée dans son type. Ce que Taxo ne transmet
// pas, ou refuse, est dit tel quel : jamais un code inventé, jamais une tuile vide.
import {useEffect, useState} from 'react';
import {kindOf, notSentText, ownerOf, refusalText, tileOf, MAX_SHOWN, type Tile} from './code';
import {Refusal, type Source} from './protocol';

type Loaded={reference:string; state:'done'; tile:Tile}|{reference:string; state:'empty'|'failed'; text:string};

/** Le code du nœud : un seul chargement par nœud choisi, le type et la méthode demandés ensemble, le type étant facultatif. */
function useCode(reference:string, source:Source){
  const [loaded,setLoaded]=useState<Loaded|null>(null);
  const kind=kindOf(reference);
  useEffect(()=>{
    if(kind==='none'||kind==='field')return;
    const controller=new AbortController();
    const {signal}=controller;
    const owner=kind==='method'?source(ownerOf(reference), signal).catch(()=>null):Promise.resolve(null);
    Promise.all([source(reference, signal), owner]).then(([own, outer])=>{
      const piece=own.items[0];
      if(piece)setLoaded({reference, state:'done', tile:tileOf(piece, outer?.items[0])});
      else setLoaded({reference, state:'empty', text:notSentText(own.not_sent?.[0]?.reason??'')});
    }, reason=>{
      if((reason as Error).name==='AbortError')return;
      const refused=reason instanceof Refusal;
      setLoaded({reference, state:'failed', text:refused?refusalText(reason.code, reason.message):(reason as Error).message});
    });
    return ()=>controller.abort();
  },[reference, source, kind]);
  return loaded?.reference===reference?loaded:null;
}

const NO_CODE:Record<string, string>={none:'Ce nœud n’a pas de code propre : seul un symbole (type, méthode ou constructeur) en a.',
  field:'Un champ n’a pas de code propre : son code est celui de son type.'};

export function CodeTile({reference, source}:Readonly<{reference:string; source:Source}>){
  const kind=kindOf(reference), loaded=useCode(reference, source);
  if(kind==='none'||kind==='field')return <p className="muted code-note">{NO_CODE[kind]}</p>;
  if(!loaded)return <output className="code-note muted">Lecture du code…</output>;
  if(loaded.state!=='done')return <p className={loaded.state==='failed'?'code-note error':'code-note muted'}
    role={loaded.state==='failed'?'alert':undefined}>{loaded.text}</p>;
  const {tile}=loaded;
  return <section className="code-tile" aria-label="Tuile de code">
    <p className="code-head"><code title={tile.path}>{tile.path}</code>
      <span className="count-pill">{tile.lines.length<tile.total?`lignes ${tile.first}–${tile.last} sur ${tile.total}`:`${tile.total} ligne${tile.total>1?'s':''}`}</span>
      {tile.selected&&<span className="count-pill selected">méthode sélectionnée</span>}</p>
    <pre className="code-lines" tabIndex={0} aria-label={`Code de ${reference}`}>{tile.lines.map(line=>
      <span key={line.number} className={line.selected?'code-line selected':'code-line'} data-selected={line.selected||undefined}>
        <span className="code-number" aria-hidden="true">{line.number}</span><span className="code-text">{line.text||' '}</span></span>)}</pre>
    {tile.truncated&&<p className="muted code-note">Taxo a coupé le code à la limite de lecture (200 lignes, 16 Ko) : la suite n’est pas transmise.</p>}
    {tile.lines.length<tile.total&&<p className="muted code-note">Affichage borné à {MAX_SHOWN} lignes autour de la sélection.</p>}
  </section>;
}
