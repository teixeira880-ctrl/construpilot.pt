// Regras de recomendação (cópia fiel de backend/engines/connect/recommend.py) para o modo offline do stand.
// O servidor continua a ser a referência para o CRM. A paridade é verificada por cases.json (pytest + jest).
import catalog from "./catalog.json";

export const PUBLIC_STATUSES = ["VERIFICADA", "PARCIAL"];

const byId = (list) => Object.fromEntries(list.map((x) => [x.id, x]));
export const CAPS = byId(catalog.capabilities);
export const PAINS = byId(catalog.pains);
export const ACTIVITIES = byId(catalog.activities);
export const DEMOS = byId(catalog.demos);

export function primaryCase(pains) {
  for (const pid of pains) {
    const c = PAINS[pid] && PAINS[pid].case;
    if (c) return c;
  }
  return "GENERAL";
}

function casesFor(pains) {
  const out = [];
  for (const pid of pains) {
    const c = PAINS[pid] && PAINS[pid].case;
    if (c && !out.includes(c)) out.push(c);
  }
  return out;
}

export function recommendClient(answers) {
  const act = ACTIVITIES[answers.activity || ""] || { group: "other" };
  const group = act.group || "other";
  const track = act.track || null;
  const pains = (answers.pains || []).filter((p) => PAINS[p]).slice(0, 3);
  const deep = answers.deep || {};

  const ordered = [];
  const reasons = {};
  for (const pid of pains) {
    for (const cid of PAINS[pid].capabilities) {
      if (!PUBLIC_STATUSES.includes(CAPS[cid].status)) continue;
      (reasons[cid] = reasons[cid] || []).push(pid);
      if (!ordered.includes(cid)) ordered.push(cid);
    }
  }
  if (!ordered.length) {
    for (const cid of ["cap_takeoff", "cap_quote", "cap_margin"]) {
      ordered.push(cid);
      reasons[cid] = reasons[cid] || [];
    }
  }
  if (group === "private") {
    // ordenação estável igual à do Python (sort com chave 0/1)
    const first = ordered.filter((c) => c === "cap_quantities" || c === "cap_takeoff");
    const rest = ordered.filter((c) => !(c === "cap_quantities" || c === "cap_takeoff"));
    ordered.splice(0, ordered.length, ...first, ...rest);
  }
  const capabilities = ordered.slice(0, 5).map((id) => ({ id, status: CAPS[id].status, pains: reasons[id] }));

  const c = primaryCase(pains);
  let demo = null;
  if (track && catalog.track_demo[track] && ["A", "B", "GENERAL"].includes(c)) demo = catalog.track_demo[track];
  if (!demo && catalog.case_demo[c]) demo = catalog.case_demo[c];
  if (!demo) demo = catalog.track_demo[group] || "demo_quote";
  const alternatives = [];
  for (const k of casesFor(pains)) {
    const d = catalog.case_demo[k];
    if (d !== demo && !alternatives.includes(d)) alternatives.push(d);
  }
  for (const d of ["demo_takeoff", "demo_quote", "demo_margin"]) {
    if (alternatives.length >= 3) break;
    if (d !== demo && !alternatives.includes(d)) alternatives.push(d);
  }

  const tool = typeof deep.tools === "string" ? deep.tools : null;
  const currentKey = tool && catalog.process.current[tool] ? tool : null;
  const withKey = { D: "with_tracking", E: "with_billing" }[c] || "with";

  const rng = byId(catalog.ranges.quotes_per_month);
  const qpm = (answers.volume || {}).quotes_per_month;
  let hours = null;
  for (const q of catalog.deep_questions.B) {
    if (q.id === "b_time") for (const o of q.options) if (o.id === deep.b_time) hours = o.hours;
  }

  return {
    profile: "client",
    activity: answers.activity || null,
    group,
    track,
    pains,
    primary_case: c,
    capabilities,
    demo,
    alternative_demos: alternatives.slice(0, 3),
    process: { current: currentKey, with: withKey },
    value_defaults: { quotes_per_month: rng[qpm] ? rng[qpm].mid : null, hours_per_quote: hours, hourly_cost: null },
    needs_human_review: pains.includes("p_other") || Boolean((answers.other_text || "").trim()),
    catalog_version: catalog.version,
  };
}

export function recommendInvestor() {
  return {
    profile: "investor", demo: "demo_quote", alternative_demos: ["demo_takeoff", "demo_margin"],
    sections: ["overview", "problem", "solution", "segments", "model", "traction", "risks", "meeting"],
    catalog_version: catalog.version,
  };
}

export function recommendPartner(answers) {
  const cap = catalog.partner.use_cases[answers.partner_type] || "cap_quote";
  const d = catalog.demos.find((x) => x.capabilities.includes(cap) && x.kind === "engine");
  const demo = d ? d.id : "demo_quote";
  return {
    profile: "partner", use_case: cap, use_case_status: CAPS[cap].status, demo,
    alternative_demos: ["demo_quote", "demo_takeoff", "demo_margin"].filter((x) => x !== demo).slice(0, 2),
    catalog_version: catalog.version,
  };
}

export function recommend(profile, answers) {
  if (profile === "client") return recommendClient(answers);
  if (profile === "investor") return recommendInvestor(answers);
  if (profile === "partner") return recommendPartner(answers);
  throw new Error("perfil inválido");
}

/** Perguntas do diagnóstico efetivamente apresentadas, por perfil de atividade e modo. */
export function deepQuestionsFor(answers, mode) {
  const pains = answers.pains || [];
  const c = primaryCase(pains);
  const qs = catalog.deep_questions[c] || catalog.deep_questions.GENERAL;
  const act = ACTIVITIES[answers.activity || ""] || {};
  const list = [];
  if (act.track && catalog.track_questions[act.track]) list.push({ ...catalog.track_questions[act.track], track: true });
  const chosen = mode === "deep" ? qs : qs.filter((q) => q.quick);
  for (const q of chosen) list.push(q);
  // modo rápido: no máximo 2 perguntas de diagnóstico para manter 5–7 perguntas no total
  if (mode === "deep") {
    for (const extra of casesFor(pains).slice(1)) {
      for (const q of catalog.deep_questions[extra]) if (!list.some((x) => x.id === q.id)) list.push(q);
    }
    return list;
  }
  return list.slice(0, mode === "stand" ? 1 : 2);
}

export function optionsOf(q) {
  return q.options === "@tools" ? catalog.tools : q.options;
}

export { catalog };
