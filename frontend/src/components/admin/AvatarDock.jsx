// Assistant vidéo admin — fenêtre flottante (coin de l'écran) + pilotage visible du site.
//
// La session LiveKit vit ici, hors des pages : on peut changer de page, l'avatar reste dans
// son coin. L'agent « construpilot-avatar » pilote l'écran de l'admin par RPC LiveKit
// (ui.read / ui.navigate / ui.click / ui.type / ui.scroll / ui.back) : un curseur animé montre
// chaque geste. Garde-fous côté navigateur : jamais de champ mot de passe, jamais de paiement
// ni de suppression définitive ; les boutons qui envoient, valident ou suppriment exigent
// confirmed=true (l'agent ne l'envoie qu'après le « oui » de l'admin).
import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { api } from "@/lib/api";

const PT = typeof window !== "undefined" && /construpilot\.pt|construpilot-recon/.test(window.location.hostname);
const T = PT ? {
  waiting: "A ligar a assistente…", live: "Em direto", stop: "Terminar", min: "Reduzir", open: "Abrir", mic: "Microfone",
  noagent: "A assistente não responde: o agente está online (LiveKit Cloud)?", ended: "Conversa terminada.",
  busy: "A assistente já está a ser usada por outro admin. Tente daqui a alguns minutos.", quota: "Quota Synthesia esgotada este mês.",
  config: "Problema de configuração do avatar (chave Synthesia ou LiveKit). ", error: "A assistente não conseguiu arrancar, tente de novo.",
} : {
  waiting: "Connexion de l'assistante…", live: "En direct", stop: "Terminer", min: "Réduire", open: "Ouvrir", mic: "Micro",
  noagent: "L'assistante ne répond pas : l'agent est-il en ligne (LiveKit Cloud) ?", ended: "Conversation terminée.",
  busy: "L'assistante est déjà utilisée par un autre admin. Réessayez dans quelques minutes.", quota: "Quota Synthesia épuisé pour ce mois.",
  config: "Problème de configuration de l'avatar (clé Synthesia ou LiveKit). ", error: "L'assistante n'a pas pu démarrer, réessayez.",
};

// ------------------------------------------------------------------ petit magasin partagé (panneau admin ↔ fenêtre flottante)
const listeners = new Set();
let state = { phase: "idle", message: "", lang: "fr", micOn: true };
const set = (patch) => { state = { ...state, ...patch }; listeners.forEach((l) => l(state)); };
export const avatarStore = { get: () => state, subscribe: (l) => { listeners.add(l); return () => listeners.delete(l); } };

let room = null;
let timer = null;
let videoEl = null;

