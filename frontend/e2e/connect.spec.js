// E2E do Discovery Engine (/connect) contra o servidor local backend/tests/connect_e2e_server.py.
// Executar: npx playwright test -c playwright.connect.config.cjs
const { test, expect } = require("playwright/test");
const fs = require("fs");
const path = require("path");

const AXE = fs.readFileSync(path.join(__dirname, "../node_modules/axe-core/axe.min.js"), "utf8");

async function axe(page, label) {
  await page.waitForTimeout(600); // deixa terminar as transições (opacidade) antes de medir o contraste
  await page.addScriptTag({ content: AXE });
  const res = await page.evaluate(async () => window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] }));
  const bad = res.violations.filter((v) => ["serious", "critical"].includes(v.impact));
  if (bad.length) console.log(label, JSON.stringify(bad.map((v) => ({ id: v.id, n: v.nodes.length, t: v.nodes.slice(0, 2).map((x) => x.target) })), null, 1));
  expect(bad, `${label}: violações graves de acessibilidade`).toEqual([]);
}

async function pick(page, testId) {
  await page.getByTestId(testId).click();
}
async function next(page) {
  await page.getByTestId("wizard-next").click();
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => { try { localStorage.setItem("cp_cookie_consent", "refused"); } catch (e) { /* */ } });
});

test("Teste 1 — Pintor: diagnóstico → resultado → demo real → resumo por e-mail → CRM", async ({ page }) => {
  await page.goto("/connect?source=websummit2026&utm_campaign=stand_client");
  await expect(page.getByTestId("connect-title")).toHaveText("O que pode a ConstruPilot resolver por si?");
  await axe(page, "home");
  await pick(page, "connect-profile-client");
  await expect(page).toHaveURL(/\/connect\/client\?source=websummit2026/);
  await pick(page, "q-activity-painting"); await next(page);
  await pick(page, "q-volume-q16_40"); await next(page);
  await pick(page, "q-pains-p_quote_slow"); await pick(page, "q-pains-p_quantities"); await next(page);
  await axe(page, "wizard");
  await pick(page, "q-deep-t_surfaces-interior_walls"); await next(page);
  await pick(page, "q-deep-tools-excel"); await next(page);
  await pick(page, "q-urgency-d30"); await next(page);
  await pick(page, "q-decision-decide"); await next(page);
  await expect(page.getByTestId("client-result")).toBeVisible();
  await expect(page.getByTestId("challenge-line")).toContainText("preparação lenta e repetitiva de orçamentos");
  await expect(page.getByTestId("process-compare")).toContainText("Passar para Excel");
  const demo = page.getByTestId("demo-player-demo_painting");
  await expect(demo).toBeVisible();
  await expect(demo.getByTestId("demo-kind")).toContainText("Demonstração real");
  await axe(page, "result");
  for (let i = 0; i < 5; i++) await demo.getByTestId("demo-next").click();
  await expect(demo.getByTestId("demo-done")).toBeVisible();
  // calculadora: 25 orçamentos (pré-preenchido do diagnóstico) × 2 h = 50 h; × 25 € = 1 250 €
  await expect(page.getByTestId("calc-quotes")).toHaveValue("25");
  await expect(page.getByTestId("calc-math")).toContainText("—");
  await page.getByTestId("calc-hours").fill("2");
  await page.getByTestId("calc-rate").fill("25");
  await expect(page.getByTestId("calc-math")).toContainText("50 horas por mês");
  await expect(page.getByTestId("calc-math")).toContainText("1250");
  await pick(page, "ns-report");
  await page.getByTestId("f-name").fill("Paulo Pintor");
  await page.getByTestId("f-company").fill("Pinturas Paulo");
  await page.getByTestId("f-email").fill("paulo@pinturas.pt");
  await expect(page.getByTestId("f-marketing")).not.toBeChecked();
  await page.getByTestId("f-privacy").check();
  await page.getByTestId("contact-submit").click();
  await expect(page.getByTestId("contact-sent")).toBeVisible();
  const leads = await (await page.request.get("/api/connect/admin/leads?q=paulo")).json();
  expect(leads.total).toBe(1);
  expect(leads.items[0].source).toBe("websummit2026");
  expect(leads.items[0].pains).toEqual(["p_quote_slow", "p_quantities"]);
  const sent = await (await page.request.get("/api/__e2e/sent")).json();
  expect(sent.some((m) => m.to === "paulo@pinturas.pt" && /diagnóstico/i.test(m.subject))).toBeTruthy();
});

