// Le parcours de l'explorateur dans Chromium, contre une API Taxo réelle (TAXO-01J § 9) : une ancre, une preuve, l'export.
import {expect, test, type Locator} from '@playwright/test';
import {join} from 'node:path';
import {ROOT} from '../playwright.config';

test.beforeAll(async({request})=>{
  const project=await request.post('/api/projects', {data:{name:'Boutique', path:join(ROOT, 'shop')}});
  expect(project.ok()).toBe(true);
  const {id}=await project.json();
  expect((await request.post(`/api/projects/${id}/scans`)).status()).toBe(201);
});

test('rechercher une ancre, développer, consulter une preuve', async({page})=>{
  await page.goto('/#/explorer');
  const search=page.getByRole('textbox', {name:'Point de départ'});
  await expect(search).toBeVisible();
  // Ce que l'explorateur demande, une fois la page affichée (la coque du portail lit l'état de Minia à son ouverture).
  const called:string[]=[];
  page.on('request', request=>called.push(new URL(request.url()).pathname));
  await search.fill('GET /ad');
  await page.getByRole('button', {name:/route GET \/admin\/users/}).click();
  await expect(page.getByText(/éléments?, \d+ nœuds?\./)).toBeVisible();
  await page.getByRole('button', {name:'Liste'}).click();
  await page.getByRole('region', {name:'Niveau 2'}).getByRole('button', {name:'Développer module admin-app'}).click();
  await expect(page.getByRole('region', {name:'Niveau 3'})).toBeVisible();
  await page.getByRole('button', {name:/^route GET \/admin\/users est traité par symbole/}).click();
  const panel=page.getByRole('region', {name:'Détail du lien'});
  await expect(panel).toContainText('Observé dans le code');
  await expect(panel.getByRole('list', {name:'Preuves'})).toContainText('UserAdminController.java:');
  expect(called.length).toBeGreaterThan(0);
  expect(called.filter(path=>path.startsWith('/api/')&&!path.endsWith('/taxo-query'))).toEqual([]);
});

// Choisir un symbole du graphe ouvre sa tuile de code dans le panneau : le code lu au commit de l'analyse, la méthode choisie
// surlignée dans son type. Le dessin du graphe n'est pas touché.
test('choisir un symbole montre son code, la méthode surlignée', async({page})=>{
  await page.goto('/#/explorer');
  await page.getByRole('textbox', {name:'Point de départ'}).fill('GET /ad');
  await page.getByRole('button', {name:/route GET \/admin\/users/}).click();
  await expect(page.getByText(/éléments?, \d+ nœuds?\./)).toBeVisible();
  await page.locator('.chain-node.tone-symbol').first().click();
  const panel=page.getByRole('region', {name:'Nœud choisi'});
  await expect(panel.locator('.type-pill')).toHaveText('symbole');
  const tile=panel.getByRole('region', {name:'Tuile de code'});
  await expect(tile).toBeVisible();
  await expect(tile.locator('.code-head code')).toContainText('.java');
  await expect(tile.locator('.code-line.selected').first()).toBeVisible();
  await expect(tile.locator('.code-text').first()).not.toHaveText('');
  await expect(panel.getByRole('button', {name:/^Copier la référence/})).toBeVisible();
  await expect(page.locator('details.explorer-gaps')).not.toHaveAttribute('open', '');
});

/** Le rapport de contraste WCAG 2.x entre le texte d'un élément et son fond, lus dans le navigateur. */
const contrast=(element:Locator)=>element.evaluate(node=>{
  const style=getComputedStyle(node);
  const luminance=(color:string)=>{
    const [r, g, b]=color.match(/\d+(\.\d+)?/g)!.slice(0, 3).map(value=>{
      const channel=Number(value)/255;
      return channel<=0.03928?channel/12.92:((channel+0.055)/1.055)**2.4;
    });
    return 0.2126*r+0.7152*g+0.0722*b;
  };
  const [light, dark]=[luminance(style.color), luminance(style.backgroundColor)].sort((a, b)=>b-a);
  return (light+0.05)/(dark+0.05);
});

// Le bouton d'export est posé sur la page du portail, pas sur le diagramme : il garde les couleurs des autres boutons du
// portail et reste lisible dans les deux thèmes de l'appareil (WCAG AA : contraste d'au moins 4,5:1, au survol aussi).
for(const colorScheme of ['light', 'dark'] as const){
  test(`le bouton d’export reste lisible en thème ${colorScheme==='light'?'clair':'sombre'}`, async({page})=>{
    await page.emulateMedia({colorScheme});
    await page.goto('/#/explorer');
    await page.getByRole('textbox', {name:'Point de départ'}).fill('GET /ad');
    await page.getByRole('button', {name:/route GET \/admin\/users/}).click();
    const exporter=page.getByRole('button', {name:'Exporter en image (PNG)'});
    await expect(exporter).toBeVisible();
    await expect.poll(()=>contrast(exporter)).toBeGreaterThanOrEqual(4.5);
    await exporter.hover();
    await expect.poll(()=>contrast(exporter), {message:'au survol'}).toBeGreaterThanOrEqual(4.5);
  });
}

// --- La mise en page : des champs alignés, une zone du graphe qui suit son contenu jusqu'à un plafond configurable, rien de
// coupé ni de débordant aux tailles de fenêtre courantes. Le dessin (nœuds, liens, couleurs) vient du moteur de disposition
// et n'est jamais modifié par ces tests. Ils partagent la mise en place du fichier : un seul enregistrement du projet.

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
    if(width>=1280)expect(new Set(boxes.map(box=>box.top)).size, 'une seule rangée').toBe(1);
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
    await expect(page.getByRole('group', {name:'Légende'})).toBeVisible();
    await expect(page.getByRole('button', {name:/^Ce que la vue ne montre pas/})).toBeVisible();
  });
}

