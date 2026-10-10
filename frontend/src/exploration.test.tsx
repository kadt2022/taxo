import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {claimText, limitText, proofText, stepText, Statements, Trajectory, verdictText, type Statement, type TrajectoryStep} from './exploration';
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
    expect(html).not.toContain('verdict verdict-none');
    expect(html).toContain('Minia : « Mal formée. »');
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
    expect(html).toContain('Aucune limite signalée par Taxo.');
  });
  it('dit pourquoi Minia est revenue au paquet', ()=>{
    const html=renderToStaticMarkup(<SelectionAnswerView answer={{...answer, mode:'paquet', statements:undefined,
      answer:'Un commit aurait changé src/app.txt.', fallback:'Minia ne progressait plus', trajectory:steps.slice(0,1)}}/>);
    expect(html).toContain('Exploration interrompue (Minia ne progressait plus)');
    expect(html).toContain('1 opération demandée à Taxo');
  });
});

describe('frontière preuve / texte libre (MINIA-11)', ()=>{
  // Le scénario à interdire : une phrase fausse de Minia, jointe à un triplet vrai.
  const catastrophe:Statement={type:'claim', text:'Ce commit supprime l’authentification.',
    claim:{subject:`commit:${'c'.repeat(40)}`, relation:'AUTHORED_BY', object:'person:kadt2022@gmail.com'},
    verdict:'CONFIRMED', reason:null, facts:[], evidence:[]};
  const html=renderToStaticMarkup(<Statements statements={[catastrophe, {type:'unknown', text:'Le risque exact n’est pas établi.'}]}
    limits={['Non analysé par Taxo : file:A.']}/>);
  const green=html.slice(html.indexOf('minia-block fact'), html.indexOf('minia-block interpretation'));
  const blue=html.slice(html.indexOf('minia-block interpretation'), html.indexOf('minia-block unknown'));
  const orange=html.slice(html.indexOf('minia-block unknown'));

  it('ne met jamais une phrase de Minia à côté d’un badge vert', ()=>{
    expect(green).toContain('Confirmée par Taxo');
    expect(green).not.toContain('supprime l’authentification');
    expect(green).toContain(`Commit ${'c'.repeat(12)} a pour auteur kadt2022@gmail.com.`);
  });
  it('montre exactement ce que Taxo a vérifié : sujet, relation, objet, verdict', ()=>{
    for(const value of [`commit:${'c'.repeat(40)}`, 'AUTHORED_BY', 'person:kadt2022@gmail.com', 'CONFIRMED'])
      expect(green).toContain(`<code>${value}</code>`);
    expect(green).toContain('Aucune preuve : Taxo n’a établi aucun fait');
  });
  it('range tout le texte de Minia dans la colonne non vérifiée', ()=>{
    expect(blue).toContain('non vérifié');
    expect(blue).toContain('Minia : « Ce commit supprime l’authentification. »');
    expect(blue).toContain('Taxo n’a vérifié que : Commit');
    expect(blue).toContain('Minia dit ne pas savoir :</em> Le risque exact n’est pas établi.');
  });
  it('ne laisse dans la colonne de Taxo que ce que Taxo constate', ()=>{
    expect(orange).toContain('Non analysé par Taxo : file:A.');
    expect(orange).not.toContain('Le risque exact');
  });
});

describe('affirmation non vérifiable (MINIA-11)', ()=>{
  it('reste un texte de Minia, jamais reformulée par Taxo en vert', ()=>{
    const unchecked:Statement={type:'claim', text:'Ce commit désactive la sécurité.', verdict:null,
      claim:{subject:`commit:${'d'.repeat(40)}`, relation:'INVENTED', object:'file:A.java'},
      error:{code:'INVALID_ARGUMENT', message:'Relation hors du vocabulaire : INVENTED.'}};
    const html=renderToStaticMarkup(<Statements statements={[unchecked]}/>);
    const green=html.slice(html.indexOf('minia-block fact'), html.indexOf('minia-block interpretation'));
    const blue=html.slice(html.indexOf('minia-block interpretation'), html.indexOf('minia-block unknown'));
    expect(green).toContain('Minia n’a fait aucune affirmation à vérifier.');
    expect(green).not.toContain('d'.repeat(12));
    expect(green).not.toContain('Non vérifiable');
    expect(blue).toContain('Minia : « Ce commit désactive la sécurité. »');
    expect(blue).toContain('Non vérifiable : Relation hors du vocabulaire : INVENTED.');
  });
});

