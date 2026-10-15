// R3d — validação final consolidada R3 (4 viewports)
const { chromium, devices } = require("playwright");

const BASE_URL = process.env.MOBILE_BASE_URL || "http://127.0.0.1:4956";
const VIEWPORTS = [
  { name: "iPhone 13 (390x844)", device: devices["iPhone 13"], mobile: true, hasBottomTabs: true },
  { name: "Pixel 7 (412x915)", device: devices["Pixel 7"] || devices["Pixel 5"], mobile: true, hasBottomTabs: true },
  { name: "iPad landscape (1024x768)", device: { viewport: { width: 1024, height: 768 }, userAgent: "Mozilla/5.0 (iPad)" }, mobile: false, hasBottomTabs: false },
  { name: "Desktop (1280x800)", device: { viewport: { width: 1280, height: 800 } }, mobile: false, hasBottomTabs: false },
];

async function run() {
  const browser = await chromium.launch();
  const results = [];
  for (const vp of VIEWPORTS) {
    const context = await browser.newContext(vp.device);
    const page = await context.newPage();
    const r = { viewport: vp.name, checks: [] };

    // Rota principal / (visitante)
    const t0 = Date.now();
    await page.goto(`${BASE_URL}/`, { waitUntil: "domcontentloaded", timeout: 15000 });
    const loadMs = Date.now() - t0;
    r.checks.push({ name: "landing_loads_<3s", pass: loadMs < 3000, detail: `${loadMs}ms` });
    await page.waitForTimeout(500);

    // Bottom tabs e FAB em mobile only
    const bt = await page.locator('[data-testid="bottom-tabs"]').isVisible().catch(() => false);
    const fab = await page.locator('[data-testid="mic-fab"]').isVisible().catch(() => false);
    r.checks.push({ name: "bottom_tabs_visibility", pass: bt === vp.hasBottomTabs, detail: `expected=${vp.hasBottomTabs}, got=${bt}` });
    r.checks.push({ name: "fab_visibility", pass: fab === vp.hasBottomTabs, detail: `expected=${vp.hasBottomTabs}, got=${fab}` });

    // /apps + AppsHub carrega
    await page.goto(`${BASE_URL}/apps`, { waitUntil: "domcontentloaded", timeout: 10000 });
    const hub = await page.waitForSelector('[data-testid="apps-hub"]', { timeout: 5000 }).catch(() => null);
    r.checks.push({ name: "apps_hub_loads", pass: !!hub });

    // Câmara button só mobile (md:hidden)
    const cam = await page.locator('[data-testid="apps-hub-quick-camera"]').isVisible().catch(() => false);
    r.checks.push({ name: "camera_button_visibility", pass: cam === vp.mobile, detail: `mobile=${vp.mobile}, got=${cam}` });

    // Autorização de obras — wizard carrega
    await page.goto(`${BASE_URL}/particulares/autorizacao-obras`, { waitUntil: "domcontentloaded", timeout: 10000 });
    const wiz = await page.waitForSelector('[data-testid="autorizacao-wizard"]', { timeout: 5000 }).catch(() => null);
    r.checks.push({ name: "autorizacao_wizard_loads", pass: !!wiz });

    // Dark mode: aplica & re-verifica em runtime
    await page.evaluate(() => { localStorage.setItem("construpilot_theme", "dark"); });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(400);
    const isDark = await page.evaluate(() => document.documentElement.classList.contains("dark"));
    r.checks.push({ name: "dark_mode_applies", pass: isDark });
    await page.evaluate(() => { localStorage.setItem("construpilot_theme", "light"); });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(300);
    const isLight = await page.evaluate(() => !document.documentElement.classList.contains("dark"));
    r.checks.push({ name: "light_mode_applies", pass: isLight });

    // Code-splitting: main sem rotas pesadas
    const main = await page.evaluate(async () => {
      const src = document.querySelector('script[src^="/static/js/main."]')?.src;
      if (!src) return null;
      const txt = await fetch(src).then((r) => r.text());
      return { has_structuro: /StructuroHouse/.test(txt), has_plan: /PlanTakeoff/.test(txt) };
    });
    r.checks.push({ name: "code_splitting_active", pass: main && !main.has_structuro && !main.has_plan, detail: JSON.stringify(main) });

    // /demo público carrega
    await page.goto(`${BASE_URL}/demo`, { waitUntil: "domcontentloaded", timeout: 10000 });
    const demo = await page.waitForSelector('[data-testid="demo-root"]', { timeout: 5000 }).catch(() => null);
    r.checks.push({ name: "demo_route_loads", pass: !!demo });

    results.push(r);
    await context.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
  const allPass = results.every((r) => r.checks.every((c) => c.pass));
  process.exit(allPass ? 0 : 1);
}

run().catch((e) => { console.error(e); process.exit(2); });
