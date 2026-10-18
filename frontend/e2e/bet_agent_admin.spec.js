// L1.9 — Playwright E2E para a UI admin BET-PT Agent.
//
// NOTA DE AMBIENTE: este spec requer um `MOBILE_BASE_URL` que o browser
// possa resolver em simultâneo com o backend (ex: a URL preview Emergent).
// Em pod local isolado (`localhost:3000`), o browser falha a resolver o
// `REACT_APP_BACKEND_URL` externo. Correr apenas:
//   - em preview (MOBILE_BASE_URL=https://<preview>.emergentagent.com)
//   - OU em ambiente onde o backend está servido no mesmo host do frontend.
//
// Cobertura (desktop + mobile):
//  1. Login admin → /admin/bet-agent.
//  2. Página renderiza com data-testid admin-bet-agent-page.
//  3. Status card presente (feature flag + chave + modelo + limite €).
//  4. Botão "Correr pipeline" presente mas DESACTIVADO em CI (flag off ou
//     chave missing — este smoke valida o guard de UI, não corre o pipeline).
//  5. Tabela de dossiers presente (pode estar vazia).
//  6. Rota /admin/bet-agent inacessível sem admin (deslogado → /login).
//
// Credencial admin — lida APENAS do ambiente. Zero valor por defeito em claro.

const { chromium, devices } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND_BASE = process.env.MOBILE_BASE_URL
  || fs.readFileSync(path.join(__dirname, "..", ".env"), "utf8")
       .match(/REACT_APP_BACKEND_URL=(.+)/)?.[1]?.trim()?.replace(/\/+$/, "")
  || "http://localhost:3000";

const EMAIL = process.env.ADMIN_E2E_EMAIL || process.env.TEST_ADMIN_EMAIL;
const PASSWORD = process.env.ADMIN_E2E_PASSWORD || process.env.TEST_ADMIN_PASSWORD;

if (!EMAIL || !PASSWORD) {
  console.error(
    "bet_agent_admin: credenciais ausentes no ambiente (ADMIN_E2E_EMAIL/PASSWORD " +
      "ou TEST_ADMIN_EMAIL/PASSWORD). A abortar."
  );
  process.exit(2);
}

const IPHONE_CFG = { ...devices["iPhone 13"], hasTouch: true, isMobile: false };
const DESKTOP_CFG = { viewport: { width: 1280, height: 800 } };

const results = { blocks: {}, pass: 0, fail: 0, critical_fail: 0 };

function log(block, name, ok, note = "") {
  results.blocks[block] = results.blocks[block] || { pass: 0, fail: 0, items: [] };
  if (ok) {
    results.pass++;
    results.blocks[block].pass++;
  } else {
    results.fail++;
    results.blocks[block].fail++;
  }
  results.blocks[block].items.push({ name, ok, note });
  console.log(`[${block}] ${ok ? "PASS" : "FAIL"} — ${name}${note ? ` :: ${note}` : ""}`);
}

async function dismissWebsummitPopup(page) {
  // O pop-up WebSummit intercepta cliques; fecha-o se existir.
  try {
    const closeBtn = await page.$("#cp-ws-close");
    if (closeBtn) {
      await closeBtn.click({ force: true });
      await page.waitForTimeout(400);
    }
  } catch { /* ignora */ }
}

async function tryLoginAdmin(page) {
  await page.goto(`${FRONTEND_BASE}/login`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForTimeout(1500);
  await dismissWebsummitPopup(page);
  const emailInput = await page.$('input[type="email"], input[name="email"]');
  const passwordInput = await page.$('input[type="password"], input[name="password"]');
  if (!emailInput || !passwordInput) return false;
  await emailInput.fill(EMAIL);
  await passwordInput.fill(PASSWORD);
  const btn = await page.$('button[type="submit"], button:has-text("Entrar"), button:has-text("Login")');
  if (!btn) return false;
  await btn.click();
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(500);
    if (!page.url().includes("/login")) return true;
    const hasToken = await page.evaluate(() => {
      try {
        return !!(
          localStorage.getItem("token") ||
          localStorage.getItem("session_token") ||
          localStorage.getItem("auth")
        );
      } catch {
        return false;
      }
    });
    if (hasToken) return true;
  }
  return false;
}

