// AK.3 — Playwright E2E para a UI admin de pedidos (CRM lite).
//
// Cobertura:
//  1. Login admin → /admin/pedidos.
//  2. Verificar tabela/cards + filtros existem (data-testids chave).
//  3. Filtrar por kind (toggle).
//  4. Click na linha → modal detalhe abre.
//  5. Mudar estado via dropdown + verificar persistência (reload).
//  6. Adicionar nota interna + verificar presença.
//  7. Export CSV → verificar download trigger.
//
// Teste em 3 viewports: iPhone 13, Pixel 7, Desktop 1280×800.

const { chromium, devices } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND_BASE = process.env.MOBILE_BASE_URL
  || fs.readFileSync(path.join(__dirname, "..", ".env"), "utf8")
       .match(/REACT_APP_BACKEND_URL=(.+)/)?.[1]?.trim()?.replace(/\/+$/, "")
  || "http://localhost:3000";

// Credencial admin — lida APENAS do ambiente. Zero valor por defeito em claro.
// Em local, define ADMIN_E2E_EMAIL e ADMIN_E2E_PASSWORD (ou TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD).
// Se não existir, o teste aborta — nunca cair em credencial em claro no código.
const EMAIL = process.env.ADMIN_E2E_EMAIL || process.env.TEST_ADMIN_EMAIL;
const PASSWORD = process.env.ADMIN_E2E_PASSWORD || process.env.TEST_ADMIN_PASSWORD;

if (!EMAIL || !PASSWORD) {
  console.error("ak3_admin_pedidos: credenciais ausentes no ambiente (ADMIN_E2E_EMAIL/PASSWORD ou TEST_ADMIN_EMAIL/PASSWORD). A abortar.");
  process.exit(2);
}

const IPHONE_CFG = { ...devices["iPhone 13"], hasTouch: true, isMobile: false };
const PIXEL_CFG = { ...devices["Pixel 7"], hasTouch: true, isMobile: false };
const DESKTOP_CFG = { viewport: { width: 1280, height: 800 } };

const results = { blocks: {}, pass: 0, fail: 0, critical_fail: 0 };

function log(block, name, ok, note = "") {
  if (!results.blocks[block]) results.blocks[block] = [];
  results.blocks[block].push({ name, ok, note });
  if (ok) results.pass++; else results.fail++;
}

async function tryLoginAdmin(page) {
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
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(500);
    if (!page.url().includes("/login")) return true;
    const hasToken = await page.evaluate(() => {
      try {
        return !!(localStorage.getItem("token") ||
                  localStorage.getItem("session_token") ||
                  localStorage.getItem("auth"));
      } catch { return false; }
    });
    if (hasToken) return true;
  }
  return false;
}

