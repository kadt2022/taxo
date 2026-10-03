import { defineConfig } from 'vite';
// `TAXO_API` : l'API servie derrière `/api` ; le parcours de bout en bout lance la sienne sur un autre port.
export default defineConfig({server:{proxy:{'/api':process.env.TAXO_API??'http://127.0.0.1:8000'}}});
