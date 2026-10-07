// La vue Appels : ce qui se passe dans le code depuis l'ancre, projeté de la vue reçue. Pur : ni React, ni réseau.
// On ne garde que les relations de l'axe d'exécution, reçues du vocabulaire (rien ici n'en nomme une), lues du sujet vers
// l'objet à partir de l'ancre. Chaque nœud se pose sous le premier lien de l'axe qui l'atteint ; tout autre lien de l'axe
// qui l'atteint devient une revisite. Les relations de contexte n'entrent pas : elles restent dans la vue Chaîne. Aucun
// nœud, aucun lien, aucun type n'est ajouté : la projection n'est qu'un sous-ensemble de la vue.
import type {Link, View} from './graph';

export type Calls={view:View; links:Link[];
  /** Les nœuds atteints où l'axe s'arrête sans coupure ni frontière de nœud : Taxo n'y établit aucun lien de l'axe. */
  ends:string[]};

export function calls(view:View, links:Link[], onAxis:(relation:string)=>boolean):Calls{
  const nodes=new Set(view.nodes.map(node=>node.reference));
  const axis=links.filter(link=>onAxis(link.relation)&&link.object!==undefined&&nodes.has(link.subject)&&nodes.has(link.object));
  const out=new Map<string, Link[]>();
  for(const link of axis)out.set(link.subject, [...out.get(link.subject)??[], link]);

  // En largeur depuis l'ancre, dans l'ordre des liens : le premier lien qui atteint un nœud le découvre.
  const reached=new Set([view.anchor]), kept:Link[]=[], queue=[view.anchor];
  while(queue.length){
    const subject=queue.shift()!;
    for(const link of out.get(subject)??[]){
      const found=!reached.has(link.object!);
      kept.push({...link, revisit:!found});
      if(found){reached.add(link.object!);queue.push(link.object!);}
    }
  }
  const order=new Map(axis.map((link, index)=>[link.identity, index]));
  kept.sort((a, b)=>order.get(a.identity)!-order.get(b.identity)!);

  const identities=new Set(kept.map(link=>link.identity));
  const selection=Object.fromEntries(Object.entries(view.selection).filter(([node])=>reached.has(node)));
  const knowledge=view.knowledge.filter(entry=>entry.scope==='NODE'?reached.has(entry.node??'')
    :entry.relation===undefined||onAxis(entry.relation));
  const projected:View={...view, nodes:view.nodes.filter(node=>reached.has(node.reference)),
    elements:view.elements.filter(element=>identities.has(element.identity)), selection, knowledge};
  const ends=[...reached].filter(node=>!out.has(node)&&!selection[node]
    &&!knowledge.some(entry=>entry.scope==='NODE'&&entry.node===node));
  return {view:projected, links:kept, ends};
}
