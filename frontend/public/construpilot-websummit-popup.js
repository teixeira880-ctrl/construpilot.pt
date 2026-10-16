/*!
 * ConstruPilot — Pop-up publicitário Web Summit 2026
 * Funciona em construpilot.pt (português) e construpilot.fr (francês).
 */
(function () {
  "use strict";
  var CONFIG = {
    endDate: "2026-11-13T00:00:00",
    delayMs: 1200,
    storageKey: "cp_websummit_2026_seen",
    colors: { primary: "#F97316", dark: "#0F172A", accentPT: "#046A38", accentFR: "#1E3A8A" },
    texts: {
      pt: {
        badge: "WEB SUMMIT 2026 · LISBOA",
        title: "Bem-vindos ao ConstruPilot",
        subtitle: "A plataforma de IA para a construção chega ao Web Summit!",
        body: "Venha assistir à demonstração ao vivo do ConstruPilot: leitura automática de plantas, medições, orçamentação e o Assistente de Obra com inteligência artificial.",
        when: "📅 9 a 12 de novembro de 2026",
        where: "📍 MEO Arena & FIL — Lisboa",
        cta: "Marcar uma demonstração",
        ctaHref: "mailto:info@construpilot.pt?subject=Demonstra%C3%A7%C3%A3o%20ConstruPilot%20-%20Web%20Summit%202026",
        secondary: "Explorar a plataforma",
        close: "Fechar"
      },
      fr: {
        badge: "WEB SUMMIT 2026 · LISBONNE",
        title: "Bienvenue sur ConstruPilot",
        subtitle: "La plateforme IA du bâtiment s'invite au Web Summit !",
        body: "Venez assister à la démonstration en direct de ConstruPilot : lecture automatique de plans, métrés, chiffrage et l'Assistant BTP propulsé par l'intelligence artificielle.",
        when: "📅 Du 9 au 12 novembre 2026",
        where: "📍 MEO Arena & FIL — Lisbonne",
        cta: "Réserver une démonstration",
        ctaHref: "mailto:info@construpilot.fr?subject=D%C3%A9monstration%20ConstruPilot%20-%20Web%20Summit%202026",
        secondary: "Découvrir la plateforme",
        close: "Fermer"
      }
    }
  };
  if (new Date() >= new Date(CONFIG.endDate)) return;
  function detectLang() {
    var host = (location.hostname || "").toLowerCase();
    if (/\.pt$/.test(host)) return "pt";
    if (/\.fr$/.test(host)) return "fr";
    var htmlLang = (document.documentElement.lang || navigator.language || "").toLowerCase();
    return htmlLang.indexOf("pt") === 0 ? "pt" : "fr";
  }
  function alreadySeen() { try { return sessionStorage.getItem(CONFIG.storageKey) === "1"; } catch (e) { return false; } }
  function markSeen() { try { sessionStorage.setItem(CONFIG.storageKey, "1"); } catch (e) {} }
  if (alreadySeen()) return;
  var lang = detectLang();
  var t = CONFIG.texts[lang];
  var accent = lang === "pt" ? CONFIG.colors.accentPT : CONFIG.colors.accentFR;
  var c = CONFIG.colors;
  var css =
    "#cp-ws-overlay{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;padding:16px;" +
    "background:rgba(15,23,42,.6);backdrop-filter:blur(4px);opacity:0;transition:opacity .35s ease;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}" +
    "#cp-ws-overlay.cp-show{opacity:1}" +
    "#cp-ws-modal{position:relative;width:100%;max-width:480px;background:#fff;border-radius:20px;overflow:hidden;" +
    "box-shadow:0 25px 60px rgba(0,0,0,.35);transform:translateY(24px) scale(.97);transition:transform .4s cubic-bezier(.2,.9,.3,1.2)}" +
    "#cp-ws-overlay.cp-show #cp-ws-modal{transform:none}" +
    "#cp-ws-head{background:linear-gradient(135deg," + c.dark + " 0%," + accent + " 100%);color:#fff;padding:28px 24px 22px;position:relative}" +
    "#cp-ws-head:after{content:'';position:absolute;left:0;right:0;bottom:0;height:4px;background:" + c.primary + "}" +
    "#cp-ws-badge{display:inline-block;background:" + c.primary + ";color:#fff;font-size:11px;font-weight:800;letter-spacing:.08em;" +
    "padding:5px 10px;border-radius:999px;margin-bottom:14px;animation:cpPulse 2s infinite}" +
    "@keyframes cpPulse{0%,100%{box-shadow:0 0 0 0 rgba(249,115,22,.6)}50%{box-shadow:0 0 0 8px rgba(249,115,22,0)}}" +
    "#cp-ws-title{margin:0 0 6px;font-size:26px;line-height:1.15;font-weight:800}" +
    "#cp-ws-sub{margin:0;font-size:15px;opacity:.9}" +
    "#cp-ws-body{padding:22px 24px 24px;color:#334155;font-size:15px;line-height:1.55}" +
    "#cp-ws-body p{margin:0 0 16px}" +
    ".cp-ws-info{display:flex;flex-direction:column;gap:6px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:12px 14px;margin-bottom:20px;font-weight:600;color:" + c.dark + "}" +
    ".cp-ws-btns{display:flex;flex-wrap:wrap;gap:10px}" +
    ".cp-ws-btn{flex:1 1 180px;text-align:center;text-decoration:none;font-weight:700;font-size:15px;padding:13px 16px;border-radius:12px;cursor:pointer;border:0;transition:transform .15s,filter .15s}" +
    ".cp-ws-btn:hover{transform:translateY(-1px);filter:brightness(1.05)}" +
    ".cp-ws-primary{background:" + c.primary + ";color:#fff}" +
    ".cp-ws-secondary{background:#fff;color:" + c.dark + ";border:2px solid #E2E8F0}" +
    "#cp-ws-close{position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:50%;border:0;cursor:pointer;" +
    "background:rgba(255,255,255,.15);color:#fff;font-size:20px;line-height:34px;z-index:2}" +
    "#cp-ws-close:hover{background:rgba(255,255,255,.3)}" +
    "@media (max-width:420px){#cp-ws-title{font-size:22px}#cp-ws-head{padding:24px 18px 18px}#cp-ws-body{padding:18px}}" +
    "@media (prefers-reduced-motion:reduce){#cp-ws-overlay,#cp-ws-modal{transition:none}#cp-ws-badge{animation:none}}";
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text) n.textContent = text;
    return n;
  }
  function build() {
    var style = el("style", { id: "cp-ws-style" });
    style.textContent = css;
    document.head.appendChild(style);
    var overlay = el("div", { id: "cp-ws-overlay", role: "dialog", "aria-modal": "true", "aria-labelledby": "cp-ws-title", lang: lang });
    var modal = el("div", { id: "cp-ws-modal" });
    var closeBtn = el("button", { id: "cp-ws-close", type: "button", "aria-label": t.close }, "×");
    var head = el("div", { id: "cp-ws-head" });
    head.appendChild(el("span", { id: "cp-ws-badge" }, t.badge));
    head.appendChild(el("h2", { id: "cp-ws-title" }, t.title));
    head.appendChild(el("p", { id: "cp-ws-sub" }, t.subtitle));
    var body = el("div", { id: "cp-ws-body" });
    body.appendChild(el("p", {}, t.body));
    var info = el("div", { "class": "cp-ws-info" });
    info.appendChild(el("span", {}, t.when));
    info.appendChild(el("span", {}, t.where));
    body.appendChild(info);
    var btns = el("div", { "class": "cp-ws-btns" });
    var cta = el("a", { "class": "cp-ws-btn cp-ws-primary", href: t.ctaHref }, t.cta);
    var sec = el("button", { "class": "cp-ws-btn cp-ws-secondary", type: "button" }, t.secondary);
    btns.appendChild(cta);
    btns.appendChild(sec);
    body.appendChild(btns);
    modal.appendChild(closeBtn);
    modal.appendChild(head);
    modal.appendChild(body);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    var lastFocus = document.activeElement;
    requestAnimationFrame(function () { overlay.classList.add("cp-show"); cta.focus(); });
    markSeen();
    function close() {
      overlay.classList.remove("cp-show");
      document.removeEventListener("keydown", onKey);
      setTimeout(function () {
        overlay.remove(); style.remove();
        if (lastFocus && lastFocus.focus) lastFocus.focus();
      }, 350);
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    closeBtn.addEventListener("click", close);
    sec.addEventListener("click", close);
    cta.addEventListener("click", function () { setTimeout(close, 100); });
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.addEventListener("keydown", onKey);
  }
  function start() { setTimeout(build, CONFIG.delayMs); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
