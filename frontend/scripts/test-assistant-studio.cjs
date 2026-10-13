// Smoke tests of the real Assistant and shared navigation with local API fixtures.
// Requires esbuild, playwright, Tailwind 3 and the frontend React/Radix dependencies.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');const {build}=require('esbuild');const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=process.env.ASSISTANT_PREVIEW_DIR||fs.mkdtempSync(path.join(require('node:os').tmpdir(),'assistant-studio-'));fs.mkdirSync(out,{recursive:true});
const mock=(n,s)=>{fs.writeFileSync(path.join(out,n+'.js'),s);return path.join(out,n+'.js');};
const aliases={
 '@/context/AuthContext':mock('auth',`export const useAuth=()=>({user:{user_id:'demo',account_type:'pro_business',role:'pro',preferences:{}}});`),
 '@/context/I18nContext':mock('i18n',`export const useI18n=()=>({lang:new URLSearchParams(location.search).get('lang')||'fr',t:(k,f)=>f||k});export const LangToggle=()=>null;`),
 '@/context/BillingContext':mock('billing',`export const useBilling=()=>({tier:'pro'});`),
 '@/components/UpgradeLock':mock('upgrade',`export const UpgradeLock=()=>null;`),
 '@/components/PushToggle':mock('push',`export default function PushToggle(){return null;}`),
 '@/context/PermissionContext':mock('permissions',`export const usePermissions=()=>({can:()=>true});`),
 '@/components/ConfirmProvider':mock('confirm',`export const useConfirm=()=>async()=>false;`),
 '@/components/chantiers/ChantierContextBar':mock('chantier',`export const useChantierContext=()=>({chantier:null});export const ChantierContextBar=()=>null;`),
 '@/lib/api':mock('api',`
  export const API='/api';export const eur=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR'});export const eur2=eur;
  const reply='Voici les points à vérifier avant de chiffrer.\\n\\n| Poste | Donnée disponible | À préciser |\\n|---|---|---|\\n| Murs | Surface fournie : 65 m² | État des supports |\\n| Peinture | Finition velours demandée | Teinte et nombre de couches |\\n\\n**Prochaine étape :** compléter les informations manquantes, puis préparer le devis modifiable.';
  const conversations=[{conversation_id:'conv-demo',title:'Rénovation · Appartement',active_docs:[],active_plans:[],messages:[{message_id:'m1',role:'user',content:'Aide-moi à préparer le devis de peinture pour cet appartement.'},{message_id:'m2',role:'assistant',content:reply,model:'fixture',response_mode:'thorough'}],jobs:[]},{conversation_id:'conv-mail',title:'Courrier au client',messages:[],jobs:[],active_docs:[],active_plans:[]}];window.__writes=[];window.__conversations=conversations;
  export const api={get:async(url)=>{let data={};
   if(url==='/assistant/conversations')data=conversations;
   else if(url==='/assistant/jobs')data={jobs:conversations.flatMap(c=>c.jobs||[]).filter(j=>['preparing','queued','running'].includes(j.status))};
   else if(url==='/assistant/settings')data={web_enabled:true};
   else if(url==='/assistant/preferences')data=[];
   else if(url==='/assistant/documents')data=[{doc_id:'doc-1',filename:'CCTP rénovation.pdf',kind:'document',mime:'application/pdf'}];
   else if(url==='/takeoffs')data={plans:[{plan_id:'plan-1',filename:'Plan du rez-de-chaussée.pdf'}]};
   else if(url.endsWith('/state/emails'))data=[];
   else if(url.endsWith('/state'))data=null;
   else if(url.endsWith('/calculations'))data={calculations:[]};
   else if(url.startsWith('/assistant/conversations/'))data=conversations.find(c=>c.conversation_id===url.split('/').at(-1));
   return {data};},
   post:async(url,body)=>{window.__writes.push({url,body});if(url==='/assistant/conversations'){const c={conversation_id:'conv-new',title:'Nouvelle conversation',messages:[],jobs:[],active_docs:[],active_plans:[]};conversations.push(c);return{data:c};}
    if(url==='/assistant/jobs'){const c=conversations.find(c=>c.conversation_id===body.conversation_id);
     if(window.__background){await new Promise(resolve=>{window.__acceptJob=()=>{const job={job_id:'job-background',conversation_id:c.conversation_id,request_id:body.request_id,status:'running',live:{role:'assistant',content:'Lecture des pièces…'}};c.jobs=[job];c.messages=[...c.messages,{role:'user',message_id:'mb-user',content:body.text,request_id:body.request_id}];window.__finishJob=()=>{job.status='completed';c.messages=[...c.messages,{role:'assistant',message_id:'mb-answer',content:'Le travail est terminé en arrière-plan.',request_id:body.request_id}];};resolve();};});return{data:{job_id:'job-background'}};}
    c.messages=[...c.messages,{role:'user',message_id:'m3',content:body.text,request_id:body.request_id},{role:'assistant',message_id:'m4',content:reply,response_mode:body.response_mode}];return{data:{job_id:'job-local'}};}
    if(url==='/assistant/documents')return{data:{doc_id:'doc-upload',filename:'notes.txt',mime:'text/plain',kind:'document'}};
    return{data:{}};},put:async()=>({data:{}}),delete:async()=>({data:{}})};
  export const uploadPlan=async()=>({plan_id:'plan-upload',filename:'plan.pdf'});
 `),
 '@':path.join(root,'src')
};
fs.writeFileSync(path.join(out,'entry.jsx'),`
import ${JSON.stringify(path.join(root,'src/index.css'))};import ${JSON.stringify(path.join(root,'src/styles/workspace.css'))};
import React from 'react';import {createRoot} from 'react-dom/client';import {MemoryRouter,Routes,Route,Link} from 'react-router-dom';
import Assistant from ${JSON.stringify(path.join(root,'src/pages/Assistant.jsx'))};
import {AssistantActivity} from ${JSON.stringify(path.join(root,'src/components/assistant/AssistantActivity.jsx'))};
import WorkspaceNavigation from ${JSON.stringify(path.join(root,'src/components/workspace/WorkspaceNavigation.jsx'))};
const shell=new URLSearchParams(location.search).has('shell');
createRoot(document.getElementById('root')).render(<MemoryRouter initialEntries={['/assistant']}><div className="workspace">{shell&&<WorkspaceNavigation/>}<div className={shell?"workspace-content":""}><main style={{maxWidth:1450,margin:'auto',padding:16}}><p style={{fontSize:11,color:'#60695f',marginBottom:12}}>Aperçu de l’Assistant BTP · données de démonstration</p><nav style={{display:"flex",gap:16,fontSize:11,marginBottom:12}}><Link to="/ailleurs" data-testid="fixture-leave">Autre page</Link><Link to="/assistant" data-testid="fixture-return">Assistant</Link>{!shell&&<AssistantActivity/>}</nav><Routes><Route path="/assistant" element={<Assistant/>}/><Route path="/ailleurs" element={<p data-testid="fixture-away">Autre page de la plateforme</p>}/></Routes></main></div></div></MemoryRouter>);
`);
async function main(){
 await build({entryPoints:[path.join(out,'entry.jsx')],outdir:out,entryNames:'app',bundle:true,jsx:'automatic',loader:{'.js':'jsx'},nodePaths:(process.env.NODE_PATH||'').split(path.delimiter).filter(Boolean),alias:aliases,define:{'process.env.NODE_ENV':'"test"'}});
 execFileSync(process.execPath,[require.resolve('tailwindcss/lib/cli.js'),'-i',path.join(out,'app.css'),'-o',path.join(out,'styles.css'),'-c',path.join(root,'tailwind.config.js')],{cwd:root,stdio:'pipe'});
 fs.writeFileSync(path.join(out,'index.html'),'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><title>Assistant BTP</title></head><body><div id="root"></div><script src="/app.js"></script></body></html>');
 const server=http.createServer((req,res)=>{const name={'/':'index.html','/app.js':'app.js','/styles.css':'styles.css'}[req.url.split('?')[0]];if(!name){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',name.endsWith('.css')?'text/css':name.endsWith('.js')?'text/javascript':'text/html');res.end(fs.readFileSync(path.join(out,name)));});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(8000);
  const url='http://127.0.0.1:'+server.address().port;await page.goto(url);await page.getByTestId('assistant-mark').waitFor();await page.screenshot({path:path.join(out,'assistant-accueil.png')});
  await page.getByTestId('assistant-prompt-quote').click();assert.ok((await page.getByTestId('assistant-input').inputValue()).length>20);assert.equal(await page.evaluate(()=>window.__writes.length),0);
  await page.getByTestId('assistant-options-toggle').click();await page.getByTestId('assistant-response-mode').selectOption('fast');await page.getByTestId('assistant-web-enabled').uncheck();
  await page.getByTestId('assistant-doc-select').selectOption('doc-1');await page.getByTestId('assistant-plan-select').selectOption('plan-1');await page.getByTestId('assistant-active-plan-plan-1').waitFor();assert.equal(await page.getByTestId('assistant-plan-select').locator('option[value="plan-1"]').evaluate(e=>e.disabled),true);
  await page.getByTestId('assistant-options-close').click();assert.match(await page.getByTestId('assistant-mode-summary').innerText(),/Rapide[\s\S]*Web désactivé/);
  await page.getByTestId('assistant-input').fill('Prépare un devis pour ces travaux.');await page.getByTestId('assistant-input').press('Enter');await page.getByTestId('assistant-msg-assistant-1').waitFor();
  const payload=await page.evaluate(()=>window.__writes.find(x=>x.url==='/assistant/jobs').body);assert.equal(payload.response_mode,'fast');assert.equal(payload.web_enabled,false);assert.deepEqual(payload.doc_ids,['doc-1']);assert.deepEqual(payload.plan_ids,['plan-1']);
  await page.getByTestId('assistant-msg-assistant-1-correct').click();assert.match(await page.getByTestId('assistant-input').inputValue(),/Corriger/);
  await page.getByTestId('assistant-attach-btn').click();let chosen=page.waitForEvent('filechooser');await page.getByTestId('assistant-import-document').click();await chosen;
  await page.getByTestId('assistant-attach-btn').focus();await page.keyboard.press('Enter');await page.getByTestId('assistant-existing-files').click();assert.equal(await page.getByTestId('assistant-context').isVisible(),true);await page.getByTestId('assistant-options-close').click();
  await page.getByTestId('assistant-remove-doc-doc-1').click();assert.equal(await page.getByTestId('assistant-active-doc-doc-1').count(),0);
  await page.getByTestId('assistant-history-search-desktop').fill('courrier');assert.equal(await page.getByTestId('assistant-conv-desktop-conv-demo').count(),0);await page.getByTestId('assistant-history-search-desktop').fill('');
  await page.getByTestId('assistant-conv-desktop-conv-demo').click();await page.getByTestId('assistant-msg-assistant-1').waitFor();await page.getByTestId('assistant-input').fill('');await page.screenshot({path:path.join(out,'assistant-conversation.png')});
  for(const width of [390,320]){
   await page.setViewportSize({width,height:844});
   const dims=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth,bottom:document.querySelector('[data-testid="assistant-send-btn"]').getBoundingClientRect().bottom,height:innerHeight,offenders:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=='fixed').slice(0,6).map(e=>({cls:e.className,test:e.dataset.testid}))}));console.log('Mobile',dims);assert.ok(dims.scroll<=width);assert.ok(dims.bottom<dims.height);
   await page.getByTestId('assistant-history-open').click();await page.getByTestId('assistant-history-dialog').waitFor();assert.equal(await page.getByTestId('assistant-new-mobile').isVisible(),true);await page.keyboard.press('Escape');await page.waitForFunction(()=>document.activeElement?.dataset.testid==='assistant-history-open');
   await page.getByTestId('assistant-options-toggle').click();assert.equal(await page.getByTestId('assistant-doc-select').isVisible(),true);await page.getByTestId('assistant-options-close').click();
   if(width===390)await page.screenshot({path:path.join(out,'assistant-mobile.png')});
  }
  await page.setViewportSize({width:1440,height:1000});await page.evaluate(()=>document.documentElement.classList.add('dark'));await page.screenshot({path:path.join(out,'assistant-sombre.png')});
  
  await page.goto(url+'/?shell=1');
  await page.getByTestId('assistant-new-desktop').click();
  await page.waitForFunction(()=>document.querySelector('[data-testid="assistant-input"]')?.value==='');
  await page.evaluate(()=>{window.__background=true;window.__writes=[];});
  await page.getByTestId('assistant-input').fill('Vérifie ce dossier pendant que je prépare mon devis.');
  await page.getByTestId('assistant-send-btn').click();
  await page.waitForFunction(()=>typeof window.__acceptJob==='function');
  await page.getByTestId('fixture-leave').click();await page.getByTestId('fixture-away').waitFor();
  await page.evaluate(()=>window.__acceptJob());
  await page.getByTestId('assistant-global-activity').waitFor();
  await page.setViewportSize({width:320,height:844});
  console.log('Header overflow',await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth})));
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(out,'assistant-background-mobile.png')});
  await page.setViewportSize({width:1440,height:1000});
  assert.equal(await page.evaluate(()=>localStorage.getItem('assistant-last-demo')),'conv-new');
  await page.getByTestId('assistant-global-activity').click();
  await page.getByTestId('assistant-background-status').waitFor();
  assert.match(await page.getByTestId('assistant-background-status').innerText(),/changez de page/);
  await page.getByTestId('fixture-leave').click();
  await page.evaluate(()=>window.__finishJob());
  await page.getByTestId('assistant-global-activity').waitFor({state:'hidden'});
  await page.getByTestId('fixture-return').click();
  await page.getByText('Le travail est terminé en arrière-plan.').waitFor();
  assert.equal(await page.evaluate(()=>window.__writes.filter(x=>x.url==='/assistant/jobs').length),1);
  assert.equal(await page.evaluate(()=>window.__writes.filter(x=>x.url.includes('/cancel')).length),0);
  // An interrupted response saved as a message must still expose status and resume.
  await page.getByTestId('fixture-leave').click();
  await page.evaluate(()=>{const c=window.__conversations.find(c=>c.conversation_id==='conv-new');c.jobs[0].status='interrupted';c.messages.at(-1).interrupted=true;});
  await page.getByTestId('fixture-return').click();
  await page.getByTestId('assistant-job-resume-job-background').waitFor();
  assert.match(await page.getByTestId('assistant-job-status-job-background').innerText(),/interrompu/);
  console.log('Background UI: leave before acknowledgement, global activity, restore running/result, no duplicate/cancel, visible interruption passed.');
  await page.goto(url+'/?lang=pt');await page.getByTestId('assistant-new-desktop').click();await page.getByTestId('assistant-mark').waitFor();assert.match(await page.locator('.assistant-welcome h2').innerText(),/sua obra/);assert.match(await page.getByTestId('assistant-attach-btn').innerText(),/Anexar/);
  assert.deepEqual(errors,[]);console.log('Assistant actual page: starters, context, local job payload, correction, files, history, keyboard, mobile 390/320, PT and dark render passed.');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
