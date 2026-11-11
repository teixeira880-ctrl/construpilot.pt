import { useEffect } from "react";
import { useI18n } from "@/context/I18nContext";
import { API } from "@/lib/api";
import PT from "@/i18n/pt_auto.json";
import EN from "@/i18n/en_auto.json";
import FR from "@/i18n/fr_auto.json";

// Tradução COMPLETA da interface, aplicada ao ecrã inteiro de uma só vez.
//
// Camadas (por ordem de prioridade):
//   1. dicionários estáticos revistos à mão (pt_auto / en_auto / fr_auto);
//   2. dicionário completo do servidor (GET /api/i18n/dict/:lang) — todos os textos do código,
//      traduzidos por Claude a partir do manifesto (frontend/scripts/i18n-manifest.cjs);
//   3. padrões com partes variáveis: "Poupa {0} + IVA por ano" → "Save {0} + VAT per year".
// Frases partidas pelo React em vários nós de texto ("Por mais ", "127,50 €", " por mês…")
// são juntadas, traduzidas e reescritas no 1.º nó.
//
// Sentidos: lang="pt" FR→PT (resíduos) · lang="en" PT/FR→EN · lang="fr" PT→FR · lang="uk" PT/FR/EN→UK
// (ucraniano: só dicionário do servidor, traduzido do manifesto inteiro).

const ATTRS = ["placeholder", "title", "aria-label", "alt"];
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "CODE", "PRE", "NOSCRIPT"]);
const NO_TRANSLATE = "[data-no-translate],[translate='no'],[contenteditable='true']";
const norm = (s) => s.replace(/\s+/g, " ").trim();
const LS_PREFIX = "cp_i18n_dict_";
const REFRESH_MS = 10 * 60 * 1000;

// Mapa inverso PT→FR a partir de pt_auto.json (resíduo histórico da versão francesa).
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

const STATIC = {
  pt: PT,
  en: EN,
  fr: { ...PT_TO_FR_LEGACY, ...FR },
  uk: {},
};

// ── Padrões ──────────────────────────────────────────────────────────────────
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function compilePatterns(list) {
  const byPrefix = new Map();
  const bySuffix = new Map();
  const loose = [];
  for (const [src, tgt] of list || []) {
    if (typeof src !== "string" || typeof tgt !== "string") continue;
    const parts = src.split(/(\{\d+\})/);
    const order = [];
    let re = "^";
    for (const p of parts) {
      const m = p.match(/^\{(\d+)\}$/);
      if (m) { order.push(Number(m[1])); re += "(.*?)"; } else re += esc(p);
    }
    re += "$";
    let rx;
    try { rx = new RegExp(re); } catch { continue; }
    const entry = { rx, tgt, order };
    const lit = parts.filter((p) => p && !/^\{\d+\}$/.test(p));
    if (!lit.length) continue;
    if (parts[0] && !/^\{\d+\}$/.test(parts[0]) && parts[0].length >= 3) {
      const k = parts[0].slice(0, 3);
      (byPrefix.get(k) || byPrefix.set(k, []).get(k)).push(entry);
    } else if (parts[parts.length - 1] && parts[parts.length - 1].length >= 3) {
      const last = parts[parts.length - 1];
      const k = last.slice(-3);
      (bySuffix.get(k) || bySuffix.set(k, []).get(k)).push(entry);
    } else loose.push(entry);
  }
  return { byPrefix, bySuffix, loose };
}

function matchPatterns(P, key) {
  if (!P) return null;
  const cands = [...(P.byPrefix.get(key.slice(0, 3)) || []), ...(P.bySuffix.get(key.slice(-3)) || []), ...P.loose];
  for (const { rx, tgt, order } of cands) {
    const m = key.match(rx);
    if (!m) continue;
    const vals = {};
    order.forEach((n, i) => { vals[n] = m[i + 1]; });
    return tgt.replace(/\{(\d+)\}/g, (_, n) => (vals[n] ?? ""));
  }
  return null;
}

