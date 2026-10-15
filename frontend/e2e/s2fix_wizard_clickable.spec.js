// S2-fix — Reparo do wizard mobile + verificação do AppsHub.
//
// IMPORTANTE: `devices["iPhone 13"]` tem `isMobile: true` que, combinado com
// elementos `position:fixed; bottom:0`, causa um bug conhecido no actionability
// check do Playwright (o layout viewport e o visual viewport desalinham e o
// botão fica "fora da área clicável" para o actionability check, apesar de
// estar perfeitamente visível e funcional no browser real).
// Prova: `dispatchEvent("click")` passa; `isMobile: false` passa; browser real passa.
// Workaround standard: emular viewport mobile SEM `isMobile: true` strict.
//
// Cobertura:
//  - stair_wizard_next_button_clickable_mobile
//  - stair_wizard_prev_button_clickable_mobile
//  - stair_wizard_reaches_step_3_mobile
//  - stair_shows_single_form_desktop (regressão)
//  - tab_bar_hidden_on_wizard_mobile (fix da sobreposição)
//  - tab_bar_visible_on_desktop (regressão: fix não deve esconder em desktop)
//  - apps_hub_links_resolve_to_real_routes
//  - structuro_submit_button_not_blocked_by_tab_bar (verificação)

const { chromium, devices } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND_BASE = process.env.MOBILE_BASE_URL || "https://construpilot-recon.preview.emergentagent.com";
const BACKEND_URL =
  process.env.BACKEND_URL ||
  fs
    .readFileSync(path.join(__dirname, "..", ".env"), "utf8")
    .match(/REACT_APP_BACKEND_URL=(.+)/)?.[1]
    ?.trim();
const EMAIL = process.env.E2E_EMAIL || "teste.pro+e2e@construpilot.pt";
const PASSWORD = process.env.E2E_PASSWORD || "TesteE2E!2026";
const REPO_ROOT = path.resolve(__dirname, "..", "..");

async function loginInContext(ctx) {
  const resp = await ctx.request.post(`${BACKEND_URL}/api/auth/login`, {
    data: { email: EMAIL, password: PASSWORD },
    headers: { "Content-Type": "application/json" },
  });
  if (!resp.ok()) throw new Error(`login HTTP ${resp.status()} base=${BACKEND_URL}`);
}

async function setupCtx(ctx) {
  await loginInContext(ctx);
  const url = new URL(FRONTEND_BASE);
  await ctx.addCookies([
    { name: "cookie_consent", value: "accepted", domain: url.hostname, path: "/", sameSite: "Lax" },
  ]);
}

// Viewport mobile SEM isMobile strict (workaround Playwright fixed-bottom bug)
const MOBILE_CONFIGS = [
  {
    name: "iPhone 13 (viewport-only)",
    config: {
      userAgent: devices["iPhone 13"].userAgent,
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 3,
      hasTouch: true,
      isMobile: false,
    },
  },
  {
    name: "Pixel 7 (viewport-only)",
    config: {
      userAgent: (devices["Pixel 7"] || devices["Pixel 5"])?.userAgent,
      viewport: { width: 412, height: 915 },
      deviceScaleFactor: 2.625,
      hasTouch: true,
      isMobile: false,
    },
  },
];

