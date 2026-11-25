// Percurso de demonstração do Dossier de Obra (13 passos + modos, impacto, telemóvel, dados antigos, teclado).
// Rotas reais do backend com Mongo em memória e assistente SIMULADO. Nunca chama produção.
// Requisitos: venv Python com requirements + mongomock-motor; Chrome/Chromium (CHROMIUM_EXECUTABLE_PATH); `yarn build` feito (CSS).
// Uso: PYTHON=/caminho/venv/bin/python CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome node scripts/test-dossier-obra.cjs
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), { spawn } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const tmp = fs.mkdtempSync(path.join(root, '.dossier-e2e-'));
const stat = path.join(tmp, 'static'); fs.mkdirSync(stat);
fs.writeFileSync(path.join(tmp, 'entry.jsx'), `import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import "@/index.css";
import "@/App.css";
import "@/styles/workspace.css";
import { I18nProvider } from "@/context/I18nContext";
import { AuthProvider } from "@/context/AuthContext";
import { BillingProvider } from "@/context/BillingContext";
import { PermissionProvider } from "@/context/PermissionContext";
import WorkspaceNavigation from "@/components/workspace/WorkspaceNavigation";
import DossierObra from "@/pages/DossierObra";
const Shell = ({ children }) => <div className="workspace"><WorkspaceNavigation /><div className="workspace-content"><main id="workspace-main" className="workspace-main">{children}</main></div></div>;
createRoot(document.getElementById("root")).render(<BrowserRouter><I18nProvider><AuthProvider><BillingProvider><PermissionProvider>
<Routes><Route path="/chantiers/:chantierId/dossier/*" element={<Shell><DossierObra /></Shell>} /><Route path="*" element={<Navigate to={\`/chantiers/\${window.__CID__}/dossier\`} replace />} /></Routes>
</PermissionProvider></BillingProvider></AuthProvider></I18nProvider><Toaster /></BrowserRouter>);`);
require('esbuild').buildSync({ entryPoints: [path.join(tmp, 'entry.jsx')], bundle: true, outdir: stat, jsx: 'automatic', alias: { '@': path.join(root, 'src') },
  define: { 'process.env.REACT_APP_BACKEND_URL': '""', 'process.env.NODE_ENV': '"production"', 'process.env': '{}' }, loader: { '.js': 'jsx', '.png': 'file', '.svg': 'file', '.jpg': 'file', '.woff2': 'file', '.woff': 'file', '.ttf': 'file' }, logLevel: 'error' });
