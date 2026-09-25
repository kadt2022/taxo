import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import {evaluationsOf, shortList, outcome, overviewCards, ProjectNav, ProjectOverview, sections, type EvaluationSummary, type Scan} from './overview';
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
  it('décrit le projet à partir de ce que Taxo a produit', ()=>{
    expect(card(scan,'technologies').value).toBe('Java · React');
    expect(card(scan,'project').value).toBe(`${(753).toLocaleString('fr-CA')} fichiers analysés`);
    expect(card(scan,'project').detail).toBe('Contenu du commit aaaaaaaaaaaa.');
    expect(card(scan,'history')).toMatchObject({value:`${(1234).toLocaleString('fr-CA')} commits analysés`, state:'known'});
  });
  it('ne transforme jamais une absence d’information en résultat', ()=>{
    for(const id of ['architecture','api','security'])expect(card(scan,id)).toMatchObject({value:'Non analysé', state:'unknown'});
    expect(card(scan,'security').detail).toContain('Rien n’est affirmé');
    const old:Scan={...scan, evaluations:undefined};
    expect(card(old,'history')).toMatchObject({value:'Non analysé', state:'unknown'});
    expect(card({...scan, evaluations:[inventory, {...git, status:'FAILED'}]},'history')).toMatchObject({value:'Non analysé', state:'failed'});
    expect(card({...scan, evaluations:[inventory, {...git, status:'PARTIAL'}]},'history').state).toBe('partial');
  });
  it('distingue « aucune technologie reconnue » d’une analyse absente', ()=>{
    expect(card({...scan, facts:[]},'technologies').value).toBe('Aucune technologie reconnue');
    expect(card({...scan, evaluations:[{...inventory, status:'PARTIAL'}]},'project').state).toBe('partial');
  });
  it('lit la source d’une analyse du dossier de travail ou ancienne', ()=>{
    expect(card({...scan, snapshot:{...snapshot, mode:'WORKING_TREE', dirty:true}},'project').detail)
      .toBe('Dossier de travail au commit aaaaaaaaaaaa, modifications non commitées incluses.');
    expect(card({...scan, snapshot:{...snapshot, mode:'WORKING_TREE'}},'project').detail).toBe('Dossier de travail au commit aaaaaaaaaaaa.');
    expect(card({id:'x', created_at:'', snapshot:null},'project')).toMatchObject({value:'0 fichiers analysés', detail:'Fichiers du dossier analysé.'});
    expect(evaluationsOf({id:'x', created_at:''})).toEqual([]);
  });
});

describe('shortList', ()=>{
  it('abrège une longue liste sans rien inventer', ()=>{
    expect(shortList(['A','B','C','D'])).toBe('A · B · C · D');
    expect(shortList(['A','B','C','D','E','F'])).toBe('A · B · C · D · +2 autres');
  });
  it('montre d’abord ce que Taxo sait', ()=>{
    expect(overviewCards(scan).map(item=>item.id)).toEqual(['technologies','project','history','architecture','api','security']);
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
  it('ne propose que les sections réellement disponibles', ()=>{
    expect(sections(scan).map(item=>item.label)).toEqual(['Vue d’ensemble', 'Technologies', 'Historique']);
    expect(sections(undefined).map(item=>item.id)).toEqual(['historique']);
    const nav=renderToStaticMarkup(<ProjectNav scan={scan}/>);
    expect(nav).toContain('href="#historique"');
    expect(nav).not.toMatch(/Evaluator|Sécurité|Architecture/);
  });
});

describe('ProjectOverview', ()=>{
  it('présente le projet sans vocabulaire interne', ()=>{
    const html=renderToStaticMarkup(<ProjectOverview scan={scan}/>);
    expect(html).toContain('Vue d’ensemble');
    expect(html).toContain('Java · React');
    expect(html).not.toMatch(/evaluator_id|execution_id|taxo\.git|NOT_INTERPRETED|HAS_COMMIT|fact_count|Faits/);
    expect(html).toContain('class="card card-unknown"');
    const failed=renderToStaticMarkup(<ProjectOverview scan={{...scan, evaluations:[inventory, {...git, status:'PARTIAL'}]}}/>);
    expect(failed).toContain('<span class="badge">En partie</span>');
  });
});

describe('AnalysisDetails', ()=>{
  it('garde tous les détails techniques, repliés, avec leur libellé humain', ()=>{
    const html=renderToStaticMarkup(<AnalysisDetails scan={{...scan, warnings:['Fichier illisible : x', 'Fichier illisible : x']}}/>);
    expect(html).toMatch(/^<details class="analysis-details"><summary>Détails de l’analyse<\/summary>/);
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
    const project={id:'p-1', name:'Takibo'};
    expect(reference(null)).toBeNull();
    expect(reference('repository:p-1',project)).toBe('dépôt Takibo');
    expect(reference('repository:autre')).toBe('dépôt autre');
    expect(reference('commit:'+'c'.repeat(40))).toBe('commit cccccccccccc');
    expect(reference('file:src/App.java')).toBe('src/App.java');
    expect(reference('person:pi@example.org')).toBe('pi@example.org');
    expect(reference('technology:react')).toBe('technologie react');
    expect(reference('inconnu:x')).toBe('inconnu:x');
    expect(reference('texte libre')).toBe('texte libre');
  });
});
