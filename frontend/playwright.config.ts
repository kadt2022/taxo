// Le parcours de bout en bout de l'explorateur (TAXO-01J, décision 12) : une API Taxo réelle sur un dépôt scénarisé,
// le portail servi par Vite, Chromium. Un seul parcours : les cas sont couverts par les tests du portail et du backend.
import {defineConfig} from '@playwright/test';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

export const ROOT=join(tmpdir(), 'taxo-e2e-explorer');
const API=8100, PORTAL=4173;

export default defineConfig({
  testDir:'e2e', timeout:60_000, retries:0, reporter:'list',
  use:{baseURL:`http://127.0.0.1:${PORTAL}`, trace:'retain-on-failure'},
  webServer:[
    {command:`python e2e/serve.py ${ROOT} ${API}`, url:`http://127.0.0.1:${API}/api/projects`, timeout:120_000, stdout:'pipe'},
    {command:`npx vite --host 127.0.0.1 --port ${PORTAL} --strictPort`, url:`http://127.0.0.1:${PORTAL}`, timeout:60_000,
      env:{TAXO_API:`http://127.0.0.1:${API}`}}],
});