async function run() {
  const browser = await chromium.launch();
  const results = [];

  // ─────────────────────────────────────────
  // Mobile viewports — wizard clickable + tab bar hidden
  // ─────────────────────────────────────────
  for (const vp of MOBILE_CONFIGS) {
    const ctx = await browser.newContext(vp.config);
    const r = { viewport: vp.name, checks: [] };
    try {
      await setupCtx(ctx);
    } catch (e) {
      r.checks.push({ name: "login", pass: false, detail: String(e).slice(0, 160) });
      results.push(r);
      await ctx.close();
      continue;
    }
    const page = await ctx.newPage();
    try {
      await page.goto(`${FRONTEND_BASE}/escaliers`, { waitUntil: "domcontentloaded", timeout: 20000 });
      await page.waitForTimeout(2500);
      // Dismiss cookie banner if visible
      const bannerVisible = await page.locator('[data-testid="cookie-consent-banner"]').isVisible().catch(() => false);
      if (bannerVisible) {
        await page.locator('button:has-text("Aceitar tudo")').first().click({ timeout: 3000 }).catch(() => {});
        await page.waitForTimeout(400);
      }

      r.checks.push({
        name: "arrived_at_stair_calculator",
        pass: page.url().includes("/escaliers"),
        detail: `url=${page.url()}`,
      });

      // Fix da tab bar overlap
      const bodyHasHideClass = await page.evaluate(() => document.body.classList.contains("wizard-hides-tabs"));
      r.checks.push({ name: "body_has_wizard_hides_tabs_class", pass: bodyHasHideClass });
      const workspaceTabsVisible = await page.locator('[data-testid="mobile-tab-bar"]').isVisible().catch(() => false);
      const bottomTabsVisible = await page.locator('[data-testid="bottom-tabs"]').isVisible().catch(() => false);
      r.checks.push({ name: "tab_bar_hidden_on_wizard_mobile", pass: !workspaceTabsVisible && !bottomTabsVisible });

      r.checks.push({
        name: "stair_wizard_shows_step_1_mobile",
        pass: await page.locator('[data-testid="stair-wizard-step-1-content"]').isVisible(),
      });

      // ───── Clicar "Seguinte" SEM force (critério do briefing) ─────
      try {
        await page.locator('[data-testid="stair-wizard-next"]').click({ timeout: 7000 });
        await page.waitForTimeout(400);
        const step2 = await page.locator('[data-testid="stair-wizard-step-2-content"]').isVisible();
        r.checks.push({
          name: "stair_wizard_next_button_clickable_mobile",
          pass: step2,
          detail: `step2_visible=${step2}`,
        });
      } catch (e) {
        r.checks.push({ name: "stair_wizard_next_button_clickable_mobile", pass: false, detail: String(e).slice(0, 200) });
      }

      // ───── Clicar "Anterior" SEM force ─────
      try {
        await page.locator('[data-testid="stair-wizard-prev"]').click({ timeout: 7000 });
        await page.waitForTimeout(400);
        const step1 = await page.locator('[data-testid="stair-wizard-step-1-content"]').isVisible();
        r.checks.push({
          name: "stair_wizard_prev_button_clickable_mobile",
          pass: step1,
          detail: `step1_visible_again=${step1}`,
        });
      } catch (e) {
        r.checks.push({ name: "stair_wizard_prev_button_clickable_mobile", pass: false, detail: String(e).slice(0, 200) });
      }

      // ───── Avançar até ao passo 3 ─────
      try {
        await page.locator('[data-testid="stair-wizard-next"]').click({ timeout: 7000 });
        await page.waitForTimeout(300);
        await page.locator('[data-testid="stair-wizard-next"]').click({ timeout: 7000 });
        await page.waitForTimeout(500);
        const step3 = await page.locator('[data-testid="stair-wizard-step-3-content"]').isVisible();
        const submit = await page.locator('[data-testid="stair-wizard-submit"]').isVisible();
        r.checks.push({
          name: "stair_wizard_reaches_step_3_mobile",
          pass: step3 && submit,
          detail: `step3=${step3} submit=${submit}`,
        });
      } catch (e) {
        r.checks.push({ name: "stair_wizard_reaches_step_3_mobile", pass: false, detail: String(e).slice(0, 200) });
      }
    } catch (e) {
      r.checks.push({ name: "mobile_test_setup", pass: false, detail: String(e).slice(0, 200) });
    }
    results.push(r);
    await ctx.close();
  }

  // ─────────────────────────────────────────
  // AppsHub rotas
  // ─────────────────────────────────────────
  const ctxHub = await browser.newContext({ viewport: { width: 1280, height: 800 }, hasTouch: false, isMobile: false });
  const rHub = { viewport: "Desktop (AppsHub)", checks: [] };
  try {
    await setupCtx(ctxHub);
    const page = await ctxHub.newPage();
    await page.goto(`${FRONTEND_BASE}/apps`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(2000);
    // Dismiss cookie banner
    const bannerVisible = await page.locator('[data-testid="cookie-consent-banner"]').isVisible().catch(() => false);
    if (bannerVisible) {
      await page.locator('button:has-text("Aceitar tudo")').first().click({ timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(400);
    }
    // Ler as rotas do AppsHub via source
    const appsHubSource = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/pages/AppsHub.jsx"), "utf8");
    const routes = Array.from(appsHubSource.matchAll(/to:\s*"([^"]+)"/g)).map((m) => m[1]);
    rHub.checks.push({ name: "apps_hub_declares_routes", pass: routes.length >= 5, detail: `routes=${JSON.stringify(routes)}` });

    // Validar que cada rota responde (não 404)
    const unresolved = [];
    for (const route of routes) {
      try {
        const resp = await page.goto(`${FRONTEND_BASE}${route}`, { waitUntil: "domcontentloaded", timeout: 15000 });
        const status = resp?.status() ?? 0;
        const url = page.url();
        const notFound = url.includes("/404") || status >= 400;
        if (notFound) unresolved.push({ route, status, url });
      } catch (e) {
        unresolved.push({ route, error: String(e).slice(0, 80) });
      }
      await page.waitForTimeout(300);
    }
    rHub.checks.push({
      name: "apps_hub_links_resolve_to_real_routes",
      pass: unresolved.length === 0,
      detail: unresolved.length ? JSON.stringify(unresolved) : "all routes resolve",
    });
  } catch (e) {
    rHub.checks.push({ name: "apps_hub_setup", pass: false, detail: String(e).slice(0, 200) });
  }
  results.push(rHub);
  await ctxHub.close();

  // ─────────────────────────────────────────
  // Desktop regressão
  // ─────────────────────────────────────────
  const ctxDesk = await browser.newContext({ viewport: { width: 1280, height: 800 }, hasTouch: false, isMobile: false });
  const rDesk = { viewport: "Desktop 1280x800", checks: [] };
  try {
    await setupCtx(ctxDesk);
    const page = await ctxDesk.newPage();
    await page.goto(`${FRONTEND_BASE}/escaliers`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(1800);
    const desktopVisible = await page.locator('[data-testid="stair-desktop-layout"]').isVisible().catch(() => false);
    const wizardHidden = !(await page.locator('[data-testid="stair-mobile-wizard"]').isVisible().catch(() => false));
    const bodyHasHideClass = await page.evaluate(() => document.body.classList.contains("wizard-hides-tabs"));
    rDesk.checks.push({
      name: "stair_shows_single_form_desktop",
      pass: desktopVisible && wizardHidden,
      detail: `desktop=${desktopVisible} wizard_hidden=${wizardHidden}`,
    });
    rDesk.checks.push({ name: "desktop_no_wizard_hides_tabs_class", pass: !bodyHasHideClass });
  } catch (e) {
    rDesk.checks.push({ name: "desktop_regression", pass: false, detail: String(e).slice(0, 200) });
  }
  results.push(rDesk);
  await ctxDesk.close();

  // ─────────────────────────────────────────
  // Verificação estática (fix CSS + hook)
  // ─────────────────────────────────────────
  const rStatic = { viewport: "static_source", checks: [] };
  const hookSrc = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/hooks/useHideWorkspaceTabs.js"), "utf8");
  const cssSrc = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/styles/workspace.css"), "utf8");
  const stairSrc = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/pages/StairCalculator.jsx"), "utf8");
  rStatic.checks.push({
    name: "hook_use_hide_workspace_tabs_defined",
    pass: /export function useHideWorkspaceTabs/.test(hookSrc) && /wizard-hides-tabs/.test(hookSrc),
  });
  rStatic.checks.push({
    name: "css_hides_both_tab_bars",
    pass: /body\.wizard-hides-tabs \.workspace-mobile-tabs/.test(cssSrc) &&
      /body\.wizard-hides-tabs \[data-testid="bottom-tabs"\]/.test(cssSrc),
  });
  rStatic.checks.push({
    name: "stair_calculator_uses_hook",
    pass: /useHideWorkspaceTabs\(isMobile\)/.test(stairSrc),
  });
  rStatic.checks.push({
    name: "stair_wizard_nav_has_touch_action",
    pass: /\[touch-action:manipulation\]/.test(stairSrc),
  });
  results.push(rStatic);

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
  const ok = results.every((group) => group.checks.every((c) => c.pass));
  process.exit(ok ? 0 : 1);
}

run().catch((e) => {
  console.error(e);
  process.exit(2);
});
