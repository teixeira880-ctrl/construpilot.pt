const { chromium, devices } = require("playwright");
const BASE = process.env.MOBILE_BASE_URL || "http://127.0.0.1:4958";

async function run() {
  const browser = await chromium.launch();
  const results = [];
  for (const vp of [
    { name: "iPhone 13", device: devices["iPhone 13"] },
    { name: "Pixel 7", device: devices["Pixel 7"] || devices["Pixel 5"] },
    { name: "Desktop 1280x800", device: { viewport: { width: 1280, height: 800 } } },
  ]) {
    const ctx = await browser.newContext(vp.device);
    const page = await ctx.newPage();
    const r = { viewport: vp.name, checks: [] };

    await page.goto(`${BASE}/particulares/autorizacao-obras`, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForSelector('[data-testid="autorizacao-wizard"]', { timeout: 5000 });
    await page.waitForTimeout(500);

    // PromptBar presente no step 0
    const bar = await page.locator('[data-testid="prompt-bar"]').isVisible().catch(() => false);
    r.checks.push({ name: "prompt_bar_autorizacao_step0", pass: bar });

    // Input accessible
    const input = await page.locator('[data-testid="prompt-input"]').count();
    r.checks.push({ name: "prompt_input_present", pass: input > 0 });

    // Botão Gerar presente
    const btn = await page.locator('[data-testid="prompt-generate"]').count();
    r.checks.push({ name: "prompt_generate_button", pass: btn > 0 });

    // Teste indireto: 6 apps registadas no bundle (via grep ao main.js)
    const bundleApps = await page.evaluate(async () => {
      const src = document.querySelector('script[src^="/static/js/main."]')?.src;
      if (!src) return null;
      const txt = await fetch(src).then((r) => r.text());
      return {
        has_autorizacao: /\"autorizacao\"/.test(txt),
        has_escadas: /\"escadas\"/.test(txt),
      };
    });
    r.checks.push({ name: "app_keys_in_bundle", pass: bundleApps && bundleApps.has_autorizacao, detail: JSON.stringify(bundleApps) });

    results.push(r);
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
  const ok = results.every((r) => r.checks.every((c) => c.pass));
  process.exit(ok ? 0 : 1);
}
run().catch((e) => { console.error(e); process.exit(2); });
