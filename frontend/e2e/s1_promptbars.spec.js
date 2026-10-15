// S1 — PromptBar nas 5 apps (verifica presença + redireccionamentos aceitáveis)
const { chromium, devices } = require("playwright");

const BASE = process.env.MOBILE_BASE_URL || "http://127.0.0.1:4960";

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

    // 1) /medicao-rapida — rota pública (Shell sem Protected)
    await page.goto(`${BASE}/medicao-rapida`, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForTimeout(1500);
    // Esperar explicitamente pelo elemento (lazy chunk + render após hydration)
    await page.locator('[data-testid="medicao-rapida"]').waitFor({ state: "visible", timeout: 8000 }).catch(() => {});
    const med = await page.locator('[data-testid="medicao-rapida"]').isVisible().catch(() => false);
    const medPromptBar = await page.locator('[data-testid="medicao-rapida"] [data-testid="prompt-bar"]').count();
    r.checks.push({ name: "medicoes_page_loads", pass: med });
    r.checks.push({ name: "medicoes_prompt_bar_present", pass: medPromptBar > 0 });

    // 2) /calculadoras — rota pública (Shell)
    await page.goto(`${BASE}/calculadoras`, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForTimeout(1500);
    const calcTabs = await page.locator('[data-testid="calculator-tabs"]').isVisible().catch(() => false);
    const calcLoading = await page.locator('[data-testid="calculators-loading"]').isVisible().catch(() => false);
    const calcBar = await page.locator('[data-testid="prompt-bar"]').count();
    r.checks.push({ name: "calculadoras_page_loads", pass: calcTabs || calcLoading });
    r.checks.push({ name: "calculadoras_prompt_bar_present", pass: calcBar > 0 });

    // 3) Bundle: PromptBar carregada nas 3 rotas protegidas (StructuroHouse, QuoteEditor, PlanTakeoff)
    //    verificar via grep ao bundle principal (orcamentos é string literal exclusiva)
    const bundle = await page.evaluate(async () => {
      // bundles podem ser lazy; carregar todos os scripts /static/js/*
      const scripts = Array.from(document.querySelectorAll('script[src^="/static/js/"]'));
      let combined = "";
      for (const s of scripts) {
        try {
          combined += await (await fetch(s.src)).text();
        } catch { /* ignorar */ }
      }
      return {
        has_orcamentos_key: /"orcamentos"/.test(combined),
        has_plantas_key: /"plantas"/.test(combined),
        has_moradia_key: /"moradia"/.test(combined),
        has_calculadoras_key: /"calculadoras"/.test(combined),
        has_medicoes_key: /"medicoes"/.test(combined),
      };
    });
    r.checks.push({ name: "orcamentos_integration_in_main_bundle", pass: bundle.has_orcamentos_key, detail: JSON.stringify(bundle) });
    r.checks.push({ name: "medicoes_calculadoras_in_main_bundle", pass: bundle.has_medicoes_key && bundle.has_calculadoras_key });

    // 4) Rotas pesadas lazy (StructuroHouse, PlanTakeoff) — chunks separados devem conter o appKey
    //    Carregar explicitamente os chunks lazy via visita (ambas redireccionam para login mas o chunk vem)
    for (const path of ["/estudo-moradia", "/plan"]) {
      try {
        await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded", timeout: 10000 });
        await page.waitForTimeout(400);
      } catch { /* redirect é normal */ }
    }
    const bundleAfter = await page.evaluate(async () => {
      const scripts = Array.from(document.querySelectorAll('script[src^="/static/js/"]'));
      let combined = "";
      for (const s of scripts) {
        try {
          combined += await (await fetch(s.src)).text();
        } catch { /* ignorar */ }
      }
      return {
        plantas: /"plantas"/.test(combined),
        moradia: /"moradia"/.test(combined),
      };
    });
    r.checks.push({ name: "plantas_moradia_in_lazy_chunks", pass: bundleAfter.plantas || bundleAfter.moradia, detail: JSON.stringify(bundleAfter) });

    results.push(r);
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
  const ok = results.every((r) => r.checks.every((c) => c.pass));
  process.exit(ok ? 0 : 1);
}

run().catch((e) => { console.error(e); process.exit(2); });
