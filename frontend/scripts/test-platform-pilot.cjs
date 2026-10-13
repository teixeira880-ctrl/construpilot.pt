// Real agent UI and global indicator, isolated services; no production calls.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { build } = require('esbuild');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const out = process.env.PILOT_PREVIEW_DIR || fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'construpilot-pilot-'));
fs.mkdirSync(out, { recursive: true });
const fixture = (name, code) => { const p = path.join(out, name + '.jsx'); fs.writeFileSync(p, code); return p; };
const alias = {
  '@/context/AuthContext': fixture('auth', `const user={user_id:'demo',account_type:'particulier'};export const useAuth=()=>({user});`),
  'sonner': fixture('toast', `window.__toasts=[];export const toast=Object.fromEntries(['success','error','info'].map(kind=>[kind,(message)=>window.__toasts.push({kind,message})]));`),
  '@/lib/api': fixture('api', `
window.__writes=[];window.__runs=[];window.__checks=[];window.__undoFails=false;
export const api={
 async get(url,{params}={}){
  if(url==='/agents/catalog')return{data:{agents:[{key:'supervise',name:'Pilote ConstruPilot',desc:'Vérifiez vos documents et corrigez les valeurs recalculables.',icon:'ShieldCheck',needs_plans:false}]}};
  if(url==='/takeoffs')return{data:{plans:[]}};
  if(url==='/agents/runs')return{data:{runs:structuredClone(window.__runs)}};
  if(url==='/agents/active')return{data:{runs:structuredClone(window.__runs.filter(r=>['queued','running'].includes(r.status)))}};
  if(url.endsWith('/checks'))return{data:{checks:structuredClone(window.__checks.slice(params?.offset||0,(params?.offset||0)+50)),next_offset:null}};
  throw new Error('Unexpected GET '+url);
 },
 async post(url,body){
  window.__writes.push({url,body});
  if(url==='/agents/plan')return{data:{run:{run_id:'run1',steps:[{key:'inspect',label:'Contrôler les données enregistrées'},{key:'repair',label:'Corriger et vérifier'}],warnings:[]},defaults:{}}};
  if(url.endsWith('/launch')){window.__runs=[{run_id:'run1',agent:'supervise',agent_name:'Pilote ConstruPilot',status:'queued',created_at:'2026-10-10T10:00:00Z'}];return{data:{queued:true}};}
  if(url.endsWith('/cancel')){window.__runs[0].cancel_requested=true;return{data:{ok:true}};}
  if(url.endsWith('/undo')){if(window.__undoFails)throw{response:{data:{detail:'Le document a changé depuis la correction'}}};window.__checks[0].restored=true;return{data:{restored:true}};}
  throw new Error('Unexpected POST '+url);
 }
};
window.__finish=(status='done')=>{window.__runs[0].status=status;window.__runs[0].error=status==='error'?'Traitement interrompu':null;
window.__runs[0].result={kind:'supervision',mode:'repair',checked:2,corrected:1,needs_review:1};
window.__checks=[{kind:'quote',id:'quote1',label:'Rénovation — devis',checked_elements:12,corrections:3,applied:true,issues:[]},{kind:'plan',id:'plan1',label:'Plan du rez-de-chaussée',checked_elements:38,corrections:0,applied:false,issues:[{code:'missing_scale',message:'Échelle fiable manquante : recalcul bloqué',path:'measurements.1'}]}];};
`),
  '@': path.join(root, 'src'),
};
fixture('entry', `
import React from 'react';import{createRoot}from'react-dom/client';import{MemoryRouter,Routes,Route,Link,useLocation}from'react-router-dom';
import '@/index.css';import '@/styles/workspace-design.css';import '@/styles/workspace-ambient.css';
import AgentsHub from '@/pages/AgentsHub';import{AgentsRunning}from'@/components/AgentsRunning';
function Destination(){return <p data-testid="destination">{useLocation().pathname}</p>}
createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={['/agents']}><nav style={{padding:16,display:'flex',gap:24}}><Link to="/agents">Agents</Link><Link to="/other">Autre page</Link></nav><Routes><Route path="/agents" element={<AgentsHub/>}/><Route path="*" element={<Destination/>}/></Routes><AgentsRunning/></MemoryRouter>);
`);
async function main() {
  await build({ entryPoints: [path.join(out, 'entry.jsx')], outdir: out, entryNames: 'app', bundle: true, jsx: 'automatic', loader: { '.js': 'jsx' }, nodePaths: [path.join(root, 'node_modules'), ...(process.env.NODE_PATH || '').split(path.delimiter).filter(Boolean)], alias, define: { 'process.env.NODE_ENV': '"test"' } });
  execFileSync(process.execPath, [require.resolve('tailwindcss/lib/cli.js'), '-i', path.join(out, 'app.css'), '-o', path.join(out, 'styles.css'), '-c', path.join(root, 'tailwind.config.js')], { cwd: root, stdio: 'pipe' });
  fs.writeFileSync(path.join(out, 'index.html'), '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script src="/app.js"></script></body></html>');
  const server = http.createServer((req, res) => { const filename = { '/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css' }[req.url]; if (!filename) { res.writeHead(404); return res.end(); } res.setHeader('Content-Type', filename.endsWith('css') ? 'text/css' : filename.endsWith('js') ? 'text/javascript' : 'text/html'); res.end(fs.readFileSync(path.join(out, filename))); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined, headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, reducedMotion: 'reduce' });
    page.setDefaultTimeout(12000);
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:' + server.address().port);
    await page.getByTestId('agent-card-supervise').click();
    assert.equal(await page.getByTestId('agent-plan-list').count(), 0);
    await page.getByLabel(/Contrôler seulement/).check();
    await page.getByTestId('agent-propose-btn').click();
    await page.getByTestId('agent-launch-btn').click();
    assert.equal(await page.evaluate(() => window.__writes.find(w => w.url.endsWith('/launch')).body.mode), 'audit');
    await page.getByTestId('agents-running-indicator').waitFor();
    await page.getByRole('link', { name: 'Autre page', exact: true }).click();
    await page.getByTestId('destination').waitFor();
    assert.ok(await page.getByTestId('agents-running-indicator').isVisible());
    await page.evaluate(() => window.__finish('error'));
    await page.waitForFunction(() => window.__toasts.some(t => t.kind === 'error' && t.message.includes('interrompue')));
    assert.equal(await page.evaluate(() => window.__toasts.filter(t => t.kind === 'success' && t.message.includes('contrôle')).length), 0);
    await page.getByRole('link', { name: 'Agents', exact: true }).click();
    await page.getByTestId('supervisor-result-run1').waitFor();
    await page.getByTestId('supervisor-details-run1').click();
    await page.getByTestId('supervisor-checks').waitFor();
    assert.match(await page.getByTestId('supervisor-checks').innerText(), /Échelle fiable manquante/);
    await page.evaluate(() => { window.__undoFails = true; });
    await page.getByTestId('supervisor-undo-quote1').click();
    await page.waitForFunction(() => window.__toasts.some(t => t.message.includes('document a changé')));
    assert.ok(await page.getByTestId('supervisor-undo-quote1').isVisible());
    await page.evaluate(() => { window.__undoFails = false; });
    await page.getByTestId('supervisor-undo-quote1').click();
    await page.getByText('Correction annulée', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(out, 'pilot-desktop.jpg'), type: 'jpeg', quality: 92 });
    for (const width of [390, 320, 768]) {
      await page.setViewportSize({ width, height: 844 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Horizontal overflow');
      if (width === 390) await page.screenshot({ path: path.join(out, 'pilot-mobile.jpg'), type: 'jpeg', quality: 92 });
    }
    await page.getByTestId('agent-card-supervise').click();
    assert.ok(await page.getByLabel(/Contrôler et corriger automatiquement/).isChecked());
    await page.getByTestId('agent-propose-btn').click(); await page.getByTestId('agent-launch-btn').click();
    await page.getByTestId('agent-cancel-run1').click();
    await page.waitForFunction(() => window.__runs[0].cancel_requested === true);
    assert.ok(await page.getByTestId('agent-cancel-run1').isDisabled());
    assert.deepEqual(errors, []);
    console.log('Pilot UI passed: individual access, audit/repair modes, persistent navigation, truthful failure notice, result details, undo/conflict, cancellation, 320/390/768/1440 px, no page errors.');
    console.log('Previews:', out);
  } finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