// ── Dicionário remoto ────────────────────────────────────────────────────────
function readCache(lang) {
  try {
    const raw = localStorage.getItem(LS_PREFIX + lang);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function writeCache(lang, data) {
  try { localStorage.setItem(LS_PREFIX + lang, JSON.stringify({ ...data, ts: Date.now() })); } catch { /* quota */ }
}

async function fetchDict(lang) {
  const r = await fetch(`${API}/i18n/dict/${lang}`, { credentials: "omit" });
  if (!r.ok) throw new Error(`i18n ${r.status}`);
  return r.json();
}

// ── Componente ───────────────────────────────────────────────────────────────
export const DomTranslator = () => {
  const { lang } = useI18n();
  useEffect(() => {
    const base = STATIC[lang] || null;
    let remote = {};
    let patterns = null;
    let complete = false;
    let ready = false; // só pedir textos em falta depois de conhecer o dicionário do servidor
    const misses = new Set();
    const asked = new Set();
    const touched = new Set(); // nós alterados (para repor ao trocar de língua sem recarregar)

    const lookupKey = (key) => {
      if (!key) return null;
      let hit = (base && base[key]) || remote[key];
      if (!hit) {
        const stripped = key.replace(/\s*[:·•→]\s*$/, "");
        const tail = key.slice(stripped.length);
        if (stripped !== key) {
          const h2 = (base && base[stripped]) || remote[stripped];
          if (h2) hit = h2 + tail;
        }
      }
      if (!hit) hit = matchPatterns(patterns, key);
      if (!hit || hit === key) return null;
      return hit;
    };

    const lookup = (raw) => {
      const key = norm(raw);
      if (!key) return null;
      const hit = lookupKey(key);
      if (!hit) {
        if (ready && !complete && /[A-Za-zÀ-ÿ]{2}/.test(key) && key.length < 3000 && !asked.has(key)) misses.add(key);
        return null;
      }
      return raw.match(/^\s*/)[0] + hit + raw.match(/\s*$/)[0];
    };

    // Origem de um nó: o último valor escrito pelo React (≠ do que nós escrevemos).
    const srcOf = (n) => {
      const rec = n.__i18n;
      if (rec && n.nodeValue === rec.out) return rec.src;
      return n.nodeValue;
    };
    const write = (n, src, out) => {
      n.__i18n = { src, out };
      if (n.nodeValue !== out) n.nodeValue = out;
      touched.add(n);
    };

    const setAttrs = (el) => {
      for (const a of ATTRS) {
        const v = el.getAttribute?.(a);
        if (!v) continue;
        const rec = el.__i18nAttr?.[a];
        const src = rec && v === rec.out ? rec.src : v;
        const t = lookup(src);
        if (t && v !== t) {
          el.__i18nAttr = { ...(el.__i18nAttr || {}), [a]: { src, out: t } };
          el.setAttribute(a, t);
          touched.add(el);
        }
      }
    };

    const doneParents = new Set();
    const handleText = (n) => {
      const p = n.parentElement;
      if (!p || SKIP.has(p.tagName) || p.closest(NO_TRANSLATE)) return;
      // Frase partida em vários nós de texto irmãos → traduzir o conjunto
      const kids = p.childNodes;
      if (kids.length > 1 && kids.length < 40) {
        if (doneParents.has(p)) return;
        let allText = true;
        for (const k of kids) if (k.nodeType !== Node.TEXT_NODE) { allText = false; break; }
        if (allText) {
          doneParents.add(p);
          const srcs = Array.from(kids, srcOf);
          const joined = srcs.join("");
          const t = lookup(joined);
          if (t) {
            Array.from(kids).forEach((k, i) => write(k, srcs[i], i === 0 ? t : ""));
            return;
          }
          // sem tradução do conjunto: tentar cada fragmento
          Array.from(kids).forEach((k, i) => {
            const ti = lookup(srcs[i]);
            if (ti) write(k, srcs[i], ti);
            else if (k.__i18n && k.nodeValue !== srcs[i]) write(k, srcs[i], srcs[i]);
          });
          return;
        }
      }
      const src = srcOf(n);
      const t = lookup(src);
      if (t) write(n, src, t);
    };

    const translateTree = (root) => {
      doneParents.clear();
      if (root.nodeType === Node.ELEMENT_NODE) setAttrs(root);
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
        acceptNode: (n) => {
          if (n.nodeType === Node.ELEMENT_NODE) {
            if (SKIP.has(n.tagName)) return NodeFilter.FILTER_REJECT;
            if (n.matches?.(NO_TRANSLATE)) return NodeFilter.FILTER_REJECT;
            return NodeFilter.FILTER_SKIP;
          }
          return NodeFilter.FILTER_ACCEPT;
        },
      });
      // atributos (placeholder…) de todos os elementos, inputs incluídos
      root.querySelectorAll?.("[placeholder],[title],[aria-label],[alt]").forEach((el) => {
        if (!el.closest(NO_TRANSLATE)) setAttrs(el);
      });
      let n;
      while ((n = walker.nextNode())) if (n.nodeType === Node.TEXT_NODE) handleText(n);
    };

    let scheduled = false;
    let stopped = false;
    const obs = new MutationObserver(() => schedule());
    const runRoot = () => {
      if (touched.size > 20000) for (const t of touched) if (!t.isConnected) touched.delete(t);
      obs.disconnect(); // as nossas próprias escritas não disparam nova passagem
      try { translateTree(document.body); } finally {
        if (!stopped) obs.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
      }
      if (misses.size) scheduleMisses();
    };
    function schedule() {
      if (scheduled || stopped) return;
      scheduled = true;
      requestAnimationFrame(() => { scheduled = false; if (!stopped) runRoot(); });
    }

    // Textos ainda sem tradução enquanto o servidor termina a pré-tradução: pedir já.
    let missTimer = null;
    let missBudget = 400;
    const scheduleMisses = () => {
      if (missTimer || complete || missBudget <= 0) return;
      missTimer = setTimeout(async () => {
        missTimer = null;
        const texts = [...misses].slice(0, 80);
        misses.clear();
        texts.forEach((t) => asked.add(t));
        missBudget -= texts.length;
        try {
          const r = await fetch(`${API}/i18n/translate`, {
            method: "POST", headers: { "Content-Type": "application/json" }, credentials: "omit",
            body: JSON.stringify({ lang, texts }),
          });
          if (!r.ok) return;
          const { translations } = await r.json();
          if (translations && Object.keys(translations).length && !stopped) {
            remote = { ...remote, ...translations };
            runRoot();
          }
        } catch { /* rede indisponível — fica no idioma de origem */ }
      }, 1500);
    };

    const apply = (data) => {
      if (!data || data.lang !== lang) return;
      remote = data.exact || {};
      patterns = compilePatterns(data.patterns);
      complete = !!data.complete;
      ready = true;
    };

    let refetchTimer = null;
    let refetches = 0;
    const load = async () => {
      try {
        const data = await fetchDict(lang);
        if (stopped) return;
        apply(data);
        writeCache(lang, data);
        runRoot();
        if (!data.complete && refetches++ < 20) refetchTimer = setTimeout(load, 15000);
      } catch { /* offline: fica com a cache */ }
    };

    const cachedDict = readCache(lang);
    if (cachedDict) apply(cachedDict);
    runRoot();
    if (!cachedDict || !cachedDict.complete || Date.now() - (cachedDict.ts || 0) > REFRESH_MS) load();

    return () => {
      stopped = true;
      obs.disconnect();
      clearTimeout(missTimer);
      clearTimeout(refetchTimer);
      // repor o texto de origem (troca de língua sem recarregar a página)
      for (const n of touched) {
        if (n.nodeType === Node.TEXT_NODE) {
          const rec = n.__i18n;
          if (rec && n.nodeValue === rec.out) n.nodeValue = rec.src;
          n.__i18n = undefined;
        } else if (n.__i18nAttr) {
          for (const [a, rec] of Object.entries(n.__i18nAttr)) {
            if (n.getAttribute(a) === rec.out) n.setAttribute(a, rec.src);
          }
          n.__i18nAttr = undefined;
        }
      }
      touched.clear();
    };
  }, [lang]);
  return null;
};
