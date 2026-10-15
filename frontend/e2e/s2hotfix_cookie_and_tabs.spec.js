// S2.1 + S2.2 hotfix verification.
//
// S2.1 — CookieConsent com pointer-events selectivo: o wrapper externo tem
//        pointer-events:none; só a card interna com os botões tem
//        pointer-events:auto. Logo o utilizador pode clicar em conteúdo por
//        baixo mesmo com o banner visível.
//
// S2.2 — Em /apps mobile autenticado, apenas a BottomTabBar global aparece
//        (MobileTabBar workspace escondida). Em /compte e /chantiers, mantém-se
//        a MobileTabBar workspace e BottomTabBar escondida.

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
  if (!resp.ok()) throw new Error(`login HTTP ${resp.status()}`);
}

const MOBILE_CONFIG = {
  userAgent: devices["iPhone 13"].userAgent,
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  hasTouch: true,
  isMobile: false, // workaround Playwright fixed-bottom bug (ver S2 fix)
};

async function run() {
  const browser = await chromium.launch();
  const results = [];

  // ─────────────────────────────────────────
  // Mobile — /apps: cookie banner não intercepta, apenas 1 tab bar visível
  // ─────────────────────────────────────────
  {
    const ctx = await browser.newContext(MOBILE_CONFIG);
    const r = { viewport: "Mobile /apps", checks: [] };
    try {
      await loginInContext(ctx);
      const page = await ctx.newPage();
      // DELIBERADAMENTE NÃO aceitar o cookie banner — teste é precisamente
      // que o utilizador consegue clicar cards com o banner visível.
      await page.goto(`${FRONTEND_BASE}/apps`, { waitUntil: "domcontentloaded", timeout: 20000 });
      await page.waitForTimeout(2000);

      // Verifica que o banner ESTÁ visível (não aceitado)
      const bannerVisible = await page.locator('[data-testid="cookie-consent-banner"]').isVisible();
      r.checks.push({ name: "cookie_banner_visible_as_expected", pass: bannerVisible });

      // Verifica pointer-events do wrapper e da card interna
      const peInfo = await page.evaluate(() => {
        const wrapper = document.querySelector('[data-testid="cookie-consent-banner"]');
        if (!wrapper) return null;
        const innerCard = wrapper.querySelector(".flex.flex-col, .sm\\:flex-row");
        const acceptBtn = document.querySelector('[data-testid="cookie-accept-btn"]');
        const acceptBtnContainer = acceptBtn?.parentElement;
        return {
          wrapper_pe: getComputedStyle(wrapper).pointerEvents,
          inner_card_pe: innerCard ? getComputedStyle(innerCard).pointerEvents : null,
          accept_btn_container_pe: acceptBtnContainer ? getComputedStyle(acceptBtnContainer).pointerEvents : null,
          accept_btn_pe: acceptBtn ? getComputedStyle(acceptBtn).pointerEvents : null,
        };
      });
      r.checks.push({
        name: "cookie_banner_wrapper_pointer_events_none",
        pass: peInfo?.wrapper_pe === "none",
        detail: JSON.stringify(peInfo),
      });
      r.checks.push({
        name: "cookie_banner_inner_card_pointer_events_none",
        pass: peInfo?.inner_card_pe === "none",
        detail: JSON.stringify(peInfo),
      });
      r.checks.push({
        name: "cookie_banner_accept_button_still_interactive",
        pass: peInfo?.accept_btn_container_pe === "auto" && peInfo?.accept_btn_pe === "auto",
        detail: JSON.stringify(peInfo),
      });

      // Verifica que apenas UMA tab bar está visível em /apps
      const workspaceTabsVisible = await page.locator('[data-testid="mobile-tab-bar"]').isVisible().catch(() => false);
      const bottomTabsVisible = await page.locator('[data-testid="bottom-tabs"]').isVisible().catch(() => false);
      r.checks.push({
        name: "only_one_tab_bar_visible_on_apps_mobile",
        pass: (workspaceTabsVisible ? 1 : 0) + (bottomTabsVisible ? 1 : 0) === 1,
        detail: `workspace=${workspaceTabsVisible} bottom=${bottomTabsVisible}`,
      });
      r.checks.push({
        name: "apps_mobile_uses_bottom_tabs_as_canonical",
        pass: bottomTabsVisible && !workspaceTabsVisible,
        detail: `workspace=${workspaceTabsVisible} bottom=${bottomTabsVisible}`,
      });

      // ───── TESTE CRÍTICO: clicar cada card do AppsHub SEM dismiss do banner ─────
      const appsSrc = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/pages/AppsHub.jsx"), "utf8");
      const cardIds = Array.from(appsSrc.matchAll(/testId:\s*"([^"]+)"/g)).map((m) => m[1]);
      const unclickable = [];
      for (const tid of cardIds) {
        try {
          // Garantir que o card está visível (scroll se preciso) e tentar click sem force
          await page.goto(`${FRONTEND_BASE}/apps`, { waitUntil: "domcontentloaded", timeout: 15000 });
          await page.waitForTimeout(1500);
          // Scroll até o card (necessário para o último, que o banner cobria)
          await page.locator(`[data-testid="${tid}"]`).scrollIntoViewIfNeeded({ timeout: 3000 });
          await page.waitForTimeout(300);
          await page.locator(`[data-testid="${tid}"]`).click({ timeout: 5000 });
          await page.waitForTimeout(600);
          const navigated = !page.url().endsWith("/apps");
          if (!navigated) unclickable.push({ tid, url: page.url() });
        } catch (e) {
          unclickable.push({ tid, error: String(e).split("\n")[0].slice(0, 120) });
        }
      }
      r.checks.push({
        name: "cookie_banner_does_not_intercept_apps_hub_clicks_mobile",
        pass: unclickable.length === 0,
        detail: unclickable.length ? JSON.stringify(unclickable) : `all ${cardIds.length} cards clickable with banner visible`,
      });
    } catch (e) {
      r.checks.push({ name: "apps_mobile_setup", pass: false, detail: String(e).slice(0, 200) });
    }
    results.push(r);
    await ctx.close();
  }

  // ─────────────────────────────────────────
  // Mobile — /compte e /chantiers: só workspace-mobile-tabs
  // ─────────────────────────────────────────
  for (const route of ["/compte", "/chantiers"]) {
    const ctx = await browser.newContext(MOBILE_CONFIG);
    const r = { viewport: `Mobile ${route}`, checks: [] };
    try {
      await loginInContext(ctx);
      const page = await ctx.newPage();
      await page.goto(`${FRONTEND_BASE}${route}`, { waitUntil: "domcontentloaded", timeout: 20000 });
      await page.waitForTimeout(1800);
      const workspace = await page.locator('[data-testid="mobile-tab-bar"]').isVisible().catch(() => false);
      const bottom = await page.locator('[data-testid="bottom-tabs"]').isVisible().catch(() => false);
      r.checks.push({
        name: `only_one_tab_bar_visible_${route.replace("/", "")}`,
        pass: (workspace ? 1 : 0) + (bottom ? 1 : 0) <= 1,
        detail: `workspace=${workspace} bottom=${bottom}`,
      });
    } catch (e) {
      r.checks.push({ name: "setup", pass: false, detail: String(e).slice(0, 200) });
    }
    results.push(r);
    await ctx.close();
  }

  // ─────────────────────────────────────────
  // Desktop regressão
  // ─────────────────────────────────────────
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, hasTouch: false, isMobile: false });
    const r = { viewport: "Desktop 1280x800", checks: [] };
    try {
      await loginInContext(ctx);
      const page = await ctx.newPage();
      await page.goto(`${FRONTEND_BASE}/apps`, { waitUntil: "domcontentloaded", timeout: 20000 });
      await page.waitForTimeout(1500);
      // Em desktop, as tab bars não estão em display: grid/fixed (CSS só activa em @media <768px).
      // Verificação simples: o grid de cards do AppsHub é visível.
      const hub = await page.locator('[data-testid="apps-hub"]').isVisible();
      r.checks.push({ name: "apps_hub_renders_on_desktop", pass: hub });
    } catch (e) {
      r.checks.push({ name: "desktop_setup", pass: false, detail: String(e).slice(0, 200) });
    }
    results.push(r);
    await ctx.close();
  }

  // ─────────────────────────────────────────
  // Verificação estática
  // ─────────────────────────────────────────
  const rStatic = { viewport: "static_source", checks: [] };
  const cookieSrc = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/components/CookieConsent.jsx"), "utf8");
  const mobileTabBarSrc = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/components/pwa/MobileTabBar.jsx"), "utf8");
  rStatic.checks.push({
    name: "cookie_banner_wrapper_has_pointer_events_none",
    pass: /className="[^"]*pointer-events-none"[\s\S]{0,200}data-testid="cookie-consent-banner"/.test(cookieSrc),
  });
  rStatic.checks.push({
    name: "cookie_banner_inner_card_also_pointer_events_none",
    pass: /flex flex-col sm:flex-row[\s\S]{0,120}pointer-events-none/.test(cookieSrc),
  });
  rStatic.checks.push({
    name: "cookie_banner_action_buttons_have_pointer_events_auto",
    pass: /flex gap-2 shrink-0 pointer-events-auto/.test(cookieSrc),
  });
  rStatic.checks.push({
    name: "mobile_tab_bar_hides_on_apps_route",
    pass: /HIDDEN_PAGES\s*=\s*\[[^\]]*"\/apps"/.test(mobileTabBarSrc),
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
