import {describe, expect, it} from 'vitest';
import {INITIAL, NO_TRAIL, addressOf, canGoBack, canGoForward, reduce, settingsOf, visit, type ExplorerState} from './state';
import {depthCut, element, tile} from './__fixtures__/tiles';

const [A, B]=['module:a', 'module:b'];
const opened=tile({items:[element(A, B)], nodes:[[A, 0, true], [B, 1, false]], frontier:[depthCut(B)], stop:'DEPTH'});
const fromB=tile({root:B, items:[element(B, 'module:c')], nodes:[[B, 0, true], ['module:c', 1, false]]});

describe('la navigation', ()=>{
  it('ignore une réponse qui n’est pas celle de la demande en cours', ()=>{
    let state:ExplorerState=reduce(INITIAL, {type:'start', pending:{id:1, action:'open'}});
    state=reduce(state, {type:'start', pending:{id:2, action:'open'}});
    expect(reduce(state, {type:'loaded', id:1, tile:opened})).toBe(state);
    expect(reduce(state, {type:'failed', id:1, message:'trop tard'})).toBe(state);
    state=reduce(state, {type:'loaded', id:2, tile:opened});
    expect(state.view?.elements).toHaveLength(1);
    expect(state.pending).toBeNull();
  });

  it('développe dans la vue existante, et une demande abandonnée n’arrive jamais', ()=>{
    let state=reduce(reduce(INITIAL, {type:'start', pending:{id:1, action:'open'}}), {type:'loaded', id:1, tile:opened});
    state=reduce(state, {type:'start', pending:{id:2, action:'expand', node:B}});
    expect(state.view?.elements, 'développer garde la vue pendant la demande').toHaveLength(1);
    const cancelled=reduce(state, {type:'cancel'});
    expect(reduce(cancelled, {type:'loaded', id:2, tile:fromB})).toBe(cancelled);
    state=reduce(state, {type:'loaded', id:2, tile:fromB});
    expect(state.view?.elements.map(item=>[item.fact.object, item.level])).toEqual([[B, 1], ['module:c', 2]]);
  });

  it('ouvrir une nouvelle ancre efface la vue, la sélection et l’erreur', ()=>{
    let state=reduce(INITIAL, {type:'start', pending:{id:1, action:'open'}});
    state=reduce(state, {type:'failed', id:1, message:'Refusé.'});
    expect(state.error).toBe('Refusé.');
    state=reduce(reduce(state, {type:'select', selected:{kind:'node', reference:A}}), {type:'start', pending:{id:2, action:'open'}});
    expect(state).toEqual({...INITIAL, pending:{id:2, action:'open'}});
  });

  it('suit précédent et suivant sur l’adresse', ()=>{
    let trail=visit(visit(visit(NO_TRAIL, 'a'), 'b'), 'c');
    expect([trail.position, canGoBack(trail), canGoForward(trail)]).toEqual([2, true, false]);
    trail=visit(trail, 'b');
    expect([trail.position, canGoForward(trail)]).toEqual([1, true]);
    trail=visit(trail, 'c');
    expect(trail.position).toBe(2);
    trail=visit(visit(trail, 'b'), 'd');
    expect(trail, 'une nouvelle ancre efface la suite').toEqual({entries:['a', 'b', 'd'], position:2});
    expect(visit(trail, 'd')).toBe(trail);
  });
});

describe('l’adresse', ()=>{
  it('se relit à l’identique, et une valeur hors contrat prend sa valeur par défaut', ()=>{
    const settings={analysis:'s1', root:'endpoint:GET /orders', relations:['HANDLED_BY', 'SERVED_BY'], direction:'OUTGOING' as const,
      depth:3, preset:'large' as const};
    const params=new URLSearchParams(Object.entries(addressOf(settings)).filter((entry):entry is [string, string]=>!!entry[1]));
    expect(settingsOf(params)).toEqual(settings);
    expect(settingsOf(new URLSearchParams('profondeur=9&sens=SIDEWAYS&budget=huge&pas=A,,A'))).toEqual({analysis:undefined,
      root:undefined, relations:['A'], direction:'BOTH', depth:2, preset:'standard'});
  });
});
