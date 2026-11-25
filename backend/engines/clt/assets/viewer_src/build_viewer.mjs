// Reconstrói viewer_template.html (three.js empacotado, sem internet):
//   npm i three@0.170.0 esbuild && node build_viewer.mjs ../viewer_template.html
import { build } from 'esbuild';
import { readFileSync, writeFileSync } from 'node:fs';
const r = await build({ entryPoints: ['viewer.js'], bundle: true, minify: true, format: 'iife', write: false, target: 'es2020', legalComments: 'none' });
const js = r.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
const html = readFileSync('viewer.html', 'utf8').replace('<script>/*APP*/</script>', () => `<script>${js}</script>`);
writeFileSync(process.argv[2] || '../viewer_template.html', html);
console.log('viewer', (html.length / 1024).toFixed(0), 'KB');
