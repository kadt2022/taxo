import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {AnalysisLimits, CardBar, CardIcon, gapsOf, panelKey, evaluationsOf, routeCounts, shortList, overviewCards, ProjectOverview, type EvaluationSummary, type Scan} from './overview';
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
  it('présente six cartes, toujours dans le même ordre, avec Git au premier rang', ()=>{
    expect(overviewCards(scan).map(item=>item.id)).toEqual(['project','git','api','architecture','security','data']);
  });
  it('garde la carte Projet centrée sur l’inventaire', ()=>{
    expect(card(scan,'project')).toMatchObject({value:(753).toLocaleString('fr-CA'), unit:'fichiers analysés', state:'known'});
    expect(card(scan,'project').lines).toEqual(['2 technologies reconnues']);
    expect(card(scan,'project').link).toEqual({href:'#/technologies', label:'Voir les technologies'});
    expect(card({...scan, files_count:1},'project').unit).toBe('fichier analysé');
    expect(card({...scan, evaluations:[{...inventory, status:'PARTIAL'}]},'project').state).toBe('known');
    expect(card({...scan, facts:[], evaluations:[inventory]},'project').lines).toEqual([]);
    expect(card({id:'x', created_at:''},'project').value).toBe('0');
    expect(evaluationsOf({id:'x', created_at:''})).toEqual([]);
  });
  it('donne à Git sa propre carte', ()=>{
    expect(card(scan,'git')).toMatchObject({value:(1234).toLocaleString('fr-CA'), unit:'commits lus', state:'known'});
    expect(card(scan,'git').link).toEqual({href:'#/historique', label:'Voir l’historique'});
    expect(card({...scan, evaluations:[inventory]},'git')).toMatchObject({value:'Non analysé', state:'unknown'});
    expect(card({...scan, evaluations:[inventory, {...git, status:'FAILED'}]},'git')).toMatchObject({value:'Non analysé', state:'failed'});
  });
  it('ne transforme jamais une absence d’information en résultat', ()=>{
    for(const id of ['architecture','api','security','data'])expect(card(scan,id)).toMatchObject({value:'Non analysé', state:'unknown'});
    expect(card(scan,'api').link).toBeUndefined();
    expect(card(scan,'data').lines[0]).toContain('Aucun analyseur de données');
  });
});

describe('carte API (TAXO-04)', ()=>{
  const spring=(extra:Partial<EvaluationSummary>)=>({...scan, evaluations:[inventory, git, summary('taxo.spring-api', extra)]});
  it('montre seulement les routes effectivement relevées', ()=>{
    expect(card(spring({relations:{HANDLED_BY:17}}),'api')).toMatchObject({value:'17', unit:'routes relevées', state:'known'});
    expect(card(spring({relations:{HANDLED_BY:1}}),'api').unit).toBe('route relevée');
    expect(card(spring({relations:{HANDLED_BY:17}}),'api').lines).toEqual([]);
    expect(card(spring({relations:{HANDLED_BY:17}}),'api').link?.href).toBe('#/routes');
  });
  it('ne remet pas les réserves dans la carte de synthèse', ()=>{
    const counts={PROTECTED:3, PERMITS_ALL:1, NOT_INTERPRETED:1, NO_CONCLUSION:0, reserved:2, missing:1};
    const value=overviewCards(spring({relations:{HANDLED_BY:5}}), counts).find(item=>item.id==='api')!;
    expect(value).toMatchObject({value:'5', unit:'routes relevées'});
    expect(value.bar).toBeUndefined();
    expect(value.lines).toEqual([]);
  });
  it('dit zéro si zéro route a été relevée et distingue un échec', ()=>{
    expect(card(spring({}),'api')).toMatchObject({value:'0', unit:'route relevée', state:'known'});
    expect(card(spring({status:'PARTIAL', relations:{HANDLED_BY:1}}),'api').state).toBe('known');
    expect(card(spring({status:'FAILED'}),'api')).toMatchObject({value:'Non analysé', state:'failed'});
  });
});