const cssDir = path.join(root, 'build/static/css');
const main = fs.existsSync(cssDir) ? fs.readdirSync(cssDir).find(f => /^main\..*\.css$/.test(f)) : null;
fs.writeFileSync(path.join(stat, 'main.css'), main ? fs.readFileSync(path.join(cssDir, main)) : '');
const S = (process.env.DOSSIER_SHOTS || path.join(tmp, 'shots')) + '/'; fs.mkdirSync(S, { recursive: true });
const server = spawn(process.env.PYTHON || 'python3', ['-m', 'uvicorn', 'dossier_obra_harness:app', '--port', '8765'], { cwd: path.join(root, '../backend/tests'), env: { ...process.env, DOSSIER_E2E_STATIC: stat }, stdio: 'inherit' });
const cleanup = () => { try { server.kill(); } catch {} fs.rmSync(tmp, { recursive: true, force: true }); };
process.on('exit', cleanup);
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  await new Promise(r => setTimeout(r, 7000));
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1586, height: 992 } });
  const errors = []; page.on('pageerror', e => errors.push(String(e))); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  const log = (s) => console.log('OK', s);
  await page.goto('http://localhost:8765/');                                   // 1. abrir a moradia
  await page.getByTestId('dob-overview').waitFor();
  assert.match(await page.getByTestId('dob-obra-name').innerText(), /Moradia em L/); log('1 abrir moradia');
  await page.getByTestId('sidebar-specialties').waitFor(); await page.getByTestId('sidebar-documento-final').waitFor(); log('menu lateral verde com ESPECIALIDADES');
  await page.screenshot({ path: S + '01_visao_geral.png' });
  await page.getByTestId('dob-start-area-arquitetura').click();               // 2. Arquitetura (modo guiado)
  await page.getByTestId('dob-start-specialties').waitFor(); log('2 entrar em Arquitetura');
  await page.getByTestId('dob-start-revest_exteriores').click();              // 3. Revestimentos exteriores
  await page.getByTestId('dob-specialty-name').filter({ hasText: 'Revestimentos exteriores' }).waitFor(); log('3 abrir Revestimentos exteriores');
  await page.getByTestId('dob-fase').selectOption('execucao');                // 4. Execução + Fachada norte
  const fn = await page.getByTestId('dob-local').locator('option', { hasText: 'Fachada norte' }).getAttribute('value');
  await page.getByTestId('dob-local').selectOption(fn);
  await page.waitForURL(/fase=execucao.*local=/);
  await page.getByText('Local: Fachada norte').waitFor(); await page.getByTestId('dob-checklist').waitFor(); log('4 fase Execução + local Fachada norte');
  await page.waitForTimeout(400);
  await page.screenshot({ path: S + '02_especialidade_resumo.png' });
  await page.getByTestId('dob-tab-plantas').click();                          // 5. planta e origem da medição
  const origin = await page.getByTestId('dob-origin').innerText();
  assert.match(origin, /Fachadas_P03/); assert.match(origin, /1:100/); assert.match(origin, /84/); log('5 origem da medição');
  await page.getByTestId('dob-sketch').waitFor();
  await page.screenshot({ path: S + '03_planta_camadas.png' });
  await page.getByTestId('dob-layer-1').first().click();                      // 6. corrigir / confirmar material
  await page.getByTestId('dob-layer-fix-input').fill('Alvenaria de tijolo 15 cm');
  await page.getByTestId('dob-layer-fix-1').click();
  await page.getByText('Alvenaria de tijolo 15 cm').first().waitFor();
  await page.getByTestId('dob-layer-5').first().click(); await page.getByTestId('dob-layer-confirm-5').click();
  await page.waitForTimeout(500); log('6 corrigir camada 1 e confirmar camada 5');
  await page.getByTestId('dob-breadcrumbs').getByRole('link', { name: 'Revestimentos exteriores' }).click();
  const rel = page.getByTestId('dob-related-agua');                            // 7. pendência ligada a Engenharia
  await rel.waitFor(); assert.equal((await rel.innerText()).trim(), 'Engenharia'); log('7 pendência ligada a Engenharia');
  await rel.click();                                                           // 8. abrir mantendo contexto
  await page.getByTestId('dob-specialty-name').filter({ hasText: 'Abastecimento de água' }).waitFor();
  assert.match(page.url(), /fase=execucao/); assert.match(page.url(), /local=/); log('8 ligação aberta com fase/local preservados');
  await page.getByTestId('dob-docs').waitFor();
  const wc = await page.getByTestId('dob-local').locator('option', { hasText: 'Casa de banho' }).getAttribute('value');
  await page.getByTestId('dob-local').selectOption(wc); await page.getByText('Concluir instalação').waitFor(); await page.waitForTimeout(500);
  await page.screenshot({ path: S + '04_engenharia_agua.png' });
  await page.getByTestId('dob-local').selectOption(fn);
  await page.goBack(); await page.goBack(); await page.getByTestId('dob-specialty-name').filter({ hasText: 'Revestimentos' }).waitFor();
  await page.getByTestId('dob-assistant-quick').first().click();               // 9. assistente
  await page.locator('.dob-bubble-a', { hasText: 'SIMULAÇÃO' }).waitFor(); log('9 assistente (contexto)');
  await page.getByTestId('dob-tab-orcamento').click();                        // orçamento só desta especialidade
  await page.getByTestId('dob-budget-subtotal').filter({ hasText: '3192' }).waitFor();
  await page.getByTestId('dob-budget-title').fill('Rodapé cerâmico'); await page.getByTestId('dob-budget-qty').fill('24'); await page.getByTestId('dob-budget-price').fill('12,5');
  await page.getByTestId('dob-budget-add').click(); await page.getByTestId('dob-budget-subtotal').filter({ hasText: '3492' }).waitFor(); log('orçamento só de fachadas: 3 492 €');
  await page.screenshot({ path: S + '05_orcamento_especialidade.png' });
  await page.getByTestId('dob-prepare-report').click();                        // 10. relatório da especialidade
  await page.locator('.dob-paper', { hasText: 'RELATÓRIO DA ESPECIALIDADE' }).waitFor(); log('10 relatório da especialidade');
  await page.getByTestId('dob-compile-agua').check(); await page.getByTestId('dob-compile-paredes').check();   // 11. várias especialidades
  await page.getByTestId('dob-compile-fase').selectOption(''); await page.getByTestId('dob-compile-local').selectOption('');
  await page.locator('.dob-paper', { hasText: 'DOSSIER DE OBRA' }).waitFor(); log('11 várias especialidades');
  await page.getByTestId('dob-complete-budget').getByTestId('dob-budget-total').filter({ hasText: '4142' }).waitFor(); log('orçamento completo (fachadas + água): 4 142 €');
  await page.getByTestId('dob-format-zip').click();
  await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(400);
  await page.screenshot({ path: S + '06_compilar_dossier.png' });
  await page.screenshot({ path: S + '06b_compilar_completo.png', fullPage: true });
  const downloads = []; page.on('download', d => downloads.push(d.suggestedFilename()));
  await page.getByTestId('dob-generate').click();                              // 12. gerar
  await page.getByTestId('dob-generated').waitFor(); await page.waitForTimeout(1500);
  assert.ok(downloads.some(n => n.endsWith('.pdf')) && downloads.some(n => n.endsWith('.zip')), 'downloads ' + downloads); log('12 gerar: ' + downloads.join(', '));
  await page.getByTestId('dob-emissions').getByText('Versão 01').waitFor(); log('13 emissão guardada');
  const [resp] = await Promise.all([page.waitForResponse(r => r.url().includes('/orcamento/rascunho')), page.getByTestId('dob-budget-complete').click()]);
  const draft = await resp.json(); assert.equal(resp.status(), 200); assert.ok(draft.doc_id.startsWith('doc_')); assert.equal(draft.specialties.length, 2);
  log('orçamento completo criado em rascunho no módulo Orçamentos: ' + draft.doc_id + ' · ' + draft.total_ht + ' €');
  // modo técnico: mesmos dados
  await page.goto(`http://localhost:8765/chantiers/${await page.evaluate(() => window.__CID__)}/dossier/especialidade/revest_exteriores`);
  await page.getByTestId('dob-mode-tecnico').click();
  await page.getByTestId('dob-spec-status').waitFor();
  await page.getByTestId('dob-tab-plantas').click(); await page.getByTestId('dob-tab-medicoes').click();
  await page.locator('[data-testid^=dob-quantities-]').first().waitFor(); log('modo técnico (mesmos registos)');
  const qin = page.locator('[data-testid^=dob-quantities-] input').first();
  await qin.fill('80'); await page.locator('[data-testid^=dob-quantities-]').getByRole('button', { name: 'Guardar' }).click();
  await page.getByTestId('dob-impact-dialog').waitFor(); log('impacto apresentado antes de confirmar');
  await page.getByTestId('dob-impact-confirm').click(); await page.waitForTimeout(800);
  await page.getByTestId('dob-mode-guiado').click();
  // telemóvel
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload(); await page.getByTestId('dob-specialty-name').waitFor();
  assert.equal(await page.getByTestId('dob-tree').getAttribute('data-open'), 'false');
  assert.equal(await page.getByTestId('dob-assistant').count(), 0, 'assistente fechado por defeito no telemóvel');
  await page.screenshot({ path: S + '07_telemovel.png' });
  await page.getByTestId('dob-tree-toggle').click(); await page.getByTestId('dob-tree-revest_exteriores').waitFor(); log('telemóvel: árvore recolhível');
  await page.getByTestId('dob-tree-toggle').click(); await page.getByTestId('dob-open-assistant').click(); await page.getByTestId('dob-assistant').waitFor(); log('telemóvel: assistente a pedido');
  await page.screenshot({ path: S + '08_telemovel_assistente.png' });
  await page.goto(page.url().split('/especialidade')[0]);
  await page.getByTestId('dob-por-organizar').waitFor(); log('dados antigos em «Por organizar»');
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.keyboard.press('Tab'); await page.keyboard.press('Tab');
  const focused = await page.evaluate(() => { const e = document.activeElement; return e && getComputedStyle(e).outlineStyle; });
  assert.notEqual(focused, 'none'); log('foco visível por teclado');
  console.log('ERRORS', JSON.stringify(errors.filter(e => !/favicon|404/.test(e))));
  await browser.close();
  console.log('PASSOU: percurso do dossier de obra');
  process.exit(0);
})().catch(e => { console.error('FAIL', e); process.exit(1); });
