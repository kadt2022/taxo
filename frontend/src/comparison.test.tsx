import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {CATEGORIES, ChangeItem, CompareLauncher, ComparisonView, proof, proofWithContent, sideLabel, statement} from './comparison';

const commit={id:'a', created_at:'2026-10-01T10:00:00Z', snapshot:{commit:'3c4d5e6f7a8b9c0d', mode:'COMMIT'}};
const tree={id:'b', created_at:'2026-10-01T11:00:00Z',
  snapshot:{commit:'3c4d5e6f7a8b9c0d', mode:'WORKING_TREE', content_fingerprint:'sha256:abcdef0123456789'}};

describe('comparaison de deux analyses', ()=>{
  it('dit ce que chaque analyse a lu : un commit, ou des fichiers non commités', ()=>{
    expect(sideLabel(commit)).toBe('commit 3c4d5e6f7a');
    expect(sideLabel(tree)).toBe('Fichiers non commités · empreinte abcdef0123…');
    expect(sideLabel({id:'c', created_at:'', snapshot:null})).toBe('instantané inconnu');
  });

  it('dit un fait en clair, le dépôt par le nom du projet', ()=>{
    expect(statement({kind:'ASSERTION', subject:'endpoint:GET /orders', relation:'HANDLED_BY',
      object:'symbol:java:com.acme.OrderController#get()', status:'OBSERVED', validity:'VALID'}))
      .toBe('route GET /orders est traité par symbole java:com.acme.OrderController#get()');
    expect(statement({kind:'ASSERTION', subject:'repository:p1', relation:'CONTAINS', object:'file:a.java',
      status:'OBSERVED', validity:'VALID'}, {id:'p1', name:'Boutique'})).toBe('dépôt Boutique contient a.java');
  });

  it('situe une preuve, et montre le contenu cité quand seules les lignes ne suffisent pas', ()=>{
    expect(proof({path:'A.java', line_start:87, line_end:87})).toBe('A.java:87');
    expect(proof({path:'A.java', line_start:3, line_end:9})).toBe('A.java:3-9');
    expect(proof({path:'A.java'})).toBe('A.java');
    expect(proof({object:'commit:0123456789abcdef0123'})).toBe('commit 0123456789ab');
    expect(proofWithContent({path:'A.java', line_start:14, line_end:14, content_hash:'sha256:9f8e7d6c5b'}))
      .toBe('A.java:14 · contenu 9f8e7d6c');
  });

  it('ne compte que des faits : aucun pourcentage, aucun impact supposé', ()=>{
    const labels=CATEGORIES.map(item=>item.label).join(' ');
    expect(labels).not.toMatch(/%|impact|risque/i);
    expect(CATEGORIES.map(item=>item.id)).toEqual(['ADDED', 'REMOVED', 'MODIFIED', 'EVIDENCE_CHANGED', 'STATUS_CHANGED',
      'OCCURRENCE_COUNT_CHANGED', 'OCCURRENCES_CHANGED']);
  });

  it('propose de comparer avec une autre analyse complète, ou dit pourquoi ce n’est pas possible', ()=>{
    const html=renderToStaticMarkup(<CompareLauncher current={commit} others={[tree]} onCompare={()=>undefined}/>);
    expect(html).toContain('Comparer avec');
    expect(html).toContain('Fichiers non commités');
    expect(renderToStaticMarkup(<CompareLauncher current={commit} others={[]} onCompare={()=>undefined}/>))
      .toContain('Une seule analyse complète');
  });

  it('annonce la comparaison en cours avant la réponse de l’API', ()=>{
    const html=renderToStaticMarkup(<ComparisonView base="/projects/p" request={()=>new Promise(()=>undefined)} before="a" after="b"
      onClose={()=>undefined} onSwap={()=>undefined}/>);
    expect(html).toContain('Comparaison en cours');
    expect(html).toContain('Inverser le sens');
  });

  it('montre tout ce que dit chaque côté quand le contenu change, y compris la graphie', ()=>{
    const fact=(object:string)=>({kind:'ASSERTION', subject:'module:root', relation:'DEPENDS_ON', object, status:'OBSERVED',
      validity:'VALID', evidence:[{path:'build.gradle', line_start:1, line_end:1, content_hash:'sha256:aaaaaaaaaa'}]});
    const html=renderToStaticMarkup(<ul><ChangeItem category="OCCURRENCES_CHANGED"
      item={{before:[fact('module:caf\u00e9')], after:[fact('module:cafe\u0301')]}}/></ul>);
    expect(html).toContain('module caf\u00e9');
    expect(html).toContain('module cafe\u0301');
    expect(html).toContain('Observé dans le code · À jour');
    expect(html).toContain('Voir les détails techniques');
    expect(html).toContain('OBSERVED · VALID');
  });

  it('dit pourquoi Taxo conclut, en clair, et garde les termes du moteur dans les détails', ()=>{
    const fact={kind:'ASSERTION', subject:'endpoint:GET /orders', relation:'MATCHED_BY', object:'route-pattern:/**', status:'INFERRED',
      validity:'VALID', derivation:{rule:'first-match', premises:['HANDLED_BY : endpoint:GET /orders -> symbol:java:com.acme.web.OrderController#get()']},
      produced_by:{producer_id:'taxo.spring-security', producer_version:'0.4.0'}};
    const html=renderToStaticMarkup(<ul><ChangeItem category="OCCURRENCES_CHANGED" item={{before:[fact], after:[fact]}}/></ul>);
    expect(html).toContain('Déduit par Taxo · À jour');
    expect(html).toContain('Pourquoi Taxo arrive à cette conclusion');
    expect(html).toContain('route GET /orders est traité par OrderController.get()');
    expect(html).toContain('INFERRED · VALID');
    expect(html).toContain('taxo.spring-security 0.4.0');
  });

  it('montre la preuve avant et après, avec le contenu cité', ()=>{
    const fact=(line:number, content:string)=>({kind:'ASSERTION', subject:'endpoint:GET /users', relation:'HANDLED_BY',
      object:'symbol:java:UserController#get()', status:'OBSERVED', validity:'VALID',
      evidence:[{path:'UserController.java', line_start:line, line_end:line, content_hash:`sha256:${content}`}]});
    const html=renderToStaticMarkup(<ul><ChangeItem category="EVIDENCE_CHANGED"
      item={{before:[fact(87, '11111111aa')], after:[fact(91, '22222222bb')]}}/></ul>);
    expect(html).toContain('UserController.java:87 · contenu 11111111');
    expect(html).toContain('UserController.java:91 · contenu 22222222');
  });
});
