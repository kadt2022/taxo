import {describe, expect, it} from 'vitest';
import {FULL_VALUES, windowAddress} from './OpenWindow';

const place={origin:'http://127.0.0.1:5173', pathname:'/', hash:''};

describe('l’adresse d’une fenêtre de l’Explorer', ()=>{
  it('reprend tout ce que la page porte et ajoute ce qu’il faut montrer', ()=>{
    const route={params:new URLSearchParams('racine=endpoint%3AGET%20%2Fa&projet=p&profondeur=3')};
    const address=windowAddress(route, place, {plein:'schema', forme:'appels'});
    const url=new URL(address);
    expect(url.origin+url.pathname).toBe('http://127.0.0.1:5173/');
    expect(url.hash.startsWith('#/explorer?')).toBe(true);
    const params=new URLSearchParams(url.hash.split('?')[1]);
    expect(Object.fromEntries(params)).toEqual({racine:'endpoint:GET /a', projet:'p', profondeur:'3', plein:'schema', forme:'appels'});
  });

  it('une valeur demandée remplace celle de la page, et la page n’est pas modifiée', ()=>{
    const route={params:new URLSearchParams('plein=code&noeud=old')};
    const address=windowAddress(route, place, {plein:'code', noeud:'symbol:java:A#m()'});
    expect(new URLSearchParams(address.split('?')[1]).get('noeud')).toBe('symbol:java:A#m()');
    expect(route.params.get('noeud'), 'les paramètres de la page restent ceux de la page').toBe('old');
  });

  it('reprend le projet que le portail a écrit dans la barre d’adresse sans que l’état de la page le sache', ()=>{
    // Le portail ajoute `projet` par replaceState : l'état de la page (la route) ne l'a pas, la barre d'adresse l'a.
    const route={params:new URLSearchParams('racine=endpoint%3AGET%20%2Fa')};
    const address=windowAddress(route, {...place, hash:'#/explorer?racine=endpoint%3AGET%20%2Fa&projet=portail'}, {plein:'code'});
    const params=new URLSearchParams(address.split('?')[1]);
    expect(params.get('projet'), 'sans projet, la fenêtre prendrait le premier de la liste : l’analyse d’un autre projet').toBe('portail');
    expect(params.get('racine')).toBe('endpoint:GET /a');
  });

  it('ne reconnaît que le code et le schéma', ()=>{
    expect(FULL_VALUES).toEqual(['code', 'schema']);
  });
});
