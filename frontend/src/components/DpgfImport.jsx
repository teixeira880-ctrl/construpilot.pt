import { Fragment, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FileSpreadsheet, Upload, Download, Loader2, Sparkles, FileText, Ban, Check,
  BookOpen, Wand2, Percent, X, Users, History, Scale, Trash2, Pencil, ShieldAlert,
  Copy, Mail, Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";

const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const VATS = [10, 20, 5.5];

const STEP_LABEL = {
  queued: "Démarrage du chiffrage…",
  reading: "Lecture des bordereaux Excel…",
  directives: "Application de vos consignes…",
  cctp_read: "Lecture du CCTP et des pièces écrites…",
  cctp_analysis: "Analyse des prescriptions du CCTP…",
  gaps: "Recherche des ouvrages oubliés…",
  library: "Recherche dans votre bibliothèque de prix…",
  pricing: "Chiffrage des lignes…",
  saving: "Enregistrement de l'étude…",
};

const SourceTag = ({ s }) => {
  const map = {
    bibliotheque: ["Votre prix", "bg-emerald-500/10 text-emerald-600"],
    ia: ["IA", "bg-amber-500/10 text-amber-600"],
    manuel: ["Saisi", "bg-primary/10 text-primary"],
    soustraitant: ["Sous-traitant", "bg-violet-500/10 text-violet-600"],
    fichier: ["Bordereau", "bg-sky-500/10 text-sky-600"],
  };
  const [label, cls] = map[s] || ["—", "text-muted-foreground"];
  return <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-full ${cls}`}>{label}</span>;
};

const FileChips = ({ items, onRemove, testid }) => (
  items.length ? (
    <div className="flex flex-wrap gap-1.5" data-testid={`${testid}s`}>
      {items.map((f, i) => (
        <span key={`${f.name}-${i}`} data-testid={`${testid}-${i}`}
          className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-0.5 text-[11px]">
          {f.name}
          <button onClick={() => onRemove(i)} className="text-muted-foreground hover:text-red-500"
            aria-label="Retirer" data-testid={`${testid}-remove-${i}`}>
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  ) : null
);

// Import Excel architecte (DPGF/BPU/DQE) → chiffrage bibliothèque + IA, CCTP, consignes, devis.
export const DpgfImport = () => {
  const nav = useNavigate();
  const fileRef = useRef(null);
  const cctpRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [cctps, setCctps] = useState([]);
  const [instructions, setInstructions] = useState("");
  const [margin, setMargin] = useState(0);
  const [analyseCctp, setAnalyseCctp] = useState(true);
  const [marketCompare, setMarketCompare] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const jobTimer = useRef(null);
  const [res, setRes] = useState(null);
  const [vat, setVat] = useState(10);
  const [fullDesc, setFullDesc] = useState(true);
  const [history, setHistory] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [rfqs, setRfqs] = useState([]);
  const [rfqLot, setRfqLot] = useState(null);
  const [rfqPick, setRfqPick] = useState([]);
  const [rfqEmail, setRfqEmail] = useState("");
  const [rfqMsg, setRfqMsg] = useState("");
  const [gapQty, setGapQty] = useState({});
  const [compare, setCompare] = useState(null);
  const [label, setLabel] = useState("");
  const [minMargin, setMinMargin] = useState(0);
  const [emailNotify, setEmailNotify] = useState(true);
  const [variants, setVariants] = useState(null);

  useEffect(() => {
    api.get("/pro/dpgf/settings/margin").then(({ data }) => setMinMargin(data.min_margin_pct)).catch(() => {});
    api.get("/pro/dpgf/settings/notify-email").then(({ data }) => setEmailNotify(data.enabled)).catch(() => {});
  }, []);

  const saveEmailNotify = async (enabled) => {
    setEmailNotify(enabled);
    try {
      await api.patch("/pro/dpgf/settings/notify-email", { enabled });
      toast.success(enabled ? "E-mail activé pour les gros chiffrages" : "E-mail désactivé");
    } catch { toast.error("Réglage non enregistré"); setEmailNotify(!enabled); }
  };

  const saveMinMargin = async (value) => {
    const pct = Math.max(0, Math.min(90, Number(value) || 0));
    if (pct === Number(minMargin)) return;
    try {
      await api.patch("/pro/dpgf/settings/margin", { min_margin_pct: pct });
      setMinMargin(pct);
      toast.success(pct ? `Alerte activée sous ${pct}% de marge` : "Alerte de marge désactivée");
    } catch { toast.error("Réglage non enregistré"); }
  };

  const renameStudy = async (fileId, current) => {
    const next = window.prompt("Nom de ce chiffrage", current || "");
    if (next === null) return;
    try {
      const { data } = await api.patch(`/pro/dpgf/${fileId}/label`, { label: next });
      if (res?.file_id === fileId) setRes(data);
      setHistory((p) => p.map((h) => (h.file_id === fileId ? { ...h, label: next.trim() } : h)));
      toast.success("Chiffrage renommé");
    } catch { toast.error("Renommage impossible"); }
  };

  const loadHistory = () => api.get("/pro/dpgf").then(({ data }) => setHistory(data)).catch(() => {});
  useEffect(() => { loadHistory(); }, []);
  useEffect(() => () => clearTimeout(jobTimer.current), []);
  // Reprise : un chiffrage lancé avant la fermeture de l'onglet est retrouvé et suivi.
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/pro/dpgf/import/job/active");
        if (data.job) {
          setBusy(true); setProgress(data.job);
          toast.info("Chiffrage en cours retrouvé — suivi reprisé");
          watchJob(data.job.job_id);
        }
      } catch { /* aucun chiffrage en cours */ }
    })();
  }, []);

  const loadStudy = async (fileId) => {    try {
      const [{ data }, { data: r }] = await Promise.all([
        api.get(`/pro/dpgf/${fileId}`),
        api.get(`/pro/dpgf/${fileId}/rfq`, { params: { origin_url: window.location.origin } }),
      ]);
      setRes(data); setRfqs(r); setVariants(null); setCompare(null);
    } catch { toast.error("Étude introuvable"); }
  };

  const removeStudy = async (h) => {
    if (!window.confirm(`Supprimer le chiffrage « ${h.filename || "Bordereau"} » ? Le devis lié, s'il existe, est conservé.`)) return;
    try {
      await api.delete(`/pro/dpgf/${h.file_id}`);
      setHistory((p) => p.filter((x) => x.file_id !== h.file_id));
      if (res?.file_id === h.file_id) { setRes(null); setRfqs([]); setCompare(null); setVariants(null); }
      toast.success("Chiffrage supprimé");
    } catch { toast.error("Suppression impossible"); }
  };

  const openRfq = async (lot) => {
    setRfqLot(lot); setRfqPick([]); setRfqEmail(""); setRfqMsg("");
    try { const { data } = await api.get("/pro/suppliers"); setSuppliers(data.items || []); }
    catch { setSuppliers([]); }
  };

  const sendRfq = async () => {
    const emails = rfqEmail.split(/[,;\s]+/).filter((e) => e.includes("@"));
    if (!rfqPick.length && !emails.length) { toast.error("Choisissez au moins un destinataire"); return; }
    try {
      await api.post(`/pro/dpgf/${res.file_id}/rfq`, {
        lot: rfqLot, supplier_ids: rfqPick, emails, message: rfqMsg,
        origin_url: window.location.origin,
      });
      toast.success("Demande de prix envoyée");
      setRfqLot(null);
      const { data } = await api.get(`/pro/dpgf/${res.file_id}/rfq`, { params: { origin_url: window.location.origin } });
      setRfqs(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Envoi impossible"); }
  };

  const setLotMargin = async (lot, value) => {
    const pct = Number(value);
    if (Number.isNaN(pct)) return;
    const current = (res.directives?.lot_margins || {})[lot];
    if (current !== undefined && Number(current) === pct) return;
    try {
      const { data } = await api.patch(`/pro/dpgf/${res.file_id}/lot-margin`, { lot, margin_pct: pct });
      setRes(data);
      toast.success(`Coefficient ${pct}% appliqué sur ${lot}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Coefficient non appliqué"); }
  };

  const loadCompare = async () => {
    try {
      const { data } = await api.get(`/pro/dpgf/${res.file_id}/offers-compare`);
      setCompare(data);
      if (!data.lots.length) toast.info("Aucune offre reçue pour l'instant");
    } catch { toast.error("Comparatif indisponible"); }
  };

  const applyOffer = async (rfq, token) => {
    try {
      const { data } = await api.post(`/pro/dpgf/${res.file_id}/rfq/${rfq.rfq_id}/apply`, { token });
      setRes(data.study);
      toast.success(`Offre de ${data.from} retenue sur ${data.applied} ligne(s)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossible de retenir cette offre"); }
  };

  const addGap = async (gap) => {
    const qty = Number(gapQty[gap.gap_id]);
    if (!qty || qty <= 0) { toast.error("Indiquez la quantité"); return; }
    try {
      const { data } = await api.post(`/pro/dpgf/${res.file_id}/gap/${gap.gap_id}/add`, { qty });
      setRes(data);
      toast.success("Ouvrage ajouté à l'étude");
    } catch (e) { toast.error(e?.response?.data?.detail || "Ajout impossible"); }
  };

  const ignoreGap = async (gap) => {
    try {
      const { data } = await api.post(`/pro/dpgf/${res.file_id}/gap/${gap.gap_id}/ignore`);
      setRes(data);
    } catch { toast.error("Erreur"); }
  };

  const run = async () => {
    if (!files.length) { toast.error("Choisissez au moins un bordereau Excel (.xlsx)"); return; }
    setBusy(true); setRes(null); setProgress({ step: "queued" });
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      cctps.forEach((f) => fd.append("cctp_files", f));
      fd.append("instructions", instructions);
      fd.append("label", label);
      fd.append("margin_pct", String(Number(margin) || 0));
      fd.append("analyse_cctp", String(!!analyseCctp));
      fd.append("market_compare", String(!!marketCompare));
      const { data } = await api.post("/pro/dpgf/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      await watchJob(data.job_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import impossible (.xlsx attendu)");
      setBusy(false); setProgress(null);
    }
  };

  // Le chiffrage tourne côté serveur : on suit l'avancement, aucune requête longue.
  const watchJob = (jobId) => new Promise((resolve) => {
    const tick = async () => {
      try {
        const { data } = await api.get(`/pro/dpgf/import/job/${jobId}`);
        setProgress(data);
        if (data.status === "done") {
          setRes(data.result); setRfqs([]); loadHistory();
          const r = data.result || {};
          toast.success(`${r.priced}/${r.line_count} lignes chiffrées · ${r.excluded} non chiffrée(s) · ${eur(r.grand_total_ht)} HT`);
        } else if (data.status === "error") {
          toast.error(data.error || "Chiffrage impossible");
        } else {
          jobTimer.current = setTimeout(tick, 3000);
          return;
        }
      } catch {
        toast.error("Suivi du chiffrage interrompu");
      }
      setBusy(false); setProgress(null); resolve();
    };
    tick();
  });

  const patchLine = async (lineId, payload) => {
    try {
      const { data } = await api.patch(`/pro/dpgf/${res.file_id}/line/${lineId}`, payload);
      setRes(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Modification impossible"); }
  };

  const download = async () => {
    try {
      const { data } = await api.get(`/pro/dpgf/file/${res.file_id}`, { responseType: "blob" });
      const multi = (res.sources || []).length > 1;
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url; a.download = multi ? "dpgf_chiffre.zip" : "dpgf_chiffre.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Téléchargement impossible"); }
  };

  const rememberPrices = async () => {
    try {
      const { data } = await api.post(`/pro/dpgf/${res.file_id}/remember`);
      toast.success(`${data.remembered} prix ajoutés à votre bibliothèque ConstruPilot (disponibles dans l'éditeur de devis)`);
    } catch { toast.error("Enregistrement impossible"); }
  };

  const duplicateStudy = async (fileId, current) => {
    const suggested = `${current || "Chiffrage"} — variante`;
    const next = window.prompt("Nom de la variante (ajustez la marge ensuite)", suggested);
    if (next === null) return;
    try {
      const { data } = await api.post(`/pro/dpgf/${fileId}/duplicate`, { label: next });
      toast.success("Variante créée — ajustez le coefficient puis comparez");
      setVariants(null);
      loadHistory();
      setRes(data); setRfqs([]); setCompare(null);
    } catch { toast.error("Duplication impossible"); }
  };

  const loadVariants = async () => {
    try {
      const { data } = await api.get(`/pro/dpgf/${res.file_id}/variants`);
      setVariants(data);
      if (data.variants.length < 2) {
        toast.info("Créez une variante pour comparer deux hypothèses de marge");
      }
    } catch { toast.error("Comparatif des variantes indisponible"); }
  };

  const [globalMargin, setGlobalMargin] = useState("");
  const applyGlobalMargin = async () => {
    const pct = Number(globalMargin);
    if (Number.isNaN(pct)) { toast.error("Indiquez un coefficient"); return; }
    try {
      const { data } = await api.patch(`/pro/dpgf/${res.file_id}/global-margin`, { margin_pct: pct });
      setRes(data);
      if (variants) loadVariants();
      toast.success(`Coefficient ${pct}% appliqué à toute la variante`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Coefficient non appliqué"); }
  };

  const toQuote = async () => {
    try {
      const { data } = await api.post(`/pro/dpgf/${res.file_id}/quote`, {
        vat_rate: Number(vat), full_descriptions: fullDesc,
      });
      toast.success(`Devis créé — ${data.lines} lignes`
        + (data.remembered_prices ? ` · ${data.remembered_prices} prix mémorisés` : ""));
      loadHistory();
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Conversion impossible"); }
  };

  const grouped = (res?.lines || []).reduce((acc, l) => {
    (acc[l.lot] = acc[l.lot] || []).push(l);
    return acc;
  }, {});
  const lotTotal = (lot) => (res?.lots || []).find((x) => x.lot === lot)?.total_ht || 0;
  const lotInfo = (lot) => (res?.lots || []).find((x) => x.lot === lot) || {};
  const lowMarginLots = Number(minMargin) > 0
    ? (res?.lots || []).filter((l) => l.total_ht > 0 && Number(l.margin_pct) < Number(minMargin))
    : [];

  return (
    <div className="surface p-6" data-testid="dpgf-import">
      <div className="flex items-center gap-2 mb-1">
        <FileSpreadsheet className="h-5 w-5 text-primary" />
        <h3 className="font-display font-bold text-lg">DPGF / BPU architecte → devis</h3>
        <span className="ml-2 text-[10px] font-bold uppercase tracking-wider bg-primary/10 text-primary px-2 py-0.5 rounded-full">Pro Business</span>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Importez le bordereau Excel : les lots sont détectés, les prix viennent de
        <span className="text-foreground"> votre bibliothèque</span> puis de l'IA, le CCTP et vos consignes
        sont appliqués — puis tout passe en devis. Plusieurs bordereaux et plusieurs CCTP peuvent être joints.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="grid gap-1.5">
          <label className="text-xs text-muted-foreground">Bordereaux (.xlsx — plusieurs possibles)</label>
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm" multiple hidden data-testid="dpgf-file-input"
                 onChange={(e) => setFiles((p) => [...p, ...Array.from(e.target.files || [])])} />
          <Button variant="outline" className="rounded-sm justify-start gap-2" onClick={() => fileRef.current?.click()} data-testid="dpgf-pick-file">
            <FileSpreadsheet className="h-4 w-4" /> {files.length ? `${files.length} bordereau(x) — ajouter` : "Choisir les fichiers DPGF"}
          </Button>
          <FileChips items={files} onRemove={(i) => setFiles(files.filter((_, x) => x !== i))} testid="dpgf-file-chip" />
        </div>
        <div className="grid gap-1.5">
          <label className="text-xs text-muted-foreground">CCTP & pièces écrites (.pdf / .docx — plusieurs possibles)</label>
          <input ref={cctpRef} type="file" accept=".pdf,.docx,.txt" multiple hidden data-testid="dpgf-cctp-input"
                 onChange={(e) => setCctps((p) => [...p, ...Array.from(e.target.files || [])])} />
          <Button variant="outline" className="rounded-sm justify-start gap-2" onClick={() => cctpRef.current?.click()} data-testid="dpgf-pick-cctp">
            <FileText className="h-4 w-4" /> {cctps.length ? `${cctps.length} document(s) — ajouter` : "Joindre les CCTP"}
          </Button>
          <FileChips items={cctps} onRemove={(i) => setCctps(cctps.filter((_, x) => x !== i))} testid="dpgf-cctp-chip" />
          {cctps.some((f) => f.size > 10 * 1024 * 1024) ? (
            <p className="text-[11px] text-amber-600" data-testid="dpgf-heavy-doc-warning">
              Un document dépasse 10 Mo : un DCE complet contient surtout des plans. Seules les
              60 premières pages de texte sont lues — joignez plutôt les CCTP par lot pour une
              analyse complète et plus rapide.
            </p>
          ) : null}
        </div>
      </div>

      <div className="grid gap-1.5 mt-3">
        <label className="text-xs text-muted-foreground">Nom du chiffrage</label>
        <Input value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder="Ex. Houilles — Lot 2 variante A" className="rounded-sm h-9"
          data-testid="dpgf-label" />
      </div>

      <div className="grid gap-1.5 mt-3">
        <label className="text-xs text-muted-foreground">Vos consignes (langage naturel)</label>
        <Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={2}
          placeholder="Ex. ne chiffre pas le carrelage ni le parquet · marge 12 % · peinture Dulux · placo hydrofuge en salle de bain"
          className="rounded-sm" data-testid="dpgf-instructions" />
      </div>

      <div className="flex flex-wrap items-center gap-5 mt-3">
        <div className="flex items-center gap-2">
          <Percent className="h-4 w-4 text-muted-foreground" />
          <Input type="number" min={-20} max={100} value={margin} onChange={(e) => setMargin(e.target.value)}
            className="rounded-sm h-9 w-20 num" data-testid="dpgf-margin" />
          <span className="text-xs text-muted-foreground">coefficient global</span>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={analyseCctp} onCheckedChange={setAnalyseCctp} data-testid="dpgf-analyse-cctp" /> Analyser le CCTP par IA
        </label>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={marketCompare} onCheckedChange={setMarketCompare} data-testid="dpgf-market-compare" /> Comparer prix marché (IA)
        </label>
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-muted-foreground" />
          <Input type="number" min={0} max={90} defaultValue={minMargin} key={`mm-${minMargin}`}
            onBlur={(e) => saveMinMargin(e.target.value)}
            className="rounded-sm h-9 w-20 num" data-testid="dpgf-min-margin" />
          <span className="text-xs text-muted-foreground">marge mini (alerte)</span>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={emailNotify} onCheckedChange={saveEmailNotify} data-testid="dpgf-email-notify" />
          <Mail className="h-3.5 w-3.5" /> E-mail si gros chiffrage
        </label>
        <Button onClick={run} disabled={busy} className="gap-2 rounded-sm ml-auto" data-testid="dpgf-upload-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {busy ? "Chiffrage en cours…" : "Chiffrer le bordereau"}
        </Button>
      </div>

      {progress && (
        <div className="mt-4 rounded-sm border border-border bg-muted/40 p-3" data-testid="dpgf-progress">
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span data-testid="dpgf-progress-step">{STEP_LABEL[progress.step] || "Chiffrage en cours…"}</span>
            {progress.step === "cctp_read" && progress.sub_total ? (
              <span className="text-xs text-muted-foreground" data-testid="dpgf-progress-pages">
                page {progress.sub_done}/{progress.sub_total} — {progress.sub_doc}
              </span>
            ) : null}
            {progress.step === "pricing" && progress.total ? (
              <span className="text-xs text-muted-foreground num" data-testid="dpgf-progress-count">
                {progress.done}/{progress.total} lignes
              </span>
            ) : null}
          </div>
          {progress.step === "pricing" && progress.total ? (
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-border">
              <div className="h-full bg-primary transition-all"
                style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }} />
            </div>
          ) : null}
          <p className="mt-2 text-[11px] text-muted-foreground">
            Le chiffrage se poursuit sur le serveur : vous pouvez fermer cette page, vous serez
            prévenu dans la cloche de notifications dès qu'il est terminé.
          </p>
        </div>
      )}

      {res && (
        <div className="mt-5 space-y-4" data-testid="dpgf-result">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <b data-testid="dpgf-study-label">{res.label || res.filename}</b>
            <button onClick={() => renameStudy(res.file_id, res.label)} title="Renommer ce chiffrage"
              className="text-muted-foreground hover:text-primary" data-testid="dpgf-rename-btn">
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <Button size="sm" variant="outline" className="h-7 rounded-sm text-[11px] gap-1 ml-auto"
              onClick={() => duplicateStudy(res.file_id, res.label || res.filename)}
              data-testid="dpgf-duplicate-btn">
              <Copy className="h-3 w-3" /> Dupliquer en variante
            </Button>
            <Button size="sm" variant="outline" className="h-7 rounded-sm text-[11px] gap-1"
              onClick={loadVariants} data-testid="dpgf-variants-btn">
              <Layers className="h-3 w-3" /> Comparer les variantes
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-sm border border-dashed border-border bg-muted/30 px-3 py-2 text-xs" data-testid="dpgf-global-margin">
            <Percent className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Coefficient sur toute la variante :</span>
            <Input type="number" min={-50} max={200} value={globalMargin}
              onChange={(e) => setGlobalMargin(e.target.value)}
              placeholder="ex. 15" className="rounded-sm h-7 w-20 num" data-testid="dpgf-global-margin-input" />
            <span className="text-muted-foreground">%</span>
            <Button size="sm" className="h-7 rounded-sm text-[11px]" onClick={applyGlobalMargin}
              data-testid="dpgf-global-margin-apply">Appliquer à tous les lots</Button>
            <span className="text-muted-foreground">remplace les coefficients par lot en un clic</span>
          </div>

          {variants?.variants?.length > 0 && (
            <div className="rounded-sm border border-border overflow-hidden" data-testid="dpgf-variants">
              <div className="flex items-center justify-between bg-secondary/40 px-3 py-2">
                <p className="text-xs font-semibold uppercase tracking-wide flex items-center gap-1.5">
                  <Layers className="h-3.5 w-3.5" /> Variantes — {variants.variants.length} hypothèse(s) de marge
                </p>
                <button onClick={() => setVariants(null)} className="text-muted-foreground hover:text-foreground"
                  data-testid="dpgf-variants-close"><X className="h-3.5 w-3.5" /></button>
              </div>
              <div className="overflow-auto">
                <table className="w-full text-xs">
                  <thead className="bg-secondary/20">
                    <tr>
                      <th className="text-left p-2">Lot</th>
                      {variants.variants.map((v) => (
                        <th key={v.file_id} className="p-2 text-right min-w-[130px]">
                          <button className={`underline decoration-dotted ${v.current ? "text-primary font-bold" : "hover:text-primary"}`}
                            onClick={() => loadStudy(v.file_id)} data-testid={`dpgf-variant-open-${v.file_id}`}>
                            {v.label}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {variants.lots.map((lot) => (
                      <tr key={lot} className="border-t border-border/60">
                        <td className="p-2">{lot}</td>
                        {variants.variants.map((v) => {
                          const cell = v.lots[lot];
                          return (
                            <td key={v.file_id} className="p-2 text-right num" data-testid={`dpgf-variant-lot-${v.file_id}-${lot}`}>
                              {cell ? (
                                <>
                                  <span className="font-semibold">{eur(cell.total_ht)}</span>
                                  <span className="block text-[10px] text-muted-foreground">marge {cell.margin_pct}%</span>
                                </>
                              ) : <span className="text-muted-foreground">—</span>}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                    <tr className="border-t-2 border-border bg-secondary/30">
                      <td className="p-2 font-bold">Total HT</td>
                      {variants.variants.map((v) => (
                        <td key={v.file_id} className="p-2 text-right num font-bold" data-testid={`dpgf-variant-total-${v.file_id}`}>
                          {eur(v.grand_total_ht)}
                          <span className="block text-[10px] font-normal text-emerald-600">
                            marge {v.margin_pct}% ({eur(v.margin_ht)})
                          </span>
                        </td>
                      ))}
                    </tr>
                    {(() => {
                      const ref = variants.variants.find((v) => v.current) || variants.variants[0];
                      return (
                        <tr className="border-t border-border/60" data-testid="dpgf-variant-ecart-row">
                          <td className="p-2 text-muted-foreground">Écart vs « {ref.label} »</td>
                          {variants.variants.map((v) => {
                            const d = Math.round((v.grand_total_ht - ref.grand_total_ht) * 100) / 100;
                            const pct = ref.grand_total_ht ? (d / ref.grand_total_ht) * 100 : 0;
                            const cls = d === 0 ? "text-muted-foreground" : d > 0 ? "text-emerald-600" : "text-red-500";
                            return (
                              <td key={v.file_id} className={`p-2 text-right num font-semibold ${cls}`}
                                data-testid={`dpgf-variant-ecart-${v.file_id}`}>
                                {v.current ? <span className="text-muted-foreground font-normal">référence</span>
                                  : <>{d > 0 ? "+" : ""}{eur(d)}<span className="block text-[10px] font-normal">{pct > 0 ? "+" : ""}{pct.toFixed(1)} %</span></>}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })()}
                  </tbody>
                </table>
              </div>
              <p className="px-3 py-2 text-[11px] text-muted-foreground">
                Dupliquez l'étude, ajustez le coefficient d'un lot sur la copie, puis lisez ici l'écart de total et de marge entre vos hypothèses.
              </p>
            </div>
          )}

          {lowMarginLots.length > 0 && (
            <div className="rounded-sm border border-red-500/40 bg-red-500/5 p-3 text-xs" data-testid="dpgf-margin-alert">
              <p className="font-semibold text-red-600 flex items-center gap-1.5">
                <ShieldAlert className="h-3.5 w-3.5" /> Marge sous votre minimum de {minMargin}%
              </p>
              <ul className="mt-1 space-y-0.5">
                {lowMarginLots.map((l) => (
                  <li key={l.lot} data-testid={`dpgf-margin-alert-${l.lot}`}>
                    {l.lot} — marge {l.margin_pct}% ({eur(l.margin_ht)} sur {eur(l.total_ht)})
                  </li>
                ))}
              </ul>
              <p className="text-muted-foreground mt-1">
                Augmentez le coefficient du lot ou négociez le prix d'achat pour repasser au-dessus.
              </p>
            </div>
          )}
          <div className="flex flex-wrap gap-4 text-sm">
            <span>Lignes : <b>{res.line_count}</b></span>
            <span className="text-primary inline-flex items-center gap-1"><Sparkles className="h-3.5 w-3.5" /> Chiffrées : <b>{res.priced}</b></span>
            {res.from_library > 0 && <span className="text-emerald-600">Vos prix : <b>{res.from_library}</b></span>}
            {res.from_ai > 0 && <span className="text-amber-600">IA : <b>{res.from_ai}</b></span>}
            {res.excluded > 0 && <span className="text-muted-foreground">Non chiffrées : <b>{res.excluded}</b></span>}
            {res.dedup_count > 0 && <span className="text-orange-600" data-testid="dpgf-dedup-count">Doublons ignorés : <b>{res.dedup_count}</b></span>}
            <span className="ml-auto">Total HT : <b data-testid="dpgf-grand-total">{eur(res.grand_total_ht)}</b></span>
          </div>

          {(res.directives?.exclude_keywords?.length > 0 || Number(res.directives?.margin_pct) > 0) && (
            <div className="rounded-sm border border-border p-3 text-xs space-y-1" data-testid="dpgf-directives">
              {res.directives.exclude_keywords?.length > 0 && (
                <div>Exclusions appliquées : {res.directives.exclude_keywords.map((k) => (
                  <span key={k} className="inline-block rounded-sm border border-border px-1.5 py-0.5 mr-1">{k}</span>))}</div>
              )}
              {!!res.directives.margin_pct && <p>Coefficient global : <b>{res.directives.margin_pct}%</b></p>}
              {res.directives.notes?.length > 0 && <p className="text-muted-foreground">Consignes techniques : {res.directives.notes.join(" · ")}</p>}
            </div>
          )}

          {res.cctp?.summary && (
            <div className="rounded-sm border border-primary/30 bg-primary/5 p-3 text-xs" data-testid="dpgf-cctp-summary">
              <p className="font-semibold mb-1 inline-flex items-center gap-1"><BookOpen className="h-3.5 w-3.5" /> CCTP — {res.cctp.filename}</p>
              <p>{res.cctp.summary}</p>
              <p className="text-muted-foreground mt-1">{res.cctp.prescriptions?.length || 0} prescription(s) rattachée(s) aux lignes.</p>
              {res.cctp.documents?.some((d) => d.plans_skipped > 0) ? (
                <p className="text-muted-foreground mt-1" data-testid="dpgf-cctp-plans">
                  {res.cctp.documents.reduce((s, d) => s + (d.plans_skipped || 0), 0)} page(s) de
                  plans ignorée(s) automatiquement : seules les pièces écrites sont analysées.
                </p>
              ) : null}
              {res.cctp.documents?.some((d) => d.truncated) ? (
                <p className="text-amber-600 mt-1" data-testid="dpgf-cctp-truncated">
                  Lecture partielle : {res.cctp.documents.filter((d) => d.truncated)
                    .map((d) => `${d.filename} (${d.pages_read}/${d.pages} pages)`).join(", ")} —
                  ces fichiers sont surtout des plans. Joignez le CCTP du lot pour une analyse complète.
                </p>
              ) : null}
            </div>
          )}

          {res.gaps?.filter((g) => !g.added).length > 0 && (
            <div className="rounded-sm border border-amber-500/40 bg-amber-500/5 p-3 space-y-2" data-testid="dpgf-gaps">
              <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">
                Oublis détectés — exigés au CCTP, absents du bordereau
              </p>
              {res.gaps.filter((g) => !g.added).map((g) => (
                <div key={g.gap_id} className="flex flex-wrap items-center gap-2 text-xs" data-testid={`dpgf-gap-${g.gap_id}`}>
                  <span className="flex-1 min-w-[240px]">
                    <b>{g.designation}</b> ({g.unit}){g.lot ? ` · ${g.lot}` : ""}
                    {g.reason && <span className="block text-muted-foreground">{g.reason}</span>}
                  </span>
                  <Input type="number" min={0} placeholder="Qté" value={gapQty[g.gap_id] ?? ""}
                    onChange={(e) => setGapQty({ ...gapQty, [g.gap_id]: e.target.value })}
                    className="rounded-sm h-8 w-20 num" data-testid={`dpgf-gap-qty-${g.gap_id}`} />
                  <Button size="sm" className="rounded-sm h-8" onClick={() => addGap(g)} data-testid={`dpgf-gap-add-${g.gap_id}`}>
                    Ajouter
                  </Button>
                  <Button size="sm" variant="ghost" className="rounded-sm h-8" onClick={() => ignoreGap(g)} data-testid={`dpgf-gap-ignore-${g.gap_id}`}>
                    Ignorer
                  </Button>
                </div>
              ))}
            </div>
          )}

          {rfqs.length > 0 && (
            <div className="rounded-sm border border-border p-3 space-y-2" data-testid="dpgf-rfq-list">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide">Demandes de prix envoyées</p>
                <Button size="sm" variant="outline" className="h-7 rounded-sm text-[11px] gap-1"
                  onClick={loadCompare} data-testid="dpgf-compare-btn">
                  <Scale className="h-3 w-3" /> Comparer les offres
                </Button>
              </div>
              {rfqs.map((r) => (
                <div key={r.rfq_id} className="text-xs space-y-1" data-testid={`dpgf-rfq-${r.rfq_id}`}>
                  <p className="font-semibold">{r.lot} — réponse avant le {r.due_date}</p>
                  {r.recipients.map((d) => (
                    <div key={d.token} className="flex flex-wrap items-center gap-2 pl-2">
                      <span className="flex-1 min-w-[200px]">
                        {d.name || d.email}
                        {d.email_status === "failed" && <span className="text-red-500"> · e-mail non envoyé</span>}
                      </span>
                      {d.responded_at ? (
                        <>
                          <span className="num font-semibold text-primary">{eur(d.total_ht)} HT</span>
                          <Button size="sm" variant="outline" className="rounded-sm h-7"
                            onClick={() => applyOffer(r, d.token)} data-testid={`dpgf-offer-apply-${d.token}`}>
                            Retenir
                          </Button>
                        </>
                      ) : (
                        <span className="text-muted-foreground">en attente ·{" "}
                          <button className="underline" onClick={() => { navigator.clipboard?.writeText(d.link || ""); toast.success("Lien copié"); }}
                            data-testid={`dpgf-offer-link-${d.token}`}>copier le lien</button>
                        </span>
                      )}
                      {d.note && <span className="text-muted-foreground w-full pl-2">« {d.note} »</span>}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {compare?.lots?.length > 0 && (
            <div className="rounded-sm border border-border overflow-hidden" data-testid="dpgf-compare">
              <table className="w-full text-xs">
                <thead className="bg-secondary/40">
                  <tr><th className="text-left p-2">Lot / offre</th><th className="p-2 text-right">Mon prix HT</th>
                    <th className="p-2 text-right">Offre HT</th><th className="p-2 text-right">Écart</th>
                    <th className="p-2" /></tr>
                </thead>
                <tbody>
                  {compare.lots.map((l) => (
                    <Fragment key={l.lot}>
                      <tr className="bg-secondary/30 border-t border-border">
                        <td className="p-2 font-bold">{l.lot}
                          <span className="ml-2 font-normal text-muted-foreground">
                            {l.answered}/{l.requested} réponse(s)
                          </span>
                        </td>
                        <td className="p-2 text-right num font-bold">{eur(l.my_lot_total_ht)}</td>
                        <td className="p-2 text-right num">{l.best ? eur(l.best.total_ht) : "—"}</td>
                        <td className="p-2 text-right num">
                          {l.saving_ht > 0 && <span className="text-emerald-600">-{eur(l.saving_ht)}</span>}
                        </td>
                        <td />
                      </tr>
                      {l.offers.map((o, i) => (
                        <tr key={o.token} className="border-t border-border/60" data-testid={`dpgf-compare-offer-${o.token}`}>
                          <td className="p-2 pl-6">
                            {i === 0 && <span className="text-[10px] font-bold uppercase text-emerald-600 mr-1">Moins cher</span>}
                            {o.name}
                            {o.note && <span className="block text-muted-foreground">« {o.note} »</span>}
                          </td>
                          <td className="p-2 text-right num text-muted-foreground">{eur(o.my_total_ht)}</td>
                          <td className="p-2 text-right num">{eur(o.total_ht)}</td>
                          <td className={`p-2 text-right num font-semibold ${o.delta_pct === null ? "" : o.delta_pct <= 0 ? "text-emerald-600" : "text-red-500"}`}>
                            {o.delta_pct === null ? "—" : `${o.delta_pct > 0 ? "+" : ""}${o.delta_pct} %`}
                          </td>
                          <td className="p-2 text-center">
                            <Button size="sm" variant="outline" className="h-6 rounded-sm text-[10px]"
                              onClick={() => applyOffer({ rfq_id: o.rfq_id }, o.token)}
                              data-testid={`dpgf-compare-apply-${o.token}`}>Retenir</Button>
                          </td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="max-h-[520px] overflow-auto rounded-sm border border-border">
            <table className="w-full text-xs">
              <thead className="bg-secondary/40 sticky top-0">
                <tr>
                  <th className="text-left p-2">Désignation</th>
                  <th className="p-2">Qté</th><th className="p-2">U.</th>
                  <th className="p-2 text-right">Votre prix</th>
                  <th className="p-2 text-right">Prix marché</th>
                  <th className="p-2 text-right">PU retenu</th>
                  <th className="p-2 text-right">Total HT</th>
                  <th className="p-2" />
                </tr>
              </thead>
              <tbody>
                {Object.entries(grouped).map(([lot, items]) => (
                  <Fragment key={lot}>
                    <tr className="bg-secondary/30 border-t border-border">
                      <td className="p-2 font-bold" colSpan={4}>{lot}
                        {lotInfo(lot).total_ht > 0 && (
                          <span className={`ml-2 text-[10px] font-bold uppercase ${Number(minMargin) > 0 && Number(lotInfo(lot).margin_pct) < Number(minMargin) ? "text-red-500" : "text-muted-foreground"}`}
                            data-testid={`dpgf-lot-margin-real-${lot}`}>
                            marge {lotInfo(lot).margin_pct}%
                          </span>
                        )}
                      </td>
                      <td className="p-2 text-right">
                        <span className="inline-flex items-center gap-1">
                          <Input type="number" min={-20} max={100} title="Coefficient du lot"
                            defaultValue={(res.directives?.lot_margins || {})[lot] ?? res.directives?.margin_pct ?? 0}
                            key={`${lot}-${(res.directives?.lot_margins || {})[lot] ?? ""}`}
                            onBlur={(e) => setLotMargin(lot, e.target.value)}
                            className="rounded-sm h-6 w-14 num text-right text-[11px]"
                            data-testid={`dpgf-lot-margin-${lot}`} />
                          <span className="text-[10px] text-muted-foreground">% marge</span>
                        </span>
                      </td>
                      <td className="p-2 text-right">
                        <Button size="sm" variant="ghost" className="h-6 rounded-sm text-[10px] gap-1"
                          onClick={() => openRfq(lot)} data-testid={`dpgf-rfq-btn-${lot}`}>
                          <Users className="h-3 w-3" /> Demander un prix
                        </Button>
                      </td>
                      <td className="p-2 text-right font-bold num">{eur(lotTotal(lot))}</td>
                      <td />
                    </tr>
                    {items.map((l) => (
                      <tr key={l.line_id} className={`border-t border-border/60 ${l.excluded ? "opacity-60" : ""}`} data-testid={`dpgf-line-${l.line_id}`}>
                        <td className="p-2">
                          {l.designation}
                          {(res.sources || []).length > 1 && (
                            <span className="ml-1 text-[10px] text-muted-foreground">[{l.src_name}]</span>
                          )}
                          {l.excluded && <span className="ml-1 text-[10px] font-bold uppercase text-muted-foreground">· {l.exclusion_reason || "Non chiffré — hors marché"}</span>}
                          {l.cctp_note && <span className="block text-[10px] text-primary mt-0.5">CCTP : {l.cctp_note}</span>}
                        </td>
                        <td className="p-2 text-center num">{l.qty ?? "—"}</td>
                        <td className="p-2 text-center">{l.unit || "—"}</td>
                        <td className="p-2 text-right num">
                          {l.pu_library ? (
                            <button className="hover:text-emerald-600 underline decoration-dotted"
                              onClick={() => patchLine(l.line_id, { source: "bibliotheque" })}
                              data-testid={`dpgf-use-lib-${l.line_id}`}>{eur(l.pu_library)}</button>
                          ) : "—"}
                        </td>
                        <td className="p-2 text-right num">
                          {l.pu_ai ? (
                            <button className="hover:text-amber-600 underline decoration-dotted"
                              onClick={() => patchLine(l.line_id, { source: "ia" })}
                              data-testid={`dpgf-use-ai-${l.line_id}`}>{eur(l.pu_ai)}</button>
                          ) : "—"}
                        </td>
                        <td className="p-2 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Input type="number" min={0} defaultValue={l.pu ?? ""} key={`${l.line_id}-${l.pu}`}
                              onBlur={(e) => { const v = Number(e.target.value); if (v > 0 && v !== l.pu) patchLine(l.line_id, { pu: v }); }}
                              className="rounded-sm h-7 w-20 num text-right" data-testid={`dpgf-pu-${l.line_id}`} />
                            <SourceTag s={l.source} />
                          </div>
                        </td>
                        <td className="p-2 text-right num">{l.total ? eur(l.total) : "—"}</td>
                        <td className="p-2 text-center">
                          <button title={l.excluded ? "Réintégrer au chiffrage" : "Ne pas chiffrer"}
                            className={`p-1 rounded-sm ${l.excluded ? "text-emerald-600" : "text-muted-foreground hover:text-red-500"}`}
                            onClick={() => patchLine(l.line_id, { excluded: !l.excluded })}
                            data-testid={`dpgf-toggle-${l.line_id}`}>
                            {l.excluded ? <Check className="h-3.5 w-3.5" /> : <Ban className="h-3.5 w-3.5" />}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" onClick={download} className="gap-2 rounded-sm" data-testid="dpgf-download-btn">
              <Download className="h-4 w-4" /> {(res.sources || []).length > 1 ? "Excels chiffrés (ZIP)" : "Excel chiffré"}
            </Button>
            <Button variant="outline" onClick={rememberPrices} className="gap-2 rounded-sm"
              data-testid="dpgf-remember-btn">
              <BookOpen className="h-4 w-4" /> Enregistrer les prix en bibliothèque
            </Button>
            <div className="flex items-center gap-1" data-testid="dpgf-vat-choice">
              {VATS.map((v) => (
                <button key={v} onClick={() => setVat(v)} data-testid={`dpgf-vat-${v}`}
                  className={`rounded-sm border px-2 py-1 text-xs transition-colors ${vat === v ? "border-primary bg-primary/10 text-primary" : "border-border hover:border-primary/40"}`}>
                  TVA {String(v).replace(".", ",")} %
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch checked={fullDesc} onCheckedChange={setFullDesc} data-testid="dpgf-full-desc" /> Descriptifs complets
            </label>
            <Button onClick={toQuote} className="gap-2 rounded-sm ml-auto" data-testid="dpgf-to-quote-btn">
              <Wand2 className="h-4 w-4" /> Passer en devis
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            « Votre prix » = bibliothèque de l'entreprise · « IA » = estimation marché à valider ·
            cliquez sur un prix pour le retenir, saisissez un PU pour l'imposer, ou barrez une ligne pour la sortir du marché.
          </p>
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-6 border-t border-border pt-4" data-testid="dpgf-history">
          <p className="text-xs font-semibold uppercase tracking-wide flex items-center gap-1.5 mb-2">
            <History className="h-3.5 w-3.5" /> Mes chiffrages DPGF
          </p>
          <div className="space-y-1.5">
            {history.slice(0, 8).map((h) => (
              <div key={h.file_id} className="flex flex-wrap items-center gap-2 text-xs" data-testid={`dpgf-hist-${h.file_id}`}>
                <span className="flex-1 min-w-[220px] truncate">
                  {h.label || h.filename || "Bordereau"} · {h.line_count} ligne(s) · <b>{eur(h.grand_total_ht)}</b> HT
                  <span className="text-muted-foreground"> — {(h.created_at || "").slice(0, 10)}</span>
                </span>
                <Button size="sm" variant="ghost" className="rounded-sm h-7" title="Renommer"
                  onClick={() => renameStudy(h.file_id, h.label)} data-testid={`dpgf-hist-rename-${h.file_id}`}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" className="rounded-sm h-7" title="Dupliquer en variante"
                  onClick={() => duplicateStudy(h.file_id, h.label || h.filename)} data-testid={`dpgf-hist-duplicate-${h.file_id}`}>
                  <Copy className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="outline" className="rounded-sm h-7" onClick={() => loadStudy(h.file_id)}
                  data-testid={`dpgf-hist-open-${h.file_id}`}>Rouvrir</Button>
                {h.quote_doc_id && (
                  <Button size="sm" variant="ghost" className="rounded-sm h-7" onClick={() => nav(`/devis-editeur/${h.quote_doc_id}`)}
                    data-testid={`dpgf-hist-quote-${h.file_id}`}>Devis lié</Button>
                )}
                <Button size="sm" variant="ghost" className="rounded-sm h-7 text-muted-foreground hover:text-red-500"
                  title="Supprimer ce chiffrage" onClick={() => removeStudy(h)}
                  data-testid={`dpgf-hist-delete-${h.file_id}`}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      <Dialog open={!!rfqLot} onOpenChange={(o) => !o && setRfqLot(null)}>
        <DialogContent className="max-w-lg" data-testid="dpgf-rfq-modal">
          <DialogHeader>
            <DialogTitle>Demander un prix — {rfqLot}</DialogTitle>
            <DialogDescription>
              Les destinataires saisissent leurs prix en ligne, sans compte. Vous comparez puis retenez l'offre.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div>
              <p className="overline mb-1">Mes sous-traitants / fournisseurs</p>
              {suppliers.filter((s) => s.email).length === 0 ? (
                <p className="text-xs text-muted-foreground">Aucune fiche avec e-mail — utilisez le champ ci-dessous.</p>
              ) : (
                <div className="max-h-40 overflow-auto space-y-1">
                  {suppliers.filter((s) => s.email).map((s) => (
                    <label key={s.supplier_id} className="flex items-center gap-2 text-xs cursor-pointer">
                      <input type="checkbox" className="accent-primary" checked={rfqPick.includes(s.supplier_id)}
                        onChange={(e) => setRfqPick(e.target.checked
                          ? [...rfqPick, s.supplier_id]
                          : rfqPick.filter((x) => x !== s.supplier_id))}
                        data-testid={`dpgf-rfq-supplier-${s.supplier_id}`} />
                      {s.name} <span className="text-muted-foreground">{s.email}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
            <label className="grid gap-1.5 text-xs text-muted-foreground">Autres e-mails (séparés par une virgule)
              <Input value={rfqEmail} onChange={(e) => setRfqEmail(e.target.value)} className="rounded-sm h-9"
                placeholder="plombier@exemple.fr, carreleur@exemple.fr" data-testid="dpgf-rfq-emails" />
            </label>
            <label className="grid gap-1.5 text-xs text-muted-foreground">Message (facultatif)
              <Textarea value={rfqMsg} onChange={(e) => setRfqMsg(e.target.value)} rows={2} className="rounded-sm"
                placeholder="Délai souhaité, contraintes d'accès, planning…" data-testid="dpgf-rfq-message" />
            </label>
          </div>
          <DialogFooter>
            <Button variant="ghost" className="rounded-sm" onClick={() => setRfqLot(null)} data-testid="dpgf-rfq-cancel">Annuler</Button>
            <Button className="rounded-sm gap-2" onClick={sendRfq} data-testid="dpgf-rfq-send">
              <Users className="h-4 w-4" /> Envoyer la demande
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