// ------------------------------------------------------------------ pilotage visible de l'écran
const SEL = 'a[href],button,input:not([type=hidden]),textarea,select,[role=button],[role=tab],[role=menuitem],[role=option],[role=combobox],[role=checkbox],[role=switch],[contenteditable=true]';
const FORBID = /\b(pagar|pagamento|payer|paiement|payment|checkout|stripe|cart[aã]o|carte bancaire|eliminar definitivamente|supprimer d[ée]finitivement|esvaziar|vider la corbeille|palavra-passe|mot de passe|password)/i;
// Autonomie (demande du fondateur, 31/10) : l'assistante agit seule ; seules les actions irréversibles ou qui partent
// vers l'extérieur (suppression, envoi d'e-mail / de facture / signature, émission, publication) demandent un « oui ».
const CONFIRM = /(apagar|eliminar|supprimer|delete|remover|enviar (?:o |a )?(?:e-?mail|fatura|orçamento|ao cliente)|envoyer (?:l['’]|le |la |au |par )?(?:e-?mail|mail|facture|devis|client)|send (?:e-?mail|invoice)|emitir|[ée]mettre|publicar|publier|signer|assinar|desativar|d[ée]sactiver|bloquear|bloquer|r[ée]voquer|revogar)/i;
const NO_CONFIRM_TESTIDS = new Set(["assistant-send-btn", "choice-submit-btn", "choice-defaults-btn"]);
let ids = new WeakMap();
let seq = 0;

function labelOf(el) {
  const aria = el.getAttribute("aria-label") || el.getAttribute("title");
  if (aria) return aria.trim();
  if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l?.innerText) return l.innerText.trim(); }
  const t = (el.innerText || el.value || "").trim();
  if (t) return t.replace(/\s+/g, " ").slice(0, 60);
  return (el.getAttribute("placeholder") || el.getAttribute("name") || el.getAttribute("data-testid") || el.tagName.toLowerCase()).slice(0, 80);
}
function visible(el) {
  if (el.closest("#cp-avatar-dock")) return false;
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && !el.disabled;
}
function snapshot() {
  const els = [...document.querySelectorAll(SEL)].filter(visible);
  const vh = window.innerHeight;
  els.sort((a, b) => {
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const ia = ra.bottom > 0 && ra.top < vh ? 0 : 1, ib = rb.bottom > 0 && rb.top < vh ? 0 : 1;
    return ia - ib || ra.top - rb.top || ra.left - rb.left;
  });
  const items = els.slice(0, 160).map((el) => {
    if (!ids.has(el)) ids.set(el, `e${++seq}`);
    const id = ids.get(el);
    el.setAttribute("data-cp-ai", id);
    const role = el.getAttribute("role") || (el.tagName === "A" ? "link" : el.tagName === "INPUT" ? `input:${el.type || "text"}` : el.tagName.toLowerCase());
    const group = el.closest("fieldset")?.querySelector("legend")?.innerText?.trim();
    const checked = el.getAttribute("aria-checked") ?? el.getAttribute("aria-selected") ?? (el.type === "checkbox" || el.type === "radio" ? String(el.checked) : null);
    return { id, role, label: labelOf(el), ...(group ? { group: group.slice(0, 90) } : {}), ...(checked != null ? { checked: checked === "true" } : {}),
             ...(el.tagName === "A" ? { href: el.getAttribute("href") } : {}) };
  });
  const main = document.querySelector("main") || document.body;
  const text = (main.innerText || "").replace(/\n{3,}/g, "\n\n").slice(0, 7000);
  return { path: window.location.pathname + window.location.search, title: document.title, text, elements: items };
}
// les réponses RPC LiveKit sont limitées à 15 Ko : on réduit le texte puis la liste
function fit(o) {
  let out = JSON.stringify(o);
  while (out.length > 14000 && o.text.length > 500) { o.text = o.text.slice(0, Math.floor(o.text.length * 0.7)); out = JSON.stringify(o); }
  while (out.length > 14000 && o.elements.length > 20) { o.elements = o.elements.slice(0, o.elements.length - 15); out = JSON.stringify(o); }
  return out;
}
function fit2(o) {
  let out = JSON.stringify(o);
  while (out.length > 14000 && o.last_answer?.length > 400) { o.last_answer = o.last_answer.slice(0, Math.floor(o.last_answer.length * 0.7)) + "…"; out = JSON.stringify(o); }
  return out;
}
function find(id) { return document.querySelector(`[data-cp-ai="${CSS.escape(id)}"]`); }

let cursor = null;
function pointTo(el) {
  return new Promise((resolve) => {
    if (!cursor) {
      cursor = document.createElement("div");
      cursor.id = "cp-avatar-cursor";
      cursor.style.cssText = "position:fixed;z-index:2147483646;width:26px;height:26px;pointer-events:none;transition:left .45s ease,top .45s ease,opacity .3s;left:50vw;top:50vh;opacity:0";
      cursor.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l16 9-7 2-3 7z" fill="#c8763a" stroke="#fff" stroke-width="1.5"/></svg>';
      document.body.appendChild(cursor);
    }
    el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
    setTimeout(() => {
      const r = el.getBoundingClientRect();
      cursor.style.opacity = "1";
      cursor.style.left = `${r.left + Math.min(r.width / 2, 40)}px`;
      cursor.style.top = `${r.top + r.height / 2}px`;
      const prev = el.style.outline;
      el.style.outline = "3px solid #c8763a";
      el.style.outlineOffset = "2px";
      setTimeout(() => { el.style.outline = prev; resolve(); }, 650);
    }, 350);
  });
}
function setNativeValue(el, value) {
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  desc?.set ? desc.set.call(el, value) : (el.value = value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}
const ok = (o) => JSON.stringify({ ok: true, ...o });
const ko = (error, o = {}) => JSON.stringify({ ok: false, error, ...o });
const parse = (d) => { try { return JSON.parse(d.payload || "{}"); } catch { return {}; } };
const settle = (ms = 900) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------------ Assistant BTP : actions structurées
// L'assistante ne « devine » plus l'écran : elle lit l'état réel de la conversation (réponse, cartes de choix,
// fichiers produits) et agit par le même chemin que l'utilisateur (window.__cpAssistant exposé par la page).
const RUNNING = ["queued", "running", "preparing"];
async function assistantPage(timeoutMs = 12000) {
  if (!window.location.pathname.startsWith("/assistant")) {
    window.history.pushState({}, "", "/assistant");
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) { if (window.__cpAssistant) return window.__cpAssistant; await settle(300); }
  return null;
}
function pendingChoices(conv) {
  const msgs = conv?.messages || [];
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m.role === "user") return [];            // une réponse a déjà suivi la dernière carte
    for (const a of m.actions || []) {
      const r = a.result || {};
      if (a.tool === "ask_user_choices" && Array.isArray(r.questions)) {
        if (document.querySelector('[data-testid="choice-card-frozen"]') && !document.querySelector('[data-testid="choice-card"]')) return [];
        return [{ intro: r.intro || "", submit_label: r.submit_label || "", questions: r.questions.map((q) => ({
          id: q.id, label: q.label, multi: !!q.multi, allow_other: !!q.allow_other, recommended: q.default_option_id || null,
          options: (q.options || []).map((o) => ({ id: o.id, label: o.label })) })) }];
      }
    }
  }
  return [];
}
function assistantState() {
  const conv = window.__cpAssistant?.state();
  if (!conv) return { ok: true, page: window.location.pathname, conversation_id: null, running: false, last_answer: "", choices: [], files: [] };
  const msgs = conv.messages || [];
  const last = [...msgs].reverse().find((m) => m.role === "assistant");
  const files = [];
  for (const a of last?.actions || []) {
    const r = a.result || {};
    for (const art of [r.artifact, r.pdf_artifact, r.xlsx_artifact].filter(Boolean)) files.push({ title: art.title, file: art.filename, format: art.format });
    if (r.ok === false && r.error) files.push({ error: `${a.tool}: ${String(r.error).slice(0, 160)}` });
  }
  const job = (conv.jobs || []).find((j) => RUNNING.includes(j.status));
  return { ok: true, conversation_id: conv.conversation_id, title: conv.title || "", running: !!job, job_status: job?.status || null,
           progress: job?.live?.label || job?.live?.status || null, messages: msgs.length,
           last_answer: (last?.content || "").slice(0, 6000), last_message_id: last?.message_id || null,
           tools_used: (last?.actions || []).map((a) => `${a.tool}${a.result?.ok === false ? " (échec)" : ""}`).slice(0, 15),
           choices: pendingChoices(conv), files };
}
async function clickTestId(testid) {
  const el = document.querySelector(`[data-testid="${CSS.escape(testid)}"]`);
  if (!el) return false;
  await pointTo(el);
  el.click();
  await settle(250);
  return true;
}

