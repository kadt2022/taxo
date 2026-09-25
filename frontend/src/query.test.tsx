import {renderToStaticMarkup} from 'react-dom/server';
import {describe as group, expect, it, vi} from 'vitest';
import {actions, askInit, when, AskTaxo, describe, factLine, outcome, queryPath, SelectionAnswerView, SelectionView, submitWith, track,
  type Selection, type SelectionAnswer} from './query';

const request={kind:'LATEST' as const, text:'3 derniers', count:3, commit:null, since:null, until:null};
const fact={subject:'commit:'+'b'.repeat(40), relation:'CHANGES', object:'file:docs/done/R1.md',
  qualifiers:{change:'RENAMED', old_path:'docs/backlog/R1.md'}, produced_by:{producer_id:'taxo.git', producer_version:'0.1.0'}};
const selection:Selection={status:'SELECTED', request, analysis:{id:'s1', created_at:'2026-09-25T10:00:00Z'}, total_commits:42,
  commits:[{sha:'b'.repeat(40), authored_at:'2026-09-25T09:00:00+00:00', subject:'R1 termine'}], facts:[fact], not_interpreted:[]};
const answer:SelectionAnswer={status:'ANSWERED', question:'Résume les 3 derniers commits', request,
  model:{provider:'ollama', model:'qwen2.5:3b'}, commits:selection.commits, facts:[{...fact, ref:'F1'}],
  answer:'Le récit R1 aurait été terminé.', unknown:'', not_interpreted:[], facts_not_sent:0, rejected_citations:[]};

group('describe', ()=>{
  it('dit la sélection en clair', ()=>{
    expect(describe(request)).toBe('3 derniers commits');
    expect(describe({...request, count:1, since:'2026-09-01'})).toBe('1 dernier commit depuis le 2026-09-01');
    expect(describe({...request, kind:'COMMIT', commit:'5b9022b'})).toBe('commit 5b9022b');
    expect(describe({...request, kind:'PERIOD', since:'2026-09-01', until:'2026-09-10'})).toBe('commits du 2026-09-01 au 2026-09-10');
    expect(describe({...request, kind:'PERIOD', until:'2026-09-10'})).toBe('commits jusqu’au 2026-09-10');
    expect(describe({...request, kind:'GLOBAL'})).toBe('analyse globale du projet');
  });
});

group('outcome et factLine', ()=>{
  it('explique une sélection vide ou impossible', ()=>{
    expect(outcome(selection)).toBeNull();
    expect(outcome({...selection, commits:[]})).toBe('Aucun commit ne correspond à cette sélection.');
    expect(outcome({...selection, status:'GLOBAL'})).toContain('analyse globale');
    expect(outcome({...selection, status:'AUTRE'})).toBe('AUTRE');
  });
  it('écrit un fait Git en une ligne', ()=>{
    expect(factLine(fact)).toBe(`commit:${'b'.repeat(40)} CHANGES file:docs/done/R1.md (RENAMED, depuis docs/backlog/R1.md)`);
    expect(factLine({subject:'repository:p', relation:'HAS_COMMIT', object:'commit:c'})).toBe('repository:p HAS_COMMIT commit:c');
  });
});

group('when', ()=>{
  it('rend une date lisible, et laisse une valeur illisible telle quelle', ()=>{
    expect(when('2026-09-25T09:00:00+00:00')).toBe(new Date('2026-09-25T09:00:00Z').toLocaleString('fr-CA'));
    expect(when('inconnue')).toBe('inconnue');
    expect(when(undefined)).toBe('');
  });
});

group('vues', ()=>{
  it('montre les commits choisis et d’où viennent les faits', ()=>{
    const html=renderToStaticMarkup(<SelectionView result={selection}/>);
    expect(html).toContain('REQUÊTE · 3 derniers commits');
    expect(html).toContain('bbbbbbbbbbbb');
    expect(html).toContain('1 faits sélectionnés parmi un historique de 42 commits');
    const empty=renderToStaticMarkup(<SelectionView result={{...selection, status:'GLOBAL', commits:[], facts:[], total_commits:null, not_interpreted:['commit:x']}}/>);
    expect(empty).not.toContain('<table');
    expect(empty).toContain('Non interprété par Taxo : commit:x.');
  });
  it('sépare les faits de Taxo, l’interprétation et l’inconnu', ()=>{
    const html=renderToStaticMarkup(<SelectionAnswerView answer={answer}/>);
    expect(html).toContain('MINIA · ollama qwen2.5:3b · 3 derniers commits');
    expect(html).toContain('taxo.git');
    expect(html).toContain('non vérifiée');
    expect(html).toContain('Aucune limite signalée.');
    const nothing=renderToStaticMarkup(<SelectionAnswerView answer={{...answer, status:'NEEDS_SELECTION', facts:[], answer:'',
      unknown:'Précisez.', facts_not_sent:2, rejected_citations:['F9'], model:{provider:null, model:null}}}/>);
    expect(nothing).toContain('Aucun fait de Taxo n’appuie cette réponse.');
    expect(nothing).toContain('Minia ne propose aucune interprétation.');
    expect(nothing).toContain('2 faits n’ont pas été transmis');
    expect(nothing).toContain('écartées : F9.');
  });
  it('présente le panneau sans rien interroger d’avance', ()=>{
    const run=vi.fn();
    const html=renderToStaticMarkup(<AskTaxo base="/projects/p" request={run}/>);
    expect(html).toContain('id="taxo-query"');
    expect(html).toContain('value=""');
    expect(run).not.toHaveBeenCalled();
  });
});

group('actions', ()=>{
  it('construit la requête et la question', ()=>{
    expect(queryPath('/projects/p', '3 derniers commits')).toBe('/projects/p/query?q=3+derniers+commits');
    expect(JSON.parse(askInit('Pourquoi ?').body as string)).toEqual({question:'Pourquoi ?'});
  });
  it('sélectionne, puis fait expliquer la sélection', async ()=>{
    const run=vi.fn().mockResolvedValueOnce(selection).mockResolvedValueOnce(answer);
    const set={setBusy:vi.fn(), setError:vi.fn(), setResult:vi.fn(), setAnswer:vi.fn()};
    const {select, explain}=actions('/projects/p', '3 derniers', run, set);
    const event={preventDefault:vi.fn()};
    await submitWith(select)(event);
    expect(event.preventDefault).toHaveBeenCalled();
    expect(run).toHaveBeenCalledWith('/projects/p/query?q=3+derniers');
    expect(set.setResult).toHaveBeenCalledWith(selection);
    expect(set.setAnswer).toHaveBeenCalledWith(null);
    await explain();
    expect(run.mock.calls[1][0]).toBe('/projects/p/ask');
    expect(set.setAnswer).toHaveBeenLastCalledWith(answer);
    expect(set.setBusy.mock.calls.map(call=>call[0])).toEqual([true, false, true, false]);
  });
  it('montre l’erreur sans rester occupé', async ()=>{
    const set={setBusy:vi.fn(), setError:vi.fn(), setValue:vi.fn()};
    await track(()=>Promise.reject(new Error('NO_ANALYSIS : lancez-la')), set);
    expect(set.setError).toHaveBeenLastCalledWith('NO_ANALYSIS : lancez-la');
    expect(set.setValue).not.toHaveBeenCalled();
    expect(set.setBusy).toHaveBeenLastCalledWith(false);
  });
});
