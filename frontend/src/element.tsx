// L'element que la question nomme (TAXO-01N / MIP-01, § 5.1) : Taxo le retrouve sans modele. Une ancre unique ouvre
// l'explorateur centre sur elle ; plusieurs candidates restent un choix de l'utilisateur, jamais de Taxo. Aucun
// type ni aucune relation n'est nomme ici : les references viennent telles quelles du serveur.
import {explorerHref} from './explorer/entry';
import {reference} from './vocabulary';

export type ElementStatus = 'FOUND'|'AMBIGUOUS'|'NONE';
/** Reponse de `/elements`, et l'ancre jointe a une reponse de Minia en repli paquet. */
export type Located = {status:ElementStatus; anchor:string|null; candidates:string[]; more_candidates?:number;
  analysis?:string};

const HINT='Pour une question sur le code, nommez l’élément (`VetController`, `OwnerRepository.findById`) ou donnez sa référence complète.';

function Explore({target, analysis, label='Ouvrir dans l’explorateur'}:Readonly<{target:string; analysis?:string; label?:string}>){
  return <a className="explore-link" href={explorerHref(target, analysis)} aria-label={`${label} : ${target}`}>{label}</a>;
}

/** Ce que Taxo a reconnu dans la question : l'element, les candidates, ou ce qu'il faut preciser. */
export function ElementView({located}:Readonly<{located:Located}>){
  if(located.status==='FOUND'&&located.anchor)return <section className="element found" aria-label="Élément reconnu">
    <p className="eyebrow">ÉLÉMENT RECONNU</p>
    <p className="element-name"><code>{reference(located.anchor)}</code><Explore target={located.anchor} analysis={located.analysis}/></p>
    <p className="muted">Taxo a trouvé un seul élément sous ce nom. L’explorateur montre ses faits, leurs preuves et ce que Taxo n’a pas pu établir ; Minia peut aussi en expliquer le voisinage.</p>
  </section>;
  if(located.status==='AMBIGUOUS'&&located.candidates.length)return <section className="element ambiguous" aria-label="Plusieurs éléments">
    <p className="eyebrow">PLUSIEURS ÉLÉMENTS</p>
    <p className="muted">Ce nom désigne plusieurs éléments. Taxo ne choisit pas à votre place : ouvrez celui qui vous intéresse, ou précisez la question.</p>
    <ul className="element-candidates">{located.candidates.map(item=><li key={item}><code>{reference(item)}</code><Explore target={item} analysis={located.analysis} label="Explorer"/></li>)}</ul>
    {(located.more_candidates??0)>0&&<p className="muted">Et {located.more_candidates} autre{located.more_candidates===1?'':'s'} : précisez le nom.</p>}
  </section>;
  if(located.status==='AMBIGUOUS')return <section className="element ambiguous" aria-label="Élément non déterminé">
    <p className="eyebrow">ÉLÉMENT NON DÉTERMINÉ</p>
    <p className="muted">Taxo n’a pas pu conclure à un seul élément (recherche incomplète) : donnez la référence complète.</p>
  </section>;
  return <section className="element none" aria-label="Aucun élément nommé">
    <p className="muted">{HINT}</p>
  </section>;
}
