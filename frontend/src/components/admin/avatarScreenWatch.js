// Écran en direct pour l'assistante vidéo : à chaque changement visible (page, saisie, défilement, message,
// fenêtre, erreur, progression de l'Assistant BTP), un résumé compact part vers l'agent (data LiveKit, topic « screen »).
// L'agent l'injecte dans ses instructions : il répond et décide sur ce que l'admin voit MAINTENANT,
// sans aller-retour ui_read, et réagit seul aux erreurs, résultats et cartes de choix.
import { describe, elements as domElements } from "./avatarDom";

// L'assistante voit TOUT l'écran : texte visible de toute la page (menus, panneaux, fenêtres hors <main>), le reste de la
// page au-dessus / en dessous, les champs remplis, les tableaux et les pièces jointes. Paquet LiveKit fiable < 15 Ko.
const MAX_BYTES = 14000;
const bytes = (s) => new TextEncoder().encode(s).length;
let room = null;
let observer = null;
let timer = null;
let poll = null;
let lastSent = "";
let lastPath = "";
let lastAlerts = "";
let lastAsst = { running: false, choices: 0, id: null };
let lastFiles = "";
let agentUntil = 0;
const pageErrors = [];
const pushErr = (m) => { if (m) { pageErrors.push(m); if (pageErrors.length > 10) pageErrors.shift(); } };
const cleanups = [];

export const markAgentAction = (ms = 4000) => { agentUntil = Date.now() + ms; };
export const agentActing = () => Date.now() < agentUntil;
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
function viewportText(root, limit = 1500, outside = false) {
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
    if (r.width === 0 && r.height === 0) continue;
    const inView = !(r.bottom < 0 || r.top > vh);
    if (inView === outside) continue;
    if (outside) { const s = getComputedStyle(p); if (s.display === "none" || s.visibility === "hidden") continue; }
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
  const lastUser = [...msgs].reverse().find((m) => m.role === "user");
  return { running: !!job, progress: clean(job?.live?.label || job?.live?.status, 120) || null, messages: msgs.length,
           last_answer: clean(last?.content, 900), last_id: last?.message_id || null, choices,
           last_sent_files: (lastUser?.attachments || []).map((f) => clean(f.filename, 80)).slice(0, 10) };
}
// Pièces jointes à l'écran AVANT envoi : composeur de l'Assistant BTP (état exact) + tout fichier marqué ailleurs
// (data-cp-attachment) + champs fichier du navigateur encore remplis. L'assistante les reconnaît sans qu'on les envoie.
function attachments() {
  const out = [];
  const seen = new Set();
  const add = (f) => { const k = `${f.name}|${f.kind || ""}`; if (f.name && !seen.has(k)) { seen.add(k); out.push(f); } };
  const comp = window.__cpAssistant?.composer?.();
  for (const f of comp?.files || []) add({ name: clean(f.name, 90), kind: f.kind, pages: f.pages || undefined, text_read: f.has_text ?? undefined,
                                           new: !!f.new, where: "assistant", busy: f.busy || undefined, files: f.total ? `${f.files ?? 0}/${f.total}` : undefined });
  document.querySelectorAll("[data-cp-attachment]").forEach((el) => {
    if (inDock(el)) return;
    add({ name: clean(el.getAttribute("data-cp-attachment"), 90), kind: el.getAttribute("data-cp-attachment-kind") || undefined,
          new: el.getAttribute("data-cp-attachment-new") === "1", where: "page" });
  });
  document.querySelectorAll('input[type="file"]').forEach((el) => {
    if (inDock(el)) return;
    for (const f of el.files || []) add({ name: clean(f.name, 90), kind: f.type || undefined, size_kb: Math.round(f.size / 1024), new: true, where: "field" });
  });
  return { files: out.slice(0, 25), uploading: !!comp?.uploading, draft: comp ? clean(comp.draft, 300) : undefined,
           ready_to_send: comp ? !!comp.ready_to_send : undefined };
}
// Champs de formulaire de la page (valeurs saisies, listes, cases) : l'assistante sait ce qui est rempli ou vide.
function fields(limit = 40) {
  const out = [];
  document.querySelectorAll("input:not([type=hidden]):not([type=file]):not([type=button]):not([type=submit]), textarea, select").forEach((el) => {
    if (out.length >= limit || inDock(el)) return;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    let value;
    if (el.type === "password") value = el.value ? "••••" : "";
    else if (el.type === "checkbox" || el.type === "radio") value = el.checked ? "✓" : "✗";
    else if (el.tagName === "SELECT") value = clean(el.selectedOptions?.[0]?.text, 80);
    else value = clean(el.value, 120);
    out.push({ field: labelOf(el), value: value || "(vide)", ...(el.required && !el.value ? { required: true } : {}), ...(el.disabled ? { disabled: true } : {}) });
  });
  return out;
}
// Pages réellement disponibles (menu latéral, barre du bas, liens internes visibles) : l'agent n'invente plus d'adresse.
function menuLinks() {
  const seen = new Map();
  document.querySelectorAll('nav a[href^="/"], aside a[href^="/"], header a[href^="/"], [data-testid^="workspace-nav"] a[href^="/"], a[data-testid^="workspace-"][href^="/"]').forEach((a) => {
    if (inDock(a)) return;
    const href = a.getAttribute("href").split("#")[0];
    const label = clean(a.getAttribute("aria-label") || a.innerText, 40);
    if (href && label && !seen.has(href)) seen.set(href, label);
  });
  return [...seen].slice(0, 80).map(([href, label]) => `${label}=${href}`);
}
const notFound = () => /\b404\b|p[áa]gina n[ãa]o encontrada|page (introuvable|non trouv[ée]e)|page not found/i.test(document.body.innerText.slice(0, 3000));
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
    visible: viewportText(document.body, 3200),
    beyond: viewportText(main, 2400, true),   // le reste de la page (hors écran) : l'assistante sait ce qu'il y a plus haut / plus bas
    fields: fields(),
    attachments: attachments(),
    not_found: notFound(),
    // éléments cliquables visibles, avec les mêmes ids que les actions : l'agent clique sans ui_read
    elements: domElements({ limit: 70, viewportOnly: true }).map(describe).map(({ href, group, ...e }) => e),
    menu: window.location.pathname !== lastPath ? menuLinks() : undefined,
  };
}
// seuls les erreurs, fenêtres et erreurs JS déclenchent une réaction ; « chargement… » reste un simple changement
const alertSig = (s) => JSON.stringify([s.alerts.filter((a) => a.type === "error"), s.dialog?.title ?? null, s.errors]);
function classify(s) {
  if (s.path !== lastPath) return "navigate";
  const al = alertSig(s);
  if (al !== lastAlerts && al !== "[[],null,[]]") return "alert";
  const fsig = JSON.stringify(s.attachments.files.map((f) => f.name));
  if (fsig !== lastFiles && s.attachments.files.length > (JSON.parse(lastFiles || "[]").length)) return "files_attached";
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
  lastFiles = JSON.stringify(s.attachments.files.map((f) => f.name));
  if (s.assistant) lastAsst = { running: s.assistant.running, choices: s.assistant.choices, id: s.assistant.last_id };
  const msg = { type: "screen", event, actor: actor(), at: Date.now(), ...s };
  let out = JSON.stringify(msg);
  // trop gros : on raccourcit d'abord le hors-écran, puis le texte visible, les éléments, les champs — jamais les pièces jointes
  const fit = (cond, cut) => { while (bytes(out) > MAX_BYTES && cond()) { cut(); out = JSON.stringify(msg); } };
  fit(() => msg.beyond.length > 100, () => { msg.beyond = msg.beyond.slice(0, Math.floor(msg.beyond.length * 0.6)); });
  fit(() => msg.visible.length > 400, () => { msg.visible = msg.visible.slice(0, Math.floor(msg.visible.length * 0.75)); });
  fit(() => msg.elements.length > 15, () => { msg.elements = msg.elements.slice(0, msg.elements.length - 8); });
  fit(() => msg.fields.length > 8, () => { msg.fields = msg.fields.slice(0, msg.fields.length - 6); });
  fit(() => (msg.menu || []).length > 10, () => { msg.menu = msg.menu.slice(0, msg.menu.length - 10); });
  try { room.localParticipant.publishData(new TextEncoder().encode(out), { reliable: true, topic: "screen" }); } catch { /* salle fermée */ }
}
const schedule = (ms = 300) => { if (!timer) timer = setTimeout(send, ms); };
// après une action de l'assistante : l'écran part tout de suite (pas d'attente du prochain changement)
export const pushScreenNow = () => { clearTimeout(timer); timer = null; send(); };
const on = (target, ev, fn, opts) => { target.addEventListener(ev, fn, opts); cleanups.push(() => target.removeEventListener(ev, fn, opts)); };

