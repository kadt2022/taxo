import {describe, expect, it} from 'vitest';
import type {Boundary} from './protocol';
import {linksOf, viewOf} from './graph';
import {element, tile} from './__fixtures__/tiles';
import {categoryTexts, compartments, countText, factText, linkMarks, knowledgeText, nodeMarks, nodeName, notSentText, scopeText, selectionText, verb, viewText} from './sentences';
import {CATEGORIES, CAUSES} from '../vocabulary';

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

  it('dit pourquoi des appels d’une zone non lue n’ont pas de cible, sans jamais la raison brute', ()=>{
    const unread={...gap('NOT_INTERPRETED'), producer:'taxo.java-calls', subject:'symbol:java:a.B#run()',
      causes:['OVERLOAD_AMBIGUOUS', 'RECEIVER_KIND_DEFERRED']};
    expect(knowledgeText(unread)).toBe('Zone non lue par Appels Java : symbole java:a.B#run() (Non analysé par Taxo : '
      +'plusieurs déclarations possibles ; receveur local ou paramètre, pas encore suivi).');
    for(const cause of Object.keys(CAUSES))expect(knowledgeText({...unread, causes:[cause]})).not.toContain(cause);
    expect(knowledgeText({...unread, causes:['NOUVELLE']})).toContain(': NOUVELLE).');
  });

  it('dit chaque catégorie par son libellé et son décompte, jamais par son nom brut', ()=>{
    const unread={...gap('NOT_INTERPRETED'), causes:['X_CODE']};
    expect(categoryTexts({...unread, categories:[{category:'UNKNOWN', count:{kind:'EXACT', value:3}},
      {category:'AMBIGUOUS', count:{kind:'AT_LEAST', value:0}}]}))
      .toEqual([{category:'UNKNOWN', text:'cible inconnue · 3'}, {category:'AMBIGUOUS', text:'plusieurs cibles possibles · au moins 0'}]);
    for(const category of Object.keys(CATEGORIES))
      expect(categoryTexts({...unread, categories:[{category, count:{kind:'EXACT', value:1}}]})[0].text).not.toContain(category);
    expect(categoryTexts({...unread, categories:[{category:'NOUVELLE', count:{kind:'EXACT', value:1}}]})[0].text).toBe('NOUVELLE · 1');
  });

  it('dit « non classé » d’une zone décrite sans catégorie, et rien d’une zone sans site', ()=>{
    expect(categoryTexts({...gap('NOT_INTERPRETED'), causes:['X_CODE']})).toEqual([{category:null, text:'non classé'}]);
    expect(categoryTexts(gap('READ_ERROR'))).toEqual([]);
    expect(categoryTexts(cut('DEPTH'))).toEqual([]);
  });

  it('lit une frontière d’avant les catégories comme une d’après, sans erreur', ()=>{
    const before:Boundary=JSON.parse('{"nature":"KNOWLEDGE","scope":"NODE","node":"m","reason":"NOT_INTERPRETED","count":{"kind":"UNKNOWN"},"causes":["A"]}');
    const after:Boundary=JSON.parse('{"nature":"KNOWLEDGE","scope":"NODE","node":"m","reason":"NOT_INTERPRETED","count":{"kind":"UNKNOWN"},"causes":["A"],'
      +'"categories":[{"category":"UNKNOWN","count":{"kind":"EXACT","value":1}}]}');
    expect(knowledgeText(after)).toBe(knowledgeText(before));
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

describe('le nom d’un symbole en compartiments UML', ()=>{
  it('sépare la classe, son paquetage et la méthode avec ses types de paramètres', ()=>{
    expect(compartments('symbol:java:com.acme.admin.UserAdminController#get(String,String)')).toEqual(
      {owner:'UserAdminController', context:'com.acme.admin', member:'get(String,String)'});
    expect(compartments('symbol:java:Foo#<init>()')).toEqual({owner:'Foo', member:'<init>()'});
    expect(compartments('symbol:java:com.acme.Foo')).toEqual({owner:'Foo', context:'com.acme'});
  });

  it('met à part l’emplacement d’une application ou d’un fichier, comme le paquetage d’une classe', ()=>{
    expect(compartments('application:app/Main.java#Main')).toEqual({owner:'Main', context:'app/Main.java'});
    expect(compartments('application:compose.yaml#api')).toEqual({owner:'api', context:'compose.yaml'});
    expect(compartments('file:src/main/A.java')).toEqual({owner:'A.java', context:'src/main'});
    expect(compartments('file:pom.xml')).toEqual({owner:'pom.xml'});
  });

  it('garde le nom entier de toute autre référence', ()=>{
    expect(compartments('endpoint:GET /orders')).toEqual({owner:'GET /orders'});
    expect(compartments('symbol:sans-langage')).toEqual({owner:'sans-langage'});
  });
});

describe('les statuts d’un lien', ()=>{
  it('montre chaque statut distinct de ses occurrences, pas seulement le premier', ()=>{
    const view=viewOf(tile({root:'endpoint:GET /a', nodes:[['endpoint:GET /a', 0, true], ['symbol:java:A#get()', 1, false]],
      items:[element('endpoint:GET /a', 'symbol:java:A#get()', {relation:'HANDLED_BY', occurrence:'o1'}),
        element('endpoint:GET /a', 'symbol:java:A#get()', {relation:'HANDLED_BY', occurrence:'o2', status:'INFERRED'}),
        element('endpoint:GET /a', 'symbol:java:A#get()', {relation:'HANDLED_BY', occurrence:'o3'})]}));
    const [link]=linksOf(view);
    expect(link.elements).toHaveLength(3);
    expect(linkMarks(link)).toEqual(['O', 'D']);
  });
});
