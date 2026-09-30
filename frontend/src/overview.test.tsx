import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {analysedAt, AnalysisLimits, CardBar, CardIcon, gapsOf, panelKey, evaluationsOf, outcomeState, routeCounts, shortList, outcome, overviewCards, ProjectNav, ProjectOverview, sections, type EvaluationSummary, type Scan} from './overview';
import type {RouteRow} from './routes';
import {AnalysisDetails, EvaluationPanel, warningsOf} from './details';
import {label, reference, RELATIONS} from './vocabulary';

const snapshot={repository:'p-1', commit:'a'.repeat(40), mode:'COMMIT' as const};
const summary=(evaluator_id:string, extra:Partial<EvaluationSummary>={}):EvaluationSummary=>({
  execution_id:`exec-${evaluator_id}`, evaluator_id, producer_version:'0.1.0', status:'SUCCESS',
  started_at:'2026-09-25T10:00:00Z', finished_at:'2026-09-25T10:00:01Z', duration_seconds:1.2,
  fact_count:40, coverage_count:1, warning_count:0, relations:{}, coverage:[], snapshot, ...extra});
const inventory=summary('taxo.inventory', {relations:{CONTAINS:12, USES_TECHNOLOGY:2},
  coverage:[{coverage_type:'NOT_INTERPRETED', count:7, subjects:['file:a.bin']}]});
const git=summary('taxo.git', {relations:{HAS_COMMIT:1234, CHANGES:4000}});
const scan:Scan={id:'s1', created_at:'2026-09-25T10:00:02Z', files_count:753, snapshot,
  facts:[{technology:'Java', file:'pom.xml', method:'manifest'}, {technology:'React', file:'package.json', method:'manifest'},
    {technology:'Java', file:'App.java', method:'filename'}],
  evaluation_summary:inventory, evaluations:[inventory, git]};
const card=(value:Scan, id:string)=>overviewCards(value).find(item=>item.id===id)!;

describe('overviewCards', ()=>{
  it('présente six cartes, toujours dans le même ordre', ()=>{
    expect(overviewCards(scan).map(item=>item.id)).toEqual(['project','api','architecture','security','data','limits']);
  });
  it('décrit le projet à partir de ce que Taxo a produit', ()=>{
    expect(card(scan,'project')).toMatchObject({value:(753).toLocaleString('fr-CA'), unit:'fichiers analysés', state:'known'});
    expect(card(scan,'project').lines).toEqual([`${(1234).toLocaleString('fr-CA')} commits`, 'Java · React']);
    expect(card(scan,'project').link?.href).toBe('#historique');
    expect(card({...scan, files_count:1},'project').unit).toBe('fichier analysé');
    expect(card({...scan, evaluations:[{...inventory, status:'PARTIAL'}]},'project').state).toBe('partial');
    expect(card({...scan, evaluations:[inventory, {...git, status:'FAILED'}]},'project').lines).toContain('Historique Git : lecture échouée');
    expect(card({...scan, evaluations:[inventory, {...git, status:'FAILED'}]},'project').link).toBeUndefined();
    expect(card({...scan, facts:[], evaluations:[inventory]},'project').lines).toEqual([]);
    expect(card({id:'x', created_at:''},'project').value).toBe('0');
    expect(evaluationsOf({id:'x', created_at:''})).toEqual([]);
  });
  it('compte applications et modules sur la carte Projet quand la structure est lue', ()=>{
    const structure=summary('taxo.structure', {relations:{CONTAINS:5}});
    const boot=summary('taxo.spring-boot', {relations:{BUILT_FROM:2}});
    expect(card({...scan, evaluations:[inventory, structure, boot]},'project').lines[0]).toBe('2 applications · 5 modules');
    expect(card({...scan, evaluations:[inventory, structure, {...boot, status:'FAILED'}]},'project').lines[0]).toBe('5 modules');
  });
  it('ne transforme jamais une absence d’information en résultat', ()=>{
    for(const id of ['architecture','api','security','data'])expect(card(scan,id)).toMatchObject({value:'Non analysé', state:'unknown'});
    for(const id of ['architecture','api','security'])expect(card(scan,id).lines[0]).toContain('relancez l’analyse globale');
    expect(card(scan,'data').lines[0]).toContain('Rien n’est affirmé');
    expect(card(scan,'api').link).toBeUndefined();
  });
});

