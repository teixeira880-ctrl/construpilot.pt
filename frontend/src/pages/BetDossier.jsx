import { useCallback, useEffect, useRef, useState } from "react";
import { api, API } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { toast } from "sonner";
import StructureAutopilotPanel from "./StructureAutopilotPanel";
import {
  Building2, Plus, Trash2, ArrowLeft, Upload, FileDown, Loader2, FileText, Image as ImageIcon,
  GitCompareArrows, ShieldAlert, FileSearch, AlertTriangle, RefreshCw, Eye, Boxes,
} from "lucide-react";

const KIND_LABEL = { bet: "Note BET", plan: "Plan", cctp: "CCTP", autre: "Autre" };
const ENGINE = {
  claude: { label: "Analysé", cls: "bg-emerald-500/15 text-emerald-600" },
  skipped: { label: "Non lisible (DWG/IFC)", cls: "bg-slate-500/15 text-slate-600" },
  error: { label: "Échec lecture", cls: "bg-red-500/15 text-red-600" },
  fallback: { label: "Partiel", cls: "bg-amber-500/15 text-amber-700" },
};

const DISCLAIMER =
  "Contrôle en lecture seule : StructuroPilot ne calcule rien et ne décide pas quelle valeur est correcte. Il rapporte ce qui est écrit et signale les écarts à faire vérifier par un ingénieur. Jamais « bon pour exécution ».";

function EngineBadge({ e }) {
  const cfg = ENGINE[e] || { label: "En attente", cls: "bg-slate-500/15 text-slate-600" };
  return <Badge className={`rounded-sm border-0 ${cfg.cls}`} data-testid="doc-engine-badge">{cfg.label}</Badge>;
}

