import {describe, expect, it} from 'vitest';
import {commitCount, consultRequest, impactSource, MAX_COMMITS, notComparable} from './history';

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

describe('impactSource', ()=>{
  const side=(kind:'ANALYSIS'|'REREAD', id:string|null, commit:string)=>({kind, id, commit, created_at:null});
  it('nomme les deux analyses enregistrées qui ont servi', ()=>{
    expect(impactSource({source:'MEMORY', analyses:{before:side('ANALYSIS','a1','1111111aaa'), after:side('ANALYSIS','a2','2222222bbb')}}))
      .toBe('Depuis les analyses enregistrées a1 (parent 1111111) et a2 (commit 2222222) : le dépôt n’a pas été relu.');
  });
  it('dit qu’il a fallu relire le dépôt, sans nommer d’analyse', ()=>{
    const text=impactSource({source:'REREAD', analyses:{before:side('REREAD',null,'1111111aaa'), after:side('REREAD',null,'2222222bbb')}});
    expect(text).toMatch(/^Le dépôt a été relu/);
    expect(text).not.toMatch(/analyses enregistrées [^ ]+ \(/);
    expect(impactSource({source:'REREAD', analyses:{before:null, after:side('REREAD',null,'2222222bbb')}})).toMatch(/pas de parent/);
  });
});

describe('notComparable', ()=>{
  it('rend la raison de Taxo, sans supposer un échec', ()=>{
    const text=notComparable(['Rien à lire pour cet analyseur dans l’analyse de départ.']);
    expect(text).toContain('Rien à lire');
    expect(text).not.toMatch(/a échoué/);
  });
});
