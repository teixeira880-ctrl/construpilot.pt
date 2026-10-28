import { useEffect } from "react";
import { useI18n } from "@/context/I18nContext";

// Tradução automática em três sentidos:
//   • lang="pt" : FR → PT        (via pt_auto.json; sentido original)
//   • lang="en" : PT → EN        (via en_auto.json gerado offline por LLM)
//   • lang="fr" : PT → FR        (via fr_auto.json gerado offline por LLM,
//                                 com fallback no mapa inverso de pt_auto.json)
// O setLang do I18nContext faz window.location.reload() em cada mudança,
// portanto não há necessidade de guardar o texto original — basta aplicar o
// mapa adequado ao idioma ativo e deixar o resto do React tratar o inicial.
//
// Desempenho (out. 2026):
//   • Os dicionários (≈510 KB no total) já não estão no bundle principal: só o
//     do idioma ativo é descarregado, em paralelo com o arranque da app.
//   • Depois da primeira passagem, só os nós que mudaram são traduzidos
//     (antes, a página inteira era relida a cada alteração do DOM).

const ATTRS = ["placeholder", "title", "aria-label", "alt"];
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "CODE", "PRE", "NOSCRIPT"]);
const norm = (s) => s.replace(/\s+/g, " ").trim();

async function loadDict(lang) {
  if (lang === "pt") return (await import("@/i18n/pt_auto.json")).default; // FR → PT
  if (lang === "en") return (await import("@/i18n/en_auto.json")).default; // PT → EN
  if (lang === "fr") {
    // PT → FR : fr_auto.json, com fallback no mapa inverso de pt_auto.json
    // (resíduo histórico das versões anteriores em francês).
    const [{ default: PT }, { default: FR }] = await Promise.all([
      import("@/i18n/pt_auto.json"),
      import("@/i18n/fr_auto.json"),
    ]);
    const legacy = {};
    for (const [fr, pt] of Object.entries(PT)) {
      if (typeof fr !== "string" || typeof pt !== "string") continue;
      const key = norm(pt);
      if (!key || key in legacy) continue;
      legacy[key] = fr;
    }
    return { ...legacy, ...FR }; // FR estático sobrepõe-se ao legado
  }
  return null;
}

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

const skipped = (el) => !el || SKIP.has(el.tagName) || !!el.closest?.("[data-no-translate]");

const setAttrs = (el, lookup) => {
  for (const a of ATTRS) {
    const v = el.getAttribute?.(a);
    if (!v) continue;
    const t = lookup(v);
    if (t && el.getAttribute(a) !== t) el.setAttribute(a, t);
  }
};

const translateText = (n, lookup) => {
  if (skipped(n.parentElement)) return;
  const t = lookup(n.nodeValue);
  if (t && n.nodeValue !== t) n.nodeValue = t;
};

const translateTree = (root, lookup) => {
  if (root.nodeType === Node.TEXT_NODE) { translateText(root, lookup); return; }
  if (root.nodeType !== Node.ELEMENT_NODE || skipped(root)) return;
  setAttrs(root, lookup);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
    acceptNode: (n) => {
      if (n.nodeType === Node.ELEMENT_NODE) {
        if (SKIP.has(n.tagName) || n.hasAttribute("data-no-translate")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_SKIP; // visita atributos no fluxo
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let n;
  while ((n = walker.nextNode())) {
    if (n.nodeType === Node.TEXT_NODE) {
      const t = lookup(n.nodeValue);
      if (t && n.nodeValue !== t) n.nodeValue = t;
    } else {
      setAttrs(n, lookup);
    }
  }
};

export const DomTranslator = () => {
  const { lang } = useI18n();
  useEffect(() => {
    let cancelled = false;
    let obs = null;
    loadDict(lang).then((dict) => {
      if (cancelled || !dict) return;
      const lookup = buildLookup(dict);
      translateTree(document.body, lookup);
      // Captura conteúdo tardio (toasts, modais, listas carregadas assíncronas):
      // só os nós alterados são traduzidos, uma vez por frame.
      const pending = new Set();
      let scheduled = false;
      const flush = () => {
        scheduled = false;
        const nodes = [...pending];
        pending.clear();
        for (const node of nodes) {
          if (node.isConnected) translateTree(node, lookup);
        }
      };
      obs = new MutationObserver((records) => {
        for (const r of records) {
          if (r.type === "childList") r.addedNodes.forEach((n) => pending.add(n));
          else pending.add(r.target); // characterData (nó de texto) ou attributes (elemento)
        }
        if (!scheduled && pending.size) {
          scheduled = true;
          requestAnimationFrame(flush);
        }
      });
      obs.observe(document.body, {
        childList: true, subtree: true, characterData: true,
        attributes: true, attributeFilter: ATTRS,
      });
    }).catch(() => { /* dicionário indisponível (offline sem cache) : textos originais */ });
    return () => { cancelled = true; obs?.disconnect(); };
  }, [lang]);
  return null;
};
