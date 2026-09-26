import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {claimText, proofText, stepText, Statements, Trajectory, verdictText, type Statement, type TrajectoryStep} from './exploration';
import {MiniaProgress, reduceMinia, stageText, startMinia} from './minia-live';
import {SelectionAnswerView, type SelectionAnswer} from './query';

const sha='c'.repeat(40);
const confirmed:Statement={type:'claim', text:'Le commit modifie src/app.txt.', verdict:'CONFIRMED', reason:null,
  claim:{subject:`commit:${sha}`, relation:'CHANGES', object:'file:src/app.txt'},
  facts:[{ref:'F1', fact:{subject:`commit:${sha}`, relation:'CHANGES', object:'file:src/app.txt', qualifiers:{change:'MODIFIED'}}, evidence_count:1}],
  evidence:[{ref:'E1', fact:'F1', location:{object:`commit:${sha}`, method:'git.log'}}]};
const refuted:Statement={type:'claim', text:'Écrit par quelqu’un d’autre.', verdict:'REFUTED', reason:null,
  claim:{subject:`commit:${sha}`, relation:'AUTHORED_BY', object:'person:autre@x'}, facts:[]};
const unproven:Statement={type:'claim', text:'Protégé par R1.', verdict:'NOT_PROVEN', reason:'NOT_ANALYSED',
  claim:{subject:'endpoint:POST /items', relation:'PROTECTED_BY', object:'policy-rule:R1'}};
const malformed:Statement={type:'claim', text:'Mal formée.', verdict:null, claim:{subject:'x', relation:'Y'},
  error:{code:'INVALID_ARGUMENT', message:'Relation hors du vocabulaire : Y.'}};
const steps:TrajectoryStep[]=[
  {operation:'describe', arguments:{}, outcome:'OK', bytes:900, items:9, not_sent:[]},
  {operation:'find_facts', arguments:{relation:'CHANGES'}, outcome:'OK', bytes:4000, items:12, not_sent:[{what:'items', count:3, reason:'BUDGET'}]},
  {operation:'get_diff', arguments:{commit:sha, path:'a'}, outcome:'ERROR', bytes:300, error:{code:'NO_CONSENT', message:'non'}},
  {operation:'verify_claim', arguments:{subject:'s', relation:'CHANGES', object:'o'}, outcome:'OK', bytes:700, items:1, verdict:'CONFIRMED', reason:null}];

describe('verdicts', ()=>{
  it('dit le verdict de Taxo et sa raison', ()=>{
    expect(verdictText(confirmed as Extract<Statement,{type:'claim'}>)).toBe('Confirmée par Taxo');
    expect(verdictText(refuted as Extract<Statement,{type:'claim'}>)).toBe('Contredite par Taxo');
    expect(verdictText(unproven as Extract<Statement,{type:'claim'}>)).toBe('Non prouvée : aucun analyseur de Taxo ne couvre encore cette dimension');
    expect(verdictText(malformed as Extract<Statement,{type:'claim'}>)).toBe('Non vérifiable : Relation hors du vocabulaire : Y.');
    expect(verdictText({...malformed, error:undefined} as Extract<Statement,{type:'claim'}>)).toBe('Non vérifiable : Taxo n’a pas pu la vérifier.');
  });
  it('écrit l’affirmation vérifiée', ()=>{
    expect(claimText({subject:`commit:${sha}`, relation:'CHANGES', object:'file:src/app.txt'})).toBe('commit cccccccccccc modifie src/app.txt');
    expect(claimText({subject:'route-pattern:/api/**', relation:'PERMITS_ALL'})).toBe('routes /api/** est ouvert à tous');
  });
});

describe('preuves', ()=>{
  it('dit où se trouve chaque preuve', ()=>{
    expect(proofText({object:`commit:${sha}`, method:'git.log'})).toBe('commit cccccccccccc (git.log)');
    expect(proofText({path:'pom.xml', line_start:3, line_end:5, method:'maven'})).toBe('pom.xml:3-5 (maven)');
    expect(proofText({path:'pom.xml', line_start:3, line_end:3})).toBe('pom.xml:3');
    expect(proofText({path:'package.json'})).toBe('package.json');
    expect(proofText({})).toBe('emplacement non précisé');
  });
});

