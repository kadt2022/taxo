import {describe, expect, it} from 'vitest';
import {linksAt, linksOf, merge, omitted, viewOf} from './graph';
import {depthCut, edgesCut, element, tile} from './__fixtures__/tiles';

const [A, B, C, D]=['module:a', 'module:b', 'module:c', 'module:d'];

// Un losange A→B, A→C, B→D, C→D, et un retour D→A : la Tuile de profondeur 2 s'arrête à D.
const first=tile({items:[element(A, B), element(A, C), element(B, D, {level:2}), element(C, D, {level:2, revisit:true})],
  nodes:[[A, 0, true], [B, 1, true], [C, 1, true], [D, 2, false]], frontier:[depthCut(D)], stop:'DEPTH'});
// Développer D : une Tuile depuis D, qui retrouve A.
const fromD=tile({root:D, items:[element(D, A, {level:1})], nodes:[[D, 0, true], [A, 1, false]], frontier:[depthCut(A)]});

describe('la vue d’une Tuile', ()=>{
  it('garde chaque occurrence, et ses revisites sont celles du moteur', ()=>{
    const view=viewOf(first);
    expect(view.elements.map(item=>[item.fact.subject, item.fact.object, item.level, item.revisit])).toEqual([
      [A, B, 1, false], [A, C, 1, false], [B, D, 2, false], [C, D, 2, true]]);
    expect(view.nodes.map(node=>[node.reference, node.level, node.expanded])).toEqual([[A, 0, true], [B, 1, true], [C, 1, true], [D, 2, false]]);
    expect(Object.keys(view.selection)).toEqual([D]);
  });

  it('une ancre inconnue reste inconnue, sans aucun nœud inventé', ()=>{
    const view=viewOf(tile({root:'module:absent', known:false, stop:'ROOT_UNKNOWN'}));
    expect(view.known).toBe(false);
    expect(view.nodes.map(node=>[node.reference, node.known])).toEqual([['module:absent', false]]);
    expect(view.elements).toEqual([]);
  });
});

describe('développer un nœud', ()=>{
  it('décale les niveaux depuis le nœud développé, et retire sa coupure', ()=>{
    const view=merge(viewOf(first), fromD, D);
    expect(view.elements.at(-1)).toMatchObject({fact:{subject:D, object:A}, level:3});
    expect(view.nodes.find(node=>node.reference===D)?.expanded).toBe(true);
    expect(view.nodes.find(node=>node.reference===A)).toMatchObject({level:0, expanded:true});
    expect(view.selection, 'A est déjà développé : sa coupure dans la nouvelle Tuile ne compte pas').toEqual({});
  });

  it('une extrémité déjà dans la vue est une revisite, même nouvelle pour la Tuile reçue', ()=>{
    const view=merge(viewOf(first), fromD, D);
    expect(fromD.items[0].revisit).toBe(false);
    expect(view.elements.at(-1)?.revisit).toBe(true);
  });

  it('fusionner deux fois la même Tuile ne change rien', ()=>{
    const once=merge(viewOf(first), fromD, D);
    expect(merge(once, fromD, D)).toEqual(once);
  });

  it('voir la suite remplace la coupure par celle de la reprise, sans doublon d’occurrence', ()=>{
    const cut=tile({items:[element(A, B)], nodes:[[A, 0, false], [B, 1, false]], frontier:[edgesCut(A, 't1'), depthCut(B)],
      stop:'EDGES'});
    const rest=tile({items:[element(A, B), element(A, C)], nodes:[[A, 0, false], [B, 1, false], [C, 1, false]],
      frontier:[edgesCut(A, 't2'), depthCut(B), depthCut(C)], stop:'EDGES'});
    const view=merge(viewOf(cut), rest, A);
    expect(view.elements.map(item=>item.fact.object)).toEqual([B, C]);
    expect(view.selection[A].continuation).toBe('t2');
    expect(new Set(Object.keys(view.selection))).toEqual(new Set([A, B, C]));
  });

  it('une Tuile d’une autre génération de faits n’est jamais mêlée à la vue', ()=>{
    const view=viewOf(first);
    const other=merge(view, {...fromD, facts_revision:2}, D);
    expect(other.stale).toBe(true);
    expect(other.elements).toEqual(view.elements);
  });

  it('un budget ne lève jamais ce que Taxo ne sait pas', ()=>{
    const gap={nature:'KNOWLEDGE' as const, scope:'NODE' as const, node:B, subject:'file:B.java', reason:'NOT_INTERPRETED',
      producer:'taxo.spring-api', count:{kind:'UNKNOWN' as const}};
    const start=tile({items:[element(A, B), element(B, D, {level:2})], nodes:[[A, 0, true], [B, 1, true], [D, 2, false]],
      frontier:[gap, gap, depthCut(D)]});
    const view=merge(viewOf(start), fromD, D);
    expect(view.knowledge).toEqual([gap]);
  });
});

