// Outils DOM partagés par l'assistante vidéo (AvatarDock, écran en direct, synchro parole/écran).
// Un même identifiant stable (e1, e2…) par élément, pour que l'écran envoyé en direct et les actions de l'agent
// parlent des mêmes boutons : l'agent clique sans relire la page. Il peut aussi viser un élément par son texte visible.
export const SEL = 'a[href],button,input:not([type=hidden]),textarea,select,[role=button],[role=tab],[role=menuitem],[role=option],[role=combobox],[role=checkbox],[role=switch],[contenteditable=true]';

const ids = new WeakMap();
let seq = 0;

// innerText (rendu) si disponible, sinon textContent
export const txt = (el) => (el ? (el.innerText ?? el.textContent ?? "") : "");
export const inDock = (el) => !!el?.closest?.("#cp-avatar-dock, #cp-avatar-cursor, #cp-avatar-dock-root");
export const clean = (s, n = 200) => String(s || "").replace(/\s+/g, " ").trim().slice(0, n);
// minuscules sans accents ni ponctuation : « Créer un devis » == « creer un devis »
export const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
  .replace(/[^a-z0-9€%]+/g, " ").trim();

export function labelOf(el) {
  const aria = el.getAttribute("aria-label") || el.getAttribute("title");
  if (aria) return clean(aria, 80);
  if (el.id) {
    const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (l && txt(l).trim()) return clean(txt(l), 80);
  }
  const t = clean(txt(el) || (el.tagName === "INPUT" && /button|submit/.test(el.type) ? el.value : ""), 60);
  if (t) return t;
  return clean(el.getAttribute("placeholder") || el.getAttribute("name") || el.getAttribute("data-testid") || el.tagName.toLowerCase(), 80);
}

export function visible(el) {
  if (!el || inDock(el)) return false;
  const r = el.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return false;
  const s = getComputedStyle(el);
  return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05 && !el.disabled;
}

export const inViewport = (el) => {
  const r = el.getBoundingClientRect();
  return r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth;
};

export function aiId(el) {
  if (!ids.has(el)) ids.set(el, `e${++seq}`);
  const id = ids.get(el);
  if (el.getAttribute("data-cp-ai") !== id) el.setAttribute("data-cp-ai", id);
  return id;
}

export function describe(el) {
  const role = el.getAttribute("role") || (el.tagName === "A" ? "link" : el.tagName === "INPUT" ? `input:${el.type || "text"}` : el.tagName.toLowerCase());
  const legend = el.closest("fieldset")?.querySelector("legend");
  const group = legend ? txt(legend).trim() : "";
  const checked = el.getAttribute("aria-checked") ?? el.getAttribute("aria-selected") ?? (el.type === "checkbox" || el.type === "radio" ? String(el.checked) : null);
  return { id: aiId(el), role, label: labelOf(el), ...(group ? { group: clean(group, 90) } : {}),
           ...(checked != null ? { checked: checked === "true" } : {}), ...(el.tagName === "A" ? { href: el.getAttribute("href") } : {}) };
}

// Éléments actionnables, ceux visibles à l'écran d'abord (puis de haut en bas).
export function elements({ limit = 160, viewportOnly = false } = {}) {
  let els = [...document.querySelectorAll(SEL)].filter(visible);
  if (viewportOnly) els = els.filter(inViewport);
  const vh = window.innerHeight;
  els.sort((a, b) => {
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const ia = ra.bottom > 0 && ra.top < vh ? 0 : 1, ib = rb.bottom > 0 && rb.top < vh ? 0 : 1;
    return ia - ib || ra.top - rb.top || ra.left - rb.left;
  });
  return els.slice(0, limit);
}

// Résumé court de l'écran renvoyé après chaque action : l'agent enchaîne sans ui_read.
export function brief(limit = 45) {
  const main = document.querySelector("main") || document.body;
  return {
    path: window.location.pathname + window.location.search,
    title: clean(document.title, 120),
    headings: [...main.querySelectorAll("h1, h2")].filter(visible).slice(0, 5).map((h) => clean(txt(h), 90)).filter(Boolean),
    elements: elements({ limit, viewportOnly: false }).map(describe).map(({ href, group, ...e }) => e),
  };
}

// Cible par id (e12) ou par texte visible. Priorité : égalité exacte, puis début, puis contenu ; visibles à l'écran d'abord.
export function findTarget(ref, { fields = false } = {}) {
  const raw = String(ref || "").trim();
  if (!raw) return null;
  if (/^e\d+$/.test(raw)) {
    const el = document.querySelector(`[data-cp-ai="${CSS.escape(raw)}"]`);
    if (el) return el;
  }
  const want = norm(raw);
  if (!want) return null;
  let pool = [...document.querySelectorAll(SEL)].filter(visible);
  if (fields) pool = pool.filter((el) => /INPUT|TEXTAREA|SELECT/.test(el.tagName) || el.isContentEditable || el.getAttribute("role") === "combobox");
  const keys = (el) => [labelOf(el), el.getAttribute("placeholder"), el.getAttribute("name"), el.getAttribute("data-testid"), txt(el)]
    .filter(Boolean).map(norm);
  let best = null, score = 0;
  for (const el of pool) {
    for (const k of keys(el)) {
      let s = 0;
      if (k === want) s = 100;
      else if (k.startsWith(want)) s = 70;
      else if (want.length >= 3 && k.includes(want)) s = 50;
      else if (k.length >= 3 && want.includes(k)) s = 30;
      if (!s) continue;
      if (inViewport(el)) s += 5;
      s -= Math.min(10, Math.abs(k.length - want.length) / 10);
      if (s > score) { score = s; best = el; }
    }
  }
  if (!best && !fields) {   // texte simple (titre, total…) : utile pour ui.point
    const walker = document.createTreeWalker(document.querySelector("main") || document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const p = walker.currentNode.parentElement;
      if (p && !inDock(p) && visible(p) && norm(walker.currentNode.nodeValue).includes(want)) { best = p; break; }
    }
  }
  return best;
}
