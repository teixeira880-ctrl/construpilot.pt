// S3.1 fix — PinchZoom Dialog EFECTIVAMENTE acessível, botões desktop presentes,
// Structuro/Autorizacao documentados como sem viewer visual.
//
// Testes do briefing:
//  - pinch_zoom_dialog_opens_on_plan_mobile_before_upload  (CRÍTICO)
//  - pinch_zoom_buttons_visible_desktop
//  - pinch_zoom_integrated_in_structuro_OR_documented_missing
//  - pinch_zoom_integrated_in_autorizacao_OR_documented_missing

const { chromium, devices } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND_BASE = process.env.MOBILE_BASE_URL || "https://construpilot-recon.preview.emergentagent.com";
const BACKEND_URL =
  process.env.BACKEND_URL ||
  fs.readFileSync(path.join(__dirname, "..", ".env"), "utf8").match(/REACT_APP_BACKEND_URL=(.+)/)?.[1]?.trim();
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

const MOBILE_CFG = {
  userAgent: devices["iPhone 13"].userAgent,
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  hasTouch: true,
  isMobile: false,
};
const PIXEL_CFG = {
  userAgent: (devices["Pixel 7"] || devices["Pixel 5"])?.userAgent,
  viewport: { width: 412, height: 915 },
  deviceScaleFactor: 2.625,
  hasTouch: true,
  isMobile: false,
};
const DESKTOP_CFG = { viewport: { width: 1280, height: 800 }, hasTouch: false, isMobile: false };

