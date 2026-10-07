import {describe, expect, it} from 'vitest';
import {CALL_AXIS} from '../vocabulary';
import {calls} from './calls';
import {chain, CHAIN_GEOMETRY, type ChainText} from './chain';
import {linksOf, viewOf} from './graph';
import type {Boundary} from './protocol';
import {depthCut, element, tile} from './__fixtures__/tiles';

const ROUTE='endpoint:GET /api/courses', CONTROLLER='symbol:java:CourseController#getCourses()';
const SERVICE='symbol:java:CourseService#getCourses()', REPOSITORY='symbol:java:CourseRepository#findAll()';
const PRICING='symbol:java:Pricing#calculate()', MAPPER='symbol:java:CourseMapper#toDto()';
const IMPL='symbol:java:CourseServiceImpl#getCourses()', MODULE='module:app', FILE='file:CourseController.java';
const onAxis=(relation:string)=>CALL_AXIS.includes(relation);
const text:ChainText={name:value=>({owner:value}), note:boundary=>boundary.reason, cut:boundary=>boundary.reason,
  revisit:(link, target)=>`revisite ${target}`, leaf:value=>value??''};

const projected=(items:ReturnType<typeof element>[], nodes:[string, number, boolean][], frontier:Boundary[]=[])=>{
  const view=viewOf(tile({root:ROUTE, items, nodes, frontier}));
  return calls(view, linksOf(view), onAxis);
};
const drawn=(found:ReturnType<typeof projected>)=>chain(found.view, found.links, ()=>'CHAIN', text);
const arrows=(found:ReturnType<typeof projected>)=>found.links.filter(link=>!link.revisit).map(link=>[link.subject, link.object]);

