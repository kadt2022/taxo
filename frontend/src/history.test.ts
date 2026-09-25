import {describe, expect, it} from 'vitest';
import {commitCount, consultRequest, MAX_COMMITS} from './history';

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

describe('consultRequest', ()=>{
  it('construit la consultation avec le nombre demandé', ()=>{
    expect(consultRequest('/projects/p/history/commits', '3')).toEqual({path:'/projects/p/history/commits?limit=3'});
  });
  it('explique pourquoi une saisie est refusée', ()=>{
    expect(consultRequest('/c', '')).toEqual({error:`Indiquez un nombre de commits entre 1 et ${MAX_COMMITS}.`});
  });
});