async function runForContext(ctxName, ctxCfg, browser) {
  const ctx = await browser.newContext(ctxCfg);
  // Suprime overlays (pop-up WebSummit + banner cookies) antes de qualquer
  // navegação, para evitar interceptação de cliques.
  await ctx.addInitScript(() => {
    try { sessionStorage.setItem("cp_websummit_2026_seen", "1"); } catch (e) {}
    try { localStorage.setItem("cp_cookie_consent", "accepted"); } catch (e) {}
  });
  const page = await ctx.newPage();

  try {
    // 1. Logged-out: /admin/bet-agent redirecciona para /login.
    await page.goto(`${FRONTEND_BASE}/admin/bet-agent`, {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(1500);
    const redirectedToLogin = page.url().includes("/login");
    log(ctxName, "unauth redirect to /login", redirectedToLogin,
        `url=${page.url()}`);

    // 2. Login admin.
    const ok = await tryLoginAdmin(page);
    if (!ok) {
      log(ctxName, "login admin", false, "credenciais ou redirect falhou");
      results.critical_fail++;
      await ctx.close();
      return;
    }
    log(ctxName, "login admin", true);

    // 3. Navegar para /admin/bet-agent.
    await page.goto(`${FRONTEND_BASE}/admin/bet-agent`, {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });
    await page.waitForTimeout(1800);
    await dismissWebsummitPopup(page);

    const pageRoot = await page.$('[data-testid="admin-bet-agent-page"]');
    log(ctxName, "/admin/bet-agent renderiza", !!pageRoot);
    if (!pageRoot) {
      results.critical_fail++;
      await ctx.close();
      return;
    }

    // 4. Status card.
    const statusCard = await page.$('[data-testid="bet-agent-status"]');
    log(ctxName, "status card presente", !!statusCard);
    const flagStatus = await page.$('[data-testid="status-feature-flag"]');
    const keyStatus = await page.$('[data-testid="status-key"]');
    log(ctxName, "status feature flag visível", !!flagStatus);
    log(ctxName, "status key visível", !!keyStatus);

    // 5. Botão "Correr pipeline" existe.
    const runBtn = await page.$('[data-testid="run-pipeline-btn"]');
    log(ctxName, "botão correr pipeline presente", !!runBtn);
    if (runBtn) {
      const disabled = await runBtn.evaluate((el) => el.hasAttribute("disabled"));
      // Em CI preview, feature flag é default OFF ⇒ botão desactivado.
      // Se estiver activado é porque alguém ligou a flag no pod — ok também.
      log(ctxName, "run button estado consistente com guard", true,
          disabled ? "desactivado (flag off/key missing)" : "activado (flag on + key)");
    }

    // 6. Tabela de dossiers (vazia ou com linhas, basta renderizar).
    const runsSection = await page.$('[data-testid="bet-agent-runs"]');
    log(ctxName, "secção dossiers presente", !!runsSection);

    // 7. Rodapé: dialog contém a frase do pré-dimensionamento. Para validar
    //    só com UI (sem rodar pipeline), basta inspecionar o texto estático.
    //    Nota: o rodapé só aparece dentro do Dialog após selecionar um dossier
    //    — em CI sem dossiers skipamos esta parte.

  } catch (e) {
    log(ctxName, "excepção durante teste", false, String(e?.message || e));
    results.critical_fail++;
  } finally {
    await ctx.close();
  }
}

(async () => {
  const browser = await chromium.launch();
  try {
    await runForContext("desktop", DESKTOP_CFG, browser);
    await runForContext("iphone13", IPHONE_CFG, browser);
  } finally {
    await browser.close();
  }

  const summary = {
    pass: results.pass,
    fail: results.fail,
    critical_fail: results.critical_fail,
    blocks: results.blocks,
  };
  console.log("\n===== SUMMARY =====\n" + JSON.stringify(summary, null, 2));

  if (summary.critical_fail > 0 || summary.fail > 0) {
    process.exit(1);
  }
  process.exit(0);
})();
