import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Ruler, FileDown, Loader2, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

const LABEL = { ok: "OK", warn: "À vérifier", ko: "Incohérence" };
const CLS = {
  ok: "bg-emerald-100 text-emerald-800 border-emerald-300",
  warn: "bg-orange-100 text-orange-800 border-orange-300",
  ko: "bg-red-100 text-red-800 border-red-300",
};

async function authedBlob(path) {
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api${path}`, {
    headers: { Authorization: `Bearer ${localStorage.getItem("construpilot_token")}` },
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Erreur serveur");
  }
  return res.blob();
}

function Summary({ s }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="cotes-summary">
      <Badge className={`rounded-sm border ${CLS[s.verdict]}`} data-testid="cotes-verdict">
        {LABEL[s.verdict]}
      </Badge>
      <span className="text-[11px] text-muted-foreground">
        {s.total} cotes · {s.ok} OK · {s.warn} à vérifier · <b className="text-red-700">{s.ko} incohérence(s)</b>
        {s.chains_total > 0 && ` · ${s.chains_total} chaîne(s) (${s.chains_ko} KO)`} · écart max {s.max_delta_cm} cm
      </span>
    </div>
  );
}

function ItemsTable({ items }) {
  const sorted = [...items].sort((a, b) => ({ ko: 0, warn: 1, ok: 2 }[a.status] - { ko: 0, warn: 1, ok: 2 }[b.status]) || a.index - b.index);
  return (
    <div className="max-h-56 overflow-auto border rounded-sm" data-testid="cotes-table">
      <table className="w-full text-[11px]">
        <thead className="bg-muted sticky top-0">
          <tr><th className="px-1 text-left">#</th><th className="px-1 text-left">Localisation</th>
            <th className="px-1 text-right">Cote (m)</th><th className="px-1 text-right">Mesuré (m)</th>
            <th className="px-1 text-right">Écart (cm)</th><th className="px-1 text-left"></th></tr>
        </thead>
        <tbody>
          {sorted.map((it) => (
            <tr key={it.index} className="border-t whitespace-nowrap" data-testid={`cotes-row-${it.index}`}>
              <td className="px-1 num">{it.index}</td>
              <td className="px-1 truncate max-w-[120px]" title={it.location || ""}>{it.location || "—"}</td>
              <td className="px-1 text-right num">{it.indicated_m.toFixed(2)}</td>
              <td className="px-1 text-right num">{it.measured_m.toFixed(2)}</td>
              <td className="px-1 text-right num">{it.delta_cm > 0 ? "+" : ""}{it.delta_cm}</td>
              <td className="px-1"><span className={`inline-block h-2.5 w-2.5 rounded-full border ${CLS[it.status]}`} title={LABEL[it.status]} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Chains({ chains }) {
  if (!chains?.length) return null;
  return (
    <div className="grid gap-1" data-testid="cotes-chains">
      <p className="text-[11px] font-medium">Chaînes de cotes</p>
      {chains.map((c, i) => (
        <div key={i} className={`text-[11px] px-1.5 py-1 rounded-sm border ${CLS[c.status]}`}>
          #{c.total_index} = {c.total_m.toFixed(2)} m ↔ {c.part_indexes.map((p, j) => `#${p} ${c.parts_m[j].toFixed(2)}`).join(" + ")}
          {" "}= {c.sum_m.toFixed(2)} m ({c.delta_cm > 0 ? "+" : ""}{c.delta_cm} cm)
        </div>
      ))}
    </div>
  );
}