describe('carte API (TAXO-04)', ()=>{
  const spring=(extra:Partial<EvaluationSummary>)=>({...scan, evaluations:[inventory, git, summary('taxo.spring-api', extra)]});
  it('compte les routes relevées par l’évaluateur Spring', ()=>{
    expect(card(spring({relations:{HANDLED_BY:17}}),'api')).toMatchObject({value:'17', unit:'routes', state:'known'});
    expect(card(spring({relations:{HANDLED_BY:1}}),'api').unit).toBe('route');
    expect(card(spring({relations:{HANDLED_BY:17}}),'api').lines[0]).toContain('prouvée à la ligne');
    expect(card(spring({relations:{HANDLED_BY:17}}),'api').link?.href).toBe('#routes');
  });
  it('répartit les routes établies, avec réserve et qui peuvent manquer', ()=>{
    const counts={PROTECTED:3, PERMITS_ALL:1, NOT_INTERPRETED:1, NO_CONCLUSION:0, reserved:2, missing:1};
    const value=overviewCards(spring({relations:{HANDLED_BY:5}}), counts).find(item=>item.id==='api')!;
    expect(value.bar).toEqual([{label:'établies', count:3, tone:'ok'}, {label:'avec réserve', count:2, tone:'warn'},
      {label:'peut manquer', count:1, tone:'muted'}]);
    expect(value.lines).toEqual([]);
    expect(overviewCards(spring({relations:{HANDLED_BY:1}}), {...counts, reserved:0, missing:0}).find(item=>item.id==='api')!.bar)
      .toEqual([{label:'établie', count:1, tone:'ok'}, {label:'avec réserve', count:0, tone:'warn'}]);
    expect(overviewCards(spring({}), counts).find(item=>item.id==='api')!.bar).toBeUndefined();
  });
  it('dit une absence analysée, une analyse partielle ou en échec, sans rien deviner', ()=>{
    expect(card(spring({}),'api')).toMatchObject({value:'0', state:'known'});
    expect(card(spring({}),'api').lines[0]).toBe('Aucune route Spring MVC dans les sources Java.');
    expect(card(spring({status:'PARTIAL', relations:{HANDLED_BY:1}}),'api').state).toBe('partial');
    expect(card(spring({status:'FAILED'}),'api')).toMatchObject({value:'Non analysé', state:'failed'});
  });
});

describe('carte Architecture (TAXO-E1)', ()=>{
  const structure=(extra:Partial<EvaluationSummary>)=>summary('taxo.structure', extra);
  const boot=summary('taxo.spring-boot', {relations:{BUILT_FROM:2, SERVED_BY:30}});
  const with_=(...items:EvaluationSummary[])=>({...scan, evaluations:[inventory, git, ...items]});
  it('compte les modules, leurs dépendances et ce qui s’en construit', ()=>{
    const value=card(with_(structure({relations:{CONTAINS:18, DEPENDS_ON:37, BUILT_FROM:1}}), boot),'architecture');
    expect(value).toMatchObject({value:'18', unit:'modules', state:'known'});
    expect(value.lines).toEqual(['37 dépendances', '2 applications Spring Boot', '1 service compose', 'Lu dans les fichiers de build, sans rien exécuter.']);
    expect(value.link?.href).toBe('#details');
  });
  it('accorde au singulier et ignore une lecture Spring Boot échouée', ()=>{
    expect(card(with_(structure({relations:{CONTAINS:1, DEPENDS_ON:1}})),'architecture')).toMatchObject({value:'1', unit:'module'});
    expect(card(with_(structure({relations:{CONTAINS:1, DEPENDS_ON:1}})),'architecture').lines[0]).toBe('1 dépendance');
    expect(card(with_(structure({}), {...boot, status:'FAILED'}),'architecture').lines.join()).not.toContain('Spring Boot');
  });
  it('dit une lecture partielle ou en échec', ()=>{
    expect(card(with_(structure({status:'PARTIAL', relations:{CONTAINS:3}})),'architecture').state).toBe('partial');
    expect(card(with_(structure({status:'FAILED'})),'architecture')).toMatchObject({value:'Non analysé', state:'failed'});
  });
});

