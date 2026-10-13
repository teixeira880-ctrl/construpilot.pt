import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Rocket, FileUp, Wand2, FileDown, Layers, Info, Building2, Mountain, CheckCircle2, FileText } from "lucide-react";

const sel = "border rounded-md p-2 bg-background text-sm w-full";
const KIND = { plan: "Plan coté", pc: "Permis (PC)", g2: "Géotechnique G2" };
const DEST = [["habitation", "Habitation"], ["bureau", "Bureau"], ["commerce", "Commerce"], ["parking", "Parking"], ["industriel", "Industriel"], ["erp", "ERP"]];
const FOND = [["isolee", "Semelles isolées"], ["filante", "Semelles filantes"], ["radier", "Radier"]];
const num = v => (v === "" || v === null || v === undefined ? null : Number(v));
const parseBays = s => String(s || "").split(/[,;x×\s]+/).map(x => parseFloat(x.replace(",", "."))).filter(x => Number.isFinite(x) && x > 0);
const fmtBays = a => (Array.isArray(a) ? a.join(", ") : "");

function Num({ label, value, onChange, testid, step = "any" }) {
  return <label className="block text-xs">{label}<Input aria-label={label} data-testid={testid} type="number" step={step} className="mt-1" value={value ?? ""} onChange={e => onChange(num(e.target.value))} /></label>;
}

