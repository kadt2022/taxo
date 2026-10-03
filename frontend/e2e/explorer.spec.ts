// Rechercher une ancre, développer, consulter une preuve : dans Chromium, contre une API Taxo réelle (TAXO-01J § 9).
import {expect, test} from '@playwright/test';
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
