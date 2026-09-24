import {describe, expect, it} from 'vitest';
import {diffFactsPath, lineLabel, linksFor, markedLines} from './links';

describe('lineLabel', ()=>{
  it('nomme les lignes des deux côtés', ()=>{
    expect(lineLabel({before:[5], after:[5, 6]})).toBe('ligne avant 5 · après 5, 6');
  });
  it('nomme un seul côté', ()=>{
    expect(lineLabel({before:[], after:[12]})).toBe('ligne après 12');
    expect(lineLabel({before:[3], after:[]})).toBe('ligne avant 3');
  });
  it('dit quand le lien ne porte que sur le fichier', ()=>{
    expect(lineLabel({before:[], after:[]})).toBe('fichier : aucune ligne modifiée ne porte sa preuve');
  });
});

describe('markedLines', ()=>{
  it('réunit les lignes de tous les faits sans mélanger les côtés', ()=>{
    const marked=markedLines([{lines:{before:[5], after:[5]}}, {lines:{before:[], after:[7, 5]}}]);
    expect([...marked.before]).toEqual([5]);
    expect([...marked.after].sort((a, b)=>a-b)).toEqual([5, 7]);
  });
  it('ne marque rien sans fait', ()=>{
    expect(markedLines([]).after.size).toBe(0);
  });
});

describe('linksFor', ()=>{
  const links={commit:'abc', path:'A.java'};
  it('garde les liens du même fichier et du même commit', ()=>{
    expect(linksFor(links, {commit:'abc', path:'A.java'})).toBe(links);
  });
  it('écarte des liens arrivés pour un autre diff', ()=>{
    expect(linksFor(links, {commit:'abc', path:'B.java'})).toBeNull();
    expect(linksFor(links, {commit:'def', path:'A.java'})).toBeNull();
    expect(linksFor(null, {commit:'abc', path:'A.java'})).toBeNull();
  });
});

describe('diffFactsPath', ()=>{
  it('encode le chemin et garde le parent choisi', ()=>{
    expect(diffFactsPath('/projects/p/history/commits', {commit:'abc', path:'src/a b.java', parent:'def'}))
      .toBe('/projects/p/history/commits/abc/diff/facts?path=src%2Fa+b.java&parent=def');
  });
  it('omet le parent d’un commit racine', ()=>{
    expect(diffFactsPath('/c', {commit:'abc', path:'a', parent:null})).toBe('/c/abc/diff/facts?path=a');
  });
});
