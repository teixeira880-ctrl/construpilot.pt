// Lit un DWG (chemin argv[2]) et écrit la base de dessin en JSON (argv[3]), sans les xdata (inutiles au métré, très volumineuses).
// Processus séparé, lancé par engines/dwg_local.py ; aucune entrée réseau.
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { pathToFileURL } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const [, , src, dst] = process.argv;
// node_modules (npm ci) ou copie embarquée dans le dépôt (vendor/) : le déploiement n'installe pas les paquets npm du backend
const base = [path.join(here, 'node_modules/@mlightcad/libredwg-web'), path.join(here, 'vendor/libredwg-web')]
  .find((p) => fs.existsSync(path.join(p, 'wasm/libredwg-web.wasm')));
if (!base) { console.error('libredwg-web absent'); process.exit(3); }
const { Dwg_File_Type, LibreDwg } = await import(pathToFileURL(path.join(base, fs.existsSync(path.join(base, 'js')) ? 'js/libredwg-web.js' : 'dist/libredwg-web.js')).href);
const lib = await LibreDwg.create(path.join(base, 'wasm/'));
const dwg = lib.dwg_read_data(fs.readFileSync(src), Dwg_File_Type.DWG);
if (!dwg) { console.error('DWG illisible'); process.exit(2); }
const db = lib.convert(dwg);
lib.dwg_free(dwg);
const SKIP = new Set(['xdata', 'thumbnailImage', 'ownerDictionaryHardId', 'transparency', 'transparencyType', 'definitionLines']);
const out = { header: db.header, tables: { LAYER: db.tables?.LAYER, BLOCK_RECORD: db.tables?.BLOCK_RECORD }, entities: db.entities };
fs.writeFileSync(dst, JSON.stringify(out, (k, v) => (SKIP.has(k) ? undefined : typeof v === 'bigint' ? Number(v) : v)));
