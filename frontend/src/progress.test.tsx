import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {openStream, parseEvents, readEvents, type ServerEvent} from './sse';
import {AnalysisProgress, analyzeProject, follow, liveScan, pendingEvaluators, progressText, reduce, startRun, type Run} from './analysis';
import {ask, askButton, MiniaProgress, questionInit, reduceMinia, stageText, startMinia} from './minia-live';
import {ProjectOverview, type EvaluationSummary, type Scan} from './overview';

const snapshot={repository:'p', commit:'a'.repeat(40), mode:'COMMIT' as const};
const summary=(evaluator_id:string, extra:Partial<EvaluationSummary>={}):EvaluationSummary=>({execution_id:`x-${evaluator_id}`,
  evaluator_id, producer_version:'0.1.0', status:'SUCCESS', started_at:'', finished_at:'', duration_seconds:0.1,
  fact_count:3, coverage_count:1, warning_count:0, relations:{}, coverage:[], snapshot, ...extra});
const event=(type:string, data:unknown={}):ServerEvent=>({type, data});

function streamOf(...chunks:string[]){
  const bytes=new TextEncoder();
  return new ReadableStream<Uint8Array>({start(controller){for(const chunk of chunks)controller.enqueue(bytes.encode(chunk));controller.close();}});
}

describe('sse', ()=>{
  it('découpe un flux en événements, commentaires ignorés', ()=>{
    const {events, rest}=parseEvents('id: 1\r\nevent: analysis.started\r\ndata: {"a":1}\r\n\r\n: en cours\n\nevent: x\ndata: [1,\ndata: 2]\n\nevent: y\ndata: {"b"');
    expect(events).toEqual([{id:'1', type:'analysis.started', data:{a:1}}, {id:undefined, type:'x', data:[1,2]}]);
    expect(rest).toBe('event: y\ndata: {"b"');
    expect(parseEvents('data: 3\n\nretry\n\n').events).toEqual([{id:undefined, type:'message', data:3}]);
  });
  it('lit les événements au fur et à mesure, même coupés entre deux morceaux', async ()=>{
    const seen=[];
    for await(const item of readEvents(streamOf('event: a\ndata: {"n":', '1}\n\nevent: b\ndata: 2', '')))seen.push(item);
    expect(seen).toEqual([{id:undefined, type:'a', data:{n:1}}, {id:undefined, type:'b', data:2}]);
  });
  it('rend le message d’une réponse en erreur', async ()=>{
    const refused=vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Projet introuvable.'}), {status:404}));
    await expect(openStream('/x', undefined, refused)).rejects.toThrow('Projet introuvable.');
    const broken=vi.fn().mockResolvedValue(new Response('oups', {status:500}));
    await expect(openStream('/x', undefined, broken)).rejects.toThrow('La requête a échoué (500).');
    const ok=vi.fn().mockResolvedValue(new Response(streamOf('data: 1\n\n')));
    const items=[];for await(const item of await openStream('/x', undefined, ok))items.push(item.data);
    expect(items).toEqual([1]);
  });
});

function played(...events:ServerEvent[]){
  return events.reduce(reduce, startRun());
}

