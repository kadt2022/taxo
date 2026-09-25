import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {gaps, gitFile, MiniaView, named, place, sentence, type MiniaAnswer} from './minia';

const answer:MiniaAnswer={status:'ANSWERED', question:'Pourquoi cette route n’est plus publique ?', commit:'b'.repeat(40),
  parent:'a'.repeat(40), project:{id:'p-1', name:'Takibo-IAM'}, files_not_sent:0,
  git:{sha:'b'.repeat(40), parent:'a'.repeat(40), author:'Pi', authored_at:'2026-09-25T00:00:00Z', subject:'Termine SEC-TMS-01',
    files:[{status:'RENAMED', path:'docs/terminer/R1.md', old_path:'docs/backlog/R1.md'}, {status:'MODIFIED', path:'Security.java', old_path:null}]},
  model:{configured:true, provider:'ollama', model:'qwen2.5:3b'},
  facts:[{ref:'F1', evaluator_id:'taxo.inventory', change:'MODIFIED', kind:'ASSERTION', subject:'route-pattern:/api/**',
    relation:'AUTHORIZED_BY', status:'OBSERVED', before:'symbol:permitAll', after:'symbol:hasRole',
    evidence_before:[{path:'Security.java', line_start:5, line_end:5}], evidence_after:[{path:'Security.java', line_start:5, line_end:7}]}],
  answer:'L’équipe aurait restreint l’accès.', unknown:'Le motif métier n’est pas connu.', not_interpreted:[], failures:[],
  facts_not_sent:0, rejected_citations:[]};

describe('place', ()=>{
  it('situe une preuve au fichier, à la ligne ou sur une plage', ()=>{
    expect(place({path:'a.json'})).toBe('a.json');
    expect(place({path:'A.java', line_start:5, line_end:5})).toBe('A.java:5');
    expect(place({path:'A.java', line_start:5})).toBe('A.java:5');
    expect(place({path:'A.java', line_start:5, line_end:7})).toBe('A.java:5-7');
  });
});

describe('gaps', ()=>{
  it('ajoute aux inconnues de Minia les limites que Taxo connaît', ()=>{
    const all=gaps({...answer, not_interpreted:['file:A'], failures:['e : boom'], files_not_sent:4, facts_not_sent:3, rejected_citations:['F9']});
    expect(all).toEqual(['Le motif métier n’est pas connu.', 'Non analysé par Taxo : file:A.',
      'Analyses en échec : e : boom.', '4 fichiers du commit n’ont pas été transmis à Minia (limite de taille).',
      '3 faits n’ont pas été transmis à Minia (limite de taille).',
      'Références inventées par Minia et écartées : F9.']);
    expect(gaps({...answer, unknown:''})).toEqual([]);
  });
});

describe('named et gitFile', ()=>{
  it('désigne le dépôt par le nom du projet', ()=>{
    expect(named('repository:p-1', answer.project)).toBe('dépôt Takibo-IAM');
    expect(named('file:A', answer.project)).toBe('file:A');
    expect(named(null, answer.project)).toBeNull();
  });
  it('décrit un fichier comme Git, renommage compris', ()=>{
    expect(gitFile(answer.git.files[0])).toBe('docs/backlog/R1.md → docs/terminer/R1.md (renommé)');
    expect(gitFile({status:'UNKNOWN', path:'x', old_path:null})).toBe('x (UNKNOWN)');
  });
});

describe('MiniaView', ()=>{
  it('montre toujours ce que Git sait du commit', ()=>{
    const html=renderToStaticMarkup(<MiniaView answer={{...answer, facts:[], git:{...answer.git, files:[]}}}/>);
    expect(html).toContain('bbbbbbbbbbbb');
    expect(html).toContain('Pi');
    expect(html).toContain('Termine SEC-TMS-01');
    expect(html).toContain('aucun');
  });
  it('nomme le type de changement et le projet', ()=>{
    const html=renderToStaticMarkup(<MiniaView answer={{...answer, facts:[{...answer.facts[0], change:'REMOVED', subject:'repository:p-1'}]}}/>);
    expect(html).toContain('<strong>Retiré</strong>');
    expect(html).toContain('dépôt Takibo-IAM');
    expect(html).toContain('docs/backlog/R1.md → docs/terminer/R1.md (renommé)');
  });
  it('sépare le fait Taxo, l’interprétation et l’inconnu', ()=>{
    const html=renderToStaticMarkup(<MiniaView answer={answer}/>);
    expect(html).toContain('MINIA · ollama qwen2.5:3b');
    expect(html).toContain('route-pattern:/api/**');
    expect(html).toContain('Security.java:5-7');
    expect(html).toContain('non vérifié');
    expect(html).toContain('Ce que Taxo sait');
    expect(html).toContain('Ce que Minia en déduit');
    expect(html).toContain('Ce que Taxo ne sait pas');
    expect(html).toContain('Inventaire du code');
    expect(html).toContain('L’équipe aurait restreint l’accès.');
    expect(html).toContain('Le motif métier n’est pas connu.');
  });
  it('dit quand rien n’appuie la réponse ni ne la limite', ()=>{
    const html=renderToStaticMarkup(<MiniaView answer={{...answer, status:'TAXO_KNOWS_NOTHING', facts:[], answer:'', unknown:'',
      model:{configured:true, provider:null, model:null}}}/>);
    expect(html).toContain('Aucun fait de Taxo n’appuie cette réponse.');
    expect(html).toContain('Minia ne propose aucune interprétation.');
    expect(html).toContain('Aucune limite signalée.');
    expect(html).toContain('>MINIA<');
  });
  it('affiche un fait sans avant ni après', ()=>{
    const html=renderToStaticMarkup(<MiniaView answer={{...answer, git:{...answer.git, files:[]}, facts:[{...answer.facts[0], before:null, after:null, relation:null}]}}/>);
    expect(html).toContain('ASSERTION');
    expect(html).not.toContain('→');
  });
});

describe('sentence', ()=>{
  it('dit le fait en clair, la preuve technique restant disponible', ()=>{
    const fact=answer.facts[0];
    expect(sentence(fact, answer.project)).toBe('routes /api/** est autorisé par : symbole permitAll → symbole hasRole');
    expect(sentence({...fact, subject:'repository:p-1', relation:'USES_TECHNOLOGY', before:null, after:'technology:react'}, answer.project))
      .toBe('dépôt Takibo-IAM utilise technologie react');
    expect(sentence({...fact, relation:'DECLARED_BY', before:'file:pom.xml', after:null}, answer.project))
      .toBe('routes /api/** est déclarée dans pom.xml');
    expect(sentence({...fact, relation:null, kind:'ASSERTION', before:null, after:null}, answer.project)).toBe('routes /api/** assertion');
    const html=renderToStaticMarkup(<MiniaView answer={answer}/>);
    expect(html).toContain('<summary>Preuve</summary>');
    expect(html).toContain('AUTHORIZED_BY');
  });
});