describe('la vue Appels', ()=>{
  it('va de la route au contrôleur qui la traite', ()=>{
    const found=projected([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'})], [[ROUTE, 0, true], [CONTROLLER, 1, true]]);
    expect(arrows(found)).toEqual([[ROUTE, CONTROLLER]]);
    expect(found.view.nodes.map(node=>node.reference)).toEqual([ROUTE, CONTROLLER]);
  });

  it('va du contrôleur au service qu’il appelle', ()=>{
    const found=projected([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}), element(CONTROLLER, SERVICE, {relation:'CALLS', level:2})],
      [[ROUTE, 0, true], [CONTROLLER, 1, true], [SERVICE, 2, true]]);
    expect(arrows(found)).toEqual([[ROUTE, CONTROLLER], [CONTROLLER, SERVICE]]);
  });

  it('dessine un appel linéaire tout droit, de haut en bas', ()=>{
    const found=projected([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}), element(CONTROLLER, SERVICE, {relation:'CALLS', level:2}),
      element(SERVICE, REPOSITORY, {relation:'CALLS', level:3})],
    [[ROUTE, 0, true], [CONTROLLER, 1, true], [SERVICE, 2, true], [REPOSITORY, 3, true]]);
    const layout=drawn(found);
    const boxes=[ROUTE, CONTROLLER, SERVICE, REPOSITORY].map(key=>layout.boxes.find(box=>box.key===key)!);
    expect(new Set(boxes.map(box=>box.x)).size, 'une seule colonne').toBe(1);
    expect(boxes.map(box=>box.y)).toEqual([...boxes.map(box=>box.y)].sort((a, b)=>a-b));
    expect(layout.arrows.every(arrow=>/^M\d+ \d+ V\d+$/.test(arrow.path)), 'des traits droits').toBe(true);
  });

  it('montre une bifurcation quand une méthode en appelle plusieurs', ()=>{
    const found=projected([element(ROUTE, SERVICE, {relation:'HANDLED_BY'}), element(SERVICE, REPOSITORY, {relation:'CALLS', level:2}),
      element(SERVICE, PRICING, {relation:'CALLS', level:2}), element(SERVICE, MAPPER, {relation:'CALLS', level:2})],
    [[ROUTE, 0, true], [SERVICE, 1, true], [REPOSITORY, 2, true], [PRICING, 2, true], [MAPPER, 2, true]]);
    expect(arrows(found)).toEqual([[ROUTE, SERVICE], [SERVICE, REPOSITORY], [SERVICE, PRICING], [SERVICE, MAPPER]]);
    const layout=drawn(found), at=(key:string)=>layout.boxes.find(box=>box.key===key)!;
    expect([REPOSITORY, PRICING, MAPPER].map(key=>at(key).x-at(SERVICE).x)).toEqual([1, 1, 1].map(()=>CHAIN_GEOMETRY.indent));
    expect(found.ends).toEqual([REPOSITORY, PRICING, MAPPER]);
  });

  it('garde la coupure de profondeur là où la vue s’arrête', ()=>{
    const found=projected([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'})], [[ROUTE, 0, true], [CONTROLLER, 1, false]],
      [depthCut(CONTROLLER)]);
    expect(found.view.selection[CONTROLLER]?.reason).toBe('DEPTH');
    expect(found.ends, 'une coupure n’est pas une fin').toEqual([]);
    expect(drawn(found).boxes.some(box=>box.kind==='cut'&&box.reference===CONTROLLER)).toBe(true);
  });

  it('dit la fin de l’axe quand aucun appel n’est établi, sans inventer de suite', ()=>{
    const found=projected([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'})], [[ROUTE, 0, true], [CONTROLLER, 1, true]]);
    expect(found.ends).toEqual([CONTROLLER]);
    expect(found.links).toHaveLength(1);
  });

  it('garde une frontière de nœud et une lacune de l’axe, pas celles du contexte', ()=>{
    const gap:Boundary={nature:'KNOWLEDGE', scope:'NODE', node:CONTROLLER, reason:'NOT_ANALYSED', count:{kind:'UNKNOWN'}};
    const axis:Boundary={nature:'KNOWLEDGE', scope:'ANALYSIS', relation:'CALLS', reason:'NO_ANALYZER', count:{kind:'UNKNOWN'}};
    const context:Boundary={nature:'KNOWLEDGE', scope:'ANALYSIS', relation:'IMPLEMENTS', reason:'NO_ANALYZER', count:{kind:'UNKNOWN'}};
    const found=projected([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'})], [[ROUTE, 0, true], [CONTROLLER, 1, true]],
      [gap, axis, context]);
    expect(found.view.knowledge).toEqual([gap, axis]);
    expect(found.ends, 'une frontière n’est pas une fin').toEqual([]);
  });

  it('n’invente rien : ni le contexte, ni une relation inconnue, ni un nœud', ()=>{
    const found=projected([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}), element(ROUTE, MODULE, {relation:'SERVED_BY'}),
      element(IMPL, CONTROLLER, {relation:'IMPLEMENTS', direction:'INCOMING', level:2}), element(FILE, CONTROLLER, {relation:'CONTAINS', direction:'INCOMING', level:2}),
      element(CONTROLLER, SERVICE, {relation:'SOMETHING_NEW', level:2})],
    [[ROUTE, 0, true], [CONTROLLER, 1, true], [MODULE, 1, false], [IMPL, 2, false], [FILE, 2, false], [SERVICE, 2, false]]);
    expect(found.links.map(link=>link.relation)).toEqual(['HANDLED_BY']);
    expect(found.view.nodes.map(node=>node.reference)).toEqual([ROUTE, CONTROLLER]);
    expect(found.view.elements.every(item=>onAxis(item.fact.relation))).toBe(true);
  });

  it('pose un nœud sous le premier appel qui l’atteint, l’autre devenant une revisite', ()=>{
    const found=projected([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}), element(CONTROLLER, SERVICE, {relation:'CALLS', level:2}),
      element(CONTROLLER, REPOSITORY, {relation:'CALLS', level:2}), element(SERVICE, REPOSITORY, {relation:'CALLS', level:3})],
    [[ROUTE, 0, true], [CONTROLLER, 1, true], [SERVICE, 2, true], [REPOSITORY, 2, true]]);
    expect(arrows(found)).toEqual([[ROUTE, CONTROLLER], [CONTROLLER, SERVICE], [CONTROLLER, REPOSITORY]]);
    expect(found.links.filter(link=>link.revisit).map(link=>[link.subject, link.object])).toEqual([[SERVICE, REPOSITORY]]);
  });
});
