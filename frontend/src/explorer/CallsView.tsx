// La vue Appels : « que se passe-t-il dans le code depuis cette route ? ». Un seul axe, de haut en bas, projeté de la vue
// reçue par `calls.ts` : les relations d'exécution du vocabulaire, rien d'autre. Elle se dessine comme la vue Chaîne (un
// trait droit quand un nœud n'a qu'une suite, une bifurcation en retrait quand il en a plusieurs) et dit, sous le
// dessin, où l'axe s'arrête et pourquoi : relation non analysée, non suivie, ou aucun lien établi par Taxo.
import {useMemo} from 'react';
import {CALL_AXIS} from '../vocabulary';
import {calls} from './calls';
import {ChainView} from './ChainView';
import type {Link, View} from './graph';
import type {NodeCommands} from './NodeActions';
import {NO_PRODUCER, type RelationChoice} from './relations';
import type {Selected} from './state';
import {verb} from './sentences';
import {useNaming} from './Naming';

const onAxis=(relation:string)=>CALL_AXIS.includes(relation);

export function CallsView({view, links, selected, onSelect, commands, busy, choices, followed}:Readonly<{view:View; links:Link[];
  selected:Selected; onSelect:(selected:Selected)=>void; commands:NodeCommands; busy:boolean; choices:RelationChoice[];
  followed:string[]}>){
  const named=useNaming();
  const projected=useMemo(()=>calls(view, links, onAxis), [view, links]);
  const gaps=CALL_AXIS.flatMap(relation=>{
    const choice=choices.find(item=>item.relation===relation);
    if(!choice?.available)return [{relation, said:`non analysé. ${NO_PRODUCER}`}];
    if(!followed.includes(relation))return [{relation, said:'non suivi dans cette vue : à cocher dans les réglages pour le voir.'}];
    return [];
  });
  return <div className="calls">
    <p className="calls-question">Ce qui s’exécute dans le code depuis <strong>{named(view.anchor)}</strong>, selon les faits
      établis par Taxo. Le contexte (module, fichier, implémentation, sécurité, Git) reste dans la vue Chaîne.</p>
    {projected.links.length===0&&<output className="explorer-empty">Aucun lien d’exécution établi par Taxo depuis cette ancre
      dans la vue reçue.</output>}
    <ChainView view={projected.view} links={projected.links} selected={selected} onSelect={onSelect} commands={commands} busy={busy}
      viewName="Appels"/>
    <section className="calls-limits" aria-label="Où s’arrête la vue Appels">
      <h3>Où s’arrête la vue Appels</h3>
      <ul>
        {gaps.map(gap=><li key={gap.relation}><strong>« {verb(gap.relation)} »</strong> : {gap.said}</li>)}
        {projected.ends.map(node=><li key={node}><strong>{named(node)}</strong> : {gaps.length
          ?'la suite n’est pas établie, faute des relations ci-dessus.'
          :'aucun lien d’exécution établi par Taxo depuis ce nœud. Une absence de preuve n’est pas une preuve d’absence.'}</li>)}
        {!gaps.length&&!projected.ends.length&&<li>Chaque nœud dessiné porte sa suite, sa coupure ou sa frontière.</li>}
      </ul>
    </section>
  </div>;
}
