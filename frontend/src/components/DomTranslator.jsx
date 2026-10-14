import { useEffect } from "react";
import { useI18n } from "@/context/I18nContext";
import PT from "@/i18n/pt_auto.json";
import EN from "@/i18n/en_auto.json";
import FR from "@/i18n/fr_auto.json";

// Tradução automática em três sentidos:
//   • lang="pt" : FR → PT        (via pt_auto.json; sentido original)
//   • lang="en" : PT → EN        (via en_auto.json gerado offline por LLM)
//   • lang="fr" : PT → FR        (via fr_auto.json gerado offline por LLM,
//                                 com fallback no mapa inverso de pt_auto.json)
// O setLang do I18nContext faz window.location.reload() em cada mudança,
// portanto não há necessidade de guardar o texto original — basta aplicar o
// mapa adequado ao idioma ativo e deixar o resto do React tratar o inicial.

const ATTRS = ["placeholder", "title", "aria-label", "alt"];
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "CODE", "PRE", "NOSCRIPT"]);
const norm = (s) => s.replace(/\s+/g, " ").trim();

// Mapa inverso PT→FR a partir de pt_auto.json (resíduo histórico das versões
// anteriores em francês). Serve como fallback para strings que não estejam
// cobertas pelo fr_auto.json gerado especificamente para a landing nova.
const PT_TO_FR_LEGACY = (() => {
  const out = {};
  for (const [fr, pt] of Object.entries(PT)) {
    if (typeof fr !== "string" || typeof pt !== "string") continue;
    const key = norm(pt);
    if (!key || key in out) continue;
    out[key] = fr;
  }
  return out;
})();

const PT_TO_FR = { ...PT_TO_FR_LEGACY, ...FR }; // FR estático sobrepõe-se ao legado
const PT_TO_EN = EN;

const dictFor = (lang) => {
  if (lang === "pt") return PT;      // FR → PT
  if (lang === "en") return PT_TO_EN; // PT → EN
  if (lang === "fr") return PT_TO_FR; // PT → FR
  return null;
};

const buildLookup = (dict) => (raw) => {
  const key = norm(raw);
  if (!key) return null;
  let hit = dict[key];
  if (!hit) {
    const stripped = key.replace(/\s*[:·•→]\s*$/, "");
    const tail = key.slice(stripped.length);
    if (stripped !== key && dict[stripped]) hit = dict[stripped] + tail;
  }
  if (!hit || hit === key) return null;
  const lead = raw.match(/^\s*/)[0];
  const trail = raw.match(/\s*$/)[0];
  return lead + hit + trail;
};

const translateTree = (root, lookup) => {
  const setAttrs = (el) => {
    for (const a of ATTRS) {
      const v = el.getAttribute?.(a);
      if (!v) continue;
      const t = lookup(v);
      if (t && el.getAttribute(a) !== t) el.setAttribute(a, t);
    }
  };
  if (root.nodeType === Node.ELEMENT_NODE) setAttrs(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
    acceptNode: (n) => {
      if (n.nodeType === Node.ELEMENT_NODE) {
        if (SKIP.has(n.tagName)) return NodeFilter.FILTER_REJECT;
        if (n.closest?.("[data-no-translate]")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_SKIP; // visita atributos no fluxo
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let n;
  while ((n = walker.nextNode())) {
    if (n.nodeType === Node.TEXT_NODE) {
      const p = n.parentElement;
      if (!p || SKIP.has(p.tagName) || p.closest("[data-no-translate]")) continue;
      const t = lookup(n.nodeValue);
      if (t && n.nodeValue !== t) n.nodeValue = t;
    } else {
      setAttrs(n);
    }
  }
};

export const DomTranslator = () => {
  const { lang } = useI18n();
  useEffect(() => {
    const dict = dictFor(lang);
    if (!dict) return undefined;
    const lookup = buildLookup(dict);
    const runRoot = () => translateTree(document.body, lookup);
    runRoot();
    // Captura conteúdo tardio (toasts, modais, listas carregadas assíncronas)
    let scheduled = false;
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        runRoot();
      });
    };
    const obs = new MutationObserver(schedule);
    obs.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => obs.disconnect();
  }, [lang]);
  return null;
};
