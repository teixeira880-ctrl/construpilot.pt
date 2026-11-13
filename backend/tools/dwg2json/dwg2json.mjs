// DWG → JSON (espaço modelo + blocos usados), lido com LibreDWG compilado em WebAssembly.
// Corre num processo Node separado: node dwg2json.mjs <entrada.dwg> <saída.json>
// LibreDWG / @mlightcad/libredwg-web: GPL-3.0 (https://github.com/mlightcad/libredwg-web) — usado como programa
// independente no servidor, sem ligação ao código do ConstruPilot.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Dwg_File_Type, LibreDwg } from '@mlightcad/libredwg-web'

const [, , input, output] = process.argv
if (!input || !output) { console.error('uso: dwg2json.mjs entrada.dwg saída.json'); process.exit(2) }
const here = path.dirname(fileURLToPath(import.meta.url))
const wasmDir = path.join(here, 'node_modules', '@mlightcad', 'libredwg-web', 'wasm') + path.sep

const lib = await LibreDwg.create(wasmDir)
const dwg = lib.dwg_read_data(fs.readFileSync(input), Dwg_File_Type.DWG)
if (!dwg) { console.error('DWG ilegível'); process.exit(3) }
const db = lib.convert(dwg)
lib.dwg_free(dwg)

const DROP = new Set(['xdata', 'ownerDictionaryHardId', 'colorName', 'transparency', 'transparencyType', 'bmpPreview',
  'reactors', 'extensionDictionary'])
const clean = (e) => Object.fromEntries(Object.entries(e).filter(([k]) => !DROP.has(k)))

const records = db.tables?.BLOCK_RECORD?.entries || []
const model = records.find((b) => /^\*model_space$/i.test(b.name))
const modelHandle = model?.handle
const entities = (model?.entities?.length ? model.entities : (db.entities || []).filter((e) => e.ownerBlockRecordSoftId === modelHandle))
const byName = new Map(records.map((b) => [b.name, b]))

// Blocos referenciados (INSERT, DIMENSION), recursivamente.
const blocks = {}
const queue = []
const want = (n) => { if (n && !blocks[n] && byName.has(n) && !/^\*(model|paper)_space/i.test(n)) { blocks[n] = null; queue.push(n) } }
for (const e of entities) if (e.type === 'INSERT' || e.type === 'DIMENSION') want(e.name)
while (queue.length) {
  const b = byName.get(queue.shift())
  blocks[b.name] = { basePoint: b.basePoint, entities: (b.entities || []).map(clean) }
  for (const e of b.entities || []) if (e.type === 'INSERT' || e.type === 'DIMENSION') want(e.name)
}
const h = db.header || {}
const out = {
  header: { INSUNITS: h.INSUNITS, EXTMIN: h.EXTMIN, EXTMAX: h.EXTMAX, LUNITS: h.LUNITS, ACADVER: h.ACADVER },
  layers: (db.tables?.LAYER?.entries || []).map((l) => ({ name: l.name, colorIndex: l.colorIndex, off: !!l.off, frozen: !!l.frozen,
    lineType: l.lineType })),
  entities: entities.map(clean),
  blocks,
}
fs.writeFileSync(output, JSON.stringify(out))
console.log(JSON.stringify({ entities: out.entities.length, blocks: Object.keys(blocks).length }))