describe('reduce', ()=>{
  it('montre les vraies étapes, dans l’ordre', ()=>{
    const run=played(event('analysis.started', {evaluators:['taxo.inventory','taxo.git']}),
      event('snapshot.ready', {commit:'b'.repeat(40)}), event('evaluator.started', {evaluator:'taxo.inventory'}),
      event('evaluator.progress', {evaluator:'taxo.inventory', stage:'files', message:'Fichiers recensés', completed:320, total:320}));
    expect(run.steps.map(step=>[step.label, step.state])).toEqual([['Préparation du projet','done'], ['Inventaire du code','running'],
      ['Historique Git','pending'], ['Consolidation des résultats','pending']]);
    expect(run.steps[0].detail).toBe('Commit bbbbbbbbbbbb');
    expect(run.steps[1].detail).toBe(progressText({message:'Fichiers recensés', completed:320, total:320}));
    expect(pendingEvaluators(run)).toEqual(['taxo.inventory','taxo.git']);
  });
  it('publie les résultats d’un évaluateur dès qu’il termine', ()=>{
    const run=played(event('analysis.started', {evaluators:['taxo.inventory','taxo.git']}),
      event('evaluator.completed', {evaluator:'taxo.inventory', summary:summary('taxo.inventory'), result:{files_count:320}}),
      event('evaluator.failed', {evaluator:'taxo.git', summary:summary('taxo.git', {status:'FAILED'}), message:'boom'}),
      event('analysis.consolidating'), event('inconnu'));
    expect(run.steps.map(step=>step.state)).toEqual(['running','done','failed','running']);
    expect(run.steps[2].detail).toBe('Analyse incomplète — voir le détail');
    expect(run.result).toEqual({files_count:320});
    expect(run.summaries.map(item=>item.evaluator_id)).toEqual(['taxo.inventory','taxo.git']);
    const done=reduce(run, event('analysis.completed', {scan:{id:'s2', created_at:'t'}}));
    expect([done.status, done.scan?.id, done.steps[3].state]).toEqual(['done','s2','done']);
  });
  it('dit pourquoi l’analyse s’est arrêtée', ()=>{
    const run=played(event('analysis.started', {evaluators:['taxo.inventory']}), event('analysis.failed', {message:'NOT_A_GIT_REPOSITORY : …'}));
    expect([run.status, run.message, run.steps[0].state]).toEqual(['failed','NOT_A_GIT_REPOSITORY : …','failed']);
  });
  it('écrit une progression réelle, jamais un pourcentage', ()=>{
    expect(progressText({message:'Commits lus', completed:1500, total:null})).toBe(`Commits lus : ${(1500).toLocaleString('fr-CA')}`);
    expect(progressText({message:'Préparation', completed:null, total:null})).toBe('Préparation');
  });
});

describe('liveScan', ()=>{
  const previous:Scan={id:'s1', created_at:'t', files_count:300, evaluations:[summary('taxo.inventory', {fact_count:1}), summary('taxo.git')]};
  it('garde l’ancienne analyse et remplace chaque partie dès qu’elle est recalculée', ()=>{
    const run=played(event('analysis.started', {evaluators:['taxo.inventory','taxo.git']}),
      event('evaluator.completed', {evaluator:'taxo.inventory', summary:summary('taxo.inventory', {fact_count:9}), result:{files_count:320}}));
    const shown=liveScan(previous, run)!;
    expect(shown.files_count).toBe(320);
    expect(shown.evaluations?.map(item=>[item.evaluator_id, item.fact_count])).toEqual([['taxo.inventory',9], ['taxo.git',3]]);
  });
  it('n’affiche rien tant que la première analyse n’a rien produit', ()=>{
    expect(liveScan(undefined, startRun())).toBeUndefined();
    const run=played(event('evaluator.completed', {evaluator:'taxo.git', summary:summary('taxo.git'), result:null}));
    expect(liveScan(undefined, run)?.evaluations?.map(item=>item.evaluator_id)).toEqual(['taxo.git']);
    expect(liveScan({id:'old', created_at:'', evaluation_summary:summary('taxo.inventory')}, run)?.evaluations).toHaveLength(2);
  });
});

describe('vues de progression', ()=>{
  it('montre chaque étape avec son état', ()=>{
    const run:Run=played(event('analysis.started', {evaluators:['taxo.inventory','taxo.git']}), event('snapshot.ready', {commit:'c'}),
      event('evaluator.started', {evaluator:'taxo.inventory'}));
    const html=renderToStaticMarkup(<AnalysisProgress run={run}/>);
    expect(html).toContain('Analyse en cours');
    expect(html).toContain('Inventaire du code…');
    expect(html).toContain('0 / 2 analyses terminées');
    expect(html).not.toMatch(/%|taxo\.git/);
    expect(renderToStaticMarkup(<AnalysisProgress run={{...run, status:'failed', message:'Échec'}}/>)).toContain('Analyse interrompue');
    expect(renderToStaticMarkup(<AnalysisProgress run={{...startRun(), status:'done'}}/>)).toContain('Analyse terminée');
  });
  it('garde les cartes visibles, marquées, pendant une nouvelle analyse', ()=>{
    const scan:Scan={id:'s', created_at:'', files_count:3, evaluations:[summary('taxo.inventory'), summary('taxo.git')]};
    const html=renderToStaticMarkup(<ProjectOverview scan={scan} pending={['taxo.git']}/>);
    expect(html).toContain('Nouvelle analyse en cours…');
    expect(html).toContain('class="card card-known card-stale" aria-label="Historique"');
    expect(html.match(/card-stale/g)).toHaveLength(1);
    expect(renderToStaticMarkup(<ProjectOverview scan={scan}/>)).not.toContain('Nouvelle analyse');
  });
});

