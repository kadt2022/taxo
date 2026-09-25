import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {gaps, MiniaView, place, type MiniaAnswer} from './minia';

const answer:MiniaAnswer={status:'ANSWERED', question:'Pourquoi cette route n’est plus publique ?', commit:'b'.repeat(40),
  parent:'a'.repeat(40), model:{configured:true, provider:'ollama', model:'qwen2.5:3b'},
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
    const all=gaps({...answer, not_interpreted:['file:A'], failures:['e : boom'], facts_not_sent:3, rejected_citations:['F9']});
    expect(all).toEqual(['Le motif métier n’est pas connu.', 'Zones non interprétées par Taxo : file:A.',
      'Évaluateurs en échec : e : boom.', '3 faits n’ont pas été transmis à Minia (limite de taille).',
      'Références inventées par Minia et écartées : F9.']);
    expect(gaps({...answer, unknown:''})).toEqual([]);
  });
});

describe('MiniaView', ()=>{
  it('sépare le fait Taxo, l’interprétation et l’inconnu', ()=>{
    const html=renderToStaticMarkup(<MiniaView answer={answer}/>);
    expect(html).toContain('MINIA · ollama qwen2.5:3b');
    expect(html).toContain('route-pattern:/api/**');
    expect(html).toContain('Security.java:5-7');
    expect(html).toContain('non vérifiée');
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
    const html=renderToStaticMarkup(<MiniaView answer={{...answer, facts:[{...answer.facts[0], before:null, after:null, relation:null}]}}/>);
    expect(html).toContain('ASSERTION');
    expect(html).not.toContain('→');
  });
});