test("Teste 2 — Arquiteto (telemóvel): medições → demo de medição; calibração errada é sinalizada", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/connect/client");
  await pick(page, "q-activity-architect"); await next(page);
  await pick(page, "q-volume-p3_5"); await next(page);
  await pick(page, "q-pains-p_measure"); await pick(page, "q-pains-p_docs_scattered"); await next(page);
  await pick(page, "q-deep-a_formats-pdf"); await next(page);
  await pick(page, "q-deep-a_main_issue-handover"); await next(page);
  await pick(page, "q-urgency-m3"); await next(page);
  await pick(page, "q-decision-evaluate"); await next(page);
  const demo = page.getByTestId("demo-player-demo_takeoff");
  await expect(demo).toBeVisible();
  const noHScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  expect(noHScroll).toBeTruthy();
  await demo.getByTestId("demo-next").click(); await demo.getByTestId("demo-next").click();
  await demo.getByTestId("ctl-calibration").fill("5.4");
  for (let i = 0; i < 3; i++) await demo.getByTestId("demo-next").click();
  await expect(demo.getByTestId("calibration-check")).toContainText("Recalibração recomendada");
});

test("Teste 3 — Construtora: obras, margens e faturação; margem recalculada pelo motor", async ({ page }) => {
  await page.goto("/connect/client");
  await pick(page, "q-activity-construction_company"); await next(page);
  await pick(page, "q-volume-q6_15"); await next(page);
  for (const p of ["p_multi_sites", "p_margins", "p_billing"]) await pick(page, `q-pains-${p}`);
  await next(page);
  await pick(page, "q-deep-d_sites-s6_15"); await next(page);
  await pick(page, "q-deep-d_late_info-costs"); await next(page);
  await pick(page, "q-urgency-immediate"); await next(page);
  await pick(page, "q-decision-decide"); await next(page);
  await expect(page.getByTestId("demo-player-demo_documents")).toBeVisible();
  await expect(page.getByTestId("demo-player-demo_documents").getByTestId("demo-kind")).toContainText("Reprodução guiada");
  for (let i = 0; i < 4; i++) await page.getByTestId("demo-next").click();
  await page.getByTestId("demo-switch-demo_margin").click();
  const demo = page.getByTestId("demo-player-demo_margin");
  for (let i = 0; i < 3; i++) await demo.getByTestId("demo-next").click();
  const before = await demo.getByTestId("margin-total").innerText();
  await demo.getByTestId("ctl-cost").fill("40");
  await expect(demo.getByTestId("margin-total")).not.toHaveText(before, { timeout: 5000 });
});

test("Teste 4 — Investidor VC ConTech: só informação pública + pedido de reunião", async ({ page }) => {
  await page.goto("/connect/investor");
  await pick(page, "q-investor_type-vc");
  await page.getByTestId("q-organization").fill("Lisbon Ventures");
  await pick(page, "q-sectors-contech");
  await pick(page, "q-stages-pre_seed");
  await pick(page, "q-availability-this_week");
  await page.getByTestId("investor-submit").click();
  await expect(page.getByTestId("investor-result")).toBeVisible();
  await expect(page.getByTestId("traction-source")).toContainText("2026-11-06");
  await expect(page.locator("body")).not.toContainText(/cap table/i);
  await page.getByTestId("see-in-action").click();
  await expect(page.getByTestId("demo-player-demo_takeoff")).toBeVisible();
  await page.getByTestId("f-name").fill("Inês Investidora");
  await page.getByTestId("f-email").fill("ines@lv.vc");
  await page.getByTestId("f-privacy").check();
  await page.getByTestId("contact-submit").click();
  await expect(page.getByTestId("contact-sent")).toBeVisible();
  const leads = await (await page.request.get("/api/connect/admin/leads?profile=investor")).json();
  expect(leads.items[0].stage).toBe("meeting_requested");
});

test("Teste 5 — outro visitante não abre o resultado privado", async ({ page, browser }) => {
  await page.goto("/connect/client");
  await pick(page, "q-activity-renovation"); await next(page);
  await pick(page, "q-volume-q0_5"); await next(page);
  await pick(page, "q-pains-p_errors"); await next(page);
  await next(page); await next(page);
  await pick(page, "q-urgency-m3"); await next(page);
  await pick(page, "q-decision-decide"); await next(page);
  await expect(page.getByTestId("client-result")).toBeVisible();
  const url = page.url();
  const other = await browser.newContext();
  const p2 = await other.newPage();
  await p2.goto(url);
  await expect(p2.getByTestId("result-denied")).toBeVisible();
  const sid = url.match(/result\/(cs_[^?]+)/)[1];
  const r = await p2.request.get(`/api/connect/sessions/${sid}`);
  expect(r.status()).toBe(403);
  await other.close();
});

