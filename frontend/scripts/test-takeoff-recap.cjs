// Runs the actual analysis callback with simulated API results, without React or a server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { parse } = require('@babel/parser');

const source = fs.readFileSync(path.join(__dirname, '../src/pages/PlanTakeoff.jsx'), 'utf8');
const tree = parse(source, { sourceType: 'module', plugins: ['jsx'] });
let callback;
function visit(node) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'VariableDeclarator' && node.id.name === 'analyzePlanFull') callback = node.init;
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(visit);
    else if (value && typeof value === 'object') visit(value);
  }
}
visit(tree);
assert.ok(callback, 'Actual analyzePlanFull callback must exist');

async function analyze(rooms, overrides = {}) {
  let recap, estimates = 0;
  const noop = () => {};
  const globals = {
    plan: { plan_id: 'p' }, currentCalib: { pixels_per_meter: 100 }, pageKey: 'p:0', pageIndex: 0,
    currentPageKeyRef: { current: 'p:0' }, planKindChoice: 'auto',
    finitePositive: value => Number.isFinite(Number(value)) && Number(value) > 0,
    setAnalysisBusy: noop, setAnalysisProgress: noop, analysisLock: { current: false }, setStructure: noop, setShowStructure: noop, setSelectedStruct: noop,
    toast: { loading: () => 'toast', dismiss: noop, warning: noop, success: noop,
      error: (message) => { throw new Error(String(message)); } },
    api: { post: async (url) => ({ data: url.includes('detect-structure')
      ? { wall_count: 1 } : { rooms: [{ estimated_surface_m2: 999 }] } }) },
    refreshPlan: async () => ({ rooms }), importAiRooms: async () => 0,
    loadDescriptif: async () => ({ beton_total_m3: 1, acier_total_kg: 10 }),
    runEstimation: async () => { estimates++; return { estimation: { total_avg: 100 } }; },
    betonPriceM3: 100, acierPriceKg: 1, laborPriceM3: 100, marginPct: 0,
    setAnalysisRecap: (result) => { recap = result; },
    ...overrides,
  };
  await vm.runInNewContext(`(${source.slice(callback.start, callback.end)})`, globals)();
  return { recap, estimates };
}

(async () => {
  const measured = await analyze([{ page_index: 0, surface_m2: 3 }, { page_index: 0, surface_m2: 4.5 }, { page_index: 1, surface_m2: 90 }]);
  assert.equal(measured.recap.surface_pieces_m2, 7.5, 'Use measured surfaces of the current page, never the AI estimate or another page');
  assert.equal(measured.recap.rooms, 2);
  assert.equal(measured.estimates, 1, 'Existing rooms must still be estimated when no new rooms are imported');
  const empty = await analyze([]);
  assert.equal(empty.recap.surface_pieces_m2, null, 'No measured geometry is unknown, not zero or the AI estimate');
  assert.equal(empty.recap.rooms, 0);
  assert.equal(empty.estimates, 0);
  const unavailable = await analyze([], { loadDescriptif: async () => null });
  assert.equal(unavailable.recap.beton_m3, null, 'Unavailable concrete is unknown, not zero');
  assert.equal(unavailable.recap.acier_kg, null);
  assert.equal(unavailable.recap.estimation_globale_eur, null);
  assert.ok(unavailable.recap.warnings.includes('descriptif indisponible'));
  let requests = 0;
  const duplicate = await analyze([], { analysisLock: { current: true }, api: { post: async () => { requests++; } } });
  assert.equal(requests, 0, 'Concurrent analysis must not launch duplicate paid requests');
  assert.equal(duplicate.recap, undefined);
  const missingArea = await analyze([{ page_index: 0, surface_m2: null }, { page_index: 0, surface_m2: 20 }]);
  assert.equal(missingArea.recap.surface_pieces_m2, null, 'A missing room area must not be silently excluded from a total');
  assert.ok(missingArea.recap.warnings.includes('surface manquante ou invalide pour certaines pièces'));
  const missingSteel = await analyze([], { loadDescriptif: async () => ({ beton_total_m3: 1 }) });
  assert.equal(missingSteel.recap.estimation_beton_eur, null, 'Unknown steel must not be priced as zero');
  const smallRoom = await analyze([{ page_index: 0, surface_m2: 0.24 }]);
  assert.equal(smallRoom.recap.surface_pieces_m2, 0.24, 'Do not round small surfaces to a tenth');
  console.log('Takeoff recap: 16 assertions passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
