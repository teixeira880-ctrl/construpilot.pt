import { useCallback, useEffect, useState } from "react";
import { Calculator, Check, ChevronDown, ChevronUp, Pencil, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const STATE = { confirmed: "confirmé", probable: "probable", indeterminate: "indéterminé", not_verifiable: "non vérifiable" };
const TOOL = { check_dimension_chain: "Chaîne de cotes", compare_dimension_values: "Comparaison de cotes", resolve_ambiguous_reading: "Lecture ambiguë",
  calculate_quantities: "Quantités", dedupe_elements: "Dédoublonnage", classify_strokes: "Classification des traits", read_rebar_schedule: "Nomenclature d'aciers" };
const useCrop = (r) => {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    if (!(r.plan_id && r.box?.length === 4)) return undefined;
    let url;
    api.get(`/assistant/plans/${r.plan_id}/crop`, { params: { page: r.page ?? 0, box: r.box.join(",") }, responseType: "blob" })
      .then(({ data }) => { url = URL.createObjectURL(data); setSrc(url); }).catch(() => setSrc(null));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [r.plan_id, r.page, r.box]);
  return src;
};

const readings = (args) => {
  const out = [];
  const walk = (node) => {
    if (Array.isArray(node)) node.forEach(walk);
    else if (node && typeof node === "object") {
      if ("candidates_m" in node && "label" in node) out.push(node);
      else Object.values(node).forEach(walk);
    }
  };
  walk(args);
  return out;
};

const Reading = ({ r, onCorrect }) => {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(r.value_m ?? "");
  const crop = useCrop(r);
  return <li className="flex items-start gap-2 py-1 border-b border-border/40" data-testid={`calc-reading-${r.label}`}>
    {crop && <img src={crop} alt={r.label} className="h-12 w-20 object-contain rounded-sm border bg-white" data-testid="calc-reading-crop" />}
    <div className="flex-1 text-xs">
      <div><b>{r.label}</b> : {r.value_m != null ? `${r.value_m} m` : `${r.candidates_m?.join(" / ")} m (ambiguë)`} <span className="text-muted-foreground">· {r.origin === "user_statement" ? "déclaré par vous" : r.origin === "native_text" ? "texte natif" : r.origin === "assumption" ? "hypothèse" : "lecture du plan"}</span></div>
      {editing ? <div className="flex items-center gap-1 mt-1">
        <input type="number" step="0.001" value={value} onChange={(e) => setValue(e.target.value)} className="h-7 w-24 rounded-sm border px-1 text-xs" data-testid="calc-correct-input" />
        <Button size="sm" className="h-7 text-xs gap-1" onClick={() => { onCorrect(r.label, Number(value)); setEditing(false); }} data-testid="calc-correct-save"><Check size={12} /> Recalculer</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditing(false)}><X size={12} /></Button>
      </div> : <button type="button" className="text-[11px] underline text-muted-foreground flex items-center gap-1 mt-0.5" onClick={() => setEditing(true)} data-testid="calc-correct-btn"><Pencil size={10} /> Corriger la lecture</button>}
    </div>
  </li>;
};

export const CalculationsPanel = ({ conversationId, refreshKey, onCorrected }) => {
  const [calcs, setCalcs] = useState([]);
  const [open, setOpen] = useState(true);
  const load = useCallback(async () => {
    if (!conversationId) { setCalcs([]); return; }
    try { const { data } = await api.get(`/assistant/conversations/${conversationId}/calculations`); setCalcs(data.calculations || []); } catch { setCalcs([]); }
  }, [conversationId]);
  useEffect(() => { load(); }, [load, refreshKey]);
  const live = calcs.filter((c) => !c.superseded_by && c.tool !== "classify_strokes" && c.tool !== "dedupe_elements");
  if (!live.length) return null;
  const correct = async (calcRef, label, value) => {
    try {
      await api.post(`/assistant/calculations/${calcRef}/correct`, { label, value_m: value });
      toast.success("Lecture corrigée — calcul recalculé (historique conservé)");
      await load(); onCorrected?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Correction impossible"); }
  };
  return <section className="mx-3 mb-2 rounded-md border border-border bg-muted/30 text-xs" data-testid="calculations-panel">
    <button type="button" className="w-full flex items-center justify-between px-3 py-2 font-semibold" onClick={() => setOpen((o) => !o)} data-testid="calculations-toggle">
      <span className="flex items-center gap-1"><Calculator size={14} /> Calculs sur le plan ({live.length})</span>{open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
    </button>
    {open && <div className="px-3 pb-2 grid gap-2 max-h-72 overflow-y-auto">
      {live.map((c) => {
        const calc = c.result?.calculation || {}; const cmp = c.result?.comparison;
        return <div key={c.calc_ref} className="rounded-sm border bg-background p-2" data-testid={`calc-${c.calc_ref}`}>
          <div className="flex justify-between gap-2"><b>{TOOL[c.tool] || c.tool}</b><span className="text-muted-foreground">{c.supersedes ? "corrigé" : ""} {STATE[calc.state] || c.result?.state || ""}</span></div>
          {calc.formula && <div className="font-mono text-[11px]" data-testid="calc-formula">{calc.formula}</div>}
          {cmp?.formula && <div className="font-mono text-[11px]">{cmp.formula} · {cmp.reason}</div>}
          {c.result?.lines?.map((l, i) => <div key={i} className="font-mono text-[11px]">{l.element} : {l.formula} · {STATE[l.state]}</div>)}
          {c.correction && <div className="text-muted-foreground">Correction : « {c.correction.label} » = {c.correction.value_m} m</div>}
          <ul className="mt-1">{readings(c.args).map((r, i) => <Reading key={`${r.label}-${i}`} r={r} onCorrect={(label, value) => correct(c.calc_ref, label, value)} />)}</ul>
        </div>;
      })}
    </div>}
  </section>;
};
