/* Cópia dos motores do servidor PARA O MODO DEMONSTRAÇÃO OFFLINE APENAS.
 * Fonte de verdade: backend/engines/trade_calcs.py e backend/engines/field_records.py.
 * A paridade é verificada por backend/tests/test_demo_parity.py (mesmas entradas → mesmos resultados).
 * Contas reais usam SEMPRE o servidor. */

export class CalcError extends Error {}
const SUG = {
  paint_yield_m2_per_l: { value: 10, note: "Valor típico de tinta plástica de interior (8–12 m²/L). Confirme na ficha técnica do produto." },
  paint_coats: { value: 2, note: "Duas demãos é o habitual sobre superfície já pintada." },
  floor_waste_pct: { value: 10, note: "Colocação reta: 5–10 %; diagonal ou espinha: 12–15 %." },
  masonry_waste_pct: { value: 5, note: "Perdas habituais de corte e quebra: 3–7 %." },
};
const r2 = (v, d = 2) => (v == null ? null : Math.round((v + Number.EPSILON) * 10 ** d) / 10 ** d);
const ceil = v => Math.ceil(v - 1e-9);

function num(value, field, { min = 0, max = 1e6, allowZero = true } = {}) {
  if (value === null || value === undefined || value === "" || value === "nao_sei") return null;
  const v = Number(value);
  if (!Number.isFinite(v)) throw new CalcError(`«${field}»: indique um número.`);
  if (v < min || v > max || (!allowZero && v === 0)) throw new CalcError(`«${field}»: valor fora dos limites aceitáveis.`);
  return v;
}

function openingsArea(openings, pending, label) {
  let total = 0;
  for (const [i, o] of (openings || []).entries()) {
    const w = num(o.width_m, `${label}: largura da abertura ${i + 1}`, { max: 50 });
    const h = num(o.height_m, `${label}: altura da abertura ${i + 1}`, { max: 50 });
    const c = num(o.count ?? 1, `${label}: número de aberturas ${i + 1}`, { max: 500 }) || 0;
    if (w === null || h === null) { pending.push(`${label}: dimensões da abertura ${i + 1}`); return null; }
    total += w * h * c;
  }
  return total;
}

function roomSurfaces(room) {
  const name = (room.name || "Divisão").trim().slice(0, 60);
  const pending = [];
  const h = num(room.height_m, `${name}: pé-direito`, { max: 30, allowZero: false });
  const L = num(room.length_m, `${name}: comprimento`, { max: 500, allowZero: false });
  const W = num(room.width_m, `${name}: largura`, { max: 500, allowZero: false });
  let per = num(room.perimeter_m, `${name}: perímetro`, { max: 2000, allowZero: false });
  let floor = num(room.floor_area_m2, `${name}: área do chão`, { max: 100000, allowZero: false });
  const direct = num(room.wall_area_m2, `${name}: área das paredes`, { max: 100000 });
  if (per === null && L !== null && W !== null) per = 2 * (L + W);
  if (floor === null && L !== null && W !== null) floor = L * W;
  const op = openingsArea(room.openings, pending, name);
  let gross = direct;
  if (gross === null) {
    if (per === null) pending.push(`${name}: comprimento e largura (ou perímetro)`);
    if (h === null) pending.push(`${name}: pé-direito`);
    if (per !== null && h !== null) gross = per * h;
  }
  let net = null;
  if (gross !== null && op !== null) {
    if (op > gross) throw new CalcError(`${name}: as aberturas são maiores do que as paredes — verifique as medidas.`);
    net = Math.max(gross - op, 0);
  }
  const walls = room.paint_walls !== false;
  const ceilOn = !!room.paint_ceiling;
  const ceiling = ceilOn ? floor : 0;
  if (ceilOn && floor === null) pending.push(`${name}: área do teto (comprimento × largura)`);
  const ok = (!walls || net !== null) && (!ceilOn || ceiling !== null);
  const surface = ok ? (walls ? net : 0) + (ceiling || 0) : null;
  return { name, walls_gross_m2: r2(gross), openings_m2: r2(op), walls_net_m2: r2(net), ceiling_m2: r2(ceilOn ? ceiling : 0),
    surface_m2: r2(surface), source: direct !== null ? "user" : "formula", pending };
}

