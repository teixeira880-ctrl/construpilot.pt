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
const TYPES = { slab: "Plancher", beam: "Poutre", wall: "Mur", column: "Poteau", footing: "Semelle" };
const COLORS = { slab: "#b9c9c0", beam: "#b46b42", wall: "#17574b", column: "#9d3e26", footing: "#837466" };
const number = value => value === "" ? null : Number(value);
const errorMessage = e => typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Vérifiez les valeurs et les champs obligatoires.";
const emptySource = () => ({ document: "", page: null, note: "" });
const blankElement = id => ({ id, kind: "wall", level: "RDC", material: "À préciser", length_m: null, width_m: null, height_m: null,
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
  if (!points.length) return <p className="py-16 text-center text-muted-foreground">Renseignez les coordonnées x/y et les dimensions pour dessiner ce niveau.</p>;
  const xmin = Math.min(...points.map(p => p[0])), xmax = Math.max(...points.map(p => p[0]));
  const ymin = Math.min(...points.map(p => p[1])), ymax = Math.max(...points.map(p => p[1]));
  const span = Math.max(xmax - xmin, ymax - ymin, 1), pad = span * .12;
  return <><svg role="img" aria-label={`Plan de principe ${level}`} className="w-full h-80 bg-[#f8faf7] rounded-xl border" viewBox={`${xmin - pad} ${ymin - pad} ${xmax - xmin + 2 * pad} ${ymax - ymin + 2 * pad}`}>
    {shapes.sort((a, b) => Number(a.e.kind !== "slab") - Number(b.e.kind !== "slab")).map(({ e, pts }) => <g key={e.id}>
      <polygon points={pts.map(p => p.join(",")).join(" ")} fill={COLORS[e.kind]} fillOpacity=".14" stroke={COLORS[e.kind]} strokeWidth={span / 220} strokeDasharray={e.reviewed ? undefined : `${span / 60} ${span / 90}`} />
      <text x={pts.reduce((s, p) => s + p[0], 0) / 4} y={pts.reduce((s, p) => s + p[1], 0) / 4} textAnchor="middle" fontSize={span / 35} fill="#173c32">{e.id}</text>
    </g>)}
  </svg><p className="text-xs text-muted-foreground mt-2">Coordonnées en mètres, coin inférieur gauche local. {elements.length - placed.length} élément(s) sans implantation. Pointillés : à confirmer.</p></>;
}

function ElementEditor({ element: e, model, update }) {
  const set = (key, value) => update({ ...e, [key]: value, reviewed: key === "reviewed" ? value : false });
  const editLoad = (i, patch) => set("loads", e.loads.map((x, k) => k === i ? { ...x, ...patch } : x));
  const editSupport = (i, patch) => set("supports", e.supports.map((x, k) => k === i ? { ...x, ...patch } : x));
  return <Card className="p-5 space-y-5">
    <div className="flex items-center gap-3"><b>{e.id}</b><select aria-label="Nature" className={selectClass} value={e.kind} onChange={ev => update({ ...e, kind: ev.target.value, reviewed: false, supports: [], loads: [] })}>
      {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      <Input aria-label="Niveau" value={e.level} onChange={ev => set("level", ev.target.value)} /></div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {[["length_m", "Longueur (m)"], ["width_m", "Largeur (m)"], ["height_m", "Hauteur / épaisseur (m)"], ["density_kn_m3", "Poids volumique (kN/m³)"],
        ["x_m", "Origine x (m)"], ["y_m", "Origine y (m)"], ["angle_deg", "Rotation (°)"], ...(e.kind === "beam" ? [["ei_kn_m2", "Rigidité EI (kN.m²), facultative"]] : [])].map(([key, title]) =>
        <label className="text-xs space-y-1" key={key}>{title}<Input type="number" step="any" value={e[key] ?? ""} onChange={ev => set(key, number(ev.target.value))} /></label>)}
    </div>
    <label className="block text-xs space-y-1">Matériau<Input value={e.material} onChange={ev => set("material", ev.target.value)} /></label>
    {e.source.document && <p className="text-xs text-muted-foreground">Source : {e.source.document} · page {e.source.page ?? "à préciser"}</p>}
    <label className="block text-xs space-y-1">Source des dimensions / contrôle des cotes<Input value={e.source.note} onChange={ev => set("source", { ...e.source, note: ev.target.value })} placeholder="Plan, page, cote ou relevé sur site" /></label>
    <label className="block text-xs space-y-1">Justification mécanique<Input value={e.mechanics_source.note} onChange={ev => set("mechanics_source", { ...e.mechanics_source, note: ev.target.value })} placeholder="Poids volumique, rigidité retenue, répartition et appuis centrés" /></label>
    <section className="space-y-2"><h3 className="font-medium text-sm">Charges ajoutées au poids propre</h3>
      <p className="text-xs text-muted-foreground">Le poids propre est calculé séparément. Ne le saisissez pas une deuxième fois. Sans ligne : aucun autre chargement.</p>
      {e.loads.map((load, i) => <div className="grid md:grid-cols-6 gap-2 border rounded p-2" key={i}>
        <select aria-label="Action" className={selectClass} value={load.action} onChange={ev => editLoad(i, { action: ev.target.value })}>{model.actions.map(a => <option key={a.id}>{a.id}</option>)}</select>
        <select aria-label="Répartition" className={selectClass} value={load.mode} onChange={ev => editLoad(i, { mode: ev.target.value, position_m: null })}>
          <option value="point">Ponctuelle (kN)</option>{["wall", "beam"].includes(e.kind) && <option value="line">Linéique (kN/m)</option>}{e.kind === "slab" && <option value="surface">Surfacique (kN/m²)</option>}
        </select>
        <Input aria-label="Valeur de charge" type="number" min="0" step="any" value={load.value ?? ""} onChange={ev => editLoad(i, { value: number(ev.target.value) })} />
        {e.kind === "beam" && load.mode === "point" ? <Input aria-label="Position depuis appui gauche (m)" placeholder="Position (m)" type="number" step="any" value={load.position_m ?? ""} onChange={ev => editLoad(i, { position_m: number(ev.target.value) })} /> : <span />}
        <Input aria-label="Source de charge" placeholder="Justification de charge" value={load.source.note} onChange={ev => editLoad(i, { source: { ...load.source, note: ev.target.value } })} />
        <Button variant="ghost" onClick={() => set("loads", e.loads.filter((_, k) => k !== i))}>Retirer</Button>
      </div>)}
      <Button variant="outline" size="sm" onClick={() => set("loads", [...e.loads, { action: model.actions[0]?.id || "G", mode: "point", value: null, position_m: null, source: emptySource() }])}>Ajouter une charge</Button>
    </section>
    {e.kind !== "footing" && <section className="space-y-2"><h3 className="font-medium text-sm">Transfert vers les appuis</h3>
      <p className="text-xs text-muted-foreground">{e.kind === "beam" ? "Deux appuis simples : gauche puis droite. Les réactions sont calculées." : "Définissez les fractions tributaires. Leur somme doit être égale à 1."}</p>
      {e.supports.map((s, i) => <div className="grid md:grid-cols-5 gap-2" key={i}>
        <select aria-label={`Appui ${i + 1}`} className={selectClass} value={s.target} onChange={ev => editSupport(i, { target: ev.target.value, receiving: model.elements.find(x => x.id === ev.target.value)?.kind === "beam" ? "point" : "axial", position_m: null })}>
          <option value="">{`Choisir l'appui ${i + 1}`}</option>{model.elements.filter(x => x.id !== e.id && x.kind !== "slab").map(x => <option key={x.id} value={x.id}>{`${x.id} · ${TYPES[x.kind]}`}</option>)}</select>
        {e.kind !== "beam" ? <Input aria-label="Fraction (0 à 1)" placeholder="Fraction" type="number" step="any" value={s.fraction ?? ""} onChange={ev => editSupport(i, { fraction: number(ev.target.value) })} /> : <span className="text-sm p-2">{i === 0 ? "Gauche" : "Droite"}</span>}
        <select aria-label="Charge reçue par l'appui" className={selectClass} value={s.receiving} onChange={ev => editSupport(i, { receiving: ev.target.value, position_m: null })}><option value="axial">Axiale centrée</option><option value="uniform">Uniforme sur poutre</option><option value="point">Ponctuelle sur poutre</option></select>
        {s.receiving === "point" ? <Input aria-label="Position sur poutre réceptrice (m)" placeholder="Position (m)" type="number" step="any" value={s.position_m ?? ""} onChange={ev => editSupport(i, { position_m: number(ev.target.value) })} /> : <span />}
        <Button variant="ghost" onClick={() => set("supports", e.supports.filter((_, k) => k !== i))}>Retirer</Button>
      </div>)}
      <Button variant="outline" size="sm" disabled={e.kind === "beam" && e.supports.length >= 2} onClick={() => set("supports", [...e.supports, { target: "", fraction: e.kind === "beam" ? null : 1, receiving: "axial", position_m: null }])}>Ajouter un appui</Button>
    </section>}
    <label className="flex gap-2 text-sm"><input type="checkbox" checked={e.reviewed} onChange={ev => set("reviewed", ev.target.checked)} /> J'ai contrôlé les dimensions, les charges, le poids propre et les appuis de cet élément.</label>
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
  useEffect(() => { refresh().catch(() => toast.error("Chargement des études impossible")); }, []);
  useEffect(() => { api.get("/structuro/calc/combinations/catalog").then(r => setCatalog(r.data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/structuro/calc/ec2/catalog").then(r => setEc2cat(r.data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/structuro/calc/ec7/catalog").then(r => setEc7cat(r.data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/structuro/calc/ec3/catalog").then(r => setEc3cat(r.data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/structuro/calc/ec5/catalog").then(r => setEc5cat(r.data)).catch(() => {}); }, []);
  const apply = data => { setStudy(data); setModel(data.model); setLevel(v => v || data.model.elements[0]?.level || "RDC"); };
  const task = async fn => { setBusy(true); try { await fn(); } catch (e) { toast.error(errorMessage(e)); } finally { setBusy(false); setProgress(""); } };
  const create = (demonstration, drawingDemo = false, autoDemo = false) => task(async () => { const { data } = await api.post(BASE, { demonstration, drawing_demonstration: drawingDemo, automation_demonstration: autoDemo, plan_id: demonstration || drawingDemo || autoDemo ? null : plan || null }); apply(data); setSelected(null); await refresh(); });
  const save = () => task(async () => {
    const { data } = await api.put(`${BASE}/${study.study_id}`, { expected_revision: study.revision, model });
    apply(data); await refresh(); toast.success(data.result.status === "blocked" ? "Étude enregistrée ; données à compléter" : "Calcul mécanique effectué ; résistance à vérifier");
  });
  const saveModel = nextModel => task(async () => {
    const { data } = await api.put(`${BASE}/${study.study_id}`, { expected_revision: study.revision, model: nextModel });
    apply(data); await refresh(); toast.success("Réactions du linteau réinjectées dans la descente de charges");
  });
  const readAll = () => task(async () => {
    let current = study, failures = [];
    for (let page = 1; page <= study.page_count; page++) {
      if (current.page_readings[String(page)]) continue;
      setProgress(`Lecture de la page ${page} / ${study.page_count}`);
      try {
        const { data } = await api.post(`${BASE}/${study.study_id}/read-page`, { expected_revision: current.revision, page }, { timeout: 95000 });
        current = data; apply(data);
      } catch (e) { if (e?.response?.status === 409) throw e; failures.push(page); }
    }
    if (failures.length) toast.error(`Pages non lues : ${failures.join(", ")}. Vous pouvez relancer les pages restantes.`);
    else toast.success("Pages lues ; vérifiez et sélectionnez les éléments à retenir.");
  });
  const download = fmt => task(async () => {
    const ext = { aciers: "pdf", plans: "pdf", nomenclature: "csv", dossier: "zip" }[fmt] || fmt;
    const { data } = await api.get(`${BASE}/${study.study_id}/export/${fmt}`, { responseType: "blob", params: { expected_revision: study.revision } });
    const url = URL.createObjectURL(data), a = document.createElement("a"); a.href = url; a.download = `structure-${fmt}-r${study.revision}.${ext}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  const automate = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/automate`, { expected_revision: study.revision, model }, { timeout: 95000 });
    apply(data); toast.success("Dossier automatique généré (indicatif) · à valider par l'ingénieur");
  });
  const qActions = () => (model?.actions || []).filter(a => a.kind === "Q");
  const genCombos = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/combinations/generate`, { expected_revision: study.revision, categories: cats, options: { uls: true, sls_char: true, sls_freq: sfreq, sls_qp: true }, apply: true });
    apply(data.study); await refresh(); toast.success(`${data.generated.length} combinaison(s) EN 1990 générée(s) · à vérifier par l'ingénieur`);
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
    setEc2res(data); toast.success("Armatures EN 1992 calculées · à vérifier par l'ingénieur");
  });
  const exportFerraillage = () => task(async () => {
    const res = await api.post(`${BASE}/${study.study_id}/export/ferraillage`, ec2opts, { responseType: "blob" });
    const url = URL.createObjectURL(res.data), a = document.createElement("a"); a.href = url; a.download = `ferraillage-r${study.revision}.pdf`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success("Note de ferraillage PDF téléchargée");
  });
  const designEc7 = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec7/design`, ec7opts);
    setEc7res(data); toast.success("Portance EN 1997 (indicatif) · à vérifier par l'ingénieur");
  });
  const ec3Payload = () => ({ profile: ec3opts.profile, grade: ec3opts.grade, section_class: ec3opts.section_class === "" ? null : Number(ec3opts.section_class), gamma_m0: Number(ec3opts.gamma_m0), gamma_m1: Number(ec3opts.gamma_m1), buckling_curve: ec3opts.buckling_curve === "" ? null : ec3opts.buckling_curve, c1: Number(ec3opts.c1), mcr_knm: ec3opts.mcr_knm === "" ? null : Number(ec3opts.mcr_knm), spans: spansPayload(), k_buckling: Number(ec3opts.k_buckling), lcr_m: ec3opts.lcr_m === "" ? null : Number(ec3opts.lcr_m), med_col_knm: ec3opts.med_col_knm === "" ? 0 : Number(ec3opts.med_col_knm), cmy: Number(ec3opts.cmy), cm_lt: Number(ec3opts.cm_lt), lateral_restraint: !!ec3opts.lateral_restraint });
  const ancPayload = () => ({ ...ec2opts, bond: ancopts.bond, rho1_pct: Number(ancopts.rho1_pct), alpha1: Number(ancopts.alpha1), alpha3: Number(ancopts.alpha3), alpha4: Number(ancopts.alpha4), alpha5: Number(ancopts.alpha5) });
  const ec5Payload = () => ({ ...ec5opts, gamma_m: ec5opts.gamma_m === "" ? null : Number(ec5opts.gamma_m), lef_m: ec5opts.lef_m === "" ? null : Number(ec5opts.lef_m) });
  const slsPayload = () => ({ ratio_char: Number(slsopts.ratio_char), ratio_qp: Number(slsopts.ratio_qp), spans: spansPayload() });
  const crackPayload = () => ({ ...ec2opts, w_max_mm: Number(crackopts.w_max_mm) });
  const designEc3 = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec3/design`, ec3Payload());
    setEc3res(data); toast.success("Vérification acier EN 1993 (indicatif) · à vérifier");
  });
  const designSls = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/sls/deflection`, slsPayload());
    setSlsres(data); toast.success("Flèches SLS calculées (indicatif) · à vérifier");
  });
  const designEc5 = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec5/design`, ec5Payload());
    setEc5res(data); toast.success("Vérification bois EN 1995 (indicatif) · à vérifier");
  });
  const designCrack = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec2/crack`, crackPayload());
    setCrackres(data); toast.success("Fissuration EN 1992 calculée (indicatif) · à vérifier");
  });
  const designAnchorage = () => task(async () => {
    const { data } = await api.post(`${BASE}/${study.study_id}/ec2/anchorage`, ancPayload());
    setAncres(data); toast.success("Ancrages & recouvrements EN 1992 calculés (indicatif) · à vérifier");
  });
  const exportDossier = () => task(async () => {
    const include = Object.entries(dossierInc).filter(([, v]) => v).map(([k]) => k);
    const body = { include, ec2: ec2opts, ec3: ec3Payload(), ec5: ec5Payload(), ec7: ec7opts, sls: slsPayload(), crack: crackPayload(), anchorage: ancPayload(), lintel: lintelOpts.clear_span_m ? lintelOpts : undefined };
    const res = await api.post(`${BASE}/${study.study_id}/export/dossier`, body, { responseType: "blob" });
    const url = URL.createObjectURL(res.data), a = document.createElement("a"); a.href = url; a.download = `dossier-bet-r${study.revision}.pdf`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success("Dossier BET PDF téléchargé");
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
      <h1 className="text-3xl font-semibold mt-2 flex gap-2 items-center"><Building2 /> Du PC au modèle porteur</h1>
      <p className="text-sm text-muted-foreground mt-2">Lecture des plans, calcul gravitaire et plans de principe avec sources.</p></div><a href="/structuro" className="text-sm underline">Espace structure</a></header>
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"><b>Version préliminaire.</b> Le moteur calcule des efforts sur le modèle saisi. Il ne dimensionne pas encore les sections ni les armatures. Sol, stabilité, résistance et séisme restent à vérifier par un ingénieur structure.</div>
    {busy && <p role="status" className="flex items-center gap-2"><Loader2 className="animate-spin h-4 w-4" />{progress || "Traitement en cours…"}</p>}
    <fieldset disabled={busy} className="space-y-6 disabled:opacity-70">
      {!study ? <>
        <Card className="p-5 space-y-4"><h2 className="font-semibold">Démarrer depuis votre permis de construire</h2><select className={selectClass} aria-label="PC source" value={plan} onChange={ev => setPlan(ev.target.value)}><option value="">Étude vide / saisie manuelle</option>{plans.map(p => <option key={p.plan_id} value={p.plan_id}>{p.filename}</option>)}</select>
          <div className="flex flex-wrap gap-2"><Button onClick={() => create(false)} data-testid="create-study-btn">Créer l'étude</Button><Button variant="outline" onClick={() => create(true)} data-testid="open-demo-study-btn">Ouvrir un exemple fictif</Button><Button variant="outline" onClick={() => create(false, false, true)} data-testid="open-automation-demo-btn">Exemple automatique (dossier)</Button><a className="text-sm underline p-2" href="/plan">Importer un nouveau PC</a></div></Card>
        <div className="grid md:grid-cols-2 gap-3">{studies.map(s => <button key={s.study_id} className="text-left border rounded-lg p-4" onClick={() => task(async () => { const { data } = await api.get(`${BASE}/${s.study_id}`); apply(data); })}><b>{s.model.title}</b><p className="text-xs text-muted-foreground">Révision {s.revision}</p></button>)}</div>
      </> : <>
        <div className="flex flex-wrap gap-2 items-center"><Button variant="ghost" disabled={dirty} onClick={() => { setStudy(null); setModel(null); setSelected(null); setLevel(""); }}>Mes études</Button>
          <Input className="max-w-md" aria-label="Titre de l'étude" value={model.title} onChange={ev => setModel({ ...model, title: ev.target.value })} />
          <Button onClick={save}><Calculator className="h-4 w-4 mr-2" />Enregistrer et calculer</Button>
          <Button variant="outline" disabled={dirty} onClick={() => download("pdf")}><FileDown className="h-4 w-4 mr-2" />PDF</Button><Button variant="outline" disabled={dirty} onClick={() => download("dxf")}>DXF</Button>
          <span className="text-xs">{dirty ? "Modifications non enregistrées · résultats masqués" : `Révision ${study.revision}`}</span>
          {dirty && <Button variant="ghost" onClick={() => setModel(study.model)}>Annuler les modifications</Button>}
        </div>
        {study.plan_id && <Card className="p-5 space-y-3"><h2 className="font-semibold">Lecture du PC : {Object.keys(study.page_readings).length} / {study.page_count} pages</h2>
          <p className="text-xs text-muted-foreground">Les candidats ne sont pas encore des éléments porteurs validés. Vérifiez les doublons entre plans, coupes et façades avant de les ajouter.</p>
          <Button variant="outline" disabled={dirty} onClick={readAll}>Lire les pages restantes</Button>
          {Object.values(study.page_readings).map(read => <details key={read.page} className="border rounded p-3"><summary className="cursor-pointer">Page {read.page} · {read.kind} · {read.elements.length} candidats</summary>
            <ul className="text-sm list-disc ml-5 mt-3">{[...read.observations, ...read.missing].map((x, i) => <li key={i}>{x}</li>)}</ul>
            {read.elements.map(e => <div key={e.id} className="flex gap-3 items-center py-2"><span className="text-sm flex-1">{e.id} · {TYPES[e.kind]} · {e.level} · {e.length_m ?? "?"} × {e.width_m ?? "?"} × {e.height_m ?? "?"} m</span><Button size="sm" variant="outline" disabled={model.elements.some(x => x.id === e.id)} onClick={() => add(e)}>Ajouter au modèle</Button></div>)}
          </details>)}
        </Card>}
        <div className="grid lg:grid-cols-[260px_1fr] gap-5"><Card className="p-4 space-y-3"><h2 className="font-semibold">Éléments porteurs</h2>
          <Button variant="outline" size="sm" onClick={() => { let n = model.elements.length + 1; while (model.elements.some(e => e.id === `E${n}`)) n++; add(blankElement(`E${n}`)); }}><Plus className="h-4 w-4" />Ajouter</Button>
          {model.elements.map(e => <div key={e.id} className={`flex items-center rounded border p-2 ${selected === e.id ? "bg-emerald-50 border-emerald-600" : ""}`}><button className="text-left flex-1 text-sm" onClick={() => { setSelected(e.id); setLevel(e.level); }}>{e.id} · {TYPES[e.kind]}<p className="text-xs text-muted-foreground">{e.level} · {e.reviewed ? "saisie confirmée" : "à confirmer"}</p></button><button aria-label={`Supprimer ${e.id}`} onClick={() => setModel({ ...model, gravity_model_reviewed: false, elements: model.elements.filter(x => x.id !== e.id) })}><Trash2 className="h-4 w-4" /></button></div>)}
        </Card><div className="space-y-4"><Card className="p-5"><div className="flex justify-between gap-3 mb-4"><h2 className="font-semibold">Plan de principe · non exécutoire</h2><select aria-label="Niveau du plan" className="border rounded p-1 text-sm" value={level} onChange={ev => setLevel(ev.target.value)}>{[...new Set([level, ...model.elements.map(e => e.level)])].map(l => <option key={l}>{l}</option>)}</select></div><Plan model={model} level={level} /></Card>
          {active && <ElementEditor element={active} model={model} update={updateElement} />}
        </div></div>
        <Card className="p-5 space-y-3"><h2 className="font-semibold">Hypothèses du modèle</h2><p className="text-sm text-muted-foreground">Gravité seule, poutres sur deux appuis simples, répartition tributaire des planchers et transferts axiaux centrés. Ce choix exclut notamment les portiques, les consoles et le contreventement.</p>
          <textarea className="w-full border rounded p-3 text-sm" rows={3} aria-label="Hypothèses" placeholder="Justifiez le schéma retenu et ses limites" value={model.assumptions.join("\n")} onChange={ev => setModel({ ...model, gravity_model_reviewed: false, assumptions: ev.target.value.split("\n") })} />
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={model.gravity_model_reviewed} onChange={ev => setModel({ ...model, gravity_model_reviewed: ev.target.checked })} />J'ai contrôlé le schéma porteur, les transferts et l'absence de double comptage.</label>
          <details><summary className="text-sm cursor-pointer">Actions et combinaisons personnalisées (saisie technique)</summary><p className="text-xs mt-2">G et Q sont calculés séparément. Une combinaison doit fournir un coefficient pour chaque action et sa justification ; aucun coefficient Eurocode n'est appliqué automatiquement.</p>
            <JsonModel model={model} onChange={m => setModel({ ...m, gravity_model_reviewed: false })} />
          </details>
        </Card>
        {!dirty && <Card className="p-5 space-y-3" data-testid="eurocode-combos">
          <h2 className="font-semibold">Combinaisons Eurocode EN 1990</h2>
          <p className="text-sm text-muted-foreground">Génère les combinaisons ELU/ELS à partir de vos actions. Coefficients usuels NA FR (γG=1,35 ; γQ=1,5 ; ψ par catégorie) — <b>à vérifier par l'ingénieur</b>. Aucune résistance n'est validée.</p>
          {qActions().length === 0 ? <p className="text-sm">Ajoutez au moins une action variable Q (et enregistrez) pour générer des combinaisons.</p> : <div className="space-y-2">
            {qActions().map(q => <div key={q.id} className="flex flex-wrap items-center gap-2 text-sm"><span className="font-medium min-w-[7rem]">{q.label} ({q.id})</span>
              <select className={selectClass + " max-w-xs"} aria-label={`Catégorie ${q.id}`} value={cats[q.id] || "A"} onChange={ev => setCats({ ...cats, [q.id]: ev.target.value })} data-testid={`combo-cat-${q.id}`}>{(catalog?.categories || [{ key: "A", label: "A — Habitation" }]).map(c => <option key={c.key} value={c.key}>{`${c.label} (ψ0=${c.psi0})`}</option>)}</select></div>)}
          </div>}
          <label className="flex gap-2 text-sm items-center"><input type="checkbox" checked={sfreq} onChange={ev => setSfreq(ev.target.checked)} data-testid="combo-sfreq" />Ajouter aussi l'ELS fréquente</label>
          <Button variant="outline" onClick={genCombos} disabled={qActions().length === 0} data-testid="combo-generate"><Calculator className="h-4 w-4 mr-2" />Générer les combinaisons EN 1990</Button>
          {model.combinations.filter(c => /^EL[US]/.test(c.id)).length > 0 && <div className="text-xs space-y-1" data-testid="combo-list"><p className="font-medium">Combinaisons générées (modifiables dans la saisie technique) :</p><ul className="list-disc ml-5 space-y-0.5">{model.combinations.filter(c => /^EL[US]/.test(c.id)).map(c => <li key={c.id}><b>{c.label}</b> — {Object.entries(c.factors).map(([k, v]) => `${k}×${v}`).join(" + ")}</li>)}</ul></div>}
        </Card>}
        {result && <Card className="p-5 space-y-4"><h2 className="font-semibold">{result.status === "blocked" ? "À compléter avant calcul" : "Résultats mécaniques · résistance non vérifiée"}</h2>
          {result.issues.length > 0 && <ul className="list-disc ml-5 text-sm space-y-1">{result.issues.map((i, k) => <li key={k}><b>{i.element || "Modèle"}</b> : {i.message}</li>)}</ul>}
          {activeCase && <><select aria-label="Cas de charge" className={selectClass} value={activeCase.id} onChange={ev => setCaseId(ev.target.value)}>{result.cases.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select>
            <div className="flex flex-wrap gap-6 text-sm"><span>Charges externes : <b>{activeCase.external_kn.toFixed(3)} kN</b></span><span>Réactions au sol : <b>{activeCase.ground_kn.toFixed(3)} kN</b></span></div>
            <div className="overflow-auto"><table className="w-full text-sm"><thead><tr className="text-left border-b"><th className="p-2">Repère</th><th>Total (kN)</th><th>Efforts / pressions</th></tr></thead><tbody>{activeCase.elements.map(r => <tr key={r.id} className="border-b"><td className="p-2 font-medium">{r.id}</td><td>{r.total_kn.toFixed(3)}</td><td>{r.kind === "beam" ? `Mmax ${r.moment_max_knm.toFixed(3)} kN.m · Vmax ${r.shear_max_kn.toFixed(3)} kN` : r.kind === "footing" ? `q moyen ${r.mean_pressure_kpa.toFixed(3)} kPa` : r.axial_stress_mpa !== undefined ? `σ moyen ${r.axial_stress_mpa.toFixed(4)} MPa` : "Répartition tributaire"}</td></tr>)}</tbody></table></div>
          </>}
          {envelope && envelope.elements?.some(e => Object.keys(e.uls || {}).length || Object.keys(e.sls || {}).length) && <details data-testid="envelope-block" open><summary className="cursor-pointer text-sm font-medium">Combinaison dimensionnante par élément (enveloppe EN 1990)</summary>
            <div className="overflow-auto mt-2"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Repère</th><th>ELU — effort dimensionnant</th><th>Combinaison</th><th>ELS</th></tr></thead><tbody>{envelope.elements.filter(e => Object.keys(e.uls || {}).length || Object.keys(e.sls || {}).length).map(e => { const u = e.uls.moment_knm || e.uls.axial_kn || e.uls.pressure_kpa; const uk = e.uls.moment_knm ? `M ${e.uls.moment_knm.value} kN·m${e.uls.shear_kn ? ` · V ${e.uls.shear_kn.value} kN` : ""}` : e.uls.axial_kn ? `N ${e.uls.axial_kn.value} kN` : e.uls.pressure_kpa ? `q ${e.uls.pressure_kpa.value} kPa` : "—"; return <tr key={e.id} className="border-b"><td className="p-1 font-medium">{e.id}</td><td>{uk}</td><td>{u?.label || "—"}</td><td>{e.sls.deflection_mm ? `flèche ${e.sls.deflection_mm.value} mm` : "—"}</td></tr>; })}</tbody></table></div>
            <p className="text-[11px] text-muted-foreground mt-1">{envelope.note}</p></details>}
          <details><summary className="cursor-pointer text-sm">Domaine et limites du calcul</summary><ul className="list-disc ml-5 text-xs mt-2 space-y-1">{result.limits.map(x => <li key={x}>{x}</li>)}</ul></details>
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="ec2-panel">
          <h2 className="font-semibold">EN 1992 — Armatures béton armé (poutres)</h2>
          <p className="text-sm text-muted-foreground">À partir du <b>moment et de l'effort tranchant dimensionnants</b> de l'enveloppe EN 1990, calcul déterministe de l'acier nécessaire (flexion simple/double, effort tranchant, As mini/maxi). Coefficients usuels AN FR, <b>à vérifier par l'ingénieur</b>. Aucune résistance validée.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Classe béton<select className={selectClass} value={ec2opts.fck} onChange={ev => setEc2opts({ ...ec2opts, fck: Number(ev.target.value) })} data-testid="ec2-fck">{(ec2cat?.concrete || [{ key: "C25/30", fck: 25 }]).map(c => <option key={c.key} value={c.fck}>{c.key}</option>)}</select></label>
            <label className="space-y-1">Acier fyk (MPa)<Input type="number" step="any" value={ec2opts.fyk} onChange={ev => setEc2opts({ ...ec2opts, fyk: Number(ev.target.value) })} data-testid="ec2-fyk" /></label>
            <label className="space-y-1">Enrobage d' (m)<Input type="number" step="any" value={ec2opts.cover_m} onChange={ev => setEc2opts({ ...ec2opts, cover_m: Number(ev.target.value) })} data-testid="ec2-cover" /></label>
            <label className="space-y-1">γc<Input type="number" step="any" value={ec2opts.gamma_c} onChange={ev => setEc2opts({ ...ec2opts, gamma_c: Number(ev.target.value) })} /></label>
            <label className="space-y-1">γs<Input type="number" step="any" value={ec2opts.gamma_s} onChange={ev => setEc2opts({ ...ec2opts, gamma_s: Number(ev.target.value) })} /></label>
            <label className="space-y-1">cot θ (1 à 2,5)<Input type="number" step="any" value={ec2opts.cot_theta} onChange={ev => setEc2opts({ ...ec2opts, cot_theta: Number(ev.target.value) })} data-testid="ec2-cottheta" /></label>
          </div>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-xs border-t pt-3">
            <label className="space-y-1 col-span-3 md:col-span-6 text-muted-foreground">Plan de ferraillage (proposition couvrant l'As) — <b>dispositions à vérifier</b></label>
            <label className="space-y-1">Barres long. Ø (mm)<select className={selectClass} value={ec2opts.bar_mm} onChange={ev => setEc2opts({ ...ec2opts, bar_mm: Number(ev.target.value) })} data-testid="ec2-bar">{[8, 10, 12, 14, 16, 20, 25, 32].map(d => <option key={d} value={d}>{`Ø${d}`}</option>)}</select></label>
            <label className="space-y-1">Cadres Ø (mm)<select className={selectClass} value={ec2opts.stirrup_mm} onChange={ev => setEc2opts({ ...ec2opts, stirrup_mm: Number(ev.target.value) })} data-testid="ec2-stirrup">{[6, 8, 10, 12].filter(d => [8, 10, 12].includes(d)).map(d => <option key={d} value={d}>{`Ø${d}`}</option>)}</select></label>
            <label className="space-y-1">Brins de cadre<select className={selectClass} value={ec2opts.legs} onChange={ev => setEc2opts({ ...ec2opts, legs: Number(ev.target.value) })} data-testid="ec2-legs">{[2, 3, 4].map(d => <option key={d} value={d}>{d}</option>)}</select></label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={designEc2} data-testid="ec2-design"><Calculator className="h-4 w-4 mr-2" />Calculer les armatures EN 1992</Button>
            {ec2res && <Button variant="outline" onClick={exportFerraillage} data-testid="ec2-pdf"><FileDown className="h-4 w-4 mr-2" />Note de ferraillage (PDF)</Button>}
          </div>
          {ec2res && <div className="overflow-auto" data-testid="ec2-results">
            {ec2res.reinjected_from_automation && <p className="text-[11px] text-emerald-800 mb-1" data-testid="ec2-reinjected">Aciers choisis par la chaîne automatique réinjectés dans la vérification EN 1992 (dossier BET unifié).</p>}
            <table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Poutre</th><th>b×h · d (m)</th><th>M dim → As flexion</th><th>V dim → Asw/s</th><th>As mini / maxi</th><th>Ferraillage (à vérifier)</th></tr></thead>
              <tbody>{ec2res.elements.map(r => r.status !== "ok"
                ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={5} className="text-amber-700">{r.message}</td></tr>
                : <tr key={r.id} className="border-b align-top">
                    <td className="p-1 font-medium">{r.id}</td>
                    <td>{r.b_m}×{r.h_m} · {r.d_m}</td>
                    <td><b>M {r.med_knm} kN·m</b> → <b>{r.design.flexure.as_req_cm2} cm²</b><div className="text-[10px] text-muted-foreground">{r.design.flexure.mode === "double" ? `double · As'=${r.design.flexure.as_comp_cm2} cm²` : "flexion simple"} · μ={r.design.flexure.mu}/{r.design.flexure.mu_lim} · {r.med_case}</div></td>
                    <td>{r.ved_kn != null ? <><b>V {r.ved_kn} kN</b> → <b>{r.design.shear.asw_s_req_cm2_m} cm²/m</b><div className="text-[10px] text-muted-foreground">{r.design.shear.needs_stirrups ? `cadres · cot θ=${r.design.shear.cot_theta} · s≤${r.design.shear.s_max_m} m` : `V_Rd,c=${r.design.shear.vrdc_kn} kN suffisant · mini`}</div></> : "—"}</td>
                    <td>{r.design.flexure.as_min_cm2} / {r.design.flexure.as_max_cm2} cm²</td>
                    <td>{r.scheme ? <><b>{r.scheme.longitudinal.label}</b>{r.scheme.stirrups ? <> · {r.scheme.stirrups.label}</> : ""}{r.reinforcement_source === "automation" && <span data-testid={`ec2-auto-${r.id}`} className={`ml-1 text-[10px] font-semibold ${r.provided_ok ? "text-emerald-700" : "text-red-700"}`}>· auto {r.provided_ok ? "✓ suffisant" : "✗ insuffisant"}</span>}<div className="text-[10px] text-muted-foreground">As,prov {r.scheme.longitudinal.as_provided_cm2} cm² (req {r.scheme.longitudinal.as_req_cm2}){r.scheme.stirrups ? ` · ${r.scheme.stirrups.asw_s_prov_cm2_m} cm²/m` : ""}{r.reinforcement_source === "automation" ? " · aciers auto réinjectés" : ""}</div></> : "—"}</td>
                  </tr>)}</tbody></table>
            {ec2res.elements.some(r => r.status === "ok" && (r.design.warnings || []).length) && <ul className="list-disc ml-5 mt-2 text-amber-700 text-[11px]" data-testid="ec2-warnings">{ec2res.elements.filter(r => r.status === "ok").flatMap(r => (r.design.warnings || []).map((w, i) => <li key={r.id + i}>{r.id} : {w}</li>))}</ul>}
            <p className="text-[11px] text-muted-foreground mt-1">{ec2res.note}</p>
          </div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="ec7-panel">
          <h2 className="font-semibold">EN 1997 — Portance des fondations (semelles)</h2>
          <p className="text-sm text-muted-foreground">À partir de la <b>pression dimensionnante</b> de l'enveloppe EN 1990, portance admissible (Annexe D, charge verticale centrée). Approche DA2 AN FR par défaut. Le rapport q_Ed/q_Rd est <b>indicatif</b> — ne vaut pas vérification réglementaire, à valider par l'ingénieur.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Régime<select className={selectClass} value={ec7opts.mode} onChange={ev => setEc7opts({ ...ec7opts, mode: ev.target.value })} data-testid="ec7-mode"><option value="drained">Drainé (c', φ')</option><option value="undrained">Non drainé (cu)</option></select></label>
            <label className="space-y-1">Encastrement D (m)<Input type="number" step="any" value={ec7opts.d_m} onChange={ev => setEc7opts({ ...ec7opts, d_m: Number(ev.target.value) })} /></label>
            <label className="space-y-1">γ sol (kN/m³)<Input type="number" step="any" value={ec7opts.gamma_soil} onChange={ev => setEc7opts({ ...ec7opts, gamma_soil: Number(ev.target.value) })} /></label>
            {ec7opts.mode === "drained" ? <>
              <label className="space-y-1">φ' (°)<Input type="number" step="any" value={ec7opts.phi_deg} onChange={ev => setEc7opts({ ...ec7opts, phi_deg: Number(ev.target.value) })} data-testid="ec7-phi" /></label>
              <label className="space-y-1">c' (kPa)<Input type="number" step="any" value={ec7opts.c_kpa} onChange={ev => setEc7opts({ ...ec7opts, c_kpa: Number(ev.target.value) })} /></label>
            </> : <label className="space-y-1">cu (kPa)<Input type="number" step="any" value={ec7opts.cu_kpa} onChange={ev => setEc7opts({ ...ec7opts, cu_kpa: Number(ev.target.value) })} data-testid="ec7-cu" /></label>}
            <label className="space-y-1">γR;v<Input type="number" step="any" value={ec7opts.gamma_Rv} onChange={ev => setEc7opts({ ...ec7opts, gamma_Rv: Number(ev.target.value) })} /></label>
          </div>
          <Button variant="outline" onClick={designEc7} data-testid="ec7-design"><Calculator className="h-4 w-4 mr-2" />Calculer la portance EN 1997</Button>
          {ec7res && <div className="overflow-auto" data-testid="ec7-results"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Semelle</th><th>B×L (m)</th><th>q_Ed (kPa)</th><th>q_Rd (kPa)</th><th>Utilisation q_Ed/q_Rd</th></tr></thead>
            <tbody>{ec7res.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={4} className="text-amber-700">{r.message || r.result?.message}</td></tr>
              : <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td>{r.result.B_m}×{r.result.L_m}</td><td>{r.result.q_ed_kpa}</td><td>{r.result.q_Rd_kpa}</td><td><Util u={r.result.utilisation} /></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{ec7res.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="spans-panel">
          <h2 className="font-semibold">Portées des poutres</h2>
          <p className="text-sm text-muted-foreground">Automatiques d'après le plan (longueur saisie). Les <b>flèches SLS</b> utilisent TOUJOURS la portée du plan automatiquement. Ce champ ne sert qu'au <b>Mcr automatique (EN 1993)</b> quand le plan ne marque pas la longueur d'une poutre.</p>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
            {Object.keys(spans).length === 0 ? <span className="text-muted-foreground">Aucune poutre dans le modèle.</span> : Object.entries(spans).map(([id, v]) => {
              const fromPlan = ((study?.model?.elements) || []).some(e => e.id === id && e.length_m != null);
              return <label key={id} className="space-y-1">{id} · L (m) <span className={fromPlan ? "text-emerald-700" : "text-amber-700"}>{fromPlan ? "du plan" : "à saisir"}</span>
                <Input type="number" step="any" value={v} onChange={ev => setSpans({ ...spans, [id]: ev.target.value })} data-testid={`span-${id}`} /></label>;
            })}
          </div>
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="ec3-panel">
          <h2 className="font-semibold">EN 1993 — Vérification acier (poutres)</h2>
          <p className="text-sm text-muted-foreground">À partir du <b>M et V dimensionnants</b> de l'enveloppe : résistance de section (flexion, cisaillement) et déversement. Propriétés de profils publiques (EN 10365). Rapports <b>indicatifs</b>, à valider par l'ingénieur.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Profil<select className={selectClass} value={ec3opts.profile} onChange={ev => setEc3opts({ ...ec3opts, profile: ev.target.value })} data-testid="ec3-profile">{ec3cat?.families ? Object.entries(ec3cat.families).map(([fam, keys]) => <optgroup key={fam} label={fam}>{keys.map(k => <option key={k} value={k}>{k}</option>)}</optgroup>) : <option value="IPE300">IPE300</option>}</select></label>
            <label className="space-y-1">Nuance<select className={selectClass} value={ec3opts.grade} onChange={ev => setEc3opts({ ...ec3opts, grade: ev.target.value })} data-testid="ec3-grade">{Object.keys(ec3cat?.grades || { S235: 235, S275: 275, S355: 355 }).map(g => <option key={g} value={g}>{g}</option>)}</select></label>
            <label className="space-y-1">Classe section<select className={selectClass} value={ec3opts.section_class} onChange={ev => setEc3opts({ ...ec3opts, section_class: ev.target.value })} data-testid="ec3-section-class"><option value="">Auto (Table 5.2)</option>{[1, 2, 3].map(c => <option key={c} value={c}>{`Classe ${c}`}</option>)}</select></label>
            <label className="space-y-1">Courbe déver.<select className={selectClass} value={ec3opts.buckling_curve} onChange={ev => setEc3opts({ ...ec3opts, buckling_curve: ev.target.value })} data-testid="ec3-ltcurve"><option value="">Auto (Table 6.4)</option>{["a", "b", "c", "d"].map(c => <option key={c} value={c}>{c}</option>)}</select></label>
            <label className="space-y-1">C1 (déversement)<Input type="number" step="any" value={ec3opts.c1} onChange={ev => setEc3opts({ ...ec3opts, c1: Number(ev.target.value) })} data-testid="ec3-c1" /></label>
            <label className="space-y-1">Mcr manuel (sinon auto)<Input type="number" step="any" placeholder="auto du plan" value={ec3opts.mcr_knm} onChange={ev => setEc3opts({ ...ec3opts, mcr_knm: ev.target.value })} data-testid="ec3-mcr" /></label>
            <label className="space-y-1">γM0<Input type="number" step="any" value={ec3opts.gamma_m0} onChange={ev => setEc3opts({ ...ec3opts, gamma_m0: Number(ev.target.value) })} /></label>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs border-t pt-3">
            <label className="space-y-1 col-span-2 md:col-span-6 text-muted-foreground">Poteaux — flexion composée N+M par la <b>méthode réglementaire §6.3.3 (méthode 2, Annexe B)</b> : flambement des deux axes χy/χz (courbes auto Table 6.2) + déversement χLT, facteurs d'interaction <b>kyy/kzy</b> (éq. 6.61 &amp; 6.62). N auto de l'enveloppe, Lcr auto du plan (K×h).</label>
            <label className="space-y-1">K long. flamb.<Input type="number" step="any" value={ec3opts.k_buckling} onChange={ev => setEc3opts({ ...ec3opts, k_buckling: Number(ev.target.value) })} data-testid="ec3-k" /></label>
            <label className="space-y-1">Lcr manuel (m)<Input type="number" step="any" placeholder="auto K×h" value={ec3opts.lcr_m} onChange={ev => setEc3opts({ ...ec3opts, lcr_m: ev.target.value })} data-testid="ec3-lcr" /></label>
            <label className="space-y-1">M appliqué (kN·m)<Input type="number" step="any" placeholder="0" value={ec3opts.med_col_knm} onChange={ev => setEc3opts({ ...ec3opts, med_col_knm: ev.target.value })} data-testid="ec3-medcol" /></label>
            <label className="space-y-1">Cmy<select className={selectClass} value={ec3opts.cmy} onChange={ev => setEc3opts({ ...ec3opts, cmy: Number(ev.target.value) })} data-testid="ec3-cmy">{(ec3cat?.cm_presets || [{ label: "0.9", value: 0.9 }]).map(c => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
            <label className="space-y-1">CmLT<select className={selectClass} value={ec3opts.cm_lt} onChange={ev => setEc3opts({ ...ec3opts, cm_lt: Number(ev.target.value) })} data-testid="ec3-cmlt">{(ec3cat?.cm_presets || [{ label: "0.9", value: 0.9 }]).map(c => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
            <label className="flex items-end gap-2 text-xs"><input type="checkbox" checked={!!ec3opts.lateral_restraint} onChange={ev => setEc3opts({ ...ec3opts, lateral_restraint: ev.target.checked })} data-testid="ec3-lateral" />Maintien latéral (χLT=1)</label>
          </div>
          <Button variant="outline" onClick={designEc3} data-testid="ec3-design"><Calculator className="h-4 w-4 mr-2" />Vérifier l'acier EN 1993</Button>
          {ec3res && <div className="overflow-auto" data-testid="ec3-results"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Poutre</th><th>Flexion M/Mc,Rd</th><th>Cisaillement V/Vpl,Rd</th><th>Déversement M/Mb,Rd</th></tr></thead>
            <tbody>{ec3res.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={3} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}<div className="text-[10px] text-muted-foreground">{r.profile}/{r.grade}{r.section_class ? ` · classe ${r.section_class} (${r.class_mode})` : ""}{r.span_m ? ` · L=${r.span_m}m (${r.span_source})` : ""}</div></td>
                  <td><Util u={r.result.bending.utilisation} /><div className="text-[10px] text-muted-foreground">{r.result.bending.mv_interaction ? `Mc,Rd réduit ${r.result.bending.mc_rd_eff_knm} (M-V)` : `Mc,Rd ${r.result.bending.mc_rd_knm}`} kN·m</div></td>
                  <td><Util u={r.result.shear.utilisation} /><div className="text-[10px] text-muted-foreground">Vpl,Rd {r.result.shear.vpl_rd_kn} kN</div></td>
                  <td><Util u={r.result.lateral_torsional.utilisation} /><div className="text-[10px] text-muted-foreground">{r.result.lateral_torsional.note || `Mb,Rd ${r.result.lateral_torsional.mb_rd_knm} · Mcr ${r.mcr_knm} (${r.mcr_source})`}</div></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{ec3res.note}</p></div>}
          {ec3res?.columns?.length > 0 && <div className="overflow-auto mt-2" data-testid="ec3-columns"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Poteau</th><th>N dim (kN)</th><th>Lcr (m)</th><th>Flambement (χy/χz)</th><th>Interaction N+M (§6.3.3 · kyy/kzy)</th></tr></thead>
            <tbody>{ec3res.columns.map(c => c.status !== "ok"
              ? <tr key={c.id} className="border-b"><td className="p-1 font-medium">{c.id}</td><td colSpan={4} className="text-amber-700">{c.message}</td></tr>
              : <tr key={c.id} className="border-b align-top"><td className="p-1 font-medium">{c.id}<div className="text-[10px] text-muted-foreground">{c.profile}/{c.grade} · classe {c.section_class} ({c.class_mode})</div></td>
                  <td>{c.ned_kn}<div className="text-[10px] text-muted-foreground">{c.ned_case}</div></td>
                  <td>{c.lcr_m} <span className="text-[10px] text-muted-foreground">({c.lcr_source})</span></td>
                  <td><Util u={c.result.buckling.utilisation} /><div className="text-[10px] text-muted-foreground">Nb,Rd {c.result.nb_rd_kn} kN · χy={c.result.chi_y} / χz={c.result.chi_z}</div></td>
                  <td>{c.result.interaction ? <><Util u={c.result.interaction.utilisation} /><div className="text-[10px] text-muted-foreground">(6.61)={c.result.interaction.eq_661} · (6.62)={c.result.interaction.eq_662} · kyy={c.result.interaction.kyy} kzy={c.result.interaction.kzy} · χLT={c.result.interaction.chi_lt}</div></> : <span className="text-muted-foreground">N seul (M=0)</span>}</td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">Flexion composée des poteaux : méthode 2 (Annexe B) — équations 6.61 &amp; 6.62, facteurs kyy/kzy. Indicatif, à valider.</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="sls-panel">
          <h2 className="font-semibold">Flèches en service (SLS · EN 1990)</h2>
          <p className="text-sm text-muted-foreground">Flèches élastiques de l'enveloppe <b>caractéristique</b> et <b>quasi-permanente</b> (selon l'EI saisi : béton/acier/bois) comparées à L/ratio. Portée <b>100 % automatique d'après la géométrie du plan</b> (length_m), pour toutes les poutres, sans saisie manuelle. Rapport <b>indicatif</b>, à valider par l'ingénieur.</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <label className="space-y-1">Limite caractéristique L/<Input type="number" step="any" value={slsopts.ratio_char} onChange={ev => setSlsopts({ ...slsopts, ratio_char: Number(ev.target.value) })} data-testid="sls-ratio-char" /></label>
            <label className="space-y-1">Limite quasi-perm. L/<Input type="number" step="any" value={slsopts.ratio_qp} onChange={ev => setSlsopts({ ...slsopts, ratio_qp: Number(ev.target.value) })} data-testid="sls-ratio-qp" /></label>
          </div>
          <Button variant="outline" onClick={designSls} data-testid="sls-design"><Calculator className="h-4 w-4 mr-2" />Vérifier les flèches</Button>
          {slsres && <div className="overflow-auto" data-testid="sls-results"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Poutre</th><th>Portée (m)</th><th>Caractéristique (w / limite)</th><th>Quasi-permanente (w / limite)</th></tr></thead>
            <tbody>{slsres.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={3} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}</td><td>{r.span_m} <span className="text-[10px] text-muted-foreground">({r.span_source})</span></td>
                  <td><Util u={r.char.utilisation} /><div className="text-[10px] text-muted-foreground">{r.char.w_mm ?? "—"} / {r.char.limit_mm} mm ({r.char.ratio_label})</div></td>
                  <td><Util u={r.qp.utilisation} /><div className="text-[10px] text-muted-foreground">{r.qp.w_mm ?? "—"} / {r.qp.limit_mm} mm ({r.qp.ratio_label})</div></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{slsres.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="crack-panel">
          <h2 className="font-semibold">EN 1992 §7.3 — Fissuration du béton (ELS quasi-permanent)</h2>
          <p className="text-sm text-muted-foreground">Ouverture de fissures wk et As mini de fissuration, sous moment <b>quasi-permanent</b> de l'enveloppe, à partir du ferraillage proposé (classe béton / enrobage / Ø du panneau EN 1992). Rapport <b>indicatif</b>, à valider par l'ingénieur.</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <label className="space-y-1">wk,max (mm)<Input type="number" step="any" value={crackopts.w_max_mm} onChange={ev => setCrackopts({ w_max_mm: Number(ev.target.value) })} data-testid="crack-wmax" /></label>
          </div>
          <Button variant="outline" onClick={designCrack} data-testid="crack-design"><Calculator className="h-4 w-4 mr-2" />Vérifier la fissuration</Button>
          {crackres && <div className="overflow-auto" data-testid="crack-results">{crackres.reinjected_from_automation && <p className="text-[11px] text-emerald-800 mb-1" data-testid="crack-reinjected">Ø issu des aciers choisis par la chaîne automatique (réinjectés dans la fissuration §7.3).</p>}<table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Poutre</th><th>Mqp (kN·m)</th><th>σs (MPa)</th><th>wk / wk,max (mm)</th><th>As,min fiss. (cm²)</th></tr></thead>
            <tbody>{crackres.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={4} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}</td><td>{r.mqp_knm}<div className="text-[10px] text-muted-foreground">{r.mqp_case}</div></td><td>{r.sigma_s_mpa}</td>
                  <td><Util u={r.utilisation} /><div className="text-[10px] text-muted-foreground">{r.wk_mm} / {r.wmax_mm} · sr,max {r.sr_max_mm}mm · Ø{r.bar_mm}{r.reinforcement_source === "automation" ? " auto" : ""}</div></td>
                  <td>{r.as_min_fiss_cm2}</td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{crackres.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="anc-panel">
          <h2 className="font-semibold">EN 1992 §8.4/§8.7 — Ancrages & recouvrements</h2>
          <p className="text-sm text-muted-foreground">Longueur d'ancrage <b>lbd</b> (§8.4) et de recouvrement <b>l0</b> (§8.7) calculées à partir du <b>ferraillage proposé</b> (Ø barre, classe béton, enrobage, As,req/As,prov du panneau EN 1992). Conditions d'adhérence et ρ1 (% barres en recouvrement) éditables. Rapport <b>indicatif</b>, à valider par l'ingénieur.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Adhérence<select className={selectClass} value={ancopts.bond} onChange={ev => setAncopts({ ...ancopts, bond: ev.target.value })} data-testid="anc-bond"><option value="good">Bonne (η1=1,0)</option><option value="poor">Médiocre (η1=0,7)</option></select></label>
            <label className="space-y-1">ρ1 recouvr. (%)<Input type="number" step="any" value={ancopts.rho1_pct} onChange={ev => setAncopts({ ...ancopts, rho1_pct: Number(ev.target.value) })} data-testid="anc-rho1" /></label>
            <label className="space-y-1">α1 (forme)<Input type="number" step="any" value={ancopts.alpha1} onChange={ev => setAncopts({ ...ancopts, alpha1: Number(ev.target.value) })} data-testid="anc-a1" /></label>
            <label className="space-y-1">α3 (transv.)<Input type="number" step="any" value={ancopts.alpha3} onChange={ev => setAncopts({ ...ancopts, alpha3: Number(ev.target.value) })} data-testid="anc-a3" /></label>
            <label className="space-y-1">α4 (soudé)<Input type="number" step="any" value={ancopts.alpha4} onChange={ev => setAncopts({ ...ancopts, alpha4: Number(ev.target.value) })} data-testid="anc-a4" /></label>
            <label className="space-y-1">α5 (pression)<Input type="number" step="any" value={ancopts.alpha5} onChange={ev => setAncopts({ ...ancopts, alpha5: Number(ev.target.value) })} data-testid="anc-a5" /></label>
          </div>
          <Button variant="outline" onClick={designAnchorage} data-testid="anc-design"><Calculator className="h-4 w-4 mr-2" />Calculer ancrages & recouvrements</Button>
          {ancres && <div className="overflow-auto" data-testid="anc-results">{ancres.reinjected_from_automation && <p className="text-[11px] text-emerald-800 mb-1" data-testid="anc-reinjected">Ø et As,prov issus des aciers choisis par la chaîne automatique (réinjectés dans §8.4/§8.7).</p>}<table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Poutre</th><th>Barre</th><th>fbd (MPa)</th><th>lb,rqd (m)</th><th>Ancrage lbd (m · ×Ø)</th><th>Recouvrement l0 (m · ×Ø)</th></tr></thead>
            <tbody>{ancres.elements.map(r => r.status !== "ok"
              ? <tr key={r.id} className="border-b"><td className="p-1 font-medium">{r.id}</td><td colSpan={5} className="text-amber-700">{r.message}</td></tr>
              : <tr key={r.id} className="border-b align-top"><td className="p-1 font-medium">{r.id}</td><td>{r.bar_label || `Ø${r.result.bar_mm}`}{r.reinforcement_source === "automation" ? <span className="text-[10px] text-emerald-700"> · auto</span> : ""}</td><td>{r.result.fbd_mpa}</td><td>{r.result.lb_rqd_m}</td>
                  <td>{r.result.lbd_m} m <span className="text-[10px] text-muted-foreground">({r.result.lbd_ratio_phi}Ø)</span></td>
                  <td>{r.result.l0_m} m <span className="text-[10px] text-muted-foreground">({r.result.l0_ratio_phi}Ø · α6={r.result.alpha6})</span></td></tr>)}</tbody></table>
            <p className="text-[11px] text-muted-foreground mt-1">{ancres.note}</p></div>}
        </Card>}
        {!dirty && result && result.status === "mechanical_only" && <Card className="p-5 space-y-3" data-testid="ec5-panel">
          <h2 className="font-semibold">EN 1995 — Vérification bois (poutres)</h2>
          <p className="text-sm text-muted-foreground">À partir du <b>M et V dimensionnants</b> : flexion, cisaillement (kcr) et déversement. kmod selon durée × classe de service, γM et classes EN 338/EN 14080. Rapports <b>indicatifs</b>, à valider par l'ingénieur.</p>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
            <label className="space-y-1">Classe bois<select className={selectClass} value={ec5opts.strength_class} onChange={ev => setEc5opts({ ...ec5opts, strength_class: ev.target.value })} data-testid="ec5-class">{(ec5cat?.classes || [{ key: "C24" }]).map(c => <option key={c.key} value={c.key}>{c.key}</option>)}</select></label>
            <label className="space-y-1">Classe de service<select className={selectClass} value={ec5opts.service_class} onChange={ev => setEc5opts({ ...ec5opts, service_class: ev.target.value })} data-testid="ec5-sc">{["1", "2", "3"].map(c => <option key={c} value={c}>{c}</option>)}</select></label>
            <label className="space-y-1">Durée de charge<select className={selectClass} value={ec5opts.load_duration} onChange={ev => setEc5opts({ ...ec5opts, load_duration: ev.target.value })} data-testid="ec5-dur">{(ec5cat?.load_durations || ["permanent", "long", "medium", "short", "instantaneous"]).map(d => <option key={d} value={d}>{d}</option>)}</select></label>
            <label className="space-y-1">lef (m, option.)<Input type="number" step="any" placeholder="pour déver." value={ec5opts.lef_m} onChange={ev => setEc5opts({ ...ec5opts, lef_m: ev.target.value })} data-testid="ec5-lef" /></label>
            <label className="space-y-1">kcr<Input type="number" step="any" value={ec5opts.kcr} onChange={ev => setEc5opts({ ...ec5opts, kcr: Number(ev.target.value) })} /></label>
            <label className="space-y-1">γM (option.)<Input type="number" step="any" placeholder="auto" value={ec5opts.gamma_m} onChange={ev => setEc5opts({ ...ec5opts, gamma_m: ev.target.value })} /></label>
          </div>
          <Button variant="outline" onClick={designEc5} data-testid="ec5-design"><Calculator className="h-4 w-4 mr-2" />Vérifier le bois EN 1995</Button>
          {ec5res && <div className="overflow-auto" data-testid="ec5-results"><table className="w-full text-xs"><thead><tr className="text-left border-b"><th className="p-1">Poutre</th><th>Flexion</th><th>Cisaillement</th><th>Déversement</th></tr></thead>
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
          <h2 className="font-semibold">Dossier BET complet (PDF)</h2>
          <p className="text-sm text-muted-foreground">Rassemble les chapitres cochés (combinaisons EN 1990 → armatures / profils / sections → portance → flèches / fissuration) dans une seule note, carimbée « NON EXÉCUTOIRE — à vérifier par l'ingénieur », avec les réglages des panneaux ci-dessus.</p>
          <div className="flex flex-wrap gap-4 text-xs">
            {[["ec2", "Béton EN 1992"], ["crack", "Fissuration §7.3"], ["anchorage", "Ancrages §8.4/§8.7"], ["ec3", "Acier EN 1993"], ["ec5", "Bois EN 1995"], ["ec7", "Fondations EN 1997"], ["sls", "Flèches SLS"], ["reinforcement", "Ferraillage manuel"], ["architecture", "Contrôles archi PC"], ["linked", "Aciers liés"], ["lintel", "Linteau (ouverture)"]].map(([k, label]) => <label key={k} className="flex items-center gap-1"><input type="checkbox" checked={!!dossierInc[k]} onChange={ev => setDossierInc({ ...dossierInc, [k]: ev.target.checked })} data-testid={`dossier-${k}`} />{label}</label>)}
          </div>
          <Button onClick={exportDossier} data-testid="dossier-export"><FileDown className="h-4 w-4 mr-2" />Télécharger le dossier BET</Button>
        </Card>}
      </>}
    </fieldset>
  </div>;
}

function JsonModel({ model, onChange }) {
  const [value, setValue] = useState(""), [error, setError] = useState("");
  useEffect(() => { setValue(JSON.stringify({ actions: model.actions, self_weight_action: model.self_weight_action, combinations: model.combinations }, null, 2)); }, [model.actions, model.self_weight_action, model.combinations]);
  return <div className="space-y-2 mt-3"><textarea aria-label="Actions et combinaisons" className="w-full border rounded p-2 font-mono text-xs" rows={10} value={value} onChange={ev => setValue(ev.target.value)} />
    <Button size="sm" variant="outline" onClick={() => { try { const v = JSON.parse(value); if (!Array.isArray(v.actions) || !Array.isArray(v.combinations)) throw new Error(); onChange({ ...model, actions: v.actions, self_weight_action: v.self_weight_action, combinations: v.combinations }); setError(""); } catch { setError("Format invalide : actions et combinations doivent être des listes."); } }}>Appliquer</Button>{error && <p role="alert" className="text-red-700 text-sm">{error}</p>}
  </div>;
}
