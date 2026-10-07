import {describe, expect, it} from 'vitest';
import {linksOf, viewOf} from './graph';
import {CHAIN_GEOMETRY, chain, wrap, type ChainText, type Form} from './chain';
import type {Boundary} from './protocol';
import {depthCut, element, tile} from './__fixtures__/tiles';

const ROUTE='endpoint:GET /courses', CONTROLLER='symbol:java:CourseController#getCourses()';
const SERVICE='symbol:java:CourseService#getCourses()', IMPL='symbol:java:CourseServiceImpl#getCourses()';
const form=(relation:string):Form=>relation==='IMPLEMENTS'?'SIDE':'CHAIN';
const text:ChainText={name:value=>({owner:value}), note:boundary=>`note ${boundary.reason}`, cut:boundary=>`coupure ${boundary.reason}`,
  revisit:(link, target)=>`revisite ${target}`, leaf:value=>value??'aucun objet'};
const drawn=(items:ReturnType<typeof element>[], nodes:[string, number, boolean][], frontier:Boundary[]=[])=>{
  const view=viewOf(tile({root:ROUTE, items, nodes, frontier}));
  return chain(view, linksOf(view), form, text);
};
const box=(found:ReturnType<typeof drawn>, key:string)=>found.boxes.find(item=>item.key===key)!;

describe('la vue Chaîne', ()=>{
  it('descend tout droit quand la chaîne ne se divise pas, la flèche du sujet vers l’objet', ()=>{
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}), element(CONTROLLER, SERVICE, {relation:'CALLS', level:2})],
      [[ROUTE, 0, true], [CONTROLLER, 1, true], [SERVICE, 2, false]], [depthCut(SERVICE)]);
    const [route, controller, service]=[ROUTE, CONTROLLER, SERVICE].map(key=>box(found, key));
    expect(route.anchor).toBe(true);
    expect([route.x, controller.x, service.x]).toEqual([route.x, route.x, route.x]);
    expect(controller.y).toBe(route.y+route.height+CHAIN_GEOMETRY.gap);
    expect(found.arrows.map(item=>[item.from.key, item.to.key, item.form])).toEqual([[ROUTE, CONTROLLER, 'CHAIN'], [CONTROLLER, SERVICE, 'CHAIN']]);
    const center=route.x+route.width/2;
    expect(found.arrows[0].path, 'un trait droit, du bas de la route au haut du contrôleur')
      .toBe(`M${center} ${route.y+route.height} V${controller.y}`);
    expect(found.arrows[0].label.x).toBeGreaterThan(center);
    expect(box(found, `cut:${SERVICE}`).lines).toEqual(['coupure DEPTH']);
  });

  it('pose en retrait les suites d’un nœud qui se divise, chacune entrant par la gauche', ()=>{
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}), element(ROUTE, SERVICE, {relation:'HANDLED_BY'})],
      [[ROUTE, 0, true], [CONTROLLER, 1, false], [SERVICE, 1, false]]);
    const [route, controller, service]=[ROUTE, CONTROLLER, SERVICE].map(key=>box(found, key));
    expect([route.depth, controller.depth, service.depth]).toEqual([0, 1, 1]);
    expect(controller.x-route.x).toBe(CHAIN_GEOMETRY.indent);
    expect(found.arrows.every(item=>item.path.endsWith(`H${controller.x}`))).toBe(true);
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
    expect(revisit.reference, 'elle désigne le nœud déjà dessiné').toBe(ROUTE);
    expect(found.ties.map(tie=>tie.box)).toContain(revisit);
  });

  it('pose un nœud sous le lien qui l’a découvert dans la Tuile, l’autre lien devenant une revisite', ()=>{
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'}), element(ROUTE, SERVICE, {relation:'HANDLED_BY'}),
      element(CONTROLLER, SERVICE, {relation:'CALLS', level:2})], [[ROUTE, 0, true], [CONTROLLER, 1, true], [SERVICE, 1, false]]);
    expect(found.arrows.map(item=>[item.from.key, item.to.key])).toEqual([[ROUTE, CONTROLLER], [ROUTE, SERVICE]]);
    const revisit=found.boxes.find(item=>item.kind==='revisit')!;
    expect([revisit.link!.subject, revisit.reference]).toEqual([CONTROLLER, SERVICE]);
    expect(box(found, SERVICE).depth).toBe(box(found, CONTROLLER).depth);
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

  it('pose la frontière juste sous son nœud, avant sa suite, que la flèche contourne', ()=>{
    const gap:Boundary={nature:'KNOWLEDGE', scope:'NODE', node:ROUTE, subject:'file:A.java', reason:'NOT_INTERPRETED',
      count:{kind:'UNKNOWN'}};
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'})], [[ROUTE, 0, true], [CONTROLLER, 1, false]], [gap]);
    const route=box(found, ROUTE), controller=box(found, CONTROLLER), note=found.boxes.find(item=>item.kind==='note')!;
    expect(note.y).toBe(route.y+route.height+CHAIN_GEOMETRY.gap);
    expect(controller.y).toBeGreaterThan(note.y);
    expect(controller.depth, 'en retrait : un trait droit traverserait la note').toBe(1);
  });

  it('montre un lien inconnu dans la chaîne et n’omet aucun lien', ()=>{
    const found=drawn([element(ROUTE, CONTROLLER, {relation:'SOMETHING_NEW'}), element(ROUTE, SERVICE, {relation:'HANDLED_BY'})],
      [[ROUTE, 0, true], [CONTROLLER, 1, false], [SERVICE, 1, false]]);
    expect(found.arrows.map(item=>item.to.key)).toEqual([CONTROLLER, SERVICE]);
    expect(box(found, SERVICE).y).toBeGreaterThan(box(found, CONTROLLER).y);
  });
});

describe('les compartiments d’une boîte', ()=>{
  it('ajoute à la hauteur le contexte, le membre et leur séparation', ()=>{
    const view=viewOf(tile({root:ROUTE, items:[element(ROUTE, CONTROLLER, {relation:'HANDLED_BY'})],
      nodes:[[ROUTE, 0, true], [CONTROLLER, 1, false]]}));
    const named={owner:'CourseController', context:'com.example', member:'getCourses(String,int)'};
    const found=chain(view, linksOf(view), form, {...text, name:value=>value===CONTROLLER?named:{owner:value}});
    const controller=found.boxes.find(item=>item.key===CONTROLLER)!, route=found.boxes.find(item=>item.key===ROUTE)!;
    expect([controller.lines, controller.context, controller.member]).toEqual([['CourseController'], ['com.example'], ['getCourses(String,int)']]);
    const {header, line, pad, separator}=CHAIN_GEOMETRY;
    expect(controller.height).toBe(header+3*line+pad+separator);
    expect(route.height).toBe(header+line+pad);
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