const HANDLERS = {
  "assistant.status": async () => fit2(assistantState()),
  "assistant.ask": async (d) => {
    const { text, new_conversation, conversation_id } = parse(d);
    if (!String(text || "").trim()) return ko("texte vide");
    const a = await assistantPage();
    if (!a) return ko("page Assistant BTP indisponible");
    if (conversation_id && a.state()?.conversation_id !== conversation_id) { await a.open(conversation_id); await settle(800); }
    else if (new_conversation) { await a.newConversation(); await settle(800); }
    const before = (a.state()?.messages || []).length;
    await a.send(String(text).slice(0, 7900));
    const end = Date.now() + 15000;
    while (Date.now() < end && (a.state()?.messages || []).length <= before && !(a.state()?.jobs || []).some((j) => RUNNING.includes(j.status))) await settle(500);
    return fit2({ ...assistantState(), sent: true });
  },
  "assistant.wait": async (d) => {
    const secs = Math.min(40, Math.max(3, Number(parse(d).seconds) || 30));
    const a = await assistantPage(4000);
    if (!a) return ko("page Assistant BTP indisponible");
    const startId = assistantState().last_message_id;
    const end = Date.now() + secs * 1000;
    while (Date.now() < end) {
      a.refresh?.();
      await settle(2500);
      const st = assistantState();
      if (!st.running && st.last_message_id !== startId) return fit2({ ...st, done: true });
      if (!st.running && st.choices.length) return fit2({ ...st, done: true });
    }
    return fit2({ ...assistantState(), done: false, note: "toujours en cours : rappeler assistant_wait" });
  },
  "assistant.choose": async (d) => {
    const { answers = {}, other = {}, use_recommended } = parse(d);
    const st = assistantState();
    const card = st.choices[0];
    if (!card) return ko("aucune carte de choix en attente");
    if (use_recommended) {
      if (!(await clickTestId("choice-defaults-btn"))) return ko("bouton « hypothèses courantes » introuvable");
    } else {
      for (const q of card.questions) {
        const want = [].concat(answers[q.id] ?? []).map(String);
        if (!want.length) continue;                        // question non précisée : la valeur recommandée reste cochée
        for (const o of q.options) {
          const el = document.querySelector(`[data-testid="${CSS.escape(`choice-opt-${q.id}-${o.id}`)}"]`);
          if (!el) continue;
          const on = el.getAttribute("aria-checked") === "true";
          if (want.includes(o.id) !== on && (q.multi || want.includes(o.id))) { await pointTo(el); el.click(); await settle(200); }
        }
        if (want.includes("other") && other[q.id]) {
          await clickTestId(`choice-opt-${q.id}-other`);
          const input = document.querySelector(`[data-testid="${CSS.escape(`choice-other-input-${q.id}`)}"]`);
          if (input) { await pointTo(input); setNativeValue(input, String(other[q.id])); await settle(200); }
        }
      }
      if (!(await clickTestId("choice-submit-btn"))) return ko("bouton de validation introuvable");
    }
    await settle(2500);
    return fit2({ ...assistantState(), submitted: true });
  },
  "ui.read": async () => fit(snapshot()),
  "ui.navigate": async (d) => {
    const p = String(parse(d).path || "");
    if (!p.startsWith("/") || p.startsWith("//")) return ko("chemin invalide (commencer par /)");
    window.history.pushState({}, "", p);
    window.dispatchEvent(new PopStateEvent("popstate"));
    await settle(1400);
    return ok({ path: window.location.pathname });
  },
  "ui.back": async () => { window.history.back(); await settle(1200); return ok({ path: window.location.pathname }); },
  "ui.scroll": async (d) => {
    const dir = parse(d).direction === "up" ? -1 : 1;
    window.scrollBy({ top: dir * window.innerHeight * 0.8, behavior: "smooth" });
    await settle(600);
    return ok({});
  },
  "ui.click": async (d) => {
    const { id, confirmed } = parse(d);
    const el = find(String(id || ""));
    if (!el) return ko("élément introuvable : relire la page avec ui_read");
    const label = labelOf(el);
    if (FORBID.test(label)) return ko("action interdite à l'assistante (paiement, mot de passe ou suppression définitive) : à faire à la main", { label });
    if (CONFIRM.test(label) && !NO_CONFIRM_TESTIDS.has(el.getAttribute("data-testid")) && !confirmed)
      return ko("confirmation requise", { needs_confirmation: true, label });
    await pointTo(el);
    el.click();
    await settle();
    return ok({ clicked: label, path: window.location.pathname });
  },
  "ui.type": async (d) => {
    const { id, text, submit } = parse(d);
    const el = find(String(id || ""));
    if (!el) return ko("élément introuvable : relire la page avec ui_read");
    if (el.type === "password" || FORBID.test(labelOf(el))) return ko("champ interdit à l'assistante");
    await pointTo(el);
    el.focus();
    if (el.isContentEditable) { document.execCommand("selectAll"); document.execCommand("insertText", false, String(text ?? "")); }
    else setNativeValue(el, String(text ?? ""));
    if (submit) el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
    await settle(500);
    return ok({ typed: true });
  },
};

