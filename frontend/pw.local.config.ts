// Configuration locale, non commitée : le chromium déjà installé, sans téléchargement ; l'API est lancée par run_e2e.sh.
import {defineConfig} from '@playwright/test';
import base from './playwright.config';

export default defineConfig({
  ...base,
  use:{...base.use, launchOptions:{executablePath:'C:/Users/Admin/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe'}},
  webServer:[{command:'npx vite --host 127.0.0.1 --port 4173 --strictPort', url:'http://127.0.0.1:4173', timeout:60_000, reuseExistingServer:true,
    env:{TAXO_API:'http://127.0.0.1:8100'}}],
});