export default function CotesCheckPanel({ plan, pageIndex, refreshPlan }) {
  const [tolPct, setTolPct] = useState(2);
  const [tolCm, setTolCm] = useState(3);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [overlay, setOverlay] = useState(null);

  useEffect(() => {
    setReport(plan?.cotes_checks?.[String(pageIndex)] || null);
    setOverlay(null);
  }, [plan?.plan_id, plan?.cotes_checks, pageIndex]);

  const run = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/cotes/check`,
        { page_index: pageIndex, tol_pct: Number(tolPct) || 2, tol_cm: Number(tolCm) || 0 });
      setReport(data);
      setOverlay(null);
      toast.success(`${data.summary.total} cotes contrôlées — ${data.summary.ko} incohérence(s)` +
        (data.auto_calibrated ? " · échelle calibrée automatiquement" : ""), { duration: 7000 });
      await refreshPlan?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Contrôle des cotes impossible"); }
    finally { setBusy(false); }
  };

  const showOverlay = async () => {
    try {
      const blob = await authedBlob(`/takeoffs/${plan.plan_id}/cotes/overlay.png?page_index=${pageIndex}`);
      setOverlay(URL.createObjectURL(blob));
    } catch (e) { toast.error(e.message); }
  };

  const downloadPdf = async () => {
    try {
      const blob = await authedBlob(`/takeoffs/${plan.plan_id}/cotes/report.pdf?page_index=${pageIndex}`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `controle-cotes-p${pageIndex + 1}.pdf`;
      a.click();
      toast.success("Rapport PDF téléchargé");
    } catch (e) { toast.error(e.message); }
  };

  return (
    <div className="border border-primary/30 bg-primary/5 p-2 rounded-sm grid gap-2" data-testid="cotes-check-panel">
      <p className="overline text-primary">Contrôle des cotes</p>
      <p className="text-[11px] text-muted-foreground">
        Relit toutes les cotes du plan, mesure chaque trait à l'échelle et signale les incohérences
        (cote indiquée ≠ mesure, chaînes de cotes qui ne totalisent pas).
      </p>
      <div className="flex items-center gap-2 text-[11px]">
        <span>Tolérance</span>
        <Input type="number" step="0.5" min="0.1" value={tolPct} onChange={(e) => setTolPct(e.target.value)}
               className="h-7 w-16 rounded-sm num" data-testid="cotes-tol-pct" /> %
        <span>ou</span>
        <Input type="number" step="1" min="0" value={tolCm} onChange={(e) => setTolCm(e.target.value)}
               className="h-7 w-16 rounded-sm num" data-testid="cotes-tol-cm" /> cm
      </div>
      <Button size="sm" className="w-full justify-start gap-2 rounded-sm" disabled={busy} onClick={run}
              data-testid="cotes-check-btn">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Ruler className="h-3.5 w-3.5" />}
        {busy ? "Lecture et mesure des cotes…" : report ? "Relancer le contrôle" : "Contrôler les cotes"}
      </Button>
      {report && (
        <div className="grid gap-2" data-testid="cotes-report">
          <Summary s={report.summary} />
          <ItemsTable items={report.items} />
          <Chains chains={report.chains} />
          {report.surfaces?.matches?.length > 0 && (
            <p className="text-[11px] text-muted-foreground" data-testid="cotes-surfaces">
              Surfaces écrites : {report.surfaces.matches.length} pièce(s) comparée(s), écart médian {report.surfaces.deviation_pct} %.
            </p>
          )}
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="flex-1 gap-2 rounded-sm" onClick={showOverlay}
                    data-testid="cotes-overlay-btn">
              <ImageIcon className="h-3.5 w-3.5" /> Voir le plan annoté
            </Button>
            <Button size="sm" variant="outline" className="flex-1 gap-2 rounded-sm" onClick={downloadPdf}
                    data-testid="cotes-pdf-btn">
              <FileDown className="h-3.5 w-3.5" /> Rapport PDF
            </Button>
          </div>
          {overlay && (
            <a href={overlay} target="_blank" rel="noreferrer" data-testid="cotes-overlay-link">
              <img src={overlay} alt="Plan annoté — cotes mesurées" className="w-full border rounded-sm" data-testid="cotes-overlay-img" />
            </a>
          )}
        </div>
      )}
    </div>
  );
}
