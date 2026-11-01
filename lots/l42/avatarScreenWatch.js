// Écran en direct pour l'assistante vidéo : à chaque changement visible (page, saisie, défilement, message,
// fenêtre, erreur, progression de l'Assistant BTP), un résumé compact part vers l'agent (data LiveKit, topic « screen »).
// L'agent l'injecte dans ses instructions : il répond et décide sur ce que l'admin voit MAINTENANT,
// sans aller-retour ui_read, et réagit seul aux erreurs, résultats et cartes de choix.
const MAX = 3800;
let room = null;
let observer = null;
let timer = null;
let poll = null;
let lastSent = "";
let lastPath = "";
let lastAlerts = "";
let lastAsst = { running: false, choices: 0, id: null };
let agentUntil = 0;
const pageErrors = [];
const pushErr = (m) => { if (m) { pageErrors.push(m); if (pageErrors.length > 10) pageErrors.shift(); } };
const cleanups = [];

export const markAgentAction = (ms = 4000) => { agentUntil = Date.now() + ms; };
const actor = () => (Date.now() < agentUntil ? "assistant" : "admin");
const clean = (s, n) => String(s || "").replace(/\s+/g, " ").trim().slice(0, n);
const inDock = (el) => !!el?.closest?.("#cp-avatar-dock, #cp-avatar-cursor");
function shown(el) {
  if (!el || inDock(el)) return false;
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return false;
  const s = getComputedStyle(el);
  return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05;
}
function labelOf(el) {
  const aria = el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.getAttribute("name");
  if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l?.innerText) return clean(l.innerText, 60); }
  return clean(aria || el.getAttribute("data-testid") || el.tagName.toLowerCase(), 60);
}
function viewportText(root, limit = 1500) {
  const vh = window.innerHeight;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.nodeValue.trim() && !inDock(n.parentElement) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
  });
  const parts = [];
  let size = 0, seen = 0, prev = null;
  while (walker.nextNode() && seen < 4000 && size < limit) {
    seen += 1;
    const p = walker.currentNode.parentElement;
    if (!p || p === prev) continue;
    const r = p.getBoundingClientRect();
    if (r.bottom < 0 || r.top > vh || r.width === 0) continue;
    if (["SCRIPT", "STYLE", "NOSCRIPT"].includes(p.tagName)) continue;
    const t = clean(walker.currentNode.nodeValue, 200);
    if (t.length < 2) continue;
    prev = p;
    parts.push(t);
    size += t.length + 3;
  }
  return parts.join(" · ").slice(0, limit);
}
function alerts() {
  const out = [];
  document.querySelectorAll('[role="alert"], [role="status"], [data-sonner-toast], .toast, [aria-live="assertive"]').forEach((el) => {
    if (!shown(el)) return;
    const t = clean(el.innerText, 220);
    if (!t) return;
    const type = el.getAttribute("data-type") || (/erro|erreur|error|falh|échec|invalid/i.test(t) ? "error" : "info");
    out.push({ type, text: t });
  });
  return out.slice(0, 5);
}
function dialog() {
  const d = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"], dialog[open]')].filter(shown).pop();
  if (!d) return null;
  const title = d.querySelector("h1,h2,h3,[id$=title],[data-slot=dialog-title]")?.innerText;
  return { title: clean(title, 120), text: clean(d.innerText, 500) };
}
function assistant() {
  const conv = window.__cpAssistant?.state?.();
  if (!conv) return null;
  const msgs = conv.messages || [];
  const last = [...msgs].reverse().find((m) => m.role === "assistant");
  const job = (conv.jobs || []).find((j) => ["queued", "running", "preparing"].includes(j.status));
  let choices = 0;
  for (const a of last?.actions || []) if (a.tool === "ask_user_choices" && Array.isArray(a.result?.questions)) choices = a.result.questions.length;
  if (msgs.length && msgs[msgs.length - 1].role === "user") choices = 0;
  return { running: !!job, progress: clean(job?.live?.label || job?.live?.status, 120) || null, messages: msgs.length,
           last_answer: clean(last?.content, 600), last_id: last?.message_id || null, choices };
}
function build() {
  const main = document.querySelector("main") || document.body;
  const active = document.activeElement;
  const isField = active && active !== document.body && !inDock(active) && (/INPUT|TEXTAREA|SELECT/.test(active.tagName) || active.isContentEditable);
  const focused = isField
    ? { field: labelOf(active), value: active.type === "password" ? "••••" : clean(active.value ?? active.innerText, 160) } : null;
  const sel = clean(window.getSelection?.()?.toString(), 300);
  const scrollMax = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
  return {
    path: window.location.pathname + window.location.search,
    title: clean(document.title, 120),
    headings: [...main.querySelectorAll("h1, h2")].filter(shown).slice(0, 6).map((h) => clean(h.innerText, 90)).filter(Boolean),
    scroll: Math.round((window.scrollY / scrollMax) * 100),
    dialog: dialog(),
    alerts: alerts(),
    focused,
    selection: sel || null,
    assistant: window.location.pathname.startsWith("/assistant") ? assistant() : null,
    errors: pageErrors.slice(-3),
    visible: viewportText(main),
  };
}
// seuls les erreurs, fenêtres et erreurs JS déclenchent une réaction ; « chargement… » reste un simple changement
const alertSig = (s) => JSON.stringify([s.alerts.filter((a) => a.type === "error"), s.dialog?.title ?? null, s.errors]);
function classify(s) {
  if (s.path !== lastPath) return "navigate";
  const al = alertSig(s);
  if (al !== lastAlerts && al !== "[[],null,[]]") return "alert";
  const a = s.assistant;
  if (a) {
    if (lastAsst.running && !a.running && a.last_id !== lastAsst.id) return "assistant_done";
    if (a.choices && !lastAsst.choices) return "assistant_choices";
  }
  return "change";
}
function send() {
  timer = null;
  if (!room || room.state === "disconnected") return;
  const s = build();
  const event = classify(s);
  const core = JSON.stringify({ ...s, scroll: Math.round(s.scroll / 10) });
  if (core === lastSent && event === "change") return;
  lastSent = core;
  lastPath = s.path;
  lastAlerts = alertSig(s);
  if (s.assistant) lastAsst = { running: s.assistant.running, choices: s.assistant.choices, id: s.assistant.last_id };
  const msg = { type: "screen", event, actor: actor(), at: Date.now(), ...s };
  let out = JSON.stringify(msg);
  while (out.length > MAX && msg.visible.length > 200) { msg.visible = msg.visible.slice(0, Math.floor(msg.visible.length * 0.7)); out = JSON.stringify(msg); }
  try { room.localParticipant.publishData(new TextEncoder().encode(out), { reliable: true, topic: "screen" }); } catch { /* salle fermée */ }
}
const schedule = (ms = 700) => { if (!timer) timer = setTimeout(send, ms); };
const on = (target, ev, fn, opts) => { target.addEventListener(ev, fn, opts); cleanups.push(() => target.removeEventListener(ev, fn, opts)); };

