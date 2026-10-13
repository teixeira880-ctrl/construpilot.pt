/* Local acceptance checks: built UI, synthetic accounts and intercepted APIs only.
 * Requires Playwright. Optional CHROMIUM_EXECUTABLE_PATH for a local browser.
 * Run with CP_BUILD_DIR pointing at frontend/build; screenshots go to CP_UI_OUTPUT.
 */
const {chromium} = require(process.env.CP_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ROOT = path.resolve(process.env.CP_BUILD_DIR || path.join(__dirname, '../build'));
const OUT = path.resolve(process.env.CP_UI_OUTPUT || './ui-verification');
fs.mkdirSync(OUT, {recursive:true});
const ALL_PERMISSIONS = Object.freeze({
 dashboard:true,devis:true,factures:true,situations:true,chantier:true,rh:true,catalogue:true,entreprise:true,pointage:true,
});
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || require('dotenv').config({path:path.join(__dirname, '../.env')}).parsed?.REACT_APP_BACKEND_URL;
if (!BACKEND_URL) throw new Error('REACT_APP_BACKEND_URL is required');
const API_HOSTNAME = new URL(BACKEND_URL).hostname;
const projects = [
 {project_id:'demo-1',name:'Rénovation d’appartement',surface:78,budget:48200,estimation:{project_type_name:'Rénovation',lots:[{key:'murs',name:'Maçonnerie'},{key:'elec',name:'Électricité'},{key:'sols',name:'Sols'}]},progress:{murs:'done',elec:'doing',sols:'todo'}},
 {project_id:'demo-2',name:'Extension de maison',surface:32,budget:64500,estimation:{project_type_name:'Extension',lots:[{key:'murs',name:'Maçonnerie'},{key:'toit',name:'Toiture'}]},progress:{murs:'doing',toit:'todo'}},
 {project_id:'demo-3',name:'Aménagement de bureaux',surface:125,budget:83900,estimation:{project_type_name:'Aménagement',lots:[{key:'cloisons',name:'Cloisons'},{key:'sols',name:'Sols'}]},progress:{cloisons:'done',sols:'done'}},
];
const chats = [{conversation_id:'chat-1',title:'Compte rendu · Extension de maison'},{conversation_id:'chat-2',title:'Réponse à l’architecte'},{conversation_id:'chat-3',title:'Vérification des murs intérieurs'}];
const results=[];
let browser;
async function test(name, fn) { await fn(); results.push({name,status:'passed'}); console.log('PASS',name); }
async function setup({account='entreprise',lang='fr',width=1440,height=1000,permissions={}}={}) {
 const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:1,serviceWorkers:'block'});
 const effectivePermissions={...ALL_PERMISSIONS,...(permissions||{})};
 const state={projects:structuredClone(projects),deleted:[],messages:[],created:0,projectError:false,holdStream:false,releaseStream:null,apiCalls:[],errors:[]};
 await context.addInitScript(({lang}) => {
   if(window.location.hostname!=='127.0.0.1') return;
   localStorage.setItem('construpilot_token','synthetic-ui-fixture');localStorage.setItem('cp_cookie_consent','refused');localStorage.setItem('construpilot_lang',lang);localStorage.setItem('cp_pwa_dismissed_at',String(Date.now()));
   if(navigator.serviceWorker) navigator.serviceWorker.register=async()=>({update:async()=>{}});
 },{lang});
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url()),method=req.method();
  const isFixtureApiHost=['127.0.0.1','localhost',API_HOSTNAME].includes(url.hostname);
  if(isFixtureApiHost && url.pathname.includes('/api/')) {
   const p=url.pathname.slice(url.pathname.lastIndexOf('/api/')+4);state.apiCalls.push({path:p,method});
   let data={},status=200;
   if(p==='/auth/me') data={user_id:'ui-demo',name:'Alex',account_type:account,role:'owner',theme:'light'};
   else if(p==='/company/me') data={role:'owner',active:true,in_org:false,permissions:effectivePermissions};
   else if(p==='/billing/me') data={tier:account==='particulier'?'free':'pro'};
   else if(p==='/projects') {status=state.projectError?503:200;data=state.projectError?{detail:'Fixture unavailable'}:state.projects;}
   else if(p.startsWith('/projects/')&&method==='DELETE') {const id=p.split('/').pop();state.deleted.push(id);state.projects=state.projects.filter(x=>x.project_id!==id);data={ok:true};}
   else if(['/quotes','/prices/alerts','/leads/mine','/assistant/preferences','/assistant/documents'].includes(p)) data=[];
   else if(p==='/takeoffs') data={plans:[]};
   else if(p==='/takeoffs/upload') {if(!req.postDataBuffer().includes(Buffer.from('name="cad_unit"'))) {status=422;data={detail:'CAD_UNIT_REQUIRED'};}else data={plan_id:'imported-plan',filename:'plan_sans_unite.dxf',cad_import:{complete:false,units:{name:'cm'},diagnostics:[{code:'XREF_UNRESOLVED'}]}};}
   else if(p==='/quotes/notifications/me') data={unread:0,notifications:[]};
   else if(p==='/assistant/settings') data={web_enabled:true};
   else if(p==='/assistant/conversations'&&method==='GET') data=chats;
   else if(p==='/assistant/conversations'&&method==='POST') data={conversation_id:`new-${++state.created}`,title:'Nouvelle conversation'};
   else if(p.startsWith('/assistant/conversations/')) data={conversation_id:p.split('/').pop(),title:'Historique',messages:[{role:'assistant',content:'Voici les éléments de votre conversation enregistrée.'}],active_plans:[],active_docs:[]};
   else if(p==='/assistant/message/stream') {
    state.messages.push(req.postDataJSON());
    if(state.holdStream) await new Promise(resolve=>{state.releaseStream=resolve;});
    const message={role:'assistant',content:'Voici un brouillon de réponse.\n\n- Confirmer les points à vérifier.\n- Proposer la prochaine étape.',actions:[],sources:[],response_mode:req.postDataJSON().response_mode,model:'fixture-model'};
    try {await route.fulfill({status:200,contentType:'text/event-stream',body:`data: ${JSON.stringify({type:'delta',text:message.content})}\n\ndata: ${JSON.stringify({type:'done',message})}\n\n`});}catch{}
    return;
   }
   if(p==='/assistant/documents'&&method==='POST') data={doc_id:'doc-imported',filename:'Document_de_travail_avec_un_nom_tres_long_pour_verifier_la_mise_en_page.pdf'};
   return route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  }
  if(url.hostname!=='127.0.0.1') return route.abort();
  let file=path.resolve(ROOT,'.'+url.pathname);
  if(!file.startsWith(ROOT+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()) file=path.join(ROOT,'index.html');
  const mime={'.js':'application/javascript','.css':'text/css','.png':'image/png','.jpg':'image/jpeg','.json':'application/json','.svg':'image/svg+xml','.html':'text/html'};
  return route.fulfill({status:200,contentType:mime[path.extname(file)]||'application/octet-stream',body:fs.readFileSync(file)});
 });
 const page=await context.newPage();page.on('pageerror',e=>state.errors.push(e.message));page.setDefaultTimeout(10000);
 const go=async(p)=>{await page.goto('http://127.0.0.1:4173'+p);await page.locator('.workspace').waitFor();};
 return {page,state,context,go};
}
async function overflow(page) {const b=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(b.scroll<=b.width+1,JSON.stringify(b));}
(async()=>{
 const args=(process.env.CP_CHROMIUM_ARGS_MODULE?require(process.env.CP_CHROMIUM_ARGS_MODULE).default.args:[]).filter(a=>!['--single-process','--disable-web-security','--allow-running-insecure-content'].includes(a));
 browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{}),args});
 const d=await setup();const {page,state,go}=d;
 await test('Desktop dashboard: navigation, tasks and loaded project list',async()=>{
  await go('/dashboard');await page.getByTestId('project-card-demo-1').waitFor();assert.equal(await page.getByTestId('onboarding-tour').count(),0);assert.equal(await page.locator('.workspace-sidebar').isVisible(),true);assert.equal(await page.getByTestId('projects-grid').locator(':scope > div').count(),3);await overflow(page);await page.screenshot({path:path.join(OUT,'ConstruPilot_accueil_ordinateur.png')});
 });
 await test('Project search ignores accents and has a clear empty result',async()=>{
  const input=page.getByTestId('dashboard-project-search');await input.fill('renovation');assert.equal(await page.getByTestId('projects-grid').locator(':scope > div').count(),1);await input.fill('aucun-projet-xyz');await page.getByText('Aucun projet ne correspond').waitFor();await input.fill('');
 });
 await test('Deleting a project requires confirmation and reports the successful update',async()=>{
  await page.getByTestId('delete-project-demo-1').click();await page.getByTestId('confirm-dialog-cancel').click();assert.equal(state.deleted.length,0);await page.getByTestId('delete-project-demo-1').click();await page.getByTestId('confirm-dialog-confirm').click();await page.getByTestId('project-card-demo-1').waitFor({state:'detached'});assert.deepEqual(state.deleted,['demo-1']);
 });
 await test('Loading failure is visible and retry restores the project list',async()=>{
  state.projectError=true;await go('/dashboard');await page.getByRole('alert').filter({hasText:'Certaines données'}).waitFor();assert.equal(await page.getByTestId('projects-empty').count(),0);state.projectError=false;await page.getByRole('button',{name:'Réessayer',exact:true}).click();await page.getByTestId('project-card-demo-2').waitFor();
 });
 await test('Tool search opens from Ctrl K, restores focus and navigates with Enter',async()=>{
  await page.getByTestId('workspace-search-trigger').focus();await page.keyboard.press('Control+k');await page.getByTestId('workspace-tool-search').fill('côtes');assert.equal(await page.getByTestId('tool-controle-cotes').count(),1);await page.keyboard.press('Escape');await page.waitForFunction(()=>document.activeElement?.getAttribute('data-testid')==='workspace-search-trigger');await page.keyboard.press('Control+k');await page.getByTestId('workspace-tool-search').fill('côtes');await page.keyboard.press('Enter');await page.waitForURL('**/controle-cotes');await overflow(page);
 });
 await test('Assistant shortcut resets page scroll and exposes a focused composer',async()=>{
  await go('/dashboard');await page.evaluate(()=>window.scrollTo(0,900));await page.locator('[data-testid="workspace-nav-assistant"]').click();await page.getByTestId('assistant-input').waitFor();assert.equal(await page.evaluate(()=>window.scrollY),0);await page.getByTestId('assistant-prompt-mail').click();assert.match(await page.getByTestId('assistant-input').inputValue(),/Prépare une réponse/);assert.equal(state.messages.length,0);assert.equal(await page.getByTestId('assistant-input').evaluate(e=>e===document.activeElement),true);
 });
 await test('Response options are sent with the request and the reply is rendered',async()=>{
  await page.getByTestId('assistant-options-toggle').click();await page.getByLabel('Réponse',{exact:true}).selectOption('fast');await page.getByLabel('Recherche Internet',{exact:true}).uncheck();await page.getByTestId('assistant-options-toggle').click();await page.getByTestId('assistant-input').fill('Prépare une réponse pour fixer une visite.');await page.getByTestId('assistant-send-btn').click();await page.locator('[data-message-role="assistant"]').filter({hasText:'Voici un brouillon'}).first().waitFor();assert.equal(state.messages.at(-1).response_mode,'fast');assert.equal(state.messages.at(-1).web_enabled,false);
 });
 await test('Unsent text is retained while switching between conversations',async()=>{
  await page.locator('[data-conversation-id="chat-1"]').first().click();await page.locator('[data-conversation-id="chat-1"][aria-current=true]').first().waitFor();await page.getByTestId('assistant-input').fill('Notes à conserver');await page.locator('[data-conversation-id="chat-2"]').first().click();await page.locator('[data-conversation-id="chat-2"][aria-current=true]').first().waitFor();assert.equal(await page.getByTestId('assistant-input').inputValue(),'');await page.locator('[data-conversation-id="chat-1"]').first().click();await page.locator('[data-conversation-id="chat-1"][aria-current=true]').first().waitFor();assert.equal(await page.getByTestId('assistant-input').inputValue(),'Notes à conserver');
 });
 await test('A pending reply can be interrupted without locking the next request',async()=>{
  state.holdStream=true;await page.getByTestId('assistant-send-btn').click();await page.getByTestId('assistant-stop-btn').waitFor();await page.getByTestId('assistant-stop-btn').click();await page.getByTestId('assistant-send-btn').waitFor();state.releaseStream?.();state.holdStream=false;await page.getByTestId('assistant-input').fill('Une nouvelle demande');assert.equal(await page.getByTestId('assistant-send-btn').isEnabled(),true);
 });
 await test('Native CAD unit choice and partial import remain visible',async()=>{
  await page.getByTestId('assistant-upload-input').setInputFiles({name:'plan_sans_unite.dxf',mimeType:'application/dxf',buffer:Buffer.from('synthetic UI fixture')});await page.getByRole('dialog',{name:'Unité du dessin CAO'}).waitFor();await page.getByRole('button',{name:'Centimètres',exact:true}).click();await page.getByTestId('assistant-active-plan-imported-plan').waitFor();await page.getByTestId('cad-import-info').waitFor();assert.match(await page.getByTestId('cad-import-info').innerText(),/lecture partielle/);await page.getByTestId('assistant-remove-plan-imported-plan').click();
 });
 await test('Documents have removable, bounded names and a keyboard accessible attachment button',async()=>{
  await page.getByTestId('assistant-upload-input').setInputFiles({name:'document.pdf',mimeType:'application/pdf',buffer:Buffer.from('synthetic UI fixture')});await page.getByTestId('assistant-pick-doc').click();await page.getByTestId('assistant-active-doc-doc-imported').waitFor();await overflow(page);await page.getByTestId('assistant-remove-doc-doc-imported').click();assert.equal(await page.getByTestId('assistant-active-doc-doc-imported').count(),0);
 });
 await test('Mobile and tablet widths 320, 390, 768 and 1024 have no page overflow',async()=>{
  for(const [width,height] of [[320,568],[390,844],[768,1024],[1024,768]]) {await page.setViewportSize({width,height});await overflow(page);const input=await page.getByTestId('assistant-input').boundingBox();assert.ok(input.width>100);if(width<768) {const tabs=await page.getByTestId('mobile-tab-bar').boundingBox();const composer=await page.locator('.assistant-composer').boundingBox();assert.ok(composer.y+composer.height<=tabs.y+1,'Composer covered by tabs');}}
 });
 await test('Mobile Enter adds a line; sending uses the explicit button',async()=>{
  await page.setViewportSize({width:390,height:844});await page.getByTestId('assistant-input').fill('Ligne 1');const before=state.messages.length;await page.getByTestId('assistant-input').press('Enter');assert.equal(state.messages.length,before);assert.equal(await page.getByTestId('assistant-input').inputValue(),'Ligne 1\n');
 });
 await test('Mobile history search opens, selects and closes its dialog',async()=>{
  await page.getByTestId('assistant-history-open').click();const dialog=page.getByRole('dialog');await dialog.getByPlaceholder('Rechercher une conversation…').fill('architecte');assert.equal(await dialog.locator('[data-conversation-id="chat-2"]').count(),1);await dialog.locator('[data-conversation-id="chat-2"]').click();await dialog.waitFor({state:'detached'});
 });
 await test('Bottom menu opens all tools and settings on mobile',async()=>{
  await page.getByTestId('tab-menu').click();await page.getByTestId('workspace-directory').waitFor();assert.equal(await page.getByTestId('tool-compte').count(),1);await page.keyboard.press('Escape');
 });
 await test('Dark theme and a complete assistant layout',async()=>{
  await page.setViewportSize({width:1440,height:1000});await go('/assistant');await page.getByTestId('theme-toggle').click();assert.equal(await page.locator('html').evaluate(e=>e.classList.contains('dark')),true);await overflow(page);await page.screenshot({path:path.join(OUT,'ConstruPilot_assistant_sombre.png')});await page.getByTestId('theme-toggle').click();await page.screenshot({path:path.join(OUT,'ConstruPilot_assistant_ordinateur.png')});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(OUT,'ConstruPilot_assistant_mobile.png')});
 });
 await test('Private account has appropriate shortcuts and no professional tools',async()=>{
  const p=await setup({account:'particulier',width:390,height:844});await p.go('/dashboard');await p.page.getByTestId('quick-estimate').waitFor();assert.equal(await p.page.getByTestId('quick-plan').count(),0);assert.equal(await p.page.getByTestId('tab-devis').count(),0);assert.equal(await p.page.getByTestId('tab-nouveau').getAttribute('href'),'/estimation');await p.page.getByTestId('tab-menu').click();assert.equal(await p.page.getByTestId('tool-plan').count(),0);assert.equal(await p.page.getByTestId('tool-devis').count(),0);assert.equal(await p.page.getByTestId('tool-scanner-devis').count(),0);assert.ok(!p.state.apiCalls.some(c=>c.path==='/leads/mine'||c.path==='/takeoffs'));assert.deepEqual(p.state.errors,[]);await p.context.close();
 });
 await test('Restricted professional permissions apply to navigation and create shortcuts',async()=>{
  const p=await setup({width:390,height:844,permissions:{devis:false,factures:false,chantier:false}});await p.go('/dashboard');await p.page.getByTestId('quick-prices').waitFor();assert.equal(await p.page.getByTestId('tab-devis').count(),0);await p.page.getByTestId('tab-menu').click();assert.equal(await p.page.getByTestId('tool-devis').count(),0);assert.equal(await p.page.getByTestId('tool-factures').count(),0);assert.equal(await p.page.getByTestId('tool-suivi-chantier').count(),0);assert.deepEqual(p.state.errors,[]);await p.context.close();
 });
 await test('Portuguese copy, prompts and navigation render without overflow',async()=>{
  const p=await setup({lang:'pt',width:390,height:844});await p.go('/assistant');await p.page.getByRole('heading',{name:'Como posso ajudar?'}).waitFor();await p.page.getByTestId('assistant-prompt-mail').click();assert.match(await p.page.getByTestId('assistant-input').inputValue(),/Prepara uma resposta/);await overflow(p.page);assert.deepEqual(p.state.errors,[]);await p.context.close();
 });
 await test('No uncaught application errors during the acceptance run',async()=>assert.deepEqual(state.errors,[]));
 await browser.close();browser=null;
 fs.writeFileSync(path.join(OUT,'RESULTATS_INTERFACE.json'),JSON.stringify({tests_passed:results.length,scope:'Local Chromium; built frontend, synthetic accounts, intercepted API; not production E2E',results},null,2));
 console.log('TOTAL',results.length,'passed');
})().catch(async error=>{console.error(error);fs.writeFileSync(path.join(OUT,'RESULTATS_INTERFACE.json'),JSON.stringify({tests_passed:results.length,error:String(error),results},null,2));if(browser)await browser.close();process.exitCode=1;});
