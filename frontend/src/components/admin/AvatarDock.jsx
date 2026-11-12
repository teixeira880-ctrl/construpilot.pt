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
import { api, API } from "@/lib/api";
import { startScreenWatch, stopScreenWatch, markAgentAction, agentActing, pushScreenNow, setCameraOn } from "./avatarScreenWatch";
import { brief, describe, elements, findTarget, labelOf } from "./avatarDom";
import { startSpeechSync, stopSpeechSync } from "./avatarSpeech";

const PT = typeof window !== "undefined" && /construpilot\.pt|construpilot-recon/.test(window.location.hostname);
const T = PT ? {
  waiting: "A ligar a assistente…", live: "Em direto", stop: "Terminar", min: "Reduzir", open: "Abrir", mic: "Microfone", cam: "Câmara", camOn: "Câmara ativa", camDenied: "Acesso à câmara recusado pelo navegador.",
  camConsent: "Ativar a câmara?\n\nA assistente vê a imagem para perceber o ambiente (sala, obra, plano mostrado à câmara).\nNão identifica pessoas pelo rosto e não guarda nenhuma imagem.\nPode desligar a qualquer momento.",
  noagent: "A assistente não responde: o agente está online (LiveKit Cloud)?", micDenied: "Microfone bloqueado: autorize o microfone para este site nas definições do navegador.", sound: "Clique em qualquer sítio para ativar o som da assistente.", micDead: "O microfone deixou de enviar som — foi religado automaticamente.", ended: "Conversa terminada.",
  busy: "A assistente já está a ser usada por outro admin. Tente daqui a alguns minutos.", quota: "Quota Synthesia esgotada este mês.",
  config: "Problema de configuração do avatar (chave Synthesia ou LiveKit). ", error: "A assistente não conseguiu arrancar, tente de novo.",
  hush: "Silêncio (ou diga « cala-te »)", listening: "A ouvir", thinking: "A pensar…", speaking: "A falar", acting: "A agir no ecrã", you: "Você",
} : {
  waiting: "Connexion de l'assistante…", live: "En direct", stop: "Terminer", min: "Réduire", open: "Ouvrir", mic: "Micro", cam: "Caméra", camOn: "Caméra active", camDenied: "Accès à la caméra refusé par le navigateur.",
  camConsent: "Activer la caméra ?\n\nL'assistante voit l'image pour comprendre l'environnement (pièce, chantier, plan montré à la caméra).\nElle n'identifie personne par le visage et n'enregistre aucune image.\nVous pouvez la couper à tout moment.",
  noagent: "L'assistante ne répond pas : l'agent est-il en ligne (LiveKit Cloud) ?", micDenied: "Micro bloqué : autorisez le micro pour ce site dans les réglages du navigateur.", sound: "Cliquez n'importe où pour activer le son de l'assistante.", micDead: "Le micro n'envoyait plus de son — il a été rallumé automatiquement.", ended: "Conversation terminée.",
  busy: "L'assistante est déjà utilisée par un autre admin. Réessayez dans quelques minutes.", quota: "Quota Synthesia épuisé pour ce mois.",
  config: "Problème de configuration de l'avatar (clé Synthesia ou LiveKit). ", error: "L'assistante n'a pas pu démarrer, réessayez.",
  hush: "Silence (ou dites « tais-toi »)", listening: "À l'écoute", thinking: "Réfléchit…", speaking: "Parle", acting: "Agit à l'écran", you: "Vous",
};

