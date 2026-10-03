// Les relations que l'explorateur propose (TAXO-01J § 9) : celles que l'analyse annonce, rangées par domaine du
// portail. Pur. Une relation qu'aucun analyseur exécuté ne produit reste montrée, désactivée, avec la raison.
import {DOMAINS, domainOf, type DomainId} from '../domains';
import type {Described} from './protocol';
import {MAX_RELATIONS} from './state';

export type RelationChoice={relation:string; count:number; domain:DomainId; available:boolean; reason?:string};
export const NO_PRODUCER='Aucun analyseur exécuté dans cette analyse ne la produit : Taxo n’en dit rien.';

export function relationChoices(described:Described):RelationChoice[]{
  const counts=new Map(described.relations.map(item=>[item.relation, item.count]));
  const producers=new Map<string, string[]>();
  for(const analyzer of described.analyzers){
    for(const relation of analyzer.relations){
      producers.set(relation, [...producers.get(relation)??[], ...(analyzer.status==='UNSUPPORTED'?[]:[analyzer.analyzer])]);
    }
  }
  const all=new Set([...counts.keys(), ...producers.keys()]);
  const order=(domain:DomainId)=>DOMAINS.findIndex(item=>item.id===domain);
  return [...all].map(relation=>{
    const capable=producers.get(relation)??[], count=counts.get(relation)??0;
    // Une relation presente a forcement un producteur ; sinon, il faut un analyseur qui avait de quoi lire.
    const available=count>0||capable.length>0;
    return {relation, count, domain:domainOf(capable[0]??'', relation), available, ...(available?{}:{reason:NO_PRODUCER})};
  }).sort((a, b)=>order(a.domain)-order(b.domain)||a.relation.localeCompare(b.relation));
}

/** Les relations suivies sans choix explicite : celles qui ont des faits dans cette analyse, au plus 16. */
export const defaultRelations=(choices:RelationChoice[])=>
  choices.filter(choice=>choice.count>0).slice(0, MAX_RELATIONS).map(choice=>choice.relation);

/** Ce que la saisie désigne : un type explicite (`route:` ou le filtre choisi) et le début de la clé. */
export function searchOf(text:string, type:string, types:string[]){
  const at=text.indexOf(':');
  if(!type&&at>0&&types.includes(text.slice(0, at)))return {type:text.slice(0, at), prefix:text.slice(at+1)};
  return {type:type||undefined, prefix:text};
}
