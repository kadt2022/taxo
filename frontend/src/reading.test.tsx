import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {AnalysisLimits, overviewCards, ProjectOverview, type EvaluationSummary, type Scan} from './overview';
import {loadCoverage, readNothing, unreadAnywhere, unreadBy, type AnalysisCoverage, type Reading} from './reading';
import {RoutesView} from './routes';
import {byDomain} from './domains';
import {reduce, startRun} from './analysis';
import type {EvaluatorEntry} from './comparison';

// TAXO-COV-01, restitution : un langage present qu'un analyseur ne lit pas est dit « non analyse », jamais absent.
const snapshot={repository:'p', commit:'a'.repeat(40), mode:'COMMIT' as const};
const summary=(evaluator_id:string, extra:Partial<EvaluationSummary>={}):EvaluationSummary=>({execution_id:evaluator_id, evaluator_id,
  producer_version:'1', status:'SUCCESS', started_at:'', finished_at:'', duration_seconds:0, fact_count:0, coverage_count:1, warning_count:0,
  relations:{}, coverage:[], snapshot, ...extra});
const scanOf=(...evaluations:EvaluationSummary[]):Scan=>({id:'s', created_at:'', files_count:422, evaluations,
  evaluation_summary:evaluations[0]});
const reading=(evaluator_id:string, status:string, reads:string[]|null, unread:string[], contract:'KNOWN'|'UNKNOWN'='KNOWN'):Reading=>
  ({evaluator_id, status, contract, reads, unread});
const TAXO:AnalysisCoverage={languages:['Python', 'TypeScript'], complete:true, evaluators:[
  reading('taxo.inventory', 'SUCCESS', null, []), reading('taxo.git', 'SUCCESS', null, []),
  reading('taxo.spring-api', 'UNSUPPORTED', ['Java'], ['Python', 'TypeScript']),
  reading('taxo.spring-security', 'UNSUPPORTED', ['Java'], ['Python', 'TypeScript'])]};
const taxoScan=scanOf(summary('taxo.inventory'), summary('taxo.git'), summary('taxo.spring-api', {status:'UNSUPPORTED'}),
  summary('taxo.spring-security', {status:'UNSUPPORTED'}));
const card=(scan:Scan, id:string, coverage?:AnalysisCoverage)=>overviewCards(scan, undefined, coverage).find(item=>item.id===id)!;