export function startScreenWatch(r) {
  stopScreenWatch();
  room = r;
  lastSent = ""; lastPath = ""; lastAlerts = ""; lastFiles = ""; lastAsst = { running: false, choices: 0, id: null };
  observer = new MutationObserver((list) => { if (list.some((m) => !inDock(m.target.nodeType === 1 ? m.target : m.target.parentElement))) schedule(350); });
  observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["aria-checked", "aria-selected", "open", "data-state"] });
  for (const k of ["pushState", "replaceState"]) {
    const orig = window.history[k];
    window.history[k] = function patched(...a) { const res = orig.apply(this, a); schedule(150); return res; };
    cleanups.push(() => { window.history[k] = orig; });
  }
  on(window, "popstate", () => schedule(150));
  on(window, "scroll", () => schedule(600), { passive: true });
  on(document, "focusin", () => schedule(250));
  on(document, "input", () => schedule(700));
  on(document, "change", () => schedule(200));   // fichier choisi, case cochée, liste : tout de suite
  on(document, "drop", () => schedule(400), true);
  on(document, "selectionchange", () => schedule(1200));
  on(window, "error", (e) => { pushErr(clean(e.message, 160)); schedule(300); });
  on(window, "unhandledrejection", (e) => { pushErr(clean(e.reason?.message || e.reason, 160)); schedule(300); });
  poll = setInterval(() => schedule(0), 4000);
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
