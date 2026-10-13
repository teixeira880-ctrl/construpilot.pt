import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  FileSpreadsheet, FileText, UploadCloud, AlertTriangle, CheckCircle2,
  Sigma, MapPin, Trash2, RefreshCw, Layers, Link2, EyeOff, Ruler, Image as ImageIcon, Sparkles,
} from "lucide-react";

const FLAG_FR = {
  hidden_row: "Ligne masquée",
  subtotal_excluded_from_sum: "Sous-total exclu du total",
  "formula_result_missing:pu": "Formule PU sans résultat",
  "formula_result_missing:amount": "Formule Montant sans résultat",
  "formula_result_missing:qty": "Formule Qté sans résultat",
};
const flagLabel = (f) => FLAG_FR[f] || (f.startsWith("formula_result_missing") ? "Formule sans résultat" : f);
const STATUS_FR = { ok: "ok", empty: "vide", absent: "absente", illegible: "illisible" };
const num = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 2 }));

function Cell({ parsed }) {
  if (!parsed) return <span className="text-muted-foreground">—</span>;
  const bad = parsed.status === "illegible";
  return (
    <span className={bad ? "text-amber-600 font-medium" : ""} title={`statut: ${STATUS_FR[parsed.status] || parsed.status}`}>
      {parsed.value === null ? (STATUS_FR[parsed.status] || "—") : num(parsed.value)}
    </span>
  );
}