describe('les liens', ()=>{
  it('regroupent les occurrences d’une identité sans en perdre une ; une revisite seulement si toutes le sont', ()=>{
    const view=viewOf(tile({items:[element(A, B, {producer:'one'}), element(A, B, {producer:'two', revisit:true}), element(A, A, {revisit:true})],
      nodes:[[A, 0, true], [B, 1, true]]}));
    const links=linksOf(view);
    expect(links.map(link=>[link.object, link.elements.length, link.revisit])).toEqual([[B, 2, false], [A, 1, true]]);
    expect(links[0].elements.map(item=>item.fact.produced_by?.producer_id)).toEqual(['one', 'two']);
  });

  it('se lisent depuis chaque nœud, de son côté, dans le sens réel du fait', ()=>{
    const view=viewOf(tile({items:[element(B, A, {direction:'INCOMING'})], nodes:[[A, 0, true], [B, 1, false]]}));
    const links=linksOf(view);
    expect(links[0]).toMatchObject({subject:B, object:A});
    expect(linksAt(links, A).from).toHaveLength(1);
    expect(linksAt(links, B).to).toHaveLength(1);
  });
});

describe('les extrémités qui ne sont pas des nœuds', ()=>{
  // Un fait sans objet, et un fait dont l'objet est une valeur littérale : rendus par le moteur, sans nœud d'arrivée.
  const open=element(A, undefined, {relation:'PERMITS_ALL'}), literal=element(A, 'authenticated()', {relation:'AUTHORIZED_BY'});
  const view=viewOf(tile({items:[open, literal, element(A, B)], nodes:[[A, 0, true], [B, 1, false]]}));

  it('gardent leurs éléments, sans nœud inventé ni revisite', ()=>{
    expect(view.elements.map(item=>[item.fact.relation, item.far, item.revisit])).toEqual([
      ['PERMITS_ALL', null, false], ['AUTHORIZED_BY', null, false], ['DEPENDS_ON', B, false]]);
    expect(view.nodes.map(node=>node.reference)).toEqual([A, B]);
    expect(linksOf(view).map(link=>link.object)).toEqual([undefined, 'authenticated()', B]);
  });
});

describe('ce qui n’a pas été transmis', ()=>{
  it('reste dit après un développement ; les preuves non résumées se comptent sur la vue', ()=>{
    const cut={...first, items:first.items.map((item, index)=>index<2?{...item, evidence:null}:item),
      not_sent:[{what:'evidence_summary', count:2, reason:'BUDGET'}, {what:'local_coverage', count:3, reason:'BUDGET'}]};
    const view=merge(viewOf(cut), fromD, D);
    expect(omitted(view)).toEqual([{what:'evidence_summary', count:2, reason:'BUDGET'}, {what:'local_coverage', count:3, reason:'BUDGET'}]);
    const later=merge(view, {...fromD, root:B, items:[], not_sent:[{what:'local_coverage', count:1, reason:'BUDGET'}]} as never, B);
    expect(omitted(later)).toContainEqual({what:'local_coverage', count:3, reason:'BUDGET'});
  });
});
