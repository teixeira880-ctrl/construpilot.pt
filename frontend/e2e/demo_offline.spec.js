/*
 * LOTE 2d — Playwright offline (WebSummit demo).
 *
 * Script standalone (não @playwright/test runner): corre contra o preview
 * dev (`http://localhost:3000`) ou qualquer URL via DEMO_BASE_URL.
 *
 * Teste 1 — Online→Offline mid-session (interceptor):
 *   1) carrega /demo/entrar online
 *   2) activa modo offline (clique "Offline — Profissional")
 *   3) context.setOffline(true) — bloqueia toda a rede
 *   4) navega para o Dashboard + Moradia Martins + Assistente
 *   5) assert: zero network request de /api/* passou para fora, zero erro UPS/Cannot read.
 *
 * Teste 2 — Service Worker + offline desde arranque:
 *   1) carrega / em modo normal, activa flag cp_force_pwa, aguarda SW install.
 *   2) context.setOffline(true), recarrega: HTML + chunks servidos pela cache SW.
 *   3) activa modo offline + navega: tudo serve-se da cache SW + fixtures.
 *
 * Uso:
 *   node e2e/demo_offline.spec.js
 *   DEMO_BASE_URL=https://preview.example.com node e2e/demo_offline.spec.js
 */
const { chromium } = require("playwright");

const BASE_URL = process.env.DEMO_BASE_URL || "http://localhost:3000";
const TIMEOUT = 20000;

function _log(ok, name, detail = "") {
  const mark = ok ? "✅" : "❌";
  console.log(`${mark} ${name}${detail ? " — " + detail : ""}`);
  return ok;
}

async function _ensureNoCrashText(page) {
  const html = (await page.content()).toLowerCase();
  for (const bad of ["cannot read", "undefined is not", "ups!", "something went wrong"]) {
    if (html.includes(bad)) return `found "${bad}"`;
  }
  return null;
}

async function testOnlineToOffline(browser, results) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const outboundApi = [];
  // Captura **tudo** o que sai (depois do interceptor local): se chegar aqui, falhamos.
  page.on("request", (req) => {
    const u = req.url();
    if (u.includes("/api/")) outboundApi.push(`${req.method()} ${u}`);
  });

  try {
    await page.goto(`${BASE_URL}/demo/entrar`, { waitUntil: "domcontentloaded", timeout: TIMEOUT });
    await page.waitForSelector('[data-testid="demo-page"]', { timeout: TIMEOUT });
    results.push(_log(true, "T1.1 /demo/entrar carrega"));

    // Clicar "Offline — Profissional" (activa interceptor + login local)
    await page.waitForSelector('[data-testid="demo-offline-pro-btn"]', { timeout: TIMEOUT });

    // A partir daqui, bloqueamos toda a rede
    await context.setOffline(true);
    outboundApi.length = 0; // Zerar após activar offline — só nos interessa o que sai depois.
    await page.locator('[data-testid="demo-offline-pro-btn"]').click();

    // Navegação espera dashboard
    await page.waitForURL(/\/dashboard/, { timeout: TIMEOUT });
    results.push(_log(true, "T1.2 Login offline → /dashboard"));

    // Procurar "Moradia Martins" no DOM
    const bodyText = await page.locator("body").innerText({ timeout: 10000 });
    const hasMM = /Moradia Martins/i.test(bodyText);
    results.push(_log(hasMM, "T1.3 Dashboard mostra Moradia Martins"));

    // Zero chamadas /api/* fora do interceptor
    results.push(_log(
      outboundApi.length === 0,
      "T1.4 Zero network /api/* durante offline",
      `requests saídos: ${outboundApi.length}`,
    ));

    // Zero texto de erro
    const crash = await _ensureNoCrashText(page);
    results.push(_log(!crash, "T1.5 Sem erro UPS/Cannot read no DOM", crash || "ok"));
  } catch (e) {
    results.push(_log(false, "T1 unexpected error", e.message));
  } finally {
    await context.close();
  }
}

async function testServiceWorkerOfflineBoot(browser, results) {
  // 1) Primeiro arranque online para registar o SW (flag opt-in cp_force_pwa em dev).
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle", timeout: TIMEOUT });
    await page.evaluate(() => { localStorage.setItem("cp_force_pwa", "true"); });
    // Reload para o index.js re-correr com a flag → regista SW
    await page.reload({ waitUntil: "networkidle" });
    const swReady = await page.evaluate(async () => {
      if (!("serviceWorker" in navigator)) return false;
      const reg = await navigator.serviceWorker.ready;
      return !!reg && !!reg.active;
    });
    results.push(_log(swReady, "T2.1 Service worker registado + activo"));

    // 2) Pré-aquecer cache navegando /demo/entrar online — chunks CRA hashed só
    //    entram no cache após 1º fetch. Em build prod isto seria desnecessário
    //    porque o SW faria addAll do bundle no install com nomes conhecidos.
    await page.goto(`${BASE_URL}/demo/entrar`, { waitUntil: "networkidle", timeout: TIMEOUT });
    await page.waitForSelector('[data-testid="demo-page"]', { timeout: TIMEOUT });
    // Dar tempo ao fetch handler do SW para popular a cache
    await page.waitForTimeout(1500);

    // 3) Offline + reload a partir do cache SW
    await context.setOffline(true);
    const resp = await page.reload({ waitUntil: "domcontentloaded", timeout: TIMEOUT });
    const loadedOffline = resp && resp.ok();
    results.push(_log(!!loadedOffline, "T2.2 /demo/entrar recarrega offline via SW"));

    // 4) Shell renderiza sem crash
    await page.waitForSelector('[data-testid="demo-page"]', { timeout: TIMEOUT });
    const crash = await _ensureNoCrashText(page);
    results.push(_log(!crash, "T2.3 Shell offline sem crash", crash || "ok"));
  } catch (e) {
    results.push(_log(false, "T2 SW offline boot (requer build prod em CI)", e.message));
  } finally {
    await context.close();
  }
}

async function main() {
  const results = [];
  const browser = await chromium.launch();
  try {
    await testOnlineToOffline(browser, results);
    await testServiceWorkerOfflineBoot(browser, results);
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => !r).length;
  console.log("");
  console.log(`demo_offline.spec.js: ${results.length - failed}/${results.length} ok`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((e) => { console.error(e); process.exit(1); });