describe('trajectoire', ()=>{
  it('dit chaque opération, son issue et ce qui n’a pas été transmis', ()=>{
    expect(stepText(steps[0])).toBe('Ce que Taxo sait servir → 9 résultats · 900 octets');
    expect(stepText(steps[1])).toBe('Recherche de faits (relation CHANGES) → 12 résultats, 3 non transmis · 4000 octets');
    expect(stepText(steps[2])).toContain('→ refusé (NO_CONSENT)');
    expect(stepText(steps[3])).toContain('→ Confirmée par Taxo');
    expect(stepText({operation:'autre', arguments:{}, outcome:'OK', bytes:1, items:1})).toBe('autre → 1 résultat · 1 octets');
    expect(stepText({operation:'diff_facts', arguments:{commit:'c'}, outcome:'OK', bytes:9, items:2, ignored:['path', 'subject']}))
      .toBe('diff_facts (commit c) → 2 résultats · 9 octets · ignorés : path, subject');
    expect(renderToStaticMarkup(<Trajectory steps={[]}/>)).toBe('');
    const html=renderToStaticMarkup(<Trajectory steps={steps}/>);
    expect(html).toContain('4 opérations demandées à Taxo');
    expect(html).toContain('class="refused"');
  });
  it('se montre en direct pendant que Minia travaille', ()=>{
    let live=startMinia();
    live=reduceMinia(live, {type:'minia.operation', data:steps[1]});
    expect(live.trajectory).toEqual([steps[1]]);
    expect(renderToStaticMarkup(<MiniaProgress live={live}/>)).toContain('Recherche de faits (relation CHANGES)');
    expect(stageText({stage:'exploration', state:'running', label:'Minia interroge Taxo', count:2})).toBe('Minia interroge Taxo : 2 opérations');
    expect(stageText({stage:'exploration', state:'running', label:'Minia interroge Taxo', count:0})).toBe('Minia interroge Taxo');
    expect(stageText({stage:'verification', state:'done', label:'Taxo vérifie', count:1})).toBe('Taxo vérifie : 1 affirmation');
  });
});

describe('réponse en exploration', ()=>{
  const answer:SelectionAnswer={status:'ANSWERED', question:'Que change le dernier commit ?',
    request:{kind:'LATEST', text:'', count:1, commit:null, since:null, until:null}, model:{provider:'gemini', model:'gemini-3.8-flash'},
    commits:[], facts:[], answer:'', unknown:'', not_interpreted:[], facts_not_sent:0, rejected_citations:[], mode:'exploration',
    statements:[confirmed, refuted, unproven, malformed, {type:'interpretation', text:'Il ajusterait l’application.'},
      {type:'unknown', text:'Taxo ne dit pas pourquoi.'}], trajectory:steps};
  it('affiche chaque affirmation avec son verdict, jamais comme établie sans lui', ()=>{
    const html=renderToStaticMarkup(<SelectionAnswerView answer={answer}/>);
    expect(html).toContain('MINIA · gemini gemini-3.8-flash · exploration');
    expect(html).toContain('verdict verdict-confirmed');
    expect(html).toContain('verdict verdict-refuted');
    expect(html).toContain('verdict verdict-not-proven');
    expect(html).toContain('verdict verdict-none');
    expect(html).toContain('commit cccccccccccc modifie src/app.txt (MODIFIED)');
    expect(html).toContain('<span class="evidence">commit cccccccccccc (git.log)</span>');
    expect(html).toContain('Il ajusterait l’application.');
    expect(html).toContain('Taxo ne dit pas pourquoi.');
    expect(html).toContain('Chemin de Minia');
  });
  it('dit quand un bloc est vide', ()=>{
    const html=renderToStaticMarkup(<Statements statements={[]}/>);
    expect(html).toContain('Minia n’a fait aucune affirmation à vérifier.');
    expect(html).toContain('Minia ne propose aucune interprétation.');
    expect(html).toContain('Aucune limite signalée.');
  });
  it('dit pourquoi Minia est revenue au paquet', ()=>{
    const html=renderToStaticMarkup(<SelectionAnswerView answer={{...answer, mode:'paquet', statements:undefined,
      answer:'Un commit aurait changé src/app.txt.', fallback:'Minia ne progressait plus', trajectory:steps.slice(0,1)}}/>);
    expect(html).toContain('Exploration interrompue (Minia ne progressait plus)');
    expect(html).toContain('1 opération demandée à Taxo');
  });
});