export function paintCalc(p) {
  const rooms = p.rooms || [];
  if (!rooms.length) throw new CalcError("Indique pelo menos uma divisão ou superfície.");
  const details = rooms.map(roomSurfaces);
  const pending = details.flatMap(d => d.pending);
  const coats = num(p.coats, "Número de demãos", { max: 10, allowZero: false });
  const y = num(p.yield_m2_per_l, "Rendimento (m²/L por demão)", { max: 100, allowZero: false });
  const can = num(p.can_size_l, "Tamanho da embalagem (L)", { max: 1000, allowZero: false });
  if (coats === null) pending.push("Número de demãos");
  if (y === null) pending.push("Rendimento da tinta (ficha técnica do produto)");
  const surface = details.some(d => d.surface_m2 === null) ? null : details.reduce((s, d) => s + d.surface_m2, 0);
  const liters = surface !== null && coats !== null && y !== null ? surface * coats / y : null;
  const cans = liters !== null && can ? ceil(liters / can) : null;
  const suggestions = {};
  if (coats === null) suggestions.coats = SUG.paint_coats;
  if (y === null) suggestions.yield_m2_per_l = SUG.paint_yield_m2_per_l;
  return { tool: "paint", rooms: details, surface_m2: r2(surface), coats, yield_m2_per_l: y, liters: r2(liters, 1), can_size_l: can, cans,
    formula: "litros = superfície (m²) × demãos ÷ rendimento (m²/L)", pending, suggestions, complete: !pending.length };
}

export function floorCalc(p) {
  const pending = [];
  let area = num(p.area_m2, "Área a revestir (m²)", { max: 100000, allowZero: false });
  if (area === null) {
    const L = num(p.length_m, "Comprimento", { max: 1000, allowZero: false });
    const W = num(p.width_m, "Largura", { max: 1000, allowZero: false });
    if (L !== null && W !== null) area = L * W; else pending.push("Área (ou comprimento e largura)");
  }
  const waste = num(p.waste_pct, "Perdas (%)", { max: 50 });
  if (waste === null) pending.push("Percentagem de perdas");
  let cov = num(p.package_m2, "Cobertura de uma embalagem (m²)", { max: 1000, allowZero: false });
  if (cov === null) {
    const pl = num(p.piece_length_m, "Comprimento da peça (m)", { max: 10, allowZero: false });
    const pw = num(p.piece_width_m, "Largura da peça (m)", { max: 10, allowZero: false });
    const pp = num(p.pieces_per_package, "Peças por embalagem", { max: 10000, allowZero: false });
    if (pl && pw && pp) cov = pl * pw * pp; else pending.push("Cobertura por embalagem (m²) ou dimensões da peça e peças por embalagem");
  }
  const ww = area !== null && waste !== null ? area * (1 + waste / 100) : null;
  const packages = ww !== null && cov ? ceil(ww / cov) : null;
  const price = num(p.package_price, "Preço por embalagem", { max: 1e6 });
  return { tool: "floor", area_m2: r2(area), waste_pct: waste, area_with_waste_m2: r2(ww), package_m2: r2(cov, 3), packages, package_price: price,
    material_cost: r2(packages !== null && price !== null ? packages * price : null),
    formula: "embalagens = arredondar acima( área × (1 + perdas/100) ÷ m² por embalagem )", pending,
    suggestions: waste !== null ? {} : { waste_pct: SUG.floor_waste_pct }, complete: !pending.length };
}