// ------------------------------------------------------------------ session
function reset(message = "") {
  clearTimeout(timer);
  room = null;
  videoEl = null;
  cursor?.remove(); cursor = null;
  set({ phase: "idle", message });
}

export async function startAvatar(lang = "fr") {
  if (room) return;
  set({ phase: "connecting", message: "", lang, micOn: true });
  try {
    const { data } = await api.get("/admin/avatar/token", { params: { lang } });
    const { Room, RoomEvent } = await import("livekit-client");
    const r = new Room({ adaptiveStream: false });
    room = r;
    let notice = null;
    r.on(RoomEvent.TrackSubscribed, (track) => {
      if (!videoEl) { videoEl = document.createElement("video"); videoEl.playsInline = true; videoEl.autoplay = true; }
      track.attach(videoEl);
      if (track.kind === "video") { clearTimeout(timer); set({ phase: "live", message: "" }); }
      else set({});
    });
    r.on(RoomEvent.DataReceived, (payload, _p, _k, topic) => {
      if (topic !== "avatar") return;
      try {
        const m = JSON.parse(new TextDecoder().decode(payload));
        if (m.type === "avatar_status") { notice = (T[m.code] || T.error) + (m.code === "config" ? (m.detail || "") : ""); r.disconnect(); }
      } catch { /* ignoré */ }
    });
    r.on(RoomEvent.Disconnected, () => reset(notice || T.ended));
    Object.entries(HANDLERS).forEach(([name, fn]) => r.registerRpcMethod(name, fn));
    await r.connect(data.url, data.token);
    await r.localParticipant.setMicrophoneEnabled(true);
    if (state.phase !== "live") set({ phase: "waiting" });
    timer = setTimeout(() => { if (state.phase !== "live") set({ message: T.noagent }); }, 60000);
  } catch (e) {
    room?.disconnect();
    reset(e?.response?.data?.detail || e?.message || T.error);
  }
}
export async function stopAvatar() { await room?.disconnect(); reset(T.ended); }
async function toggleMic() {
  if (!room) return;
  const on = !state.micOn;
  await room.localParticipant.setMicrophoneEnabled(on);
  set({ micOn: on });
}

