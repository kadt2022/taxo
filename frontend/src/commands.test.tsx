import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {AnalysisCommand} from './commands';

const noop=()=>undefined;

describe('panneau Analyse', ()=>{
  it('sans projet actif : choisir d’abord un projet', ()=>{
    const html=renderToStaticMarkup(<AnalysisCommand running={false} canAnalyze={false} onAnalyze={noop} onClose={noop}/>);
    expect(html).toContain('Sélectionnez d’abord un projet.');
    expect(html).toContain('href="#/projets"');
    expect(html).not.toContain('Dernière analyse');
  });
  it('pendant une analyse : le lancement attend la fin', ()=>{
    const html=renderToStaticMarkup(<AnalysisCommand project={{name:'Iam'}} latest={{id:'s', created_at:'2026-10-02T01:51:47Z', snapshot:{repository:'r',
      commit:'045d211f48'.padEnd(40, '0'), mode:'COMMIT'}}} running canAnalyze onAnalyze={noop} onClose={noop}/>);
    expect(html).toMatch(/disabled=""[^>]*>.*Analyse en cours…/);
    expect(html).toContain('commit 045d211f48');
  });
});
