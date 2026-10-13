// Browser checks for the real workspace header/results with a simulated parent.
// Requires playwright + its Chromium browser, esbuild and the frontend dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const { build } = require('esbuild');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'construpilot-workflow-'));

async function main() {
  const entry = path.join(output, 'fixture.jsx');
  fs.writeFileSync(entry, `
    import React, { useState } from 'react';
    import { createRoot } from 'react-dom/client';
    import Header, { PlanAnalysisResults } from ${JSON.stringify(path.join(root, 'src/components/planTakeoff/PlanWorkflowHeader.jsx'))};
    import ${JSON.stringify(path.join(root, 'src/index.css'))};
    const initial = { rooms: 4, surface_pieces_m2: 84.6, walls: 16, columns: 4, beams: 6, floors: 1, beton_m3: 12.8, acier_kg: 1024, estimation_globale_eur: 48500, warnings: [] };
    function Fixture() {
      const [mode, setMode] = useState('complete'), [kind, setKind] = useState('auto');
      const [busy, setBusy] = useState(false), [recap, setRecap] = useState(initial);
      const [pageCount, setPageCount] = useState(3);
      const record = (action) => { window.lastAction = action; };
      return <main className="plan-workspace" style={{ maxWidth: 1260, margin: 'auto', padding: '28px 20px' }}>
        <Header filename="Maison · Gros œuvre — RDC.pdf" pageIndex={0} pageCount={pageCount} calibration={{pixels_per_meter: 100}}
          mode={mode} onModeChange={setMode} planKind={kind} onPlanKindChange={setKind} busy={busy} hasRecap={!!recap}
          onAnalyze={() => { record(mode); setBusy(true); }} progress="2 / 5 · Lecture des pièces et ouvertures…"
          onCalibrate={() => record('calibrate')} onReview={() => record('review')} onEstimate={() => record('estimate')}
          documentActions={[{ id: 'duplicate', label: 'Dupliquer ce plan', run: () => record('duplicate') }]}
          exportActions={[{ id: 'excel', label: 'Tableur Excel', run: () => record('excel') }]}
          studyActions={[{ id: 'review', label: 'Contrôle des cotes', run: () => record('review') }]} />
        {recap && <PlanAnalysisResults recap={recap} onClose={() => setRecap(null)} onReview={() => record('review')} onQuote={() => record('quote')} />}
        <div data-testid="fixture-controls" style={{ marginTop: 30, fontSize: 12, display: 'flex', flexWrap: 'wrap', gap: 14 }}>
          <span>Données de démonstration · test local</span>
          <button onClick={() => setBusy(false)}>Terminer le test</button>
          <button onClick={() => setPageCount(1)}>Document monopage</button>
          <button onClick={() => setRecap({ ...initial, beton_m3: null, acier_kg: null, estimation_globale_eur: null, estimation_beton_eur: null, warnings: ['Descriptif indisponible'] })}>Résultat incomplet</button>
          <button onClick={() => setRecap({ ...initial, estimation_globale_eur: 0, estimation_beton_eur: 500 })}>Prix nul</button>
        </div>
      </main>;
    }
    createRoot(document.getElementById('root')).render(<Fixture />);
  `);
  await build({ entryPoints: [entry], outdir: output, entryNames: 'app', bundle: true, jsx: 'automatic',
    alias: { '@': path.join(root, 'src') }, nodePaths: (process.env.NODE_PATH || '').split(path.delimiter).filter(Boolean),
    define: { 'process.env.NODE_ENV': '"test"' } });
  execFileSync(process.execPath, [require.resolve('tailwindcss/lib/cli.js'), '-i', path.join(output, 'app.css'), '-o', path.join(output, 'styles.css'), '-c', path.join(root, 'tailwind.config.js')], { cwd: root, stdio: 'pipe' });
  fs.writeFileSync(path.join(output, 'index.html'), '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><title>Test Plans & métrés</title></head><body><div id="root"></div><script src="/app.js"></script></body></html>');
  const server = http.createServer((req, res) => {
    const file = { '/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css' }[req.url];
    if (!file) { res.writeHead(404); res.end(); return; }
    res.setHeader('Content-Type', file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : 'text/html');
    res.end(fs.readFileSync(path.join(output, file)));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByRole('heading', { name: 'Plans & métrés', exact: true }).waitFor();
    assert.equal(await page.getByTestId('plan-analyze-btn').count(), 1);
    if (process.env.AUDIT_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.AUDIT_SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.AUDIT_SCREENSHOT_DIR, 'plans-metres-desktop.png'), fullPage: true });
    }
    await page.getByRole('button', { name: 'Document', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Dupliquer ce plan' }).click();
    assert.equal(await page.evaluate(() => window.lastAction), 'duplicate');
    await page.getByRole('button', { name: 'Exporter', exact: true }).focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => window.lastAction), 'excel');
    await page.locator('#plan-analysis-mode').selectOption('reading');
    assert.equal(await page.getByTestId('analyze-kind-toggle').isDisabled(), true);
    assert.match(await page.locator('#plan-analysis-description').textContent(), /avant calibration/);
    await page.getByTestId('plan-analyze-btn').click();
    assert.equal(await page.evaluate(() => window.lastAction), 'reading');
    assert.equal(await page.getByTestId('plan-analyze-btn').isDisabled(), true);
    assert.equal(await page.getByRole('button', { name: 'Document', exact: true }).isDisabled(), true);
    assert.match(await page.getByRole('status').textContent(), /2 \/ 5/);
    await page.getByRole('button', { name: 'Terminer le test' }).click();
    await page.locator('#plan-analysis-mode').selectOption('structure_all');
    assert.match(await page.locator('#plan-analysis-description').textContent(), /chiffrage restent à traiter par page/);
    await page.getByTestId('plan-analyze-btn').click();
    assert.equal(await page.evaluate(() => window.lastAction), 'structure_all');
    await page.getByRole('button', { name: 'Terminer le test' }).click();
    await page.locator('#plan-analysis-mode').selectOption('complete');
    assert.equal(await page.getByTestId('analyze-kind-toggle').isDisabled(), false);
    await page.getByTestId('plan-analyze-btn').click();
    assert.equal(await page.evaluate(() => window.lastAction), 'complete');
    await page.getByRole('button', { name: 'Terminer le test' }).click();
    await page.getByRole('button', { name: 'Document monopage' }).click();
    assert.equal(await page.locator('option[value="structure_all"]').count(), 0);
    await page.getByTestId('recap-see-rooms').click();
    assert.equal(await page.evaluate(() => window.lastAction), 'review');
    await page.getByRole('button', { name: 'Résultat incomplet' }).click();
    assert.match(await page.getByTestId('recap-estimation').textContent(), /Indisponible/);
    assert.match(await page.getByTestId('recap-beton').textContent(), /Indisponible/);
    assert.match(await page.getByRole('status').textContent(), /Descriptif indisponible/);
    await page.getByRole('button', { name: 'Prix nul' }).click();
    assert.match(await page.getByTestId('recap-estimation').textContent(), /0 €/);
    assert.doesNotMatch(await page.getByTestId('recap-estimation').textContent(), /500/);
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, `No horizontal overflow at ${width}px`);
      if (width === 390 && process.env.AUDIT_SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.AUDIT_SCREENSHOT_DIR, 'plans-metres-mobile.png'), fullPage: true });
    }
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.waitForFunction(() => getComputedStyle(document.querySelector('.plan-menu-button')).backgroundColor === 'rgb(32, 40, 34)');
    assert.equal(await page.getByRole('button', { name: 'Document', exact: true }).evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(32, 40, 34)', 'Dark mode menu buttons retain their dark background');
    if (process.env.AUDIT_SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.AUDIT_SCREENSHOT_DIR, 'plans-metres-dark.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Plan workflow: 24 browser assertions passed (desktop, keyboard, 390px, 320px, dark mode).');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => fs.rmSync(output, { recursive: true, force: true }));