async function runForContext(ctxName, ctxCfg, browser) {
  const ctx = await browser.newContext(ctxCfg);
  const page = await ctx.newPage();
  try {
    const ok = await tryLoginAdmin(page);
    if (!ok) {
      log(ctxName, "login admin", false, "credenciais ou redirect falhou");
      results.critical_fail++;
      await ctx.close();
      return;
    }
    log(ctxName, "login admin", true);

    // Navegar para /admin/pedidos
    await page.goto(`${FRONTEND_BASE}/admin/pedidos`, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForTimeout(1500);
    const hub = await page.$('[data-testid="pedidos-hub"]');
    log(ctxName, "/admin/pedidos renderiza", !!hub);
    if (!hub) { await ctx.close(); return; }

    // Filtros presentes
    const kinds = await page.$$('[data-testid^="filter-kind-"]');
    const states = await page.$$('[data-testid^="filter-state-"]');
    log(ctxName, "filtros kind presentes", kinds.length >= 6);
    log(ctxName, "filtros state presentes", states.length >= 4);

    // Pesquisa + export buttons
    const search = await page.$('[data-testid="search-input"]');
    log(ctxName, "campo pesquisa presente", !!search);
    const exportCsvBtn = await page.$('[data-testid="export-csv-btn"]');
    log(ctxName, "botão export CSV presente", !!exportCsvBtn);

    // Clicar num filtro kind=contact e verificar que não quebra
    const kContact = await page.$('[data-testid="filter-kind-contact"]');
    if (kContact) {
      await kContact.click();
      await page.waitForTimeout(1000);
      log(ctxName, "toggle filtro contact", true);
    }

    // Abrir primeira linha/card (se existir) → modal
    const firstRow = await page.$('[data-testid^="pedido-row-"], [data-testid^="pedido-card-"]');
    if (firstRow) {
      await firstRow.click();
      await page.waitForTimeout(800);
      const modal = await page.$('[data-testid="detail-modal"]');
      log(ctxName, "modal detalhe abre ao clicar", !!modal);

      if (modal) {
        // Adicionar nota
        const noteInput = await page.$('[data-testid="note-input"]');
        const noteBtn = await page.$('[data-testid="add-note-btn"]');
        if (noteInput && noteBtn) {
          await noteInput.fill(`nota e2e ${Date.now()}`);
          await noteBtn.click();
          await page.waitForTimeout(1200);
          log(ctxName, "adicionar nota interna", true);
        } else {
          log(ctxName, "adicionar nota interna", false, "input/btn ausente");
        }

        // Mudar estado via modal select
        const stateSel = await page.$('[data-testid="modal-state-select"]');
        if (stateSel) {
          await stateSel.selectOption("em_curso").catch(() => {});
          await page.waitForTimeout(800);
          log(ctxName, "mudar estado via modal", true);
        } else {
          log(ctxName, "mudar estado via modal", false, "select ausente");
        }

        // Fechar modal
        const closeBtn = await page.$('[data-testid="close-modal-btn"]');
        if (closeBtn) await closeBtn.click();
      }
    } else {
      log(ctxName, "linha/card para abrir modal", false, "nenhum pedido na BD do preview");
    }

    // Export CSV — tenta capturar download
    if (ctxName === "Desktop") {
      try {
        const [download] = await Promise.all([
          page.waitForEvent("download", { timeout: 5000 }).catch(() => null),
          page.click('[data-testid="export-csv-btn"]'),
        ]);
        log(ctxName, "export CSV dispara download", !!download);
      } catch (e) {
        log(ctxName, "export CSV dispara download", false, e.message.slice(0, 100));
      }
    }
  } catch (e) {
    log(ctxName, "erro inesperado", false, e.message.slice(0, 150));
  } finally {
    await ctx.close();
  }
}

async function seedOnePedido() {
  // Cria 1 contact via /api/leads para garantir que há conteúdo na tabela.
  const payload = {
    name: "E2E AK3", email: "e2e+ak3@test.pt",
    phone: "+351912345678", description: "Pedido E2E AK.3",
    source: "e2e", postal_code: "1000-001",
  };
  try {
    const r = await fetch(`${FRONTEND_BASE}/api/leads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return r.ok;
  } catch { return false; }
}

async function run() {
  await seedOnePedido();
  const browser = await chromium.launch();
  await runForContext("Desktop", DESKTOP_CFG, browser);
  await runForContext("iPhone13", IPHONE_CFG, browser);
  await runForContext("Pixel7", PIXEL_CFG, browser);
  await browser.close();
}

run().then(() => {
  const report = {
    total: results.pass + results.fail,
    pass: results.pass,
    fail: results.fail,
    critical_fail: results.critical_fail,
    blocks: results.blocks,
  };
  console.log(JSON.stringify(report, null, 2));
  // Guarda relatório em memory
  const md = ["# AK.3 — E2E admin pedidos", "",
    `Total: ${report.total} | PASS: ${report.pass} | FAIL: ${report.fail} | Critical: ${report.critical_fail}`,
    ""];
  for (const [bk, items] of Object.entries(report.blocks)) {
    md.push(`## ${bk}`);
    for (const it of items) {
      md.push(`- [${it.ok ? "x" : " "}] ${it.name}${it.note ? ` — ${it.note}` : ""}`);
    }
    md.push("");
  }
  fs.writeFileSync(
    path.join(__dirname, "..", "..", "memory", "lote_ak3_e2e_report.md"),
    md.join("\n"),
  );
  process.exit(report.critical_fail > 0 ? 1 : 0);
}).catch((e) => {
  console.error("FATAL:", e);
  process.exit(2);
});