// ------------------------------------------------------------------ petit magasin partagé (panneau admin ↔ fenêtre flottante)
// Lot 105 : taille de la fenêtre de l'avatar (S → scène) et mode présentatrice
const SIZES = ["S", "M", "L", "XL", "stage"];
const loadSize = () => { try { const v = window.localStorage.getItem("cp_avatar_size"); return SIZES.includes(v) ? v : "M"; } catch { return "M"; } };
const dockW = (sz) => {
  const vw = typeof window !== "undefined" ? window.innerWidth : 1280;
  const vh = typeof window !== "undefined" ? window.innerHeight : 800;
  const w = { S: 160, M: 230, L: 340, XL: 480, stage: Math.min(vw * 0.5, (vh - 140) / 1.26) }[sz] || 230;
  return Math.round(Math.max(120, Math.min(w, vw - 24, (vh - 90) / 1.26)));
};
const dockPos = (sz, pos) => (sz === "stage" && typeof window !== "undefined"
  ? { right: Math.max(4, Math.round((window.innerWidth - dockW(sz)) / 2)), bottom: 24 } : { right: pos.right, bottom: pos.bottom });
const listeners = new Set();
let state = { phase: "idle", message: "", lang: "fr", micOn: true, camOn: false, size: loadSize(), presenter: false, ptt: false,   // Lot 104 : caméra éteinte par défaut
              caption: null, agentState: null, acting: 0 };
const set = (patch) => { state = { ...state, ...patch }; listeners.forEach((l) => l(state)); };
export const avatarStore = { get: () => state, subscribe: (l) => { listeners.add(l); return () => listeners.delete(l); } };

let room = null;
let timer = null;
let videoEl = null;
let roomName = null;

// Libère la salle côté serveur (créneau Synthesia unique) : fermeture d'onglet ou « Terminer ».
function releaseRoom() {
  const rn = roomName;
  if (!rn) return;
  roomName = null;
  try {
    const url = `${API}/admin/avatar/release`;
    const body = JSON.stringify({ room: rn });
    if (navigator.sendBeacon) navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
    else fetch(url, { method: "POST", credentials: "include", keepalive: true,
                      headers: { "Content-Type": "application/json" }, body });
  } catch { /* ignoré */ }
}
if (typeof window !== "undefined") {
  window.addEventListener("pagehide", releaseRoom);
  window.addEventListener("beforeunload", releaseRoom);
}

