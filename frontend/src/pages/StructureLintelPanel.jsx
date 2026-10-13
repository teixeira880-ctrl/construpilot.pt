import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Calculator, DoorOpen, FileDown, Save, Trash2, Wand2, Plus } from "lucide-react";

const sel = "border rounded-md p-2 bg-background text-sm w-full";
const n = v => (v === "" || v === null || v === undefined ? null : Number(v));
const uid = () => `lint_${Math.random().toString(16).slice(2, 10)}`;

function Num({ label, value, onChange, testid, disabled }) {
  return <label className="block text-xs min-w-0">{label}<Input aria-label={label} data-testid={testid} disabled={disabled} type="number" step="any" className="mt-1" value={value ?? ""} onChange={e => onChange(n(e.target.value))} /></label>;
}

export const DEFAULT_LINTEL = {
  clear_span_m: 2.4, wall_thickness_m: 0.2, masonry_unit_weight_kn_m3: 20, masonry_height_above_m: 2.6,
  load_model: "arching", arch_angle_deg: 60, permanent_line_kn_m: 0, variable_line_kn_m: 0, psi2: 0.3,
  bearing_length_m: 0.2, masonry_comp_strength_mpa: 0.6, deflection_limit_total: 300, deflection_limit_qp: 500,
  material: "both", steel_grade: "S235", steel_families: ["IPE", "HEA", "HEB"], max_profiles: 2,
  gamma_m0: 1.0, gamma_m1: 1.0, lateral_restraint_masonry: true, ltb_c1: 1.12,
  rc_width_m: null, rc_height_m: null, fck: 25, fyk: 500, bar_mm: 12,
  steel_eur_per_kg: 3, concrete_eur_per_m3: 180, rebar_eur_per_kg: 2,
};

// centre géométrique d'un élément rectangle implanté (coin + rotation)
const placed = e => [e.x_m, e.y_m, e.length_m, e.width_m].every(v => v !== null && Number.isFinite(v));
const center = e => { const a = (e.angle_deg || 0) * Math.PI / 180; return [e.x_m + (e.length_m / 2) * Math.cos(a) - (e.width_m / 2) * Math.sin(a), e.y_m + (e.length_m / 2) * Math.sin(a) + (e.width_m / 2) * Math.cos(a)]; };
const wallEnds = w => { const a = (w.angle_deg || 0) * Math.PI / 180, m = w.width_m / 2; const pt = dx => [w.x_m + dx * Math.cos(a) - m * Math.sin(a), w.y_m + dx * Math.sin(a) + m * Math.cos(a)]; return [pt(0), pt(w.length_m)]; };

