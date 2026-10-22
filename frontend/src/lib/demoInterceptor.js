/**
 * demoInterceptor.js — LOTE 2b WebSummit
 *
 * Intercepta chamadas axios para `/api/*` quando o modo demo offline está activo
 * (`localStorage.is_demo === "true"`), resolvendo-as a partir de fixtures JSON
 * geradas pelos motores backend reais (`src/fixtures/demo/*.json`) e de uma
 * store IndexedDB para mutações (POST/PUT/PATCH/DELETE).
 *
 * Regras duras:
 * - Contas normais (sem flag) → request passa pela rede INTACTO.
 * - Sem toque em `api.defaults.baseURL`, só substitui o `adapter`.
 * - Zero dado real; zero rede quando a flag está activa.
 *
 * API pública:
 *   enableDemoMode({ kind: "pro" | "particular" })
 *   disableDemoMode()
 *   isDemoActive(): boolean
 *   installDemoInterceptor(api)
 *   resetDemoStore(): Promise<void>
 */

import users from "@/fixtures/demo/users.json";
import projects from "@/fixtures/demo/projects.json";
import brandingFx from "@/fixtures/demo/demo_branding.json";
import assistantDocsFx from "@/fixtures/demo/assistant_docs.json";
import plansFx from "@/fixtures/demo/plans.json";
import quotesFx from "@/fixtures/demo/quotes.json";
import assistantResponses from "@/fixtures/demo/assistant_responses.json";

const LS_FLAG = "is_demo";
const LS_KIND = "demo_kind";
const IDB_NAME = "construpilot_demo_v1";
const IDB_STORE = "mutations";

// -------------------- flag helpers --------------------

export function isDemoActive() {
  try { return typeof localStorage !== "undefined" && localStorage.getItem(LS_FLAG) === "true"; }
  catch { return false; }
}

export function enableDemoMode({ kind = "pro" } = {}) {
  try {
    localStorage.setItem(LS_FLAG, "true");
    localStorage.setItem(LS_KIND, kind === "particular" ? "particular" : "pro");
  } catch { /* noop */ }
}

export function disableDemoMode() {
  try {
    localStorage.removeItem(LS_FLAG);
    localStorage.removeItem(LS_KIND);
    localStorage.removeItem("construpilot_session");
  } catch { /* noop */ }
}

function currentKind() {
  try { return localStorage.getItem(LS_KIND) === "particular" ? "particular" : "pro"; }
  catch { return "pro"; }
}

function currentUser() {
  const kind = currentKind();
  return users.find((u) => u.demo_kind === kind) || users[0];
}

// -------------------- IndexedDB mini store --------------------

function _openIdb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(IDB_STORE)) db.createObjectStore(IDB_STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbGet(key) {
  if (typeof indexedDB === "undefined") return undefined;
  try {
    const db = await _openIdb();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, "readonly");
      const req = tx.objectStore(IDB_STORE).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } catch { return undefined; }
}

async function idbSet(key, value) {
  if (typeof indexedDB === "undefined") return;
  try {
    const db = await _openIdb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, "readwrite");
      tx.objectStore(IDB_STORE).put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch { /* noop */ }
}

export async function resetDemoStore() {
  if (typeof indexedDB === "undefined") return;
  await new Promise((resolve) => {
    const req = indexedDB.deleteDatabase(IDB_NAME);
    req.onsuccess = () => resolve();
    req.onerror = () => resolve();
    req.onblocked = () => resolve();
  });
  disableDemoMode();
}

// -------------------- fixtures lazy getters --------------------

async function _overlay(key, base) {
  const stored = await idbGet(key);
  if (!stored) return base;
  return Array.isArray(base) ? stored : { ...base, ...stored };
}

async function getProjectsForUser(userId) {
  const base = projects.filter((p) => p.user_id === userId || p.owner_user_id === userId);
  const overlay = (await idbGet(`projects:${userId}`)) || [];
  // Deduplicação por project_id (overlay vence)
  const map = new Map(base.map((p) => [p.project_id, p]));
  for (const p of overlay) map.set(p.project_id, p);
  return Array.from(map.values());
}

async function getAssistantDocs() {
  return await _overlay("assistant_docs", assistantDocsFx);
}

// -------------------- routing table --------------------

function _ok(data, status = 200) {
  return { data, status, statusText: "OK", headers: {}, config: {} };
}
function _notFound(msg = "demo: route not implemented") {
  const err = new Error(msg);
  err.response = { status: 404, data: { detail: msg }, headers: {}, config: {} };
  return err;
}

