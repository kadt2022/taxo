// Consultation de l'historique Git (TAXO-EVAL-01) : toujours explicite, jamais une fenetre par defaut.
export const MAX_COMMITS=100;

/** Nombre de commits demande par l'utilisateur ; null si la saisie n'est pas un entier entre 1 et MAX_COMMITS. */
export function commitCount(value:string):number|null{
  const text=value.trim();
  if(!/^\d+$/.test(text))return null;
  const count=Number(text);
  return count>=1&&count<=MAX_COMMITS?count:null;
}

/** Adresse de la consultation demandee, ou le message a afficher si le nombre saisi n'est pas valable. */
export function consultRequest(base:string, value:string):{path:string}|{error:string}{
  const count=commitCount(value);
  return count===null?{error:`Indiquez un nombre de commits entre 1 et ${MAX_COMMITS}.`}:{path:`${base}?limit=${count}`};
}

// D'ou vient l'impact d'un commit (TAXO-01F, tranche E) : des analyses enregistrees, ou d'une relecture du depot.
export type ImpactSide={kind:'ANALYSIS'|'REREAD'; id:string|null; commit:string; created_at:string|null};
export type ImpactOrigin={source:'MEMORY'|'REREAD'; analyses:{before:ImpactSide|null; after:ImpactSide}};

const short=(sha:string)=>sha.slice(0,7);

/** La phrase qui dit d'ou vient l'impact affiche : les deux analyses nommees, ou la relecture du depot. */
export function impactSource(origin:ImpactOrigin):string{
  const {before, after}=origin.analyses;
  if(origin.source==='MEMORY'&&before)
    return `Depuis les analyses enregistrées ${before.id} (parent ${short(before.commit)}) et ${after.id} (commit ${short(after.commit)}) : le dépôt n’a pas été relu.`;
  return before
    ? `Le dépôt a été relu : le parent ${short(before.commit)} et le commit ${short(after.commit)} n’ont pas chacun une analyse enregistrée.`
    : `Le dépôt a été relu : ce commit n’a pas de parent.`;
}

/** Pourquoi un evaluateur n'est pas compare : la raison dite par Taxo, jamais un echec suppose. */
export function notComparable(failures:string[]):string{
  return `Comparaison impossible : ${failures.join(' ; ')} Taxo n’affiche aucun changement plutôt que d’en inventer.`;
}