describe('confirmation par déduction (TAXO-05)', ()=>{
  const endpoint='endpoint:GET /api/v1/users';
  const protectedClaim:Statement={type:'claim', text:'Cette route est protégée.', verdict:'CONFIRMED', reason:null,
    claim:{subject:endpoint, relation:'PROTECTED_BY', object:'policy-rule:authenticated()'},
    facts:[{ref:'F1', evidence_count:1, fact:{subject:endpoint, relation:'PROTECTED_BY', object:'policy-rule:authenticated()',
      status:'INFERRED', derivation:{rule:'spring-security.route-authorization-applies',
        premises:[`MATCHED_BY : ${endpoint} -> route-pattern:/**`, 'AUTHORIZED_BY : route-pattern:/** -> authenticated()'],
        counter_examples_checked:['ligne 12 : POST /login -> permitAll() : ne correspond pas'],
        known_gaps:['les rôles et autorités des utilisateurs sont des données, hors du code']}}}],
    evidence:[{ref:'E1', fact:'F1', location:{path:'SecurityConfig.java', line_start:14, line_end:14}}]};
  const html=renderToStaticMarkup(<Statements statements={[protectedClaim]}/>);

  it('dit qu’une confirmation repose sur une déduction, pas sur une observation', ()=>{
    expect(verdictText(protectedClaim as Extract<Statement,{type:'claim'}>)).toBe('Confirmée par Taxo, par déduction');
    expect(verdictText(confirmed as Extract<Statement,{type:'claim'}>)).toBe('Confirmée par Taxo');
  });
  it('montre les prémisses, ce qui a été écarté et les limites connues', ()=>{
    expect(html).toContain('spring-security.route-authorization-applies');
    expect(html).toContain('AUTHORIZED_BY : route-pattern:/** -&gt; authenticated()');
    expect(html).toContain('POST /login -&gt; permitAll() : ne correspond pas');
    expect(html).toContain('hors du code');
    expect(html).toContain('Route GET /api/v1/users est protégé par règle authenticated().');
  });
  it('lit un fait sans objet (PERMITS_ALL)', ()=>{
    const open:Statement={...protectedClaim, claim:{subject:'route-pattern:/public/**', relation:'PERMITS_ALL'},
      facts:[{ref:'F2', evidence_count:0, fact:{subject:'route-pattern:/public/**', relation:'PERMITS_ALL', status:'OBSERVED'}}]};
    expect(renderToStaticMarkup(<Statements statements={[open]}/>)).toContain('routes /public/** est ouvert à tous');
  });
});

describe('limites jointes au verdict (TAXO-MINIA-SEC-01)', ()=>{
  const limited={type:'claim', text:'La route exige seulement une authentification.', verdict:'CONFIRMED', reason:null,
    claim:{subject:'endpoint:GET /api/items', relation:'PROTECTED_BY', object:'policy-rule:authenticated()'}, facts:[], evidence:[],
    limits:[{subject:'endpoint:GET /api/items', type:'NOT_INTERPRETED', producer:'taxo.spring-security',
      reason:'sécurité de méthode non interprétée (@PreAuthorize)'}]} as Extract<Statement,{type:'claim'}>;
  it('dit qu’une confirmation a des limites, et lesquelles', ()=>{
    expect(verdictText(limited)).toBe('Confirmée par Taxo, avec limites');
    expect(limitText(limited.limits![0])).toContain('sécurité de méthode non interprétée (@PreAuthorize)');
    const html=renderToStaticMarkup(<Statements statements={[limited]}/>);
    expect(html).toContain('verdict-limited');
    expect(html).toContain('Taxo n’a pas lu : sécurité de méthode non interprétée (@PreAuthorize)');
  });
  it('une limite sans raison reste dite, selon son type', ()=>{
    expect(limitText({...limited.limits![0], reason:null})).toContain('zone non interprétée');
    expect(limitText({...limited.limits![0], type:'READ_ERROR', reason:null})).toContain('fichier illisible');
  });
  it('une limite non transmise faute de place garde la confirmation limitée', ()=>{
    const unsent={...limited, limits:[], not_sent:[{what:'limits', count:2, reason:'BUDGET'}]};
    expect(verdictText(unsent)).toBe('Confirmée par Taxo, avec limites');
    const html=renderToStaticMarkup(<Statements statements={[unsent]}/>);
    expect(html).toContain('verdict-limited');
    expect(html).toContain('Taxo connaît 2 autres limites, non transmises faute de place.');
  });
  it('une confirmation sans limite reste une confirmation', ()=>{
    expect(verdictText({...limited, limits:[]})).toBe('Confirmée par Taxo');
  });
});