describe('carte Sécurité (TAXO-05)', ()=>{
  const spring=(extra:Partial<EvaluationSummary>)=>({...scan, evaluations:[inventory, git, summary('taxo.spring-security', extra)]});
  const row=(state:RouteRow['state'], gaps=0):RouteRow=>({endpoint:`endpoint:GET /${state}${gaps}`, verb:'GET', path:`/${state}`, state,
    handlers:[], applications:[], matched:[], rules:[], protections:[],
    gaps:Array.from({length:gaps}, ()=>({subject:'s', type:'NOT_INTERPRETED', reason:'r', evaluator:'e'}))});
  const counts=routeCounts({routes:[row('PROTECTED'), row('PROTECTED', 1), row('PERMITS_ALL'), row('NOT_INTERPRETED', 2), row('NO_CONCLUSION')],
    unestablished:[{subject:'x', type:'NOT_INTERPRETED', reason:'r', evaluator:'e'}]});
  it('compte les routes par état établi, et ce qui les rend incomplètes', ()=>{
    expect(counts).toEqual({PROTECTED:2, PERMITS_ALL:1, NOT_INTERPRETED:1, NO_CONCLUSION:1, reserved:2, missing:1});
    const value=overviewCards(spring({}), counts).find(item=>item.id==='security')!;
    expect(value).toMatchObject({value:'2', unit:'routes protégées', state:'known'});
    expect(value.lines).toEqual(['2 routes restent à déterminer.']);
    expect(overviewCards(spring({}), {...counts, NOT_INTERPRETED:0, NO_CONCLUSION:0}).find(item=>item.id==='security')!.lines).toEqual([]);
    expect(overviewCards(spring({}), {...counts, NOT_INTERPRETED:1, NO_CONCLUSION:0}).find(item=>item.id==='security')!.lines).toEqual(['1 route reste à déterminer.']);
    expect(value.bar?.map(item=>[item.label, item.count])).toEqual([['protégées',2], ['permitAll()',1], ['non interprétée',1], ['sans conclusion',1]]);
    expect(value.link).toEqual({href:'#routes', label:'Explorer la sécurité'});
  });
  it('sans le détail par route, ne compte que les règles lues', ()=>{
    expect(card(spring({relations:{AUTHORIZED_BY:3, PERMITS_ALL:2}}),'security')).toMatchObject({value:'5', unit:'règles de sécurité lues'});
    expect(card(spring({relations:{PERMITS_ALL:1}}),'security').unit).toBe('règle de sécurité lue');
    expect(card(spring({status:'PARTIAL'}),'security')).toMatchObject({value:'0', state:'partial'});
    expect(card(spring({status:'FAILED'}),'security')).toMatchObject({value:'Non analysé', state:'failed'});
  });
});

describe('limites de l’analyse', ()=>{
  const spring=summary('taxo.spring-api', {coverage:[{coverage_type:'NOT_INTERPRETED', count:9, subjects:['symbol:java:a.B']},
    {coverage_type:'READ_ERROR', count:1, subjects:['file:x.java']}, {coverage_type:'ANALYSED', count:40, subjects:[]}]});
  const limited={...scan, evaluations:[inventory, git, spring]};
  it('liste les zones non lues par analyseur, les plus nombreuses d’abord', ()=>{
    expect(gapsOf(limited).map(gap=>[gap.evaluator, gap.type, gap.count])).toEqual([
      ['taxo.spring-api','NOT_INTERPRETED',9], ['taxo.inventory','NOT_INTERPRETED',7], ['taxo.spring-api','READ_ERROR',1]]);
    expect(card(limited,'limits')).toMatchObject({value:'17', unit:'zones non interprétées', state:'known'});
    expect(card(limited,'limits').lines).toEqual(['chez 2 analyseurs, chacune avec sa raison.']);
    expect(card(limited,'limits').link?.href).toBe('#limites');
  });
  it('dit l’absence de zone et l’absence de couverture', ()=>{
    const clean={...scan, evaluations:[{...inventory, coverage:[]}]};
    expect(card(clean,'limits')).toMatchObject({value:'0', unit:'zone non interprétée'});
    expect(card({...scan, evaluations:undefined, evaluation_summary:undefined},'limits')).toMatchObject({value:'Non analysé', state:'unknown'});
    expect(renderToStaticMarkup(<AnalysisLimits scan={clean}/>)).toContain('Aucune zone non interprétée parmi ce que les analyseurs savent lire.');
    expect(renderToStaticMarkup(<AnalysisLimits scan={{id:'x', created_at:''}}/>)).toContain('ne détaille pas sa couverture');
  });
  it('montre chaque zone en clair, avec des exemples', ()=>{
    const html=renderToStaticMarkup(<AnalysisLimits scan={limited}/>);
    expect(html).toContain('id="limites"');
    expect(html).toContain('Endpoints Spring');
    expect(html).toContain('Illisible');
    expect(html).toContain('x.java');
    expect(html).toContain('+ 8 autres');
    expect(html).not.toContain('NOT_INTERPRETED');
  });
});

