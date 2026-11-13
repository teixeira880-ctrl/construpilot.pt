#!/usr/bin/env node
/*
 * Copia para public/bim/ os ficheiros binários do visualizador BIM, sempre na versão instalada:
 *  - web-ifc.wasm (leitura de IFC em WebAssembly, MPL-2.0)
 *  - o worker do @thatopen/fragments (geometria fora da thread principal, MIT)
 * Servidos pelo próprio ConstruPilot: nenhuma dependência de CDN externa em produção.
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const out = path.join(root, "public", "bim");
const files = [
  ["node_modules/web-ifc/web-ifc.wasm", "web-ifc.wasm"],
  ["node_modules/@thatopen/fragments/dist/Worker/worker.min.mjs", "fragments-worker.js"],
];

fs.mkdirSync(out, { recursive: true });
let missing = 0;
for (const [src, dst] of files) {
  const from = path.join(root, src);
  if (!fs.existsSync(from)) {
    console.warn(`[bim-assets] em falta: ${src} (execute yarn install)`);
    missing += 1;
    continue;
  }
  fs.copyFileSync(from, path.join(out, dst));
}
const pkg = (p) => {
  try { return require(path.join(root, "node_modules", p, "package.json")).version; } catch { return null; }
};
fs.writeFileSync(path.join(out, "versions.json"), JSON.stringify({
  "web-ifc": pkg("web-ifc"), "@thatopen/fragments": pkg("@thatopen/fragments"),
  "@thatopen/components": pkg("@thatopen/components"),
}, null, 2) + "\n");
console.log(missing ? `[bim-assets] ${missing} ficheiro(s) em falta` : "[bim-assets] ok → public/bim/");
