#!/usr/bin/env node
/* eslint-disable */
// Gera o manifesto de textos de interface (frontend/src) usado pela tradução automática.
//
// Saída: { version, exact: [texto…], patterns: ["Poupa {0} + IVA por ano", …] }
//   • exact    → textos fixos (JSXText, strings de props, toasts, labels…)
//   • patterns → textos com partes variáveis (template literals e JSX com {expr})
//
// O backend só traduz textos que constem deste manifesto (nunca dados de clientes).
// Uso: node scripts/i18n-manifest.cjs [--out <ficheiro>]…
// Por defeito escreve em ../backend/data/i18n_manifest.json (se a pasta existir).

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const parser = require("@babel/parser");
const traverse = require("@babel/traverse").default;

const ROOT = path.resolve(__dirname, "..", "src");
const SKIP_DIRS = new Set(["__tests__", "__mocks__", "i18n"]);
const norm = (s) => String(s).replace(/\s+/g, " ").trim();

// Atributos JSX que nunca são texto visível
const ATTR_DENY = new Set([
  "className", "style", "id", "key", "href", "src", "srcSet", "type", "name", "to", "variant", "size",
  "data-testid", "testId", "role", "htmlFor", "target", "rel", "method", "action", "accept", "autoComplete",
  "inputMode", "pattern", "lang", "dir", "fill", "stroke", "d", "viewBox", "xmlns", "transform", "points",
  "strokeWidth", "strokeLinecap", "strokeLinejoin", "fontFamily", "textAnchor", "dominantBaseline",
  "icon", "align", "side", "orientation", "mode", "path", "element", "as", "color", "tone", "kind",
  "position", "sizes", "media", "loading", "decoding", "crossOrigin", "referrerPolicy", "download",
  "encType", "form", "list", "step", "min", "max", "value", "defaultValue", "layout", "dataKey",
  "stopColor", "offset", "gradientTransform", "clipPath", "mask", "filter", "x", "y", "width", "height",
]);

const CODE_CALLEES = new Set(["require", "import", "get", "post", "put", "patch", "delete", "fetch",
  "querySelector", "querySelectorAll", "getElementById", "addEventListener", "removeEventListener",
  "getItem", "setItem", "removeItem", "startsWith", "endsWith", "includes", "indexOf", "split", "replace",
  "match", "test", "matchMedia", "createElement", "setAttribute", "getAttribute", "closest", "useState",
  "toLocaleString", "toLocaleDateString", "Intl", "NumberFormat", "DateTimeFormat", "lazy", "navigate",
  "open", "assign", "dispatchEvent", "Event", "CustomEvent", "Date", "RegExp", "t"]);

