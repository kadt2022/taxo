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