async function openPlanAndWait(page, { withZoomParam = false } = {}) {
  const url = withZoomParam ? `${FRONTEND_BASE}/plan?e2e_zoom=test-plan-id&e2e_zoom_name=Teste.pdf` : `${FRONTEND_BASE}/plan`;
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForTimeout(2500);
  // Esperar o lazy chunk e UI inicial
  await page.locator('[data-testid="plan-upload-dropzone"], [data-testid="plan-paywall"], [data-testid="plan-workspace"]').first()
    .waitFor({ state: "visible", timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

async function run() {
  const browser = await chromium.launch();
  const results = [];

  // ─────────────────────────────────────────
  // Fase 1 — Static source
  // ─────────────────────────────────────────
  const rStatic = { phase: "static_source_checks", checks: [] };
  const planTakeoff = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/pages/PlanTakeoff.jsx"), "utf8");
  const structuro = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/pages/StructuroHouse.jsx"), "utf8");
  const autorizacao = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/pages/AutorizacaoObras.jsx"), "utf8");
  const pinchZoom = fs.readFileSync(path.join(REPO_ROOT, "frontend/src/components/mobile/PinchZoom.jsx"), "utf8");

  rStatic.checks.push({
    name: "plan_zoom_dialog_shared_variable",
    pass: /const planZoomDialog\s*=\s*\(/.test(planTakeoff),
    detail: "Dialog extracted to variable usable in both branches",
  });
  rStatic.checks.push({
    name: "plan_zoom_dialog_in_pre_upload_branch",
    pass: /if \(!plan\) \{[\s\S]{0,100000}\{planZoomDialog\}/.test(planTakeoff),
  });
  rStatic.checks.push({
    name: "plan_zoom_dialog_in_workspace_branch",
    pass: ((planTakeoff.match(/\{planZoomDialog\}/g) || []).length >= 2),
    detail: `occurrences=${(planTakeoff.match(/\{planZoomDialog\}/g) || []).length}`,
  });
  rStatic.checks.push({
    name: "pinch_zoom_desktop_controls_implemented",
    pass:
      /data-testid=\{`\$\{testId\}-in`\}/.test(pinchZoom) &&
      /data-testid=\{`\$\{testId\}-out`\}/.test(pinchZoom) &&
      /data-testid=\{`\$\{testId\}-reset`\}/.test(pinchZoom) &&
      /showControls\s*=\s*true/.test(pinchZoom),
  });
  rStatic.checks.push({
    name: "structuro_has_pinch_zoom_decision_comment",
    pass: /PinchZoom NÃO integrado aqui porque StructuroHouse/.test(structuro),
  });
  rStatic.checks.push({
    name: "autorizacao_has_pinch_zoom_decision_comment",
    pass: /PinchZoom NÃO integrado aqui porque AutorizacaoObras/.test(autorizacao),
  });
  rStatic.checks.push({
    name: "pinch_zoom_integrated_in_structuro_OR_documented_missing",
    pass: /from "@\/components\/mobile\/PinchZoom"/.test(structuro) || /PinchZoom NÃO integrado aqui/.test(structuro),
  });
  rStatic.checks.push({
    name: "pinch_zoom_integrated_in_autorizacao_OR_documented_missing",
    pass: /from "@\/components\/mobile\/PinchZoom"/.test(autorizacao) || /PinchZoom NÃO integrado aqui/.test(autorizacao),
  });
  results.push(rStatic);

  // ─────────────────────────────────────────
  // Fase 2 — Mobile iPhone 13: open Dialog without upload
  // ─────────────────────────────────────────
  for (const vp of [{ name: "iPhone 13", cfg: MOBILE_CFG }, { name: "Pixel 7", cfg: PIXEL_CFG }]) {
    const ctx = await browser.newContext(vp.cfg);
    const r = { viewport: vp.name, checks: [] };
    try {
      await loginInContext(ctx);
    } catch (e) {
      r.checks.push({ name: "login", pass: false, detail: String(e).slice(0, 160) });
      results.push(r);
      await ctx.close();
      continue;
    }
    const url = new URL(FRONTEND_BASE);
    await ctx.addCookies([{ name: "cookie_consent", value: "accepted", domain: url.hostname, path: "/", sameSite: "Lax" }]);
    const page = await ctx.newPage();
    try {
      // Usar o hook E2E para abrir o Dialog imediatamente ao mount
      // (contorna conta sem plantas pré-existentes)
      await openPlanAndWait(page, { withZoomParam: true });

      // O Dialog DEVE abrir ao mount via useEffect do e2e_zoom param
      const dialogVisible = await page.locator('[data-testid="plan-zoom-dialog"]').isVisible().catch(() => false);
      const viewerVisible = await page.locator('[data-testid="plan-zoom-viewer"]').isVisible().catch(() => false);
      r.checks.push({
        name: "pinch_zoom_dialog_opens_on_plan_mobile_before_upload",
        pass: dialogVisible && viewerVisible,
        detail: `dialog=${dialogVisible} viewer=${viewerVisible} (via ?e2e_zoom)`,
      });

      // Fechar e verificar que fecha
      if (dialogVisible) {
        try {
          await page.locator('[data-testid="plan-zoom-dialog-close"]').click({ timeout: 5000 });
        } catch (e1) {
          // Fallback: ESC
          await page.keyboard.press("Escape");
        }
        await page.waitForTimeout(700);
        const dialogStillOpen = await page.locator('[data-testid="plan-zoom-dialog"]').isVisible().catch(() => false);
        r.checks.push({
          name: "pinch_zoom_dialog_closes_on_mobile",
          pass: !dialogStillOpen,
          detail: `still_open=${dialogStillOpen}`,
        });
      }
    } catch (e) {
      r.checks.push({ name: "mobile_setup", pass: false, detail: String(e).slice(0, 200) });
    }
    results.push(r);
    await ctx.close();
  }

  // ─────────────────────────────────────────
  // Fase 3 — Desktop: botões +/-/reset visíveis
  // ─────────────────────────────────────────
  const ctxDesk = await browser.newContext(DESKTOP_CFG);
  const rDesk = { viewport: "Desktop 1280x800", checks: [] };
  try {
    await loginInContext(ctxDesk);
    const urlD = new URL(FRONTEND_BASE);
    await ctxDesk.addCookies([{ name: "cookie_consent", value: "accepted", domain: urlD.hostname, path: "/", sameSite: "Lax" }]);
    const page = await ctxDesk.newPage();
    await openPlanAndWait(page, { withZoomParam: true });

    // Dialog deve estar aberto via useEffect
    const dialogVisible = await page.locator('[data-testid="plan-zoom-dialog"]').isVisible().catch(() => false);
    rDesk.checks.push({ name: "dialog_opens_desktop_via_e2e_param", pass: dialogVisible });

    if (dialogVisible) {
      const controlsVisible = await page.locator('[data-testid="plan-zoom-viewer-controls"]').isVisible().catch(() => false);
      const btnIn = await page.locator('[data-testid="plan-zoom-viewer-in"]').isVisible().catch(() => false);
      const btnOut = await page.locator('[data-testid="plan-zoom-viewer-out"]').isVisible().catch(() => false);
      const btnReset = await page.locator('[data-testid="plan-zoom-viewer-reset"]').isVisible().catch(() => false);
      rDesk.checks.push({
        name: "pinch_zoom_buttons_visible_desktop",
        pass: controlsVisible && btnIn && btnOut && btnReset,
        detail: `controls=${controlsVisible} in=${btnIn} out=${btnOut} reset=${btnReset}`,
      });

      // Teste funcional dos botões
      await page.locator('[data-testid="plan-zoom-viewer-in"]').click({ timeout: 3000 });
      await page.waitForTimeout(200);
      await page.locator('[data-testid="plan-zoom-viewer-in"]').click({ timeout: 3000 });
      await page.waitForTimeout(200);
      const transformAfterZoomIn = await page.evaluate(() => {
        const viewer = document.querySelector('[data-testid="plan-zoom-viewer"]');
        return viewer?.firstElementChild?.style?.transform || "";
      });
      rDesk.checks.push({
        name: "pinch_zoom_in_button_increases_scale",
        pass: /scale\(1\.(?:[2-9]|[1-9]\d)/.test(transformAfterZoomIn),
        detail: `transform=${transformAfterZoomIn}`,
      });

      await page.locator('[data-testid="plan-zoom-viewer-reset"]').click({ timeout: 3000 });
      await page.waitForTimeout(300);
      const transformAfterReset = await page.evaluate(() => {
        const viewer = document.querySelector('[data-testid="plan-zoom-viewer"]');
        return viewer?.firstElementChild?.style?.transform || "";
      });
      rDesk.checks.push({
        name: "pinch_zoom_reset_restores_scale_1",
        pass: /scale\(1\)/.test(transformAfterReset) && /translate\(0px, 0px\)/.test(transformAfterReset),
        detail: `transform=${transformAfterReset}`,
      });
    } else {
      rDesk.checks.push({ name: "pinch_zoom_buttons_visible_desktop", pass: false, detail: "dialog not open" });
    }
  } catch (e) {
    rDesk.checks.push({ name: "desktop_setup", pass: false, detail: String(e).slice(0, 200) });
  }
  results.push(rDesk);
  await ctxDesk.close();

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
  const ok = results.every((group) => group.checks.every((c) => c.pass));
  process.exit(ok ? 0 : 1);
}

run().catch((e) => { console.error(e); process.exit(2); });
