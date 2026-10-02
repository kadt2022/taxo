import {useEffect, useState} from 'react';

// Ce que l'analyse affichee a lu, analyseur par analyseur (TAXO-COV-01, restitution). Le serveur compare les
// langages presents a ce que lit le contrat de chaque catalogue ; le portail ne fait que le dire. Un langage non
// lu n'est jamais une absence : ce qui s'y trouve est inconnu.

/** Un analyseur : ce que son contrat lit (`null` : independant du langage) et les langages presents qu'il n'a pas lus. */
export type Reading = {evaluator_id:string; status:string|null; contract:'KNOWN'|'UNKNOWN'; reads:string[]|null; unread:string[]};
export type AnalysisCoverage = {languages:string[]; complete:boolean; evaluators:Reading[]};

type Request=<T>(path:string)=>Promise<T>;

export function readingOf(coverage:AnalysisCoverage|undefined, evaluator:string){
  return coverage?.evaluators.find(item=>item.evaluator_id===evaluator);
}

/** N'a rien lu : il n'avait rien a lire, ou son contrat ne lit aucun langage present d'un inventaire complet. */
export function readNothing(reading:Reading|undefined, coverage:AnalysisCoverage|undefined){
  if(!reading||!coverage)return false;
  if(reading.status==='UNSUPPORTED')return true;
  return reading.reads!==null&&coverage.complete&&!reading.reads.some(item=>coverage.languages.includes(item));
}

/** Les langages presents que ces analyseurs n'ont pas lus, sans doublon. */
export function unreadBy(coverage:AnalysisCoverage|undefined, evaluators:string[]){
  const found=new Set<string>();
  for(const id of evaluators)for(const language of readingOf(coverage, id)?.unread??[])found.add(language);
  return [...found].sort((left, right)=>left.localeCompare(right));
}

/** Tous les langages presents qu'au moins un analyseur lie a des langages n'a pas lus. */
export const unreadAnywhere=(coverage:AnalysisCoverage|undefined)=>
  unreadBy(coverage, coverage?.evaluators.map(item=>item.evaluator_id)??[]);

export const languages=(values:string[])=>values.join(', ');

/** Lue une fois par analyse affichee ; une reponse arrivee apres un changement d'analyse est ignoree. */
export function loadCoverage(request:Request, base:string, scanId:string,
  {onResult, onError}:{onResult:(value:AnalysisCoverage)=>void; onError:(message:string)=>void}){
  let active=true;
  request<AnalysisCoverage>(`${base}/scans/${scanId}/coverage`).then(value=>{if(active)onResult(value);})
    .catch(reason=>{if(active)onError((reason as Error).message);});
  return ()=>{active=false;};
}

/** Ce qu'a lu l'analyse affichee, recharge a chaque changement d'analyse ; rien pendant une analyse en cours. */
export function useCoverage(request:Request, base:string, scanId:string|undefined, shownId:string|undefined, running:boolean){
  const [reading,setReading]=useState<{scanId:string; value:AnalysisCoverage}|null>(null);
  useEffect(()=>{
    if(!scanId||running){return undefined;}
    return loadCoverage(request, base, scanId, {onResult:value=>setReading({scanId, value}), onError:()=>setReading(null)});
  },[base, scanId, running]);
  return reading&&reading.scanId===shownId?reading.value:undefined;
}
