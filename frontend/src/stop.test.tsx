import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {ask, cancelMinia, createStop, MiniaProgress, reduceMinia, startMinia, STOPPED, stoppedMinia} from './minia-live';
import {actions} from './query';
import type {ServerEvent} from './sse';

const step={operation:'describe', arguments:{}, outcome:'OK' as const, bytes:900, items:9, not_sent:[]};
const event=(type:string, data:unknown={}):ServerEvent=>({type, data});

describe('arrêter Minia (TAXO-UX-03)', ()=>{
  it('retient l’identifiant de la demande et s’arrête sans erreur, trajectoire gardée', ()=>{
    let live=reduceMinia(startMinia(), event('minia.started', {request_id:'r1'}));
    live=reduceMinia(live, event('minia.operation', step));
    live=reduceMinia(live, event('minia.delta', {text:'brouillon'}));
    live=reduceMinia(live, event('minia.cancelled', {message:STOPPED}));
    expect(live).toMatchObject({requestId:'r1', stopped:true, text:'', failure:'', result:null});
    expect(live.trajectory).toEqual([step]);
  });

  it('prend un arrêt côté navigateur pour un arrêt, pas pour une erreur', async ()=>{
    const updates:any[]=[];
    const aborted=Object.assign(new Error('arrêté'), {name:'AbortError'});
    await ask(()=>Promise.reject(aborted), change=>updates.push(change(updates.at(-1)??startMinia())));
    expect(updates.at(-1).stopped).toBe(true);
    await expect(ask(()=>Promise.reject(new Error('panne')), ()=>undefined)).rejects.toThrow('panne');
  });

  it('coupe le flux et prévient le serveur', async ()=>{
    const fetcher=vi.fn().mockResolvedValue(new Response(null, {status:202}));
    const run=createStop(fetcher);
    run.stop('r1');
    expect(run.signal.aborted).toBe(true);
    expect(String(fetcher.mock.calls[0][0])).toContain('/api/minia/requests/r1/cancel');
    expect(fetcher.mock.calls[0][1]).toEqual({method:'POST'});
    const early=vi.fn(), before=createStop(early);
    before.stop();
    expect(before.signal.aborted && early.mock.calls.length===0).toBe(true);
    await expect(cancelMinia('r2', vi.fn().mockRejectedValue(new Error('hors ligne')))).resolves.toBeUndefined();
  });

  it('propose Arrêter tant que Minia travaille, puis dit l’arrêt', ()=>{
    const working=reduceMinia(startMinia(), event('minia.stage', {stage:'exploration', state:'running', label:'Minia interroge Taxo', count:1}));
    const html=renderToStaticMarkup(<MiniaProgress live={{...working, trajectory:[step]}} onStop={()=>undefined}/>);
    expect(html).toContain('>Arrêter</button>');
    const stopped=renderToStaticMarkup(<MiniaProgress live={stoppedMinia({...working, trajectory:[step]})} onStop={()=>undefined}/>);
    expect(stopped).toContain(STOPPED);
    expect(stopped).not.toContain('Arrêter</button>');
    expect(stopped).toContain('Ce que Taxo sait servir');
    expect(stopped).toContain('step-stopped');
    expect(renderToStaticMarkup(<MiniaProgress live={working}/>)).not.toContain('Arrêter</button>');
  });

  it('donne au flux de la demande le signal d’arrêt', async ()=>{
    const control={current:null as ReturnType<typeof createStop>|null};
    const stream=vi.fn().mockResolvedValue((async function*(){})());
    const set={setBusy:vi.fn(), setError:vi.fn(), setResult:vi.fn(), setLive:vi.fn()};
    await actions('/projects/p', 'q', vi.fn(), set, stream, '', control).explain();
    expect(stream.mock.calls[0][1].signal).toBe(control.current?.signal);
  });
});
