import {describe, expect, it} from 'vitest';
import {apiUrl} from './api';

const origin='http://taxo.local:5173';

describe('apiUrl', ()=>{
  it('construit une adresse de l’API, sur l’origine du portail', ()=>{
    expect(apiUrl('/projects/p-1/scans', origin).href).toBe('http://taxo.local:5173/api/projects/p-1/scans');
    expect(apiUrl('/api/projects/p/analyses/j/events', origin).href).toBe('http://taxo.local:5173/api/projects/p/analyses/j/events');
    expect(apiUrl('projects?q=a b', origin).href).toBe('http://taxo.local:5173/api/projects?q=a%20b');
  });
  it('refuse toute adresse qui sortirait de l’API ou du portail', ()=>{
    for(const path of ['/api/../admin', '/projects/%2e%2e/%2e%2e/admin', '/projects/../../admin'])
      expect(()=>apiUrl(path, origin), path).toThrow('Adresse d’API refusée.');
    for(const path of ['//evil.test/x', 'http://evil.test/api/x']){
      const url=apiUrl(path, origin);
      expect([url.origin, url.pathname.startsWith('/api/')], path).toEqual([origin, true]);
    }
  });
  it('se passe de fenêtre hors navigateur', ()=>{
    expect(apiUrl('/health').pathname).toBe('/api/health');
  });
});
