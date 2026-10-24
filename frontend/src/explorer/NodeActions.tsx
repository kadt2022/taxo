// Les actions sur un nœud de la vue : développer, voir la suite d'une adjacence coupée, recentrer. Aucune règle ici :
// la coupure du nœud dit ce qui est possible.
import {useState} from 'react';
import type {Boundary} from './protocol';
import {useNaming} from './Naming';

/** Ouvrir le fichier du nœud dans l'éditeur de l'utilisateur (un IDE, VS Code) : la place est prête, le branchement viendra
 * plus tard ; le bouton le dit au lieu de ne rien faire en silence. */
export function OpenInEditor(){
  return <button type="button" className="ghost" disabled aria-label="Ouvrir dans l’éditeur (pas encore branché)"
    title="Bientôt : ouvrir ce fichier dans votre éditeur">Ouvrir</button>;
}

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

/** Copier la référence complète d'un nœud ; dit si la copie a eu lieu, sans jamais la supposer. */
export function CopyReference({reference}:Readonly<{reference:string}>){
  const [said,setSaid]=useState('');
  async function copy(){
    try{
      await navigator.clipboard.writeText(reference);
      setSaid('Référence copiée.');
    }catch{setSaid('Copie impossible : sélectionnez la référence.');}
  }
  return <>
    <button type="button" className="ghost" aria-label={`Copier la référence ${reference}`} onClick={copy}>Copier la référence</button>
    <output className="explorer-said">{said}</output>
  </>;
}
