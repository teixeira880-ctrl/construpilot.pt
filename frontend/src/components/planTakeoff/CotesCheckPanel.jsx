import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Ruler, FileDown, Loader2, Image as ImageIcon, Pencil, EyeOff, Eye, Check, X, RefreshCw, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { api } from "@/lib/api";

const LABEL = { ok: "OK", warn: "À vérifier", ko: "Incohérence", ignored: "Ignorée" };
const CLS = {
  ok: "bg-emerald-100 text-emerald-800 border-emerald-300",
  warn: "bg-orange-100 text-orange-800 border-orange-300",
  ko: "bg-red-100 text-red-800 border-red-300",
  ignored: "bg-slate-100 text-slate-500 border-slate-300",
};
const RANK = { ko: 0, warn: 1, ok: 2, ignored: 3 };

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
      <Badge className={`rounded-sm border ${CLS[s.verdict]}`} data-testid="cotes-verdict">{LABEL[s.verdict]}</Badge>
      <span className="text-[11px] text-muted-foreground">
        {s.total} cotes · {s.ok} OK · {s.warn} à vérifier · <b className="text-red-700">{s.ko} incohérence(s)</b>
        {s.ignored > 0 && ` · ${s.ignored} ignorée(s)`}
        {s.chains_total > 0 && ` · ${s.chains_total} chaîne(s) (${s.chains_ko} KO)`} · écart max {s.max_delta_cm} cm
      </span>
    </div>
  );
}

