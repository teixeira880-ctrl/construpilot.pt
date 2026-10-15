// S2 — StairCalculator wizard mobile (3 passos) + StructuroHouse secções recolhíveis.
//
// Estratégia (idêntica ao S1-fix validado pelo tester):
//  1) Verificação estática do source (determinística) — provas inequívocas de que
//     os marcadores estão no sítio certo.
//  2) Smoke browser em iPhone 13, Pixel 7 e Desktop 1280×800 — confirma que as
//     rotas respondem (200 ou redirect gated) sem erro de runtime.

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

  // =========================================================
  // Fase 1 — Verificação estática do source
  // =========================================================
  const staticChecks = [];

  // --- StairCalculator ---
  const stair = fileContains("frontend/src/pages/StairCalculator.jsx", {
    imports_use_is_mobile: /from "@\/hooks\/useIsMobile"/,
    uses_is_mobile_hook: /const\s+isMobile\s*=\s*useIsMobile\(\)/,
    declares_wizard_state: /const\s+\[wizardStep,\s*setWizardStep\]\s*=\s*useState\(1\)/,
    wizard_has_three_steps: /WIZARD_STEPS\s*=\s*\[[\s\S]*?Geometria[\s\S]*?Dimensionamento[\s\S]*?Resultados/,
    desktop_hidden_in_mobile: /isMobile\s*\?\s*"hidden"\s*:\s*"grid grid-cols-1 lg:grid-cols-\[380px_1fr\]/,
    mobile_wizard_block: /data-testid="stair-mobile-wizard"/,
    stepper_testid: /data-testid="stair-wizard-stepper"/,
    step1_content: /data-testid="stair-wizard-step-1-content"/,
    step2_content: /data-testid="stair-wizard-step-2-content"/,
    step3_content: /data-testid="stair-wizard-step-3-content"/,
    sticky_nav: /data-testid="stair-wizard-nav"/,
    nav_prev_button: /data-testid="stair-wizard-prev"/,
    nav_next_button: /data-testid="stair-wizard-next"/,
    nav_submit_button: /data-testid="stair-wizard-submit"/,
    auto_advance_on_calc: /if \(isMobile\) setWizardStep\(3\)/,
    pb_safe_padding: /pb-\[max\(0\.75rem,env\(safe-area-inset-bottom\)\)\]/,
    touch_target_min_44: /min-h-\[44px\]/,
    sticky_fixed_bottom: /fixed inset-x-0 bottom-0/,
    dark_classes_wizard: /dark:bg-neutral-900/,
  });
  staticChecks.push({
    name: "stair_calculator_mobile_wizard_present",
    pass:
      stair.exists &&
      stair.matches.imports_use_is_mobile &&
      stair.matches.uses_is_mobile_hook &&
      stair.matches.declares_wizard_state &&
      stair.matches.wizard_has_three_steps &&
      stair.matches.desktop_hidden_in_mobile &&
      stair.matches.mobile_wizard_block &&
      stair.matches.stepper_testid &&
      stair.matches.step1_content &&
      stair.matches.step2_content &&
      stair.matches.step3_content &&
      stair.matches.sticky_nav &&
      stair.matches.nav_prev_button &&
      stair.matches.nav_next_button &&
      stair.matches.nav_submit_button &&
      stair.matches.auto_advance_on_calc &&
      stair.matches.pb_safe_padding &&
      stair.matches.touch_target_min_44 &&
      stair.matches.sticky_fixed_bottom &&
      stair.matches.dark_classes_wizard,
    detail: JSON.stringify(stair.matches),
  });

  // --- StructuroHouse ---
  const structuro = fileContains("frontend/src/pages/StructuroHouse.jsx", {
    imports_use_is_mobile: /from "@\/hooks\/useIsMobile"/,
    uses_is_mobile_hook: /const\s+isMobile\s*=\s*useIsMobile\(\)/,
    collapsible_component_defined: /function Collapsible\(/,
    collapsible_uses_details_in_mobile: /<details[\s\S]{0,200}data-testid=\{testId\}/,
    collapsible_renders_section_in_desktop: /if \(!isMobile\)[\s\S]{0,300}<section/,
    section_geometry_testid: /testId="structuro-section-geometry"/,
    section_floors_testid: /testId="structuro-section-floors"/,
    section_basement_testid: /testId="structuro-section-basement"/,
    first_section_default_open: /defaultOpen[\s\S]{0,120}structuro-section-geometry/,
    second_not_open_by_default: /testId="structuro-section-floors"[\s\S]{0,300}title="Pisos"/,
    chevron_rotates: /group-open:rotate-180/,
    chevron_imported: /ChevronDown/,
    dark_classes: /dark:border-neutral-800/,
  });
  // garantir que a secção "Pisos" NÃO tem `defaultOpen` entre a sua declaração e o fecho do componente
  const srcStructuro = fs.existsSync(path.join(REPO_ROOT, "frontend/src/pages/StructuroHouse.jsx"))
    ? fs.readFileSync(path.join(REPO_ROOT, "frontend/src/pages/StructuroHouse.jsx"), "utf8")
    : "";
  const floorsBlock = srcStructuro.match(/testId="structuro-section-floors"[\s\S]{0,250}>/);
  const floorsHasDefaultOpen = !!(floorsBlock && floorsBlock[0].includes("defaultOpen"));
  staticChecks.push({
    name: "structuro_house_collapsible_sections_present",
    pass:
      structuro.exists &&
      structuro.matches.imports_use_is_mobile &&
      structuro.matches.uses_is_mobile_hook &&
      structuro.matches.collapsible_component_defined &&
      structuro.matches.collapsible_uses_details_in_mobile &&
      structuro.matches.collapsible_renders_section_in_desktop &&
      structuro.matches.section_geometry_testid &&
      structuro.matches.section_floors_testid &&
      structuro.matches.section_basement_testid &&
      structuro.matches.first_section_default_open &&
      structuro.matches.chevron_rotates &&
      structuro.matches.chevron_imported &&
      structuro.matches.dark_classes &&
      !floorsHasDefaultOpen,
    detail: JSON.stringify({ ...structuro.matches, floors_default_open: floorsHasDefaultOpen }),
  });

  // --- Hook useIsMobile ---
  const hook = fileContains("frontend/src/hooks/useIsMobile.js", {
    exports_named: /export function useIsMobile/,
    exports_default: /export default useIsMobile/,
    uses_match_media: /matchMedia/,
    breakpoint_767: /767\.98/,
    ssr_safe: /typeof window === "undefined"/,
  });
  staticChecks.push({
    name: "use_is_mobile_hook_valid",
    pass:
      hook.exists &&
      hook.matches.exports_named &&
      hook.matches.exports_default &&
      hook.matches.uses_match_media &&
      hook.matches.breakpoint_767 &&
      hook.matches.ssr_safe,
    detail: JSON.stringify(hook.matches),
  });

  results.push({ phase: "static_source_checks", checks: staticChecks });

  // =========================================================
  // Fase 2 — Smoke browser (3 viewports)
  // =========================================================
  const browser = await chromium.launch();
  for (const vp of [
    { name: "iPhone 13", device: devices["iPhone 13"] },
    { name: "Pixel 7", device: devices["Pixel 7"] || devices["Pixel 5"] },
    { name: "Desktop 1280x800", device: { viewport: { width: 1280, height: 800 } } },
  ]) {
    const ctx = await browser.newContext(vp.device);
    const page = await ctx.newPage();
    const r = { viewport: vp.name, checks: [] };

    for (const route of ["/escaliers", "/estudo-moradia"]) {
      try {
        const resp = await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded", timeout: 15000 });
        await page.waitForTimeout(400);
        r.checks.push({
          name: `${route}_route_200_or_redirect`,
          pass: resp && resp.status() < 500,
          detail: `status=${resp?.status()} url=${page.url()}`,
        });
      } catch (e) {
        r.checks.push({ name: `${route}_route_200_or_redirect`, pass: false, detail: String(e).slice(0, 160) });
      }
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