export default function DocIntelPage() {
  const [items, setItems] = useState([]);
  const [current, setCurrent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [vat, setVat] = useState("20");
  const fileRef = useRef(null);
  const cctpRef = useRef(null);
  const [reconciling, setReconciling] = useState(false);
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState("");
  const [planReconciling, setPlanReconciling] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/doc-intel");
      setItems(data);
    } catch { toast.error("Chargement impossible"); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);
  useEffect(() => { api.get("/takeoffs").then(({ data }) => setPlans(data.plans || [])).catch(() => {}); }, []);

  const doPlanReconcile = async () => {
    if (!current || !selectedPlan) return toast.error("Choisissez un plan métré");
    setPlanReconciling(true);
    try {
      const { data } = await api.post(`/doc-intel/${current.import_id}/plan-reconcile`, { plan_id: selectedPlan });
      setCurrent({ ...current, plan_reconciliation: data });
      toast.success(`Rapprochement plan terminé : ${data.summary.ecarts} écart(s) sur ${data.summary.compared} poste(s) rapproché(s)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Rapprochement impossible"); }
    setPlanReconciling(false);
  };

  const correctDevisLine = async (c) => {
    if (!current || !c.devis_line_id) return;
    try {
      await api.patch(`/doc-intel/${current.import_id}/lines/${c.devis_line_id}`, { qty: c.measured });
      toast.success(`Devis corrigé : « ${c.devis.designation} » → ${num(c.measured)} ${c.unit}`);
      // rafraîchit l'analyse (arithmétique) puis le rapprochement plan
      const { data: fresh } = await api.get(`/doc-intel/${current.import_id}`);
      const { data: rec } = await api.post(`/doc-intel/${current.import_id}/plan-reconcile`, { plan_id: selectedPlan });
      setCurrent({ ...fresh, plan_reconciliation: rec });
    } catch (e) { toast.error(e?.response?.data?.detail || "Correction impossible"); }
  };

  const applyAllCorrections = async () => {
    if (!current || !selectedPlan) return;
    try {
      const { data: rec } = await api.post(`/doc-intel/${current.import_id}/plan-reconcile/apply-all`, { plan_id: selectedPlan });
      toast.success(`${rec.corrected} ligne(s) de devis alignée(s) sur le métré`);
      const { data: fresh } = await api.get(`/doc-intel/${current.import_id}`);
      setCurrent({ ...fresh, plan_reconciliation: rec });
    } catch (e) { toast.error(e?.response?.data?.detail || "Correction en lot impossible"); }
  };

  // Ouvre le plan avec les postes en écart mis en évidence (cotes dessinées uniquement)
  const viewEcartsOnPlan = (comps) => {
    const pid = current?.plan_reconciliation?.plan?.plan_id;
    if (!pid) return;
    const ids = (comps || []).filter((c) => c.flag && c.measurement_id && !String(c.measurement_id).startsWith("dxf_"))
      .map((c) => c.measurement_id);
    const q = ids.length ? `&highlight=${encodeURIComponent(ids.join(","))}` : "";
    window.open(`/plan?open=${encodeURIComponent(pid)}${q}`, "_blank");
  };


  const open = async (id) => {
    try {
      const { data } = await api.get(`/doc-intel/${id}`);
      setCurrent(data);
    } catch { toast.error("Ouverture impossible"); }
  };

  const doImport = async (file) => {
    if (!file) return;
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!["xlsx", "xlsm", "pdf", "jpg", "jpeg", "png", "webp"].includes(ext))
      return toast.error("Fichier .xlsx, .pdf ou image (JPG/PNG/WEBP)");
    const fd = new FormData();
    fd.append("file", file);
    if (vat.trim()) fd.append("vat_rate", vat.trim());
    setBusy(true);
    try {
      const { data } = await api.post("/doc-intel/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(data.reused ? "Fichier déjà analysé (résultat réutilisé)" : "Analyse terminée");
      await load();
      setCurrent(data.result ? data : await (await api.get(`/doc-intel/${data.import_id}`)).data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Analyse impossible"); }
    setBusy(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const doReconcile = async (file) => {
    if (!file || !current) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) return toast.error("Le CCTP doit être un PDF");
    const fd = new FormData();
    fd.append("cctp", file);
    setReconciling(true);
    try {
      const { data } = await api.post(`/doc-intel/${current.import_id}/reconcile`, fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      setCurrent({ ...current, reconciliation: data });
      toast.success(`Rapprochement terminé : ${data.summary.anomalies} point(s) à vérifier`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Rapprochement impossible"); }
    setReconciling(false);
    if (cctpRef.current) cctpRef.current.value = "";
  };

  const ignoreAnomaly = async (a) => {
    try {
      await api.post("/doc-intel/corrections", {
        signature: a.signature, resolution: "ignored", scope: "entreprise",
        kind: "exception", justification: "Vérifié et accepté depuis le rapprochement",
        import_id: current.import_id,
      });
      const rec = current.reconciliation;
      const kept = rec.anomalies.filter((x) => x.signature !== a.signature);
      const next = {
        ...rec,
        anomalies: kept,
        summary: {
          ...rec.summary,
          anomalies: kept.length,
          [a.type]: Math.max(0, (rec.summary[a.type] || 0) - 1),
        },
      };
      setCurrent({ ...current, reconciliation: next });
      toast.message("Point neutralisé (mémorisé pour l'entreprise)");
    } catch { toast.error("Enregistrement impossible"); }
  };

  const del = async (id) => {
    try {
      await api.delete(`/doc-intel/${id}`);
      if (current?.import_id === id) setCurrent(null);
      await load();
      toast.message("Analyse supprimée");
    } catch { toast.error("Suppression impossible"); }
  };

  const res = current?.result;
  const arith = res?.arithmetic;
  const checkByLine = {};
  (arith?.checks || []).forEach((c) => { checkByLine[c.line_id] = c; });
  const anomalies = [];
  (res?.lines || []).forEach((l) => (l.flags || []).forEach((f) =>
    anomalies.push({ kind: flagLabel(f), where: l.provenance?.designation || `${l.sheet}!${l.row}`, txt: l.designation })));
  (arith?.checks || []).filter((c) => c.status === "mismatch").forEach((c) =>
    anomalies.push({ kind: "Écart arithmétique", where: c.provenance || `${c.sheet}!${c.row}`, txt: `calculé ${num(c.computed)} ≠ fichier ${num(c.file_amount)}` }));
  (res?.warnings || []).forEach((w) => anomalies.push({ kind: w.type === "scanned_page" ? "Page scannée (OCR requis)" : w.type === "hidden_sheet" ? "Feuille masquée" : w.type, where: w.sheet ? w.sheet : w.page ? `page ${w.page}` : "—", txt: w.message }));

  return (
    <div className="mx-auto max-w-6xl px-4 py-8" data-testid="doc-intel-page">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Analyse de documents</h1>
        <p className="mt-2 text-muted-foreground text-sm">
          Importez un DPGF/devis Excel, un PDF ou une <strong>image (facture, devis, CCTP scanné ou photographié)</strong>.
          Les documents scannés sont lus par IA (OCR) — l'IA <strong>relève les champs tels qu'affichés, sans jamais calculer</strong> ;
          chaque donnée reste reliée à sa source et l'arithmétique est recontrôlée de façon déterministe.
        </p>
      </div>

      {/* IMPORT */}
      <div className="rounded-lg border border-border p-4 mb-6 bg-card" data-testid="doc-intel-import">
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <Label className="text-xs">Fichier (.xlsx / .pdf / image)</Label>
            <Input ref={fileRef} type="file" accept=".xlsx,.xlsm,.pdf,.jpg,.jpeg,.png,.webp" data-testid="doc-intel-file"
                   onChange={(e) => doImport(e.target.files?.[0])} className="w-72" disabled={busy} />
          </div>
          <div className="grid gap-1">
            <Label className="text-xs">TVA (%)</Label>
            <Input value={vat} onChange={(e) => setVat(e.target.value)} className="w-24" inputMode="decimal"
                   data-testid="doc-intel-vat" placeholder="20" />
          </div>
          <Button onClick={() => fileRef.current?.click()} disabled={busy} data-testid="doc-intel-upload-btn"
                  className="gap-2">
            <UploadCloud className="h-4 w-4" /> {busy ? "Analyse…" : "Importer et analyser"}
          </Button>
          <Button variant="outline" onClick={load} disabled={loading} className="gap-2 ml-auto">
            <RefreshCw className="h-4 w-4" /> Actualiser
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        {/* LISTE */}
        <div className="space-y-2" data-testid="doc-intel-list">
          {items.length === 0 && <p className="text-sm text-muted-foreground">Aucune analyse pour l'instant.</p>}
          {items.map((it) => (
            <button key={it.import_id} data-testid={`doc-intel-item-${it.import_id}`}
                    onClick={() => open(it.import_id)}
                    className={`w-full text-left rounded-md border p-3 transition-colors hover:border-primary ${current?.import_id === it.import_id ? "border-primary bg-primary/5" : "border-border"}`}>
              <div className="flex items-center gap-2">
                {it.format === "pdf" ? <FileText className="h-4 w-4 text-rose-500" />
                  : it.format === "image" ? <ImageIcon className="h-4 w-4 text-indigo-500" />
                  : <FileSpreadsheet className="h-4 w-4 text-emerald-600" />}
                <span className="flex-1 truncate text-sm font-medium">{it.filename}</span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                <span>{it.lines} lignes</span>
                {it.ocr && <Badge variant="outline" className="h-4 border-indigo-400 text-indigo-600 text-[10px] gap-0.5"><Sparkles className="h-2.5 w-2.5" /> IA</Badge>}
                {it.warnings > 0 && <Badge variant="outline" className="h-4 border-amber-400 text-amber-600 text-[10px]">{it.warnings} alerte(s)</Badge>}
                {it.arithmetic?.mismatches > 0 && <Badge variant="outline" className="h-4 border-red-400 text-red-600 text-[10px]">{it.arithmetic.mismatches} écart(s)</Badge>}
              </div>
            </button>
          ))}
        </div>

        {/* DÉTAIL */}
        <div>
          {!current && <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">Sélectionnez une analyse ou importez un fichier.</div>}
          {current && res && (
            <div className="space-y-5" data-testid="doc-intel-detail">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-lg font-semibold">{current.filename}</h2>
                <Badge variant="outline">{res.format?.toUpperCase()}</Badge>
                {res.ocr?.engine && (
                  <Badge variant="outline" className="border-indigo-400 text-indigo-600 gap-1">
                    <Sparkles className="h-3 w-3" /> Lu par IA · {res.ocr.engine === "gemini-user" ? "Assistant BTP" : "IA (repli)"}
                  </Badge>
                )}
                {res.language && <Badge variant="outline">{res.language.toUpperCase()}</Badge>}
                <span className="text-xs text-muted-foreground">{res.engine_version} · {res.duration_ms} ms</span>
                <Button size="sm" variant="ghost" className="ml-auto text-destructive gap-1" onClick={() => del(current.import_id)} data-testid="doc-intel-delete">
                  <Trash2 className="h-4 w-4" /> Supprimer
                </Button>
              </div>

              {/* Synthèse arithmétique */}
              {arith && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="doc-intel-arith">
                  {[["Total HT calculé", `${num(arith.summary.sum_computed_ht)} €`, Sigma],
                    ["TVA", arith.summary.vat_amount != null ? `${num(arith.summary.vat_amount)} €` : "—", Sigma],
                    ["Total TTC", arith.summary.total_ttc != null ? `${num(arith.summary.total_ttc)} €` : "—", Sigma],
                    ["Écarts détectés", `${arith.summary.mismatches}`, AlertTriangle]].map(([k, v, Ic]) => (
                    <div key={k} className="rounded-md border border-border p-3">
                      <div className="flex items-center gap-1 text-[11px] text-muted-foreground"><Ic className="h-3 w-3" /> {k}</div>
                      <div className="mt-1 text-lg font-semibold num">{v}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Anomalies & incertitudes */}
              <div className="rounded-lg border border-border" data-testid="doc-intel-anomalies">
                <div className="flex items-center gap-2 border-b border-border px-3 py-2 text-sm font-semibold">
                  <AlertTriangle className="h-4 w-4 text-amber-500" /> Points à vérifier ({anomalies.length})
                </div>
                {anomalies.length === 0 ? (
                  <div className="flex items-center gap-2 px-3 py-3 text-sm text-emerald-600"><CheckCircle2 className="h-4 w-4" /> Aucun point détecté (l'absence d'anomalie ne garantit pas l'exactitude).</div>
                ) : (
                  <ul className="divide-y divide-border">
                    {anomalies.slice(0, 60).map((a, i) => (
                      <li key={i} className="flex items-start gap-2 px-3 py-2 text-sm">
                        <Badge variant="outline" className="shrink-0 border-amber-400 text-amber-700">{a.kind}</Badge>
                        <span className="flex-1">{a.txt}</span>
                        <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground"><MapPin className="h-3 w-3" /> {a.where}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Rapprochement CCTP ↔ devis (Étape 2) */}
              {res.format === "xlsx" && (
                <div className="rounded-lg border border-border" data-testid="doc-intel-reconcile">
                  <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2 text-sm font-semibold">
                    <Link2 className="h-4 w-4 text-primary" /> Rapprochement CCTP ↔ devis
                    <span className="flex-1" />
                    <input ref={cctpRef} type="file" accept=".pdf" className="hidden"
                           data-testid="reconcile-cctp-file" onChange={(e) => doReconcile(e.target.files?.[0])} />
                    <Button size="sm" variant="outline" className="gap-2" disabled={reconciling}
                            data-testid="reconcile-btn" onClick={() => cctpRef.current?.click()}>
                      <UploadCloud className="h-4 w-4" /> {reconciling ? "Analyse…" : (current.reconciliation ? "Relancer avec un CCTP" : "Joindre le CCTP (PDF)")}
                    </Button>
                  </div>
                  {!current.reconciliation ? (
                    <p className="px-3 py-3 text-sm text-muted-foreground">Joignez le CCTP (PDF) pour comparer les prescriptions au devis : épaisseurs, ouvrages manquants, doubles comptages.</p>
                  ) : (
                    <div className="p-3 space-y-3" data-testid="reconcile-result">
                      <div className="flex flex-wrap gap-2 text-xs">
                        <Badge variant="outline">{current.reconciliation.summary.prescriptions} prescriptions</Badge>
                        <Badge variant="outline">{current.reconciliation.summary.matched} rapprochées</Badge>
                        <Badge variant="outline" className="border-amber-400 text-amber-600">{current.reconciliation.summary.anomalies} à vérifier</Badge>
                      </div>
                      {current.reconciliation.anomalies.length === 0 ? (
                        <div className="flex items-center gap-2 text-sm text-emerald-600"><CheckCircle2 className="h-4 w-4" /> Aucun écart détecté (ne garantit pas l'exhaustivité).</div>
                      ) : (
                        <ul className="divide-y divide-border rounded border border-border">
                          {current.reconciliation.anomalies.map((a) => (
                            <li key={a.signature} className="p-2 text-sm" data-testid={`reconcile-anomaly-${a.signature}`}>
                              <div className="flex items-start gap-2">
                                <Badge variant="outline" className="shrink-0 border-amber-400 text-amber-700">
                                  {a.type === "thickness_mismatch" ? "Écart d'épaisseur" : a.type === "prescribed_not_found" ? "Omission possible" : "Double comptage"}
                                </Badge>
                                <span className="flex-1">{a.message}</span>
                                <Button size="sm" variant="ghost" className="h-7 gap-1 text-muted-foreground"
                                        data-testid={`reconcile-ignore-${a.signature}`} onClick={() => ignoreAnomaly(a)}>
                                  <EyeOff className="h-3.5 w-3.5" /> Vérifié
                                </Button>
                              </div>
                              <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                                {a.cctp && <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" /> CCTP p{a.cctp.page} : « {a.cctp.text?.slice(0, 90)} »</span>}
                                {a.devis && <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" /> Devis {a.devis.source || ""} : {a.devis.designation}</span>}
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Rapprochement Plan (métré) ↔ devis */}
              {res.format === "xlsx" && (
                <div className="rounded-lg border border-border" data-testid="doc-intel-plan-reconcile">
                  <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2 text-sm font-semibold">
                    <Ruler className="h-4 w-4 text-primary" /> Rapprochement plan (métré) ↔ devis
                    <span className="flex-1" />
                    <select value={selectedPlan} onChange={(e) => setSelectedPlan(e.target.value)}
                            data-testid="plan-reconcile-select"
                            className="h-8 rounded-md border border-border bg-background px-2 text-xs max-w-[220px]">
                      <option value="">Choisir un plan…</option>
                      {plans.map((p) => (
                        <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id}</option>
                      ))}
                    </select>
                    <Button size="sm" variant="outline" className="gap-2" disabled={planReconciling || !selectedPlan}
                            data-testid="plan-reconcile-btn" onClick={doPlanReconcile}>
                      <Link2 className="h-4 w-4" /> {planReconciling ? "Analyse…" : "Comparer"}
                    </Button>
                  </div>
                  {!current.plan_reconciliation ? (
                    <p className="px-3 py-3 text-sm text-muted-foreground">
                      Comparez les quantités MESURÉES sur un plan (murs en ml/m², surfaces) aux quantités du devis, par libellé. Les écarts &gt; 5 % sont signalés avec leurs deux sources.
                    </p>
                  ) : (
                    <div className="p-3 space-y-3" data-testid="plan-reconcile-result">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <Badge variant="outline">{current.plan_reconciliation.summary.compared} rapproché(s)</Badge>
                        <Badge variant="outline" className="border-amber-400 text-amber-600">{current.plan_reconciliation.summary.ecarts} écart(s) &gt; 5 %</Badge>
                        <Badge variant="outline">{current.plan_reconciliation.summary.unmatched} non rapproché(s)</Badge>
                        {current.plan_reconciliation.summary.semantic_used && <Badge variant="outline" className="border-primary/40 text-primary">appoint sémantique</Badge>}
                        <span className="flex-1" />
                        {current.plan_reconciliation.summary.ecarts > 0 && (
                          <>
                            <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]"
                                    data-testid="plan-reconcile-fix-all" onClick={applyAllCorrections}>
                              Tout corriger ({current.plan_reconciliation.summary.ecarts})
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]"
                                    data-testid="plan-reconcile-view-plan"
                                    onClick={() => viewEcartsOnPlan(current.plan_reconciliation.comparisons)}>
                              <MapPin className="h-3 w-3" /> Voir sur le plan
                            </Button>
                          </>
                        )}
                      </div>
                      {current.plan_reconciliation.comparisons.length === 0 ? (
                        <div className="text-sm text-muted-foreground">Aucun poste rapproché (vérifiez que les cotes du plan ont un libellé proche des lignes du devis).</div>
                      ) : (
                        <ul className="divide-y divide-border rounded border border-border">
                          {current.plan_reconciliation.comparisons.map((c) => (
                            <li key={c.measurement_id} className="p-2 text-sm" data-testid={`plan-comp-${c.measurement_id}`}>
                              <div className="flex items-start gap-2">
                                <Badge variant="outline" className={c.flag ? "shrink-0 border-amber-400 text-amber-700" : "shrink-0 border-emerald-400 text-emerald-700"}>
                                  {c.flag ? `Écart ${c.delta_pct > 0 ? "+" : ""}${c.delta_pct}%` : "OK"}
                                </Badge>
                                <span className="flex-1">{c.label} — mesuré <b className="num">{num(c.measured)} {c.unit}</b> vs devis <b className="num">{num(c.devis_qty)} {c.unit}</b></span>
                                {c.source === "dxf" && <Badge variant="outline" className="h-4 border-sky-400 text-sky-600 text-[10px]">CAO</Badge>}
                                {c.method === "sémantique" && <Badge variant="outline" className="h-4 border-primary/40 text-primary text-[10px]">sémantique</Badge>}
                                {c.flag && c.devis_line_id && (
                                  <Button size="sm" variant="outline" className="h-6 gap-1 text-[11px]"
                                          data-testid={`plan-comp-fix-${c.measurement_id}`}
                                          onClick={() => correctDevisLine(c)}>
                                    Corriger le devis → {num(c.measured)} {c.unit}
                                  </Button>
                                )}
                              </div>
                              <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                                <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" /> Plan : « {c.label} »</span>
                                <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" /> Devis {c.devis.source || ""} : {c.devis.designation}</span>
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                      {current.plan_reconciliation.unmatched.length > 0 && (
                        <div className="text-[11px] text-muted-foreground">
                          <span className="font-medium">Cotes du plan sans ligne de devis : </span>
                          {current.plan_reconciliation.unmatched.map((u) => u.label).join(" · ")}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Lignes Excel */}
              {res.format === "xlsx" && (
                <div className="overflow-x-auto rounded-lg border border-border" data-testid="doc-intel-lines">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 text-left">
                      <tr>
                        {["Lot", "Désignation", "Qté", "Un.", "PU", "Montant fichier", "Calculé", "Écart", "Source", "Flags"].map((h) => (
                          <th key={h} className="px-2 py-2 font-semibold whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {res.lines.map((l) => {
                        const ck = checkByLine[l.line_id];
                        const mismatch = ck?.status === "mismatch";
                        const isStruct = l.kind !== "detail";
                        return (
                          <tr key={l.line_id} data-testid={`doc-line-${l.line_id}`}
                              className={`border-t border-border ${isStruct ? "bg-muted/30 italic" : ""} ${mismatch ? "bg-red-50" : ""}`}>
                            <td className="px-2 py-1 whitespace-nowrap text-muted-foreground">{l.lot}</td>
                            <td className="px-2 py-1">{l.kind === "lot_title" ? <b>{l.designation}</b> : l.designation}{l.kind === "subtotal" && <span className="ml-1 text-[10px] text-muted-foreground">(sous-total, exclu)</span>}</td>
                            <td className="px-2 py-1"><Cell parsed={l.qty} /></td>
                            <td className="px-2 py-1 whitespace-nowrap">{l.unit || "—"}</td>
                            <td className="px-2 py-1"><Cell parsed={l.pu} /></td>
                            <td className="px-2 py-1"><Cell parsed={l.amount} /></td>
                            <td className="px-2 py-1">{ck?.computed != null ? num(ck.computed) : "—"}</td>
                            <td className={`px-2 py-1 ${mismatch ? "text-red-600 font-semibold" : "text-muted-foreground"}`}>{ck?.diff != null ? num(ck.diff) : "—"}</td>
                            <td className="px-2 py-1 whitespace-nowrap text-[10px] text-muted-foreground">{l.provenance?.amount || l.provenance?.pu || l.provenance?.designation}</td>
                            <td className="px-2 py-1">
                              <div className="flex flex-wrap gap-1">
                                {(l.flags || []).map((f) => (
                                  <span key={f} className="rounded bg-amber-100 px-1 text-[10px] text-amber-700">{flagLabel(f)}</span>
                                ))}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Champs relevés par IA (OCR) — lecture seule, jamais calculés */}
              {res.ocr && (res.ocr.document || (res.ocr.line_items || []).length > 0) && (
                <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-4 space-y-3" data-testid="doc-intel-ocr-fields">
                  <div className="flex items-center gap-2 text-sm font-semibold text-indigo-700">
                    <Sparkles className="h-4 w-4" /> Champs relevés par l'IA (tels qu'affichés — non recalculés)
                  </div>
                  {res.ocr.document && (
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 text-xs">
                      {[["Type", res.ocr.document.document_type], ["Fournisseur", res.ocr.document.supplier_name],
                        ["Client", res.ocr.document.customer_name], ["N°", res.ocr.document.doc_number],
                        ["Date", res.ocr.document.issue_date], ["Devise", res.ocr.document.currency],
                        ["Sous-total", res.ocr.document.subtotal], ["TVA", res.ocr.document.tax],
                        ["Total", res.ocr.document.total]].filter(([, v]) => v).map(([k, v]) => (
                        <div key={k} className="rounded-md border border-indigo-200 bg-white px-2 py-1">
                          <div className="text-[10px] uppercase text-muted-foreground">{k}</div>
                          <div className="font-medium break-words">{v}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  {(res.ocr.line_items || []).length > 0 && (
                    <div className="max-h-52 overflow-y-auto rounded-md border border-indigo-200 bg-white">
                      <table className="w-full text-xs" data-testid="doc-intel-ocr-items">
                        <thead className="bg-indigo-50 text-left text-[10px] uppercase text-muted-foreground">
                          <tr><th className="px-2 py-1">Désignation</th><th className="px-2 py-1">Qté</th><th className="px-2 py-1">Unité</th><th className="px-2 py-1">PU</th><th className="px-2 py-1">Montant</th></tr>
                        </thead>
                        <tbody>
                          {res.ocr.line_items.map((it, i) => (
                            <tr key={i} className="border-t border-indigo-100">
                              <td className="px-2 py-1">{it.description || "—"}</td>
                              <td className="px-2 py-1">{it.quantity || "—"}</td>
                              <td className="px-2 py-1">{it.unit || "—"}</td>
                              <td className="px-2 py-1">{it.unit_price || "—"}</td>
                              <td className="px-2 py-1">{it.amount || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <p className="text-[11px] text-muted-foreground">
                    ⚠️ Valeurs lues par OCR — à vérifier. Aucun total n'est recalculé par l'IA.
                  </p>
                </div>
              )}

              {/* Contenu PDF / image (texte, incluant l'OCR) */}
              {(res.format === "pdf" || res.format === "image") && (
                <div className="space-y-3" data-testid="doc-intel-pdf">
                  <div className="flex flex-wrap gap-2 text-xs">
                    {(res.pages || []).map((p) => (
                      <Badge key={p.page} variant="outline" className={p.ocr ? "border-indigo-400 text-indigo-600" : p.scanned ? "border-amber-400 text-amber-600" : ""}>
                        Page {p.page} · {p.lines} lignes{p.ocr ? " · IA (OCR)" : p.scanned ? " · scan (OCR)" : ""}{p.tables ? ` · ${p.tables} tableau(x)` : ""}
                      </Badge>
                    ))}
                  </div>
                  <div className="max-h-[420px] overflow-y-auto rounded-lg border border-border divide-y divide-border">
                    {(res.lines || []).length === 0 && (
                      <div className="px-3 py-6 text-center text-xs text-muted-foreground">Aucun texte lisible.</div>
                    )}
                    {(res.lines || []).slice(0, 400).map((l) => (
                      <div key={l.line_id} className="flex items-start gap-2 px-3 py-1.5 text-xs">
                        <span className="inline-flex items-center gap-1 shrink-0 text-[10px] text-muted-foreground">
                          {l.ocr ? <Sparkles className="h-3 w-3 text-indigo-500" /> : <MapPin className="h-3 w-3" />} p{l.page}
                        </span>
                        <span className="flex-1">{l.text}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
