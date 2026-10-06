import {describe, expect, it} from 'vitest';
import {linksOf, viewOf} from './graph';
import {CHAIN_GEOMETRY, chain, wrap, type ChainText, type Form} from './chain';
import type {Boundary} from './protocol';
import {depthCut, element, tile} from './__fixtures__/tiles';

const ROUTE='endpoint:GET /courses', CONTROLLER='symbol:java:CourseController#getCourses()';
const SERVICE='symbol:java:CourseService#getCourses()', IMPL='symbol:java:CourseServiceImpl#getCourses()';
const form=(relation:string):Form=>relation==='IMPLEMENTS'?'SIDE':'CHAIN';
const text:ChainText={name:value=>value, note:boundary=>`note ${boundary.reason}`, cut:boundary=>`coupure ${boundary.reason}`,
  revisit:(link, target)=>`revisite ${target}`, leaf:value=>value??'aucun objet'};
const drawn=(items:ReturnType<typeof element>[], nodes:[string, number, boolean][], frontier:Boundary[]=[])=>{
  const view=viewOf(tile({root:ROUTE, items, nodes, frontier}));
  return chain(view, linksOf(view), form, text);
};
const box=(found:ReturnType<typeof drawn>, key:string)=>found.boxes.find(item=>item.key===key)!;

describe('la vue Chaîne', ()=>{
  it('pose chaque nœud de la chaîne une ligne plus bas, en retrait, la flèche du sujet vers l’objet', ()=>{
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}), element(CONTROLLER, SERVICE, {relation:'CALLS', level:2})],
      [[ROUTE, 0, true], [CONTROLLER, 1, true], [SERVICE, 2, false]], [depthCut(SERVICE)]);
    const [route, controller, service]=[ROUTE, CONTROLLER, SERVICE].map(key=>box(found, key));
    expect(route.anchor).toBe(true);
    expect([route.depth, controller.depth, service.depth]).toEqual([0, 1, 2]);
    expect(controller.x-route.x).toBe(CHAIN_GEOMETRY.indent);
    expect(controller.y).toBe(route.y+route.height+CHAIN_GEOMETRY.gap);
    expect(found.arrows.map(item=>[item.from.key, item.to.key, item.form])).toEqual([[ROUTE, CONTROLLER, 'CHAIN'], [CONTROLLER, SERVICE, 'CHAIN']]);
    expect(found.arrows[0].path.endsWith(`H${controller.x}`), 'elle entre dans la boîte par la gauche').toBe(true);
    expect(box(found, `cut:${SERVICE}`).lines).toEqual(['coupure DEPTH']);
  });

  it('dessine à côté une relation de côté, sur la ligne de son nœud, dans son sens réel', ()=>{
    const found=drawn([element(ROUTE, SERVICE, {relation:'HANDLED_BY'}),
      element(IMPL, SERVICE, {relation:'IMPLEMENTS', direction:'INCOMING', level:2})],
    [[ROUTE, 0, true], [SERVICE, 1, true], [IMPL, 2, false]]);
    const [service, impl]=[SERVICE, IMPL].map(key=>box(found, key));
    expect(impl.column).toBe('side');
    expect(impl.y).toBe(service.y);
    expect(impl.x).toBeGreaterThan(service.x+service.width);
    const side=found.arrows.find(item=>item.form==='SIDE')!;
    expect([side.from.key, side.to.key]).toEqual([IMPL, SERVICE]);
    expect(side.path.startsWith(`M${impl.x} `), 'elle part de la boîte de droite').toBe(true);
  });

  it('ne trace aucun arc de retour : un lien vers un nœud déjà dessiné devient une revisite', ()=>{
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}),
      element(CONTROLLER, ROUTE, {relation:'CALLS', level:2, revisit:true})], [[ROUTE, 0, true], [CONTROLLER, 1, true]]);
    expect(found.arrows).toHaveLength(1);
    const revisit=found.boxes.find(item=>item.kind==='revisit')!;
    expect(revisit.lines).toEqual([`revisite ${ROUTE}`]);
    expect(found.ties.map(tie=>tie.box)).toContain(revisit);
  });

  it('montre chaque fait sans nœud au bout : aucun objet, ou une valeur', ()=>{
    const found=drawn([element(ROUTE, undefined, {relation:'PERMITS_ALL'}), element(ROUTE, 'authenticated()', {relation:'AUTHORIZED_BY'})],
      [[ROUTE, 0, true]]);
    expect(found.boxes.filter(item=>item.kind==='leaf').map(item=>item.lines.join(''))).toEqual(['aucun objet', 'authenticated()']);
    expect(found.arrows.map(item=>item.from.key)).toEqual([ROUTE, ROUTE]);
  });

  it('accroche une frontière de connaissance sous son nœud', ()=>{
    const gap:Boundary={nature:'KNOWLEDGE', scope:'NODE', node:CONTROLLER, subject:'file:A.java', reason:'NOT_INTERPRETED',
      count:{kind:'UNKNOWN'}};
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'})], [[ROUTE, 0, true], [CONTROLLER, 1, true]], [gap]);
    const controller=box(found, CONTROLLER), note=found.boxes.find(item=>item.kind==='note')!;
    expect(note.lines).toEqual(['note NOT_INTERPRETED']);
    expect(note.y).toBeGreaterThan(controller.y);
    expect(note.depth).toBe(controller.depth+1);
  });

  it('montre un lien inconnu dans la chaîne et n’omet aucun lien', ()=>{
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'SOMETHING_NEW'}), element(ROUTE, SERVICE, {relation:'HANDLED_BY'})],
      [[ROUTE, 0, true], [CONTROLLER, 1, false], [SERVICE, 1, false]]);
    expect(found.arrows.map(item=>item.to.key)).toEqual([CONTROLLER, SERVICE]);
    expect(box(found, SERVICE).y).toBeGreaterThan(box(found, CONTROLLER).y);
  });
});

describe('les noms passés à la ligne', ()=>{
  it('coupe après la ponctuation, sans rien perdre', ()=>{
    const name='com.example.courses.CourseServiceImpl#getCourses(java.lang.String)';
    const lines=wrap(name, 20);
    expect(lines.join('')).toBe(name);
    expect(lines.every(said=>said.length<=20)).toBe(true);
    expect(lines[0]).toBe('com.example.courses.');
  });

  it('coupe un mot trop long à la largeur', ()=>{
    expect(wrap('a'.repeat(25), 10)).toEqual(['a'.repeat(10), 'a'.repeat(10), 'a'.repeat(5)]);
    expect(wrap('GET /api/courses', 34)).toEqual(['GET /api/courses']);
  });
});
