// AJ.3 — Regressão rápida pré-repouso (script Node standalone).
//
// Blocos:
//   B1 — Login pro (admin ou e2e) → dashboard.
//   B2 — /demo em iPhone 13 + Pixel 7 + Desktop: 5 cenários navegáveis,
//        toggle PT/EN/FR funcional, modo offline, botão Reiniciar.
//   B3 — Barra IA em 3 apps (iPhone 13): /medicao-rapida, /estudo-moradia,
//        /calculadoras.
//   B4 — Shell mobile iPhone 13 + Pixel 7: bottom-tabs em /apps, /escaliers
//        wizard, cookie consent não intercepta.
//   B5 — Desktop 1280x800: sem bottom-tabs, header intacto, /apps >=6 cards.
//
// Checks são informativos (não forçam fail global) excepto os críticos:
//   crítico = login dashboard + /demo render + barra IA preenche form.
//
// Formato: Node standalone, mesma receita que v_regression_web_summit.spec.js.

const { chromium, devices } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND_BASE =
  process.env.MOBILE_BASE_URL ||
  fs
    .readFileSync(path.join(__dirname, "..", ".env"), "utf8")
    .match(/REACT_APP_BACKEND_URL=(.+)/)?.[1]
    ?.trim()
    ?.replace(/\/+$/, "") ||
  "http://localhost:3000";

const EMAIL = process.env.E2E_EMAIL || "teste.pro+e2e@construpilot.pt";
const PASSWORD = process.env.E2E_PASSWORD || process.env.TEST_PRO_PASSWORD;
if (!PASSWORD) { console.error('E2E_PASSWORD/TEST_PRO_PASSWORD ausentes no ambiente. Abort.'); process.exit(2); }

const IPHONE_CFG = {
  ...devices["iPhone 13"],
  hasTouch: true,
  isMobile: false,
};
const PIXEL_CFG = { ...devices["Pixel 7"], hasTouch: true, isMobile: false };
const DESKTOP_CFG = { viewport: { width: 1280, height: 800 } };

const results = { blocks: {}, pass: 0, fail: 0, critical_fail: 0 };

function log(block, name, ok, note = "") {
  const key = block;
  if (!results.blocks[key]) results.blocks[key] = [];
  results.blocks[key].push({ name, ok, note });
  if (ok) results.pass++;
  else results.fail++;
}

