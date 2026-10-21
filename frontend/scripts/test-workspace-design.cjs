// Real workspace pages with local service fixtures. No production API calls.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');const {build}=require('esbuild');const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),out=process.env.WORKSPACE_PREVIEW_DIR||fs.mkdtempSync(path.join(require('node:os').tmpdir(),'workspace-design-'));fs.mkdirSync(out,{recursive:true});
const mock=(name,src)=>{const p=path.join(out,name+'.jsx');fs.writeFileSync(p,src);return p;};
const aliases={
 '@/context/AuthContext':mock('auth',`import React,{createContext,useContext,useState} from 'react';const C=createContext(null);const free=new URLSearchParams(location.search).get('account')==='free';export function AuthFixture({children}){const[user,setUser]=useState({user_id:'demo',name:'Camille Martin',account_type:free?'particulier':'pro',role:'owner',nav_favorites:[]});return <C.Provider value={{user,setUser,logout:async()=>{}}}>{children}</C.Provider>;}export const useAuth=()=>useContext(C);`),
 '@/context/BillingContext':mock('billing',`export const useBilling=()=>({tier:new URLSearchParams(location.search).get('account')==='free'?'free':'pro'});`),
 '@/context/PermissionContext':mock('permissions',`export const usePermissions=()=>({loading:false,error:false,can:key=>!(new URLSearchParams(location.search).has('limited')&&['devis','factures'].includes(key))});`),
 '@/components/ConfirmProvider':mock('confirm',`export const useConfirm=()=>async()=>false;`),
 '@/components/PushToggle':mock('push',`export default function PushToggle(){return null;}`),
 '@/components/RevenueChart':mock('chart',`export const RevenueChart=()=>null;`),
 '@/lib/offlineProjects':mock('offline',`import {projects} from './api.jsx';export const fetchProjects=async()=>({list:projects});`),
 '@/lib/api':mock('api',`
 export const API='/api';export const DIFF_STYLE={};export const eur=n=>Number(n||0).toLocaleString('fr-FR',{style:'currency',currency:'EUR',maximumFractionDigits:0});export const eur2=eur;export const num=(n,d=0)=>Number(n||0).toLocaleString('fr-FR',{maximumFractionDigits:d});
 export const projects=[{project_id:'p1',name:'Rénovation · Appartement Monceau',budget:24500,surface:68,estimation:{project_type_name:'Rénovation intérieure'},progress:{preparation:'done',peinture:'doing',sols:'todo',finitions:'todo'}},{project_id:'p2',name:'Extension · Maison des Lilas',budget:82000,surface:42,estimation:{project_type_name:'Extension de maison'},progress:{terrassement:'done',fondations:'done',structure:'doing',couverture:'todo',facades:'todo'}},{project_id:'p3',name:'Salle de bains · Rue des Arts',budget:13800,surface:9,estimation:{project_type_name:'Salle de bains'},progress:{plomberie:'done',carrelage:'done',peinture:'done'}}];
 let clients=[{client_id:'c1',first_name:'Alice',last_name:'Durand',email:'alice@example.test',phone:'0100000000',address:'Adresse de démonstration',postal_code:'75017',city:'Paris'},{client_id:'c2',first_name:'Thomas',last_name:'Martin',company:'Atelier des Lilas',email:'atelier@example.test',phone:'0100000001',city:'Les Lilas'},{client_id:'c3',first_name:'Emma',last_name:'Laurent',email:'emma@example.test',city:'Paris'}];
 let sites=[{chantier_id:'s1',name:'Appartement Monceau',client_name:'Alice Durand',address:'Adresse de démonstration',city:'Paris',postal_code:'75017',status:'en_cours',counts:{documents:3,plans:2,plans_pro:1,diagnostics:0,reports:4}},{chantier_id:'s2',name:'Maison des Lilas',client_name:'Thomas Martin',city:'Les Lilas',status:'prospect',counts:{documents:2,plans:3,plans_pro:1,diagnostics:1,reports:0}},{chantier_id:'s3',name:'Salle de bains · Rue des Arts',client_name:'Emma Laurent',city:'Paris',status:'termine',counts:{documents:3,plans:1,plans_pro:0,diagnostics:0,reports:2}}];
 window.__writes=[];window.__running=false;
 export const api={get:async(url)=>{const u=new URL(url,'http://fixture');let data=[];
 if(u.pathname==='/chantiers')data={chantiers:sites.filter(c=>(!u.searchParams.get('q')||c.name.toLowerCase().includes(u.searchParams.get('q').toLowerCase()))&&(!u.searchParams.get('status')||c.status===u.searchParams.get('status')))};
 else if(u.pathname==='/clients')data={clients:clients.filter(c=>(c.first_name+' '+c.last_name+' '+(c.company||'')).toLowerCase().includes((u.searchParams.get('q')||'').toLowerCase()))};
 else if(url==='/takeoffs')data={plans:[]};
 else if(url==='/onboarding/status')data={client:true,chantier:true,plan:true,quote:true,page_published:true};
 else if(url==='/quotes/notifications/me')data={unread:1,notifications:[{notif_id:'n1',type:'assistant',title:'Réponse de l’assistant prête',message:'Dossier de démonstration',link:'/assistant',read:false}]};
 else if(url==='/assistant/jobs')data={jobs:window.__running?[{job_id:'j1',conversation_id:'demo',status:'running'}]:[]};
 else if(url==='/dashboard/today')data={date:'2026-10-09',running_analyses:0,next_action:{kind:'quote_followup',label:'Relancer le devis de l’appartement Monceau',url:'/devis'},items:[{kind:'quote_followup',label:'Relancer le devis Monceau',url:'/devis'},{kind:'plan_review',label:'Vérifier les mesures du plan des Lilas',url:'/plan'}]};
 else if(url==='/leads/mine')data=[{lead_id:'l1',name:'Demande de rénovation',viewed:true,budget:34000,status:'nouveau'}];
 else if(url==='/cotes/latest')data={latest:null};else if(url==='/pro/price-library')data={items:[]};
 return{data};},post:async(url,body)=>{window.__writes.push({url,body});if(url==='/clients'){const c={client_id:'new-client',...body};clients.push(c);return{data:c};}if(url==='/chantiers'){const c={chantier_id:'new-site',...body};sites.push(c);return{data:c};}return{data:{}};},put:async(url,body)=>{window.__writes.push({url,body});return{data:{}};},delete:async(url)=>{window.__writes.push({url});return{data:{}};}};
 `),
 '@':path.join(root,'src')
};
fs.writeFileSync(path.join(out,'entry.jsx'),`
import '@/index.css';import '@/styles/workspace.css';
import React from 'react';import{createRoot}from'react-dom/client';import{MemoryRouter,Routes,Route,useLocation}from'react-router-dom';
import{AuthFixture}from'@/context/AuthContext';import{I18nProvider}from'@/context/I18nContext';
import Dashboard from '@/pages/Dashboard';import Clients from '@/pages/Clients';import Chantiers from '@/pages/Chantiers';
import WorkspaceNavigation from '@/components/workspace/WorkspaceNavigation';import{WorkspaceFooter}from'@/components/workspace/WorkspaceFooter';import{MobileTabBar}from'@/components/pwa/MobileTabBar';

function Destination(){const l=useLocation();return <div className="surface p-8" data-testid="fixture-destination">{l.pathname}{l.search}</div>;}
function App(){return <div className="workspace"><WorkspaceNavigation/><div className="workspace-content"><main className="workspace-main" id="workspace-main" tabIndex={-1}><p style={{fontSize:10,color:'hsl(var(--muted-foreground))',marginBottom:18}}>Aperçu ConstruPilot · données de démonstration</p><Routes><Route path="/dashboard" element={<Dashboard/>}/><Route path="/clients" element={<Clients/>}/><Route path="/chantiers" element={<Chantiers/>}/><Route path="*" element={<Destination/>}/></Routes></main><WorkspaceFooter/></div><MobileTabBar/></div>;}
createRoot(document.getElementById('root')).render(<AuthFixture><I18nProvider><MemoryRouter initialEntries={[new URLSearchParams(location.search).get('route')||'/dashboard']}><App/></MemoryRouter></I18nProvider></AuthFixture>);
`);
async function main(){
 await build({entryPoints:[path.join(out,'entry.jsx')],outdir:out,entryNames:'app',bundle:true,jsx:'automatic',loader:{'.js':'jsx'},nodePaths:(process.env.NODE_PATH||'').split(path.delimiter).filter(Boolean),alias:aliases,define:{'process.env.NODE_ENV':'"test"'}});
 execFileSync(process.execPath,[require.resolve('tailwindcss/lib/cli.js'),'-i',path.join(out,'app.css'),'-o',path.join(out,'styles.css'),'-c',path.join(root,'tailwind.config.js')],{cwd:root,stdio:'pipe'});
 fs.writeFileSync(path.join(out,'index.html'),'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><title>ConstruPilot · aperçu</title></head><body><div id="root"></div><script src="/app.js"></script></body></html>');
 const server=http.createServer((req,res)=>{const uri=req.url.split('?')[0];const file={'/':'index.html','/app.js':'app.js','/styles.css':'styles.css'}[uri];if(uri==='/construpilot-icon.png'){res.setHeader('Content-Type','image/png');res.end(fs.readFileSync(path.join(root,'public/construpilot-icon.png')));return;}if(!file){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'text/html');res.end(fs.readFileSync(path.join(out,file)));});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100},reducedMotion:'reduce'});page.setDefaultTimeout(10000);const errors=[];page.on('pageerror',e=>errors.push(e.message));const url='http://127.0.0.1:'+server.address().port;
 const noOverflow=async()=>{const d=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(d.scroll<=d.width,JSON.stringify(d));};
 await page.goto(url);await page.getByTestId('project-card-p1').waitFor();assert.match(await page.getByTestId('stat-projects').innerText(),/3/);assert.equal(await page.getByTestId('workspace-nav-essentials').locator('a').count(),7);await noOverflow();await page.screenshot({path:path.join(out,'workspace-desktop.png'),fullPage:false});await page.screenshot({path:path.join(out,'workspace-copper-desktop.jpg'),type:'jpeg',quality:92});
 await page.getByTestId('today-more').click();await page.getByTestId('today-item-plan_review').waitFor();await page.getByTestId('today-more').click();
 await page.getByTestId('dashboard-project-search').fill('lilas');assert.equal(await page.getByTestId('project-card-p1').count(),0);await page.getByTestId('project-card-p2').waitFor();await page.getByTestId('dashboard-project-search-clear').click();
 await page.getByTestId('workspace-search-trigger').click();await page.waitForFunction(()=>document.activeElement?.dataset.testid==='workspace-tool-search');assert.equal(await page.locator('[data-tool-link]').count(),7);
 await page.getByTestId('workspace-tool-category').selectOption('billing');assert.ok(await page.getByTestId('tool-factures').isVisible());await page.getByTestId('workspace-tool-search').fill('escalier');assert.equal(await page.locator('[data-tool-link]').count(),1);await page.getByTestId('tool-fav-escaliers').click();await page.getByTestId('workspace-search-clear').click();await page.getByTestId('workspace-tool-category').selectOption('favorites');await page.getByTestId('tool-escaliers').waitFor();assert.equal(await page.locator('[data-tool-link]').count(),1);await page.keyboard.press('Escape');await page.waitForFunction(()=>document.activeElement?.dataset.testid==='workspace-search-trigger');await page.getByTestId('workspace-nav-escaliers').waitFor();
 await page.keyboard.press('Control+k');await page.getByTestId('workspace-tool-search').fill('chantiers');await page.keyboard.press('Enter');await page.getByTestId('chantiers-page').waitFor();
 await page.getByTestId('chantiers-filter-en_cours').click();await page.getByTestId('chantier-row-s2').waitFor({state:'hidden'});await page.getByTestId('chantiers-filter-all').click();await page.getByTestId('chantier-row-s2').waitFor();
 await page.getByTestId('workspace-nav-clients').click();await page.getByTestId('client-card-c1').waitFor();assert.equal(await page.getByTestId('client-card-c1').locator('a[href^="tel:"]').count(),1);
 for(const width of [390,320,768]){
   await page.setViewportSize({width,height:844});await noOverflow();
   await page.getByTestId('client-new-btn').click();await page.getByTestId('client-dialog').waitFor();const box=await page.getByTestId('client-dialog').boundingBox();assert.ok(box.x>=0&&box.y>=0&&box.x+box.width<=width+1&&box.y+box.height<=845);await page.getByTestId('client-save-btn').scrollIntoViewIfNeeded();assert.ok(await page.getByTestId('client-save-btn').isVisible());await page.setViewportSize({width,height:500});const shortBox=await page.getByTestId('client-dialog').boundingBox();assert.ok(shortBox.y>=0&&shortBox.y+shortBox.height<=501);await page.getByTestId('client-save-btn').scrollIntoViewIfNeeded();await page.getByTestId('client-dialog-close').click();await page.setViewportSize({width,height:844});
 }
 await page.setViewportSize({width:390,height:844});await page.getByTestId('tab-chantiers').click();await page.getByTestId('chantier-row-s1').waitFor();await noOverflow();await page.screenshot({path:path.join(out,'workspace-chantiers-mobile.png'),fullPage:true});
 await page.getByTestId('chantiers-new-btn').click();await page.getByTestId('chantier-name-input').fill('Chantier de test');await page.getByTestId('chantier-client-select').selectOption('c1');await page.getByTestId('chantier-form-submit').click();await page.getByTestId('fixture-destination').waitFor();assert.equal(await page.getByTestId('fixture-destination').innerText(),'/chantiers/new-site');assert.equal(await page.evaluate(()=>window.__writes.find(w=>w.url==='/chantiers').body.client_id),'c1');
 await page.getByTestId('tab-menu').click();await page.getByTestId('workspace-directory').waitFor();assert.notEqual(await page.evaluate(()=>document.activeElement?.dataset.testid),'workspace-tool-search');const modal=await page.getByTestId('workspace-directory').boundingBox();assert.ok(modal.y>=0&&modal.y+modal.height<=845);await page.screenshot({path:path.join(out,'workspace-menu-mobile.png')});await page.getByTestId('tool-clients').click();await page.getByTestId('client-card-c1').waitFor();
 await page.getByTestId('client-new-btn').click();await page.getByTestId('client-firstname').fill('Test');await page.getByTestId('client-lastname').fill('Local');await page.getByTestId('client-email').fill('test@example.test');await page.getByTestId('client-save-btn').click();await page.getByTestId('client-card-new-client').waitFor();assert.equal(await page.evaluate(()=>window.__writes.filter(w=>w.url==='/clients').length),1);
 await page.getByTestId('tab-accueil').click();await page.getByTestId('project-card-p1').waitFor();await page.evaluate(()=>scrollTo(0,0));await noOverflow();await page.screenshot({path:path.join(out,'workspace-mobile.png'),fullPage:false});await page.screenshot({path:path.join(out,'workspace-copper-mobile.jpg'),type:'jpeg',quality:92});
 await page.evaluate(()=>{window.__running=true;dispatchEvent(new Event('construpilot:assistant-job-submitted'));});await page.getByTestId('assistant-global-activity').waitFor();await page.setViewportSize({width:320,height:844});await noOverflow();
 await page.getByTestId('workspace-account-menu').click();await page.getByTestId('logout-btn').waitFor();await page.keyboard.press('Escape');
 await page.setViewportSize({width:1440,height:1100});await page.getByTestId('theme-toggle').click();assert.ok(await page.evaluate(()=>document.documentElement.classList.contains('dark')));await page.screenshot({path:path.join(out,'workspace-dark.png'),fullPage:true});await page.getByTestId('theme-toggle').click();
 await page.getByTestId('sidebar-pin-toggle').click();await page.getByTestId('workspace-reopen-menu').click();await page.getByTestId('workspace-directory').waitFor();await page.keyboard.press('Escape');
 await page.goto(url+'/?account=free');await page.getByTestId('project-card-p1').waitFor();assert.equal(await page.getByTestId('workspace-nav-devis').count(),0);assert.equal(await page.getByTestId('quick-new-quote').count(),0);await page.getByTestId('workspace-search-trigger').click();await page.getByTestId('workspace-tool-search').fill('assistant btp');assert.equal(await page.getByTestId('tool-assistant').getAttribute('href'),'/tarifs');await page.keyboard.press('Escape');
 await page.goto(url+'/?limited=1');await page.getByTestId('project-card-p1').waitFor();assert.equal(await page.getByTestId('workspace-nav-devis').count(),0);assert.equal(await page.getByTestId('quick-new-quote').count(),0);
 await page.getByTestId('lang-toggle').selectOption('pt');await page.getByRole('heading',{name:'Visão geral'}).waitFor();
 // Decorative movement must remain optional and must never capture interactions.
 await page.goto(url);await page.getByTestId('project-card-p1').waitFor();
 const backdrop=page.getByTestId('workspace-backdrop');
 assert.equal(await backdrop.getAttribute('data-paused'),'true');
 assert.equal(await backdrop.evaluate(el=>getComputedStyle(el).pointerEvents),'none');
 assert.equal(await page.locator('.workspace-halo-copper').evaluate(el=>getComputedStyle(el).animationName),'none');
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.waitForFunction(()=>document.querySelector('[data-testid="workspace-backdrop"]').dataset.paused==='false');
 const start=await page.locator('.workspace-halo-copper').evaluate(el=>getComputedStyle(el).transform);
 await page.waitForFunction(initial=>getComputedStyle(document.querySelector('.workspace-halo-copper')).transform!==initial,start);
 await page.getByTestId('workspace-search-trigger').click();await page.getByTestId('workspace-motion-toggle').click();
 assert.equal(await backdrop.getAttribute('data-paused'),'true');
 assert.equal(await page.locator('.workspace-halo-copper').evaluate(el=>getComputedStyle(el).animationPlayState),'paused');
 await page.reload();await page.getByTestId('project-card-p1').waitFor();assert.equal(await backdrop.getAttribute('data-paused'),'true');
 await page.getByTestId('workspace-search-trigger').click();await page.getByTestId('workspace-motion-toggle').click();
 await page.emulateMedia({reducedMotion:'reduce'});await page.waitForFunction(()=>document.querySelector('[data-testid="workspace-motion-toggle"]').disabled);
 await page.keyboard.press('Escape');
 await page.emulateMedia({media:'print'});assert.equal(await backdrop.evaluate(el=>getComputedStyle(el).display),'none');
 await page.emulateMedia({media:'screen'});
 if(process.env.WORKSPACE_RECORD_MOTION==='1'){
   const recording=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'no-preference',recordVideo:{dir:out,size:{width:390,height:844}}});
   const mobile=await recording.newPage();await mobile.goto(url);await mobile.getByTestId('project-card-p1').waitFor();
   await mobile.waitForTimeout(10000);const video=mobile.video();await recording.close();await video.saveAs(path.join(out,'workspace-copper-mobile.webm'));
 }
 assert.deepEqual(errors,[]);console.log('Workspace UI passed: essentials, categories/search, favourites, keyboard, permissions, real client/site forms, mobile 320/390, tablet 768, desktop, dark, PT, background badge, ambient motion/pause/persistence/reduced motion/print.');console.log('Screenshots:',out);
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