describe('ce que chaque analyseur a lu', ()=>{
  it('un analyseur sans rien à lire ne lit rien ; un contrat qui lit un langage présent a lu', ()=>{
    expect(readNothing(TAXO.evaluators[2], TAXO)).toBe(true);
    const legacy=reading('taxo.spring-api', 'SUCCESS', ['Java'], ['Python']);
    expect(readNothing(legacy, {...TAXO, languages:['Python']})).toBe(true);
    expect(readNothing(legacy, {...TAXO, languages:['Python'], complete:false})).toBe(false);
    expect(readNothing(reading('x', 'SUCCESS', ['Java'], ['Python']), {...TAXO, languages:['Java', 'Python']})).toBe(false);
    expect(readNothing(undefined, TAXO)).toBe(false);
    expect(unreadBy(TAXO, ['taxo.spring-api', 'taxo.git'])).toEqual(['Python', 'TypeScript']);
    expect(unreadAnywhere(undefined)).toEqual([]);
  });

  it('Overview : fichiers inventoriés, routes et sécurité « Non analysé » avec les langages non lus', ()=>{
    expect(card(taxoScan, 'project', TAXO).unit).toBe('fichiers inventoriés');
    const structure=scanOf(summary('taxo.inventory'), summary('taxo.structure', {relations:{CONTAINS:2}}),
      summary('taxo.spring-boot', {status:'UNSUPPORTED'}));
    const boot={...TAXO, evaluators:[reading('taxo.spring-boot', 'UNSUPPORTED', ['Java'], ['Python'])]};
    expect(card(structure, 'architecture', boot).lines).toEqual(['0 dépendance', 'Lu dans les fichiers de build, sans rien exécuter.']);
    expect(card(structure, 'architecture').lines[1]).toBe('0 application Spring Boot');
    expect(card(taxoScan, 'api', TAXO)).toMatchObject({value:'Non analysé', state:'unknown',
      lines:['Routes non cherchées en Python, TypeScript : aucun analyseur de ce domaine ne lit ces langages.']});
    expect(card(taxoScan, 'security', TAXO)).toMatchObject({value:'Non analysé',
      lines:['Règles de sécurité non cherchées en Python, TypeScript : aucun analyseur de ce domaine ne lit ces langages.']});
    const nothing={...TAXO, languages:[], evaluators:[reading('taxo.spring-api', 'UNSUPPORTED', ['Java'], [])]};
    expect(card(taxoScan, 'api', nothing).lines[0]).toBe('Routes non cherchées : aucun fichier dans les langages que son analyseur lit.');
  });

  it('Overview : un domaine en partie lu garde son compte et nomme ce qu’il n’a pas lu', ()=>{
    const mixed:AnalysisCoverage={languages:['Java', 'Python'], complete:true,
      evaluators:[reading('taxo.spring-api', 'SUCCESS', ['Java'], ['Python'])]};
    const scan=scanOf(summary('taxo.inventory'), summary('taxo.spring-api', {relations:{HANDLED_BY:4}}));
    expect(card(scan, 'api', mixed)).toMatchObject({value:'4', state:'known', lines:['Non analysé : Python']});
    const security=scanOf(summary('taxo.inventory'), summary('taxo.spring-security', {relations:{AUTHORIZED_BY:2}}));
    expect(card(security, 'security', {...mixed, evaluators:[reading('taxo.spring-security', 'SUCCESS', ['Java'], ['Python'])]}).lines)
      .toEqual(['Non analysé : Python']);
  });

  it('jamais « Aucune limite signalée » quand des langages ne sont pas lus', ()=>{
    const html=renderToStaticMarkup(<ProjectOverview scan={taxoScan} coverage={TAXO}/>);
    expect(html).toContain('Non analysé : Python, TypeScript');
    expect(html).not.toContain('Aucune limite signalée');
    const gaps=scanOf(summary('taxo.inventory', {coverage:[{coverage_type:'READ_ERROR', count:2, subjects:['file:a']}]}));
    expect(renderToStaticMarkup(<ProjectOverview scan={gaps} coverage={TAXO}/>))
      .toContain('<strong>2 limites signalées</strong><span> · 1 analyseur concerné · Non analysé : Python, TypeScript</span>');
    expect(renderToStaticMarkup(<ProjectOverview scan={gaps}/>)).not.toContain('Non analysé : ');
  });

  it('la page Limites dit ce que chaque analyseur lit et n’a pas lu', ()=>{
    const unknown={...TAXO, complete:false, evaluators:[...TAXO.evaluators, reading('taxo.retire', 'SUCCESS', [], ['Python'], 'UNKNOWN')]};
    const html=renderToStaticMarkup(<AnalysisLimits scan={taxoScan} coverage={unknown}/>);
    expect(html).toContain('Langages non analysés');
    expect(html).toContain('<td>Java</td><td>Python, TypeScript</td>');
    expect(html).toContain('Contrat inconnu');
    expect(html).toContain('L’inventaire n’a pas tout lu');
    expect(html).not.toContain('Inventaire du code</td>');
  });

  it('Routes : aucune route dans ce que Taxo a lu n’est pas « aucune route »', ()=>{
    const view=(routes:number, unread:string[])=>renderToStaticMarkup(<RoutesView result={{routes:Array.from({length:routes}, (_, index)=>({
      endpoint:`endpoint:GET /r${index}`, verb:'GET', path:`/r${index}`, handlers:[], applications:[], matched:[], rules:[], protections:[],
      gaps:[], state:'NO_CONCLUSION'})),
    unestablished:[]} as never} error="" text="" filter="ALL" selected="" onText={vi.fn()} onFilter={vi.fn()} onSelect={vi.fn()} unread={unread}/>);
    const empty=view(0, ['Python', 'TypeScript']);
    expect(empty).toContain('Aucune route établie dans ce que Taxo a lu. Non analysé : Python, TypeScript');
    expect(empty).toContain('ces langages n’est ni trouvée ni exclue');
    expect(empty).not.toContain('Aucune route HTTP établie par cette analyse');
    expect(view(2, ['Python'])).toContain('Non analysé : Python — une route écrite dans ce langage');
    expect(view(0, [])).toContain('Aucune route HTTP établie par cette analyse');
  });

  it('comparaison : un domaine sans rien à lire est « Non analysé », jamais « Aucun changement »', ()=>{
    const refused=(evaluator_id:string, reason:string):EvaluatorEntry=>({evaluator_id, comparable:false, reason, message:`raison ${reason}`,
      versions:{before:[], after:[]}, not_analysed:{before:['Python'], after:['Python', 'TypeScript']}});
    const domains=byDomain({evaluators:[refused('taxo.spring-security', 'NOT_SUPPORTED_BEFORE'),
      {evaluator_id:'taxo.inventory', comparable:true, versions:{before:[], after:[]}, relations:{}, not_analysed:{before:[], after:[]}},
      refused('taxo.git', 'CATALOG_CHANGED')]});
    const security=domains.find(item=>item.id==='securite')!;
    expect(security).toMatchObject({state:'absent', unread:['Python', 'TypeScript']});
    expect(security.reasons[0].message).toBe('raison NOT_SUPPORTED_BEFORE');
    expect(domains.find(item=>item.id==='git')?.state).toBe('refused');
    expect(domains.find(item=>item.id==='fichiers')).toMatchObject({state:'unchanged', unread:[]});
    expect(byDomain({evaluators:[refused('outil.maison', 'NOT_SUPPORTED_AFTER')]}).find(item=>item.id==='autres')?.state).toBe('absent');
  });

  it('la progression dit qu’un analyseur sans rien à lire n’a rien analysé', ()=>{
    const run=reduce({...startRun(), steps:[{id:'taxo.spring-api', label:'Endpoints', state:'running'}]} as never,
      {type:'evaluator.completed', data:{evaluator:'taxo.spring-api', summary:summary('taxo.spring-api', {status:'UNSUPPORTED'}), result:null}} as never);
    expect(run.steps.find(step=>step.id==='taxo.spring-api')).toMatchObject({state:'done', detail:'Non pris en charge : rien à lire'});
  });

  it('se charge une fois par analyse, et ignore une réponse arrivée trop tard', async()=>{
    const onResult=vi.fn(), onError=vi.fn();
    const request=vi.fn(()=>Promise.resolve(TAXO)) as never;
    const cancel=loadCoverage(request, '/projects/p', 's', {onResult, onError});
    expect((request as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe('/projects/p/scans/s/coverage');
    cancel();
    await Promise.resolve();
    expect(onResult).not.toHaveBeenCalled();
    const failing=vi.fn(()=>Promise.reject(new Error('panne'))) as never;
    loadCoverage(failing, '/projects/p', 's', {onResult, onError});
    await new Promise(resolve=>setTimeout(resolve, 0));
    expect(onError).toHaveBeenCalledWith('panne');
  });
});
