// Web Summit Demo — P1.2 Pré-flight de plantas em produção.
//
// Objectivo: para cada candidato de planta, fazer login em prod, criar um projecto
// temporário com prefixo "__preflight_", fazer upload da planta, disparar leitura IA,
// medir tempo até resultado, tirar screenshot e apagar o projecto no fim.
//
// Credenciais: lidas de /app/backend/.env (TEST_PRO_EMAIL_PT, TEST_PRO_PASSWORD_PT).
// Se vazias ou "<redacted>", aborta antes de qualquer navegação.
//
// Execução:
//   cd /app/scripts/websummit_demo
//   node preflight.spec.js
//
// Artefactos:
//   /app/memory/webrsummit_demo/preflight/<slug>.png      (screenshot do resultado IA)
//   /app/memory/webrsummit_demo/preflight/results.json    (métricas por candidato)
//
// Zero commits, zero deploy, zero PII em logs. Nunca escrever credenciais em stdout.

const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

// --- Config ----------------------------------------------------------------
const BACKEND_ENV = "/app/backend/.env";
const OUT_DIR = "/app/memory/webrsummit_demo/preflight";
const BASE_URL_PT = "https://construpilot.pt";
const SLOW_MO = 150; // ms por acção, para headful visível
const CANDIDATE_TIMEOUT_MS = 10 * 60 * 1000; // 10 min por candidato
const AI_WAIT_MS = 5 * 60 * 1000; // 5 min máx para resposta IA

const CANDIDATES = [
  {
    slug: "moradia-sintetica-png",
    file: "/app/backend/tests/fixtures/plans_pro/thumbnail_moradia_sintetica.png",
    label: "Moradia sintética (PNG 1600×1600)",
  },
  {
    slug: "plan-test-pdf",
    file: "/app/backend/tests/fixtures/plan_test.pdf",
    label: "Plan test (PDF 1 página)",
  },
];

// --- Utilidades ------------------------------------------------------------
function readEnvKey(key) {
  const txt = fs.readFileSync(BACKEND_ENV, "utf8");
  for (const line of txt.split("\n")) {
    if (line.startsWith(key + "=")) {
      return line.slice(key.length + 1).trim();
    }
  }
  return null;
}

