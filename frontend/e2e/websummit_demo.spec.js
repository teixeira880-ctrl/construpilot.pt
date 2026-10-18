// E2E Web Summit demo — standalone Playwright script (sem test runner).
//
// Testa:
//  1. /demo/entrar renderiza
//  2. /login mostra botão demo se configurado
//  3. /api/auth/demo-login response não contém password
//  4. Cookie session_token é HttpOnly + SameSite=Lax
//  5. Rate limit activa ao 11º pedido
//  6. Guard middleware bloqueia envios em modo demo
//  7. Guard middleware bloqueia change-password em modo demo
//
// Uso:
//   BASE_URL=http://localhost:3000 API_URL=http://localhost:8001 \
//     node /app/frontend/e2e/websummit_demo.spec.js
//
// Zero credenciais hardcoded. Se segredos ausentes, testes de login fail-closed
// são validados; os de guard são saltados graciosamente.
const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";
const API_URL = process.env.API_URL || "http://localhost:8001";

const results = [];
function log(name, ok, detail) {
  results.push({ name, ok, detail: detail || "" });
  const s = ok ? "✓" : "✗";
  console.log(`${s} ${name}${detail ? "  -- " + detail : ""}`);
}

async function demoStatus(reqCtx) {
  const r = await reqCtx.get(`${API_URL}/api/auth/demo-status`);
  if (!r.ok()) return { pro: false, particular: false };
  return await r.json();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const reqCtx = context.request;

  try {
    const status = await demoStatus(reqCtx);
    console.log(`[info] demo status: ${JSON.stringify(status)}`);

    // 1. /demo/entrar renderiza
    try {
      const page = await context.newPage();
      await page.goto(`${BASE_URL}/demo/entrar`, { waitUntil: "domcontentloaded" });
      await page.waitForSelector('[data-testid="demo-page"]', { timeout: 10000 });
      await page.waitForSelector('[data-testid="demo-notice"]', { timeout: 10000 });
      log("test_1_demo_entrar_renders", true);
      await page.close();
    } catch (e) {
      log("test_1_demo_entrar_renders", false, e.message);
    }

    // 2. /login mostra bloco demo quando configurado
    // NOTA: em ambiente local o frontend chama REACT_APP_BACKEND_URL (preview externo),
    // não o localhost:8001. Para validar o render real da UI com segredos, precisa de
    // ser executado em staging/produção depois do deploy. Localmente o teste verifica
    // apenas se o código do bundle contém o testid (prova que a feature foi incluída).
    try {
      const bundleResp = await reqCtx.get(`${BASE_URL}/static/js/bundle.js`);
      const bundleText = await bundleResp.text().catch(() => "");
      const hasTestId = bundleText.includes("demo-login-block") && bundleText.includes("demo-login-pro-btn");
      log("test_2_login_demo_block_in_bundle", hasTestId, hasTestId ? "testid presente no bundle" : "testid AUSENTE no bundle");
    } catch (e) {
      log("test_2_login_demo_block_in_bundle", false, e.message);
    }

    // 3. /api/auth/demo-login não vaza password
    if (status.pro) {
      try {
        const r = await reqCtx.post(`${API_URL}/api/auth/demo-login`, {
          data: { kind: "pro" },
        });
        const text = await r.text();
        const body = JSON.parse(text);
        const ok =
          r.status() === 200 &&
          !text.toLowerCase().includes("password_hash") &&
          body.user?.password === undefined &&
          body.user?.password_hash === undefined &&
          body.user?.is_demo === true;
        log("test_3_response_no_password_leak", ok, `status=${r.status()}`);
      } catch (e) {
        log("test_3_response_no_password_leak", false, e.message);
      }
    } else {
      log("test_3_response_no_password_leak_SKIPPED", true, "pro not configured");
    }

    // 4. Cookie HttpOnly + SameSite=Lax
    if (status.pro) {
      try {
        const r = await reqCtx.post(`${API_URL}/api/auth/demo-login`, {
          data: { kind: "pro" },
        });
        const sc = (r.headers()["set-cookie"] || "").toLowerCase();
        const ok = sc.includes("httponly") && sc.includes("samesite=lax");
        log("test_4_cookie_httponly_samesite", ok, `header=${sc.slice(0, 100)}`);
      } catch (e) {
        log("test_4_cookie_httponly_samesite", false, e.message);
      }
    } else {
      log("test_4_cookie_httponly_SKIPPED", true, "pro not configured");
    }

    // 5. Rate limit (12 pedidos → algum 429) — EXECUTADO POR ÚLTIMO porque esgota a quota
    // Movido para o fim após testes 6/7/8.

    // 6. Guard: envio de documento → 403 demo_blocked
    if (status.pro) {
      try {
        const fresh = await browser.newContext();
        const login = await fresh.request.post(`${API_URL}/api/auth/demo-login`, {
          data: { kind: "pro" },
        });
        // Cookie `secure=true` não é enviado em HTTP local pelo Playwright,
        // extraímos manualmente e injectamos via header `Cookie`.
        const setCookie = login.headers()["set-cookie"] || "";
        const match = setCookie.match(/session_token=([^;]+)/);
        const sessionCookie = match ? `session_token=${match[1]}` : "";
        const r = await fresh.request.post(`${API_URL}/api/documents/fake123/send`, {
          data: {},
          headers: { Cookie: sessionCookie },
        });
        const body = await r.json().catch(() => ({}));
        const ok =
          r.status() === 403 &&
          body.error === "demo_blocked" &&
          body.action === "send_document";
        log("test_6_guard_blocks_send_document", ok, `status=${r.status()}`);
        await fresh.close();
      } catch (e) {
        log("test_6_guard_blocks_send_document", false, e.message);
      }
    } else {
      log("test_6_guard_blocks_send_document_SKIPPED", true, "pro not configured");
    }

    // 7. Guard: change-password → 403
    if (status.pro) {
      try {
        const fresh = await browser.newContext();
        const login = await fresh.request.post(`${API_URL}/api/auth/demo-login`, {
          data: { kind: "pro" },
        });
        const setCookie = login.headers()["set-cookie"] || "";
        const match = setCookie.match(/session_token=([^;]+)/);
        const sessionCookie = match ? `session_token=${match[1]}` : "";
        const r = await fresh.request.post(`${API_URL}/api/auth/change-password`, {
          data: { current_password: "x", new_password: "y" },
          headers: { Cookie: sessionCookie },
        });
        const body = await r.json().catch(() => ({}));
        const ok =
          r.status() === 403 &&
          body.error === "demo_blocked" &&
          body.action === "change_password";
        log("test_7_guard_blocks_change_password", ok, `status=${r.status()}`);
        await fresh.close();
      } catch (e) {
        log("test_7_guard_blocks_change_password", false, e.message);
      }
    } else {
      log("test_7_guard_blocks_change_password_SKIPPED", true, "pro not configured");
    }

    // 8. 503 demo_unavailable quando kind inválido (pydantic 422) ou segredo em falta
    try {
      const r = await reqCtx.post(`${API_URL}/api/auth/demo-login`, {
        data: { kind: "nonexistent_kind" },
      });
      const ok = r.status() === 422 || r.status() === 503;
      log("test_8_invalid_kind_422_or_503", ok, `status=${r.status()}`);
    } catch (e) {
      log("test_8_invalid_kind_422_or_503", false, e.message);
    }

    // 5. Rate limit (12 pedidos → algum 429) — por último porque esgota quota
    try {
      const freshCtx = await browser.newContext();
      const results5 = [];
      for (let i = 0; i < 12; i++) {
        const r = await freshCtx.request.post(`${API_URL}/api/auth/demo-login`, {
          data: { kind: "pro" },
        });
        results5.push(r.status());
      }
      const has429 = results5.some((s) => s === 429);
      log("test_5_rate_limit_triggers_429", has429, `statuses=${results5.join(",")}`);
      await freshCtx.close();
    } catch (e) {
      log("test_5_rate_limit_triggers_429", false, e.message);
    }

  } finally {
    await browser.close();
  }

  const total = results.length;
  const passed = results.filter((r) => r.ok).length;
  const failed = total - passed;
  console.log(`\n==== Summary: ${passed}/${total} passed, ${failed} failed ====`);
  if (failed) process.exit(1);
})();