function Row({ it, selected, onFocus, onEdit, onToggleIgnore, busy }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(it.indicated_m);
  const ref = useRef(null);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);
  const save = async () => {
    const v = Number(String(val).replace(",", "."));
    if (!v || v <= 0) return toast.error("Valeur invalide");
    await onEdit(it.index, v);
    setEditing(false);
  };
  return (
    <tr className={`border-t whitespace-nowrap cursor-pointer ${selected ? "bg-amber-100 text-slate-900" : "hover:bg-muted/60"} ${it.ignored ? "opacity-50" : ""}`}
        data-testid={`cotes-row-${it.index}`} onClick={() => onFocus(it)}>
      <td className="px-1 num">{it.index}</td>
      <td className="px-1 truncate max-w-[110px]" title={`${it.location || ""}${it.edited ? ` (corrigée, lu ${it.original_m})` : ""}`}>
        {it.location || "—"}{it.edited && <span className="text-amber-700"> ✎</span>}
      </td>
      <td className="px-1 text-right num" onClick={(e) => { if (editing) e.stopPropagation(); }}>
        {editing ? (
          <span className="inline-flex items-center gap-0.5">
            <Input ref={ref} value={val} onChange={(e) => setVal(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }}
                   className="h-5 w-14 px-1 text-[11px] rounded-sm num" data-testid={`cotes-edit-input-${it.index}`} />
            <button onClick={save} className="text-emerald-700" data-testid={`cotes-edit-save-${it.index}`}><Check className="h-3 w-3" /></button>
            <button onClick={() => setEditing(false)} className="text-muted-foreground"><X className="h-3 w-3" /></button>
          </span>
        ) : it.indicated_m.toFixed(2)}
      </td>
      <td className="px-1 text-right num">{it.measured_m.toFixed(2)}</td>
      <td className="px-1 text-right num">{it.delta_cm > 0 ? "+" : ""}{it.delta_cm}</td>
      <td className="px-1">
        <span className={`inline-block h-2.5 w-2.5 rounded-full border ${CLS[it.status]}`} title={LABEL[it.status]} data-testid={`cotes-status-${it.index}`} />
      </td>
      <td className="px-1" onClick={(e) => e.stopPropagation()}>
        <span className="inline-flex gap-1">
          <button disabled={busy || it.ignored} onClick={() => { setVal(it.indicated_m); setEditing(true); }}
                  className="text-muted-foreground hover:text-foreground disabled:opacity-30" title="Corriger la cote lue"
                  data-testid={`cotes-edit-btn-${it.index}`}><Pencil className="h-3 w-3" /></button>
          <button disabled={busy} onClick={() => onToggleIgnore(it)} className="text-muted-foreground hover:text-foreground"
                  title={it.ignored ? "Réintégrer la cote" : "Ignorer la cote"} data-testid={`cotes-ignore-btn-${it.index}`}>
            {it.ignored ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
          </button>
        </span>
      </td>
    </tr>
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

function SendDialog({ open, onClose, plan, pageIndex, report, onSent }) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [copyMe, setCopyMe] = useState(true);
  const [busy, setBusy] = useState(false);
  const send = async () => {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return toast.error("Adresse e-mail invalide");
    setBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/cotes/send`,
        { page_index: pageIndex, to_email: email, message, copy_me: copyMe });
      toast.success(`Rapport envoyé à ${data.sent_to}${data.copy_sent ? " (copie reçue)" : ""}`, { duration: 7000 });
      onSent?.();
      onClose();
    } catch (e) { toast.error(e?.response?.data?.detail || "Envoi impossible"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-sm sm:max-w-md" data-testid="cotes-send-dialog">
        <DialogHeader>
          <DialogTitle>Envoyer le rapport de contrôle des cotes</DialogTitle>
          <DialogDescription>
            Le PDF (synthèse, toutes les cotes, chaînes et plan annoté) est joint à l'e-mail.
            {report && ` Verdict actuel : ${LABEL[report.summary.verdict]} — ${report.summary.ko} incohérence(s).`}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label className="text-xs">Destinataire (architecte, client, bureau d'études)</Label>
          <Input type="email" placeholder="architecte@exemple.fr" value={email} onChange={(e) => setEmail(e.target.value)}
                 className="rounded-sm" data-testid="cotes-send-email" />
          <Label className="text-xs">Message (optionnel)</Label>
          <Textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} className="rounded-sm text-sm"
                    placeholder="Bonjour, veuillez trouver ci-joint le contrôle des cotes du plan…" data-testid="cotes-send-message" />
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={copyMe} onChange={(e) => setCopyMe(e.target.checked)} data-testid="cotes-send-copy" />
            M'envoyer une copie
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose} disabled={busy}>Annuler</Button>
          <Button className="rounded-sm gap-2" onClick={send} disabled={busy} data-testid="cotes-send-submit">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />} Envoyer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function CotesCheckPanel({ plan, pageIndex, refreshPlan, selectedIndex = null, onFocusCote }) {
  const [tolPct, setTolPct] = useState(2);
  const [tolCm, setTolCm] = useState(3);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [overlay, setOverlay] = useState(null);
  const [sendOpen, setSendOpen] = useState(false);

  useEffect(() => {
    const r = plan?.cotes_checks?.[String(pageIndex)] || null;
    setReport(r);
    setOverlay(null);
    if (r?.tolerance) { setTolPct(r.tolerance.pct); setTolCm(r.tolerance.cm); }
  }, [plan?.plan_id, plan?.cotes_checks, pageIndex]);

  const tolChanged = report && (Number(tolPct) !== report.tolerance?.pct || Number(tolCm) !== report.tolerance?.cm);

  const apply = async (fn, okMsg) => {
    setBusy(true);
    try {
      const { data } = await fn();
      setReport(data);
      setOverlay(null);
      if (okMsg) toast.success(okMsg(data), { duration: 6000 });
      await refreshPlan?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Opération impossible"); }
    finally { setBusy(false); }
  };

  const run = () => apply(
    () => api.post(`/takeoffs/${plan.plan_id}/cotes/check`, { page_index: pageIndex, tol_pct: Number(tolPct) || 2, tol_cm: Number(tolCm) || 0 }),
    (d) => `${d.summary.total} cotes contrôlées — ${d.summary.ko} incohérence(s)` + (d.auto_calibrated ? " · échelle calibrée automatiquement" : ""));
  const recompute = () => apply(
    () => api.post(`/takeoffs/${plan.plan_id}/cotes/recompute`, { page_index: pageIndex, tol_pct: Number(tolPct) || 2, tol_cm: Number(tolCm) || 0 }),
    (d) => `Recalculé avec ±${d.tolerance.pct} % / ${d.tolerance.cm} cm — ${d.summary.ko} incohérence(s)`);
  const editItem = (index, indicated_m) => apply(
    () => api.patch(`/takeoffs/${plan.plan_id}/cotes/items/${index}`, { page_index: pageIndex, indicated_m }),
    () => `Cote #${index} corrigée et rapport recalculé`);
  const toggleIgnore = (it) => apply(
    () => api.patch(`/takeoffs/${plan.plan_id}/cotes/items/${it.index}`, { page_index: pageIndex, ignored: !it.ignored }),
    () => (it.ignored ? `Cote #${it.index} réintégrée` : `Cote #${it.index} ignorée`));

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

  const sorted = report ? [...report.items].sort((a, b) => (RANK[a.status] - RANK[b.status]) || a.index - b.index) : [];

  return (
    <div className="border border-primary/30 bg-primary/5 p-2 rounded-sm grid gap-2" data-testid="cotes-check-panel">
      <p className="overline text-primary">Contrôle des cotes</p>
      <p className="text-[11px] text-muted-foreground">
        Relit toutes les cotes du plan, mesure chaque trait à l'échelle et signale les incohérences
        (cote indiquée ≠ mesure, chaînes de cotes qui ne totalisent pas). Cliquez une ligne pour zoomer sur la cote.
      </p>
      <div className="flex items-center gap-2 text-[11px]">
        <span>Tolérance</span>
        <Input type="number" step="0.5" min="0.1" value={tolPct} onChange={(e) => setTolPct(e.target.value)}
               className="h-7 w-16 rounded-sm num" data-testid="cotes-tol-pct" /> %
        <span>ou</span>
        <Input type="number" step="1" min="0" value={tolCm} onChange={(e) => setTolCm(e.target.value)}
               className="h-7 w-16 rounded-sm num" data-testid="cotes-tol-cm" /> cm
      </div>
      <div className="flex gap-2">
        <Button size="sm" className="flex-1 justify-start gap-2 rounded-sm" disabled={busy} onClick={run} data-testid="cotes-check-btn">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Ruler className="h-3.5 w-3.5" />}
          {busy ? "Lecture et mesure des cotes…" : report ? "Relancer (relecture IA)" : "Contrôler les cotes"}
        </Button>
        {tolChanged && (
          <Button size="sm" variant="outline" className="gap-1 rounded-sm" disabled={busy} onClick={recompute}
                  title="Recalculer avec la nouvelle tolérance, sans relire le plan" data-testid="cotes-recompute-btn">
            <RefreshCw className="h-3.5 w-3.5" /> Recalculer
          </Button>
        )}
      </div>
      {report && (
        <div className="grid gap-2" data-testid="cotes-report">
          <Summary s={report.summary} />
          <div className="max-h-64 overflow-auto border rounded-sm" data-testid="cotes-table">
            <table className="w-full text-[11px]">
              <thead className="bg-muted sticky top-0">
                <tr><th className="px-1 text-left">#</th><th className="px-1 text-left">Localisation</th>
                  <th className="px-1 text-right">Cote (m)</th><th className="px-1 text-right">Mesuré (m)</th>
                  <th className="px-1 text-right">Écart (cm)</th><th className="px-1"></th><th className="px-1"></th></tr>
              </thead>
              <tbody>
                {sorted.map((it) => (
                  <Row key={it.index} it={it} selected={selectedIndex === it.index} busy={busy}
                       onFocus={onFocusCote} onEdit={editItem} onToggleIgnore={toggleIgnore} />
                ))}
              </tbody>
            </table>
          </div>
          <Chains chains={report.chains} />
          {report.surfaces?.matches?.length > 0 && (
            <p className="text-[11px] text-muted-foreground" data-testid="cotes-surfaces">
              Surfaces écrites : {report.surfaces.matches.length} pièce(s) comparée(s), écart médian {report.surfaces.deviation_pct} %.
            </p>
          )}
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="flex-1 gap-2 rounded-sm" onClick={showOverlay} data-testid="cotes-overlay-btn">
              <ImageIcon className="h-3.5 w-3.5" /> Plan annoté
            </Button>
            <Button size="sm" variant="outline" className="flex-1 gap-2 rounded-sm" onClick={downloadPdf} data-testid="cotes-pdf-btn">
              <FileDown className="h-3.5 w-3.5" /> PDF
            </Button>
            <Button size="sm" variant="outline" className="flex-1 gap-2 rounded-sm" onClick={() => setSendOpen(true)} data-testid="cotes-send-btn">
              <Mail className="h-3.5 w-3.5" /> Envoyer
            </Button>
          </div>
          {report.last_sent && (
            <p className="text-[11px] text-muted-foreground" data-testid="cotes-last-sent">
              Dernier envoi : {report.last_sent.to_email} · {new Date(report.last_sent.sent_at).toLocaleString("fr-FR")}
            </p>
          )}
          <SendDialog open={sendOpen} onClose={() => setSendOpen(false)} plan={plan} pageIndex={pageIndex}
                      report={report} onSent={() => refreshPlan?.()} />
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
