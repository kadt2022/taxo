import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {DataPage, NotFoundPage, PendingPage} from './pages';

describe('pages d’état', ()=>{
  it('une première analyse en cours : la page attend, et renvoie à Overview', ()=>{
    const html=renderToStaticMarkup(<PendingPage/>);
    expect(html).toContain('Analyse en cours');
    expect(html).toContain('href="#/"');
  });
  it('une adresse inconnue, et des données jamais analysées, sans rien affirmer', ()=>{
    expect(renderToStaticMarkup(<NotFoundPage/>)).toContain('Page introuvable');
    expect(renderToStaticMarkup(<DataPage/>)).toContain('ni présence ni absence');
  });
});
