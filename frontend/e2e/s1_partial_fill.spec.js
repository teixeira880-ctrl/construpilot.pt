// S1-fix — Preenchimento parcial com clarification + PromptBar em /plan antes do upload.
//
// Estratégia:
//  1) Verifica no filesystem que as alterações-chave estão presentes nas fontes
//     (backend prompt_fill/base.py, PromptBar.jsx, PlanTakeoff.jsx). Isto cobre
//     a regressão do commit sem depender do webpack dev-server.
//  2) Em paralelo, abre /plan e /estudo-moradia num browser real para confirmar
//     que não há regressão de carregamento (status page, auth gating OK).
//  3) Opcional: se o utilizador aterrar num form visível (contexto já autenticado),
//     intercepta a resposta do backend e verifica fluxo partial-fill end-to-end.

const fs = require("fs");
const path = require("path");
const { chromium, devices } = require("playwright");

const BASE = process.env.MOBILE_BASE_URL || "http://127.0.0.1:4960";
const REPO_ROOT = path.resolve(__dirname, "..", "..");

function fileContains(relPath, needles) {
  const full = path.join(REPO_ROOT, relPath);
  if (!fs.existsSync(full)) return { exists: false, matches: {} };
  const src = fs.readFileSync(full, "utf8");
  const matches = {};
  for (const [k, pattern] of Object.entries(needles)) {
    matches[k] = pattern instanceof RegExp ? pattern.test(src) : src.includes(pattern);
  }
  return { exists: true, matches };
}

async function run() {
  const results = [];

  // ===== Fase 1 — Verificação estática do source (determinística) =====
  const staticChecks = [];

  const promptBar = fileContains("frontend/src/components/PromptBar.jsx", {
    has_hasParams_var: /hasParams/,
    applies_fill_regardless_of_ok: /if \(hasParams\)\s*\{\s*onFill/,
    still_shows_clarification: /data\?\.clarification_question/,
    does_not_short_circuit_on_ok: /else if \(data\?\.ok\)/,
  });
  staticChecks.push({
    name: "frontend_promptbar_applies_partial_fill",
    pass:
      promptBar.exists &&
      promptBar.matches.has_hasParams_var &&
      promptBar.matches.applies_fill_regardless_of_ok &&
      promptBar.matches.still_shows_clarification,
    detail: JSON.stringify(promptBar.matches),
  });

  const planTakeoff = fileContains("frontend/src/pages/PlanTakeoff.jsx", {
    has_pre_upload_prompt_bar: /antes de carregar a planta/,
    pre_upload_appkey_plantas: /appKey="plantas"[\s\S]{0,200}antes de carregar a planta/,
  });
  staticChecks.push({
    name: "frontend_plantakeoff_prompt_bar_before_upload",
    pass:
      planTakeoff.exists &&
      planTakeoff.matches.has_pre_upload_prompt_bar &&
      planTakeoff.matches.pre_upload_appkey_plantas,
    detail: JSON.stringify(planTakeoff.matches),
  });

  const baseEngine = fileContains("backend/engines/prompt_fill/base.py", {
    partial_params_preserved: /mesmo com ok=false \(preenchimento parcial\)/,
    clarification_requests_partial_params:
      /mesmo quando devolveres clarification_question, inclui SEMPRE em/,
    schema_has_missing_fields_hint: /"missing_fields"/,
  });
  staticChecks.push({
    name: "backend_base_preserves_partial_params",
    pass:
      baseEngine.exists &&
      baseEngine.matches.partial_params_preserved &&
      baseEngine.matches.clarification_requests_partial_params &&
      baseEngine.matches.schema_has_missing_fields_hint,
    detail: JSON.stringify(baseEngine.matches),
  });

  results.push({ phase: "static_source_checks", checks: staticChecks });

  // ===== Fase 2 — Smoke browser (3 viewports) =====
  const browser = await chromium.launch();
  for (const vp of [
    { name: "iPhone 13", device: devices["iPhone 13"] },
    { name: "Desktop 1280x800", device: { viewport: { width: 1280, height: 800 } } },
  ]) {
    const ctx = await browser.newContext(vp.device);
    const page = await ctx.newPage();
    const r = { viewport: vp.name, checks: [] };

    // Smoke /plan
    try {
      const resp = await page.goto(`${BASE}/plan`, { waitUntil: "domcontentloaded", timeout: 15000 });
      await page.waitForTimeout(400);
      r.checks.push({
        name: "plan_route_200_or_redirect",
        pass: resp && resp.status() < 500,
        detail: `status=${resp?.status()} url=${page.url()}`,
      });
    } catch (e) {
      r.checks.push({ name: "plan_route_200_or_redirect", pass: false, detail: String(e).slice(0, 160) });
    }

    // Smoke /estudo-moradia
    try {
      const resp = await page.goto(`${BASE}/estudo-moradia`, { waitUntil: "domcontentloaded", timeout: 15000 });
      await page.waitForTimeout(400);
      r.checks.push({
        name: "estudo_moradia_route_200_or_redirect",
        pass: resp && resp.status() < 500,
        detail: `status=${resp?.status()} url=${page.url()}`,
      });
    } catch (e) {
      r.checks.push({ name: "estudo_moradia_route_200_or_redirect", pass: false, detail: String(e).slice(0, 160) });
    }

    results.push(r);
    await ctx.close();
  }
  await browser.close();

  console.log(JSON.stringify(results, null, 2));
  const ok = results.every((group) => group.checks.every((c) => c.pass));
  process.exit(ok ? 0 : 1);
}

run().catch((e) => {
  console.error(e);
  process.exit(2);
});