// ------------------------------------------------------------------ fenêtre flottante
function Dock() {
  const [s, setS] = useState(state);
  const [min, setMin] = useState(false);
  const [pos, setPos] = useState({ right: 20, bottom: 20 });
  const holder = useRef(null);
  const drag = useRef(null);
  useEffect(() => avatarStore.subscribe(setS), []);
  useEffect(() => {
    if (holder.current && videoEl && videoEl.parentElement !== holder.current) {
      videoEl.style.cssText = "width:100%;height:100%;object-fit:cover;display:block;background:transparent";
      holder.current.replaceChildren(videoEl);
    }
  });
  if (s.phase === "idle") return null;
  const onDown = (e) => { drag.current = { x: e.clientX, y: e.clientY, ...pos }; e.currentTarget.setPointerCapture(e.pointerId); };
  const onMove = (e) => {
    if (!drag.current) return;
    const d = drag.current;
    setPos({ right: Math.max(4, d.right - (e.clientX - d.x)), bottom: Math.max(4, d.bottom - (e.clientY - d.y)) });
  };
  const btn = { border: 0, borderRadius: 8, padding: "4px 8px", fontSize: 12, cursor: "pointer", color: "#fff" };
  return (
    <div id="cp-avatar-dock" data-testid="avatar-dock"
      style={{ position: "fixed", right: pos.right, bottom: pos.bottom, zIndex: 2147483645, width: min ? 64 : 230,
               borderRadius: 16, overflow: "hidden", boxShadow: "0 12px 32px rgba(0,0,0,.35)", background: "#14532d",
               border: "2px solid #c8763a", fontFamily: "inherit" }}>
      <div onPointerDown={onDown} onPointerMove={onMove} onPointerUp={() => { drag.current = null; }}
        style={{ cursor: "move", height: min ? 64 : 290, position: "relative" }}>
        <div ref={holder} style={{ width: "100%", height: "100%", background: "transparent" }} />
        {s.phase !== "live" && !min && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#f5efe3",
                        fontSize: 12, textAlign: "center", padding: 12 }}>{s.message || T.waiting}</div>)}
      </div>
      {!min && (
        <div style={{ display: "flex", gap: 6, padding: 6, alignItems: "center", background: "#14532d" }}>
          <span style={{ color: "#f5efe3", fontSize: 11, flex: 1 }}>{s.phase === "live" ? `● ${T.live}` : "…"}</span>
          <button type="button" style={{ ...btn, background: s.micOn ? "#285541" : "#7a2e2e" }} onClick={toggleMic} title={T.mic}>{s.micOn ? "🎙" : "🔇"}</button>
          <button type="button" style={{ ...btn, background: "#285541" }} onClick={() => setMin(true)} title={T.min}>▁</button>
          <button type="button" style={{ ...btn, background: "#b42318" }} onClick={stopAvatar} data-testid="avatar-dock-stop">{T.stop}</button>
        </div>)}
      {min && <button type="button" onClick={() => setMin(false)} title={T.open}
        style={{ position: "absolute", inset: 0, background: "transparent", border: 0, cursor: "pointer" }} />}
    </div>
  );
}

// montage unique, hors de l'arbre des pages (la session survit aux changements de page)
if (typeof document !== "undefined" && !document.getElementById("cp-avatar-dock-root")) {
  const host = document.createElement("div");
  host.id = "cp-avatar-dock-root";
  document.body.appendChild(host);
  ReactDOM.createRoot(host).render(<Dock />);
}
export const __uiHandlers = HANDLERS;   // tests
