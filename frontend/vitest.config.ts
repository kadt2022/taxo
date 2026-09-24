import {defineConfig} from 'vitest/config';
// Seuls les modules charges par les tests sont mesures ; les autres ne sont pas declares couverts a zero.
export default defineConfig({test:{include:['src/**/*.test.ts','src/**/*.test.tsx'],coverage:{provider:'v8',reporter:['text','lcov']}}});