const TAILWIND_TOKEN = /^[!-]?[a-z0-9]+([:\-\/.\[\]#%()_,][a-z0-9\-\/.\[\]#%()_,'"=&>]*)*$/;

function looksLikeText(s) {
  if (!s || s.length < 2 || s.length > 3000) return false;
  if (!/[A-Za-zÀ-ÿ]{2}/.test(s)) return false;
  if (/^(https?:|mailto:|tel:|data:|blob:|#[0-9a-f]{3,8}$)/i.test(s)) return false;
  if (/^(\/|\.\/|\.\.\/|@\/)/.test(s) && !/\s/.test(s)) return false;          // caminhos (não "/mês + IVA")
  if (/^[\w.+-]+@[\w-]+\.[\w.]+$/.test(s)) return false;
  if (/^[a-z]+(\.[a-z0-9_-]+)+$/i.test(s) && !/\s/.test(s)) return false; // chaves i18n, ficheiros
  if (/^[A-Z0-9_]+$/.test(s)) return false;                               // CONSTANTES
  if (/^(application|image|text|video|audio)\//.test(s)) return false;
  const tokens = s.split(/\s+/);
  if (tokens.length === 1) {
    // palavra única: só se começar por maiúscula ou tiver acentos (evita valores de código)
    if (/^[a-z0-9_\-:.\/]+$/.test(s)) return false;
    if (/^[a-z]+[A-Z]\w*$/.test(s)) return false; // camelCase
  }
  if (!/[À-ÿ]/.test(s) && tokens.every((t) => TAILWIND_TOKEN.test(t)) &&
      tokens.some((t) => /[-:\/\[]/.test(t))) return false;               // classes CSS
  if (/^[\s\d.,:%+\-×x*\/()€$£°]+$/.test(s)) return false;
  if (/^(rgba?|hsla?|var|calc|url|linear-gradient|translate)\(/.test(s)) return false;
  if (/[{};]\s*$/.test(s) && /[:;]/.test(s) && !/\s[a-zà-ÿ]{3,}\s[a-zà-ÿ]{3,}/i.test(s)) return false; // CSS/JS
  if (/\b(SELECT|INSERT|function|return|const|=>)\b/.test(s) && /[=(){}]/.test(s)) return false;
  return true;
}

function walk(dir, out) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) {
      if (!SKIP_DIRS.has(e.name)) walk(path.join(dir, e.name), out);
    } else if (/\.(jsx?|tsx?)$/.test(e.name) && !/\.(test|spec)\./.test(e.name) && !/setupTests/.test(e.name)) {
      out.push(path.join(dir, e.name));
    }
  }
  return out;
}

function isJsxish(node) {
  if (!node) return false;
  switch (node.type) {
    case "JSXElement": case "JSXFragment": return true;
    case "ConditionalExpression": return isJsxish(node.consequent) || isJsxish(node.alternate);
    case "LogicalExpression": return isJsxish(node.right) || isJsxish(node.left);
    case "CallExpression": return true; // .map(…), render helpers… (desconhecido → não juntar)
    default: return false;
  }
}

function templateToPattern(tpl) {
  let s = "";
  tpl.quasis.forEach((q, i) => {
    s += q.value.cooked ?? q.value.raw;
    if (i < tpl.expressions.length) s += `{${i}}`;
  });
  return norm(s);
}

function staticPart(p) { return p.replace(/\{\d+\}/g, " "); }

function inCodeContext(p) {
  // strings dentro de console.*, imports, chaves de objeto, comparações, chamadas técnicas…
  const parent = p.parentPath;
  if (!parent) return false;
  const pn = parent.node;
  if (parent.isImportDeclaration() || parent.isExportAllDeclaration() || parent.isExportNamedDeclaration()) return true;
  if (parent.isObjectProperty() && pn.key === p.node && !pn.computed) return true;
  if (parent.isObjectMethod() && pn.key === p.node) return true;
  if (parent.isBinaryExpression() && ["===", "!==", "==", "!=", "in", "instanceof"].includes(pn.operator)) return true;
  if (parent.isSwitchCase()) return true;
  if (parent.isMemberExpression() && pn.property === p.node) return true;
  if (parent.isJSXAttribute()) {
    const name = pn.name && (pn.name.name || (pn.name.namespace && pn.name.name.name));
    if (typeof name === "string" && (ATTR_DENY.has(name) || name.startsWith("data-") || name.startsWith("on"))) return true;
  }
  // sobe até uma chamada: console.x(...), api.get(...), etc.
  let cur = p;
  for (let depth = 0; cur && depth < 4; depth++, cur = cur.parentPath) {
    const n = cur.parentPath && cur.parentPath.node;
    if (!n) break;
    if ((n.type === "CallExpression" || n.type === "NewExpression") && n.arguments.includes(cur.node)) {
      const c = n.callee;
      const name = c.type === "Identifier" ? c.name : c.type === "MemberExpression" && !c.computed ? c.property.name : null;
      const obj = c.type === "MemberExpression" && c.object.type === "Identifier" ? c.object.name : null;
      if (obj === "console" || obj === "logger" || obj === "JSON" || obj === "Object" || obj === "localStorage" || obj === "sessionStorage") return true;
      if (name && CODE_CALLEES.has(name)) {
        // t("chave", "fallback visível") → o fallback é texto
        if (name === "t" && n.arguments.indexOf(cur.node) === 1) return false;
        return true;
      }
      if (c.type === "Identifier" && /^(cn|clsx|cva|twMerge|classNames)$/.test(c.name)) return true;
      break;
    }
    if (n.type === "JSXAttribute" || n.type === "ObjectProperty" && n.key && (n.key.name === "className" || n.key.name === "style")) {
      if (n.type === "ObjectProperty") return true;
      const nm = n.name && n.name.name;
      if (typeof nm === "string" && (ATTR_DENY.has(nm) || nm.startsWith("data-") || nm.startsWith("on"))) return true;
      break;
    }
  }
  return false;
}

function extract() {
  const exact = new Set();
  const patterns = new Set();
  const files = walk(ROOT, []);
  for (const file of files) {
    const code = fs.readFileSync(file, "utf8");
    let ast;
    try {
      ast = parser.parse(code, { sourceType: "module", plugins: ["jsx", "typescript", "classProperties", "optionalChaining", "nullishCoalescingOperator", "dynamicImport", "topLevelAwait"], errorRecovery: true });
    } catch (e) {
      process.stderr.write(`[i18n-manifest] ignorado (parse): ${path.relative(ROOT, file)}\n`);
      continue;
    }
    traverse(ast, {
      JSXText(p) {
        const s = norm(p.node.value);
        if (looksLikeText(s) || (s.length >= 2 && /[A-Za-zÀ-ÿ]{2}/.test(s) && /\s|[À-ÿ]|^[A-ZÀ-Ý]/.test(s))) exact.add(s);
      },
      StringLiteral(p) {
        const s = norm(p.node.value);
        if (!looksLikeText(s) || inCodeContext(p)) return;
        exact.add(s);
      },
      TemplateLiteral(p) {
        if (p.parentPath.isTaggedTemplateExpression()) return;
        if (inCodeContext(p)) return;
        const pat = templateToPattern(p.node);
        if (p.node.expressions.length === 0) {
          if (looksLikeText(pat)) exact.add(pat);
          return;
        }
        const st = norm(staticPart(pat));
        if (!/[A-Za-zÀ-ÿ]{3}/.test(st)) return;
        if (!looksLikeText(st)) return;
        if (/^\{\d+\}$/.test(pat)) return;
        patterns.add(pat);
      },
      "JSXElement|JSXFragment"(p) {
        // filhos só de texto + {expr} não-JSX → um único elemento com vários nós de texto no DOM
        const kids = p.node.children.filter((c) => !(c.type === "JSXText" && !c.value.trim() && /\n/.test(c.value)));
        if (kids.length < 2) return;
        if (!kids.some((c) => c.type === "JSXExpressionContainer")) return;
        let s = "", n = 0, ok = true;
        for (const c of kids) {
          if (c.type === "JSXText") s += c.value.replace(/\s*\n\s*/g, " ");
          else if (c.type === "JSXExpressionContainer") {
            const ex = c.expression;
            if (ex.type === "JSXEmptyExpression") continue;
            if (ex.type === "StringLiteral") s += ex.value;
            else if (isJsxish(ex) && !(ex.type === "CallExpression" && ex.callee.type === "Identifier" && ex.callee.name === "t")) { ok = false; break; }
            else s += `{${n++}}`;
          } else { ok = false; break; }
        }
        if (!ok) return;
        const pat = norm(s);
        if (n === 0) { if (looksLikeText(pat)) exact.add(pat); return; }
        if (!/[A-Za-zÀ-ÿ]{3}/.test(staticPart(pat))) return;
        patterns.add(pat);
      },
    });
  }
  const ex = [...exact].sort();
  const pa = [...patterns].filter((p) => !exact.has(p)).sort();
  const version = crypto.createHash("sha1").update(JSON.stringify([ex, pa])).digest("hex").slice(0, 12);
  return { version, generated_from: "frontend/src", exact: ex, patterns: pa };
}

function main() {
  const args = process.argv.slice(2);
  const outs = [];
  for (let i = 0; i < args.length; i++) if (args[i] === "--out") outs.push(path.resolve(args[++i]));
  if (!outs.length) {
    const backendData = path.resolve(__dirname, "..", "..", "backend", "data");
    if (fs.existsSync(backendData)) outs.push(path.join(backendData, "i18n_manifest.json"));
  }
  const m = extract();
  for (const o of outs) {
    fs.writeFileSync(o, JSON.stringify(m, null, 0));
    process.stdout.write(`[i18n-manifest] ${m.exact.length} textos + ${m.patterns.length} padrões → ${o} (v${m.version})\n`);
  }
  if (!outs.length) process.stdout.write(JSON.stringify({ version: m.version, exact: m.exact.length, patterns: m.patterns.length }) + "\n");
}

main();
