// Testes Playwright multi-viewport para o modo demo (/demo).
// Executa contra o build servido localmente ou via REACT_APP_BACKEND_URL.
const { chromium, devices } = require("playwright");

const BASE_URL = process.env.DEMO_BASE_URL || "http://localhost:3000";
const VIEWPORTS = [
  { name: "iPhone 13", device: devices["iPhone 13"] },
  { name: "Pixel 7", device: devices["Pixel 7"] || devices["Pixel 5"] },
  { name: "Desktop 1280x800", device: { viewport: { width: 1280, height: 800 }, userAgent: "Mozilla/5.0" } },
];

async function run() {
  const browser = await chromium.launch();
  const results = [];
  for (const vp of VIEWPORTS) {
    const context = await browser.newContext(vp.device);
    const page = await context.newPage();
    const vpResult = { viewport: vp.name, checks: [] };

    const t0 = Date.now();
    const resp = await page.goto(`${BASE_URL}/demo`, { waitUntil: "domcontentloaded", timeout: 15000 });
    const loadMs = Date.now() - t0;
    vpResult.checks.push({ name: "status", pass: resp && resp.status() === 200, detail: resp?.status() });
    vpResult.checks.push({ name: "load_time_ms", pass: loadMs < 5000, detail: loadMs });

    await page.waitForSelector('[data-testid="demo-root"]', { timeout: 5000 });
    const scnVisible = await page.locator('[data-testid="demo-scn-escada_meio_quarto"]').isVisible();
    vpResult.checks.push({ name: "escada_scenario_visible", pass: scnVisible });

    // Modo offline (bloqueia /api/prompt-fill/*)
    await context.route("**/api/prompt-fill/**", (route) => route.abort());

    await page.locator('[data-testid="demo-scn-escada_meio_quarto"]').click();

    // Esperar resultado (até ao fallback simulado)
    try {
      await page.waitForSelector('[data-testid="demo-result-stairs"]', { timeout: 10000 });
      vpResult.checks.push({ name: "result_appears_offline", pass: true });
      const elapsed = await page.locator('[data-testid="demo-elapsed"]').innerText();
      vpResult.checks.push({ name: "elapsed_label", pass: /\d+,\d/.test(elapsed), detail: elapsed });
    } catch (e) {
      vpResult.checks.push({ name: "result_appears_offline", pass: false, detail: e.message });
    }

    // Reiniciar
    try {
      await page.locator('[data-testid="demo-restart"]').click();
      // Esperar que o resultado seja desmontado (AnimatePresence tem exit anim)
      await page.waitForFunction(
        () => !document.querySelector('[data-testid="demo-result"]'),
        null,
        { timeout: 5000 }
      );
      vpResult.checks.push({ name: "restart_clears_result", pass: true });
    } catch (e) {
      vpResult.checks.push({ name: "restart_clears_result", pass: false, detail: e.message });
    }

    // Troca idioma PT→EN
    try {
      const langBtn = page.locator('[data-testid="demo-lang-toggle"]');
      if (await langBtn.count()) {
        await langBtn.click();
        vpResult.checks.push({ name: "lang_toggle_clickable", pass: true });
      } else {
        vpResult.checks.push({ name: "lang_toggle_clickable", pass: false, detail: "sem toggle" });
      }
    } catch (e) {
      vpResult.checks.push({ name: "lang_toggle_clickable", pass: false, detail: e.message });
    }

    results.push(vpResult);
    await context.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
  const allPass = results.every((r) => r.checks.every((c) => c.pass));
  process.exit(allPass ? 0 : 1);
}

run().catch((e) => {
  console.error(e);
  process.exit(2);
});