function isRedactedOrEmpty(v) {
  if (!v) return true;
  const t = v.trim().replace(/^["']|["']$/g, "");
  return t === "" || t === "<redacted>";
}

function log(msg) {
  // Logger sem valores sensíveis — nunca passar passwords/tokens aqui.
  const ts = new Date().toISOString();
  console.log(`[${ts}] ${msg}`);
}

async function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

// --- Fluxo por candidato ---------------------------------------------------
async function runCandidate(browser, cand, creds) {
  const result = {
    slug: cand.slug,
    label: cand.label,
    file: cand.file,
    file_exists: fs.existsSync(cand.file),
    file_size_bytes: fs.existsSync(cand.file) ? fs.statSync(cand.file).size : 0,
    started_at: new Date().toISOString(),
    ended_at: null,
    login_ok: false,
    project_created: false,
    project_name: `__preflight_${cand.slug}__`,
    upload_ok: false,
    ai_triggered: false,
    ai_result_received: false,
    ai_elapsed_ms: null,
    screenshot: null,
    project_deleted: false,
    errors: [],
    notes: [],
  };

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "pt-PT",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(45_000);

  try {
    // 1) Login ---------------------------------------------------------------
    log(`[${cand.slug}] login a ${BASE_URL_PT}`);
    await page.goto(`${BASE_URL_PT}/login`, { waitUntil: "domcontentloaded" });

    // Preenche com data-testids conhecidos; fallback para name/type.
    const emailSel = 'input[data-testid="login-email-input"], input[type="email"], input[name="email"]';
    const pwdSel = 'input[data-testid="login-password-input"], input[type="password"], input[name="password"]';
    const submitSel = 'button[data-testid="login-submit-btn"], button[type="submit"]';

    await page.waitForSelector(emailSel, { timeout: 20_000 });
    await page.fill(emailSel, creds.email);
    await page.fill(pwdSel, creds.password);
    await page.click(submitSel);

    // Espera redireccionamento pós-login (dashboard ou /app ou similar).
    await page.waitForURL(/\/(dashboard|app|projects|home|smart|chiffrer)/i, {
      timeout: 30_000,
    }).catch(() => {});
    const postLoginUrl = page.url();
    result.login_ok = !/\/login/.test(postLoginUrl);
    result.notes.push(`post_login_url=${postLoginUrl}`);
    if (!result.login_ok) {
      throw new Error(`Login não parece ter sucedido (url=${postLoginUrl})`);
    }

    // 2) Navegar para o leitor de plantas / takeoff -------------------------
    log(`[${cand.slug}] navegar para plan takeoff`);
    // Rotas candidatas no app (ajustar em runtime com base no observado).
    const planRoutes = ["/plan-takeoff", "/plans", "/chiffrer/plans", "/takeoff"];
    let planLoaded = false;
    for (const r of planRoutes) {
      await page.goto(`${BASE_URL_PT}${r}`, { waitUntil: "domcontentloaded" }).catch(() => {});
      // Procura dropzone ou input de upload.
      const dz = await page.$('[data-testid="plan-upload-dropzone"], [data-testid="plan-upload-input"]');
      if (dz) {
        planLoaded = true;
        result.notes.push(`plan_route=${r}`);
        break;
      }
    }
    if (!planLoaded) {
      throw new Error("Não encontrou dropzone de upload em rotas candidatas");
    }

    // 3) Upload da planta ----------------------------------------------------
    log(`[${cand.slug}] upload ${path.basename(cand.file)}`);
    const uploadInput = await page.$('input[data-testid="plan-upload-input"], input[type="file"]');
    if (!uploadInput) {
      throw new Error("Input de upload não encontrado");
    }
    await uploadInput.setInputFiles(cand.file);
    result.upload_ok = true;

    // Pode aparecer um diálogo "plan-import-dialog" pedindo nome de projecto.
    const importDialog = await page.waitForSelector('[data-testid="plan-import-dialog"]', {
      timeout: 15_000,
    }).catch(() => null);

    if (importDialog) {
      // Modo "new project" com nome preflight.
      const newBtn = await page.$('[data-testid="group-mode-new"]');
      if (newBtn) await newBtn.click().catch(() => {});
      const nameInput = await page.$('[data-testid="group-import-name"]');
      if (nameInput) {
        await nameInput.fill(result.project_name);
      }
      const confirmBtn = await page.$('[data-testid="plan-import-confirm"]');
      if (confirmBtn) {
        await confirmBtn.click();
        result.project_created = true;
      }
    } else {
      // Fluxo sem diálogo: assume que a planta foi carregada directamente.
      result.notes.push("sem_dialogo_import");
    }

    // 4) Disparar leitura IA ------------------------------------------------
    log(`[${cand.slug}] aguardar leitura IA`);
    const aiStart = Date.now();
    result.ai_triggered = true;

    // Esperar por marcador visual de "resultado IA" ou avisos.
    const resultSel = '[data-testid="ai-analysis-result"], [data-testid="plan-reading-warnings"], [data-testid="analysis-block"]';
    const aiOk = await page.waitForSelector(resultSel, {
      timeout: AI_WAIT_MS,
    }).catch(() => null);

    result.ai_elapsed_ms = Date.now() - aiStart;
    result.ai_result_received = !!aiOk;

    // 5) Screenshot ---------------------------------------------------------
    const shotPath = path.join(OUT_DIR, `${cand.slug}.png`);
    await page.screenshot({ path: shotPath, fullPage: true });
    result.screenshot = shotPath;
    log(`[${cand.slug}] screenshot em ${shotPath}`);

    // 6) Apagar projecto temporário ----------------------------------------
    log(`[${cand.slug}] a tentar apagar projecto`);
    // Caminho defensivo: dashboard projectos → procurar linha com nome preflight → apagar.
    await page.goto(`${BASE_URL_PT}/dashboard`, { waitUntil: "domcontentloaded" }).catch(() => {});
    const projectSearch = await page.$('[data-testid="dashboard-project-search"]');
    if (projectSearch) {
      await projectSearch.fill(result.project_name).catch(() => {});
      await page.waitForTimeout(1500);
    }
    // Botão apagar (depende da UI final — pode exigir click no projecto primeiro).
    const deleteBtns = await page.$$('button[data-testid*="delete-project"], button[aria-label*="apagar" i], button[aria-label*="eliminar" i]');
    if (deleteBtns.length > 0) {
      await deleteBtns[0].click().catch(() => {});
      const confirm = await page.waitForSelector('button[data-testid*="confirm"]', { timeout: 5_000 }).catch(() => null);
      if (confirm) await confirm.click().catch(() => {});
      result.project_deleted = true;
    } else {
      result.notes.push("delete_btn_nao_encontrado_apagar_manual");
    }
  } catch (err) {
    result.errors.push(String(err.message || err));
    log(`[${cand.slug}] ERRO: ${err.message}`);
    try {
      const errShot = path.join(OUT_DIR, `${cand.slug}_error.png`);
      await page.screenshot({ path: errShot, fullPage: true });
      result.notes.push(`error_screenshot=${errShot}`);
    } catch (_) {}
  } finally {
    result.ended_at = new Date().toISOString();
    await context.close();
  }

  return result;
}

// --- Main ------------------------------------------------------------------
(async () => {
  await ensureDir(OUT_DIR);

  // Verifica credenciais primeiro (fail-fast).
  const email = readEnvKey("TEST_PRO_EMAIL_PT") || readEnvKey("TEST_PRO_EMAIL");
  const password = readEnvKey("TEST_PRO_PASSWORD_PT") || readEnvKey("TEST_PRO_PASSWORD");

  if (isRedactedOrEmpty(email) || isRedactedOrEmpty(password)) {
    const msg = "ABORTAR: credenciais vazias/<redacted> em .env (TEST_PRO_EMAIL_PT/TEST_PRO_PASSWORD_PT). Preencher antes de executar.";
    log(msg);
    const out = {
      aborted: true,
      reason: "credenciais_em_falta",
      env_keys_expected: ["TEST_PRO_EMAIL_PT", "TEST_PRO_PASSWORD_PT"],
      candidates: CANDIDATES.map(c => ({ slug: c.slug, label: c.label, file: c.file })),
      timestamp: new Date().toISOString(),
    };
    fs.writeFileSync(path.join(OUT_DIR, "results.json"), JSON.stringify(out, null, 2));
    process.exit(2);
  }

  log("credenciais OK (não loggadas)");

  const browser = await chromium.launch({
    headless: true, // Modo headful opcional via xvfb-run; para pré-flight uso headless.
    slowMo: SLOW_MO,
  });

  const results = [];
  for (const cand of CANDIDATES) {
    log(`======== CANDIDATO ${cand.slug} ========`);
    const r = await Promise.race([
      runCandidate(browser, cand, { email, password }),
      new Promise(res => setTimeout(() => res({ slug: cand.slug, timeout: true, errors: ["timeout_global"] }), CANDIDATE_TIMEOUT_MS)),
    ]);
    results.push(r);
  }

  await browser.close();

  const summary = {
    aborted: false,
    base_url: BASE_URL_PT,
    env_keys_used: ["TEST_PRO_EMAIL_PT|TEST_PRO_EMAIL", "TEST_PRO_PASSWORD_PT|TEST_PRO_PASSWORD"],
    candidates: results,
    timestamp: new Date().toISOString(),
  };

  fs.writeFileSync(path.join(OUT_DIR, "results.json"), JSON.stringify(summary, null, 2));
  log(`escrito ${OUT_DIR}/results.json`);
})();