export default function BetDossier() {
  const [list, setList] = useState([]);
  const [current, setCurrent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [cmp, setCmp] = useState({ a: "", b: "" });
  const [resp, setResp] = useState("");
  const fileRef = useRef(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get("/structuro/bet/studies"); setList(data.studies || []); }
    catch { toast.error("Chargement impossible."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { loadList(); }, [loadList]);

  const openDossier = async (id) => {
    setBusy(true);
    try { const { data } = await api.get(`/structuro/bet/studies/${id}`); setCurrent(data); setCmp({ a: "", b: "" }); setResp(data.responsable || ""); }
    catch { toast.error("Dossier introuvable."); }
    finally { setBusy(false); }
  };

  const createDossier = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/structuro/bet/studies", { title: title.trim() });
      setTitle(""); await loadList(); setCurrent(data);
      toast.success("Dossier créé.");
    } catch { toast.error("Création impossible."); }
    finally { setBusy(false); }
  };

  const deleteDossier = async (id) => {
    if (!window.confirm("Supprimer ce dossier et ses documents ?")) return;
    try { await api.delete(`/structuro/bet/studies/${id}`); setCurrent(null); await loadList(); toast.success("Dossier supprimé."); }
    catch { toast.error("Suppression impossible."); }
  };

  const liveDocs = (current?.documents || []).filter((d) => !d.is_deleted);

  const upload = async (file) => {
    if (!file || !current) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post(`/structuro/bet/studies/${current.dossier_id}/documents`, fd,
        { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 });
      setCurrent(data);
      toast.success("Document importé et lu.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Import impossible."); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const reanalyze = async (docId) => {
    setBusy(true);
    try { const { data } = await api.post(`/structuro/bet/studies/${current.dossier_id}/documents/${docId}/reanalyze`); setCurrent(data); toast.success("Relu."); }
    catch { toast.error("Relecture impossible."); }
    finally { setBusy(false); }
  };

  const analyzeAutodesk = async (docId, filename) => {
    if (!window.confirm(`Lancer la lecture Autodesk de « ${filename} » ?\n\nLa traduction DWG/IFC via Autodesk consomme du crédit (mise en cache ensuite par fichier).`)) return;
    setBusy(true);
    toast.info("Traduction Autodesk en cours… cela peut prendre jusqu'à 1 min.");
    try { const { data } = await api.post(`/structuro/bet/studies/${current.dossier_id}/documents/${docId}/analyze-autodesk`, {}, { timeout: 180000 }); setCurrent(data); toast.success("Lecture Autodesk terminée."); }
    catch (e) { toast.error(e?.response?.data?.detail || "Lecture Autodesk impossible."); }
    finally { setBusy(false); }
  };

  const saveResponsable = async () => {
    setBusy(true);
    try { const { data } = await api.patch(`/structuro/bet/studies/${current.dossier_id}`, { responsable: resp }); setCurrent(data); toast.success("Responsable enregistré."); }
    catch { toast.error("Enregistrement impossible."); }
    finally { setBusy(false); }
  };

  const deleteDoc = async (docId) => {
    setBusy(true);
    try { const { data } = await api.delete(`/structuro/bet/studies/${current.dossier_id}/documents/${docId}`); setCurrent(data); setCmp({ a: "", b: "" }); }
    catch { toast.error("Suppression impossible."); }
    finally { setBusy(false); }
  };

  const runCompare = async () => {
    if (!cmp.a || !cmp.b || cmp.a === cmp.b) { toast.error("Choisissez deux documents différents."); return; }
    setBusy(true);
    try { const { data } = await api.post(`/structuro/bet/studies/${current.dossier_id}/compare`, { doc_a: cmp.a, doc_b: cmp.b }); setCurrent(data); toast.success("Comparaison effectuée."); }
    catch (e) { toast.error(e?.response?.data?.detail || "Comparaison impossible."); }
    finally { setBusy(false); }
  };

  const runInconsistencies = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/structuro/bet/studies/${current.dossier_id}/inconsistencies`); setCurrent(data); toast.success("Analyse terminée."); }
    catch { toast.error("Analyse impossible."); }
    finally { setBusy(false); }
  };

  const nameOf = (id) => liveDocs.find((d) => d.id === id)?.original_filename || id;

  // ---------- List view ----------
  if (!current) {
    return (
      <div className="max-w-5xl mx-auto space-y-6" data-testid="bet-list-page">
        <header className="space-y-2">
          <div className="flex items-center gap-2 text-primary"><FileSearch className="h-5 w-5" /><span className="overline">StructuroPilot</span></div>
          <h1 className="font-display text-2xl font-bold">Analyse de dossier BET</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Importez plans et notes de calcul d'un bureau d'études en <strong>lecture seule</strong>. L'IA lit les PDF et images,
            compare les versions (indice A → B) et signale les incohérences. Rapport de contrôle PDF à la clé.
          </p>
        </header>

        <Card className="p-4 flex flex-col sm:flex-row gap-3 sm:items-end" data-testid="bet-create-card">
          <div className="flex-1">
            <label className="text-xs font-semibold text-muted-foreground">Nouveau dossier</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex. Maison Dupont — ouverture mur porteur"
              data-testid="bet-title-input" onKeyDown={(e) => e.key === "Enter" && createDossier()} />
          </div>
          <Button onClick={createDossier} disabled={busy} data-testid="bet-create-btn" className="gap-2">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Créer
          </Button>
        </Card>

        {loading ? <div className="flex items-center gap-2 text-muted-foreground p-6"><Loader2 className="h-4 w-4 animate-spin" />Chargement…</div>
          : list.length === 0 ? <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="bet-empty">Aucun dossier pour l'instant.</Card>
          : <div className="grid sm:grid-cols-2 gap-3" data-testid="bet-dossier-grid">
              {list.map((d) => (
                <Card key={d.dossier_id} className="p-4 flex items-center gap-3 hover:border-primary/50 transition-colors" data-testid={`bet-dossier-${d.dossier_id}`}>
                  <span className="h-10 w-10 grid place-items-center rounded-lg bg-primary/10 text-primary shrink-0"><Building2 className="h-5 w-5" /></span>
                  <button className="flex-1 min-w-0 text-left" onClick={() => openDossier(d.dossier_id)} data-testid={`bet-open-${d.dossier_id}`}>
                    <p className="font-semibold truncate">{d.title}</p>
                    <p className="text-xs text-muted-foreground">{d.document_count || 0} document(s)</p>
                  </button>
                  <Button variant="ghost" size="icon" onClick={() => deleteDossier(d.dossier_id)} data-testid={`bet-delete-${d.dossier_id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                </Card>
              ))}
            </div>}
      </div>
    );
  }

  // ---------- Detail view ----------
  const inco = (current.inconsistencies || {}).incoherences || [];
  const comparisons = current.comparisons || [];
  return (
    <div className="max-w-5xl mx-auto space-y-6" data-testid="bet-detail-page">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="sm" onClick={() => { setCurrent(null); loadList(); }} data-testid="bet-back-btn" className="gap-1"><ArrowLeft className="h-4 w-4" /> Dossiers</Button>
          <h1 className="font-display text-xl font-bold truncate">{current.title}</h1>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <div className="flex items-center gap-1.5">
            <Input value={resp} onChange={(e) => setResp(e.target.value)} placeholder="Responsable du contrôle"
              className="h-9 w-48" data-testid="bet-responsable-input" />
            <Button variant="ghost" size="sm" onClick={saveResponsable} disabled={busy || resp === (current.responsable || "")} data-testid="bet-responsable-save">OK</Button>
          </div>
          <Button asChild variant="outline" className="gap-2" data-testid="bet-report-btn">
            <a href={`${API}/structuro/bet/studies/${current.dossier_id}/report.pdf`} target="_blank" rel="noopener noreferrer"><FileDown className="h-4 w-4" /> Rapport de contrôle</a>
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 flex gap-2 text-xs text-amber-700" data-testid="bet-disclaimer">
        <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" /><span>{DISCLAIMER}</span>
      </div>

      <StructureAutopilotPanel dossier={current} onChange={setCurrent} />

      {/* Documents */}
      <Card className="p-4 space-y-4" data-testid="bet-documents-card">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Documents ({liveDocs.length})</h2>
          <div>
            <input ref={fileRef} type="file" className="hidden" data-testid="bet-file-input"
              accept=".pdf,.png,.jpg,.jpeg,.webp,.dwg,.dxf,.ifc" onChange={(e) => upload(e.target.files?.[0])} />
            <Button onClick={() => fileRef.current?.click()} disabled={busy} className="gap-2" data-testid="bet-upload-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Importer
            </Button>
          </div>
        </div>
        {liveDocs.length === 0 ? <p className="text-sm text-muted-foreground py-4 text-center" data-testid="bet-docs-empty">Importez des PDF (notes) ou images (plans). DWG/IFC acceptés (stockés, lecture géométrique non disponible).</p>
          : <div className="space-y-2">
              {liveDocs.map((d) => {
                const ext = (d.extraction || {});
                const isImg = (d.content_type || "").startsWith("image/");
                const fext = (d.original_filename || "").split(".").pop().toLowerCase();
                const isCad = ["dwg", "dxf", "ifc"].includes(fext);
                return (
                  <div key={d.id} className="rounded-lg border border-border p-3" data-testid={`bet-doc-${d.id}`}>
                    <div className="flex items-center gap-3">
                      <span className="h-9 w-9 grid place-items-center rounded-md bg-secondary shrink-0">{isImg ? <ImageIcon className="h-4 w-4" /> : <FileText className="h-4 w-4" />}</span>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate text-sm">{d.original_filename}</p>
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          {d.index && <Badge variant="outline" className="rounded-sm" data-testid={`bet-doc-index-${d.id}`}>Indice {d.index}</Badge>}
                          <Badge variant="outline" className="rounded-sm">{KIND_LABEL[d.kind] || d.kind}</Badge>
                          <EngineBadge e={ext.source_engine} />
                          {ext.autodesk && <Badge variant="outline" className="rounded-sm">Autodesk · {ext.autodesk.objects} obj.</Badge>}
                        </div>
                      </div>
                      {isCad && (
                        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => analyzeAutodesk(d.id, d.original_filename)} disabled={busy} data-testid={`bet-doc-autodesk-${d.id}`}>
                          <Boxes className="h-4 w-4" /> Analyser via Autodesk
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" title="Ouvrir" asChild data-testid={`bet-doc-view-${d.id}`}>
                        <a href={`${API}/structuro/bet/studies/${current.dossier_id}/documents/${d.id}/file`} target="_blank" rel="noopener noreferrer"><Eye className="h-4 w-4" /></a>
                      </Button>
                      {!isCad && <Button variant="ghost" size="icon" title="Relire" onClick={() => reanalyze(d.id)} disabled={busy} data-testid={`bet-doc-reanalyze-${d.id}`}><RefreshCw className="h-4 w-4" /></Button>}
                      <Button variant="ghost" size="icon" title="Supprimer" onClick={() => deleteDoc(d.id)} disabled={busy} data-testid={`bet-doc-delete-${d.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                    </div>
                    {ext.resume && <p className="text-xs text-muted-foreground mt-2 pl-12">{ext.resume}</p>}
                    {(ext.cotes?.length > 0 || ext.charges?.length > 0) && (
                      <div className="mt-2 pl-12 flex flex-wrap gap-1.5">
                        {(ext.cotes || []).slice(0, 6).map((c, i) => <span key={`c${i}`} className="text-[11px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">{c.libelle}: {c.valeur} {c.unite}</span>)}
                        {(ext.charges || []).slice(0, 6).map((c, i) => <span key={`q${i}`} className="text-[11px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600">{c.libelle}: {c.valeur} {c.unite}</span>)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>}
      </Card>

      {/* Compare versions */}
      <Card className="p-4 space-y-3" data-testid="bet-compare-card">
        <h2 className="font-semibold flex items-center gap-2"><GitCompareArrows className="h-4 w-4 text-primary" /> Comparer deux versions</h2>
        <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
          <div className="flex-1">
            <label className="text-xs text-muted-foreground">Version A (ancienne)</label>
            <Select value={cmp.a} onValueChange={(v) => setCmp((s) => ({ ...s, a: v }))}>
              <SelectTrigger data-testid="bet-compare-a"><SelectValue placeholder="Choisir…" /></SelectTrigger>
              <SelectContent>{liveDocs.map((d) => <SelectItem key={d.id} value={d.id}>{d.original_filename}{d.index ? ` (${d.index})` : ""}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="flex-1">
            <label className="text-xs text-muted-foreground">Version B (nouvelle)</label>
            <Select value={cmp.b} onValueChange={(v) => setCmp((s) => ({ ...s, b: v }))}>
              <SelectTrigger data-testid="bet-compare-b"><SelectValue placeholder="Choisir…" /></SelectTrigger>
              <SelectContent>{liveDocs.map((d) => <SelectItem key={d.id} value={d.id}>{d.original_filename}{d.index ? ` (${d.index})` : ""}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <Button onClick={runCompare} disabled={busy} className="gap-2" data-testid="bet-compare-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitCompareArrows className="h-4 w-4" />} Comparer</Button>
        </div>
        {comparisons.map((c) => {
          const r = c.result || {};
          const total = (r.modifications?.length || 0) + (r.ajouts?.length || 0) + (r.suppressions?.length || 0) + (r.conflits_a_verifier?.length || 0);
          return (
            <div key={c.comp_id} className="rounded-lg border border-border p-3 text-sm" data-testid={`bet-comparison-${c.comp_id}`}>
              <p className="font-medium text-xs text-muted-foreground mb-2">{nameOf(c.doc_a)} → {nameOf(c.doc_b)}</p>
              {total === 0 ? <p className="text-xs text-emerald-600">Aucune différence détectée.</p> : <ul className="space-y-1 text-xs">
                {(r.modifications || []).map((m, i) => <li key={`m${i}`}>✏️ <strong>{m.sujet}</strong> : « {m.avant} » → « {m.apres} »</li>)}
                {(r.ajouts || []).map((a, i) => <li key={`a${i}`} className="text-emerald-600">＋ {a}</li>)}
                {(r.suppressions || []).map((s, i) => <li key={`s${i}`} className="text-red-600">－ {s}</li>)}
                {(r.conflits_a_verifier || []).map((cf, i) => <li key={`cf${i}`} className="text-amber-700">⚠ <strong>{cf.sujet}</strong> — {cf.detail}</li>)}
              </ul>}
            </div>
          );
        })}
      </Card>

      {/* Inconsistencies */}
      <Card className="p-4 space-y-3" data-testid="bet-inconsistencies-card">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-amber-600" /> Incohérences entre documents</h2>
          <Button variant="outline" onClick={runInconsistencies} disabled={busy} className="gap-2" data-testid="bet-inconsistencies-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />} Analyser</Button>
        </div>
        {!current.inconsistencies ? <p className="text-xs text-muted-foreground">Lancez l'analyse après avoir importé au moins deux documents lisibles.</p>
          : inco.length === 0 ? <p className="text-xs text-emerald-600" data-testid="bet-inco-none">Aucune incohérence signalée.</p>
          : <div className="space-y-2">{inco.map((it, i) => (
              <div key={i} className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm" data-testid={`bet-inco-${i}`}>
                <p className="font-medium text-amber-700">{it.sujet}</p>
                <div className="mt-1 flex flex-wrap gap-2 text-xs">{(it.valeurs || []).map((v, j) => <span key={j} className="px-1.5 py-0.5 rounded bg-background border border-border">{v.document}: <strong>{v.valeur}</strong></span>)}</div>
                {it.note && <p className="text-xs text-muted-foreground mt-1">{it.note}</p>}
              </div>
            ))}</div>}
      </Card>
    </div>
  );
}
