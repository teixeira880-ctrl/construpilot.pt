import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Building2, Calculator, FileDown, Loader2, Plus, Trash2 } from "lucide-react";
import StructureAutomationPanel from "./StructureAutomationPanel";
import StructureDrawingsPanel from "./StructureDrawingsPanel";
import StructureManualPanels from "./StructureManualPanels";
import StructureLintelPanel, { DEFAULT_LINTEL } from "./StructureLintelPanel";

const BASE = "/structuro/calc/studies";
const TYPES = { slab: "Laje", beam: "Viga", wall: "Parede", column: "Pilar", footing: "Sapata" };
const COLORS = { slab: "#b9c9c0", beam: "#b46b42", wall: "#17574b", column: "#9d3e26", footing: "#837466" };
const number = value => value === "" ? null : Number(value);
const errorMessage = e => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Verifique os valores e os campos obrigatórios.";
const emptySource = () => ({ document: "", page: null, note: "" });
const blankElement = id => ({ id, kind: "wall", level: "R/C", material: "A precisar", length_m: null, width_m: null, height_m: null,
  x_m: null, y_m: null, angle_deg: 0, density_kn_m3: null, ei_kn_m2: null, source: emptySource(), mechanics_source: emptySource(),
  reviewed: false, loads: [], supports: [] });
const selectClass = "border rounded-md p-2 bg-background text-sm w-full";

function Plan({ model, level }) {
  const elements = model.elements.filter(e => e.level === level);
  const placed = elements.filter(e => [e.x_m, e.y_m, e.length_m, e.width_m].every(v => v !== null && Number.isFinite(v)) && e.length_m > 0 && e.width_m > 0);
  const shapes = placed.map(e => {
    const a = e.angle_deg * Math.PI / 180;
    return { e, pts: [[0, 0], [e.length_m, 0], [e.length_m, e.width_m], [0, e.width_m]].map(([x, y]) =>
      [e.x_m + x * Math.cos(a) - y * Math.sin(a), -(e.y_m + x * Math.sin(a) + y * Math.cos(a))]) };
  });
  const points = shapes.flatMap(s => s.pts);
  if (!points.length) return <p className="py-16 text-center text-muted-foreground">Indique as coordenadas x/y e as dimensões para desenhar este piso.</p>;
  const xmin = Math.min(...points.map(p => p[0])), xmax = Math.max(...points.map(p => p[0]));
  const ymin = Math.min(...points.map(p => p[1])), ymax = Math.max(...points.map(p => p[1]));
  const span = Math.max(xmax - xmin, ymax - ymin, 1), pad = span * .12;
  return <><svg role="img" aria-label={`Planta de princípio ${level}`} className="w-full h-80 bg-[#f8faf7] rounded-xl border" viewBox={`${xmin - pad} ${ymin - pad} ${xmax - xmin + 2 * pad} ${ymax - ymin + 2 * pad}`}>
    {shapes.sort((a, b) => Number(a.e.kind !== "slab") - Number(b.e.kind !== "slab")).map(({ e, pts }) => <g key={e.id}>
      <polygon points={pts.map(p => p.join(",")).join(" ")} fill={COLORS[e.kind]} fillOpacity=".14" stroke={COLORS[e.kind]} strokeWidth={span / 220} strokeDasharray={e.reviewed ? undefined : `${span / 60} ${span / 90}`} />
      <text x={pts.reduce((s, p) => s + p[0], 0) / 4} y={pts.reduce((s, p) => s + p[1], 0) / 4} textAnchor="middle" fontSize={span / 35} fill="#173c32">{e.id}</text>
    </g>)}
  </svg><p className="text-xs text-muted-foreground mt-2">Coordenadas em metros, canto inferior esquerdo local. {elements.length - placed.length} elemento(s) sem implantação. Tracejado: a confirmar.</p></>;
}