describe('suivre une analyse', ()=>{
  it('lance, suit le flux et ajoute l’analyse terminée', async ()=>{
    async function* events(){yield event('analysis.started', {evaluators:[]});yield event('analysis.completed', {scan:{id:'s9', created_at:''}});}
    let run:Run|null=null;
    const deps={request:vi.fn().mockResolvedValue({events:'/api/projects/p/analyses/j/events'}), open:vi.fn().mockResolvedValue(events()),
      setRun:vi.fn((change:(value:Run|null)=>Run|null)=>{run=change(run);}), addScan:vi.fn(), setError:vi.fn(), setBusy:vi.fn()};
    await analyzeProject('p', deps);
    expect(deps.request).toHaveBeenCalledWith('/projects/p/analyses', {method:'POST'});
    expect(deps.open).toHaveBeenCalledWith('/api/projects/p/analyses/j/events');
    expect(deps.addScan).toHaveBeenCalledWith({id:'s9', created_at:''});
    expect((run as Run|null)?.status).toBe('done');
    expect(deps.setBusy.mock.calls.map(call=>call[0])).toEqual([true,false]);
  });
  it('rend la main et dit l’erreur si le lancement échoue', async ()=>{
    let run:Run|null=null;
    const deps={request:vi.fn().mockRejectedValue(new Error('Projet introuvable.')), open:vi.fn(),
      setRun:vi.fn((change:(value:Run|null)=>Run|null)=>{run=change(run);}), addScan:vi.fn(), setError:vi.fn(), setBusy:vi.fn()};
    await analyzeProject('p', deps);
    expect(deps.setError).toHaveBeenLastCalledWith('Projet introuvable.');
    expect(run).toBeNull();
    expect(deps.open).not.toHaveBeenCalled();
    const seen:string[]=[];
    await follow(async()=>({events:'/e'}), async()=>[event('a'), event('b')], item=>seen.push(item.type));
    expect(seen).toEqual(['a','b']);
  });
});

describe('Minia en direct', ()=>{
  it('suit les étapes, le texte provisoire puis la réponse', async ()=>{
    let live=null as ReturnType<typeof startMinia>|null;
    async function* events(){
      yield event('minia.stage', {stage:'facts', state:'running', label:'Sélection des faits pertinents', count:null});
      yield event('minia.stage', {stage:'facts', state:'done', label:'Sélection des faits pertinents', count:14});
      yield event('minia.stage', {stage:'interpretation', state:'running', label:'Minia interprète 14 faits Taxo', count:14});
      yield event('minia.delta', {text:'D’après les faits Taxo, '});
      yield event('minia.delta', {text:'ce commit modifie…'});
      yield event('autre');
    }
    await ask(async()=>events(), change=>{live=change(live as never);});
    expect(live!.stages.map(stage=>stageText(stage))).toEqual(['Sélection des faits pertinents : 14 faits', 'Minia interprète 14 faits Taxo']);
    expect(live!.text).toBe('D’après les faits Taxo, ce commit modifie…');
    const html=renderToStaticMarkup(<MiniaProgress live={live!}/>);
    expect(html).toContain('Minia examine les faits Taxo…');
    expect(html).toContain('Minia interprète 14 faits Taxo…');
    expect(html).toContain('en cours d’écriture');
    const done=reduceMinia(live!, event('minia.completed', {answer:'x'}));
    expect(done.result).toEqual({answer:'x'});
    const failed=reduceMinia(startMinia(), event('minia.failed', {message:'Ollama a répondu 500.'}));
    expect(renderToStaticMarkup(<MiniaProgress live={failed}/>)).toContain('Ollama a répondu 500.');
    expect(stageText({stage:'facts', state:'done', label:'Sélection', count:1})).toBe('Sélection : 1 fait');
  });
  it('change le bouton pendant que Minia travaille', ()=>{
    expect(askButton(true, 'Demander à Minia')).toBe('● Minia travaille…');
    expect(askButton(false, 'Demander à Minia')).toBe('Demander à Minia');
    expect(questionInit({question:'q'})).toMatchObject({method:'POST', body:'{"question":"q"}'});
  });
});
