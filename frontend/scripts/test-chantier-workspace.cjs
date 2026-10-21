// Real dossier/forecast/pilot/portal components with isolated services. Never calls production.
const fs = require('node:fs'), path = require('node:path'), http = require('node:http'), assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {build} = require('esbuild'), {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const out = process.env.WORKSPACE_PREVIEW_DIR || fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'construpilot-dossier-'));
fs.mkdirSync(out, {recursive: true});
const fixture = (name, code) => {const p=path.join(out,name+'.jsx');fs.writeFileSync(p,code);return p;};
const stub = names => names.map(n=>`export const ${n}=()=> <div>${n}</div>;`).join('\n');
const alias = {
 '@':path.join(root,'src'),
 'sonner':fixture('toast',`window.__toasts=[];export const toast=Object.fromEntries(['success','error','info'].map(k=>[k,m=>window.__toasts.push({k,m})]));`),
 '@/components/ConfirmProvider':fixture('confirm',`export const useConfirm=()=>async()=>false;`),
 '@/components/chantiers/SharePanels':fixture('shares',stub(['ShareParticipantsPanel','MilestonesPanel','PublishToggle'])),
 '@/components/chantiers/ChantierFormDialog':fixture('form',stub(['ChantierFormDialog'])+`export const CHANTIER_STATUS={en_cours:'En cours'};`),
 '@/components/chantiers/ReceptionPanel':fixture('reception',stub(['ReceptionPanel'])),
 '@/components/chantiers/PhotoCompareDialog':fixture('photos',stub(['PhotoCompareDialog'])),
 '@/components/portal/Messaging':fixture('messages',stub(['ChantierMessagesPanel'])),
 '@/components/portal/Issues':fixture('issues',stub(['ChantierIssuesPanel'])),
 '@/components/portal/PortalTabs':fixture('portal-tabs',stub(['PortalMessages','PortalIssues'])),
 '@/components/portal/PortalDocuments':fixture('portal-docs',stub(['PortalDocuments'])),
 '@/components/portal/PortalReceptions':fixture('portal-recept',stub(['PortalReceptions'])),
 '@/components/portal/PortalPlanning':fixture('portal-planning',stub(['PortalPlanning'])),
 '@/components/voice/VoiceButtons':fixture('voice',stub(['ListenButton'])),
 'axios':fixture('axios',`export default {create:()=>({async get(url){return{data:url==='/me'?{participant:{participant_id:'client'},chantiers:[]}:{chantier:{name:'Votre maison, pas à pas',ref:'CP-DEMO',address:'Paris'},company:{name:'ConstruPilot'},participant:{role:'client',permissions:{quotes:true,chat:true,report_issue:true}},milestones:[],reports:[],photos:[],progress_pct:40}};},async post(){return{data:{}};}})};`),
 '@/lib/api':fixture('api',`
window.__writes=[]; window.__conflict=false; window.__run=false;
const quote={doc_id:'q1',title:'Rénovation de la maison',status:'draft',doc_type:'quote',totals:{ttc:216},created_at:'2026-10-10'};
const dossier={chantier_id:'c1',name:'Maison des Tilleuls',status:'en_cours',city:'Versailles',client:{client_id:'client1'},client_name:'Mme Martin',documents:[quote],plans:[{plan_id:'p1',filename:'RDC — version B.pdf',kind:'pdf'}],plans_pro:[],diagnostics:[],reports:[],reserves:[],photos:[],milestones:[],kpis:{quotes:1,signed_ttc:0,invoiced_ttc:0,paid:0,open_reserves:0}};
let costs={cost_version:0,cost_settings:{},scope:{quotes:1,signed:0,using_signed_only:false,selected_ids:['q1'],available_quotes:[{doc_id:'q1',label:'Devis rénovation'}]},totals:{vente_ht:180,cost_prev_ht:80,margin_ht:100,margin_pct:55.6,coverage:{complete:true}},forecast:{final_cost_ht:null,margin_ht:null,over_budget_ht:null},labor:{hours_validated:2,hours_total:2,rate_used:null,cost_est:null},purchases:{orders:1,items:2,priced_total:20,unpriced_items:0},real_cost_known_ht:20,purchase_entries:[{order_id:'o1',supplier:'Matériaux du chantier',items:2,amount:20,engaged:true,status:'confirmé',delivery:{},delivery_version:0}],notes:['Les commandes au brouillon sont exclues.']};
export const eur=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});
export const api={async get(url){
 if(url.endsWith('/pilot'))return{data:{summary:{unchecked:0,stale:1,needs_review:1,checked:0},resources:[{kind:'plan',id:'p1',label:'RDC — version B.pdf',state:'stale'},{kind:'quote',id:'q1',label:'Devis rénovation',state:'needs_review',issues:1}],runs:window.__run?[{run_id:'r1',status:'queued'}]:[],note:'Contrôles de cohérence sur données enregistrées. Les métrés réels restent à vérifier.'}};
 if(url.endsWith('/costs'))return{data:structuredClone(costs)};
 if(url.endsWith('/inbox'))return{data:{unread:{},new_issues:0}};
 if(url==='/chantiers/c1')return{data:dossier};
 throw Error('Unexpected GET '+url);
 },async post(url,body){window.__writes.push({url,body});if(url==='/agents/plan')return{data:{run:{run_id:'r1'}}};if(url.endsWith('/launch')){window.__run=true;return{data:{queued:true}};}throw Error('Unexpected POST '+url);},async put(url,body){window.__writes.push({url,body});if(window.__conflict)throw{response:{data:{detail:'Le budget a changé. Rechargez avant d’enregistrer.'}}};if(url.endsWith('/cost-settings')){costs={...costs,cost_version:1,cost_settings:body,forecast:{final_cost_ht:110,margin_ht:70,over_budget_ht:30},labor:{...costs.labor,rate_used:body.labor_rate,cost_est:60}};return{data:structuredClone(costs)};}if(url.endsWith('/delivery')){costs.purchase_entries[0].delivery=body;costs.purchase_entries[0].delivery_version++;return{data:{}};}throw Error('Unexpected PUT '+url);}};
`)
};
fixture('entry',`import React from 'react';import{createRoot}from'react-dom/client';import{MemoryRouter,Routes,Route,Link}from'react-router-dom';import '@/index.css';import '@/styles/workspace-design.css';import '@/styles/workspace-ambient.css';import ChantierDetail from '@/pages/ChantierDetail';import{PortalChantier}from'@/pages/Portal';createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={['/chantiers/c1']}><nav className="p-3 flex gap-5"><Link to="/chantiers/c1">Entreprise</Link><Link to="/espace/CP-DEMO?tab=messages">Client</Link></nav><Routes><Route path="/chantiers/:chantierId" element={<div className="p-4 max-w-6xl mx-auto"><ChantierDetail/></div>}/><Route path="/espace/:ref" element={<PortalChantier/>}/></Routes></MemoryRouter>);`);
async function main(){
 await build({entryPoints:[path.join(out,'entry.jsx')],outdir:out,entryNames:'app',bundle:true,jsx:'automatic',loader:{'.js':'jsx'},nodePaths:[...(process.env.NODE_PATH||'').split(path.delimiter).filter(Boolean)],alias,define:{'process.env.NODE_ENV':'"test"','process.env.REACT_APP_BACKEND_URL':'""'}});
 execFileSync(process.execPath,[require.resolve('tailwindcss/lib/cli.js'),'-i',path.join(out,'app.css'),'-o',path.join(out,'styles.css'),'-c',path.join(root,'tailwind.config.js')],{cwd:root,stdio:'pipe'});
 fs.writeFileSync(path.join(out,'index.html'),'<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><div id="root"></div><script src="/app.js"></script></html>');
 const server=http.createServer((req,res)=>{const file={'/':'index.html','/app.js':'app.js','/styles.css':'styles.css'}[req.url];if(!file){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',file.endsWith('css')?'text/css':file.endsWith('js')?'text/javascript':'text/html');res.end(fs.readFileSync(path.join(out,file)));});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,headless:true});const page=await browser.newPage({viewport:{width:1440,height:1050},reducedMotion:'reduce'});page.setDefaultTimeout(10000);const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:'+server.address().port);
 await page.getByTestId('pilot-count-stale').waitFor();assert.equal(await page.getByTestId('chantier-costs').count(),0);
 await page.getByTestId('chantier-pilot-launch').click();assert.deepEqual(await page.evaluate(()=>window.__writes.find(w=>w.url==='/agents/plan').body),{agent:'supervise',chantier_id:'c1'});assert.equal(await page.evaluate(()=>window.__writes.find(w=>w.url.endsWith('/launch')).body.mode),'audit');
 await page.getByTestId('chantier-tab-budget').click();await page.getByTestId('chantier-forecast').waitFor();await page.getByTestId('chantier-costs-rate').fill('30');await page.getByTestId('chantier-remaining').fill('30');await page.getByTestId('forecast-save').click();await page.waitForFunction(()=>window.__writes.some(w=>w.url.endsWith('cost-settings')));assert.equal(await page.evaluate(()=>window.__writes.find(w=>w.url.endsWith('cost-settings')).body.remaining_cost_ht),30);
 await page.evaluate(()=>window.__conflict=true);await page.getByTestId('forecast-save').click();await page.getByRole('alert').filter({hasText:'Le budget a changé'}).waitFor();await page.evaluate(()=>window.__conflict=false);
 await page.getByTestId('purchase-deliveries').locator('summary').click();await page.getByTestId('purchase-deliveries').locator('select').selectOption('partial');await page.getByLabel('Livraison prévue').fill('2026-10-16');await page.getByText('Enregistrer le suivi',{exact:true}).click();await page.waitForFunction(()=>window.__writes.some(w=>w.url.endsWith('/delivery')));
 for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:1050});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)){console.log(await page.evaluate(()=>[...document.querySelectorAll('*')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,12).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent.slice(0,80),width:e.getBoundingClientRect().width}))));await page.screenshot({path:require('node:path').join(out,'overflow.png')});throw Error('Budget overflow '+width);}if(width===390)await page.screenshot({path:path.join(out,'dossier-budget-mobile.jpg'),type:'jpeg',quality:90});}
 await page.getByTestId('chantier-tab-documents').click();await page.getByTestId('chantier-plans').waitFor();assert.equal(await page.getByRole('link',{name:'Sources & révisions'}).getAttribute('href'),'/analyse/p1');
 await page.getByTestId('chantier-tab-reception').click();await page.getByText('ReceptionPanel',{exact:true}).waitFor();
 await page.getByTestId('chantier-tab-overview').click();await page.getByTestId('chantier-pilot-launch').waitFor();assert.ok(await page.getByTestId('chantier-pilot-launch').isDisabled());
 await page.screenshot({path:path.join(out,'dossier-desktop.jpg'),type:'jpeg',quality:90});
 await page.getByRole('link',{name:'Client',exact:true}).click();await page.getByTestId('portal-overview').waitFor();for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Portal overflow '+width);if(width===390)await page.screenshot({path:path.join(out,'portal-mobile.jpg'),type:'jpeg',quality:90});}assert.deepEqual(errors,[]);console.log('Dossier UI passed: five sections, scoped background job across tabs, budget save/conflict, delivery save, revision link, client portal, 320/390/768/1440 px.');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
