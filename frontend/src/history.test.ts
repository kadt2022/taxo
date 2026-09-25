import {describe, expect, it} from 'vitest';
import {commitCount, MAX_COMMITS} from './history';

describe('commitCount', ()=>{
  it('accepte le nombre demandé, sans valeur par défaut', ()=>{
    expect(commitCount('3')).toBe(3);
    expect(commitCount(' 10 ')).toBe(10);
    expect(commitCount(String(MAX_COMMITS))).toBe(MAX_COMMITS);
  });
  it('refuse une saisie vide, nulle, négative, décimale ou trop grande', ()=>{
    for(const value of ['', '0', '-2', '2.5', 'dix', String(MAX_COMMITS+1)])expect(commitCount(value)).toBeNull();
  });
});
