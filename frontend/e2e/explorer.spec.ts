// Le parcours de l'explorateur dans Chromium, contre une API Taxo réelle (TAXO-01J § 9) : une ancre, une preuve, l'export.
import {expect, test, type Locator} from '@playwright/test';
import {execSync} from 'node:child_process';
import {mkdirSync, writeFileSync} from 'node:fs';
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
  // Le code est coloré comme dans un éditeur, et sa barre de défilement est sombre : aucune bande claire dans le bloc.
  await expect(tile.locator('.tk-keyword').first()).toBeVisible();
  await expect(tile.locator('.tk-annotation').first()).toBeVisible();
  expect(await tile.locator('.code-lines').evaluate(node=>getComputedStyle(node).colorScheme)).toBe('dark');
  await expect(panel.getByRole('button', {name:/^Ouvrir/})).toBeDisabled();
  // Le code occupe la place la plus haute du panneau, et le schéma reste la plus grande zone.
  const [codeTop, pillTop]=await Promise.all([tile.boundingBox(), panel.locator('.type-pill').boundingBox()]);
  expect(codeTop!.y, 'la tuile de code est au-dessus de l’identité du nœud').toBeLessThan(pillTop!.y);
  const [graph, side]=await Promise.all([page.locator('.chain-frame').boundingBox(), page.locator('.explorer-side').boundingBox()]);
  expect(graph!.width, 'le schéma reste plus grand que le panneau').toBeGreaterThan(side!.width);
  await expect(panel.getByRole('button', {name:/^Copier la référence/})).toBeVisible();
  await expect(page.locator('details.explorer-gaps')).not.toHaveAttribute('open', '');
});

// « Agrandir » ouvre une vraie fenêtre : la classe et son code en grand, ou le schéma en grand, sans menu ni barre latérale.
test('Agrandir la tuile de code ouvre une fenêtre avec la classe et son code, en grand', async({page})=>{
  await page.goto('/#/explorer');
  await page.getByRole('textbox', {name:'Point de départ'}).fill('GET /ad');
  await page.getByRole('button', {name:/route GET \/admin\/users/}).click();
  await expect(page.getByText(/éléments?, \d+ nœuds?\./)).toBeVisible();
  await page.locator('.chain-node.tone-symbol').first().click();
  await expect(page.getByRole('region', {name:'Tuile de code'})).toBeVisible();
  const [popup]=await Promise.all([page.waitForEvent('popup'), page.getByRole('button', {name:'Agrandir le code dans une nouvelle fenêtre'}).click()]);
  const tile=popup.getByRole('region', {name:'Tuile de code'});
  await expect(tile).toBeVisible();
  await expect(tile.locator('.code-line.selected').first()).toBeVisible();
  await expect(tile.locator('.code-head code')).toContainText('.java');
  expect(await popup.locator('aside, header.page-head, .explorer-head').count(), 'ni menu, ni barre latérale, ni recherche').toBe(0);
  await expect(popup.getByRole('button', {name:/^Agrandir/}), 'déjà dans la fenêtre').toHaveCount(0);
  expect(await tile.locator('.code-lines').evaluate(node=>getComputedStyle(node).maxHeight), 'toute la hauteur du code').toBe('none');
  expect(await tile.locator('.code-lines').evaluate(node=>Number.parseFloat(getComputedStyle(node).fontSize)), 'en grand').toBeGreaterThanOrEqual(15);
  await popup.close();
});

test('Agrandir le schéma ouvre une fenêtre avec le schéma, ses commandes et sa forme', async({page})=>{
  await openRoute(page);
  const [popup]=await Promise.all([page.waitForEvent('popup'), page.getByRole('button', {name:'Agrandir le schéma dans une nouvelle fenêtre'}).click()]);
  await expect(popup.locator('.plein-schema .chain-node.anchor')).toBeVisible();
  await expect(popup.getByRole('toolbar', {name:'Commandes du graphe'})).toBeVisible();
  expect(await popup.locator('aside, header.page-head, .explorer-head, .explorer-tabs, input').count(), 'rien d’autre que le schéma').toBe(0);
  await expect(popup.getByRole('button', {name:/^Agrandir/}), 'déjà dans la fenêtre').toHaveCount(0);
  const zone=popup.locator('.chain-scroll');
  const [height, view]=await Promise.all([zone.evaluate(node=>node.getBoundingClientRect().height), popup.evaluate(()=>window.innerHeight)]);
  expect(height, 'le schéma prend la hauteur de la fenêtre').toBeGreaterThan(view*0.5);
  await popup.getByRole('button', {name:'Zoom avant'}).click();
  await popup.close();
});

// La fenêtre rouvre le projet et l'analyse affichés, pas ceux que le portail choisirait par défaut (le premier de la liste). Le portail écrit
// le projet dans l'adresse sans que la page le sache : sans cela, la fenêtre cherchait le code dans un autre projet.
test('Agrandir ouvre le code du projet affiché, même s’il n’est pas le premier de la liste', async({page, request})=>{
  const folder=join(ROOT, 'second');
  mkdirSync(join(folder, 'src/main/java/com/acme/only'), {recursive:true});
  writeFileSync(join(folder, 'src/main/java/com/acme/only/OnlyHere.java'),
    'package com.acme.only;\n\npublic class OnlyHere {\n    public String ping() { return "pong"; }\n}\n');
  const git=(command:string)=>execSync(`git -C "${folder}" -c user.name=Taxo -c user.email=taxo@example.invalid ${command}`);
  git('init -q');
  git('add -A');
  git('commit -q -m "Un second projet"');
  const created=await request.post('/api/projects', {data:{name:'Second', path:folder}});
  expect(created.ok()).toBe(true);
  const {id}=await created.json();
  expect((await request.post(`/api/projects/${id}/scans`)).status()).toBe(201);
  await page.goto(`/#/explorer?projet=${id}`);
  // Naviguer dans le portail retire le projet de l'état de la page : il ne reste que dans la barre d'adresse (replaceState).
  await page.getByRole('link', {name:/^Analyses/}).click();
  await page.getByRole('link', {name:/^Explorer/}).click();
  await page.getByRole('textbox', {name:'Point de départ'}).fill('java:com.acme.only.OnlyHere#ping');
  await page.getByRole('button', {name:/OnlyHere#ping/}).click();
  await page.locator('.chain-node.anchor').first().click();
  await expect(page.getByRole('region', {name:'Tuile de code'})).toContainText('ping');
  const [popup]=await Promise.all([page.waitForEvent('popup'), page.getByRole('button', {name:'Agrandir le code dans une nouvelle fenêtre'}).click()]);
  await expect(popup.locator('.plein-code .code-line.selected').first()).toBeVisible();
  await expect(popup.locator('.plein-code')).toContainText('OnlyHere');
  await expect(popup.locator('.plein-code [role=alert]'), 'aucun refus : c’est bien le projet affiché').toHaveCount(0);
  await popup.close();
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
// la largeur de la zone ; le recentrage ramène l'ancre ; l'agrandissement ouvre le schéma dans une fenêtre ; la languette rouvre le panneau.
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

  await expect(page.getByRole('button', {name:'Agrandir le schéma dans une nouvelle fenêtre'}), 'l’agrandissement est une fenêtre').toBeVisible();

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