export function masonryCalc(p) {
  const pending = [];
  const L = num(p.wall_length_m, "Comprimento da parede", { max: 1000, allowZero: false });
  const H = num(p.wall_height_m, "Altura da parede", { max: 50, allowZero: false });
  if (L === null || H === null) pending.push("Comprimento e altura da parede");
  const op = openingsArea(p.openings, pending, "Parede");
  const bl = num(p.block_length_m, "Comprimento do bloco (m)", { max: 2, allowZero: false });
  const bh = num(p.block_height_m, "Altura do bloco (m)", { max: 2, allowZero: false });
  const j = num(p.joint_m, "Espessura da junta (m)", { max: 0.05 });
  if (bl === null || bh === null) pending.push("Dimensões do bloco (comprimento × altura)");
  if (j === null) pending.push("Espessura da junta");
  const waste = num(p.waste_pct, "Perdas (%)", { max: 50 });
  if (waste === null) pending.push("Percentagem de perdas");
  let net = null;
  if (L !== null && H !== null && op !== null) { net = L * H - op; if (net <= 0) throw new CalcError("As aberturas ocupam toda a parede — verifique as medidas."); }
  const per = bl && bh && j !== null ? 1 / ((bl + j) * (bh + j)) : null;
  const blocks = net !== null && per && waste !== null ? ceil(net * per * (1 + waste / 100)) : null;
  return { tool: "masonry", net_area_m2: r2(net), openings_m2: r2(op), blocks_per_m2: r2(per), waste_pct: waste, blocks,
    formula: "blocos = área líquida × 1/((c+junta)×(a+junta)) × (1 + perdas/100)",
    limits: "Cálculo de quantidades apenas. Não verifica estabilidade nem dimensiona a parede.", pending,
    suggestions: waste !== null ? {} : { waste_pct: SUG.masonry_waste_pct }, complete: !pending.length };
}

const POINTS = {
  canalizacao: { agua_fria: "Ponto de água fria", agua_quente: "Ponto de água quente", esgoto: "Ponto de esgoto", sanita: "Sanita", lavatorio: "Lavatório", base_duche: "Base de duche / banheira", lava_loica: "Lava-loiça", maquina: "Máquina (lavar roupa / loiça)", esquentador: "Esquentador / termoacumulador", outro: "Outro" },
  eletricidade: { tomada: "Tomada", tomada_dedicada: "Tomada dedicada (forno, placa, máquina)", interruptor: "Interruptor / comutador", ponto_luz: "Ponto de luz", tomada_rede: "Tomada de rede / TV", quadro: "Quadro elétrico", campainha: "Campainha / intercomunicador", outro: "Outro" },
};

export function pointsTakeoff(p) {
  const types = POINTS[p.trade];
  if (!types) throw new CalcError("Escolha a especialidade: canalização ou eletricidade.");
  const items = p.items || [];
  if (!items.length) throw new CalcError("Adicione pelo menos um ponto.");
  const totals = {}, byRoom = {}, pending = [];
  items.forEach((it, i) => {
    if (!types[it.type]) throw new CalcError(`Linha ${i + 1}: tipo de ponto desconhecido.`);
    const label = it.type === "outro" ? (it.label || "").trim().slice(0, 80) : types[it.type];
    if (it.type === "outro" && !label) throw new CalcError(`Linha ${i + 1}: descreva o ponto «Outro».`);
    const q = num(it.qty, `Linha ${i + 1}: quantidade`, { max: 10000 });
    const room = (it.room || "Sem divisão").trim().slice(0, 60) || "Sem divisão";
    if (q === null) { pending.push(`Quantidade: ${label} (${room})`); return; }
    totals[label] = (totals[label] || 0) + q;
    byRoom[room] = byRoom[room] || {};
    byRoom[room][label] = (byRoom[room][label] || 0) + q;
  });
  for (const label of Object.keys(totals)) if (num((p.prices || {})[label], `Preço: ${label}`, { max: 1e6 }) === null) pending.push(`Preço: ${label}`);
  return { tool: "points", trade: p.trade, totals, by_room: byRoom,
    limits: "Levantamento de quantidades. Não dimensiona circuitos, secções de cabo, diâmetros nem verifica a conformidade regulamentar.",
    pending, complete: !pending.length };
}