describe('shortList', ()=>{
  it('abrège une longue liste sans rien inventer', ()=>{
    expect(shortList(['A','B','C','D'])).toBe('A · B · C · D');
    expect(shortList(['A','B','C','D','E','F'])).toBe('A · B · C · D · +2 autres');
  });
});

describe('CardIcon', ()=>{
  it('reste décorative, avec une icône par défaut', ()=>{
    expect(renderToStaticMarkup(<CardIcon id="history"/>)).toContain('aria-hidden="true"');
    expect(renderToStaticMarkup(<CardIcon id="inconnue"/>)).toContain('<path d="M3 7a2');
  });
});

describe('outcome et sections', ()=>{
  it('résume l’analyse en une phrase', ()=>{
    expect(outcome(scan)).toBe('Analyse terminée');
    expect(outcome({...scan, evaluations:[inventory, {...git, status:'PARTIAL', warning_count:1}]})).toBe('Analyse terminée, en partie · 1 point à vérifier');
    expect(outcome({...scan, warnings:['manifeste illisible'], evaluations:[{...inventory, warning_count:1}, {...git, status:'FAILED', warning_count:1}]}))
      .toBe('Analyse terminée, une partie a échoué · 2 points à vérifier');
    expect(outcome({id:'old', created_at:'', warnings:['a','a','b']})).toBe('Analyse terminée · 2 points à vérifier');
  });
  it('donne la tonalité du résultat', ()=>{
    expect(outcomeState(scan)).toBe('ok');
    expect(outcomeState({...scan, evaluations:[inventory, {...git, status:'PARTIAL'}]})).toBe('partial');
    expect(outcomeState({...scan, evaluations:[inventory, {...git, status:'FAILED'}]})).toBe('failed');
  });
  it('ne propose que les sections réellement disponibles', ()=>{
    expect(sections(scan).map(item=>item.label)).toEqual(['Vue d’ensemble', 'Technologies', 'Limites', 'Routes', 'Historique']);
    expect(sections(undefined).map(item=>item.id)).toEqual(['historique']);
    const nav=renderToStaticMarkup(<ProjectNav scan={scan}/>);
    expect(nav).toContain('href="#historique"');
    expect(nav).not.toMatch(/Evaluator|Sécurité|Architecture/);
  });
});

describe('ProjectOverview', ()=>{
  it('présente le projet sans vocabulaire interne', ()=>{
    const html=renderToStaticMarkup(<ProjectOverview scan={scan} project={{name:'Démo'}}/>);
    expect(html).toContain('Vue d’ensemble');
    expect(html).toContain('<dd>Démo</dd>');
    expect(html).toContain('<code>aaaaaaaaaaaa</code>');
    expect(html).toContain('Java · React');
    expect(html).not.toMatch(/evaluator_id|execution_id|taxo\.git|NOT_INTERPRETED|HAS_COMMIT|fact_count|Faits/);
    expect(html).toContain('class="card card-unknown"');
    expect(html).toContain('<a class="card-link" href="#historique">Voir l’historique <span aria-hidden="true">→</span></a>');
    const failed=renderToStaticMarkup(<ProjectOverview scan={{...scan, evaluations:[{...inventory, status:'PARTIAL'}, git]}}/>);
    expect(failed).toContain('<span class="badge">En partie</span>');
    expect(failed).toContain('<dd>p-1</dd>');
  });
  it('dit un dossier de travail et une analyse sans instantané', ()=>{
    expect(renderToStaticMarkup(<ProjectOverview scan={{...scan, snapshot:{...snapshot, mode:'WORKING_TREE'}}}/>)).toContain('dossier de travail');
    expect(analysedAt({id:'x', created_at:''})).toEqual({commit:'', working:false, date:''});
    expect(renderToStaticMarkup(<ProjectOverview scan={{id:'x', created_at:''}} pending={['taxo.inventory']}/>)).toContain('Nouvelle analyse en cours');
  });
  it('dessine une répartition sans parts vides dans la barre', ()=>{
    const html=renderToStaticMarkup(<CardBar segments={[{label:'a', count:2, tone:'ok'}, {label:'b', count:0, tone:'warn'}]}/>);
    expect(html.match(/tone-warn/g)).toHaveLength(1);
    expect(html).toContain('flex-grow:2');
    expect(renderToStaticMarkup(<CardBar segments={[{label:'a', count:0, tone:'ok'}]}/>)).not.toContain('card-bar');
  });
});