export function startScreenWatch(r) {
  stopScreenWatch();
  room = r;
  lastSent = ""; lastPath = ""; lastAlerts = ""; lastAsst = { running: false, choices: 0, id: null };
  observer = new MutationObserver((list) => { if (list.some((m) => !inDock(m.target.nodeType === 1 ? m.target : m.target.parentElement))) schedule(900); });
  observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["aria-checked", "aria-selected", "open", "data-state"] });
  for (const k of ["pushState", "replaceState"]) {
    const orig = window.history[k];
    window.history[k] = function patched(...a) { const res = orig.apply(this, a); schedule(400); return res; };
    cleanups.push(() => { window.history[k] = orig; });
  }
  on(window, "popstate", () => schedule(400));
  on(window, "scroll", () => schedule(1200), { passive: true });
  on(document, "focusin", () => schedule(500));
  on(document, "input", () => schedule(1200));
  on(document, "selectionchange", () => schedule(1200));
  on(window, "error", (e) => { pushErr(clean(e.message, 160)); schedule(300); });
  on(window, "unhandledrejection", (e) => { pushErr(clean(e.reason?.message || e.reason, 160)); schedule(300); });
  poll = setInterval(() => schedule(0), 5000);
  schedule(300);
}
export function stopScreenWatch() {
  clearTimeout(timer); timer = null;
  clearInterval(poll); poll = null;
  observer?.disconnect(); observer = null;
  while (cleanups.length) cleanups.pop()();
  pageErrors.length = 0;
  room = null;
}
export const __screenBuild = build; // tests
