import {describe, expect, it} from 'vitest';
import type {Boundary} from './protocol';
import {countText, factText, knowledgeText, nodeMarks, nodeName, notSentText, scopeText, selectionText, verb, viewText} from './sentences';

const SELECTIONS=['DEPTH', 'NOT_REACHED', 'NODES', 'EDGES', 'WORK', 'BYTES', 'FANOUT'];
const KNOWLEDGE=['NO_ANALYZER', 'ANALYSIS_INCOMPLETE', 'NOT_ANALYSED', 'LANGUAGES_UNKNOWN', 'LOCAL_COVERAGE_NOT_READ',
  'NOT_INTERPRETED', 'READ_ERROR'];
const cut=(reason:string, count:Boundary['count']={kind:'UNKNOWN'}):Boundary=>({nature:'SELECTION', node:'module:a', reason, count});
const gap=(reason:string):Boundary=>({nature:reason==='NO_ANALYZER'?'CONTEXT':'KNOWLEDGE', scope:'NODE', node:'module:a',
  relation:'HANDLED_BY', reason, producer:'taxo.spring-api', subject:'file:A.java', languages:['Kotlin'], count:{kind:'UNKNOWN'}});

describe('ce que l’explorateur dit', ()=>{
  it('a une phrase pour chaque raison, jamais la raison brute', ()=>{
    for(const reason of SELECTIONS)expect(selectionText(cut(reason))).not.toContain(reason);
    for(const reason of KNOWLEDGE)expect(knowledgeText(gap(reason))).not.toContain(reason);
  });

  it('ne dit jamais de pourcentage, ni « complet »', ()=>{
    const said=[...SELECTIONS.map(reason=>selectionText(cut(reason, {kind:'AT_LEAST', value:3}))),
      ...KNOWLEDGE.map(reason=>knowledgeText(gap(reason))), scopeText(['HANDLED_BY'], 'BOTH', 3), viewText(VIEW), viewText({...VIEW, selection:{}})];
    for(const sentence of said){
      expect(sentence).not.toMatch(/%|complet/i);
    }
  });

  it('qualifie chaque décompte : rien quand il est inconnu', ()=>{
    expect(countText({kind:'UNKNOWN'})).toBe('');
    expect(countText({kind:'AT_LEAST', value:1})).toBe('au moins 1');
    expect(countText({kind:'EXACT', value:12})).toBe('12');
    expect(selectionText({...cut('EDGES', {kind:'AT_LEAST', value:1}), relation:'DEPENDS_ON', direction:'INCOMING'}))
      .toBe('Suite disponible : limite de liens atteinte (au moins 1) · dépend de, entrant');
  });

  it('affiche brut un type ou une relation que le portail ne connaît pas, sans planter', ()=>{
    expect(nodeName('gizmo:x')).toBe('gizmo:x');
    expect(verb('TELEPORTS_TO')).toBe('TELEPORTS_TO');
    expect(factText({subject:'gizmo:x', relation:'TELEPORTS_TO', object:'module:y'})).toBe('gizmo:x TELEPORTS_TO module y');
    expect(selectionText(cut('SOMETHING_NEW'))).toContain('SOMETHING_NEW');
  });

  it('marque un nœud par ce qui le concerne seulement', ()=>{
    const node={reference:'module:a', level:1, known:true, expanded:false};
    expect(nodeMarks(node, cut('DEPTH'), [])).toEqual(['non développé']);
    expect(nodeMarks(node, {...cut('EDGES', {kind:'AT_LEAST', value:1}), continuation:'t'}, [gap('NOT_INTERPRETED'), gap('NO_ANALYZER')]))
      .toEqual(['suite disponible (au moins 1)', 'zone non lue', 'aucun analyseur pour un pas']);
    expect(nodeMarks({...node, reference:'module:b'}, undefined, [gap('NOT_INTERPRETED')])).toEqual([]);
    expect(nodeMarks({...node, known:false}, undefined, [])).toEqual(['inconnu de cette analyse']);
  });
});

const VIEW={nodes:[{reference:'module:a', level:0, known:true, expanded:true}, {reference:'module:b', level:1, known:true, expanded:false}],
  elements:[], selection:{'module:b':cut('DEPTH')}};

describe('l’état de la vue', ()=>{
  it('se dit sur toute la vue, pas sur la dernière Tuile reçue', ()=>{
    expect(viewText(VIEW)).toBe('0 élément, 2 nœuds. 1 nœud à développer ou à poursuivre.');
    expect(viewText({...VIEW, selection:{}})).toBe('0 élément, 2 nœuds. Aucune coupure : tout ce que les pas suivis atteignent depuis cette ancre est montré.');
  });
});

describe('ce qui n’a pas été transmis', ()=>{
  it('dit où le retrouver, en comptes', ()=>{
    expect(notSentText({what:'evidence_summary', count:3, reason:'BUDGET'})).toBe('Preuves résumées non transmises pour 3 éléments : chacune se charge depuis son lien.');
    expect(notSentText({what:'local_coverage', count:1, reason:'BUDGET'})).toContain('1 zone non lue sans place pour être située');
    expect(notSentText({what:'local_coverage', count:3, reason:'BUDGET'})).toContain('Au moins 3 zones non lues sans place pour être situées');
    expect(notSentText({what:'items', count:2, reason:'BUDGET'})).toBe('2 items non transmis (BUDGET).');
  });
});