export function carpentryCalc(p) {
  const pieces = p.pieces || [];
  if (!pieces.length) throw new CalcError("Adicione pelo menos uma peça.");
  const pending = [], mats = {}, hardware = {};
  let edge = 0;
  pieces.forEach((pc, i) => {
    const name = (pc.name || `Peça ${i + 1}`).trim().slice(0, 60) || `Peça ${i + 1}`;
    const L = num(pc.length_m, `${name}: comprimento`, { max: 10, allowZero: false });
    const W = num(pc.width_m, `${name}: largura`, { max: 10, allowZero: false });
    const q = num(pc.qty ?? 1, `${name}: quantidade`, { max: 10000, allowZero: false });
    const mat = (pc.material || "").trim().slice(0, 60);
    if (!mat) pending.push(`${name}: material`);
    if (L === null || W === null || q === null) { pending.push(`${name}: medidas`); return; }
    if (mat) mats[mat] = (mats[mat] || 0) + L * W * q;
    const e = num(pc.edges_m, `${name}: orla por peça (m)`, { max: 100 });
    if (e) edge += e * q;
    for (const h of pc.hardware || []) {
      const hn = (h.name || "").trim().slice(0, 60);
      const hq = num(h.qty, `${name}: quantidade de ${hn || "ferragem"}`, { max: 10000 });
      if (hn && hq) hardware[hn] = (hardware[hn] || 0) + hq * q;
    }
  });
  const waste = num(p.waste_pct, "Perdas de corte (%)", { max: 60 });
  if (waste === null) pending.push("Percentagem de perdas de corte");
  const sheet = num(p.sheet_m2, "Área de uma placa (m²)", { max: 20, allowZero: false });
  const materials = Object.entries(mats).map(([material, area]) => {
    const ww = waste !== null ? area * (1 + waste / 100) : null;
    return { material, area_m2: r2(area), area_with_waste_m2: r2(ww), sheets: ww !== null && sheet ? ceil(ww / sheet) : null };
  });
  return { tool: "carpentry", materials, edge_banding_ml: r2(edge), hardware,
    formula: "placas = arredondar acima( Σ(c × l × qtd) × (1 + perdas/100) ÷ área da placa )",
    limits: "Não otimiza o plano de corte: o número real de placas pode ser superior.", pending, complete: !pending.length };
}

export const TOOLS = { paint: paintCalc, floor: floorCalc, masonry: masonryCalc, points: pointsTakeoff, carpentry: carpentryCalc };

export function paintingQuoteLines(job) {
  const calc = paintCalc({ rooms: job.rooms || [], coats: job.coats, yield_m2_per_l: job.yield_m2_per_l, can_size_l: job.can_size_l });
  const pr = job.prices || {};
  const labor = num(pr.labor_per_m2, "Mão de obra por m²", { max: 10000 });
  const pl = num(pr.paint_per_l, "Preço da tinta por litro", { max: 10000 });
  const pc = num(pr.paint_per_can, "Preço por embalagem", { max: 100000 });
  const crackMl = num(job.crack_repair_ml, "Fissuras a reparar (metros)", { max: 100000 });
  const crackP = num(pr.crack_per_ml, "Preço da reparação de fissuras por metro", { max: 10000 });
  const prep = num(pr.prep_per_m2, "Preparação de superfícies por m²", { max: 10000 });
  const toConfirm = [...calc.pending];
  const lines = [{ kind: "section", title: "Pintura" }];
  const names = calc.rooms.map(d => d.name).join(", ");
  const line = (designation, unit, qty, price, lineKind, description = "", priceLabel = "") => {
    if (price === null) toConfirm.push(`Preço: ${priceLabel || designation}`);
    if (qty === null) toConfirm.push(`Quantidade: ${designation}`);
    lines.push({ kind: "line", line_kind: lineKind, designation, description, unit, qty: qty ?? 0, unit_price_ht: price || 0, vat_rate: null,
      price_missing: price === null, quantity_missing: qty === null, price_source: price !== null ? "utilizador" : "" });
  };
  if (job.surface_prep !== false) line("Preparação de superfícies (limpeza, lixagem, betumação pontual)", "m²", calc.surface_m2, prep, "main_oeuvre", `Divisões: ${names}`, "preparação por m²");
  if (job.crack_repair) line("Reparação de fissuras (abertura, tratamento e betumação)", "ml", crackMl, crackP, "main_oeuvre", "", "reparação de fissuras por metro");
  const ceilingTxt = (job.rooms || []).some(r => r.paint_ceiling) ? " e tetos" : "";
  line(`Pintura de paredes${ceilingTxt}${calc.coats ? ` — ${Math.trunc(calc.coats)} demãos` : ""}`, "m²", calc.surface_m2, labor, "main_oeuvre", `Divisões: ${names}`, "mão de obra de pintura por m²");
  if (job.supply_paint !== false) {
    if (pc !== null && calc.cans !== null) line(`Tinta — ${calc.cans} embalagem(ns) de ${calc.can_size_l} L`, "u", calc.cans, pc, "fourniture", `${calc.liters} L calculados (${calc.formula})`);
    else line("Tinta", "L", calc.liters, pl, "fourniture", calc.liters !== null ? calc.formula : "Quantidade por confirmar", "tinta por litro");
  }
  const totals = { ht: r2(lines.filter(l => l.kind === "line").reduce((s, l) => s + l.qty * l.unit_price_ht, 0)) };
  return { lines, calc, to_confirm: [...new Set(toConfirm)], totals };
}

