// Lien entre le diff et les faits (TAXO-HIST-03) : logique pure, sans rendu.
export type LinkLines = {before:number[]; after:number[]};
export type Side = keyof LinkLines;

/** Où la preuve d'un fait touche le diff : ses lignes modifiées, ou le fichier seul. */
export function lineLabel(lines:LinkLines){
  const parts=[
    lines.before.length?`avant ${lines.before.join(', ')}`:'',
    lines.after.length?`après ${lines.after.join(', ')}`:'',
  ].filter(part=>part!=='');
  return parts.length?`ligne ${parts.join(' · ')}`:'fichier : aucune ligne modifiée ne porte sa preuve';
}

/** Numéros de lignes reliés à au moins un fait, de chaque côté du diff. */
export function markedLines(facts:readonly {lines:LinkLines}[]):Record<Side,Set<number>>{
  return {before:new Set(facts.flatMap(f=>f.lines.before)),after:new Set(facts.flatMap(f=>f.lines.after))};
}

/** Des liens ne s'affichent que sous le diff du même fichier et du même commit. */
export function linksFor<T extends {commit:string; path:string}>(links:T|null, diff:{commit:string; path:string}):T|null{
  return links&&links.commit===diff.commit&&links.path===diff.path?links:null;
}

/** Adresse des liens d'un diff ; le parent choisi est conservé. */
export function diffFactsPath(base:string, diff:{commit:string; path:string; parent:string|null}){
  const query=new URLSearchParams({path:diff.path});
  if(diff.parent)query.set('parent',diff.parent);
  return `${base}/${diff.commit}/diff/facts?${query}`;
}