export default function StructureLintelPanel({ study, model, opts, setOpts, base, busy, saveModel }) {
  const [res, setRes] = useState(null);
  const [running, setRunning] = useState(false);
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [name, setName] = useState("Ouverture");
  const [parentWall, setParentWall] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [saved, setSaved] = useState([]);
  const set = patch => setOpts({ ...opts, ...patch });
  const walls = (model?.elements || []).filter(e => e.kind === "wall");
  const piers = (model?.elements || []).filter(e => e.kind === "wall" || e.kind === "column");
  const toggleFamily = (f, on) => set({ steel_families: on ? [...opts.steel_families, f] : opts.steel_families.filter(x => x !== f) });
  const LINTELS = `${base}/${study.study_id}/lintels`;

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setSaved(study?.lintels || []); }, [study?.study_id, study?.revision]);

  const toPayload = e => ({ ...e.inputs, id: e.id, name: e.name, left: e.left, right: e.right });

  const persist = async list => {
    const { data } = await api.put(LINTELS, { lintels: list });
    setSaved(data.lintels);
    return data.lintels;
  };

  const applyReinject = (leftId, rightId, reactions, tag) => {
    if (!leftId || !rightId) { toast.error("Escolha os dois nembos/apoios que recebem a padieira"); return; }
    if (!reactions) { toast.error("Dimensione primeiro a padieira"); return; }
    const gAction = model.self_weight_action || (model.actions.find(a => a.kind === "G") || {}).id;
    const qAction = (model.actions.find(a => a.kind === "Q") || {}).id;
    if (!gAction) { toast.error("Nenhuma ação permanente G no modelo"); return; }
    const strip = loads => (loads || []).filter(l => (l.source?.document || "") !== tag);
    const mk = (action, value) => ({ action, value: Math.abs(Number(value) || 0), mode: "point", position_m: null, source: { document: tag, page: null, note: "Reação da padieira (reforço de abertura) — a validar" } });
    const targets = new Set([leftId, rightId]);
    const elements = model.elements.map(e => {
      const loads = strip(e.loads);
      if (targets.has(e.id)) {
        if (reactions.g_kn) loads.push(mk(gAction, reactions.g_kn));
        if (qAction && reactions.q_kn) loads.push(mk(qAction, reactions.q_kn));
      }
      return { ...e, loads };
    });
    saveModel({ ...model, gravity_model_reviewed: false, elements });
  };

  const reinject = () => applyReinject(left, right, res?.reactions, `LINTEL_REACTION:${editingId || study.study_id}`);
  const reinjectSaved = e => applyReinject(e.left, e.right, e.result?.reactions, `LINTEL_REACTION:${e.id}`);

  const autoDetect = () => {
    const w = walls.find(e => e.id === parentWall && placed(e)) || walls.find(placed);
    if (!w) { toast.error("Implante a parede da abertura (coordenadas x/y e dimensões) ou escolha os apoios manualmente"); return; }
    const cand = piers.filter(p => p.id !== w.id && placed(p));
    if (cand.length < 2) { toast.error("São necessários pelo menos dois nembos/pilares implantados para a deteção automática"); return; }
    const [Lp, Rp] = wallEnds(w);
    const d = (c, pt) => Math.hypot(c[0] - pt[0], c[1] - pt[1]);
    const byL = [...cand].sort((x, y) => d(center(x), Lp) - d(center(y), Lp));
    const byR = [...cand].sort((x, y) => d(center(x), Rp) - d(center(y), Rp));
    let l = byL[0], r = byR[0];
    if (l.id === r.id) r = byR.find(p => p.id !== l.id) || byL.find(p => p.id !== l.id);
    setLeft(l.id); setRight(r.id); setParentWall(w.id);
    toast.success(`Apoios detetados: esquerdo «${l.id} », droite « ${r.id} » — modifiables`);
  };

  const prefillWall = id => {
    const w = walls.find(e => e.id === id);
    if (!w) return;
    setParentWall(id);
    set({ wall_thickness_m: w.width_m ?? opts.wall_thickness_m, masonry_height_above_m: w.height_m ?? opts.masonry_height_above_m });
    toast.info(`Espessura e altura retomadas da parede${id}— introduza as cargas segundo a descida de cargas`);
  };

  const compute = async () => {
    if (!opts.clear_span_m) { toast.error("Indique o vão livre da abertura"); return; }
    setRunning(true);
    try {
      const { data } = await api.post(`${base}/${study.study_id}/opening/lintel`, opts);
      setRes(data);
      toast.success("Padieira dimensionada (indicativo)");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cálculo impossível");
    } finally { setRunning(false); }
  };

  const saveCurrent = async () => {
    if (!res) { toast.error("Dimensione a padieira antes de a guardar"); return; }
    const id = editingId || uid();
    const payload = { ...opts, id, name: name || "Ouverture", left: left || null, right: right || null };
    try {
      await persist([...saved.filter(e => e.id !== id).map(toPayload), payload]);
      setEditingId(id);
      toast.success(`Ouverture « ${payload.name}» guardada no estudo`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar"); }
  };

  const newOpening = () => { setEditingId(null); setRes(null); setName(`Ouverture ${saved.length + 1}`); setLeft(""); setRight(""); setOpts(DEFAULT_LINTEL); };

  const loadSaved = e => {
    setOpts({ ...DEFAULT_LINTEL, ...e.inputs });
    setName(e.name); setLeft(e.left || ""); setRight(e.right || ""); setRes(e.result); setEditingId(e.id);
    toast.info(`« ${e.name}» carregada no editor`);
  };

  const removeSaved = async e => {
    try { await persist(saved.filter(x => x.id !== e.id).map(toPayload)); if (editingId === e.id) setEditingId(null); toast.success("Abertura eliminada"); }
    catch (err) { toast.error("Não foi possível eliminar"); }
  };

  const exportLintel = async (e, fmt) => {
    try {
      const { data } = await api.get(`${LINTELS}/${e.id}/export/${fmt}`, { responseType: "blob" });
      const url = URL.createObjectURL(data), a = document.createElement("a");
      a.href = url; a.download = `linteau-${(e.name || "ouverture").replace(/[^a-z0-9]/gi, "-")}.${fmt}`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Planta cotada${fmt.toUpperCase()}descarregado`);
    } catch (err) { toast.error("Exportação impossível — guarde a abertura e tente novamente"); }
  };

  const Reco = ({ r }) => r?.recommendation
    ? <p className="text-sm font-medium text-emerald-800" data-testid="lintel-reco">Solução mais económica: {r.recommendation.material === "steel" ? "Aço" : "Betão armado"} — {r.recommendation.label} ({r.recommendation.cost_eur} €)</p>
    : null;

  const restrained = opts.lateral_restraint_masonry !== false;

  return <Card className="p-5 space-y-4" data-testid="lintel-panel">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-semibold flex items-center gap-2"><DoorOpen className="h-4 w-4" />Abertura em parede resistente (padieira NP EN 1992/1993)</h2>
      <Button variant="outline" size="sm" onClick={newOpening} data-testid="lintel-new"><Plus className="h-4 w-4 mr-1" />Nova abertura</Button>
    </div>
    <p className="text-sm text-muted-foreground">Descida da carga acima da abertura (efeito de arco ou retangular) e depois dimensionamento de uma <b>padieira metálica</b> (perfil mais leve) <b>e/ou de betão armado</b>, com flecha, apoio na alvenaria e encurvadura lateral opcional. A ferramenta indica a solução mais económica. Guarde várias aberturas: todas são anexadas ao processo de engenharia. Relatório <b>indicativo, não executório</b> — a validar pelo engenheiro.</p>

    {saved.length > 0 && <div className="space-y-2 border rounded-lg p-3 bg-muted/20" data-testid="lintel-saved-list">
      <h3 className="text-sm font-medium">Aberturas guardadas no estudo ({saved.length})</h3>
      <div className="space-y-2">{saved.map(e => {
        const reco = e.result?.recommendation;
        return <div key={e.id} className={`flex flex-wrap items-center gap-2 text-xs border rounded-md p-2 ${editingId === e.id ? "border-emerald-500 bg-emerald-50/50" : ""}`} data-testid={`lintel-saved-${e.id}`}>
          <span className="font-medium flex-1 min-w-[8rem]">{e.name}<span className="text-muted-foreground"> · L {e.inputs?.clear_span_m} m{reco ? ` · ${reco.material === "steel" ? "Aço" : "BA"} ${reco.label} (${reco.cost_eur} €)` : "· não resolvido"}{e.left && e.right ? ` · appuis ${e.left}/${e.right}` : ""}</span></span>
          <Button variant="ghost" size="sm" onClick={() => loadSaved(e)} data-testid={`lintel-load-${e.id}`}>Charger</Button>
          <Button variant="outline" size="sm" disabled={busy || !e.left || !e.right} onClick={() => reinjectSaved(e)} data-testid={`lintel-reinject-saved-${e.id}`}>Reinjetar</Button>
          <Button variant="outline" size="sm" onClick={() => exportLintel(e, "pdf")} data-testid={`lintel-pdf-${e.id}`}><FileDown className="h-3.5 w-3.5 mr-1" />PDF</Button>
          <Button variant="outline" size="sm" onClick={() => exportLintel(e, "dxf")} data-testid={`lintel-dxf-${e.id}`}>DXF</Button>
          <button aria-label={`Eliminar${e.name}`} onClick={() => removeSaved(e)} data-testid={`lintel-delete-${e.id}`}><Trash2 className="h-4 w-4 text-muted-foreground hover:text-red-600" /></button>
        </div>;
      })}</div>
    </div>}

    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
      <label className="block text-xs md:col-span-1">Nome da abertura<Input aria-label="Nome da abertura" data-testid="lintel-name" className="mt-1" value={name} onChange={e => setName(e.target.value)} placeholder="Vão da sala, porta da cozinha…" /></label>
      {walls.length > 0 && <label className="block text-xs">Parede da abertura (pré-preencher + deteção dos apoios)
        <select className={sel + " mt-1"} data-testid="lintel-prefill-wall" value={parentWall} onChange={e => prefillWall(e.target.value)}>
          <option value="">Escolher uma parede…</option>{walls.map(w => <option key={w.id} value={w.id}>{`${w.id} · ${w.level || ""}`}</option>)}
        </select></label>}
    </div>

    <div className="space-y-2">
      <h3 className="text-sm font-medium">Abertura &amp; parede</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Num label="Vão livre L (m)" value={opts.clear_span_m} onChange={v => set({ clear_span_m: v })} testid="lintel-span" />
        <Num label="Espessura da parede (m)" value={opts.wall_thickness_m} onChange={v => set({ wall_thickness_m: v })} testid="lintel-wall-thickness" />
        <Num label="Peso da alvenaria (kN/m³)" value={opts.masonry_unit_weight_kn_m3} onChange={v => set({ masonry_unit_weight_kn_m3: v })} />
        <Num label="Altura de alvenaria acima (m)" value={opts.masonry_height_above_m} onChange={v => set({ masonry_height_above_m: v })} />
        <label className="block text-xs">Modelo de carga<select className={sel + " mt-1"} value={opts.load_model} onChange={e => set({ load_model: e.target.value })} data-testid="lintel-model"><option value="arching">Efeito de arco (económico)</option><option value="rectangular">Retangular (do lado da segurança)</option></select></label>
        {opts.load_model === "arching" && <Num label="Ângulo do arco (°)" value={opts.arch_angle_deg} onChange={v => set({ arch_angle_deg: v })} />}
      </div>
    </div>

    <div className="space-y-2">
      <h3 className="text-sm font-medium">Cargas suportadas acima (por metro de parede)</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Num label="Permanentes G (kN/m)" value={opts.permanent_line_kn_m} onChange={v => set({ permanent_line_kn_m: v })} testid="lintel-perm" />
        <Num label="Exploitation Q (kN/m)" value={opts.variable_line_kn_m} onChange={v => set({ variable_line_kn_m: v })} testid="lintel-var" />
        <Num label="ψ2 (quasi-perm.)" value={opts.psi2} onChange={v => set({ psi2: v })} />
      </div>
    </div>

    <div className="space-y-2">
      <h3 className="text-sm font-medium">Apoio na alvenaria &amp; flecha</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Num label="Entrega / comprimento de apoio (m)" value={opts.bearing_length_m} onChange={v => set({ bearing_length_m: v })} />
        <Num label="Resistência da alvenaria (MPa)" value={opts.masonry_comp_strength_mpa} onChange={v => set({ masonry_comp_strength_mpa: v })} />
        <Num label="Limite de flecha total L/" value={opts.deflection_limit_total} onChange={v => set({ deflection_limit_total: v })} />
        <Num label="Limite de flecha quase perm. L/" value={opts.deflection_limit_qp} onChange={v => set({ deflection_limit_qp: v })} />
      </div>
    </div>

    <div className="space-y-2">
      <h3 className="text-sm font-medium">Solução pretendida</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <label className="block text-xs">Material<select className={sel + " mt-1"} value={opts.material} onChange={e => set({ material: e.target.value })} data-testid="lintel-material"><option value="both">Aço + betão (comparar)</option><option value="steel">Só aço</option><option value="rc">Só betão armado</option></select></label>
        <label className="block text-xs">Classe do aço<select className={sel + " mt-1"} value={opts.steel_grade} onChange={e => set({ steel_grade: e.target.value })}><option>S235</option><option>S275</option><option>S355</option></select></label>
        <label className="block text-xs">N.º máx. de perfis<select className={sel + " mt-1"} value={opts.max_profiles} onChange={e => set({ max_profiles: Number(e.target.value) })}><option value={1}>1 perfil</option><option value={2}>2 perfis</option></select></label>
        <div className="text-xs"><span className="block mb-1">Famílias de aço</span><div className="flex gap-2">{["IPE", "HEA", "HEB"].map(f => <label key={f} className="flex items-center gap-1"><input type="checkbox" checked={opts.steel_families.includes(f)} onChange={e => toggleFamily(f, e.target.checked)} />{f}</label>)}</div></div>
        <Num label="Betão fck (MPa)" value={opts.fck} onChange={v => set({ fck: v })} />
        <Num label="Largura BA (m, omissão=parede)" value={opts.rc_width_m} onChange={v => set({ rc_width_m: v })} />
        <Num label="Altura BA imposta (m, opcional)" value={opts.rc_height_m} onChange={v => set({ rc_height_m: v })} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 border-t pt-3">
        <label className="flex items-start gap-2 text-xs md:col-span-1"><input type="checkbox" className="mt-0.5" checked={restrained} onChange={e => set({ lateral_restraint_masonry: e.target.checked })} data-testid="lintel-lateral-restraint" /><span>Travamento lateral pela alvenaria (χLT = 1).<br /><span className="text-muted-foreground">Desmarque se a padieira não estiver travada lateralmente: a <b>encurvadura lateral NP EN 1993-1-1 §6.3.2</b> é então verificada (Mcr automático) e os perfis que não passam são afastados.</span></span></label>
        {!restrained && <><Num label="C1 (forma do momento)" value={opts.ltb_c1} onChange={v => set({ ltb_c1: v })} testid="lintel-c1" /><Num label="γM1 (encurvadura lateral)" value={opts.gamma_m1} onChange={v => set({ gamma_m1: v })} /></>}
      </div>
    </div>

    <div className="space-y-2">
      <h3 className="text-sm font-medium">Custos dos materiais (editáveis)</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Num label="Aço (€/kg)" value={opts.steel_eur_per_kg} onChange={v => set({ steel_eur_per_kg: v })} />
        <Num label="Betão (€/m³)" value={opts.concrete_eur_per_m3} onChange={v => set({ concrete_eur_per_m3: v })} />
        <Num label="Armatures (€/kg)" value={opts.rebar_eur_per_kg} onChange={v => set({ rebar_eur_per_kg: v })} />
      </div>
    </div>

    <div className="flex flex-wrap gap-2">
      <Button onClick={compute} disabled={busy || running} data-testid="lintel-compute"><Calculator className="h-4 w-4 mr-2" />{running ? "Calcul…" : "Dimensionar a padieira"}</Button>
      <Button variant="outline" onClick={saveCurrent} disabled={busy || !res} data-testid="lintel-save"><Save className="h-4 w-4 mr-2" />{editingId ? "Atualizar a abertura" : "Guardar esta abertura"}</Button>
    </div>

    {res && <div className="space-y-3 border-t pt-3" data-testid="lintel-results">
      <p className="text-xs text-muted-foreground">Modelo « {res.load_model} » · M_Ed <b>{res.actions.m_ed_knm}</b> kN·m · V_Ed <b>{res.actions.v_ed_kn}</b> kN · {res.actions.combination}</p>
      <div className="grid md:grid-cols-2 gap-3">
        <div className="border rounded-lg p-3" data-testid="lintel-steel">
          <p className="text-sm font-medium">Aço NP EN 1993</p>
          {res.steel ? (res.steel.status === "ok"
            ? <div className="text-xs mt-1"><p className="text-base font-semibold">{res.steel.label} <span className="text-muted-foreground">({res.steel.grade})</span></p><p>M_Rd {res.steel.mrd_knm} kN·m · V_Rd {res.steel.vrd_kn} kN</p><p>Flecha {res.steel.defl_char_mm}/{res.steel.defl_char_limit_mm} mm (totale) · {res.steel.defl_qp_mm}/{res.steel.defl_qp_limit_mm} mm (q-p)</p>{res.steel.ltb ? <p className="text-emerald-800" data-testid="lintel-ltb">Encurvadura lateral: Mb,Rd {res.steel.ltb.mb_rd_knm} kN·m · χLT {res.steel.ltb.chi_lt} · Mcr {res.steel.ltb.mcr_knm} kN·m (courbe {res.steel.ltb.curve})</p> : <p className="text-muted-foreground">Encurvadura lateral não verificada (travamento lateral suposto, χLT=1)</p>}<p>Masse {res.steel.mass_kg} kg · <b>{res.steel.cost_eur} €</b></p>{res.steel.bearing_plate && <p className="text-muted-foreground">Platine {res.steel.bearing_plate.length_mm}×{res.steel.bearing_plate.width_mm}×{res.steel.bearing_plate.thickness_mm} mm ({res.steel.bearing_plate.sigma_kpa}≤{res.steel.bearing_plate.allow_kpa} kPa)</p>}</div>
            : <p className="text-xs text-amber-700 mt-1">{res.steel.message}</p>) : <p className="text-xs text-muted-foreground mt-1">Não pedido</p>}
        </div>
        <div className="border rounded-lg p-3" data-testid="lintel-rc">
          <p className="text-sm font-medium">Betão armado NP EN 1992</p>
          {res.rc ? (res.rc.status === "ok"
            ? <div className="text-xs mt-1"><p className="text-base font-semibold">{res.rc.label}</p><p>As {res.rc.as_required_cm2} cm² (mini {res.rc.as_min_cm2}) · Asw/s {res.rc.asw_required_cm2_m} cm²/m</p><p>Vão/altura útil L/d {res.rc.span_depth_ratio} ≤ {res.rc.span_depth_limit}</p><p>{res.rc.concrete_m3} m³ + {res.rc.rebar_kg} kg de aço · <b>{res.rc.cost_eur} €</b></p>{res.rc.detailing?.anchorage && <p className="text-muted-foreground">Ancrage {res.rc.detailing.anchorage.straight_mm} mm · crochet {res.rc.detailing.anchorage.hook_mm} mm (Ø{res.rc.bar_mm})</p>}</div>
            : <p className="text-xs text-amber-700 mt-1">{res.rc.message}</p>) : <p className="text-xs text-muted-foreground mt-1">Não pedido</p>}
        </div>
      </div>
      <Reco r={res} />
      <div className={`text-xs border rounded-lg p-3 ${res.bearing.status === "ok" ? "border-emerald-200" : "border-red-300"}`} data-testid="lintel-bearing">
        <b>Apoio na alvenaria:</b> reação ELU {res.bearing.reaction_kn} kN · pression {res.bearing.sigma_kpa} kPa ≤ {res.bearing.allow_kpa} kPa → <span className={res.bearing.status === "ok" ? "text-emerald-700 font-semibold" : "text-red-700 font-semibold"}>{res.bearing.status === "ok" ? "OK" : "A REVER"}</span> · about requis ≥ {res.bearing.required_length_m} m
      </div>
      {res.notes?.map((x, i) => <p key={i} className="text-[11px] text-amber-700">• {x}</p>)}
      {res.reactions && <div className="border rounded-lg p-3 bg-muted/30 space-y-2" data-testid="lintel-reinject">
        <p className="text-sm font-medium">Fechar a descida de cargas</p>
        <p className="text-xs text-muted-foreground">Reação por apoio: <b>G {res.reactions.g_kn} kN</b> + <b>Q {res.reactions.q_kn} kN</b> (características). Detete automaticamente os nembos que enquadram a abertura (ou escolha-os) para reinjetar estas reações como cargas pontuais.</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 items-end">
          <label className="block text-xs">Appui gauche<select className={sel + " mt-1"} value={left} onChange={e => setLeft(e.target.value)} data-testid="lintel-left-support"><option value="">Escolher…</option>{piers.map(p => <option key={p.id} value={p.id}>{`${p.id} · ${p.kind === "wall" ? "mur" : "poteau"}`}</option>)}</select></label>
          <label className="block text-xs">Appui droit<select className={sel + " mt-1"} value={right} onChange={e => setRight(e.target.value)} data-testid="lintel-right-support"><option value="">Escolher…</option>{piers.map(p => <option key={p.id} value={p.id}>{`${p.id} · ${p.kind === "wall" ? "mur" : "poteau"}`}</option>)}</select></label>
          <Button variant="outline" size="sm" onClick={autoDetect} disabled={busy} data-testid="lintel-autodetect"><Wand2 className="h-4 w-4 mr-1" />Detetar os apoios</Button>
          <Button variant="outline" size="sm" onClick={reinject} disabled={busy || !left || !right} data-testid="lintel-reinject-btn">Reinjetar na descida</Button>
        </div>
        <p className="text-[11px] text-muted-foreground">As cargas pontuais são marcadas por abertura; relançar o botão atualiza-as sem as acumular. Verifique e depois volte a confirmar o modelo gravítico.</p>
      </div>}
      <p className="text-[11px] text-muted-foreground">{res.note}</p>
    </div>}
  </Card>;
}