const routes = [
  // Auth
  { method: "GET", match: /^\/auth\/me$/, handle: async () => _ok(currentUser()) },
  { method: "GET", match: /^\/auth\/demo-status$/, handle: async () => _ok({ enabled: true, kind: currentKind() }) },
  { method: "POST", match: /^\/auth\/demo-login$/, handle: async (req) => {
      const kind = (req.data && JSON.parse(req.data).kind) || "pro";
      enableDemoMode({ kind });
      return _ok({ user: currentUser() });
    } },
  { method: "POST", match: /^\/auth\/login$/, handle: async () => _ok({ user: currentUser() }) },
  { method: "POST", match: /^\/auth\/logout$/, handle: async () => _ok({ ok: true }) },

  // Projects
  { method: "GET", match: /^\/projects\/?$/, handle: async () => {
      const u = currentUser();
      return _ok(await getProjectsForUser(u.user_id));
    } },
  { method: "GET", match: /^\/projects\/([^/]+)$/, handle: async (_req, m) => {
      const u = currentUser();
      const ps = await getProjectsForUser(u.user_id);
      const p = ps.find((x) => x.project_id === m[1]);
      if (!p) throw _notFound("project not found (demo)");
      return _ok(p);
    } },

  // Branding (modo demo pro)
  { method: "GET", match: /^\/branding\/?$/, handle: async () => {
      return _ok(currentKind() === "pro" ? brandingFx : {});
    } },

  // Growth / seo-overrides e redirects (chamados em arranque) — devolvem vazio
  { method: "GET", match: /^\/growth\/(seo-overrides|redirects)$/, handle: async () => _ok([]) },

  // Assistant docs (preenchidos em 2c)
  { method: "GET", match: /^\/assistant\/docs\/?$/, handle: async () => _ok(await getAssistantDocs()) },
  { method: "GET", match: /^\/assistant_docs\/?$/, handle: async () => _ok(await getAssistantDocs()) },

  // Plans / quotes (listagens — vazias até 2c)
  { method: "GET", match: /^\/plans\/?$/, handle: async () => _ok(plansFx) },
  { method: "GET", match: /^\/quotes\/?$/, handle: async () => _ok(quotesFx) },

  // Leads (POST) — guardar em IndexedDB
  { method: "POST", match: /^\/leads\/?$/, handle: async (req) => {
      const payload = req.data ? JSON.parse(req.data) : {};
      const existing = (await idbGet("leads")) || [];
      const lead = { ...payload, lead_id: `lead_demo_${Date.now()}`, created_at: new Date().toISOString() };
      existing.push(lead);
      await idbSet("leads", existing);
      return _ok({ ok: true, lead_id: lead.lead_id });
    } },

  // Estimation materials (POST) — passagem silenciosa, devolve lista vazia
  { method: "POST", match: /^\/estimation\/materials$/, handle: async () => _ok({ items: [] }) },

  // Assistente offline — matching por keywords normalizadas, zero LLM.
  // Devolve { reply, suggestions, matched_id } + fallback com sugestões clicáveis.
  { method: "POST", match: /^\/assistant\/(chat|ask|message)\/?$/, handle: async (req) => {
      const body = req.data ? JSON.parse(req.data) : {};
      const text = (body.message || body.text || body.query || body.prompt || "").toString();
      const match = _matchAssistant(text);
      if (match) {
        return _ok({
          reply: match.answer_md,
          suggestions: match.suggestions || [],
          matched_id: match.id,
          source: "demo_offline:fixtures/assistant_responses.json",
        });
      }
      // Fallback — mostra 3-4 sugestões clicáveis dos cenários mais populares
      const popular = assistantResponses.slice(0, 4).map((r) => ({
        label: r.title, action: "ask", prompt: r.title,
      }));
      return _ok({
        reply: "Nesta demo offline o Assistente responde a cenários pré-carregados sobre a Moradia Martins. Experimente perguntar:",
        suggestions: popular,
        matched_id: null,
        source: "demo_offline:fallback",
      });
    } },

  // Threads/history vazios na demo
  { method: "GET", match: /^\/assistant\/(threads|history)\/?$/, handle: async () => _ok([]) },
];

function _normalise(s) {
  return (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function _matchAssistant(text) {
  const q = _normalise(text);
  if (!q) return null;
  let best = null;
  let bestScore = 0;
  for (const r of assistantResponses) {
    let score = 0;
    for (const kw of r.keywords) {
      if (q.includes(_normalise(kw))) score += 1;
    }
    if (score > bestScore) {
      best = r;
      bestScore = score;
    }
  }
  return bestScore > 0 ? best : null;
}

// -------------------- adapter --------------------

function _normalizePath(url, baseURL) {
  let path = url || "";
  if (baseURL && path.startsWith(baseURL)) path = path.slice(baseURL.length);
  // Remover query string
  const q = path.indexOf("?");
  if (q >= 0) path = path.slice(0, q);
  // Remover prefixo absoluto se escaped
  path = path.replace(/^https?:\/\/[^/]+/, "");
  // Garantir prefixo com /
  if (!path.startsWith("/")) path = "/" + path;
  // Despir prefixo `/api` se existir (routes assumem já sem prefixo)
  if (path.startsWith("/api/")) path = path.slice(4);
  if (path === "/api") path = "/";
  return path;
}

function _makeDemoAdapter() {
  return function demoAdapter(config) {
    return new Promise(async (resolve, reject) => {
      try {
        const method = (config.method || "get").toUpperCase();
        const path = _normalizePath(config.url || "", config.baseURL || "");
        for (const r of routes) {
          if (r.method !== method) continue;
          const m = path.match(r.match);
          if (m) {
            const res = await r.handle({ ...config, data: config.data }, m);
            res.config = config;
            resolve(res);
            return;
          }
        }
        // Rota não implementada em demo → 404 silencioso
        const err = _notFound(`demo: ${method} ${path} not implemented`);
        err.config = config;
        reject(err);
      } catch (e) {
        if (!e.config) e.config = config;
        reject(e);
      }
    });
  };
}

// -------------------- install --------------------

/**
 * Instala o adapter demo no cliente axios `api`. Preserva o adapter original e
 * delega-lhe quando `is_demo !== "true"` (contas normais passam intactas).
 */
export function installDemoInterceptor(apiClient) {
  const originalAdapter = apiClient.defaults.adapter;
  const demoAdapter = _makeDemoAdapter();
  apiClient.defaults.adapter = function switchingAdapter(config) {
    if (isDemoActive()) return demoAdapter(config);
    return originalAdapter(config);
  };
  return apiClient;
}