describe('AnalysisDetails', ()=>{
  it('garde tous les détails techniques, repliés, avec leur libellé humain', ()=>{
    const html=renderToStaticMarkup(<AnalysisDetails scan={{...scan, warnings:['Fichier illisible : x', 'Fichier illisible : x']}}/>);
    expect(html).toMatch(/^<details class="analysis-details" id="details"><summary>Détails de l’analyse<\/summary>/);
    for(const text of ['exec-taxo.inventory', 'exec-taxo.git', 'taxo.inventory', 'Historique Git', 'Inventaire du code',
      'Non analysé par Taxo', 'NOT_INTERPRETED', 'Fichiers modifiés', 'CHANGES', 'Éléments identifiés', 'Points à vérifier', 'Terminée'])
      expect(html).toContain(text);
    expect(html.match(/Fichier illisible : x/g)).toHaveLength(1);
  });
  it('explique chaque avertissement par l’évaluateur qui l’a émis, sans doublon', ()=>{
    const partial={...git, status:'PARTIAL', warning_count:7, warnings:['Historique au-delà de 50000 commits non lu']};
    expect(warningsOf({...scan, warnings:['ignoré'], evaluations:[inventory, partial]})).toEqual([
      {source:'Historique Git', text:'Historique au-delà de 50000 commits non lu'},
      {source:'Historique Git', text:'+ 6 autres avertissements'}]);
    const html=renderToStaticMarkup(<AnalysisDetails scan={{...scan, evaluations:[inventory, partial]}}/>);
    expect(html).toContain('<strong>Historique Git : </strong>Historique au-delà de 50000 commits non lu');
  });
  it('dit quand rien n’est détaillé', ()=>{
    const html=renderToStaticMarkup(<EvaluationPanel summary={summary('autre')}/>);
    expect(html).toContain('Aucune couverture détaillée disponible.');
    expect(html).toContain('Aucun fait produit.');
    expect(html).toContain('<h3>autre</h3>');
    expect(renderToStaticMarkup(<EvaluationPanel summary={{...inventory, coverage:[{coverage_type:'ANALYSED', count:1, subjects:['repository:p-1']}]}}/>)).toContain('>repository<');
  });
});

describe('vocabulaire', ()=>{
  it('traduit sans jamais perdre un terme inconnu', ()=>{
    expect(label(RELATIONS,'AUTHORED_BY')).toBe('Auteur');
    expect(label(RELATIONS,'NOUVELLE')).toBe('NOUVELLE');
  });
  it('dit une référence en clair', ()=>{
    const project={id:'p-1', name:'Demo'};
    expect(reference(null)).toBeNull();
    expect(reference('repository:p-1',project)).toBe('dépôt Demo');
    expect(reference('repository:autre')).toBe('dépôt autre');
    expect(reference('commit:'+'c'.repeat(40))).toBe('commit cccccccccccc');
    expect(reference('file:src/App.java')).toBe('src/App.java');
    expect(reference('person:pi@example.org')).toBe('pi@example.org');
    expect(reference('technology:react')).toBe('technologie react');
    expect(reference('inconnu:x')).toBe('inconnu:x');
    expect(reference('texte libre')).toBe('texte libre');
  });
});

describe('panelKey', ()=>{
  it('donne une clé distincte à chaque panneau d’un même projet', ()=>{
    expect(panelKey('ask','p1')).not.toBe(panelKey('history','p1'));
    expect(panelKey('ask','p1')).not.toBe(panelKey('ask','p2'));
  });
});
