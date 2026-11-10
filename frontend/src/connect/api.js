// Cliente HTTP próprio do /connect: NÃO usa a instância `api` (que, em modo demo/stand, interceta
// todos os pedidos /api com fixtures). Assim os pedidos reais chegam ao servidor quando há rede,
// e o diagnóstico continua a funcionar offline com o motor local.
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const http = axios.create({ baseURL: `${BACKEND_URL}/api/connect`, timeout: 12000 });

const SKEY = (profile) => `cp_connect_${profile}`;
const RESULTS = "cp_connect_results";
const OUTBOX = "cp_connect_outbox";

function read(storage, key, fallback) {
  try { const v = storage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}
function write(storage, key, value) {
  try { storage.setItem(key, JSON.stringify(value)); } catch { /* armazenamento indisponível */ }
}

/** Estado local do percurso (respostas nunca se perdem ao recuar, mudar de idioma ou recarregar). */
export function loadState(profile) {
  return read(sessionStorage, SKEY(profile), { answers: {}, step: 0, sid: null, token: null });
}
export function saveState(profile, state) {
  write(sessionStorage, SKEY(profile), state);
}
export function clearAll() {
  try {
    ["client", "investor", "partner"].forEach((p) => sessionStorage.removeItem(SKEY(p)));
    sessionStorage.removeItem(RESULTS);
  } catch { /* noop */ }
}

/** Mapa sid → token, para reabrir /connect/result/:sid no mesmo navegador. */
export function rememberResult(sid, token, profile) {
  const m = read(sessionStorage, RESULTS, {});
  m[sid] = { token, profile };
  write(sessionStorage, RESULTS, m);
}
export function tokenFor(sid) {
  const m = read(sessionStorage, RESULTS, {});
  if (m[sid]) return m[sid];
  try {
    const h = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const t = h.get("t");
    if (t) return { token: t, profile: null };
  } catch { /* noop */ }
  return null;
}

export function attribution() {
  try {
    const q = new URLSearchParams(window.location.search);
    const clean = (v) => (v || "").toLowerCase().replace(/[^a-z0-9_.-]/g, "").slice(0, 60);
    return {
      source: clean(q.get("source") || q.get("utm_source")),
      utm_source: clean(q.get("utm_source")),
      utm_medium: clean(q.get("utm_medium")),
      utm_campaign: clean(q.get("utm_campaign")),
    };
  } catch { return {}; }
}

export function analyticsConsent() {
  try { return localStorage.getItem("cp_cookie_consent") === "accepted"; } catch { return false; }
}

const auth = (token) => ({ headers: { "X-Connect-Token": token } });

export async function ensureSession(profile, lang, { stand = false } = {}) {
  const st = loadState(profile);
  if (st.sid && st.token) return st;
  const { data } = await http.post("/sessions", { profile, lang, stand, ...attribution() });
  const next = { ...st, sid: data.session_id, token: data.token };
  saveState(profile, next);
  rememberResult(data.session_id, data.token, profile);
  return next;
}

export async function saveAnswers(sid, token, answers, step, lang) {
  const { data } = await http.put(`/sessions/${sid}/answers`, { answers, step, lang }, auth(token));
  return data;
}

export async function getSession(sid, token) {
  const { data } = await http.get(`/sessions/${sid}`, auth(token));
  return data;
}

export async function demoProgress(sid, token, demo_id, event, step = 0) {
  if (!sid || !token) return;
  try { await http.post(`/sessions/${sid}/demo`, { demo_id, event, step }, auth(token)); } catch { /* fail-soft */ }
}

export async function track(sid, token, name, extra = {}) {
  if (!sid || !token || !analyticsConsent()) return;
  try { await http.post(`/sessions/${sid}/events`, { name, analytics_consent: true, ...extra }, auth(token)); } catch { /* fail-soft */ }
}

export async function computeDemo(demoId, params) {
  const { data } = await http.post(`/demo/${demoId}/compute`, { params });
  return data;
}

export async function fetchCatalogStatus() {
  try { const { data } = await http.get("/status"); return data; } catch { return null; }
}

function isNetworkError(e) {
  return !e.response && (e.code === "ERR_NETWORK" || e.code === "ECONNABORTED" || !navigator.onLine || e.message === "Network Error");
}

/** Envia o contacto; sem rede, guarda numa fila local e reenvia quando a ligação voltar (stand offline). */
export async function submitContact(sid, token, payload) {
  try {
    const { data } = await http.post(`/sessions/${sid}/contact`, payload, auth(token));
    return { ...data, queued: false };
  } catch (e) {
    if (isNetworkError(e)) {
      const box = read(localStorage, OUTBOX, []);
      box.push({ sid, token, payload, at: Date.now() });
      write(localStorage, OUTBOX, box);
      return { ok: true, queued: true };
    }
    throw e;
  }
}

/** Fila offline: respostas pendentes também (sessão criada offline). */
export async function flushOutbox() {
  const box = read(localStorage, OUTBOX, []);
  if (!box.length) return 0;
  const rest = [];
  let sent = 0;
  for (const item of box) {
    try {
      let { sid, token } = item;
      if (item.pendingSession) {
        const { data } = await http.post("/sessions", item.pendingSession);
        sid = data.session_id; token = data.token;
        await http.put(`/sessions/${sid}/answers`, { answers: item.answers, step: 9, lang: item.pendingSession.lang }, auth(token));
      }
      await http.post(`/sessions/${sid}/contact`, item.payload, auth(token));
      sent += 1;
    } catch (e) {
      if (isNetworkError(e)) rest.push(item);
      // erros 4xx são descartados (dados inválidos não ficam guardados indefinidamente)
    }
  }
  write(localStorage, OUTBOX, rest);
  return sent;
}

export function queueOfflineLead({ profile, lang, answers, payload, stand }) {
  const box = read(localStorage, OUTBOX, []);
  box.push({ pendingSession: { profile, lang, stand: !!stand, ...attribution() }, answers, payload, at: Date.now() });
  write(localStorage, OUTBOX, box);
}

export function outboxSize() {
  return read(localStorage, OUTBOX, []).length;
}

if (typeof window !== "undefined") {
  window.addEventListener("online", () => { flushOutbox(); });
}
