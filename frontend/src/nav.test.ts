// @vitest-environment happy-dom
import {act, createElement} from 'react';
import {createRoot} from 'react-dom/client';
import {describe, expect, it} from 'vitest';
import {go, href, parse, useRoute, type Route} from './nav';

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;

describe('adresses du portail', ()=>{
  it('lit la page, l’élément et les paramètres', ()=>{
    expect(parse('#/analyses/a%201')).toMatchObject({page:'analyses', id:'a 1'});
    const compared=parse('#/comparaisons?a=x&b=y');
    expect([compared.page, compared.id, compared.params.get('a'), compared.params.get('b')]).toEqual(['comparaisons', undefined, 'x', 'y']);
  });
  it('ouvre Overview sans page, garde les anciennes ancres, et dit introuvable une page inconnue', ()=>{
    for(const hash of ['', '#', '#/', '#/overview/x'])expect(parse(hash)).toMatchObject({page:'overview', id:undefined});
    expect(parse('#routes').page).toBe('routes');
    expect(parse('#/nulle-part').page).toBe('introuvable');
    expect(href('introuvable')).toBe('#/');
  });
  it('écrit une adresse, sans paramètre vide', ()=>{
    expect(href('overview')).toBe('#/');
    expect(href('analyses', 'a 1')).toBe('#/analyses/a%201');
    expect(href('comparaisons', undefined, {a:'x', b:undefined})).toBe('#/comparaisons?a=x');
    expect(parse(href('comparaisons', 'choix', {a:'x', b:'y'}))).toMatchObject({page:'comparaisons', id:'choix'});
  });
  it('change d’adresse, et suit chaque changement', async()=>{
    const place={hash:''};
    go('#/routes', place);
    expect(place.hash).toBe('#/routes');
    const host=document.createElement('div'), root=createRoot(host), seen:Route[]=[];
    function Probe(){seen.push(useRoute());return null;}
    window.location.hash='#/limites';
    await act(async()=>{root.render(createElement(Probe));});
    expect(seen.at(-1)?.page).toBe('limites');
    await act(async()=>{window.location.hash='#/architecture';window.dispatchEvent(new Event('hashchange'));});
    expect(seen.at(-1)?.page).toBe('architecture');
    act(()=>root.unmount());
  });
});