function ElementEditor({ element: e, model, update }) {
  const set = (key, value) => update({ ...e, [key]: value, reviewed: key === "reviewed" ? value : false });
  const editLoad = (i, patch) => set("loads", e.loads.map((x, k) => k === i ? { ...x, ...patch } : x));
  const editSupport = (i, patch) => set("supports", e.supports.map((x, k) => k === i ? { ...x, ...patch } : x));
  return <Card className="p-5 space-y-5">
    <div className="flex items-center gap-3"><b>{e.id}</b><select aria-label="Natureza" className={selectClass} value={e.kind} onChange={ev => update({ ...e, kind: ev.target.value, reviewed: false, supports: [], loads: [] })}>
      {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      <Input aria-label="Piso" value={e.level} onChange={ev => set("level", ev.target.value)} /></div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {[["length_m", "Comprimento (m)"], ["width_m", "Largura (m)"], ["height_m", "Altura / espessura (m)"], ["density_kn_m3", "Peso volúmico (kN/m³)"],
        ["x_m", "Origem x (m)"], ["y_m", "Origem y (m)"], ["angle_deg", "Rotation (°)"], ...(e.kind === "beam" ? [["ei_kn_m2", "Rigidez EI (kN.m²), opcional"]] : [])].map(([key, title]) =>
        <label className="text-xs space-y-1" key={key}>{title}<Input type="number" step="any" value={e[key] ?? ""} onChange={ev => set(key, number(ev.target.value))} /></label>)}
    </div>
    <label className="block text-xs space-y-1">Material<Input value={e.material} onChange={ev => set("material", ev.target.value)} /></label>
    {e.source.document && <p className="text-xs text-muted-foreground">Fonte: {e.source.document} · page {e.source.page ?? "a precisar"}</p>}
    <label className="block text-xs space-y-1">Fonte das dimensões / controlo das cotas<Input value={e.source.note} onChange={ev => set("source", { ...e.source, note: ev.target.value })} placeholder="Planta, página, cota ou levantamento no local" /></label>
    <label className="block text-xs space-y-1">Justificação mecânica<Input value={e.mechanics_source.note} onChange={ev => set("mechanics_source", { ...e.mechanics_source, note: ev.target.value })} placeholder="Peso volúmico, rigidez adotada, distribuição e apoios centrados" /></label>
    <section className="space-y-2"><h3 className="font-medium text-sm">Cargas adicionadas ao peso próprio</h3>
      <p className="text-xs text-muted-foreground">O peso próprio é calculado separadamente. Não o introduza uma segunda vez. Sem linha: nenhum outro carregamento.</p>
      {e.loads.map((load, i) => <div className="grid md:grid-cols-6 gap-2 border rounded p-2" key={i}>
        <select aria-label="Ação" className={selectClass} value={load.action} onChange={ev => editLoad(i, { action: ev.target.value })}>{model.actions.map(a => <option key={a.id}>{a.id}</option>)}</select>
        <select aria-label="Distribuição" className={selectClass} value={load.mode} onChange={ev => editLoad(i, { mode: ev.target.value, position_m: null })}>
          <option value="point">Pontual (kN)</option>{["wall", "beam"].includes(e.kind) && <option value="line">Linear (kN/m)</option>}{e.kind === "slab" && <option value="surface">Surfacique (kN/m²)</option>}
        </select>
        <Input aria-label="Valor da carga" type="number" min="0" step="any" value={load.value ?? ""} onChange={ev => editLoad(i, { value: number(ev.target.value) })} />
        {e.kind === "beam" && load.mode === "point" ? <Input aria-label="Posição a partir do apoio esquerdo (m)" placeholder="Position (m)" type="number" step="any" value={load.position_m ?? ""} onChange={ev => editLoad(i, { position_m: number(ev.target.value) })} /> : <span />}
        <Input aria-label="Fonte da carga" placeholder="Justificação da carga" value={load.source.note} onChange={ev => editLoad(i, { source: { ...load.source, note: ev.target.value } })} />
        <Button variant="ghost" onClick={() => set("loads", e.loads.filter((_, k) => k !== i))}>Remover</Button>
      </div>)}
      <Button variant="outline" size="sm" onClick={() => set("loads", [...e.loads, { action: model.actions[0]?.id || "G", mode: "point", value: null, position_m: null, source: emptySource() }])}>Adicionar uma carga</Button>
    </section>
    {e.kind !== "footing" && <section className="space-y-2"><h3 className="font-medium text-sm">Transferência para os apoios</h3>
      <p className="text-xs text-muted-foreground">{e.kind === "beam" ? "Dois apoios simples: esquerdo e depois direito. As reações são calculadas." : "Defina as frações tributárias. A sua soma deve ser igual a 1."}</p>
      {e.supports.map((s, i) => <div className="grid md:grid-cols-5 gap-2" key={i}>
        <select aria-label={`Apoio ${i + 1}`} className={selectClass} value={s.target} onChange={ev => editSupport(i, { target: ev.target.value, receiving: model.elements.find(x => x.id === ev.target.value)?.kind === "beam" ? "point" : "axial", position_m: null })}>
          <option value="">{`Escolher o apoio ${i + 1}`}</option>{model.elements.filter(x => x.id !== e.id && x.kind !== "slab").map(x => <option key={x.id} value={x.id}>{`${x.id} · ${TYPES[x.kind]}`}</option>)}</select>
        {e.kind !== "beam" ? <Input aria-label="Fração (0 a 1)" placeholder="Fraction" type="number" step="any" value={s.fraction ?? ""} onChange={ev => editSupport(i, { fraction: number(ev.target.value) })} /> : <span className="text-sm p-2">{i === 0 ? "Esquerda" : "Direita"}</span>}
        <select aria-label="Carga recebida pelo apoio" className={selectClass} value={s.receiving} onChange={ev => editSupport(i, { receiving: ev.target.value, position_m: null })}><option value="axial">Axial centrada</option><option value="uniform">Uniforme sobre viga</option><option value="point">Pontual sobre viga</option></select>
        {s.receiving === "point" ? <Input aria-label="Posição na viga recetora (m)" placeholder="Position (m)" type="number" step="any" value={s.position_m ?? ""} onChange={ev => editSupport(i, { position_m: number(ev.target.value) })} /> : <span />}
        <Button variant="ghost" onClick={() => set("supports", e.supports.filter((_, k) => k !== i))}>Remover</Button>
      </div>)}
      <Button variant="outline" size="sm" disabled={e.kind === "beam" && e.supports.length >= 2} onClick={() => set("supports", [...e.supports, { target: "", fraction: e.kind === "beam" ? null : 1, receiving: "axial", position_m: null }])}>Adicionar um apoio</Button>
    </section>}
    <label className="flex gap-2 text-sm"><input type="checkbox" checked={e.reviewed} onChange={ev => set("reviewed", ev.target.checked)} /> Controlei as dimensões, as cargas, o peso próprio e os apoios deste elemento.</label>
  </Card>;
}

export default function StructureCalc() {
  const [studies, setStudies] = useState([]), [plans, setPlans] = useState([]), [plan, setPlan] = useState("");
  const [study, setStudy] = useState(null), [model, setModel] = useState(null), [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null), [level, setLevel] = useState(""), [caseId, setCaseId] = useState("");
  const [progress, setProgress] = useState("");
  const [catalog, setCatalog] = useState(null), [cats, setCats] = useState({}), [sfreq, setSfreq] = useState(false), [envelope, setEnvelope] = useState(null);
  const [ec2cat, setEc2cat] = useState(null), [ec2res, setEc2res] = useState(null);
  const [ec2opts, setEc2opts] = useState({ fck: 25, fyk: 500, gamma_c: 1.5, gamma_s: 1.15, alpha_cc: 1.0, cot_theta: 2.5, cover_m: 0.05, bar_mm: 16, stirrup_mm: 8, legs: 2 });
  const [ec7cat, setEc7cat] = useState(null), [ec7res, setEc7res] = useState(null);
  const [ec7opts, setEc7opts] = useState({ mode: "drained", d_m: 0.5, gamma_soil: 18, c_kpa: 0, phi_deg: 30, cu_kpa: 0, gamma_Rv: 1.4, gamma_phi: 1.0, gamma_c: 1.0, gamma_cu: 1.0 });
  const [ec3cat, setEc3cat] = useState(null), [ec3res, setEc3res] = useState(null);
  const [ec3opts, setEc3opts] = useState({ profile: "IPE300", grade: "S235", section_class: "", gamma_m0: 1.0, gamma_m1: 1.0, buckling_curve: "", c1: 1.0, mcr_knm: "", k_buckling: 1.0, lcr_m: "", med_col_knm: "", cmy: 0.9, cm_lt: 0.9, lateral_restraint: false });
  const [ec5cat, setEc5cat] = useState(null), [ec5res, setEc5res] = useState(null);
  const [ec5opts, setEc5opts] = useState({ strength_class: "C24", service_class: "1", load_duration: "medium", gamma_m: "", lef_m: "", kcr: 0.67, ksys: 1.0 });
  const [spans, setSpans] = useState({});
  const [slsopts, setSlsopts] = useState({ ratio_char: 250, ratio_qp: 300 }), [slsres, setSlsres] = useState(null);
  const [crackopts, setCrackopts] = useState({ w_max_mm: 0.3 }), [crackres, setCrackres] = useState(null);
  const [ancopts, setAncopts] = useState({ bond: "good", rho1_pct: 50, alpha1: 1.0, alpha3: 1.0, alpha4: 1.0, alpha5: 1.0 }), [ancres, setAncres] = useState(null);
  const [dossierInc, setDossierInc] = useState({ ec2: true, crack: true, anchorage: false, ec3: false, ec5: false, ec7: true, sls: true, reinforcement: true, architecture: true, linked: true, lintel: false });
  const [lintelOpts, setLintelOpts] = useState(DEFAULT_LINTEL);
  const utilColor = s => s === "ok" ? "text-emerald-700" : s === "proche" ? "text-amber-700" : s === "a_revoir" ? "text-red-700 font-semibold" : "text-muted-foreground";
  const Util = ({ u }) => u ? <span className={utilColor(u.status)}>{u.ratio != null ? `${u.ratio} · ${u.label}` : u.label}</span> : <span className="text-muted-foreground">—</span>;
  const dirty = !!study && JSON.stringify(model) !== JSON.stringify(study.model);
  const refresh = async () => {
    const [a, b] = await Promise.all([api.get(BASE), api.get("/takeoffs")]);
    setStudies(a.data.studies); setPlans(b.data.plans || []);
  };
  useEffect(() => { refresh().catch(() => toast.error("Carregamento dos estudos impossível")); }, []);
  useEffect(() => { api.get("/structuro/calc/combinations/catalog").then(r => setCatalog(r.data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/structuro/calc/ec2/catalog").then(r => setEc2cat(r.data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/structuro/calc/ec7/catalog").then(r => setEc7cat(r.data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/structuro/calc/ec3/catalog").then(r => setEc3cat(r.data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/structuro/calc/ec5/catalog").then(r => setEc5cat(r.data)).catch(() => {}); }, []);
  const apply = data => { setStudy(data); setModel(data.model); setLevel(v => v || data.model.elements[0]?.level || "R/C"); };
  const task = async fn => { setBusy(true); try { await fn(); } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); setProgress(""); } };
  const create = (demonstration, drawingDemo = false, autoDemo = false) => task(async () => { const { data } = await api.post(BASE, { demonstration, drawing_demonstration: drawingDemo, automation_demonstration: autoDemo, plan_id: demonstration || drawingDemo || autoDemo ? null : plan || null }); apply(data); setSelected(null); await refresh(); });
  const save = () => task(async () => {
    const { data } = await api.put(`${BASE}/${study.study_id}`, { expected_revision: study.revision, model });
    apply(data); await refresh(); toast.success(data.result.status === "blocked" ? "Estudo guardado; dados a completar" : "Cálculo mecânico efetuado; resistência a verificar");
  });
  const saveModel = nextModel => task(async () => {
    const { data } = await api.put(`${BASE}/${study.study_id}`, { expected_revision: study.revision, model: nextModel });
    apply(data); await refresh(); toast.success("Reações da padieira reinjetadas na descida de cargas");
  });
  const readAll = () => task(async () => {
    let current = study, failures = [];
    for (let page = 1; page <= study.page_count; page++) {
      if (current.page_readings[String(page)]) continue;
      setProgress(`Leitura da página ${page} / ${study.page_count}`);
      try {
        const { data } = await api.post(`${BASE}/${study.study_id}/read-page`, { expected_revision: current.revision, page }, { timeout: 95000 });
        current = data; apply(data);
      } catch (e) { if (e?.response?.status === 409) throw e; failures.push(page); }
    }
    if (failures.length) toast.error(`Páginas não lidas: ${failures.join(", ")}. Pode relançar as páginas restantes.`);
    else toast.success("Páginas lidas; verifique e selecione os elementos a reter.");
  });
  const download = fmt => task(async () => {
    const ext = { aciers: "pdf", plans: "pdf", nomenclature: "csv", dossier: "zip" }[fmt] || fmt;
    const { data } = await api.get(`${BASE}/${study.study_id}/export/${fmt}`, { responseType: "blob", params: { expected_revision: study.revision } });
    const url = URL.createObjectURL(data), a = document.createElement("a"); a.href = url; a.download = `structure-${fmt}-r${study.revision}.${ext}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const automate = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/automate`, { expected_revision: study.revision, model }, { timeout: 95000 });
    apply(data); toast.success("Processo automático gerado (indicativo) · a validar pelo engenheiro");
  });
  const qActions = () => (model?.actions || []).filter(a => a.kind === "Q");
  const genCombos = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/combinations/generate`, { expected_revision: study.revision, categories: cats, options: { uls: true, sls_char: true, sls_freq: sfreq, sls_qp: true }, apply: true });
    apply(data.study); await refresh(); toast.success(`${data.generated.length} combinação(ões) NP EN 1990 gerada(s) · a verificar pelo engenheiro`);
  });
  useEffect(() => {
    if (!study || JSON.stringify(model) !== JSON.stringify(study?.model)) { setEnvelope(null); setEc2res(null); setEc7res(null); setEc3res(null); setEc5res(null); setSlsres(null); setCrackres(null); setAncres(null); return; }
    api.get(`${BASE}/${study.study_id}/design`).then(r => setEnvelope(r.data)).catch(() => setEnvelope(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [study?.study_id, study?.revision]);
  useEffect(() => {
    const beams = ((study?.model?.elements) || []).filter(e => e.kind === "beam");
    setSpans(Object.fromEntries(beams.map(b => [b.id, b.length_m != null ? b.length_m : ""])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [study?.study_id]);
  const beamPlanLen = id => { const e = ((study?.model?.elements) || []).find(x => x.id === id); return e && e.length_m != null ? e.length_m : null; };
  const spansPayload = () => Object.fromEntries(Object.entries(spans).filter(([id, v]) => { if (v === "" || v == null) return false; const pl = beamPlanLen(id); return pl == null || Number(v) !== pl; }).map(([k, v]) => [k, Number(v)]));
  const designEc2 = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec2/design`, ec2opts);
    setEc2res(data); toast.success("Armaduras NP EN 1992 calculadas · a verificar pelo engenheiro");
  });
  const exportFerraillage = () => task(async () => {
    const res = await api.post(`${BASE}/${study.study_id}/export/ferraillage`, ec2opts, { responseType: "blob" });
    const url = URL.createObjectURL(res.data), a = document.createElement("a"); a.href = url; a.download = `ferraillage-r${study.revision}.pdf`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success("Nota de armaduras PDF transferida");
  });
  const designEc7 = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec7/design`, ec7opts);
    setEc7res(data); toast.success("Capacidade resistente NP EN 1997 (indicativo) · a verificar pelo engenheiro");
  });
  const ec3Payload = () => ({ profile: ec3opts.profile, grade: ec3opts.grade, section_class: ec3opts.section_class === "" ? null : Number(ec3opts.section_class), gamma_m0: Number(ec3opts.gamma_m0), gamma_m1: Number(ec3opts.gamma_m1), buckling_curve: ec3opts.buckling_curve === "" ? null : ec3opts.buckling_curve, c1: Number(ec3opts.c1), mcr_knm: ec3opts.mcr_knm === "" ? null : Number(ec3opts.mcr_knm), spans: spansPayload(), k_buckling: Number(ec3opts.k_buckling), lcr_m: ec3opts.lcr_m === "" ? null : Number(ec3opts.lcr_m), med_col_knm: ec3opts.med_col_knm === "" ? 0 : Number(ec3opts.med_col_knm), cmy: Number(ec3opts.cmy), cm_lt: Number(ec3opts.cm_lt), lateral_restraint: !!ec3opts.lateral_restraint });
  const ancPayload = () => ({ ...ec2opts, bond: ancopts.bond, rho1_pct: Number(ancopts.rho1_pct), alpha1: Number(ancopts.alpha1), alpha3: Number(ancopts.alpha3), alpha4: Number(ancopts.alpha4), alpha5: Number(ancopts.alpha5) });
  const ec5Payload = () => ({ ...ec5opts, gamma_m: ec5opts.gamma_m === "" ? null : Number(ec5opts.gamma_m), lef_m: ec5opts.lef_m === "" ? null : Number(ec5opts.lef_m) });
  const slsPayload = () => ({ ratio_char: Number(slsopts.ratio_char), ratio_qp: Number(slsopts.ratio_qp), spans: spansPayload() });
  const crackPayload = () => ({ ...ec2opts, w_max_mm: Number(crackopts.w_max_mm) });
  const designEc3 = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec3/design`, ec3Payload());
    setEc3res(data); toast.success("Verificação do aço NP EN 1993 (indicativo) · a verificar");
  });
  const designSls = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/sls/deflection`, slsPayload());
    setSlsres(data); toast.success("Flechas ELS calculadas (indicativo) · a verificar");
  });
  const designEc5 = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec5/design`, ec5Payload());
    setEc5res(data); toast.success("Verificação da madeira NP EN 1995 (indicativo) · a verificar");
  });
  const designCrack = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec2/crack`, crackPayload());
    setCrackres(data); toast.success("Fendilhação NP EN 1992 calculada (indicativo) · a verificar");
  });
  const designAnchorage = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec2/anchorage`, ancPayload());
    setAncres(data); toast.success("Amarrações e emendas NP EN 1992 calculadas (indicativo) · a verificar");
  });
  const exportDossier = () => task(async () => {
    const include = Object.entries(dossierInc).filter(([, v]) => v).map(([k]) => k);
    const body = { include, ec2: ec2opts, ec3: ec3Payload(), ec5: ec5Payload(), ec7: ec7opts, sls: slsPayload(), crack: crackPayload(), anchorage: ancPayload(), lintel: lintelOpts.clear_span_m ? lintelOpts : undefined };
    const res = await api.post(`${BASE}/${study.study_id}/export/dossier`, body, { responseType: "blob" });
    const url = URL.createObjectURL(res.data), a = document.createElement("a"); a.href = url; a.download = `dossier-bet-r${study.revision}.pdf`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success("Processo de engenharia PDF transferido");
  });
  const updateElement = e => setModel(m => ({ ...m, gravity_model_reviewed: false, elements: m.elements.map(x => x.id === e.id ? e : x) }));
  const add = candidate => {
    if (model.elements.some(e => e.id === candidate.id)) return;
    setModel(m => ({ ...m, gravity_model_reviewed: false, elements: [...m.elements, candidate] })); setSelected(candidate.id); setLevel(candidate.level);
  };
  const result = !dirty ? study?.result : null;
  const activeCase = result?.cases.find(c => c.id === caseId) || result?.cases[0];
  const active = model?.elements.find(e => e.id === selected);
  return <div className="max-w-7xl mx-auto p-4 md:p-8 space-y-6" data-testid="structure-calc">
    <header className="flex flex-wrap justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-emerald-800">ConstruPilot · Structure</p>
      <h1 className="text-3xl font-semibold mt-2 flex gap-2 items-center"><Building2 /> Do projeto de licenciamento ao modelo estrutural</h1>
      <p className="text-sm text-muted-foreground mt-2">Leitura das plantas, cálculo gravítico e plantas de princípio com fontes.</p></div><a href="/structuro" className="text-sm underline">Espaço estrutura</a></header>
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"><b>Versão preliminar.</b> O motor calcula esforços no modelo introduzido. Ainda não dimensiona as secções nem as armaduras. Solo, estabilidade, resistência e sismo continuam a ser verificados por um engenheiro de estruturas.</div>
    {busy && <p role="status" className="flex items-center gap-2"><Loader2 className="animate-spin h-4 w-4" />{progress || "Traitement en cours…"}</p>}
    <fieldset disabled={busy} className="space-y-6 disabled:opacity-70">
      {!study ? <>
        <Card className="p-5 space-y-4"><h2 className="font-semibold">Começar a partir do seu projeto de licenciamento</h2><select className={selectClass} aria-label="PC source" value={plan} onChange={ev => setPlan(ev.target.value)}><option value="">Estudo vazio / introdução manual</option>{plans.map(p => <option key={p.plan_id} value={p.plan_id}>{p.filename}</option>)}</select>
          <div className="flex flex-wrap gap-2"><Button onClick={() => create(false)} data-testid="create-study-btn">Criar o estudo</Button><Button variant="outline" onClick={() => create(true)} data-testid="open-demo-study-btn">Abrir um exemplo fictício</Button><Button variant="outline" onClick={() => create(false, false, true)} data-testid="open-automation-demo-btn">Exemplo automático (processo)</Button><a className="text-sm underline p-2" href="/plan">Importar um novo projeto de licenciamento</a></div></Card>
        <div className="grid md:grid-cols-2 gap-3">{studies.map(s => <button key={s.study_id} className="text-left border rounded-lg p-4" onClick={() => task(async () => { const { data } = await api.get(`${BASE}/${s.study_id}`); apply(data); })}><b>{s.model.title}</b><p className="text-xs text-muted-foreground">Revisão {s.revision}</p></button>)}</div>
      </> : <>
        <div className="flex flex-wrap gap-2 items-center"><Button variant="ghost" disabled={dirty} onClick={() => { setStudy(null); setModel(null); setSelected(null); setLevel(""); }}>Os meus estudos</Button>
          <Input className="max-w-md" aria-label="Título do estudo" value={model.title} onChange={ev => setModel({ ...model, title: ev.target.value })} />
          <Button onClick={save}><Calculator className="h-4 w-4 mr-2" />Guardar e calcular</Button>
          <Button variant="outline" disabled={dirty} onClick={() => download("pdf")}><FileDown className="h-4 w-4 mr-2" />PDF</Button><Button variant="outline" disabled={dirty} onClick={() => download("dxf")}>DXF</Button>
          <span className="text-xs">{dirty ? "Alterações não guardadas · resultados ocultos" : `Revisão ${study.revision}`}</span>
          {dirty && <Button variant="ghost" onClick={() => setModel(study.model)}>Anular as alterações</Button>}
        </div>
        {study.plan_id && <Card className="p-5 space-y-3"><h2 className="font-semibold">Leitura do projeto de licenciamento: {Object.keys(study.page_readings).length} / {study.page_count} pages</h2>
          <p className="text-xs text-muted-foreground">Os candidatos ainda não são elementos estruturais validados. Verifique os duplicados entre plantas, cortes e alçados antes de os adicionar.</p>
          <Button variant="outline" disabled={dirty} onClick={readAll}>Ler as páginas restantes</Button>
          {Object.values(study.page_readings).map(read => <details key={read.page} className="border rounded p-3"><summary className="cursor-pointer">Página {read.page} · {read.kind} · {read.elements.length} candidats</summary>
            <ul className="text-sm list-disc ml-5 mt-3">{[...read.observations, ...read.missing].map((x, i) => <li key={i}>{x}</li>)}</ul>
            {read.elements.map(e => <div key={e.id} className="flex gap-3 items-center py-2"><span className="text-sm flex-1">{e.id} · {TYPES[e.kind]} · {e.level} · {e.length_m ?? "?"} × {e.width_m ?? "?"} × {e.height_m ?? "?"} m</span><Button size="sm" variant="outline" disabled={model.elements.some(x => x.id === e.id)} onClick={() => add(e)}>Adicionar ao modelo</Button></div>)}
          </details>)}
        </Card>}
        <div className="grid lg:grid-cols-[260px_1fr] gap-5"><Card className="p-4 space-y-3"><h2 className="font-semibold">Elementos estruturais</h2>
          <Button variant="outline" size="sm" onClick={() => { let n = model.elements.length + 1; while (model.elements.some(e => e.id === `E${n}`)) n++; add(blankElement(`E${n}`)); }}><Plus className="h-4 w-4" />Adicionar</Button>
          {model.elements.map(e => <div key={e.id} className={`flex items-center rounded border p-2 ${selected === e.id ? "bg-emerald-50 border-emerald-600" : ""}`}><button className="text-left flex-1 text-sm" onClick={() => { setSelected(e.id); setLevel(e.level); }}>{e.id} · {TYPES[e.kind]}<p className="text-xs text-muted-foreground">{e.level} · {e.reviewed ? "introdução confirmada" : "a confirmar"}</p></button><button aria-label={`Eliminar ${e.id}`} onClick={() => setModel({ ...model, gravity_model_reviewed: false, elements: model.elements.filter(x => x.id !== e.id) })}><Trash2 className="h-4 w-4" /></button></div>)}
        </Card><div className="space-y-4"><Card className="p-5"><div className="flex justify-between gap-3 mb-4"><h2 className="font-semibold">Planta de princípio · não executória</h2><select aria-label="Piso da planta" className="border rounded p-1 text-sm" value={level} onChange={ev => setLevel(ev.target.value)}>{[...new Set([level, ...model.elements.map(e => e.level)])].map(l => <option key={l}>{l}</option>)}</select></div><Plan model={model} level={level} /></Card>
          {active && <ElementEditor element={active} model={model} update={updateElement} />}
        </div></div>
        <Card className="p-5 space-y-3"><h2 className="font-semibold">Hipóteses do modelo</h2><p className="text-sm text-muted-foreground">Só gravidade, vigas sobre dois apoios simples, distribuição tributária das lajes e transferências axiais centradas. Esta escolha exclui nomeadamente os pórticos, as consolas e o contraventamento.</p>
          <textarea className="w-full border rounded p-3 text-sm" rows={3} aria-label="Hipóteses" placeholder="Justifique o esquema adotado e os seus limites" value={model.assumptions.join("\n")} onChange={ev => setModel({ ...model, gravity_model_reviewed: false, assumptions: ev.target.value.split("\n") })} />
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={model.gravity_model_reviewed} onChange={ev => setModel({ ...model, gravity_model_reviewed: ev.target.checked })} />Controlei o esquema estrutural, as transferências e a ausência de dupla contagem.</label>
          <details><summary className="text-sm cursor-pointer">Ações e combinações personalizadas (introdução técnica)</summary><p className="text-xs mt-2">G e Q são calculados separadamente. Uma combinação deve fornecer um coeficiente para cada ação e a sua justificação; nenhum coeficiente do Eurocódigo é aplicado automaticamente.</p>
            <JsonModel model={model} onChange={m => setModel({ ...m, gravity_model_reviewed: false })} />
          </details>
        </Card>
        {!dirty && <Card className="p-5 space-y-3" data-testid="eurocode-combos">
          <h2 className="font-semibold">Combinações Eurocódigo NP EN 1990</h2>
          <p className="text-sm text-muted-foreground">Gera as combinações ELU/ELS a partir das suas ações. Coeficientes usuais do Anexo Nacional português (γG=1,35 ; γQ=1,5 ; ψ por categoria) — <b>a verificar pelo engenheiro</b>. Nenhuma resistência é validada.</p>
          {qActions().length === 0 ? <p className="text-sm">Adicione pelo menos uma ação variável Q (e guarde) para gerar combinações.</p> : <div className="space-y-2">
            {qActions().map(q => <div key={q.id} className="flex flex-wrap items-center gap-2 text-sm"><span className="font-medium min-w-[7rem]">{q.label} ({q.id})</span>
              <select className={selectClass + " max-w-xs"} aria-label={`Categoria ${q.id}`} value={cats[q.id] || "A"} onChange={ev => setCats({ ...cats, [q.id]: ev.target.value })} data-testid={`combo-cat-${q.id}`}>{(catalog?.categories || [{ key: "A", label: "A — Habitation" }]).map(c => <option key={c.key} value={c.key}>{`${c.label} (ψ0=${c.psi0})`}</option>)}</select></div>)}
          </div>}
          <label className="flex gap-2 text-sm items-center"><input type="checkbox" checked={sfreq} onChange={ev => setSfreq(ev.target.checked)} data-testid="combo-sfreq" />Adicionar também a ELS frequente</label>
          <Button variant="outline" onClick={genCombos} disabled={qActions().length === 0} data-testid="combo-generate"><Calculator className="h-4 w-4 mr-2" />Gerar as combinações NP EN 1990</Button>
          {model.combinations.filter(c => /^EL[US]/.test(c.id)).length > 0 && <div className="text-xs space-y-1" data-testid="combo-list"><p className="font-medium">Combinações geradas (editáveis na introdução técnica):</p><ul className="list-disc ml-5 space-y-0.5">{model.combinations.filter(c => /^EL[US]/.test(c.id)).map(c => <li key={c.id}><b>{c.label}</b> — {Object.entries(c.factors).map(([k, v]) => `${k}×${v}`).join(" + ")}</li>)}</ul></div>}
        </Card>}
        {result && <Card className="p-5 space-y-4"><h2 className="font-semibold">{result.status === "blocked" ? "A completar antes do cálculo" : "Resultados mecânicos · resistência não verificada"}</h2>
          {result.issues.length > 0 && <ul className="list-disc ml-5 text-sm space-y-1">{result.issues.map((i, k) => <li key={k}><b>{i.element || "Modelo"}</b> : {i.message}</li>)}</ul>}
          {activeCase && <><select aria-label="Caso de carga" className={selectClass} value={activeCase.id} onChange={ev => setCaseId(ev.target.value)}>{result.cases.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select>
            <div className="flex flex-wrap gap-6 text-sm"><span>Cargas externas: <b>{activeCase.external_kn.toFixed(3)} kN</b></span><span>Reações no solo: <b>{activeCase.ground_kn.toFixed(3)} kN</b></span></div>
            <div className="overflow-auto"><table className="w-full text-sm"><thead><tr className="text-left border-b"><th className="p-2">Referência</th><th>Total (kN)</th><th>Esforços / pressões</th></tr></thead><tbody>{activeCase.elements.map(r => <tr key={r.id} className="border-b"><td className="p-2 font-medium">{r.id}</td><td>{r.total_kn.toFixed(3)}</td><td>{r.kind === "beam" ? `Mmax ${r.moment_max_knm.toFixed(3)} kN.m · Vmax ${r.shear_max_kn.toFixed(3)} kN` : r.kind === "footing" ? `q médio ${r.mean_pressure_kpa.toFixed(3)} kPa` : r.axial_stress_mpa !== undefined ? `σ médio ${r.axial_stress_mpa.toFixed(4)} MPa` : "Distribuição tributária"}</td></tr>)}</tbody></table></div>
          </>}
          {envelope && envelope.elements?.some(e => Object.keys(e.uls || {}).length || Object.keys(e.sls || {}).length) && <details data-testid="envelope-block" open><summary className="cursor-pointer text-sm font-medium">Combinação condicionante por elemento (envolvente NP EN 1990)</summary>
            <div className="overflow-auto mt-2"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Referência</th><th>ELU — effort dimensionnant</th><th>Combinação</th><th>ELS</th></tr></thead><tbody>{envelope.elements.filter(e => Object.keys(e.uls || {}).length || Object.keys(e.sls || {}).length).map(e => { const u = e.uls.moment_knm || e.uls.axial_kn || e.uls.pressure_kpa; const uk = e.uls.moment_knm ? `M ${e.uls.moment_knm.value} kN·m${e.uls.shear_kn ? ` · V ${e.uls.shear_kn.value} kN` : ""}` : e.uls.axial_kn ? `N ${e.uls.axial_kn.value} kN` : e.uls.pressure_kpa ? `q ${e.uls.pressure_kpa.value} kPa` : "—"; return <tr key={e.id} className="border-b"><td className="p-1 font-medium">{e.id}</td><td>{uk}</td><td>{u?.label || "—"}</td><td>{e.sls.deflection_mm ? `flecha ${e.sls.deflection_mm.value} mm` : "—"}</td></tr>; })}</tbody></table></div>
            <p className="text-[11px] text-muted-foreground mt-1">{envelope.note}</p></details>}
          <details><summary className="cursor-pointer text-sm">Domínio e limites do cálculo</summary><ul className="list-disc ml-5 text-xs mt-2 space-y-1">{result.limits.map(x => <li key={x}>{x}</li>)}</ul></details>
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="ec2-panel">
          <h2 className="font-semibold">NP EN 1992 — Armaduras de betão armado (vigas)</h2>
          <p className="text-sm text-muted-foreground">A partir do <b>momento e do esforço transverso condicionantes</b> da envolvente NP EN 1990, cálculo determinístico do aço necessário (flexão simples/dupla, esforço transverso, As mín./máx.). Coeficientes usuais do Anexo Nacional português, <b>a verificar pelo engenheiro</b>. Nenhuma resistência validada.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Classe do betão<select className={selectClass} value={ec2opts.fck} onChange={ev => setEc2opts({ ...ec2opts, fck: Number(ev.target.value) })} data-testid="ec2-fck">{(ec2cat?.concrete || [{ key: "C25/30", fck: 25 }]).map(c => <option key={c.key} value={c.fck}>{c.key}</option>)}</select></label>
            <label className="space-y-1">Aço fyk (MPa)<Input type="number" step="any" value={ec2opts.fyk} onChange={ev => setEc2opts({ ...ec2opts, fyk: Number(ev.target.value) })} data-testid="ec2-fyk" /></label>
            <label className="space-y-1">Recobrimento d' (m)<Input type="number" step="any" value={ec2opts.cover_m} onChange={ev => setEc2opts({ ...ec2opts, cover_m: Number(ev.target.value) })} data-testid="ec2-cover" /></label>
            <label className="space-y-1">γc<Input type="number" step="any" value={ec2opts.gamma_c} onChange={ev => setEc2opts({ ...ec2opts, gamma_c: Number(ev.target.value) })} /></label>
            <label className="space-y-1">γs<Input type="number" step="any" value={ec2opts.gamma_s} onChange={ev => setEc2opts({ ...ec2opts, gamma_s: Number(ev.target.value) })} /></label>
            <label className="space-y-1">cot θ (1 a 2,5)<Input type="number" step="any" value={ec2opts.cot_theta} onChange={ev => setEc2opts({ ...ec2opts, cot_theta: Number(ev.target.value) })} data-testid="ec2-cottheta" /></label>
          </div>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-xs border-t pt-3">
            <label className="space-y-1 col-span-3 md:col-span-6 text-muted-foreground">Planta de armaduras (proposta que cobre o As) — <b>disposições a verificar</b></label>
            <label className="space-y-1">Varões long. Ø (mm)<select className={selectClass} value={ec2opts.bar_mm} onChange={ev => setEc2opts({ ...ec2opts, bar_mm: Number(ev.target.value) })} data-testid="ec2-bar">{[8, 10, 12, 14, 16, 20, 25, 32].map(d => <option key={d} value={d}>{`Ø${d}`}</option>)}</select></label>
            <label className="space-y-1">Estribos Ø (mm)<select className={selectClass} value={ec2opts.stirrup_mm} onChange={ev => setEc2opts({ ...ec2opts, stirrup_mm: Number(ev.target.value) })} data-testid="ec2-stirrup">{[6, 8, 10, 12].filter(d => [8, 10, 12].includes(d)).map(d => <option key={d} value={d}>{`Ø${d}`}</option>)}</select></label>
            <label className="space-y-1">Ramos de estribo<select className={selectClass} value={ec2opts.legs} onChange={ev => setEc2opts({ ...ec2opts, legs: Number(ev.target.value) })} data-testid="ec2-legs">{[2, 3, 4].map(d => <option key={d} value={d}>{d}</option>)}</select></label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={designEc2} data-testid="ec2-design"><Calculator className="h-4 w-4 mr-2" />Calcular as armaduras NP EN 1992</Button>
            {ec2res && <Button variant="outline" onClick={exportFerraillage} data-testid="ec2-pdf"><FileDown className="h-4 w-4 mr-2" />Nota de armaduras (PDF)</Button>}
          </div>
          {ec2res && <div className="overflow-auto" data-testid="ec2-results">
            {ec2res.reinjected_from_automation && <p className="text-[11px] text-emerald-800 mb-1" data-testid="ec2-reinjected">Aços escolhidos pela cadeia automática reinjetados na verificação NP EN 1992 (processo de engenharia unificado).</p>}
            <table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Viga</th><th>b×h · d (m)</th><th>M dim → As flexion</th><th>V dim → Asw/s</th><th>As mini / maxi</th><th>Armaduras (a verificar)</th></tr></thead>
              <tbody>{ec2res.elements.map(r => r.status !== "ok"
                ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={5} className="text-amber-700">{r.message}</td></tr>
                : <tr key={r.id} className="border-b align-top">
                    <td className="p-1 font-medium">{r.id}</td>
                    <td>{r.b_m}×{r.h_m} · {r.d_m}</td>
                    <td><b>M {r.med_knm} kN·m</b> → <b>{r.design.flexure.as_req_cm2} cm²</b><div className="text-[10px] text-muted-foreground">{r.design.flexure.mode === "double" ? `double · As'=${r.design.flexure.as_comp_cm2} cm²` : "flexion simple"} · μ={r.design.flexure.mu}/{r.design.flexure.mu_lim} · {r.med_case}</div></td>
                    <td>{r.ved_kn != null ? <><b>V {r.ved_kn} kN</b> → <b>{r.design.shear.asw_s_req_cm2_m} cm²/m</b><div className="text-[10px] text-muted-foreground">{r.design.shear.needs_stirrups ? `estribos · cot θ=${r.design.shear.cot_theta} · s≤${r.design.shear.s_max_m} m` : `V_Rd,c=${r.design.shear.vrdc_kn} kN suficiente · mín.`}</div></> : "—"}</td>
                    <td>{r.design.flexure.as_min_cm2} / {r.design.flexure.as_max_cm2} cm²</td>
                    <td>{r.scheme ? <><b>{r.scheme.longitudinal.label}</b>{r.scheme.stirrups ? <> · {r.scheme.stirrups.label}</> : ""}{r.reinforcement_source === "automation" && <span data-testid={`ec2-auto-${r.id}`} className={`ml-1 text-[10px] font-semibold ${r.provided_ok ? "text-emerald-700" : "text-red-700"}`}>· auto {r.provided_ok ? "✓ suficiente" : "✗ insuficiente"}</span>}<div className="text-[10px] text-muted-foreground">As,prov {r.scheme.longitudinal.as_provided_cm2} cm² (req {r.scheme.longitudinal.as_req_cm2}){r.scheme.stirrups ? ` · ${r.scheme.stirrups.asw_s_prov_cm2_m} cm²/m` : ""}{r.reinforcement_source === "automation" ? " · aços automáticos reinjetados" : ""}</div></> : "—"}</td>
                  </tr>)}</tbody></table>
            {ec2res.elements.some(r => r.status === "ok" && (r.design.warnings || []).length) && <ul className="list-disc ml-5 mt-2 text-amber-700 text-[11px]" data-testid="ec2-warnings">{ec2res.elements.filter(r => r.status === "ok").flatMap(r => (r.design.warnings || []).map((w, i) => <li key={r.id + i}>{r.id} : {w}</li>))}</ul>}
            <p className="text-[11px] text-muted-foreground mt-1">{ec2res.note}</p>
          </div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="ec7-panel">
          <h2 className="font-semibold">NP EN 1997 — Capacidade resistente das fundações (sapatas)</h2>
          <p className="text-sm text-muted-foreground">A partir da <b>pressão condicionante</b> da envolvente NP EN 1990, capacidade resistente admissível (Anexo D, carga vertical centrada). Abordagem de cálculo 1 (Anexo Nacional português) por omissão. A razão q_Ed/q_Rd é <b>indicatif</b> — não vale como verificação regulamentar, a validar pelo engenheiro.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Regime<select className={selectClass} value={ec7opts.mode} onChange={ev => setEc7opts({ ...ec7opts, mode: ev.target.value })} data-testid="ec7-mode"><option value="drained">Drenado (c', φ')</option><option value="undrained">Não drenado (cu)</option></select></label>
            <label className="space-y-1">Encastrement D (m)<Input type="number" step="any" value={ec7opts.d_m} onChange={ev => setEc7opts({ ...ec7opts, d_m: Number(ev.target.value) })} /></label>
            <label className="space-y-1">γ sol (kN/m³)<Input type="number" step="any" value={ec7opts.gamma_soil} onChange={ev => setEc7opts({ ...ec7opts, gamma_soil: Number(ev.target.value) })} /></label>
            {ec7opts.mode === "drained" ? <>
              <label className="space-y-1">φ' (°)<Input type="number" step="any" value={ec7opts.phi_deg} onChange={ev => setEc7opts({ ...ec7opts, phi_deg: Number(ev.target.value) })} data-testid="ec7-phi" /></label>
              <label className="space-y-1">c' (kPa)<Input type="number" step="any" value={ec7opts.c_kpa} onChange={ev => setEc7opts({ ...ec7opts, c_kpa: Number(ev.target.value) })} /></label>
            </> : <label className="space-y-1">cu (kPa)<Input type="number" step="any" value={ec7opts.cu_kpa} onChange={ev => setEc7opts({ ...ec7opts, cu_kpa: Number(ev.target.value) })} data-testid="ec7-cu" /></label>}
            <label className="space-y-1">γR;v<Input type="number" step="any" value={ec7opts.gamma_Rv} onChange={ev => setEc7opts({ ...ec7opts, gamma_Rv: Number(ev.target.value) })} /></label>
          </div>
          <Button variant="outline" onClick={designEc7} data-testid="ec7-design"><Calculator className="h-4 w-4 mr-2" />Calcular a capacidade resistente NP EN 1997</Button>
          {ec7res && <div className="overflow-auto" data-testid="ec7-results"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Sapata</th><th>B×L (m)</th><th>q_Ed (kPa)</th><th>q_Rd (kPa)</th><th>Utilização q_Ed/q_Rd</th></tr></thead>
            <tbody>{ec7res.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={4} className="text-amber-700">{r.message || r.result?.message}</td></tr>
              : <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td>{r.result.B_m}×{r.result.L_m}</td><td>{r.result.q_ed_kpa}</td><td>{r.result.q_Rd_kpa}</td><td><Util u={r.result.utilisation} /></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{ec7res.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="spans-panel">
          <h2 className="font-semibold">Vãos das vigas</h2>
          <p className="text-sm text-muted-foreground">Automáticos segundo a planta (comprimento introduzido). As <b>flechas ELS</b> utilizam SEMPRE o vão da planta automaticamente. Este campo só serve para o <b>Mcr automático (NP EN 1993)</b> quando a planta não marca o comprimento de uma viga.</p>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
            {Object.keys(spans).length === 0 ? <span className="text-muted-foreground">Nenhuma viga no modelo.</span> : Object.entries(spans).map(([id, v]) => {
              const fromPlan = ((study?.model?.elements) || []).some(e => e.id === id && e.length_m != null);
              return <label key={id} className="space-y-1">{id} · L (m) <span className={fromPlan ? "text-emerald-700" : "text-amber-700"}>{fromPlan ? "da planta" : "a introduzir"}</span>
                <Input type="number" step="any" value={v} onChange={ev => setSpans({ ...spans, [id]: ev.target.value })} data-testid={`span-${id}`} /></label>;
            })}
          </div>
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="ec3-panel">
          <h2 className="font-semibold">NP EN 1993 — Verificação do aço (vigas)</h2>
          <p className="text-sm text-muted-foreground">A partir do <b>M e V condicionantes</b> da envolvente: resistência da secção (flexão, corte) e encurvadura lateral. Propriedades de perfis públicas (EN 10365). Razões <b>indicatifs</b>, a validar pelo engenheiro.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Perfil<select className={selectClass} value={ec3opts.profile} onChange={ev => setEc3opts({ ...ec3opts, profile: ev.target.value })} data-testid="ec3-profile">{ec3cat?.families ? Object.entries(ec3cat.families).map(([fam, keys]) => <optgroup key={fam} label={fam}>{keys.map(k => <option key={k} value={k}>{k}</option>)}</optgroup>) : <option value="IPE300">IPE300</option>}</select></label>
            <label className="space-y-1">Classe<select className={selectClass} value={ec3opts.grade} onChange={ev => setEc3opts({ ...ec3opts, grade: ev.target.value })} data-testid="ec3-grade">{Object.keys(ec3cat?.grades || { S235: 235, S275: 275, S355: 355 }).map(g => <option key={g} value={g}>{g}</option>)}</select></label>
            <label className="space-y-1">Classe da secção<select className={selectClass} value={ec3opts.section_class} onChange={ev => setEc3opts({ ...ec3opts, section_class: ev.target.value })} data-testid="ec3-section-class"><option value="">Auto (Table 5.2)</option>{[1, 2, 3].map(c => <option key={c} value={c}>{`Classe ${c}`}</option>)}</select></label>
            <label className="space-y-1">Curva de encurv. lat.<select className={selectClass} value={ec3opts.buckling_curve} onChange={ev => setEc3opts({ ...ec3opts, buckling_curve: ev.target.value })} data-testid="ec3-ltcurve"><option value="">Auto (Table 6.4)</option>{["a", "b", "c", "d"].map(c => <option key={c} value={c}>{c}</option>)}</select></label>
            <label className="space-y-1">C1 (encurvadura lateral)<Input type="number" step="any" value={ec3opts.c1} onChange={ev => setEc3opts({ ...ec3opts, c1: Number(ev.target.value) })} data-testid="ec3-c1" /></label>
            <label className="space-y-1">Mcr manual (senão automático)<Input type="number" step="any" placeholder="automático da planta" value={ec3opts.mcr_knm} onChange={ev => setEc3opts({ ...ec3opts, mcr_knm: ev.target.value })} data-testid="ec3-mcr" /></label>
            <label className="space-y-1">γM0<Input type="number" step="any" value={ec3opts.gamma_m0} onChange={ev => setEc3opts({ ...ec3opts, gamma_m0: Number(ev.target.value) })} /></label>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs border-t pt-3">
            <label className="space-y-1 col-span-2 md:col-span-6 text-muted-foreground">Pilares — flexão composta N+M pelo <b>método regulamentar §6.3.3 (método 2, Anexo B)</b> : encurvadura nos dois eixos χy/χz (curvas automáticas Quadro 6.2) + encurvadura lateral χLT, fatores de interação <b>kyy/kzy</b> (eq. 6.61 &amp; 6.62). N automático da envolvente, Lcr automático da planta (K×h).</label>
            <label className="space-y-1">K long. flamb.<Input type="number" step="any" value={ec3opts.k_buckling} onChange={ev => setEc3opts({ ...ec3opts, k_buckling: Number(ev.target.value) })} data-testid="ec3-k" /></label>
            <label className="space-y-1">Lcr manuel (m)<Input type="number" step="any" placeholder="auto K×h" value={ec3opts.lcr_m} onChange={ev => setEc3opts({ ...ec3opts, lcr_m: ev.target.value })} data-testid="ec3-lcr" /></label>
            <label className="space-y-1">M aplicado (kN·m)<Input type="number" step="any" placeholder="0" value={ec3opts.med_col_knm} onChange={ev => setEc3opts({ ...ec3opts, med_col_knm: ev.target.value })} data-testid="ec3-medcol" /></label>
            <label className="space-y-1">Cmy<select className={selectClass} value={ec3opts.cmy} onChange={ev => setEc3opts({ ...ec3opts, cmy: Number(ev.target.value) })} data-testid="ec3-cmy">{(ec3cat?.cm_presets || [{ label: "0.9", value: 0.9 }]).map(c => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
            <label className="space-y-1">CmLT<select className={selectClass} value={ec3opts.cm_lt} onChange={ev => setEc3opts({ ...ec3opts, cm_lt: Number(ev.target.value) })} data-testid="ec3-cmlt">{(ec3cat?.cm_presets || [{ label: "0.9", value: 0.9 }]).map(c => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
            <label className="flex items-end gap-2 text-xs"><input type="checkbox" checked={!!ec3opts.lateral_restraint} onChange={ev => setEc3opts({ ...ec3opts, lateral_restraint: ev.target.checked })} data-testid="ec3-lateral" />Travamento lateral (χLT=1)</label>
          </div>
          <Button variant="outline" onClick={designEc3} data-testid="ec3-design"><Calculator className="h-4 w-4 mr-2" />Verificar o aço NP EN 1993</Button>
          {ec3res && <div className="overflow-auto" data-testid="ec3-results"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Viga</th><th>Flexion M/Mc,Rd</th><th>Corte V/Vpl,Rd</th><th>Encurvadura lateral M/Mb,Rd</th></tr></thead>
            <tbody>{ec3res.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={3} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}<div className="text-[10px] text-muted-foreground">{r.profile}/{r.grade}{r.section_class ? ` · classe ${r.section_class} (${r.class_mode})` : ""}{r.span_m ? ` · L=${r.span_m}m (${r.span_source})` : ""}</div></td>
                  <td><Util u={r.result.bending.utilisation} /><div className="text-[10px] text-muted-foreground">{r.result.bending.mv_interaction ? `Mc,Rd reduzido ${r.result.bending.mc_rd_eff_knm} (M-V)` : `Mc,Rd ${r.result.bending.mc_rd_knm}`} kN·m</div></td>
                  <td><Util u={r.result.shear.utilisation} /><div className="text-[10px] text-muted-foreground">Vpl,Rd {r.result.shear.vpl_rd_kn} kN</div></td>
                  <td><Util u={r.result.lateral_torsional.utilisation} /><div className="text-[10px] text-muted-foreground">{r.result.lateral_torsional.note || `Mb,Rd ${r.result.lateral_torsional.mb_rd_knm} · Mcr ${r.mcr_knm} (${r.mcr_source})`}</div></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{ec3res.note}</p></div>}
          {ec3res?.columns?.length > 0 && <div className="overflow-auto mt-2" data-testid="ec3-columns"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Pilar</th><th>N dim (kN)</th><th>Lcr (m)</th><th>Encurvadura (χy/χz)</th><th>Interaction N+M (§6.3.3 · kyy/kzy)</th></tr></thead>
            <tbody>{ec3res.columns.map(c => c.status !== "ok"
              ? <tr key={c.id} className="border-b"><td className="p-1 font-medium">{c.id}</td><td colSpan={4} className="text-amber-700">{c.message}</td></tr>
              : <tr key={c.id} className="border-b align-top"><td className="p-1 font-medium">{c.id}<div className="text-[10px] text-muted-foreground">{c.profile}/{c.grade} · classe {c.section_class} ({c.class_mode})</div></td>
                  <td>{c.ned_kn}<div className="text-[10px] text-muted-foreground">{c.ned_case}</div></td>
                  <td>{c.lcr_m} <span className="text-[10px] text-muted-foreground">({c.lcr_source})</span></td>
                  <td><Util u={c.result.buckling.utilisation} /><div className="text-[10px] text-muted-foreground">Nb,Rd {c.result.nb_rd_kn} kN · χy={c.result.chi_y} / χz={c.result.chi_z}</div></td>
                  <td>{c.result.interaction ? <><Util u={c.result.interaction.utilisation} /><div className="text-[10px] text-muted-foreground">(6.61)={c.result.interaction.eq_661} · (6.62)={c.result.interaction.eq_662} · kyy={c.result.interaction.kyy} kzy={c.result.interaction.kzy} · χLT={c.result.interaction.chi_lt}</div></> : <span className="text-muted-foreground">Só N (M=0)</span>}</td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">Flexão composta dos pilares: método 2 (Anexo B) — equações 6.61 &amp; 6.62, fatores kyy/kzy. Indicativo, a validar.</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="sls-panel">
          <h2 className="font-semibold">Flechas em serviço (ELS · NP EN 1990)</h2>
          <p className="text-sm text-muted-foreground">Flechas elásticas da envolvente <b>característica</b> et <b>quasi-permanente</b> (segundo o EI introduzido: betão/aço/madeira) comparadas com L/razão. Vão <b>100 % automático segundo a geometria da planta</b> (length_m), para todas as vigas, sem introdução manual. Razão <b>indicatif</b>, a validar pelo engenheiro.</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <label className="space-y-1">Limite característico L/<Input type="number" step="any" value={slsopts.ratio_char} onChange={ev => setSlsopts({ ...slsopts, ratio_char: Number(ev.target.value) })} data-testid="sls-ratio-char" /></label>
            <label className="space-y-1">Limite quasi-perm. L/<Input type="number" step="any" value={slsopts.ratio_qp} onChange={ev => setSlsopts({ ...slsopts, ratio_qp: Number(ev.target.value) })} data-testid="sls-ratio-qp" /></label>
          </div>
          <Button variant="outline" onClick={designSls} data-testid="sls-design"><Calculator className="h-4 w-4 mr-2" />Verificar as flechas</Button>
          {slsres && <div className="overflow-auto" data-testid="sls-results"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Viga</th><th>Vão (m)</th><th>Característica (w / limite)</th><th>Quasi-permanente (w / limite)</th></tr></thead>
            <tbody>{slsres.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={3} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}</td><td>{r.span_m} <span className="text-[10px] text-muted-foreground">({r.span_source})</span></td>
                  <td><Util u={r.char.utilisation} /><div className="text-[10px] text-muted-foreground">{r.char.w_mm ?? "—"} / {r.char.limit_mm} mm ({r.char.ratio_label})</div></td>
                  <td><Util u={r.qp.utilisation} /><div className="text-[10px] text-muted-foreground">{r.qp.w_mm ?? "—"} / {r.qp.limit_mm} mm ({r.qp.ratio_label})</div></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{slsres.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="crack-panel">
          <h2 className="font-semibold">NP EN 1992 §7.3 — Fendilhação do betão (ELS quase permanente)</h2>
          <p className="text-sm text-muted-foreground">Abertura de fendas wk e As mín. de fendilhação, sob momento <b>quasi-permanent</b> da envolvente, a partir das armaduras propostas (classe do betão / recobrimento / Ø do painel NP EN 1992). Razão <b>indicatif</b>, a validar pelo engenheiro.</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <label className="space-y-1">wk,max (mm)<Input type="number" step="any" value={crackopts.w_max_mm} onChange={ev => setCrackopts({ w_max_mm: Number(ev.target.value) })} data-testid="crack-wmax" /></label>
          </div>
          <Button variant="outline" onClick={designCrack} data-testid="crack-design"><Calculator className="h-4 w-4 mr-2" />Verificar a fendilhação</Button>
          {crackres && <div className="overflow-auto" data-testid="crack-results">{crackres.reinjected_from_automation && <p className="text-[11px] text-emerald-800 mb-1" data-testid="crack-reinjected">Ø proveniente dos aços escolhidos pela cadeia automática (reinjetados na fendilhação §7.3).</p>}<table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Viga</th><th>Mqp (kN·m)</th><th>σs (MPa)</th><th>wk / wk,max (mm)</th><th>As,min fiss. (cm²)</th></tr></thead>
            <tbody>{crackres.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={4} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}</td><td>{r.mqp_knm}<div className="text-[10px] text-muted-foreground">{r.mqp_case}</div></td><td>{r.sigma_s_mpa}</td>
                  <td><Util u={r.utilisation} /><div className="text-[10px] text-muted-foreground">{r.wk_mm} / {r.wmax_mm} · sr,max {r.sr_max_mm}mm · Ø{r.bar_mm}{r.reinforcement_source === "automation" ? " auto" : ""}</div></td>
                  <td>{r.as_min_fiss_cm2}</td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{crackres.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="anc-panel">
          <h2 className="font-semibold">NP EN 1992 §8.4/§8.7 — Amarrações e emendas</h2>
          <p className="text-sm text-muted-foreground">Comprimento de amarração <b>lbd</b> (§8.4) e de emenda <b>l0</b> (§8.7) calculados a partir das <b>armaduras propostas</b> (Ø do varão, classe do betão, recobrimento, As,req/As,prov do painel NP EN 1992). Condições de aderência e ρ1 (% de varões emendados) editáveis. Razão <b>indicatif</b>, a validar pelo engenheiro.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Aderência<select className={selectClass} value={ancopts.bond} onChange={ev => setAncopts({ ...ancopts, bond: ev.target.value })} data-testid="anc-bond"><option value="good">Bonne (η1=1,0)</option><option value="poor">Má (η1=0,7)</option></select></label>
            <label className="space-y-1">ρ1 recouvr. (%)<Input type="number" step="any" value={ancopts.rho1_pct} onChange={ev => setAncopts({ ...ancopts, rho1_pct: Number(ev.target.value) })} data-testid="anc-rho1" /></label>
            <label className="space-y-1">α1 (forme)<Input type="number" step="any" value={ancopts.alpha1} onChange={ev => setAncopts({ ...ancopts, alpha1: Number(ev.target.value) })} data-testid="anc-a1" /></label>
            <label className="space-y-1">α3 (transv.)<Input type="number" step="any" value={ancopts.alpha3} onChange={ev => setAncopts({ ...ancopts, alpha3: Number(ev.target.value) })} data-testid="anc-a3" /></label>
            <label className="space-y-1">α4 (soldado)<Input type="number" step="any" value={ancopts.alpha4} onChange={ev => setAncopts({ ...ancopts, alpha4: Number(ev.target.value) })} data-testid="anc-a4" /></label>
            <label className="space-y-1">α5 (pression)<Input type="number" step="any" value={ancopts.alpha5} onChange={ev => setAncopts({ ...ancopts, alpha5: Number(ev.target.value) })} data-testid="anc-a5" /></label>
          </div>
          <Button variant="outline" onClick={designAnchorage} data-testid="anc-design"><Calculator className="h-4 w-4 mr-2" />Calcular amarrações e emendas</Button>
          {ancres && <div className="overflow-auto" data-testid="anc-results">{ancres.reinjected_from_automation && <p className="text-[11px] text-emerald-800 mb-1" data-testid="anc-reinjected">Ø e As,prov provenientes dos aços escolhidos pela cadeia automática (reinjetados em §8.4/§8.7).</p>}<table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Viga</th><th>Varão</th><th>fbd (MPa)</th><th>lb,rqd (m)</th><th>Amarração lbd (m · ×Ø)</th><th>Emenda l0 (m · ×Ø)</th></tr></thead>
            <tbody>{ancres.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={5} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}</td><td>{r.bar_label || `Ø${r.result.bar_mm}`}{r.reinforcement_source === "automation" ? <span className="text-[10px] text-emerald-700"> · auto</span> : ""}</td><td>{r.result.fbd_mpa}</td><td>{r.result.lb_rqd_m}</td>
                  <td>{r.result.lbd_m} m <span className="text-[10px] text-muted-foreground">({r.result.lbd_ratio_phi}Ø)</span></td>
                  <td>{r.result.l0_m} m <span className="text-[10px] text-muted-foreground">({r.result.l0_ratio_phi}Ø · α6={r.result.alpha6})</span></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{ancres.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="ec5-panel">
          <h2 className="font-semibold">NP EN 1995 — Verificação da madeira (vigas)</h2>
          <p className="text-sm text-muted-foreground">A partir do <b>M e V condicionantes</b> : flexão, corte (kcr) e encurvadura lateral. kmod segundo duração × classe de serviço, γM e classes EN 338/EN 14080. Razões <b>indicatifs</b>, a validar pelo engenheiro.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Classe da madeira<select className={selectClass} value={ec5opts.strength_class} onChange={ev => setEc5opts({ ...ec5opts, strength_class: ev.target.value })} data-testid="ec5-class">{(ec5cat?.classes || [{ key: "C24" }]).map(c => <option key={c.key} value={c.key}>{c.key}</option>)}</select></label>
            <label className="space-y-1">Classe de serviço<select className={selectClass} value={ec5opts.service_class} onChange={ev => setEc5opts({ ...ec5opts, service_class: ev.target.value })} data-testid="ec5-sc">{["1", "2", "3"].map(c => <option key={c} value={c}>{c}</option>)}</select></label>
            <label className="space-y-1">Duração da carga<select className={selectClass} value={ec5opts.load_duration} onChange={ev => setEc5opts({ ...ec5opts, load_duration: ev.target.value })} data-testid="ec5-dur">{(ec5cat?.load_durations || ["permanent", "long", "medium", "short", "instantaneous"]).map(d => <option key={d} value={d}>{d}</option>)}</select></label>
            <label className="space-y-1">lef (m, option.)<Input type="number" step="any" placeholder="para encurv. lat." value={ec5opts.lef_m} onChange={ev => setEc5opts({ ...ec5opts, lef_m: ev.target.value })} data-testid="ec5-lef" /></label>
            <label className="space-y-1">kcr<Input type="number" step="any" value={ec5opts.kcr} onChange={ev => setEc5opts({ ...ec5opts, kcr: Number(ev.target.value) })} /></label>
            <label className="space-y-1">γM (option.)<Input type="number" step="any" placeholder="auto" value={ec5opts.gamma_m} onChange={ev => setEc5opts({ ...ec5opts, gamma_m: ev.target.value })} /></label>
          </div>
          <Button variant="outline" onClick={designEc5} data-testid="ec5-design"><Calculator className="h-4 w-4 mr-2" />Verificar a madeira NP EN 1995</Button>
          {ec5res && <div className="overflow-auto" data-testid="ec5-results"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Viga</th><th>Flexão</th><th>Corte</th><th>Encurvadura lateral</th></tr></thead>
            <tbody>{ec5res.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={3} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}<div className="text-[10px] text-muted-foreground">{r.strength_class} · {r.b_m}×{r.h_m}</div></td>
                  <td><Util u={r.result.bending.utilisation} /><div className="text-[10px] text-muted-foreground">σm,d {r.result.bending.sigma_m_d_mpa}/{r.result.bending.fm_d_mpa} MPa</div></td>
                  <td><Util u={r.result.shear.utilisation} /><div className="text-[10px] text-muted-foreground">τd {r.result.shear.tau_d_mpa}/{r.result.shear.fv_d_mpa} MPa</div></td>
                  <td><Util u={r.result.lateral_torsional.utilisation} /><div className="text-[10px] text-muted-foreground">{r.result.lateral_torsional.note || `kcrit ${r.result.lateral_torsional.kcrit}`}</div></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{ec5res.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <StructureAutomationPanel study={study} model={model} change={automation_settings => setModel({ ...model, automation_settings })} dirty={dirty} generate={automate} download={download} />}
        {!dirty && result && result.status === "mechanical_only" && <StructureDrawingsPanel study={study} model={model} change={drawings => setModel({ ...model, drawings })} dirty={dirty} download={download} />}
        {study && model && <StructureManualPanels study={study} model={model} setModel={setModel} dirty={dirty} save={save} envelope={envelope} ec2opts={ec2opts} busy={busy} />}
        {study && model && <StructureLintelPanel study={study} model={model} opts={lintelOpts} setOpts={setLintelOpts} base={BASE} busy={busy} saveModel={saveModel} />}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="dossier-panel">
          <h2 className="font-semibold">Processo de engenharia completo (PDF)</h2>
          <p className="text-sm text-muted-foreground">Reúne os capítulos assinalados (combinações NP EN 1990 → armaduras / perfis / secções → capacidade resistente → flechas / fendilhação) numa única nota, carimbada «NÃO EXECUTÓRIO — a verificar pelo engenheiro», com as definições dos painéis acima.</p>
          <div className="flex flex-wrap gap-4 text-xs">
            {[["ec2", "Betão NP EN 1992"], ["crack", "Fendilhação §7.3"], ["anchorage", "Amarrações §8.4/§8.7"], ["ec3", "Aço NP EN 1993"], ["ec5", "Bois EN 1995"], ["ec7", "Fundações NP EN 1997"], ["sls", "Flechas ELS"], ["reinforcement", "Armaduras manuais"], ["architecture", "Controlos de arquitetura"], ["linked", "Aços associados"], ["lintel", "Padieira (abertura)"]].map(([k, label]) => <label key={k} className="flex items-center gap-1"><input type="checkbox" checked={!!dossierInc[k]} onChange={ev => setDossierInc({ ...dossierInc, [k]: ev.target.checked })} data-testid={`dossier-${k}`} />{label}</label>)}
          </div>
          <Button onClick={exportDossier} data-testid="dossier-export"><FileDown className="h-4 w-4 mr-2" />Transferir o processo de engenharia</Button>
        </Card>}
      </>}
    </fieldset>
  </div>;
}

function JsonModel({ model, onChange }) {
  const [value, setValue] = useState(""), [error, setError] = useState("");
  useEffect(() => { setValue(JSON.stringify({ actions: model.actions, self_weight_action: model.self_weight_action, combinations: model.combinations }, null, 2)); }, [model.actions, model.self_weight_action, model.combinations]);
  return <div className="space-y-2 mt-3"><textarea aria-label="Ações e combinações" className="w-full border rounded p-2 font-mono text-xs" rows={10} value={value} onChange={ev => setValue(ev.target.value)} />
    <Button size="sm" variant="outline" onClick={() => { try { const v = JSON.parse(value); if (!Array.isArray(v.actions) || !Array.isArray(v.combinations)) throw new Error(); onChange({ ...model, actions: v.actions, self_weight_action: v.self_weight_action, combinations: v.combinations }); setError(""); } catch { setError("Formato inválido: actions e combinations devem ser listas."); } }}>Aplicar</Button>{error && <p role="alert" className="text-red-700 text-sm">{error}</p>}
  </div>;
}
