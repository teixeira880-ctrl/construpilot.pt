import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileDown, Calculator, Loader2, Save, AlertTriangle, ReceiptText, Square } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const num = (value, euro = false) => value == null ? "N/C" : new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2, ...(euro ? { style: "currency", currency: "EUR" } : {}) }).format(value);
const running = job => ["queued", "running", "committing"].includes(job?.status);

export default function DossierStudyDialog({ open, onClose, study, busy, onRun, onDownload, onDownloadXlsx, planId, onRefresh }) {
  const nav = useNavigate();
  const [job, setJob] = useState(null);
  const [changes, setChanges] = useState({});
  const [prices, setPrices] = useState({});
  const [reviewed, setReviewed] = useState({});
  const [saving, setSaving] = useState(false);
  const [country, setCountry] = useState("");
  const [vat, setVat] = useState("");
  const [request, setRequest] = useState("Gros œuvre, sous-sol ou vide sanitaire si présent, enduits et maçonnerie de clôture. Hors charpente-couverture et second œuvre.");
  useEffect(() => { setChanges({}); setPrices({}); setReviewed({}); setCountry(study?.settings_snapshot?.country || ""); setVat(study?.totals?.tva_rate == null ? "" : String(Math.round(study.totals.tva_rate * 10000) / 100)); }, [study?.revision, planId]);
  useEffect(() => {
    if (!open || !planId) return undefined;
    setJob(null);
    let stop = false, polling = false, current = null;
    const poll = async () => {
      if (polling) return;
      polling = true;
      try {
        const { data } = await api.get("/pc/study-jobs");
        if (stop) return;
        const next = (data.jobs || []).find(j => j.plan_id === planId);
        if (next && current && running(current) && !running(next)) {
          if (next.status === "completed") { await onRefresh?.(); toast.success("Étude et devis disponibles"); }
          else if (next.status !== "cancelled") toast.error(next.error || "Étude interrompue");
        }
        if (next) { current = next; setJob(next); }
      } catch { /* An intermittent status error never cancels server work. */ }
      finally { polling = false; }
    };
    poll(); const timer = setInterval(poll, 3000);
    return () => { stop = true; clearInterval(timer); };
  }, [open, planId, onRefresh]);
  const launch = async () => {
    const next = await onRun?.({ request, request_id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}` });
    if (next) setJob(next);
  };
  const cancel = async () => {
    try { const { data } = await api.post(`/pc/study-jobs/${job.job_id}/cancel`); setJob(data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Annulation impossible"); }
  };
  const save = async () => {
    const parse = map => Object.fromEntries(Object.entries(map).map(([key, value]) => [key, value === "" ? null : Number(value)]));
    const parsed = { ...parse(changes), ...parse(prices) };
    if (Object.values(parsed).some(v => v !== null && !Number.isFinite(v))) return toast.error("Vérifiez les nombres saisis");
    setSaving(true);
    try {
      await api.post(`/takeoffs/${planId}/pc-study/revise`, { expected_revision: study.revision, parameter_changes: parse(changes), price_changes: parse(prices), review_states: reviewed, ...(country && country !== study.settings_snapshot?.country ? { country } : {}), ...(vat !== "" && vat !== originalVat ? { vat_rate: Number(vat) } : {}) });
      await onRefresh?.(); toast.success("Mesures et prix recalculés ; version précédente conservée");
    } catch (e) { toast.error(e?.response?.data?.detail || "Correction impossible"); }
    finally { setSaving(false); }
  };
  const quote = async () => {
    setSaving(true);
    try {
      const { data } = await api.post(`/takeoffs/${planId}/pc-study/quote`, { expected_revision: study.revision });
      nav(data.edit_url);
    } catch (e) { toast.error(e?.response?.data?.detail || "Création impossible"); }
    finally { setSaving(false); }
  };
  const active = busy || running(job);
  const originalVat = study?.totals?.tva_rate == null ? "" : String(Math.round(study.totals.tva_rate * 10000) / 100);
  const dirty = Object.keys(changes).length + Object.keys(prices).length + Object.keys(reviewed).length > 0 || country !== (study?.settings_snapshot?.country || "") || vat !== (study?.totals?.tva_rate == null ? "" : String(Math.round(study.totals.tva_rate * 10000) / 100));
  return <Dialog open={open} onOpenChange={o => !o && onClose()}>
    <DialogContent className="w-[calc(100vw-1rem)] max-w-5xl max-h-[92dvh] overflow-y-auto border-[#dfd1c2] bg-[#f7f1e9] text-[#302b26] p-4 sm:p-6" data-testid="dossier-study-dialog">
      <DialogHeader><DialogTitle className="text-xl sm:text-2xl">Étude & devis gros œuvre</DialogTitle><DialogDescription className="text-[#6e6359]">Métrés sourcés, calculs contrôlés et devis détaillé. Les hypothèses restent visibles à chaque étape.</DialogDescription></DialogHeader>
      <label className="grid gap-1 text-sm font-medium">Périmètre à chiffrer<textarea className="rounded-xl border border-[#dfd1c2] bg-white/70 p-3 text-sm font-normal" rows={3} value={request} onChange={e => setRequest(e.target.value)} maxLength={2000} disabled={active} /></label>
      <div className="flex flex-wrap gap-2">
        <Button className="bg-[#925535] hover:bg-[#784329] text-white gap-2" onClick={launch} disabled={active || dirty} data-testid="dossier-run">{active ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}{active ? "Étude en cours" : study ? "Nouvelle analyse" : "Analyser le dossier"}</Button>
        {study && <><Button variant="outline" className="gap-2" disabled={dirty} onClick={() => onDownload("pdf")} data-testid="dossier-pdf"><FileDown size={16} />Devis PDF</Button><Button variant="outline" disabled={dirty} onClick={() => onDownload("docx")}>Word</Button><Button variant="outline" disabled={dirty} onClick={onDownloadXlsx}>Excel</Button></>}
      </div>
      {active && <div className="rounded-xl border border-[#dfd1c2] bg-white/60 p-3 text-sm" role="status" data-testid="dossier-progress"><p className="font-semibold">{job?.progress?.phase || "Démarrage"} · {job?.progress?.completed_pages || 0}/{job?.progress?.total_pages || "…"} pages</p><p className="mt-1 text-[#6e6359]">Tu peux changer de page. L’étude continue sur le serveur ; une notification annoncera le résultat.</p>{job && job.status !== "committing" && <Button variant="ghost" className="mt-1 gap-1" onClick={cancel}><Square size={12} />Arrêter l’étude</Button>}</div>}
      {!active && job?.error && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm">{job.error}</p>}
      {!study && !active && <p className="text-sm text-[#6e6359]">Toutes les pages sélectionnées seront lues, y compris les dernières feuilles. Les fondations et les matériaux ne sont pas imposés par des règles fixes.</p>}
      {study && <>
        <section className="rounded-2xl bg-[#925535] p-5 text-white" data-testid="dossier-total"><p className="text-sm opacity-90">{study.totals.partial ? "Budget partiel HT" : "Budget estimatif HT"}</p><p className="text-3xl font-bold tabular-nums mt-1">{num(study.totals.ht, true)}</p><p className="text-sm mt-2">{num(study.totals.ttc, true)} TTC · TVA {num(study.totals.tva_rate == null ? null : study.totals.tva_rate * 100)} %</p></section>
        <p className="text-xs text-[#6e6359]">M : mesure contrôlée · H : hypothèse / mesure à contrôler · P : provision · N/C : non chiffré. Prix budgétaires de fourniture et pose, sans marge ajoutée automatiquement.</p>
        {study.variants?.map(v => <div className="rounded-xl border border-[#dfd1c2] p-3 text-sm" key={v.label}><b>{v.label}</b> : -{num(v.deduction_ht, true)} HT, soit {num(v.total_ht, true)} HT.<p className="text-xs mt-1 text-[#6e6359]">{v.note}</p></div>)}
        <details className="rounded-xl border border-[#dfd1c2] bg-white/50 p-3" open={study.controls?.some(c => c.severity === "error")}><summary className="cursor-pointer font-semibold text-sm flex gap-2"><AlertTriangle size={16} />Points à vérifier ({(study.warnings?.length || 0)+(study.controls?.length || 0)})</summary><ul className="mt-3 space-y-2 text-sm list-disc pl-5">{study.controls?.map((c,i) => <li key={`c${i}`}>{c.item_id} : {c.message}</li>)}{study.warnings?.map((w,i) => <li key={i}>{w}</li>)}</ul></details>
        <div className="space-y-3">{study.lots.map(lot => <section key={lot.key} className="rounded-xl overflow-hidden border border-[#dfd1c2]"><h3 className="px-3 py-2 bg-[#f0e7dc] font-semibold text-sm flex flex-wrap justify-between gap-2"><span>{lot.lot}</span><span>{num(lot.total_ht, true)} HT{lot.partial ? " (partiel)" : ""}</span></h3><div className="divide-y divide-[#dfd1c2]">{lot.lines.map(line => <details key={line.id} className="bg-white/60 p-3"><summary className="cursor-pointer text-sm"><span className="font-medium">{line.designation}</span><span className="flex flex-wrap justify-between gap-2 mt-1 text-xs text-[#6e6359]"><span>{num(line.qty)} {line.unit} · {line.quantity_status}</span><b className="text-[#302b26]">{num(line.total, true)} HT</b></span></summary><div className="mt-3 space-y-2 text-xs"><p>{line.detail}</p><p className="break-words"><b>Calcul :</b> {line.expression}</p>{line.sources?.map(s => <p key={s.id}>{s.label} = {num(s.value)} {s.unit}{s.sources?.length ? ` · ${s.sources.map(x => `p. ${x.page} : ${x.text}`).join(" ; ")}` : ` · ${s.note || "À confirmer"}`}</p>)}<label className="flex flex-wrap items-center gap-2">Prix unitaire HT<input type="number" min="0" step="0.01" aria-label={`Prix ${line.designation}`} className="w-32 border rounded-lg p-2 bg-white text-[#302b26]" value={prices[line.id] ?? line.unit_price ?? ""} onChange={e => setPrices(p => ({ ...p, [line.id]: e.target.value }))} /></label><p className="text-[#6e6359]">{line.price_source === "estimation_budgetaire" ? "Estimation budgétaire à confirmer avec l’entreprise" : line.price_source === "prix_utilisateur" ? "Prix saisi" : "Prix absent"}</p></div></details>)}</div></section>)}</div>
        <details className="rounded-xl border border-[#dfd1c2] p-3" data-testid="dossier-inputs"><summary className="cursor-pointer font-semibold">Contrôler et corriger les mesures</summary><div className="grid sm:grid-cols-2 gap-3 mt-4">{study.spec.parameters.filter(p => !p.expression).map(p => <div key={p.id} className="border border-[#dfd1c2] rounded-xl p-3 min-w-0 bg-white/50"><label className="text-sm grid gap-1">{p.label || p.id} ({p.unit})<input type="number" step="any" aria-label={`Mesure ${p.id}`} value={changes[p.id] ?? p.value ?? ""} onChange={e => { setChanges(c => ({ ...c, [p.id]: e.target.value })); setReviewed(r => ({ ...r, [p.id]: false })); }} className="w-full min-w-0 rounded-lg border p-2 bg-white" /></label><p className="text-xs mt-1 text-[#6e6359]">{p.note || p.sources?.map(s => `p. ${s.page} : ${s.text}`).join(" ; ") || "Source à confirmer"}</p><label className="flex gap-2 items-start text-xs mt-2"><input type="checkbox" checked={reviewed[p.id] ?? Boolean(p.reviewed && !(p.id in changes))} onChange={e => setReviewed(r => ({ ...r, [p.id]: e.target.checked }))} />J’ai contrôlé cette mesure</label></div>)}</div></details>
        <div className="flex flex-wrap gap-3 text-sm"><label>Pays fiscal<select className="block border rounded-lg p-2 bg-white" value={country} onChange={e => {setCountry(e.target.value); setVat(e.target.value === "PT" ? "23" : e.target.value === "FR" ? "20" : "");}}><option value="">À confirmer</option><option value="FR">France</option><option value="PT">Portugal</option></select></label><label>TVA (%)<input className="block border rounded-lg p-2 bg-white w-24" type="number" min="0" max="100" step="0.1" value={vat} onChange={e => setVat(e.target.value)} /></label></div>
        <div className="flex flex-wrap gap-2"><Button className="bg-[#925535] text-white hover:bg-[#784329] gap-2" onClick={save} disabled={saving || active} data-testid="dossier-save"><Save size={16} />Enregistrer et recalculer</Button><Button variant="outline" onClick={quote} disabled={saving || active || dirty || study.totals.partial || study.totals.ttc == null} className="gap-2"><ReceiptText size={16} />Créer un devis modifiable</Button></div>
        {dirty && <p className="text-xs text-[#925535]" role="status">Enregistre les corrections avant d’exporter le devis.</p>}
        <p className="text-xs text-[#6e6359]">Le devis modifiable est un brouillon distinct. Les commandes de matériaux nécessitent des quantités de fourniture vérifiées ; elles ne sont pas déduites des forfaits.</p>
      </>}
    </DialogContent>
  </Dialog>;
}