// ------------------------------------------------------------------ pilotage visible de l'écran
const SEL = 'a[href],button,input:not([type=hidden]),textarea,select,[role=button],[role=tab],[role=menuitem],[role=option],[role=combobox],[role=checkbox],[role=switch],[contenteditable=true]';
const FORBID = /\b(pagar|pagamento|payer|paiement|payment|checkout|stripe|cart[aã]o|carte bancaire|eliminar definitivamente|supprimer d[ée]finitivement|esvaziar|vider la corbeille|palavra-passe|mot de passe|password)/i;
// Autonomie (demande du fondateur, 31/10) : l'assistante agit seule ; seules les actions irréversibles ou qui partent
// vers l'extérieur (suppression, envoi d'e-mail / de facture / signature, émission, publication) demandent un « oui ».
const CONFIRM = /(apagar|eliminar|supprimer|delete|remover|enviar (?:o |a )?(?:e-?mail|fatura|orçamento|ao cliente)|envoyer (?:l['’]|le |la |au |par )?(?:e-?mail|mail|facture|devis|client)|send (?:e-?mail|invoice)|emitir|[ée]mettre|publicar|publier|signer|assinar|desativar|d[ée]sactiver|bloquear|bloquer|r[ée]voquer|revogar)/i;
const NO_CONFIRM_TESTIDS = new Set(["assistant-send-btn", "choice-submit-btn", "choice-defaults-btn"]);
// Identifiants, libellés et recherche d'éléments partagés avec l'écran en direct (avatarDom.js) : l'agent clique
// directement sur les ids envoyés en direct, ou sur le texte visible d'un bouton.
function snapshot() {
  const items = elements({ limit: 160 }).map(describe);
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
// résultat d'action + nouvel écran (court) : l'agent enchaîne sans relire la page
function withScreen(o) {
  const b = brief();
  let out = JSON.stringify({ ok: true, ...o, screen: b });
  while (out.length > 13500 && b.elements.length > 10) { b.elements = b.elements.slice(0, b.elements.length - 8); out = JSON.stringify({ ok: true, ...o, screen: b }); }
  return out;
}
const find = (ref, o) => findTarget(ref, o);

// Pointeur : rapide et non bloquant (avant ~1 s par geste). soft = l'assistante parle de l'élément (contour léger, pas de clic).
let cursor = null;
function pointTo(el, { soft = false } = {}) {
  return new Promise((resolve) => {
    if (!cursor) {
      cursor = document.createElement("div");
      cursor.id = "cp-avatar-cursor";
      cursor.style.cssText = "position:fixed;z-index:2147483646;width:26px;height:26px;pointer-events:none;transition:left .22s ease-out,top .22s ease-out,opacity .2s;left:50vw;top:50vh;opacity:0";
      cursor.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l16 9-7 2-3 7z" fill="#c8763a" stroke="#fff" stroke-width="1.5"/></svg>';
      document.body.appendChild(cursor);
    }
    const r0 = el.getBoundingClientRect();
    const off = r0.top < 60 || r0.bottom > window.innerHeight - 40;
    if (off) el.scrollIntoView({ behavior: soft ? "smooth" : "auto", block: "center", inline: "nearest" });
    requestAnimationFrame(() => {
      const r = el.getBoundingClientRect();
      cursor.style.opacity = "1";
      cursor.style.left = `${r.left + Math.min(r.width / 2, 40)}px`;
      cursor.style.top = `${r.top + r.height / 2}px`;
      const prevO = el.style.outline, prevOff = el.style.outlineOffset, prevT = el.style.transition, prevB = el.style.boxShadow;
      el.style.transition = "box-shadow .2s";
      el.style.outline = soft ? "2px solid rgba(200,118,58,.85)" : "3px solid #c8763a";
      el.style.outlineOffset = "2px";
      if (soft) el.style.boxShadow = "0 0 0 6px rgba(200,118,58,.18)";
      setTimeout(() => { el.style.outline = prevO; el.style.outlineOffset = prevOff; el.style.boxShadow = prevB; el.style.transition = prevT; },
                 soft ? 1600 : 700);
      setTimeout(resolve, soft ? 0 : 230);   // le clic part dès que le pointeur est arrivé
    });
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
// Attend que la page se stabilise (plus aucune mutation pendant quiet ms), au plus max ms : rapide quand la page l'est.
function settleSmart(max = 1500, quiet = 220) {
  return new Promise((resolve) => {
    let t = null;
    const done = () => { obs.disconnect(); clearTimeout(t); clearTimeout(hard); resolve(); };
    const obs = new MutationObserver(() => { clearTimeout(t); t = setTimeout(done, quiet); });
    obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    t = setTimeout(done, quiet);
    const hard = setTimeout(done, max);
  });
}

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

// Lot 107 : « appuyer pour parler » (stand / scène bruyants) — micro coupé sauf pendant l'appui (bouton ou barre d'espace)
let pttKeys = null;
async function micOn(on) {
  if (!room) return;
  try { await room.localParticipant.setMicrophoneEnabled(on); set({ micOn: on }); } catch { set({ micOn: false, message: T.micDenied }); }
}
export async function setPushToTalk(on) {
  set({ ptt: on });
  if (pttKeys) { window.removeEventListener("keydown", pttKeys.down); window.removeEventListener("keyup", pttKeys.up); pttKeys = null; }
  if (on) {
    const busy = () => ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    pttKeys = {
      down: (e) => { if (e.code === "Space" && !e.repeat && !busy()) { e.preventDefault(); micOn(true); } },
      up: (e) => { if (e.code === "Space" && !busy()) { e.preventDefault(); micOn(false); } },
    };
    window.addEventListener("keydown", pttKeys.down);
    window.addEventListener("keyup", pttKeys.up);
  }
  await micOn(!on);
}
export const pttPress = (down) => { if (state.ptt) micOn(down); };

export function setAvatarSize(size) {   // Lot 105
  if (!SIZES.includes(size)) return;
  set({ size });
  try { window.localStorage.setItem("cp_avatar_size", size); } catch { /* navigation privée */ }
}
export function resizeAvatar(step) {
  const i = Math.max(0, SIZES.indexOf(state.size));
  setAvatarSize(SIZES[Math.max(0, Math.min(SIZES.length - 1, i + step))]);
}
export async function togglePresenter(force) {
  const on = typeof force === "boolean" ? force : !state.presenter;
  set({ presenter: on });
  try {
    await room?.localParticipant.publishData(new TextEncoder().encode(JSON.stringify({ type: "presenter", on })), { reliable: true, topic: "avatar_ctrl" });
  } catch { /* salle fermée */ }
}

const HANDLERS = {
  "ui.avatar_size": async (d) => {   // Lot 105
    const v = String(parse(d).size || "").trim().toLowerCase();
    const i = Math.max(0, SIZES.indexOf(state.size));
    const next = ["bigger", "+", "plus"].includes(v) ? SIZES[Math.min(SIZES.length - 1, i + 1)]
      : ["smaller", "-", "moins", "menos"].includes(v) ? SIZES[Math.max(0, i - 1)] : SIZES.find((x) => x.toLowerCase() === v);
    if (!next) return ko("taille inconnue (S, M, L, XL, stage, bigger, smaller)");
    setAvatarSize(next);
    return ok({ size: next });
  },
  // « Desligar Aurora » compris par l'agent (toutes formulations) : elle dit au revoir, puis la fenêtre se ferme.
  "ui.close": async (d) => { const ms = Math.max(0, Math.min(4000, Number(parse(d).delay_ms) || 1200)); setTimeout(() => { stopAvatar(); }, ms); return ok({ closing: true }); },
  "ui.presenter": async (d) => { set({ presenter: !!parse(d).on }); return ok({ presenter: state.presenter }); },
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
  "ui.navigate": async (d) => res(await act.navigate(parse(d).path)),
  "ui.back": async () => res(await act.back()),
  "ui.scroll": async (d) => res(await act.scroll(parse(d).direction)),
  "ui.click": async (d) => { const { id, confirmed } = parse(d); return res(await act.click(id, confirmed)); },
  "ui.type": async (d) => { const { id, text, submit } = parse(d); return res(await act.type(id, text, submit)); },
  "ui.point": async (d) => res(await act.point(parse(d).id), false),
  // Plusieurs gestes en un seul appel : l'agent ne fait plus un aller-retour (et une réflexion) par clic.
  "ui.do": async (d) => {
    const steps = Array.isArray(parse(d).steps) ? parse(d).steps.slice(0, 12) : [];
    if (!steps.length) return ko("aucune étape");
    const done = [];
    for (const st of steps) {
      let r;
      if (!st || typeof st !== "object") continue;
      if ("navigate" in st) r = await act.navigate(st.navigate);
      else if ("click" in st) r = await act.click(st.click, !!st.confirmed);
      else if ("type" in st) r = await act.type(st.type, st.text, !!st.submit);
      else if ("scroll" in st) r = await act.scroll(st.scroll);
      else if ("back" in st) r = await act.back();
      else if ("point" in st) r = await act.point(st.point);
      else if ("wait" in st) { await settle(Math.max(0, Math.min(5, Number(st.wait) || 0)) * 1000); r = { ok: true }; }
      else continue;
      done.push({ step: st, ok: r.ok, ...(r.ok ? {} : { error: r.error, needs_confirmation: r.needs_confirmation, label: r.label }) });
      if (!r.ok) return withScreen({ ok: false, done, error: r.error });
    }
    return withScreen({ done });
  },
};

// ------------------------------------------------------------------ gestes élémentaires (objets, pas encore sérialisés)
const res = (r, screen = true) => (r.ok ? (screen ? withScreen(r) : JSON.stringify(r)) : JSON.stringify(r));
const act = {
  async navigate(path) {
    const p = String(path || "");
    if (!p.startsWith("/") || p.startsWith("//")) return { ok: false, error: "chemin invalide (commencer par /)" };
    if (window.location.pathname + window.location.search === p || window.location.pathname === p)
      return { ok: true, path: p, note: "page déjà ouverte" };
    window.history.pushState({}, "", p);
    window.dispatchEvent(new PopStateEvent("popstate"));
    await settleSmart(1600, 260);
    pushScreenNow();
    return { ok: true, path: window.location.pathname };
  },
  async back() { window.history.back(); await settleSmart(1400, 260); pushScreenNow(); return { ok: true, path: window.location.pathname }; },
  async scroll(direction) {
    const dir = direction === "up" ? -1 : 1;
    window.scrollBy({ top: dir * window.innerHeight * 0.8, behavior: "smooth" });
    await settle(380);
    return { ok: true };
  },
  async click(ref, confirmed) {
    const el = find(String(ref || ""));
    if (!el) return { ok: false, error: `élément « ${String(ref).slice(0, 60)} » introuvable : regarder l'écran en direct ou ui_read` };
    const label = labelOf(el);
    if (FORBID.test(label)) return { ok: false, error: "action interdite à l'assistante (paiement, mot de passe ou suppression définitive) : à faire à la main", label };
    if (CONFIRM.test(label) && !NO_CONFIRM_TESTIDS.has(el.getAttribute("data-testid")) && !confirmed)
      return { ok: false, error: "confirmation requise", needs_confirmation: true, label };
    await pointTo(el);
    el.click();
    await settleSmart(1200, 200);
    pushScreenNow();
    return { ok: true, clicked: label, path: window.location.pathname };
  },
  async type(ref, text, submit) {
    const el = find(String(ref || ""), { fields: true }) || find(String(ref || ""));
    if (!el) return { ok: false, error: `champ « ${String(ref).slice(0, 60)} » introuvable` };
    if (el.type === "password" || FORBID.test(labelOf(el))) return { ok: false, error: "champ interdit à l'assistante" };
    await pointTo(el);
    el.focus();
    if (el.isContentEditable) { document.execCommand("selectAll"); document.execCommand("insertText", false, String(text ?? "")); }
    else setNativeValue(el, String(text ?? ""));
    if (submit) {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
      await settleSmart(1000, 200);
    } else await settle(120);
    return { ok: true, typed: labelOf(el) };
  },
  async point(ref) {
    const el = find(String(ref || ""));
    if (!el) return { ok: false, error: "élément introuvable" };
    pointTo(el, { soft: true });
    return { ok: true, pointed: labelOf(el) };
  },
};

// ------------------------------------------------------------------ session
function reset(message = "") {
  clearInterval(micWatch);
  setPushToTalk(false);   // Lot 107
  stopScreenWatch();
  stopSpeechSync();
  clearTimeout(timer);
  room = null;
  roomName = null;
  videoEl = null;
  cursor?.remove(); cursor = null;
  clearTimeout(hushTimer);
  set({ phase: "idle", message, caption: null, agentState: null, acting: 0, hushed: false, micLevel: 0 });
}
// Préchargement du client LiveKit dès que le panneau admin s'affiche : « Parler » démarre sans attendre le téléchargement.
let lkModule = null;
export const preloadAvatar = () => { lkModule = lkModule || import("livekit-client"); return lkModule; };

export async function startAvatar(lang = "fr") {
  set({ camOn: false });   // Lot 104
  setCameraOn(false);
  if (room) return;
  set({ phase: "connecting", message: "", lang, micOn: true });
  try {
    const [{ data }, { Room, RoomEvent }] = await Promise.all([api.get("/admin/avatar/token", { params: { lang } }), preloadAvatar()]);
    roomName = data.room;
    const r = new Room({ audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },   // Lot 107 : micro propre dans le bruit
       adaptiveStream: false });
    room = r;
    let notice = null;
    r.on(RoomEvent.TrackSubscribed, (track) => {
      if (!videoEl) { videoEl = document.createElement("video"); videoEl.playsInline = true; videoEl.autoplay = true; }
      track.attach(videoEl);
      if (track.kind === "audio" && !state.hushed) { videoEl.muted = false; videoEl.play?.().catch(() => set({ message: T.sound })); }
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
    Object.entries(HANDLERS).forEach(([name, fn]) => r.registerRpcMethod(name, async (d) => {
      markAgentAction();
      if (name !== "ui.read" && name !== "assistant.status") set({ acting: state.acting + 1 });
      try { return await fn(d); } finally {
        markAgentAction();
        if (name !== "ui.read" && name !== "assistant.status") set({ acting: Math.max(0, state.acting - 1) });
      }
    }));
    // sous-titres, état de l'assistante, l'écran qui suit ses mots, navigation vocale instantanée
    startSpeechSync(r, {
      onHush: () => hush(false),
      onOff: () => { hush(false); setTimeout(() => { stopAvatar(); }, 250); },   // « desligar Aurora » : fermeture immédiate
      onSpeak: () => unhush(),
      onCaption: (c) => set({ caption: c }),
      onState: (st) => {
        set({ agentState: st });
        if (st === "listening") setTimeout(() => { if (state.agentState === "listening" && state.caption?.who === "agent") set({ caption: null }); }, 5000);
      },
      point: (el, o) => pointTo(el, o),
      isAgentActing: agentActing,
      markAgentAction,
    });
    // Som da assistente: o navegador pode bloquear o áudio que chega depois do clique (política de autoplay) — a cara
    // aparece mas não se ouve nada. Desbloqueia-se já e, se ainda bloqueado, no próximo clique em qualquer sítio (12/11).
    const unlockAudio = () => { try { r.startAudio(); } catch { /* */ } if (videoEl && !state.hushed) { videoEl.muted = false; videoEl.play?.().catch(() => {}); } };
    r.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      if (r.canPlaybackAudio) { if (state.message === T.sound) set({ message: "" }); return; }
      set({ message: T.sound });
      document.addEventListener("pointerdown", unlockAudio, { once: true, capture: true });
    });
    await r.connect(data.url, data.token);
    unlockAudio();
    startScreenWatch(r);
    try { await r.localParticipant.setMicrophoneEnabled(true); }
    catch (e) { const err = new Error(T.micDenied); err.cause = e; throw err; }
    startMicWatch(r);
    if (state.phase !== "live") set({ phase: "waiting" });
    timer = setTimeout(() => { if (state.phase !== "live") set({ message: T.noagent }); }, 60000);
  } catch (e) {
    room?.disconnect();
    reset(e?.response?.data?.detail || e?.message || T.error);
  }
}
export async function stopAvatar() { releaseRoom(); await room?.disconnect(); reset(T.ended); }
// Lot 104 : caméra sur demande, consentement explicite à chaque session, jamais allumée en silence
async function toggleCam() {
  if (!room) return;
  const on = !state.camOn;
  if (on && !window.confirm(T.camConsent)) return;
  try {
    await room.localParticipant.setCameraEnabled(on, on ? { resolution: { width: 640, height: 480, frameRate: 10 } } : undefined);
    set({ camOn: on });
    setCameraOn(on);   // l'assistante sait tout de suite que la caméra est allumée (ou éteinte)
  } catch {
    set({ camOn: false, message: T.camDenied });
    setCameraOn(false);
  }
}
// « Cala-te » (voix ou bouton) : le son est coupé ici tout de suite, et l'agent arrête de parler et se tait (topic « avatar »).
// Le son revient quand l'admin lui reparle, ou dès qu'elle a fini de se taire (au plus tard 4 s après).
let hushTimer = null;
function hush(fromButton = true) {
  if (videoEl) videoEl.muted = true;
  set({ caption: null, hushed: true });
  try { room?.localParticipant?.publishData(new TextEncoder().encode(JSON.stringify({ type: "hush", from: fromButton ? "button" : "voice" })),
                                            { reliable: true, topic: "avatar" }); } catch { /* salle fermée */ }
  clearTimeout(hushTimer);
  const t0 = Date.now();
  const check = () => {
    if (!state.hushed) return;
    if (Date.now() - t0 > 4000 && state.agentState !== "speaking") return unhush();
    hushTimer = setTimeout(check, 300);
  };
  hushTimer = setTimeout(check, 600);
}
function unhush() {
  clearTimeout(hushTimer);
  if (videoEl) videoEl.muted = false;
  if (state.hushed) set({ hushed: false });
}
export const hushAvatar = () => hush(true);

async function toggleMic() {
  if (!room) return;
  const on = !state.micOn;
  try { await room.localParticipant.setMicrophoneEnabled(on); set({ micOn: on, message: "" }); }
  catch { set({ micOn: false, message: T.micDenied }); }
}

// Surveillance du micro : niveau sonore affiché (l'admin voit que sa voix part) et relance automatique si le
// navigateur coupe la piste (iPad/Safari : interruption audio, changement de casque, onglet mis en veille…).
let micWatch = null;
function startMicWatch(r) {
  clearInterval(micWatch);
  let silentTicks = 0;
  micWatch = setInterval(async () => {
    if (room !== r) { clearInterval(micWatch); return; }
    const lp = r.localParticipant;
    const level = Math.min(1, (lp?.audioLevel || 0) * 4);
    if (Math.abs((state.micLevel || 0) - level) > 0.05) set({ micLevel: level });
    if (!state.micOn || state.ptt) { silentTicks = 0; return; }
    const pub = [...(lp?.audioTrackPublications?.values?.() || [])][0];
    const mst = pub?.track?.mediaStreamTrack;
    const dead = !pub || !mst || mst.readyState === "ended" || pub.isMuted;
    silentTicks = dead ? silentTicks + 1 : 0;
    if (silentTicks >= 2) {   // ~2 s sans piste valide : on relance le micro
      silentTicks = 0;
      try {
        await lp.setMicrophoneEnabled(false);
        await lp.setMicrophoneEnabled(true);
        set({ message: T.micDead });
        setTimeout(() => { if (state.message === T.micDead) set({ message: "" }); }, 6000);
      } catch { set({ micOn: false, message: T.micDenied }); }
    }
  }, 1000);
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
      style={{ position: "fixed", ...dockPos(s.size, pos), zIndex: 2147483645, width: min ? 64 : dockW(s.size),
               borderRadius: 16, overflow: "hidden", boxShadow: "0 12px 32px rgba(0,0,0,.35)", background: "#14532d",
               border: "2px solid #c8763a", fontFamily: "inherit" }}>
      <div onPointerDown={onDown} onPointerMove={onMove} onPointerUp={() => { drag.current = null; }}
        style={{ cursor: "move", height: min ? 64 : Math.round(dockW(s.size) * 1.26), position: "relative" }}>
        <div ref={holder} style={{ width: "100%", height: "100%", background: "transparent" }} />
        {s.camOn && (
          <div data-testid="avatar-cam-on" style={{ position: "absolute", top: 6, left: 6, zIndex: 3, background: "#b42318", color: "#fff", fontSize: 10,
                        fontWeight: 700, padding: "2px 6px", borderRadius: 6 }}>● {T.camOn}</div>)}
        {s.phase !== "live" && !min && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#f5efe3",
                        fontSize: 12, textAlign: "center", padding: 12 }}>{s.message || T.waiting}</div>)}
        {s.phase === "live" && !min && s.caption?.text && (
          <div data-testid="avatar-caption" aria-live="polite"
            style={{ position: "absolute", left: 6, right: 6, bottom: 6, padding: "5px 8px", borderRadius: 10, fontSize: 12, lineHeight: 1.35,
                     color: "#fff", background: s.caption.who === "admin" ? "rgba(40,85,65,.82)" : "rgba(20,20,20,.62)",
                     maxHeight: 74, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 4, WebkitBoxOrient: "vertical" }}>
            {s.caption.who === "admin" ? <b>{T.you} : </b> : null}{s.caption.text}
          </div>)}
      </div>
      {!min && (
        <div style={{ display: "flex", gap: 6, padding: 6, alignItems: "center", background: "#14532d" }}>
          <span data-testid="avatar-state" style={{ color: "#f5efe3", fontSize: 11, flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {s.phase !== "live" ? "…" : s.acting > 0 ? `⚙ ${T.acting}` : s.agentState === "thinking" ? `💭 ${T.thinking}`
              : s.agentState === "speaking" ? `● ${T.speaking}` : s.agentState === "listening" ? `👂 ${T.listening}` : `● ${T.live}`}
          </span>
          <button type="button" data-testid="avatar-hush" style={{ ...btn, background: s.hushed ? "#c8763a" : "#285541" }} onClick={() => hush(true)}
            title={T.hush} aria-label={T.hush}>🤫</button>
          <button type="button" data-testid="avatar-dock-mic" style={{ ...btn, background: s.micOn ? "#285541" : "#7a2e2e", position: "relative", overflow: "hidden" }} onClick={toggleMic} title={T.mic}>
            {s.micOn && <span aria-hidden="true" style={{ position: "absolute", left: 0, bottom: 0, width: "100%", height: `${Math.round((s.micLevel || 0) * 100)}%`, background: "rgba(140,230,170,.55)", transition: "height .15s" }} />}
            <span style={{ position: "relative" }}>{s.micOn ? "🎙" : "🔇"}</span></button>
          <button type="button" style={{ ...btn, background: s.camOn ? "#b42318" : "#285541" }} onClick={toggleCam} title={T.cam}
            data-testid="avatar-dock-cam" aria-pressed={s.camOn}>📷</button>
          <button type="button" style={{ ...btn, background: s.ptt ? "#c8763a" : "#285541" }} onClick={() => setPushToTalk(!s.ptt)}
            data-testid="avatar-dock-ptt" aria-pressed={!!s.ptt} title={state.lang === "fr" ? "Appuyer pour parler (barre d'espace)" : "Premir para falar (barra de espaço)"}>✋</button>
          {s.ptt && <button type="button" style={{ ...btn, background: s.micOn ? "#b42318" : "#7a2e2e", userSelect: "none", touchAction: "none" }}
            onPointerDown={() => pttPress(true)} onPointerUp={() => pttPress(false)} onPointerLeave={() => pttPress(false)} onPointerCancel={() => pttPress(false)}
            data-testid="avatar-dock-ptt-hold">{state.lang === "fr" ? "Maintenir" : "Manter"}</button>}
          <button type="button" style={{ ...btn, background: "#285541" }} onClick={() => resizeAvatar(-1)} data-testid="avatar-dock-smaller"
            title={state.lang === "fr" ? "Réduire la fenêtre" : "Diminuir a janela"}>−</button>
          <button type="button" style={{ ...btn, background: "#285541" }} onClick={() => resizeAvatar(1)} data-testid="avatar-dock-bigger"
            title={state.lang === "fr" ? "Agrandir la fenêtre" : "Aumentar a janela"}>+</button>
          <button type="button" style={{ ...btn, background: s.presenter ? "#c8763a" : "#285541" }} onClick={() => togglePresenter()}
            data-testid="avatar-dock-presenter" aria-pressed={!!s.presenter} title={state.lang === "fr" ? "Mode présentatrice" : "Modo apresentadora"}>🎤</button>
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
