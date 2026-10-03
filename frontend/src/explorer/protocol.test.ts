import {describe, expect, it, vi} from 'vitest';
import {Refusal, describe as describeAnalysis, evidenceOf, expandTile, findReferences, openTile, queryOf, tileArguments, type CompactTile} from './protocol';

const COMMON={kind:'ASSERTION', contract_version:1, status:'OBSERVED', validity:'VALID', snapshot:{commit:'c'},
  produced_by:{producer_id:'taxo.spring-api', producer_version:'0.2.0'}};
// Une Tuile compacte écrite à la main, telle que `neighborhood/2` la rend avec `form: COMPACT`.
const COMPACT:CompactTile={anchor:{reference:'endpoint:GET /orders', known:true}, facts_revision:4, stop_reason:'ADJACENCY_COMPLETE',
  continuation:null, not_sent:[], bytes:900, frontier:[],
  parameters:{root:'endpoint:GET /orders', depth:1, steps:[{relation:'HANDLED_BY', direction:'OUTGOING'},
    {relation:'HANDLED_BY', direction:'INCOMING'}]},
  nodes:['endpoint:GET /orders', 'symbol:java:A#get()'],
  node_details:[{level:0, known:true, expanded:true, parents:0, discovered_by:null},
    {level:1, known:true, expanded:false, parents:1, discovered_by:0}],
  shared:{common:[COMMON]},
  items:[{ref:'F1', fact:{subject:'endpoint:GET /orders', relation:'HANDLED_BY', object:'symbol:java:A#get()', qualifiers:{}},
    common:0, evidence_count:1, identity:'i1', occurrence:'o1', via:{from:0, step:0}, level:1, revisit:false,
    evidence:[{path:'A.java', line_start:9}]}]};

function answering(...responses:unknown[]){
  const post=vi.fn(async(_path:string, _init:RequestInit)=>({responses:[responses.shift()]}));
  return {post, query:queryOf(post as never, '/projects/p', 'scan-1')};
}

describe('le contrat de l’explorateur', ()=>{
  it('relit la forme compacte en forme complète, sans rien inventer', ()=>{
    const full=expandTile(COMPACT);
    expect(full.node_details.map(node=>node.reference)).toEqual(COMPACT.nodes);
    expect(full.items[0]).toEqual({ref:'F1', evidence_count:1, identity:'i1', occurrence:'o1', level:1, revisit:false,
      evidence:[{path:'A.java', line_start:9}],
      fact:{subject:'endpoint:GET /orders', relation:'HANDLED_BY', object:'symbol:java:A#get()', qualifiers:{}, ...COMMON},
      via:{from:'endpoint:GET /orders', relation:'HANDLED_BY', direction:'OUTGOING'}});
    expect('shared' in full).toBe(false);
  });

  it('demande toujours neighborhood/2, preuves résumées, forme compacte', async()=>{
    const {post, query}=answering({outcome:'OK', ...COMPACT});
    const budget={max_nodes:60, max_edges:120, max_work:300, max_fanout:20};
    await openTile(query, {root:'endpoint:GET /orders', relations:['HANDLED_BY'], direction:'BOTH', depth:2, budget, continuation:'t'});
    const [path, init]=post.mock.calls[0];
    expect(path).toBe('/projects/p/taxo-query');
    expect(JSON.parse(init.body as string)).toEqual({analysis:'scan-1', requests:[{operation:'get_neighborhood', max_bytes:32000,
      arguments:{analysis:'scan-1', engine:'neighborhood/2', root:'endpoint:GET /orders', follow:['HANDLED_BY'], direction:'BOTH',
        depth:2, ...budget, evidence:'SUMMARY', form:'COMPACT', continuation:'t'}}]});
    expect(tileArguments({root:'r', relations:[], direction:'OUTGOING', depth:1, budget})).not.toHaveProperty('continuation');
  });

  it('nomme l’analyse seulement aux opérations qui la prennent', async()=>{
    const {post, query}=answering({outcome:'OK', items:[]}, {outcome:'OK', evidence:[]}, {outcome:'OK', items:[], next:null});
    await describeAnalysis(query);
    await evidenceOf(query, 'o1');
    await findReferences(query, 'GET /', 'endpoint', 'after-1');
    const sent=post.mock.calls.map(call=>JSON.parse(call[1].body as string).requests[0].arguments);
    expect(sent).toEqual([{}, {occurrence:'o1'}, {analysis:'scan-1', prefix:'GET /', type:'endpoint', after:'after-1', limit:20}]);
  });

  it('dit un refus de Taxo par son code et son motif', async()=>{
    const {query}=answering({outcome:'ERROR', error:{code:'INVALID_ARGUMENT', message:'Les faits ont changé.'}});
    const refused=await evidenceOf(query, 'o1').catch(error=>error);
    expect(refused).toBeInstanceOf(Refusal);
    expect([refused.code, refused.message]).toEqual(['INVALID_ARGUMENT', 'Les faits ont changé.']);
  });

  it('lit ce que l’analyse annonce', async()=>{
    const {query}=answering({outcome:'OK', items:[{kind:'operation', operation:'describe'},
      {kind:'analyzer', analyzer:'taxo.spring-api', status:'SUCCESS', relations:['HANDLED_BY']},
      {kind:'relation', relation:'HANDLED_BY', count:3, subject_types:['endpoint'], object_types:['symbol']},
      {kind:'relation', relation:'SERVED_BY', count:1, subject_types:['endpoint'], object_types:['application']}]});
    expect(await describeAnalysis(query)).toEqual({relations:[{relation:'HANDLED_BY', count:3}, {relation:'SERVED_BY', count:1}],
      analyzers:[{analyzer:'taxo.spring-api', status:'SUCCESS', relations:['HANDLED_BY']}],
      types:['application', 'endpoint', 'symbol']});
  });
});
