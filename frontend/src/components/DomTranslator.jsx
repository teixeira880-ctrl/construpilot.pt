import { useEffect } from "react";
import { useI18n } from "@/context/I18nContext";
import PT from "@/i18n/pt_auto.json";

// Traduction automatique FR → PT-PT des libellés non couverts par t() : remplace les nœuds texte
// (et placeholder/title/aria-label) dont le contenu correspond exactement au dictionnaire pt_auto.json.
const ATTRS = ["placeholder", "title", "aria-label", "alt"];
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "CÓDIGO", "PRE", "NOSCRIPT"]);
const norm = (s) => s.replace(/\s+/g, " ").trim();

const lookup = (raw) => {
  const key = norm(raw);
  if (!key) return null;
  let hit = PT[key];
  if (!hit) {
    const stripped = key.replace(/\s*[:·•→]\s*$/, "");
    const tail = key.slice(stripped.length);
    if (stripped !== key && PT[stripped]) hit = PT[stripped] + tail;
  }
  if (!hit || hit === key) return null;
  const lead = raw.match(/^\s*/)[0];
  const trail = raw.match(/\s*$/)[0];
  return lead + hit + trail;
};

const translateNode = (node) => {
  if (node.nodeType === Node.TEXT_NODE) {
    const p = node.parentElement;
    if (!p || SKIP.has(p.tagName) || p.closest("[data-no-translate]")) return;
    if (node.__fr === undefined) node.__fr = node.nodeValue;
    const t = lookup(node.__fr);
    if (t && node.nodeValue !== t) node.nodeValue = t;
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE || SKIP.has(node.tagName)) return;
  for (const a of ATTRS) setAttr(node, a);
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let n;
  while ((n = walker.nextNode())) {
    if (n.nodeType === Node.TEXT_NODE) translateNode(n);
    else for (const a of ATTRS) setAttr(n, a);
  }
};

// Ne restaure que les nœuds encore porteurs de NOTRE traduction (React a déjà réécrit les autres).
const restore = () => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (n.__fr === undefined) continue;
    if (n.nodeValue !== n.__fr && n.nodeValue === lookup(n.__fr)) n.nodeValue = n.__fr;
    n.__fr = undefined;
  }
  document.querySelectorAll("[placeholder],[title],[aria-label],[alt]").forEach((el) => {
    for (const a of ATTRS) {
      const fr = el.__fr_attr?.[a];
      if (fr && el.getAttribute(a) === lookup(fr)) el.setAttribute(a, fr);
    }
    el.__fr_attr = undefined;
  });
};

const setAttr = (el, a) => {
  const v = el.getAttribute?.(a);
  if (!v) return;
  el.__fr_attr = el.__fr_attr || {};
  const fr = el.__fr_attr[a] && el.getAttribute(a) === lookup(el.__fr_attr[a]) ? el.__fr_attr[a] : v;
  const t = lookup(fr);
  if (t) { el.__fr_attr[a] = fr; if (el.getAttribute(a) !== t) el.setAttribute(a, t); }
};

export const DomTranslator = () => {
  const { lang } = useI18n();
  useEffect(() => {
    if (lang !== "pt") { restore(); return undefined; }
    let scheduled = false;
    const run = () => { scheduled = false; translateNode(document.body); };
    run();
    const obs = new MutationObserver((muts) => {
      for (const m of muts) {
        if (m.type === "characterData") {
          const n = m.target;
          if (n.__fr !== undefined && n.nodeValue !== n.__fr && lookup(n.__fr) === n.nodeValue) continue; // notre propre écriture
          n.__fr = n.nodeValue;
        }
      }
      if (!scheduled) { scheduled = true; requestAnimationFrame(run); }
    });
    obs.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => obs.disconnect();
  }, [lang]);
  return null;
};