describe('carte Architecture (TAXO-E1)', ()=>{
  const structure=(extra:Partial<EvaluationSummary>)=>summary('taxo.structure', extra);
  const boot=summary('taxo.spring-boot', {relations:{BUILT_FROM:2, SERVED_BY:30}});
  const with_=(...items:EvaluationSummary[])=>({...scan, evaluations:[inventory, git, ...items]});
  it('reste concise : modules, dépendances et applications', ()=>{
    const value=card(with_(structure({relations:{CONTAINS:18, DEPENDS_ON:37, BUILT_FROM:1}}), boot),'architecture');
    expect(value).toMatchObject({value:'18', unit:'modules détectés', state:'known'});
    expect(value.lines).toEqual(['37 dépendances', '2 applications Spring Boot']);
    expect(value.link).toEqual({href:'#/architecture', label:'Explorer l’architecture'});
  });
  it('accorde au singulier et ne transforme pas PARTIAL en badge éditorial', ()=>{
    expect(card(with_(structure({relations:{CONTAINS:1, DEPENDS_ON:1}})),'architecture')).toMatchObject({value:'1', unit:'module détecté'});
    expect(card(with_(structure({status:'PARTIAL', relations:{CONTAINS:3}})),'architecture').state).toBe('known');
    expect(card(with_(structure({status:'FAILED'})),'architecture')).toMatchObject({value:'Non analysé', state:'failed'});
  });
});

describe('carte Sécurité (TAXO-05)', ()=>{
  const spring=(extra:Partial<EvaluationSummary>)=>({...scan, evaluations:[inventory, git, summary('taxo.spring-security', extra)]});
  const row=(state:RouteRow['state'], gaps=0):RouteRow=>({endpoint:`endpoint:GET /${state}${gaps}`, verb:'GET', path:`/${state}${gaps}`, state,
    handlers:[], applications:[], matched:[], rules:[], protections:[],
    gaps:Array.from({length:gaps}, ()=>({subject:'s', type:'NOT_INTERPRETED', reason:'r', evaluator:'e'}))});
  const counts=routeCounts({routes:[row('PROTECTED'), row('PROTECTED', 1), row('PERMITS_ALL'), row('NOT_INTERPRETED', 2), row('NO_CONCLUSION')],
    unestablished:[{subject:'x', type:'NOT_INTERPRETED', reason:'r', evaluator:'e'}]});
  it('résume les routes examinées sans transformer les limites en résultat principal', ()=>{
    expect(counts).toEqual({PROTECTED:2, PERMITS_ALL:1, NOT_INTERPRETED:1, NO_CONCLUSION:1, reserved:2, missing:1});
    const value=overviewCards(spring({}), counts).find(item=>item.id==='security')!;
    expect(value).toMatchObject({value:'5', unit:'routes examinées', state:'known'});
    expect(value.lines).toEqual(['3 statuts de sécurité établis']);
    expect(value.bar).toBeUndefined();
    expect(value.link).toEqual({href:'#/securite', label:'Explorer la sécurité'});
  });
  it('sans détail par route, montre seulement les règles effectivement lues', ()=>{
    expect(card(spring({relations:{AUTHORIZED_BY:3, PERMITS_ALL:2}}),'security')).toMatchObject({value:'5', unit:'règles de sécurité lues'});
    expect(card(spring({relations:{PERMITS_ALL:1}}),'security').unit).toBe('règle de sécurité lue');
    expect(card(spring({status:'PARTIAL'}),'security')).toMatchObject({value:'0', state:'known'});
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
  });
  it('dit l’absence de zone et l’absence de couverture', ()=>{
    const clean={...scan, evaluations:[{...inventory, coverage:[]}]};
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
  it('résume les limites sous les cartes, sans en faire une septième carte', ()=>{
    const html=renderToStaticMarkup(<ProjectOverview scan={limited}/>);
    expect(html).toContain('17 limites signalées');
    expect(html).toContain('2 analyseurs concernés');
    expect(html).toContain('href="#/limites"');
    expect(html).not.toContain('aria-label="Limites"');
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

describe('ProjectOverview', ()=>{
  it('présente des cartes de résultat, sans badge « En partie » ni vocabulaire interne', ()=>{
    const html=renderToStaticMarkup(<ProjectOverview scan={scan}/>);
    expect(html).toContain('id="vue-ensemble"');
    expect(html).toContain('2 technologies reconnues');
    expect(html).toContain('Git');
    expect(html).not.toMatch(/En partie|evaluator_id|execution_id|taxo\.git|NOT_INTERPRETED|HAS_COMMIT|fact_count|Faits/);
    expect(html).toContain('class="card card-unknown"');
    expect(html).toContain('<a class="card-link" href="#/historique">Voir l’historique <span aria-hidden="true">→</span></a>');
    expect(renderToStaticMarkup(<ProjectOverview scan={{id:'x', created_at:''}} pending={['taxo.inventory']}/>)).toContain('aria-busy="true"');
  });
  it('garde le composant de répartition disponible pour les vues détaillées', ()=>{
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
