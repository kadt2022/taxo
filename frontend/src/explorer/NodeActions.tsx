// Les actions sur un nœud de la vue : développer, voir la suite d'une adjacence coupée, recentrer. Aucune règle ici :
// la coupure du nœud dit ce qui est possible.
import type {Boundary} from './protocol';
import {useNaming} from './Naming';

export type NodeCommands={expand:(reference:string)=>void; more:(reference:string)=>void; recenter:(reference:string)=>void};

export function NodeActions({reference, boundary, commands, busy, anchor=false}:Readonly<{reference:string; boundary?:Boundary;
  commands:NodeCommands; busy:boolean; anchor?:boolean}>){
  const name=useNaming()(reference);
  return <span className="explorer-actions">
    {boundary&&!boundary.continuation&&<button type="button" className="ghost" disabled={busy} aria-label={`Développer ${name}`}
      onClick={()=>commands.expand(reference)}>Développer</button>}
    {boundary?.continuation&&<button type="button" className="ghost" disabled={busy} aria-label={`Voir la suite de ${name}`}
      onClick={()=>commands.more(reference)}>Voir la suite</button>}
    {!anchor&&<button type="button" className="ghost" disabled={busy} aria-label={`Recentrer sur ${name}`}
      onClick={()=>commands.recenter(reference)}>Recentrer</button>}
  </span>;
}
