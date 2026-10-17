// La mise en page de l'explorateur dans Chromium, contre une API Taxo réelle : des champs alignés, une zone du graphe qui suit
// son contenu jusqu'à un plafond configurable, rien de coupé ni de débordant aux tailles de fenêtre courantes. Le dessin lui-même
// (nœuds, liens, couleurs) vient du moteur de disposition et n'est jamais modifié par ces tests.
import {expect, test, type Page} from '@playwright/test';
import {join} from 'node:path';
import {ROOT} from '../playwright.config';

test.beforeAll(async({request})=>{
  // Le dépôt peut déjà être enregistré (le parcours de `explorer.spec.ts` le fait aussi) : on s'en tient à l'état obtenu.
  const project=await request.post('/api/projects', {data:{name:'Boutique', path:join(ROOT, 'shop')}});
  const same=(path:string)=>path.split(/[\\/]/).join('/');
  const known=project.ok()?await project.json():(await (await request.get('/api/projects')).json())
    .find((item:{path:string})=>same(item.path)===same(join(ROOT, 'shop')));
  expect(known?.id).toBeTruthy();
  const scans=await (await request.get(`/api/projects/${known.id}/scans`)).json();
  if(!scans.length)expect((await request.post(`/api/projects/${known.id}/scans`)).status()).toBe(201);
});

async function openRoute(page:Page){
  await page.goto('/#/explorer');
  await page.getByRole('textbox', {name:'Point de départ'}).fill('GET /ad');
  await page.getByRole('button', {name:/route GET \/admin\/users/}).click();
  await expect(page.locator('.explorer-canvas').first()).toBeVisible();
}

test('la zone du graphe suit son contenu jusqu’à un plafond configurable', async({page})=>{
  await page.setViewportSize({width:1280, height:800});
  await openRoute(page);
  const zone=page.locator('.explorer-layers').first(), canvas=zone.locator('.explorer-canvas');
  const measure=()=>zone.evaluate(node=>({box:node.clientHeight, content:node.scrollHeight,
    max:getComputedStyle(node).maxHeight, overflow:getComputedStyle(node).overflowY}));
  const drawn=()=>canvas.evaluate(node=>({width:node.style.width, height:node.style.height}));
  const before=await drawn();

  // Plafond par défaut : 120vh, soit 960 px pour une fenêtre de 800 px ; sous ce plafond, aucun ascenseur.
  const initial=await measure();
  expect(initial.max).toBe('960px');
  expect(initial.overflow).toBe('auto');
  expect(initial.box).toBeLessThanOrEqual(960);
  if(initial.content<=960)expect(initial.content, 'aucun ascenseur sous le plafond').toBeLessThanOrEqual(initial.box);
  else expect(initial.box, 'au-delà, la zone s’arrête au plafond').toBeGreaterThanOrEqual(900);

  // Plafond réduit : le contenu le dépasse, l'ascenseur vertical apparaît et la zone ne dépasse pas le plafond.
  await page.evaluate(()=>document.documentElement.style.setProperty('--explorer-graph-max-height', '120px'));
  const capped=await measure();
  expect(capped.box).toBeLessThanOrEqual(120);
  expect(capped.content, 'ascenseur au-delà du plafond').toBeGreaterThan(capped.box);

  // Plafond relevé : l'ascenseur disparaît, la zone reprend la hauteur de son contenu.
  await page.evaluate(()=>document.documentElement.style.setProperty('--explorer-graph-max-height', '5000px'));
  const raised=await measure();
  expect(raised.content, 'plus d’ascenseur sous le plafond relevé').toBeLessThanOrEqual(raised.box);
  await page.evaluate(()=>document.documentElement.style.removeProperty('--explorer-graph-max-height'));
  expect((await measure()).box).toBe(initial.box);
  expect(await drawn(), 'le dessin calculé par le moteur de disposition est inchangé').toEqual(before);
});

for(const [width, height] of [[1440, 900], [1100, 800], [800, 900], [480, 900]]){
  test(`champs alignés, rien ne déborde, aucun nœud coupé à ${width} px`, async({page})=>{
    await page.setViewportSize({width, height});
    await openRoute(page);
    // Les trois champs sont alignés et à la même hauteur quand ils partagent une rangée.
    const boxes=await page.locator('.explorer-search-fields > label').evaluateAll(nodes=>nodes.map(node=>{
      const field=node.querySelector('input,select')!.getBoundingClientRect();
      return {top:Math.round(field.top), height:Math.round(field.height)};
    }));
    expect(boxes).toHaveLength(3);
    expect(new Set(boxes.map(box=>box.height)).size, 'mêmes hauteurs').toBe(1);
    if(width>=1100)expect(new Set(boxes.map(box=>box.top)).size, 'une seule rangée').toBe(1);
    // Aucun défilement horizontal de la page, ni de l'en-tête.
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
    expect(await page.locator('.explorer-head, .explorer-search, .explorer-bar').evaluateAll(nodes=>
      nodes.every(node=>node.scrollWidth<=node.clientWidth+1)), 'aucun intitulé ne déborde').toBe(true);
    // Tout nœud dessiné reste dans le tracé : la hauteur de la zone n'en coupe aucun (on y accède en défilant).
    const inside=await page.locator('.explorer-layers').first().evaluate(zone=>{
      const canvas=zone.querySelector('.explorer-canvas') as HTMLElement, frame=canvas.getBoundingClientRect();
      return Array.from(canvas.querySelectorAll('.chain-node')).every(node=>{
        const box=node.getBoundingClientRect();
        return box.left>=frame.left-1&&box.right<=frame.right+1&&box.top>=frame.top-1&&box.bottom<=frame.bottom+1;
      })&&zone.scrollHeight>=canvas.offsetHeight;
    });
    expect(inside).toBe(true);
    // Les onglets, l'export, la légende et le panneau restent accessibles.
    for(const name of ['Appels', 'Chaîne', 'Couches', 'Liste'])await expect(page.getByRole('button', {name, exact:true})).toBeVisible();
    await expect(page.getByRole('button', {name:'Exporter en image (PNG)'})).toBeVisible();
    await expect(page.getByText('Légende')).toBeVisible();
    await expect(page.getByRole('region', {name:'Ce que la vue ne montre pas'})).toBeVisible();
  });
}