export default function StructureAutopilotPanel({ dossier, onChange }) {
  const navigate = useNavigate();
  const base = `/structuro/bet/studies/${dossier.dossier_id}`;
  const stored = dossier.autopilot || {};
  const [inputs, setInputs] = useState(stored.inputs || null);
  const [baysX, setBaysX] = useState(fmtBays(stored.inputs?.grid?.bays_x_m));
  const [baysY, setBaysY] = useState(fmtBays(stored.inputs?.grid?.bays_y_m));
  const [busy, setBusy] = useState(false);
  const [quoteMargin, setQuoteMargin] = useState(12);
  const [quoteVat, setQuoteVat] = useState(20);
  const [result, setResult] = useState(stored.calc_study_id ? { calc_study_id: stored.calc_study_id, summary: stored.summary } : null);
  const docs = (dossier.documents || []).filter(d => !d.is_deleted && ["plan", "pc", "g2"].includes(d.kind));

  const b = inputs?.building || {};
  const ld = inputs?.loads || {};
  const sc = inputs?.sections || {};
  const so = inputs?.soil || {};
  const setB = patch => setInputs(p => ({ ...p, building: { ...p.building, ...patch } }));
  const setLd = patch => setInputs(p => ({ ...p, loads: { ...p.loads, ...patch } }));
  const setSc = patch => setInputs(p => ({ ...p, sections: { ...p.sections, ...patch } }));
  const setSo = patch => setInputs(p => ({ ...p, soil: { ...p.soil, ...patch } }));
  const setSy = patch => setInputs(p => ({ ...p, system: { ...p.system, ...patch } }));
  const setPr = patch => setInputs(p => ({ ...p, prices: { ...p.prices, ...patch } }));
  const sy = inputs?.system || {};
  const pr = inputs?.prices || {};
  const isWalls = sy.structure === "voiles";

  const uploadFor = async (kind, file) => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    try {
      const { data } = await api.post(`${base}/documents`, fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 });
      onChange(data);
      toast.success(`${KIND[kind]} importé`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Import impossible"); }
    finally { setBusy(false); }
  };

  const collectInputs = () => {
    const i = inputs ? JSON.parse(JSON.stringify(inputs)) : {};
    i.grid = { bays_x_m: parseBays(baysX), bays_y_m: parseBays(baysY) };
    return i;
  };

  const analyze = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`${base}/autopilot/extract`, {}, { timeout: 180000 });
      onChange(data);
      const inp = data.autopilot?.inputs;
      setInputs(inp); setBaysX(fmtBays(inp?.grid?.bays_x_m)); setBaysY(fmtBays(inp?.grid?.bays_y_m));
      toast.success("Documents analysés — vérifiez et corrigez avant de générer");
    } catch (e) { toast.error(e?.response?.data?.detail || "Analyse impossible — importez un plan/PC/G2"); }
    finally { setBusy(false); }
  };

  const useDefaults = () => {
    const d = { building: { destination: "habitation", levels: 1, storey_height_m: 2.8, ground_height_m: 3.0 },
      system: { structure: "portique", wall_thickness_m: 0.2, two_way_slab: false },
      grid: { bays_x_m: [4, 4], bays_y_m: [4] },
      loads: { floor_var_kn_m2: 1.5, floor_perm_extra_kn_m2: 1.5, roof_var_kn_m2: 1.0, roof_perm_extra_kn_m2: 1.5 },
      sections: { col_side_m: 0.3, beam_width_m: 0.2, beam_height_m: 0.4, slab_thickness_m: 0.2 },
      prices: { concrete_eur_m3: 150, steel_eur_kg: 2.0, formwork_eur_m2: 45 },
      soil: { q_els_kpa: null, q_elu_kpa: null, q_confirmed: false, foundation_type: "isolee", anchorage_depth_m: 0.8, water_table: false, soil_class: "", mode: "drained", phi_deg: 0, c_kpa: 0, cu_kpa: 0, gamma_soil_kn_m3: 18 }, incertitudes: [] };
    setInputs(d); setBaysX(fmtBays(d.grid.bays_x_m)); setBaysY(fmtBays(d.grid.bays_y_m));
    toast.info("Trame par défaut chargée — ajustez puis générez");
  };

  const saveInputs = async () => {
    setBusy(true);
    try { const { data } = await api.put(`${base}/autopilot/inputs`, collectInputs()); onChange(data); toast.success("Données enregistrées"); }
    catch (e) { toast.error("Enregistrement impossible"); }
    finally { setBusy(false); }
  };

  const generate = async () => {
    const i = collectInputs();
    if (!i.grid.bays_x_m.length || !i.grid.bays_y_m.length) { toast.error("Renseignez au moins une portée en X et une en Y"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`${base}/autopilot/generate`, { inputs: i }, { timeout: 120000 });
      setResult({ calc_study_id: data.calc_study_id, summary: data.summary });
      if (data.dossier) onChange(data.dossier);
      toast.success("Modèle + descente de charges générés");
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : (d?.message || "Génération impossible"));
    } finally { setBusy(false); }
  };

  const downloadDossier = async () => {
    if (!result?.calc_study_id) return;
    setBusy(true);
    try {
      const body = { include: ["ec2", "ec7", "sls"], ec7: { mode: so.mode || "drained", d_m: so.anchorage_depth_m || 0, phi_deg: so.phi_deg || 0, c_kpa: so.c_kpa || 0, cu_kpa: so.cu_kpa || 0, gamma_soil: so.gamma_soil_kn_m3 || 0 } };
      const { data } = await api.post(`/structuro/calc/studies/${result.calc_study_id}/export/dossier`, body, { responseType: "blob", timeout: 120000 });
      const url = URL.createObjectURL(data), a = document.createElement("a");
      a.href = url; a.download = `dossier-bet-auto-${result.calc_study_id}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Dossier BET téléchargé");
    } catch (e) { toast.error("Export du dossier impossible"); }
    finally { setBusy(false); }
  };

  const downloadCoffrage = async () => {
    setBusy(true);
    try {
      const { data } = await api.get(`${base}/autopilot/coffrage.pdf`, { responseType: "blob", timeout: 120000 });
      const url = URL.createObjectURL(data), a = document.createElement("a");
      a.href = url; a.download = `plans-coffrage-${dossier.dossier_id}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Plans de coffrage téléchargés");
    } catch (e) { toast.error("Export des plans de coffrage impossible — générez d'abord le modèle"); }
    finally { setBusy(false); }
  };

  const generateQuote = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/documents/from-autopilot/${dossier.dossier_id}?margin_pct=${Number(quoteMargin) || 0}&vat_rate=${Number(quoteVat) || 0}`, {}, { timeout: 60000 });
      toast.success("Devis gros œuvre créé — ouverture de l'éditeur");
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Création du devis impossible — générez d'abord le modèle"); }
    finally { setBusy(false); }
  };

  const UploadBtn = ({ kind, icon }) => {
    const id = `autopilot-upload-${kind}`;
    return <label className="flex-1">
      <input id={id} data-testid={id} type="file" className="hidden" accept=".pdf,.png,.jpg,.jpeg,.webp"
        onChange={e => { uploadFor(kind, e.target.files?.[0]); e.target.value = ""; }} />
      <Button type="button" variant="outline" className="w-full gap-2" disabled={busy}
        onClick={() => document.getElementById(id)?.click()}>{icon}{KIND[kind]}</Button>
    </label>;
  };

  return <Card className="p-5 space-y-5 border-primary/30" data-testid="autopilot-panel">
    <div className="flex items-center gap-2">
      <Rocket className="h-5 w-5 text-primary" />
      <h2 className="font-semibold">Auto-pilote BET — descente de charges &amp; fondations automatiques</h2>
      <Badge className="rounded-sm border-0 bg-primary/15 text-primary">Phase 1</Badge>
    </div>
    <p className="text-sm text-muted-foreground">Importez un <b>plan coté</b>, le <b>PC</b> et la <b>G2</b> : l'IA pré-remplit la trame, les niveaux, les charges et le sol. <b>Vous validez</b>, puis le moteur calcule la descente de charges et pré-dimensionne les semelles (100 % déterministe, EN 1990/1991/1997). Plans d'exécution &amp; ferraillage dans le dossier BET. <b>Non exécutoire — à viser par l'ingénieur.</b></p>

    <div className="space-y-2">
      <h3 className="text-sm font-medium flex items-center gap-2"><FileUp className="h-4 w-4" />1. Importer les pièces</h3>
      <div className="flex flex-col sm:flex-row gap-2">
        <UploadBtn kind="plan" icon={<Layers className="h-4 w-4" />} />
        <UploadBtn kind="pc" icon={<Building2 className="h-4 w-4" />} />
        <UploadBtn kind="g2" icon={<Mountain className="h-4 w-4" />} />
      </div>
      {docs.length > 0 && <div className="flex flex-wrap gap-2 pt-1" data-testid="autopilot-docs">
        {docs.map(d => <Badge key={d.id} variant="secondary" className="rounded-sm" data-testid={`autopilot-doc-${d.id}`}>{KIND[d.kind]} · {d.original_filename}</Badge>)}
      </div>}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button onClick={analyze} disabled={busy || docs.length === 0} className="gap-2" data-testid="autopilot-analyze"><Wand2 className="h-4 w-4" />Analyser les documents (IA)</Button>
        <Button variant="ghost" onClick={useDefaults} disabled={busy} data-testid="autopilot-defaults">Partir d'une trame par défaut</Button>
      </div>
    </div>

    {inputs && <>
      <div className="space-y-3 border-t pt-4" data-testid="autopilot-form">
        <h3 className="text-sm font-medium">2. Vérifier &amp; corriger les données extraites</h3>
        {(inputs.incertitudes?.length > 0) && <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-700 flex gap-2" data-testid="autopilot-uncertainties"><Info className="h-4 w-4 shrink-0" /><div><b>À vérifier (lecture IA) :</b> {inputs.incertitudes.join(" · ")}</div></div>}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <label className="block text-xs">Système porteur<select className={sel + " mt-1"} value={sy.structure || "portique"} onChange={e => setSy({ structure: e.target.value })} data-testid="autopilot-system"><option value="portique">Portique (poteaux-poutres)</option><option value="voiles">Voiles / murs porteurs</option></select></label>
          {isWalls ? <Num label="Épaisseur mur (m)" value={sy.wall_thickness_m} onChange={v => setSy({ wall_thickness_m: v })} testid="autopilot-wall-thickness" />
            : <label className="flex items-center gap-2 text-xs pt-5"><input type="checkbox" checked={!!sy.two_way_slab} onChange={e => setSy({ two_way_slab: e.target.checked })} data-testid="autopilot-two-way" />Plancher 2 sens (dalle portée 4 côtés)</label>}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <label className="block text-xs">Destination<select className={sel + " mt-1"} value={b.destination || "habitation"} onChange={e => setB({ destination: e.target.value })} data-testid="autopilot-destination">{DEST.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <Num label="Nb de niveaux" value={b.levels} onChange={v => setB({ levels: v })} testid="autopilot-levels" step="1" />
          <Num label="Hauteur étage (m)" value={b.storey_height_m} onChange={v => setB({ storey_height_m: v })} />
          <Num label="Hauteur RDC (m)" value={b.ground_height_m} onChange={v => setB({ ground_height_m: v })} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="block text-xs">Portées X (m, séparées par virgule)<Input aria-label="Portées X" data-testid="autopilot-bays-x" className="mt-1" value={baysX} onChange={e => setBaysX(e.target.value)} placeholder="4, 4" /></label>
          <label className="block text-xs">Portées Y (m, séparées par virgule)<Input aria-label="Portées Y" data-testid="autopilot-bays-y" className="mt-1" value={baysY} onChange={e => setBaysY(e.target.value)} placeholder="5" /></label>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Num label="Exploitation plancher Q (kN/m²)" value={ld.floor_var_kn_m2} onChange={v => setLd({ floor_var_kn_m2: v })} testid="autopilot-floor-q" />
          <Num label="Perm. compl. plancher (kN/m²)" value={ld.floor_perm_extra_kn_m2} onChange={v => setLd({ floor_perm_extra_kn_m2: v })} />
          <Num label="Exploitation toiture (kN/m²)" value={ld.roof_var_kn_m2} onChange={v => setLd({ roof_var_kn_m2: v })} />
          <Num label="Perm. compl. toiture (kN/m²)" value={ld.roof_perm_extra_kn_m2} onChange={v => setLd({ roof_perm_extra_kn_m2: v })} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Num label="Poteau (côté, m)" value={sc.col_side_m} onChange={v => setSc({ col_side_m: v })} />
          <Num label="Poutre largeur (m)" value={sc.beam_width_m} onChange={v => setSc({ beam_width_m: v })} />
          <Num label="Poutre hauteur (m)" value={sc.beam_height_m} onChange={v => setSc({ beam_height_m: v })} />
          <Num label="Dalle épaisseur (m)" value={sc.slab_thickness_m} onChange={v => setSc({ slab_thickness_m: v })} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Num label="Prix béton (€/m³)" value={pr.concrete_eur_m3} onChange={v => setPr({ concrete_eur_m3: v })} testid="autopilot-price-concrete" />
          <Num label="Prix acier (€/kg)" value={pr.steel_eur_kg} onChange={v => setPr({ steel_eur_kg: v })} testid="autopilot-price-steel" />
        </div>

        <div className="rounded-md bg-muted/30 p-3 space-y-2">
          <h4 className="text-xs font-medium flex items-center gap-2"><Mountain className="h-3.5 w-3.5" />Sol (G2 PRO)</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Num label="Contrainte adm. ELS (kPa)" value={so.q_els_kpa} onChange={v => setSo({ q_els_kpa: v })} testid="autopilot-q-els" />
            <Num label="Contrainte adm. ELU (kPa)" value={so.q_elu_kpa} onChange={v => setSo({ q_elu_kpa: v })} testid="autopilot-q-elu" />
            <label className="block text-xs">Type de fondation<select className={sel + " mt-1"} value={so.foundation_type || "isolee"} onChange={e => setSo({ foundation_type: e.target.value })} data-testid="autopilot-foundation-type">{FOND.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
            <Num label="Ancrage D (m)" value={so.anchorage_depth_m} onChange={v => setSo({ anchorage_depth_m: v })} />
            <Num label="φ' (°) — si connu" value={so.phi_deg} onChange={v => setSo({ phi_deg: v })} />
            <Num label="c' (kPa)" value={so.c_kpa} onChange={v => setSo({ c_kpa: v })} />
            <Num label="cu (kPa)" value={so.cu_kpa} onChange={v => setSo({ cu_kpa: v })} />
            <label className="flex items-center gap-2 text-xs pt-5"><input type="checkbox" checked={!!so.water_table} onChange={e => setSo({ water_table: e.target.checked })} data-testid="autopilot-water" />Nappe rencontrée</label>
            <label className="flex items-center gap-2 text-xs pt-5 md:col-span-2"><input type="checkbox" checked={!!so.q_confirmed} onChange={e => setSo({ q_confirmed: e.target.checked })} data-testid="autopilot-q-confirmed" />Valeurs q_ELS / q_ELU confirmées par le rapport G2</label>
          </div>
          {!(so.q_confirmed && so.q_els_kpa) && <p className="text-[11px] text-amber-700" data-testid="autopilot-soil-warning">Sans contrainte de sol confirmée (G2), les fondations ne sont pas dimensionnées : aucune valeur par défaut n'est utilisée.</p>}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={generate} disabled={busy} className="gap-2" data-testid="autopilot-generate"><Rocket className="h-4 w-4" />Accepter &amp; générer (descente + fondations)</Button>
          <Button variant="outline" onClick={saveInputs} disabled={busy} data-testid="autopilot-save-inputs">Enregistrer les données</Button>
        </div>
      </div>
    </>}

    {result?.summary && <div className="space-y-3 border-t pt-4" data-testid="autopilot-summary">
      <h3 className="text-sm font-medium flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-600" />3. Résultat — descente de charges, fondations &amp; ferraillage</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <div className="border rounded-md p-2"><span className="text-muted-foreground">Éléments</span><p className="text-base font-semibold">{result.summary.total_elements}</p></div>
        <div className="border rounded-md p-2"><span className="text-muted-foreground">Semelles ({result.summary.footing_type === "filante" ? "filantes" : "isolées"})</span><p className="text-base font-semibold">{result.summary.n_footings}</p></div>
        <div className="border rounded-md p-2"><span className="text-muted-foreground">Réaction au sol ELU</span><p className="text-base font-semibold">{result.summary.ground_reaction_elu_kn} kN</p></div>
        <div className="border rounded-md p-2"><span className="text-muted-foreground">Semelle max.</span><p className="text-base font-semibold">{result.summary.max_footing_dim_m != null ? `${result.summary.max_footing_dim_m} m` : "Sol à confirmer"}</p></div>
      </div>
      {(result.summary.warnings || []).length > 0 && <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 space-y-1" data-testid="autopilot-warnings">
        {result.summary.warnings.map((w, i) => <p key={i}>⚠ {w}</p>)}
      </div>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs border" data-testid="autopilot-footings-table">
          <thead className="bg-muted/50"><tr><th className="text-left p-2">Semelle</th><th className="text-right p-2">N ELS (kN)</th><th className="text-right p-2">N ELU (kN)</th><th className="text-right p-2">Dimension</th></tr></thead>
          <tbody>{(result.summary.footings || []).map(f => <tr key={f.id} className="border-t"><td className="p-2 font-medium">{f.id}</td><td className="text-right p-2">{f.n_els_kn}</td><td className="text-right p-2">{f.n_elu_kn}</td><td className="text-right p-2 font-semibold">{f.status === "sol_a_confirmer" ? <span className="text-amber-700">Sol G2 à confirmer</span> : f.type === "filante" ? `filante, larg. ${f.width_m} m` : `${f.side_m}×${f.side_m} m`}</td></tr>)}</tbody>
        </table>
      </div>

      {result.summary.superstructure && (() => { const ss = result.summary.superstructure; return <div className="space-y-3" data-testid="autopilot-superstructure">
        {ss.beams?.length > 0 && <div className="overflow-x-auto"><p className="text-xs font-medium mb-1">Poutres — ferraillage EC2 (gouvernant par niveau{ss.continuity ? " et par sens, files continues" : ""})</p>
          <table className="w-full text-xs border" data-testid="autopilot-beams-table"><thead className="bg-muted/50"><tr><th className="text-left p-2">Niveau</th><th className="text-left p-2">Poutre</th><th className="text-right p-2">b×h (m)</th><th className="text-right p-2">M travée (kN·m)</th><th className="text-right p-2">M appui (kN·m)</th><th className="text-right p-2">As inf. (cm²)</th><th className="text-right p-2">As sup. (cm²)</th><th className="text-right p-2">Asw/s (cm²/m)</th><th className="text-right p-2">Flèche LT / lim. (mm)</th></tr></thead>
            <tbody>{ss.beams.map(b => <tr key={b.id} className="border-t"><td className="p-2">{b.level}</td><td className="p-2 font-medium">{b.id}</td><td className="text-right p-2">{b.b_m}×{b.h_m}</td><td className="text-right p-2">{b.med_knm}</td><td className="text-right p-2">{b.m_support_knm != null ? `−${b.m_support_knm}` : "—"}</td><td className="text-right p-2 font-semibold">{b.as_req_cm2}</td><td className="text-right p-2 font-semibold">{b.as_top_req_cm2 ?? "—"}</td><td className="text-right p-2">{b.asw_s_req_cm2_m}</td><td className={`text-right p-2 ${b.deflection?.status === "a_revoir" ? "text-red-700 font-semibold" : ""}`}>{b.deflection ? `${b.deflection.w_long_term_mm} / ${b.deflection.limit_mm}` : "—"}</td></tr>)}</tbody></table>
          {ss.continuity && <p className="text-[11px] text-muted-foreground mt-1">{ss.continuity.method}</p>}</div>}
        {ss.columns?.length > 0 && <div className="overflow-x-auto"><p className="text-xs font-medium mb-1">Poteaux — aciers EC2 (compression centrée)</p>
          <table className="w-full text-xs border" data-testid="autopilot-columns-table"><thead className="bg-muted/50"><tr><th className="text-left p-2">Niveau</th><th className="text-left p-2">Poteau</th><th className="text-right p-2">Section (m)</th><th className="text-right p-2">N_Ed (kN)</th><th className="text-left p-2">Aciers long.</th><th className="text-right p-2">As (cm²)</th><th className="text-left p-2">Cadres</th><th className="text-center p-2">Statut</th></tr></thead>
            <tbody>{ss.columns.map(c => <tr key={c.id} className="border-t"><td className="p-2">{c.level}</td><td className="p-2 font-medium">{c.id}</td><td className="text-right p-2">{c.b_m}×{c.h_m}</td><td className="text-right p-2">{c.n_ed_kn}</td><td className="p-2 font-semibold">{c.long_bars}</td><td className="text-right p-2">{c.as_prov_cm2}</td><td className="p-2">{c.ties}</td><td className={`text-center p-2 ${c.status === "ok" ? "text-emerald-700" : "text-amber-700 font-semibold"}`}>{c.status === "ok" ? "OK" : "À revoir"}</td></tr>)}</tbody></table></div>}
        {ss.walls?.length > 0 && <div className="overflow-x-auto"><p className="text-xs font-medium mb-1">Voiles / murs porteurs — aciers EC2 (§9.6)</p>
          <table className="w-full text-xs border" data-testid="autopilot-walls-table"><thead className="bg-muted/50"><tr><th className="text-left p-2">Niveau</th><th className="text-left p-2">Voile</th><th className="text-right p-2">Ép.×L (m)</th><th className="text-right p-2">N_Ed (kN)</th><th className="text-right p-2">As vert. (cm²)</th><th className="text-right p-2">As horiz. (cm²)</th></tr></thead>
            <tbody>{ss.walls.map(w => <tr key={w.id} className="border-t"><td className="p-2">{w.level}</td><td className="p-2 font-medium">{w.id}</td><td className="text-right p-2">{w.thickness_m}×{w.length_m}</td><td className="text-right p-2">{w.n_ed_kn}</td><td className="text-right p-2 font-semibold">{w.as_vert_cm2}</td><td className="text-right p-2">{w.as_horiz_cm2}</td></tr>)}</tbody></table></div>}
      </div>; })()}

      {result.summary.metre && (() => { const m = result.summary.metre; return <div className="space-y-2" data-testid="autopilot-metre">
        <h4 className="text-sm font-medium">Métré &amp; estimation matière (indicatif)</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="border rounded-md p-2"><span className="text-muted-foreground">Béton total</span><p className="text-base font-semibold" data-testid="autopilot-metre-concrete">{m.concrete.total_m3} m³</p></div>
          <div className="border rounded-md p-2"><span className="text-muted-foreground">Acier total</span><p className="text-base font-semibold" data-testid="autopilot-metre-steel">{m.steel.total_kg} kg</p><span className="text-[10px] text-muted-foreground">≈ {m.steel.ratio_kg_m3} kg/m³</span></div>
          <div className="border rounded-md p-2"><span className="text-muted-foreground">Coût béton</span><p className="text-base font-semibold">{m.cost.concrete_eur} €</p><span className="text-[10px] text-muted-foreground">{m.cost.concrete_eur_m3} €/m³</span></div>
          <div className="border rounded-md p-2 bg-primary/5"><span className="text-muted-foreground">Coût matière total</span><p className="text-base font-semibold text-primary" data-testid="autopilot-metre-cost">{m.cost.total_eur} €</p><span className="text-[10px] text-muted-foreground">acier {m.cost.steel_eur} €</span></div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border" data-testid="autopilot-rebar-schedule"><thead className="bg-muted/50"><tr><th className="text-left p-2">Repère</th><th className="text-left p-2">Ouvrage</th><th className="text-left p-2">Niveau</th><th className="text-left p-2">Aciers</th><th className="text-right p-2">Nb</th><th className="text-right p-2">Poids (kg)</th></tr></thead>
            <tbody>{(m.steel.schedule || []).map((r, i) => <tr key={i} className="border-t"><td className="p-2 font-medium">{r.mark}</td><td className="p-2">{r.type}</td><td className="p-2">{r.level}</td><td className="p-2">{r.bars}</td><td className="text-right p-2">{r.count}</td><td className="text-right p-2 font-semibold">{r.weight_kg}</td></tr>)}</tbody></table>
        </div>
        <p className="text-[11px] text-muted-foreground">{m.note}</p>
        <div className="rounded-md border border-primary/30 bg-primary/5 p-3 space-y-2" data-testid="autopilot-quote-block">
          <p className="text-xs font-medium flex items-center gap-2"><FileText className="h-3.5 w-3.5" />Générer un devis « Gros œuvre » depuis ce métré</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 items-end">
            <Num label="Marge (%)" value={quoteMargin} onChange={v => setQuoteMargin(v)} testid="autopilot-quote-margin" />
            <label className="block text-xs">TVA<select className={sel + " mt-1"} value={quoteVat} onChange={e => setQuoteVat(Number(e.target.value))} data-testid="autopilot-quote-vat"><option value={20}>20 % (neuf)</option><option value={10}>10 % (rénovation)</option><option value={0}>0 % (sous-traitance)</option></select></label>
            <Button onClick={generateQuote} disabled={busy} className="gap-2 md:col-span-2" data-testid="autopilot-generate-quote"><FileText className="h-4 w-4" />Créer le devis &amp; ouvrir l'éditeur</Button>
          </div>
          <p className="text-[11px] text-muted-foreground">Une ligne de béton par ouvrage (m³) + une ligne d'acier par repère (kg) au prix matière × (1 + marge). Lignes 100 % modifiables dans l'éditeur.</p>
        </div>
      </div>; })()}

      <div className="flex flex-wrap gap-2">
        <Button onClick={downloadCoffrage} disabled={busy} className="gap-2" data-testid="autopilot-download-coffrage"><Layers className="h-4 w-4" />Télécharger les plans de coffrage (cotés + nomenclature aciers)</Button>
        <Button onClick={downloadDossier} disabled={busy} variant="outline" className="gap-2" data-testid="autopilot-download-dossier"><FileDown className="h-4 w-4" />Dossier BET (descente + ferraillage EC2 + fondations EC7)</Button>
        <Button asChild variant="outline" data-testid="autopilot-open-calc"><a href="/structuro/calcul">Ouvrir dans le module de calcul</a></Button>
      </div>
      <p className="text-[11px] text-muted-foreground">Pré-dimensionnement automatique indicatif. Vérifiez les hypothèses, complétez vent/séisme/continuité et faites viser par l'ingénieur / le bureau de contrôle.</p>
    </div>}
  </Card>;
}