// Registo diário (mesmas regras de engines/field_records.parse_daily)
const NUM = { um: 1, uma: 1, dois: 2, duas: 2, tres: 3, quatro: 4, cinco: 5, seis: 6, sete: 7, oito: 8, nove: 9, dez: 10 };
const DONE = ["coloc", "pint", "assent", "acab", "termin", "fiz", "fizemos", "mont", "instal", "reboc", "demol", "limp", "betum", "lix", "aplic", "lig", "pass", "abri", "fech", "subst", "repar", "comec"];
const norm = s => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const count = t => (/^\d+$/.test(t) ? Number(t) : NUM[norm(t)] ?? null);

function clauses(raw) {
  const out = [];
  for (const part of raw.split(/[,.;\n]/)) {
    const pieces = part.split(/\s+e\s+/);
    let cur = pieces[0];
    for (const nxt of pieces.slice(1)) {
      const first = nxt.trim() ? norm(nxt).split(" ")[0] : "";
      if (DONE.some(v => first.startsWith(v)) || ["falt", "acab", "ficam"].some(v => first.startsWith(v))) { out.push(cur); cur = nxt; }
      else cur = `${cur} e ${nxt}`;
    }
    out.push(cur);
  }
  return out;
}

export function parseDaily(text) {
  const raw = String(text || "").trim().slice(0, 3000);
  if (!raw) throw new CalcError("Escreva ou dite o que se passou hoje.");
  const t = norm(raw);
  const ambiguous = [];
  let workers = null;
  const m = t.match(/\b(?:fomos|eramos|estivemos|estavamos|somos)\s+(\w+)/) || t.match(/\b(\w+)\s+(?:trabalhadores|pessoas|operarios|homens)\b/);
  if (m) workers = count(m[1]);
  if (workers === null && /\beu e (?:o|a)\s+\w+/.test(t)) workers = 2;
  if (workers === null) ambiguous.push(/\b(?:fomos|eramos|estivemos)\b/.test(t) ? "Número de pessoas na equipa" : "Número de pessoas na equipa (não indicado)");
  let hours = null;
  const span = t.match(/das\s+(\d{1,2})(?:h|:\d{2})?\s*(?:h)?\s*(?:as|ate)\s+(\d{1,2})/);
  const h = t.match(/(\d{1,2})\s*(?:h|horas)\b(?!\s*(?:as|da|de))/);
  if (span) { const a = +span[1], b = +span[2]; if (a >= 0 && a < b && b <= 24) { hours = b - a; ambiguous.push("Horas: calculadas pelo intervalo indicado — confirme se houve pausa"); } }
  else if (h) hours = +h[1] > 0 && +h[1] <= 24 ? +h[1] : null;
  const missing = [];
  for (const mm of t.matchAll(/\b(?:faltou|faltaram|falta|faltam|acabou|acabaram|ficamos sem|precisamos de)\s+(?:o |a |os |as |de |mais )?([^,.;]+)/g)) {
    const item = mm[1].trim().split(/\s+(?:e|mas|porque|para)\s+/)[0].trim();
    if (item && item.length < 80) { const i = norm(raw).indexOf(item); missing.push({ item: i >= 0 ? raw.slice(i, i + item.length) : item, quantity: null }); }
  }
  if (missing.length) ambiguous.push("Quantidade dos materiais em falta (não indicada)");
  const done = [];
  for (const c of clauses(raw)) {
    const n = norm(c).trim();
    if (!n || ["hoje fomos", "fomos", "eramos", "estivemos"].some(p => n.startsWith(p))) continue;
    if (/\b(?:faltou|faltaram|falta|faltam|acabou|ficamos sem)\b/.test(n)) continue;
    if (DONE.some(v => new RegExp(`\\b${v}\\w*`).test(n))) done.push(c.trim().slice(0, 200));
  }
  return { workers, hours, work_done: done, missing_materials: missing, blockers: [], ambiguous, source_text: raw, requires_confirmation: true };
}