// La barre d'outils du graphe : le zoom met à l'échelle le dessin déjà calculé, il ne le recalcule jamais ; l'ajustement tient
// la largeur de la zone ; le recentrage ramène l'ancre ; l'agrandissement lève la hauteur maximale ; la languette rouvre le panneau.
test('la barre d’outils du graphe : zoom, ajustement, recentrage, agrandissement, panneau', async({page})=>{
  await page.setViewportSize({width:1280, height:800});
  await openRoute(page);
  const canvas=page.locator('.explorer-canvas').first(), zone=page.locator('.explorer-layers').first();
  const drawn=()=>canvas.evaluate(node=>({width:node.style.width, height:node.style.height}));
  const before=await drawn();
  const shown=()=>canvas.evaluate(node=>node.getBoundingClientRect().width);
  const natural=await shown();

  await page.getByRole('button', {name:'Zoom avant'}).click();
  expect(await shown(), 'zoom avant').toBeGreaterThan(natural*1.2);
  await page.getByRole('button', {name:'Zoom arrière'}).click();
  await page.getByRole('button', {name:'Zoom arrière'}).click();
  expect(await shown(), 'zoom arrière').toBeLessThan(natural*0.9);
  expect(await drawn(), 'le dessin calculé par le moteur de disposition est inchangé').toEqual(before);

  await page.getByRole('button', {name:'Ajuster à la largeur'}).click();
  const width=await zone.evaluate(node=>node.clientWidth);
  expect(await shown(), 'ajusté : le dessin tient dans la largeur de la zone').toBeLessThanOrEqual(width);

  await page.getByRole('button', {name:'Recentrer sur l’ancre'}).click();
  await expect(page.locator('.chain-node.anchor').first()).toBeVisible();

  const limited=await zone.evaluate(node=>getComputedStyle(node).maxHeight);
  await page.getByRole('button', {name:'Agrandir la zone'}).click();
  expect(await zone.evaluate(node=>getComputedStyle(node).maxHeight), 'la hauteur maximale est levée').toBe('none');
  await page.getByRole('button', {name:'Réduire la zone'}).click();
  expect(await zone.evaluate(node=>getComputedStyle(node).maxHeight)).toBe(limited);

  // Le panneau latéral est replié en languette ; elle le rouvre, et il se referme.
  const side=page.locator('#explorer-side');
  await expect(side).toBeHidden();
  await page.getByRole('button', {name:/^Ce que la vue ne montre pas/}).click();
  await expect(side).toBeVisible();
  await expect(page.getByRole('region', {name:'Ce que la vue ne montre pas'})).toBeVisible();
  await page.getByRole('button', {name:'Masquer le panneau'}).click();
  await expect(side).toBeHidden();
});

// Le bouton de thème du cadre : il part du thème de l'appareil, bascule le cadre (barre d'outils, légende, tracé) entre sombre
// et clair, et le choix est retenu au rechargement. Dans les deux fonds, le texte reste lisible (WCAG AA).
for(const device of ['dark', 'light'] as const){
  test(`le bouton de thème bascule le cadre du graphe, parti du thème ${device==='dark'?'sombre':'clair'} de l’appareil`, async({page})=>{
    await page.emulateMedia({colorScheme:device});
    await openRoute(page);
    const frame=page.locator('.chain-frame').first();
    const background=()=>frame.locator('.chain-scroll').evaluate(node=>getComputedStyle(node).backgroundImage);
    const dark=(css:string)=>/rgb\(23, 32, 29\)/.test(css);
    await expect(frame).toHaveAttribute('data-theme', device);
    expect(dark(await background()), 'fond de départ').toBe(device==='dark');
    const other=device==='dark'?'light':'dark';
    await page.getByRole('button', {name:other==='light'?'Passer le graphe en clair':'Passer le graphe en sombre'}).click();
    await expect(frame).toHaveAttribute('data-theme', other);
    expect(dark(await background()), 'fond après bascule').toBe(other==='dark');
    const exporter=page.getByRole('button', {name:'Exporter en image (PNG)'});
    await expect.poll(()=>contrast(exporter), {message:'export lisible après bascule'}).toBeGreaterThanOrEqual(4.5);
    await page.reload();
    await page.locator('.explorer-canvas').first().waitFor();
    await expect(page.locator('.chain-frame').first(), 'le choix est retenu au rechargement').toHaveAttribute('data-theme', other);
  });
}

// L'ajustement à la largeur fait tenir le dessin dans la zone, même sur un écran étroit : son plancher n'est pas celui du zoom manuel.
test('ajuster à la largeur fait tenir le dessin sur un écran étroit', async({page})=>{
  await page.setViewportSize({width:420, height:900});
  await openRoute(page);
  const canvas=page.locator('.explorer-canvas').first(), zone=page.locator('.explorer-layers').first();
  await page.getByRole('button', {name:'Ajuster à la largeur'}).click();
  const [shown, available]=[await canvas.evaluate(node=>node.getBoundingClientRect().width), await zone.evaluate(node=>node.clientWidth)];
  expect(shown, 'le dessin tient dans la largeur de la zone').toBeLessThanOrEqual(available);
  expect(await zone.evaluate(node=>node.scrollWidth<=node.clientWidth+1), 'aucun défilement horizontal après l’ajustement').toBe(true);
});