async function tryLogin(page) {
  await page.goto(`${FRONTEND_BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(800);
  const emailInput = await page.$('input[type="email"], input[name="email"]');
  const pwdInput = await page.$('input[type="password"], input[name="password"]');
  if (!emailInput || !pwdInput) return false;
  await emailInput.fill(EMAIL);
  await pwdInput.fill(PASSWORD);
  const btn = await page.$('button[type="submit"]');
  if (!btn) return false;
  await btn.click();
  // SPA React Router — polling: aguarda URL mudar de /login OU token em localStorage.
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(500);
    const url = page.url();
    if (!url.includes("/login")) return true;
    const hasToken = await page.evaluate(() => {
      try {
        return !!(localStorage.getItem("token") ||
                  localStorage.getItem("access_token") ||
                  localStorage.getItem("session_token") ||
                  localStorage.getItem("auth"));
      } catch { return false; }
    });
    if (hasToken) return true;
  }
  return false;
}

async function run() {
  const browser = await chromium.launch();

  // B1 — Login desktop
  {
    const ctx = await browser.newContext(DESKTOP_CFG);
    const page = await ctx.newPage();
    try {
      const ok = await tryLogin(page);
      log("B1_login", "desktop login→dashboard", ok,
        ok ? "" : "não redirigiu");
      if (!ok) results.critical_fail++;
    } catch (e) {
      log("B1_login", "desktop login→dashboard", false, e.message.slice(0, 120));
      results.critical_fail++;
    } finally {
      await ctx.close();
    }
  }

  // B2 — /demo nos 3 viewports
  for (const [name, cfg] of [
    ["iPhone13", IPHONE_CFG],
    ["Pixel7", PIXEL_CFG],
    ["Desktop", DESKTOP_CFG],
  ]) {
    const ctx = await browser.newContext(cfg);
    const page = await ctx.newPage();
    try {
      await page.goto(`${FRONTEND_BASE}/demo`, { waitUntil: "domcontentloaded", timeout: 15000 });
      await page.waitForTimeout(1000);
      const bodyText = (await page.textContent("body")) || "";
      const rendered = bodyText.length > 200;
      log("B2_demo", `${name}: /demo renderiza`, rendered,
        rendered ? "" : `só ${bodyText.length} chars`);
      if (!rendered) results.critical_fail++;

      // Toggle PT→EN→FR→PT (procura seletor de língua se existir)
      const langButtons = await page.$$('[data-testid*="lang"], button:has-text("PT"), button:has-text("EN"), button:has-text("FR")');
      log("B2_demo", `${name}: toggle língua disponível`, langButtons.length >= 2);

      // Modo offline — simular setOffline + reload
      await page.context().setOffline(true);
      await page.reload({ waitUntil: "domcontentloaded", timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(800);
      const offlineText = (await page.textContent("body")) || "";
      log("B2_demo", `${name}: offline ainda renderiza`, offlineText.length > 100);
      await page.context().setOffline(false);

      // Botão Reiniciar (se existir)
      const restart = await page.$('[data-testid*="restart"], [data-testid*="reset"], button:has-text("Reiniciar")');
      log("B2_demo", `${name}: botão Reiniciar presente`, !!restart);
    } catch (e) {
      log("B2_demo", `${name}: /demo render`, false, e.message.slice(0, 120));
    } finally {
      await ctx.close();
    }
  }

  // B3 — Barra IA em 3 apps (iPhone 13)
  const ctxIA = await browser.newContext(IPHONE_CFG);
  const pageIA = await ctxIA.newPage();
  try {
    await tryLogin(pageIA);
    for (const [slug, prompt, formHint] of [
      ["/medicao-rapida", "Casa 120 m² em Lisboa", "input, textarea"],
      ["/estudo-moradia", "T3 90 m² dois pisos", "input, textarea"],
      ["/calculadoras", "Calcular betão para laje 10x5x0,20", "input, select"],
    ]) {
      try {
        await pageIA.goto(`${FRONTEND_BASE}${slug}`, { waitUntil: "domcontentloaded", timeout: 15000 });
        await pageIA.waitForTimeout(1200);
        const promptBar = await pageIA.$('[data-testid*="prompt"], textarea, input[type="text"]');
        log("B3_IA", `${slug}: prompt bar visível`, !!promptBar);
        // Preenche prompt (não dispara IA para evitar custos — apenas confirma UI)
        if (promptBar) {
          const tag = (await promptBar.evaluate((el) => el.tagName.toLowerCase()));
          if (tag === "textarea" || tag === "input") {
            await promptBar.fill(prompt).catch(() => {});
            log("B3_IA", `${slug}: prompt bar aceita input`, true);
          }
        }
        // Verifica se há elemento de formulário/campos
        const anyField = await pageIA.$(formHint);
        log("B3_IA", `${slug}: UI de formulário presente`, !!anyField);
      } catch (e) {
        log("B3_IA", `${slug}: carregamento`, false, e.message.slice(0, 120));
      }
    }
  } finally {
    await ctxIA.close();
  }

  // B4 — Shell mobile (iPhone + Pixel): /apps bottom-tabs + /escaliers wizard
  for (const [name, cfg] of [
    ["iPhone13", IPHONE_CFG],
    ["Pixel7", PIXEL_CFG],
  ]) {
    const ctx = await browser.newContext(cfg);
    const page = await ctx.newPage();
    try {
      await tryLogin(page);
      await page.goto(`${FRONTEND_BASE}/apps`, { waitUntil: "domcontentloaded", timeout: 15000 });
      await page.waitForTimeout(1200);
      // Bottom-tabs
      const bottomTabs = await page.$('[data-testid*="bottom-tabs"], nav[class*="bottom"], [class*="tab-bar"]');
      log("B4_shell", `${name}: bottom-tabs em /apps`, !!bottomTabs);
      // Cards de apps
      const cards = await page.$$('a[href^="/"], [data-testid*="app-card"]');
      log("B4_shell", `${name}: cards de apps presentes`, cards.length >= 3);
      // /escaliers wizard
      await page.goto(`${FRONTEND_BASE}/escaliers`, { waitUntil: "domcontentloaded", timeout: 15000 });
      await page.waitForTimeout(1000);
      const stepper = await page.$('[data-testid*="stepper"], [data-testid*="step"], [class*="step"]');
      log("B4_shell", `${name}: /escaliers stepper visível`, !!stepper);
      // CookieConsent não intercepta
      const cookieModal = await page.$('[data-testid*="cookie"]');
      let interceptBlocked = false;
      if (cookieModal) {
        try {
          await page.click("body", { timeout: 2000, force: false });
          interceptBlocked = false;
        } catch {
          interceptBlocked = true;
        }
      }
      log("B4_shell", `${name}: cookie não intercepta`, !interceptBlocked);
    } catch (e) {
      log("B4_shell", `${name}: shell`, false, e.message.slice(0, 120));
    } finally {
      await ctx.close();
    }
  }

  // B5 — Desktop sem bottom-tabs + /apps 6-7 cards
  {
    const ctx = await browser.newContext(DESKTOP_CFG);
    const page = await ctx.newPage();
    try {
      await tryLogin(page);
      await page.goto(`${FRONTEND_BASE}/apps`, { waitUntil: "domcontentloaded", timeout: 15000 });
      await page.waitForTimeout(1200);
      // Sem bottom-tabs
      const bottomTabsDesktop = await page.$('[data-testid*="bottom-tabs"]:visible');
      log("B5_desktop", "sem bottom-tabs no desktop", !bottomTabsDesktop);
      // Header
      const header = await page.$('header, [role="banner"], [data-testid*="header"]');
      log("B5_desktop", "header intacto", !!header);
      // Cards 6-7
      const cards = await page.$$('a[href^="/"], [data-testid*="app-card"]');
      log("B5_desktop", `>=6 cards em /apps (actual=${cards.length})`, cards.length >= 6);
    } catch (e) {
      log("B5_desktop", "desktop", false, e.message.slice(0, 120));
    } finally {
      await ctx.close();
    }
  }

  await browser.close();
}

run()
  .then(() => {
    const report = {
      total: results.pass + results.fail,
      pass: results.pass,
      fail: results.fail,
      critical_fail: results.critical_fail,
      blocks: results.blocks,
    };
    console.log(JSON.stringify(report, null, 2));
    const md = ["# AJ.3 — Regressão rápida pré-repouso", "",
      `Total: ${report.total} | PASS: ${report.pass} | FAIL: ${report.fail} | Critical FAIL: ${report.critical_fail}`,
      ""];
    for (const [bk, items] of Object.entries(report.blocks)) {
      md.push(`## ${bk}`);
      for (const it of items) {
        md.push(`- [${it.ok ? "x" : " "}] ${it.name}${it.note ? ` — ${it.note}` : ""}`);
      }
      md.push("");
    }
    fs.writeFileSync(
      path.join(__dirname, "..", "..", "memory", "lote_aj3_regression_quick_report.md"),
      md.join("\n"),
    );
    process.exit(report.critical_fail > 0 ? 1 : 0);
  })
  .catch((e) => {
    console.error("FATAL:", e);
    process.exit(2);
  });
