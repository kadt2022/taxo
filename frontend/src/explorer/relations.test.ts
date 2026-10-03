import {describe, expect, it} from 'vitest';
import {NO_PRODUCER, defaultRelations, relationChoices, searchOf} from './relations';

const described={types:[], relations:[{relation:'HANDLED_BY', count:4}, {relation:'CHANGES', count:9}, {relation:'GLUES', count:1}],
  analyzers:[{analyzer:'taxo.spring-api', status:'SUCCESS', relations:['HANDLED_BY', 'ACCEPTS']},
    {analyzer:'taxo.git', status:'PARTIAL', relations:['CHANGES']},
    {analyzer:'taxo.data', status:'UNSUPPORTED', relations:['READS']}]};

describe('les relations proposées', ()=>{
  it('viennent de ce que l’analyse annonce, rangées par domaine ; sans producteur exécuté, désactivées avec la raison', ()=>{
    expect(relationChoices(described).map(choice=>[choice.relation, choice.domain, choice.count, choice.available, choice.reason]))
      .toEqual([['ACCEPTS', 'api', 0, true, undefined], ['HANDLED_BY', 'api', 4, true, undefined], ['CHANGES', 'git', 9, true, undefined],
        ['GLUES', 'autres', 1, true, undefined], ['READS', 'autres', 0, false, NO_PRODUCER]]);
  });

  it('suit par défaut celles qui ont des faits, au plus 16', ()=>{
    expect(defaultRelations(relationChoices(described))).toEqual(['HANDLED_BY', 'CHANGES', 'GLUES']);
    const many={types:[], analyzers:[], relations:Array.from({length:20}, (_, index)=>({relation:`R${index}`, count:1}))};
    expect(defaultRelations(relationChoices(many))).toHaveLength(16);
  });
});

describe('la saisie d’une ancre', ()=>{
  it('reconnaît un type connu écrit en tête, sinon garde la saisie entière', ()=>{
    expect(searchOf('endpoint:GET /o', '', ['endpoint'])).toEqual({type:'endpoint', prefix:'GET /o'});
    expect(searchOf('GET /o', 'endpoint', ['endpoint'])).toEqual({type:'endpoint', prefix:'GET /o'});
    expect(searchOf('http://x', '', ['endpoint'])).toEqual({type:undefined, prefix:'http://x'});
    expect(searchOf('endpoint:GET', 'file', ['endpoint', 'file']), 'le filtre choisi l’emporte').toEqual({type:'file', prefix:'endpoint:GET'});
  });
});
