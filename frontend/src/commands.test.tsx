import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {AnalysisCommand, LaunchCard} from './commands';

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

describe('poste de lancement de la page Analyses', ()=>{
  const latest={id:'s', created_at:'2026-10-02T01:51:47Z', snapshot:{repository:'r', commit:'045d211f48'.padEnd(40, '0'), mode:'COMMIT' as const}};
  const steps=[{id:'preparation', label:'Préparation du projet', state:'done' as const, detail:''},
    {id:'taxo.git', label:'Historique Git', state:'running' as const, detail:'Commits lus : 500'},
    {id:'consolidation', label:'Consolidation des résultats', state:'pending' as const, detail:''}];
  const run=(status:'running'|'failed'|'done', message='')=>({status, steps, summaries:[], result:null, scan:null, message});
  it('au repos : le projet, ce que fait l’analyse, la dernière, et le lancement', ()=>{
    const html=renderToStaticMarkup(<LaunchCard project={{name:'Iam'}} latest={latest} count={7} run={null} canAnalyze onAnalyze={noop}/>);
    expect(html).toContain('Analyser Iam maintenant');
    expect(html).toContain('commit 045d211f48');
    expect(html).toContain('7 analyses enregistrées');
    expect(html).toMatch(/<button[^>]*class="launch-button"[^>]*>.*Lancer l’analyse globale/);
    expect(html).not.toContain('disabled');
  });
  it('sans analyse : la première ; sans projet : rien à lancer', ()=>{
    expect(renderToStaticMarkup(<LaunchCard project={{name:'Iam'}} count={0} run={null} canAnalyze onAnalyze={noop}/>))
      .toContain('Lancer la première analyse');
    const none=renderToStaticMarkup(<LaunchCard count={0} run={null} canAnalyze onAnalyze={noop}/>);
    expect(none).toContain('Choisissez un projet');
    expect(none).toMatch(/class="launch-button" disabled=""/);
  });
  it('en cours : une piste d’étapes réelles, l’étape courante et le compte, sans pourcentage', ()=>{
    const html=renderToStaticMarkup(<LaunchCard project={{name:'Iam'}} latest={latest} count={7} run={run('running')} canAnalyze onAnalyze={noop}/>);
    expect(html).toContain('Analyse de Iam…');
    expect(html.match(/<li class="track-/g)).toHaveLength(3);
    expect(html).toContain('<strong>Historique Git</strong> · Commits lus : 500');
    expect(html).toContain('1 étape sur 3');
    expect(html).toMatch(/disabled=""[^>]*>Analyse en cours…/);
    expect(html).not.toContain('%');
  });
  it('interrompue : dit pourquoi et propose de relancer ; terminée : revient au repos', ()=>{
    const failed=renderToStaticMarkup(<LaunchCard project={{name:'Iam'}} latest={latest} count={7} run={run('failed', 'Dépôt illisible.')} canAnalyze onAnalyze={noop}/>);
    expect(failed).toContain('Analyse interrompue');
    expect(failed).toContain('Dépôt illisible.');
    expect(failed).toContain('Relancer l’analyse');
    expect(renderToStaticMarkup(<LaunchCard project={{name:'Iam'}} latest={latest} count={8} run={run('done')} canAnalyze onAnalyze={noop}/>))
      .toContain('Analyser Iam maintenant');
  });
});