test("Idiomas: EN e FR sem texto português misturado", async ({ page }) => {
  await page.goto("/connect?lang=en");
  await expect(page.getByTestId("connect-title")).toHaveText("What can ConstruPilot solve for you?");
  await pick(page, "connect-profile-client");
  await expect(page.getByText("What best describes your activity?")).toBeVisible();
  await page.getByTestId("connect-lang-fr").click();
  await expect(page.getByText("Qu'est-ce qui décrit le mieux votre activité ?")).toBeVisible();
  const body = await page.locator("main").innerText();
  for (const pt of ["Continuar", "Voltar", "orçamentos", "Passo "]) expect(body).not.toContain(pt);
});

test("Stand offline: diagnóstico rápido sem rede, demo pré-calculada e pedido em fila", async ({ page }) => {
  await page.route("**/api/connect/**", (route) => route.abort("internetdisconnected"));
  await page.goto("/connect/stand");
  await expect(page.getByTestId("stand-qr-client")).toBeVisible();
  await pick(page, "stand-quick-client");
  await pick(page, "q-pains-p_quote_slow"); await next(page);
  await pick(page, "q-activity-general_contractor"); await next(page);
  await pick(page, "q-volume-q6_15"); await next(page);
  await pick(page, "q-urgency-d30"); await next(page);
  await expect(page).toHaveURL(/result\/local/);
  const demo = page.getByTestId("demo-player-demo_quote");
  await expect(demo).toBeVisible();
  await demo.getByTestId("demo-next").click();
  await expect(demo.getByTestId("demo-offline")).toBeVisible();
  await pick(page, "ns-individual_demo");
  await page.getByTestId("f-name").fill("Visitante Stand");
  await page.getByTestId("f-email").fill("visitante@obra.pt");
  await page.getByTestId("f-privacy").check();
  await page.getByTestId("contact-submit").click();
  await expect(page.getByTestId("contact-sent")).toContainText("guardado neste dispositivo");
  // rede volta → fila enviada
  await page.unroute("**/api/connect/**");
  await page.goto("/connect/stand");
  await expect.poll(async () => (await (await page.request.get("/api/connect/admin/leads?q=visitante")).json()).total, { timeout: 10000 }).toBe(1);
});

test("Commercial Hub: lista, filtro, detalhe com justificação e mudança de etapa", async ({ page }) => {
  await page.goto("/admin/connect");
  await expect(page.getByTestId("admin-connect")).toBeVisible();
  await expect(page.getByTestId("hub-table")).toBeVisible();
  await page.getByTestId("hub-search").fill("paulo");
  const row = page.locator("[data-testid^=hub-row-]").first();
  await expect(row).toContainText("Paulo Pintor");
  await row.click();
  await expect(page.getByTestId("hub-justification")).toContainText("é decisor");
  await page.getByTestId("hub-stage").selectOption("demo_done");
  await page.getByTestId("hub-note").fill("Demonstração feita no stand");
  await page.getByRole("button", { name: "Guardar" }).last().click();
  await expect(page.getByTestId("hub-drawer")).toContainText("Demonstração feita no stand");
  await page.keyboard.press("Escape");
  await page.getByTestId("hub-tab-dashboard").click();
  await expect(page.getByTestId("hub-dashboard")).toContainText("Diagnósticos iniciados");
});

test("Movimento reduzido: demo funciona sem animações", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/connect/demo/demo_takeoff");
  const demo = page.getByTestId("demo-player-demo_takeoff");
  await demo.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(demo.getByTestId("ctl-calibration")).toBeVisible();
  await axe(page, "demo");
});

test("Demo pública e QR Codes servidos", async ({ page }) => {
  await page.goto("/connect/demo/demo_margin?lang=fr");
  await expect(page.getByTestId("demo-player-demo_margin")).toContainText("Coûts, marge et coefficient");
  for (const p of ["client", "investor", "partner"]) {
    const r = await page.request.get(`/connect/qr-${p}.svg`);
    expect(r.status()).toBe(200);
    expect(await r.text()).toContain(`connect/${p}?source=websummit2026`.replace("?", "?").slice(0, 10));
  }
});
