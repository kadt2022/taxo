import {describe, expect, it} from 'vitest';
import {linksOf, viewOf} from './graph';
import {GEOMETRY, layout} from './layout';
import {element, tile} from './__fixtures__/tiles';

const [A, B, C, D]=['module:a', 'module:b', 'module:c', 'module:d'];
const placed=(items:ReturnType<typeof element>[], nodes:[string, number, boolean][])=>{
  const view=viewOf(tile({items, nodes}));
  return layout(view, linksOf(view));
};

describe('la vue en couches', ()=>{
  it('met une colonne par niveau, les nœuds dans l’ordre de la vue', ()=>{
    const found=placed([element(A, B), element(A, C), element(B, D, {level:2})], [[A, 0, true], [B, 1, true], [C, 1, true], [D, 2, false]]);
    expect(found.nodes.map(node=>[node.reference, node.level, node.row])).toEqual([[A, 0, 0], [B, 1, 0], [C, 1, 1], [D, 2, 0]]);
    expect(found.nodes[1].x-found.nodes[0].x).toBe(GEOMETRY.column);
    expect(found.nodes[2].y-found.nodes[1].y).toBe(GEOMETRY.row);
    expect(found.width).toBeGreaterThan(found.nodes[3].x+GEOMETRY.width);
  });

  it('trace la flèche dans le sens réel du fait, même lu en entrant', ()=>{
    // B dépend de A ; lu depuis A en entrant, B est au niveau 1 : la flèche part de B, vers la gauche.
    const found=placed([element(B, A, {direction:'INCOMING'})], [[A, 0, true], [B, 1, false]]);
    const [edge]=found.edges;
    expect([edge.from.reference, edge.to.reference]).toEqual([B, A]);
    const [start, end]=[edge.path.match(/^M(\d+) /)![1], edge.path.match(/ (\d+) \d+$/)![1]].map(Number);
    expect(start).toBe(edge.from.x+GEOMETRY.width);
    expect(end, 'un lien vers une colonne précédente arrive par la droite du nœud').toBe(edge.to.x+GEOMETRY.width);
  });

  it('sépare les liens parallèles et compte les occurrences d’un lien', ()=>{
    const found=placed([element(A, B), element(A, B, {producer:'other'}), element(A, B, {relation:'CONTAINS'}),
      element(B, A, {level:2, revisit:true})], [[A, 0, true], [B, 1, true]]);
    expect(found.edges.map(edge=>[edge.link.relation, edge.lane, edge.lanes, edge.count, edge.dashed])).toEqual([
      ['DEPENDS_ON', 0, 3, 2, false], ['CONTAINS', 1, 3, 1, true], ['DEPENDS_ON', 2, 3, 1, true]]);
    // B est déjà dans la vue quand CONTAINS l'atteint : par définition, une revisite.
    expect(new Set(found.edges.map(edge=>edge.path)).size).toBe(3);
  });

  it('dessine une boucle sur son nœud', ()=>{
    const found=placed([element(A, A, {revisit:true})], [[A, 0, true]]);
    expect(found.edges[0]).toMatchObject({dashed:true, from:{reference:A}, to:{reference:A}});
    expect(found.edges[0].path.startsWith(`M${GEOMETRY.margin+GEOMETRY.width} `)).toBe(true);
  });
});
