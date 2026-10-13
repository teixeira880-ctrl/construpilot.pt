import { QuoteEditorMenu } from "@/components/quote/QuoteEditorMenu";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import "@/components/quote/QuoteEditor.css";
import { CadUnitPicker } from "@/components/planTakeoff/CadImportInfo";
import { useEffect, useMemo, useState, useCallback, useRef, Fragment } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, Trash2, Download, Save, BookOpen, Loader2, Search, ArrowLeft, User, Sparkles, Ruler, Video, Send, X,
  Images, Camera, Square, Clock, FileVideo, AlertTriangle, Mic, Music, FileText, Eye, Layers, Paperclip, TrendingUp, Library, Lock,
  MoreHorizontal, Upload, MapPin, CalendarClock, ChevronUp, ChevronDown, GripVertical, ShieldCheck,
  Package, UserCheck, FolderPlus, Folder, Scissors, ImagePlus, Pencil, Columns2, Printer, Copy, LayoutTemplate, GraduationCap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { api, API, uploadPlan } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { VerifiedProBadge } from "@/components/VerifiedProBadge";
import { useI18n } from "@/context/I18nContext";
import { OuvrageComposeDialog } from "@/components/OuvrageComposeDialog";
import { QuoteLineProvenance } from "@/components/assistant/QuoteLineProvenance";
import { useQuoteCopy } from "@/components/assistant/quoteCopy";
import { DocumentVersionNotice } from "@/components/assistant/DocumentVersionNotice";
import { ChantierContextBar, useChantierContext } from "@/components/chantiers/ChantierContextBar";
import { QuoteCheckPanel } from "@/components/quote/QuoteCheckPanel";
import { DictateButton } from "@/components/voice/VoiceButtons";

const UNITS = ["u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L"];
const VAT_RATES = [0, 6, 13, 23]; // Portugal continental (CIVA)
const VAT_RATES_PT = [0, 6, 13, 23];
const STATUSES = [
  ["draft", "crm.st_e_draft"], ["sent", "crm.st_e_sent"], ["signed", "crm.st_e_signed"], ["refused", "crm.st_e_refused"],
];
const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const contentStamp = d => JSON.stringify([d.doc_type, d.client_id, d.lead_id, d.title, d.lines, d.notes, d.payment_terms, d.deposit_pct, d.status, d.signed || false]);
const blankLine = (vat = null, line_kind = "fourniture") => ({
  kind: "line", line_kind, designation: "", description: "", unit: "u", qty: 1, unit_price_ht: 0, discount_pct: 0,
  cost_price_ht: 0, cost_confirmed_zero: false, vat_rate: vat, category: "", components: [], photos: [], _saveToLib: true,
});
const newEntry = (kind, vat = null) => {
  if (kind === "section" || kind === "subsection") return { kind, title: "", collapsed: false };
  if (kind === "text") return { kind, text: "" };
  if (kind === "pagebreak") return { kind };
  return blankLine(vat, kind); // fourniture | main_oeuvre | ouvrage
};

// Inséreur inline : options de blocs à insérer sous chaque ligne du devis.
const BLOCK_OPTIONS = [
  { id: "fourniture", label: "Fornecimento", desc: "Materiais e equipamentos", Icon: Package, badge: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30" },
  { id: "main_oeuvre", label: "Mão de obra", desc: "Tempo de trabalho e prestações", Icon: UserCheck, badge: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30" },
  { id: "ouvrage", label: "Artigo", desc: "Montagem de subelementos", Icon: Layers, badge: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30" },
  { id: "section", label: "Secção", desc: "Título de capítulo principal", Icon: FolderPlus, badge: "bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900 border-slate-700 dark:border-slate-300" },
  { id: "subsection", label: "Subsecção", desc: "Subtítulo e subtotal", Icon: Folder, badge: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-600" },
  { id: "text", label: "Texto livre", desc: "Nota, descrição ou observação", Icon: FileText, badge: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30" },
  { id: "pagebreak", label: "Quebra de página", desc: "Separador de impressão PDF", Icon: Scissors, badge: "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/30" },
];

function LinePhotos({ slug, photos, onChange, size = 56, onZoom }) {
  const list = photos || [];
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  const upload = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    const room = 3 - list.length;
    if (room <= 0) { toast.error("Maximum 3 photos"); return; }
    setBusy(true);
    const added = [];
    for (const f of files.slice(0, room)) {
      try {
        const fd = new FormData(); fd.append("file", f);
        const { data } = await api.post("/document-photos", fd);
        added.push({ photo_id: data.photo_id, storage_path: data.storage_path });
      } catch { toast.error("Falha no envio da fotografia"); }
    }
    setBusy(false);
    if (added.length) { onChange([...list, ...added]); toast.success(added.length > 1 ? `${added.length} fotografias adicionadas` : "Fotografia adicionada"); }
  };
  const remove = async (pid) => {
    onChange(list.filter((p) => p.photo_id !== pid));
    try { await api.delete(`/document-photos/${pid}`); } catch { /* la ligne est déjà retirée côté UI */ }
  };
  const dim = { height: size, width: size };
  return (
    <div className="flex items-center gap-2 flex-wrap" data-testid={`line-photos-${slug}`}>
      {list.map((p) => (
        <div key={p.photo_id} style={dim} className="relative group/ph rounded-sm overflow-hidden border border-border bg-muted">
          <img src={`${API}/document-photos/${p.photo_id}/raw`} alt="Fotografia da linha" loading="lazy"
               onClick={() => onZoom?.(`${API}/document-photos/${p.photo_id}/raw`)}
               className="h-full w-full object-cover cursor-zoom-in" data-testid={`line-photo-img-${slug}-${p.photo_id}`} />
          <button type="button" onClick={() => remove(p.photo_id)} data-testid={`line-photo-del-${slug}-${p.photo_id}`}
            title="Eliminar a fotografia"
            className="absolute top-0.5 right-0.5 grid h-4 w-4 place-items-center rounded-full bg-black/60 text-white opacity-0 group-hover/ph:opacity-100 transition-opacity">
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}
      {list.length < 3 && (
        <button type="button" onClick={() => inputRef.current?.click()} disabled={busy} data-testid={`line-photo-add-${slug}`}
          style={dim}
          className="rounded-sm border border-dashed border-border flex flex-col items-center justify-center text-muted-foreground hover:border-primary hover:text-primary transition-colors disabled:opacity-50">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><ImagePlus className="h-4 w-4" /><span className="text-[9px] mt-0.5">Fotografia</span></>}
        </button>
      )}
      <input ref={inputRef} type="file" accept="image/*" multiple className="hidden" onChange={upload} data-testid={`line-photo-input-${slug}`} />
    </div>
  );
}

function InlineInserter({ index, onInsert }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="group/ins relative flex h-5 items-center justify-center" data-testid={`inline-insert-row-${index}`}>
      <div className={`pointer-events-none absolute inset-x-0 top-1/2 h-px -translate-y-1/2 transition-colors ${open ? "bg-primary/40" : "bg-transparent group-hover/ins:bg-primary/25"}`} />
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" data-testid={`inline-insert-btn-${index}`}
            className={`relative z-10 inline-flex items-center gap-1 rounded-full border border-primary/40 bg-card px-3 py-1 text-xs font-semibold text-primary shadow-sm transition-[opacity,background-color,color] hover:bg-primary hover:text-white ${open ? "opacity-100" : "opacity-0 group-hover/ins:opacity-100 focus-visible:opacity-100"}`}>
            <Plus className="h-3.5 w-3.5" /> Adicionar aqui
          </button>
        </PopoverTrigger>
        <PopoverContent align="center" sideOffset={6} className="w-72 p-1.5" data-testid={`inline-insert-menu-${index}`}>
          <p className="px-2 py-1.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Inserir um bloco</p>
          <div className="grid gap-0.5">
            {BLOCK_OPTIONS.map((o) => (
              <button key={o.id} type="button" onClick={() => { onInsert(o.id, index + 1); setOpen(false); }}
                data-testid={`inline-insert-option-${o.id}-${index}`}
                className="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted">
                <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-md border ${o.badge}`}><o.Icon className="h-4 w-4" /></span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-foreground">{o.label}</span>
                  <span className="block text-xs text-muted-foreground truncate">{o.desc}</span>
                </span>
              </button>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
// Migration douce : un ancien devis (lignes plates avec `category`) devient des sections explicites.
const ensureBlocks = (lines) => {
  const arr = Array.isArray(lines) ? lines : [];
  if (arr.some((l) => l.kind && l.kind !== "line")) {
    return arr.map((l) => ({ ...l, kind: l.kind || "line", line_kind: l.line_kind || (l.kind === "line" || !l.kind ? "fourniture" : "") }));
  }
  const out = [];
  const order = [];
  const groups = {};
  arr.forEach((l) => {
    const cat = (l.category || "").trim() || "__nocat__";
    if (!(cat in groups)) { groups[cat] = []; order.push(cat); }
    groups[cat].push({ ...l, kind: "line", line_kind: l.line_kind || "fourniture" });
  });
  const onlyNoCat = order.length === 1 && order[0] === "__nocat__";
  order.forEach((cat) => {
    if (!onlyNoCat) out.push({ kind: "section", title: cat === "__nocat__" ? "Obras" : cat, collapsed: false });
    groups[cat].forEach((l) => out.push(l));
  });
  return out;
};
const FROZEN_STATUSES = ["signed", "issued", "partial", "paid"];
const lineMargin = (l) => {
  const pv = Number(l.unit_price_ht) || 0, c = Number(l.cost_price_ht) || 0;
  if (c <= 0) return null;
  return { pct: pv > 0 ? ((pv - c) / pv) * 100 : -100, loss: pv < c };
};

export default function QuoteEditor() {
  const [cadFile, setCadFile] = useState(null);
  const { docId: paramDocId } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [chantierId, setChantierId] = useState(sp.get("chantier") || "");
  const { chantier: ctxChantier } = useChantierContext(chantierId);
  const { t, lang } = useI18n();
  const quoteText = useQuoteCopy();
  const [assistantOrigin, setAssistantOrigin] = useState(null);
  const [loadedAt, setLoadedAt] = useState(null);
  const [versionConflict, setVersionConflict] = useState(false);
  const savedContent = useRef(null);
  const isPT = lang === "pt"; // affichage uniquement — jamais utilisé pour la TVA
  const [fiscal, setFiscal] = useState(null);
  useEffect(() => { api.get("/documents/fiscal-profile").then(({ data }) => setFiscal(data)).catch(() => setFiscal({ known: false, rates: [...new Set([...VAT_RATES, ...VAT_RATES_PT])].sort((a, b) => a - b), default_rate: null })); }, []);
  const vatRates = fiscal?.rates || VAT_RATES;
  const defVat = fiscal?.default_rate ?? null;
  const [viewMode, setViewMode] = useState("editor"); // editor | split | preview
  const [zoomSrc, setZoomSrc] = useState(null);
  const [saveState, setSaveState] = useState("idle");
  const [frozenInfo, setFrozenInfo] = useState(null);
  const dirtyRef = useRef(false);

  const [docId, setDocId] = useState(paramDocId || null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clients, setClients] = useState([]);
  const [library, setLibrary] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQ, setPickerQ] = useState("");

  const [clientId, setClientId] = useState(sp.get("client") || "");
  const [srcPlanId, setSrcPlanId] = useState(sp.get("plan") || "");
  // P2 — création d'un client à la volée depuis l'éditeur de devis
  const [newClientOpen, setNewClientOpen] = useState(false);
  const [ncBusy, setNcBusy] = useState(false);
  const [nc, setNc] = useState({ first_name: "", last_name: "", company: "", email: "", phone: "", address: "" });
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [depositPct, setDepositPct] = useState(0);
  const [validityDays, setValidityDays] = useState(30);
  const [validUntil, setValidUntil] = useState("");
  const [projectAddress, setProjectAddress] = useState("");
  const [projectDuration, setProjectDuration] = useState("");
  const [projectStart, setProjectStart] = useState("");
  const [schedule, setSchedule] = useState([]);
  const [status, setStatus] = useState("draft");
  const [number, setNumber] = useState(null);
  const [leadId, setLeadId] = useState(() => sp.get("lead") || null);
  const [lines, setLines] = useState([blankLine(null)]);
  const dragIdxRef = useRef(null);
  const [dragIdx, setDragIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const compDragRef = useRef(null); // { line, comp }
  const [compDragOver, setCompDragOver] = useState(null); // `${i}-${ci}`
  const [tplOpen, setTplOpen] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [tplName, setTplName] = useState("");
  const [tplBusy, setTplBusy] = useState(false);
  const [checkOpen, setCheckOpen] = useState(false);
  const [aiLineBusy, setAiLineBusy] = useState(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [videoBusy, setVideoBusy] = useState(false);
  const [cctpBusy, setCctpBusy] = useState(false);
  const [cctpPreview, setCctpPreview] = useState(null);
  const lotPrefs = useRef({ kept: user?.cctp_lots_kept || [], skipped: user?.cctp_lots_skipped || [] });
  const normLot = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/\blot\s*n?°?\s*\d+[a-z]?\b/g, "").replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  const lotWords = (s) => normLot(s).split(" ").filter((w) => w.length >= 4);
  const lotMatches = (lot, list) => list.some((k) => { const kw = lotWords(k); const lw = lotWords(lot); return kw.length && lw.length && kw.some((w) => lw.includes(w)); });
  const preselectLot = (lot) => {
    const kept = lotMatches(lot, lotPrefs.current.kept), skipped = lotMatches(lot, lotPrefs.current.skipped);
    if (kept && !skipped) return true;
    if (skipped && !kept) return false;
    return true;
  };
  const learnLots = async (lots, selected) => {
    const kept = new Set(lotPrefs.current.kept), skipped = new Set(lotPrefs.current.skipped);
    lots.forEach((lot) => { const n = normLot(lot); if (!n) return; if (selected.has(lot)) { kept.add(n); skipped.delete(n); } else { skipped.add(n); kept.delete(n); } });
    lotPrefs.current = { kept: [...kept], skipped: [...skipped] };
    try { await api.put("/users/me/preferences", { cctp_lots_kept: [...kept], cctp_lots_skipped: [...skipped] }); } catch { /* silencieux */ }
  };
  const importCctp = async (file) => {
    if (!file) return;
    setCctpBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/documents/cctp/extract", fd, { timeout: 300000 });
      const lots = [...new Set((data.lines || []).map((l) => (l.category || "").trim() || "Outros"))];
      if (lots.length <= 1) { applyCctp(data, new Set(lots)); return; }
      const selected = new Set(lots.filter(preselectLot));
      const remembered = lots.length - selected.size;
      setCctpPreview({ data, lots, selected: selected.size ? selected : new Set(lots), remembered });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Leitura do caderno de encargos impossível");
    } finally { setCctpBusy(false); }
  };
  const applyCctp = (data, selected, lots = null) => {
    if (lots && lots.length > 1) learnLots(lots, selected);
    const keep = (data.lines || []).filter((l) => selected.has((l.category || "").trim() || "Outros"));
    const newLines = keep.map((l) => ({ ...blankLine(defVat), ...l, _saveToLib: false }));
    setLines((ls) => [...ls.filter((l) => l.designation?.trim() || Number(l.unit_price_ht) > 0), ...newLines]);
    if (!title && data.title) setTitle(data.title);
    if (data.prescriptions?.length) {
      const presc = data.prescriptions.map((p) => `• ${p.theme ? p.theme + " : " : ""}${p.text}`).join("\n");
      setNotes((n) => (n?.trim() ? `${n.trim()}\n\nPrescrições do caderno de encargos:\n${presc}` : `Prescrições do caderno de encargos:\n${presc}`));
    }
    const imposed = keep.filter((l) => l.imposed_materials?.length).length;
    toast.success(`${newLines.length} artigo(s) importado(s) do caderno de encargos${data.ocr ? " (OCR)" : ""} · ${imposed} com materiais impostos · ${selected.size} lot(s)`);
    setCctpPreview(null);
  };
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoPreviews, setPhotoPreviews] = useState([]);

  // Photo → devis : lit une ou plusieurs photos EN PARALLÈLE via l'IA et ajoute les lignes
  const addPhotosFromFiles = async (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f && f.type.startsWith("image/"));
    if (!files.length) { toast.error(t("crm.t_need_photo")); return; }
    setPhotoBusy(true);
    const tid = toast.loading(files.length > 1 ? t("crm.t_reading_photos").replace("{n}", files.length) : t("crm.t_reading_photo"));
    try {
      const b64s = await Promise.all(files.map((file) => new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result);
        r.onerror = rej;
        r.readAsDataURL(file);
      })));
      const results = await Promise.all(b64s.map(async (b64) => {
        try {
          const { data } = await api.post("/quotes/analyse", { image_base64: b64 });
          return { src: b64, found: (data?.analysis?.lines) || [] };
        } catch {
          return { src: b64, found: [] };
        }
      }));
      setPhotoPreviews((prev) => [...prev, ...results.map((r) => ({ src: r.src, count: r.found.length }))]);
      const allFound = results.flatMap((r) => r.found);
      if (allFound.length) {
        setLines((ls) => {
          const cleaned = ls.filter((l) => (l.designation || "").trim() || (l.qty || 0));
          const mapped = allFound.map((l) => ({
            ...blankLine(),
            designation: l.label || "",
            unit: l.unit || "u",
            qty: Number(l.quantity) || 1,
            unit_price_ht: Number(l.unit_price) || 0,
            category: "Lido a partir de foto",
          }));
          return [...cleaned, ...mapped];
        });
        const okCount = results.filter((r) => r.found.length).length;
        toast.success(t("crm.t_lines_from_photos").replace("{n}", allFound.length).replace("{p}", okCount), { id: tid });
      } else {
        toast.error(t("crm.t_no_prestation"), { id: tid });
      }
    } finally { setPhotoBusy(false); }
  };
  const [transcriptDialog, setTranscriptDialog] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [transcriptBusy, setTranscriptBusy] = useState(false);
  const [transcriptPhotos, setTranscriptPhotos] = useState([]);
  const [docType, setDocType] = useState(
    ["invoice", "credit_note"].includes(sp.get("type")) ? sp.get("type") : "quote");

  const applyDoc = useCallback((d) => {
    setLoadedAt(d.updated_at || null);
    savedContent.current = contentStamp(d);
    setVersionConflict(false);
    setAssistantOrigin(d.source === "assistant" ? { client: d.client_name || "", conversation: d.assistant_conversation_id } : null);
    setDocId(d.doc_id);
    setClientId(d.client_id || "");
    if (d.chantier_id) setChantierId(d.chantier_id);
    if (d.plan_id) setSrcPlanId(d.plan_id);
    setTitle(d.title || "");
    setNotes(d.notes || "");
    setDepositPct(d.deposit_pct || 0);
    setValidityDays(d.validity_days ?? 30);
    setValidUntil(d.valid_until || "");
    setProjectAddress(d.project_address || "");
    setProjectDuration(d.project_duration || "");
    setProjectStart(d.project_start || "");
    setSchedule(Array.isArray(d.payment_schedule) ? d.payment_schedule : []);
    setStatus(d.status || "draft");
    setNumber(d.number || null);
    if (d.lead_id) setLeadId(d.lead_id);
    setDocType(d.doc_type || "quote");
    setLines(ensureBlocks((d.lines || []).map((l) => ({ ...blankLine(), ...l, _saveToLib: false }))));
    setFrozenInfo(d.signed || FROZEN_STATUSES.includes(d.status) ? { hash: d.frozen_hash, at: d.frozen_at || d.signed_at, revision: d.revision, revision_of: d.revision_of, superseded_by: d.superseded_by, doc_type: d.doc_type } : (d.revision_of ? { revision: d.revision, revision_of: d.revision_of, draft: true } : null));
    dirtyRef.current = false;
  }, []);

  // A10 — sauvegarde continue des brouillons (temporisée), garde de sortie, états explicites
  const isFrozen = !!frozenInfo && !frozenInfo.draft;
  useEffect(() => {
    if (docType !== "quote" || !chantierId) return;
    let cancel = false;
    api.get(`/chantiers/${chantierId}`).then(({ data }) => {
      if (cancel) return;
      const addr = [data.address, data.postal_code, data.city].filter(Boolean).join(", ");
      if (addr) setProjectAddress((v) => v || addr);
    }).catch(() => {});
    return () => { cancel = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chantierId, docType]);
  const scheduleSum = Math.round((schedule || []).reduce((s, x) => s + (Number(x.pct) || 0), 0) * 100) / 100;
  const baseline = useRef(null);
  const localStamp = () => { const { expected_updated_at, ...rest } = payload(); return JSON.stringify(rest); };
  useEffect(() => { baseline.current = localStamp(); dirtyRef.current = false; setSaveState((st) => (st === "dirty" ? "idle" : st));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedAt]);
  useEffect(() => {
    if (loading || baseline.current == null) return;
    const dirty = localStamp() !== baseline.current;
    dirtyRef.current = dirty;
    if (!dirty) return;
    setSaveState("dirty");
    if (!docId || isFrozen || status !== "draft" || versionConflict || saving) return;
    const timer = setTimeout(async () => { setSaveState("saving"); await save(); }, 2500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, title, notes, depositPct, clientId, status, leadId, validityDays, validUntil, projectAddress, projectDuration, projectStart, schedule]);
  useEffect(() => {
    const guard = (e) => { if (dirtyRef.current) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);

  // Bootstrap: existing doc, from-plan, or blank
  useEffect(() => {
    if (!user) return;
    (async () => {
      setLoading(true);
      try {
        const [{ data: cl }, { data: lib }] = await Promise.all([
          api.get("/clients"), api.get("/library"),
        ]);
        setClients(cl.clients || []);
        setLibrary(lib.items || []);
        if (!paramDocId && sp.get("chantier") && !sp.get("client")) {
          try {
            const { data: ch } = await api.get(`/chantiers/${sp.get("chantier")}`);
            if (ch.client_id) setClientId(ch.client_id);
            setTitle((cur) => cur || ch.name);
          } catch { /* dossier inaccessible : on continue sans préremplissage */ }
        }
        if (paramDocId) {
          const { data } = await api.get(`/documents/${paramDocId}`);
          applyDoc(data);
        } else if (sp.get("plan")) {
          const q = sp.get("client") ? `?client_id=${sp.get("client")}` : "";
          const { data } = await api.post(`/documents/from-plan/${sp.get("plan")}${q}`);
          applyDoc(data);
          nav(`/devis-editeur/${data.doc_id}`, { replace: true });
        }
        const pend = sessionStorage.getItem("construpilot_pending_ouvrages");
        if (pend) {
          try {
            const arr = JSON.parse(pend);
            if (Array.isArray(arr) && arr.length) {
              setLines((ls) => {
                const base = ls.filter((l) => (l.designation || "").trim() || (Number(l.unit_price_ht) || 0));
                return [...base, ...arr.map((l) => ({ ...blankLine(), ...l, _saveToLib: false }))];
              });
              toast.success(t("crm.t_ouvrages_from_plan").replace("{n}", arr.length));
            }
          } catch { /* ignore */ }
          sessionStorage.removeItem("construpilot_pending_ouvrages");
        }
      } catch (e) {
        toast.error(e?.response?.data?.detail || t("crm.load_fail"));
      } finally { setLoading(false); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, paramDocId]);

  const totals = useMemo(() => {
    let ht = 0; let cost = 0; let coveredHt = 0; let known = 0; let total = 0; let vatUnset = 0; const tva = {};
    lines.forEach((l) => {
      if (l.kind && l.kind !== "line") return;
      if (!l.designation?.trim()) return;
      total += 1;
      const q = Number(l.qty) || 0;
      const disc = Number(l.discount_pct) || 0;
      const lh = q * (Number(l.unit_price_ht) || 0) * (1 - disc / 100);
      ht += lh;
      const c = Number(l.cost_price_ht) || 0;
      if (c > 0 || l.cost_confirmed_zero) { known += 1; coveredHt += lh; cost += q * c; }
      if (l.vat_rate === "" || l.vat_rate == null) vatUnset += 1;
      const r = Number(l.vat_rate) || 0;
      tva[r] = (tva[r] || 0) + lh * r / 100;
    });
    const tvaTotal = Object.values(tva).reduce((a, b) => a + b, 0);
    const ttc = ht + tvaTotal;
    const dep = ttc * (Number(depositPct) || 0) / 100;
    const complete = total > 0 && known === total;
    const margin = complete ? ht - cost : null;
    const partialMargin = known > 0 && !complete ? coveredHt - cost : null;
    return { ht, tva, tvaTotal, ttc, dep, remaining: ttc - dep, cost, margin,
             marginPct: complete && ht > 0 ? (margin / ht) * 100 : null,
             coverage: { known, total, complete, missing: total - known, coveredHt }, partialMargin, vatUnset };
  }, [lines, depositPct]);

  const lotSubtotals = useMemo(() => {
    const map = new Map();
    for (const l of lines) {
      const cat = (l.category || "").trim();
      if (!cat) continue;
      const q = Number(l.qty) || 0;
      const lh = q * (Number(l.unit_price_ht) || 0);
      const c = Number(l.cost_price_ht) || 0;
      const cur = map.get(cat) || { ht: 0, cost: 0, hasCost: false, loss: 0 };
      cur.ht += lh;
      if (c > 0) { cur.hasCost = true; cur.cost += q * c; if (c > (Number(l.unit_price_ht) || 0)) cur.loss += 1; }
      map.set(cat, cur);
    }
    return [...map.entries()].map(([cat, v]) => ({
      cat, ht: v.ht, cost: v.cost, loss: v.loss,
      marginPct: v.hasCost && v.ht > 0 ? ((v.ht - v.cost) / v.ht) * 100 : null,
    }));
  }, [lines]);
  const lossLines = useMemo(() => lines.filter((l) => lineMargin(l)?.loss).length, [lines]);

  const lotOrder = useMemo(() => {
    const seen = [];
    lines.forEach((l) => { const c = (l.category || "").trim() || "Outros"; if (!seen.includes(c)) seen.push(c); });
    return seen;
  }, [lines]);

  const blockNumbers = useMemo(() => {
    const nums = []; let sec = 0, sub = 0, ln = 0;
    lines.forEach((l) => {
      if (l.kind === "section") { sec++; sub = 0; ln = 0; nums.push(String(sec)); }
      else if (l.kind === "subsection") { sub++; ln = 0; nums.push(sec ? `${sec}.${sub}` : String(sub)); }
      else if (l.kind === "text" || l.kind === "pagebreak") { nums.push(""); }
      else { ln++; nums.push(sec ? (sub ? `${sec}.${sub}.${ln}` : `${sec}.${ln}`) : String(ln)); }
    });
    return nums;
  }, [lines]);

  const sectionSubtotals = useMemo(() => {
    const map = {}; let cur = null;
    lines.forEach((l, i) => {
      if (l.kind === "section") { cur = i; map[i] = 0; }
      else if (!l.kind || l.kind === "line") {
        if (cur != null) map[cur] += (Number(l.qty) || 0) * (Number(l.unit_price_ht) || 0) * (1 - (Number(l.discount_pct) || 0) / 100);
      }
    });
    return map;
  }, [lines]);

  const addBlock = (kind) => setLines((ls) => [...ls, newEntry(kind, defVat)]);
  const insertBlock = (kind, at) => {
    setLines((ls) => { const n = [...ls]; n.splice(Math.max(0, Math.min(at, n.length)), 0, newEntry(kind, defVat)); return n; });
    toast.success(t("crm.line_added"));
  };

  const knownLots = useMemo(() => {
    const s = new Set();
    lines.forEach((l) => { const c = (l.category || "").trim(); if (c) s.add(c); });
    ["Obra grossa", "Cobertura", "Canalização", "Eletricidade", "Pintura", "Carpintaria",
     "Revestimento cerâmico", "Isolamento", "Pavimento", "Pladur", "VRD"].forEach((c) => s.add(c));
    return [...s];
  }, [lines]);

  const [targetMargin, setTargetMargin] = useState(() => Number(user?.target_margin_pct) || 0);
  const [libraryMode, setLibraryMode] = useState(() => user?.price_library_mode || "shared_first");
  const saveLibraryMode = async (m) => {
    setLibraryMode(m);
    try { await api.put("/users/me/preferences", { price_library_mode: m }); toast.success(isPT ? "Preferência guardada" : "Preferência guardada"); } catch { toast.error(isPT ? "Erro ao guardar" : "Não foi possível guardar"); }
  };
  const [lotMargins, setLotMargins] = useState(() => user?.target_margins_by_lot || {});
  const [showLotMargins, setShowLotMargins] = useState(false);
  const marginFor = (category) => {
    const k = Object.keys(lotMargins).find((c) => c.trim().toLowerCase() === (category || "").trim().toLowerCase());
    return k != null && Number(lotMargins[k]) > 0 ? Number(lotMargins[k]) : targetMargin;
  };
  const saveLotMargins = async (next) => {
    setLotMargins(next);
    try { await api.put("/users/me/preferences", { target_margins_by_lot: next }); } catch { /* silencieux */ }
  };
  const priceFromCost = (cost, m) => (m > 0 && m < 100 && cost > 0 ? Math.round((cost / (1 - m / 100)) * 100) / 100 : null);
  const saveTargetMargin = async (v) => {
    const m = Math.min(90, Math.max(0, Number(v) || 0));
    setTargetMargin(m);
    try { await api.put("/users/me/preferences", { target_margin_pct: m }); } catch { /* silencieux */ }
  };
  const applyTargetMargin = () => {
    const targets = lines.filter((l) => (Number(l.cost_price_ht) || 0) > 0 && !(Number(l.unit_price_ht) > 0) && marginFor(l.category) > 0);
    if (!targets.length) { toast.error(targetMargin || Object.keys(lotMargins).length ? "Nenhuma linha com custo e sem preço" : "Defina primeiro uma margem alvo"); return; }
    setLines((ls) => ls.map((l) => {
      const c = Number(l.cost_price_ht) || 0, m = marginFor(l.category);
      return c > 0 && !(Number(l.unit_price_ht) > 0) && m > 0 ? { ...l, unit_price_ht: priceFromCost(c, m) } : l;
    }));
    toast.success(`${targets.length} preço(s) de venda calculado(s) (margem alvo global ou por capítulo)`);
  };
  const setLine = (i, k, v) => setLines((ls) => ls.map((l, idx) => {
    if (idx !== i) return l;
    const nl = { ...l, [k]: v };
    if (k === "unit_price_ht" && v !== "") Object.assign(nl, { price_source: "user_input", price_estimated: false, price_missing: false, price_reference: "", price_reference_label: "" });
    if (k === "qty" && v !== "") nl.quantity_missing = false;
    if (k === "vat_rate" && v !== "") nl.vat_assumed = false;
    const m = marginFor(k === "category" ? v : l.category);
    if (k === "cost_price_ht" && m > 0 && !(Number(l.unit_price_ht) > 0)) {
      const p = priceFromCost(Number(v) || 0, m);
      if (p) nl.unit_price_ht = p;
    }
    return nl;
  }));
  const setAllVat = (rate) => {
    setLines((ls) => ls.map((l) => ({ ...l, vat_rate: rate, vat_assumed: false, vat_confirmed: true })));
    toast.success(t("crm.t_vat_applied").replace("{r}", rate));
  };
  const buildCheckPayload = () => ({
    lines: lines.filter((l) => (l.designation || "").trim() || Number(l.unit_price_ht) > 0),
    chantier_id: chantierId || null,
    title: title || "",
    use_ai: true,
  });
  const focusLine = (i) => {
    const el = document.querySelector(`[data-testid="editor-line-${i}"]`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("ring-2", "ring-primary", "rounded-sm");
      setTimeout(() => el.classList.remove("ring-2", "ring-primary", "rounded-sm"), 2200);
    }
  };
  const applyCheckFix = (fix) => {
    if (fix.type === "set_vat") {
      const set = new Set(fix.indexes);
      setLines((ls) => ls.map((l, idx) => (set.has(idx) ? { ...l, vat_rate: fix.rate, vat_assumed: false, vat_confirmed: true } : l)));
    }
  };

  const setComponents = (i, comps) => setLines((ls) => ls.map((l, idx) => {
    if (idx !== i) return l;
    const total = (comps || []).reduce((s, c) => s + (Number(c.qty) || 0) * (Number(c.unit_price_ht) || 0), 0);
    const cost = (comps || []).reduce((s, c) => s + (Number(c.qty) || 0) * (Number(c.cost_price_ht ?? c.unit_price_ht) || 0), 0);
    return { ...l, components: comps, unit_price_ht: Math.round(total * 100) / 100, cost_price_ht: Math.round(cost * 100) / 100 };
  }));
  const addComponent = (i, kind) => setLines((ls) => ls.map((l, idx) => (idx === i
    ? { ...l, _open: true, components: [...(l.components || []), { kind, designation: "", unit: kind === "main_oeuvre" ? "h" : "u", qty: 1, unit_price_ht: 0 }] } : l)));

  const addLine = () => setLines((ls) => [...ls, blankLine(defVat)]);
  const delLine = (i) => setLines((ls) => ls.filter((_, idx) => idx !== i));
  const moveLine = (i, dir) => setLines((ls) => {
    const j = i + dir;
    if (j < 0 || j >= ls.length) return ls;
    const next = [...ls];
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  });
  const reorderLine = (from, to) => setLines((ls) => {
    if (from == null || to == null || from === to || from < 0 || to < 0 || from >= ls.length || to >= ls.length) return ls;
    const next = [...ls];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    return next;
  });

  const loadTemplates = async () => {
    try { const { data } = await api.get("/quote-templates"); setTemplates(data || []); }
    catch { toast.error("Carregamento dos modelos impossível"); }
  };
  const openTemplates = () => { setTplName(title || ""); setTplOpen(true); loadTemplates(); };
  const saveTemplate = async () => {
    const name = (tplName || "").trim();
    if (!name) { toast.error("Nome do modelo obrigatório"); return; }
    setTplBusy(true);
    try {
      const p = payload();
      const tlines = (p.lines || []).map((l) => ({ ...l, photos: [], components: Array.isArray(l.components) ? l.components.map((c) => ({ ...c, photos: [] })) : [] }));
      await api.post("/quote-templates", { name, doc_type: docType, title, notes, deposit_pct: Number(depositPct) || 0, validity_days: Number(validityDays) || 0, lines: tlines });
      toast.success("Modelo guardado");
      setTplName("");
      loadTemplates();
    } catch { toast.error("Gravação do modelo impossível"); }
    finally { setTplBusy(false); }
  };
  const applyTemplate = (tpl) => {
    const hasContent = lines.some((l) => (l.designation || "").trim() || (l.title || "").trim());
    if (hasContent && !window.confirm("Substituir o conteúdo atual do orçamento por este modelo?")) return;
    if (tpl.title) setTitle(tpl.title);
    if (tpl.notes) setNotes(tpl.notes);
    if (tpl.deposit_pct != null) setDepositPct(tpl.deposit_pct);
    if (tpl.validity_days != null) setValidityDays(tpl.validity_days);
    setLines(ensureBlocks((tpl.lines || []).map((l) => ({ ...blankLine(), ...l, photos: [], _saveToLib: false }))));
    setTplOpen(false);
    toast.success("Modelo aplicado");
  };
  const deleteTemplate = async (id) => {
    try { await api.delete(`/quote-templates/${id}`); setTemplates((ts) => ts.filter((t) => t.template_id !== id)); toast.success("Modelo eliminado"); }
    catch { toast.error("Não foi possível eliminar"); }
  };
  const [aiExampleBusy, setAiExampleBusy] = useState(false);
  const saveAsAiExample = async () => {
    const rows = lines.filter((l) => (!l.kind || l.kind === "line") && ((l.designation || "").trim() || Number(l.unit_price_ht) > 0));
    if (!rows.length) { toast.error("Adicione pelo menos uma linha antes de o transformar num exemplo."); return; }
    const txt = rows.map((l) => {
      const d = (l.designation || "").trim();
      const desc = (l.description || "").trim();
      const q = Number(l.qty) || 0;
      const u = l.unit || "u";
      return `- ${d} (${q} ${u})` + (desc ? `\n    ${desc.replace(/\n/g, "\n    ")}` : "");
    }).join("\n");
    setAiExampleBusy(true);
    try {
      await api.post("/admin/learning", {
        scope: "devis",
        title: (title || "Orçamento").slice(0, 120),
        context: notes ? notes.slice(0, 1000) : "",
        content: txt.slice(0, 8000),
        approved: true,
      });
      toast.success("Orçamento guardado como exemplo — a IA vai inspirar-se nele.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    } finally { setAiExampleBusy(false); }
  };

  const moveLot = (cat, dir) => setLines((ls) => {
    const order = [];
    const map = new Map();
    ls.forEach((l) => {
      const c = (l.category || "").trim() || "Outros";
      if (!map.has(c)) { map.set(c, []); order.push(c); }
      map.get(c).push(l);
    });
    const idx = order.indexOf(cat);
    const j = idx + dir;
    if (idx < 0 || j < 0 || j >= order.length) return ls;
    [order[idx], order[j]] = [order[j], order[idx]];
    return order.flatMap((c) => map.get(c));
  });

  const suggestDescription = async (i) => {
    const l = lines[i];
    if (!(l?.designation || "").trim()) return toast.error(t("crm.t_need_desig"));
    setAiLineBusy(i);
    try {
      const { data } = await api.post("/documents/ai/describe", {
        designation: l.designation, context: title || "",
      });
      const suggestion = (data.description || "").trim();
      if (!suggestion) return toast.error(t("crm.t_no_suggest"));
      setLines((ls) => ls.map((ln, idx) => idx === i
        ? { ...ln, description: ln.description?.trim() ? ln.description + "\n" + suggestion : suggestion }
        : ln));
      toast.success(t("crm.t_suggest_added"));
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_suggest_unavailable"));
    } finally { setAiLineBusy(null); }
  };
  const addFromLib = (it) => {
    setLines((ls) => [...ls, {
      designation: it.designation, unit: it.unit, qty: 1,
      unit_price_ht: it.unit_price_ht, cost_price_ht: it.cost_price_ht || 0, vat_rate: it.vat_rate, category: it.category, _saveToLib: false,
    }]);
    setPickerOpen(false);
    toast.success(t("crm.line_added"));
  };

  const payload = () => ({
    expected_updated_at: loadedAt,
    doc_type: docType, client_id: clientId || null, title, notes, lead_id: leadId, chantier_id: chantierId || null,
    deposit_pct: Number(depositPct) || 0, status,
    validity_days: Number(validityDays) || 0,
    valid_until: validUntil || null,
    project_address: projectAddress, project_duration: projectDuration, project_start: projectStart,
    payment_schedule: (schedule || []).filter((s) => (s.label || "").trim()).map((s) => ({ label: s.label, pct: Number(s.pct) || 0 })),
    lines: (() => {
      let sec = "";
      const out = [];
      for (const l of lines) {
        if (l.kind === "section") { sec = (l.title || "").trim(); out.push({ kind: "section", title: l.title || "", collapsed: !!l.collapsed }); continue; }
        if (l.kind === "subsection") { out.push({ kind: "subsection", title: l.title || "", collapsed: !!l.collapsed }); continue; }
        if (l.kind === "text") { out.push({ kind: "text", text: l.text || "" }); continue; }
        if (l.kind === "pagebreak") { out.push({ kind: "pagebreak" }); continue; }
        if (!l.designation?.trim()) continue;
        out.push({
          kind: "line", line_kind: l.line_kind || "fourniture",
          designation: l.designation, description: l.description || "", unit: l.unit, qty: Number(l.qty) || 0,
          line_id: l.line_id || null,
          unit_price_ht: Number(l.unit_price_ht) || 0, discount_pct: Number(l.discount_pct) || 0,
          cost_price_ht: Number(l.cost_price_ht) || 0, cost_confirmed_zero: !!l.cost_confirmed_zero,
          vat_rate: (l.vat_rate === "" || l.vat_rate == null) ? null : Number(l.vat_rate),
          category: (l.category || sec || ""),
          components: Array.isArray(l.components) ? l.components : [],
          photos: Array.isArray(l.photos) ? l.photos.filter((p) => p && p.photo_id).map((p) => ({ photo_id: p.photo_id, storage_path: p.storage_path || "" })) : [],
          price_source: l.price_source || "", price_reference: l.price_reference || "", price_reference_label: l.price_reference_label || "",
          price_estimated: !!l.price_estimated, price_missing: !!l.price_missing, quantity_missing: !!l.quantity_missing, vat_assumed: !!l.vat_assumed, vat_confirmed: !!l.vat_confirmed,
        });
      }
      return out;
    })(),
  });

  const autoSaveLibrary = async () => {
    const known = new Set(library.map((i) => (i.designation || "").trim().toLowerCase()));
    const toSave = lines.filter((l) => (!l.kind || l.kind === "line") && l._saveToLib && (l.designation || "").trim()
      && !known.has((l.designation || "").trim().toLowerCase()));
    for (const l of toSave) {
      try {
        await api.post("/library", {
          type: "ouvrage", category: l.category || "Devis", designation: l.designation,
          unit: l.unit, unit_price_ht: Number(l.unit_price_ht) || 0, cost_price_ht: Number(l.cost_price_ht) || 0, vat_rate: (l.vat_rate === "" || l.vat_rate == null) ? (defVat ?? 0) : Number(l.vat_rate),
        });
      } catch { /* ignore */ }
    }
    if (toSave.length) toast.success(t("crm.lib_added").replace("{n}", toSave.length));
  };

  const save = async () => {
    if (!lines.some((l) => (!l.kind || l.kind === "line") && (l.designation || "").trim())) return toast.error(t("crm.need_line"));
    setSaving(true);
    try {
      let d;
      if (docId) {
        try { ({ data: d } = await api.put(`/documents/${docId}`, payload())); }
        catch (e) {
          if (e.response?.status !== 409) throw e;
          const { data: current } = await api.get(`/documents/${docId}`);
          // PDF numbering/view counters can change the timestamp without changing editable content.
          // Only retry that harmless case; never silently rebase changed lines or customer data.
          if (contentStamp(current) !== savedContent.current) throw e;
          ({ data: d } = await api.put(`/documents/${docId}`, { ...payload(), expected_updated_at: current.updated_at }));
        }
      }
      else ({ data: d } = await api.post("/documents", payload()));
      if (d.revision_created) {
        toast.info(d.message || "Nova revisão em rascunho criada — o original assinado é conservado.", { duration: 9000 });
        applyDoc(d);
        nav(`/devis-editeur/${d.doc_id}`, { replace: true });
        setSaveState("saved");
        return d;
      }
      applyDoc(d);
      setSaveState("saved");
      if (!paramDocId && d.doc_id) nav(`/devis-editeur/${d.doc_id}`, { replace: true });
      await autoSaveLibrary();
      toast.success(t("crm.saved"));
      return d;
    } catch (e) {
      setSaveState("error");
      if (e.response?.status === 409 && /figé|émise|signé/i.test(e.response?.data?.detail || "")) {
        toast.error(e.response.data.detail, { duration: 10000 });
      } else if (e.response?.status === 409) {
        setVersionConflict(true);
        toast.error(lang === "pt" ? "O documento foi alterado. Reveja a versão guardada." : lang === "en" ? "The document changed. Review the saved version." : "O documento mudou. Releia a versão guardada.");
      } else toast.error(e?.response?.data?.detail || t("crm.save_fail"));
    }
    finally { setSaving(false); }
  };

  const createClientInline = async () => {
    if (!(nc.first_name || nc.last_name || nc.company || nc.email)) {
      toast.error(t("crm.t_need_client_identity")); return;
    }
    setNcBusy(true);
    try {
      const { data } = await api.post("/clients", nc);
      setClients((prev) => [data, ...prev]);
      setClientId(data.client_id);
      setNewClientOpen(false);
      setNc({ first_name: "", last_name: "", company: "", email: "", phone: "", address: "" });
      toast.success(t("crm.t_client_added"));
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_client_create_fail"));
    } finally { setNcBusy(false); }
  };

  const addPlanFromFile = async (file, cadUnit) => {
    setCadFile(null);
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) { toast.error(t("crm.t_file_too_big20")); return; }
    setPlanBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (cadUnit) fd.append("cad_unit", cadUnit);
      const data = await uploadPlan(fd);
      toast.success(t("crm.t_plan_imported"));
      nav(`/plan?open=${data.plan_id}&auto=1`);
    } catch (e) {
      if (typeof e?.response?.data?.detail === "string" && e.response.data.detail.includes("CAD_UNIT_REQUIRED")) { setCadFile(file); return; }
      toast.error(e?.response?.data?.detail || t("crm.t_plan_import_fail"));
    } finally { setPlanBusy(false); }
  };

  // --- Enregistreur vidéo intégré basse résolution (480p) ---
  const [recOpen, setRecOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
  const [recMode, setRecMode] = useState("video");
  const [streamReady, setStreamReady] = useState(false);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const videoElRef = useRef(null);

  const closeRecorder = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (recorderRef.current && recorderRef.current.state !== "inactive") { try { recorderRef.current.stop(); } catch {} }
    recorderRef.current = null;
    if (streamRef.current) { streamRef.current.getTracks().forEach((tr) => tr.stop()); streamRef.current = null; }
    if (videoElRef.current) videoElRef.current.srcObject = null;
    setStreamReady(false);
    setRecording(false);
    setRecSecs(0);
    setRecOpen(false);
  };

  const openRecorder = async (mode = "video") => {
    if (!navigator.mediaDevices?.getUserMedia) { toast.error(t("crm.t_mic_cam_unsupported")); return; }
    setRecMode(mode);
    setStreamReady(false);
    setRecOpen(true);
    try {
      const constraints = mode === "audio"
        ? { audio: true }
        : { audio: true, video: { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24, max: 30 } } };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      if (mode !== "audio" && videoElRef.current) { videoElRef.current.srcObject = stream; videoElRef.current.play().catch(() => {}); }
      setStreamReady(true);
    } catch {
      toast.error(mode === "audio" ? t("crm.t_mic_denied") : t("crm.t_cam_denied"));
      closeRecorder();
    }
  };

  const startRec = () => {
    const stream = streamRef.current;
    if (!stream) return;
    chunksRef.current = [];
    const cand = recMode === "audio"
      ? ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
      : ["video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];
    const mime = cand.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
    const opts = mime ? { mimeType: mime, ...(recMode === "audio" ? { audioBitsPerSecond: 96000 } : { videoBitsPerSecond: 600000 }) } : {};
    const rec = new MediaRecorder(stream, opts);
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data); };
    rec.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: rec.mimeType || (recMode === "audio" ? "audio/webm" : "video/webm") });
      const isMp4 = (rec.mimeType || "").includes("mp4");
      const ext = recMode === "audio" ? (isMp4 ? "m4a" : "webm") : (isMp4 ? "mp4" : "webm");
      const file = new File([blob], `chantier-${Date.now()}.${ext}`, { type: blob.type });
      closeRecorder();
      if (blob.size > 0) reviewVideo(file);
    };
    rec.start();
    recorderRef.current = rec;
    setRecording(true);
    setRecSecs(0);
    timerRef.current = setInterval(() => setRecSecs((s) => s + 1), 1000);
  };

  const stopRec = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    setRecording(false);
  };

  const fmtSecs = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  useEffect(() => () => { closeRecorder(); }, []);

  // --- Revue de la vidéo (taille / durée) avant transcription ---
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewFile, setReviewFile] = useState(null);
  const [reviewInfo, setReviewInfo] = useState({ sizeMB: 0, duration: 0, url: null });

  const reviewVideo = (file) => {
    if (!file) return;
    if (file.size > 80 * 1024 * 1024) { toast.error(t("crm.t_video_too_big")); return; }
    const url = URL.createObjectURL(file);
    const sizeMB = file.size / (1024 * 1024);
    let done = false;
    const finalize = (duration) => {
      if (done) return;
      done = true;
      setReviewFile(file);
      setReviewInfo({ sizeMB, duration: isFinite(duration) && duration > 0 ? duration : 0, url });
      setReviewOpen(true);
    };
    // Garde-fou : certains navigateurs (webm MediaRecorder) ne fournissent jamais
    // les métadonnées de durée → on ouvre quand même la revue après 2,5 s.
    const guard = setTimeout(() => finalize(0), 2500);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.muted = true;
    v.onloadedmetadata = () => {
      if (v.duration === Infinity || isNaN(v.duration)) {
        v.currentTime = 1e101;
        v.ontimeupdate = () => { v.ontimeupdate = null; clearTimeout(guard); finalize(v.duration); };
      } else { clearTimeout(guard); finalize(v.duration); }
    };
    v.onerror = () => { clearTimeout(guard); finalize(0); };
    v.src = url;
  };

  const closeReview = () => {
    if (reviewInfo.url) URL.revokeObjectURL(reviewInfo.url);
    setReviewOpen(false);
    setReviewFile(null);
    setReviewInfo({ sizeMB: 0, duration: 0, url: null });
  };

  const confirmTranscribe = () => {
    const f = reviewFile;
    if (reviewInfo.url) URL.revokeObjectURL(reviewInfo.url);
    setReviewOpen(false);
    setReviewFile(null);
    setReviewInfo({ sizeMB: 0, duration: 0, url: null });
    if (f) transcribeVideo(f);
  };

  const transcribeVideo = async (file) => {
    if (!file) return;
    if (file.size > 80 * 1024 * 1024) { toast.error(t("crm.t_video_too_big")); return; }
    setVideoBusy(true);
    const tid = toast.loading(t("crm.t_transcribing"));
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/documents/video-transcribe", fd, {
        headers: { "Content-Type": "multipart/form-data" }, timeout: 180000,
      });
      toast.success(t("crm.t_transcript_ready"), { id: tid });
      setTranscript(data.transcript || "");
      setTranscriptPhotos([]);
      setTranscriptDialog(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_transcript_fail"), { id: tid });
    } finally { setVideoBusy(false); }
  };

  const addTranscriptPhotos = (files) => {
    const list = Array.from(files || []).slice(0, 6 - transcriptPhotos.length);
    list.forEach((f) => {
      if (!f.type.startsWith("image/") || f.size > 8 * 1024 * 1024) return;
      const reader = new FileReader();
      reader.onload = () => setTranscriptPhotos((p) => (p.length >= 6 ? p : [...p, reader.result]));
      reader.readAsDataURL(f);
    });
  };

  const generateFromTranscript = async () => {
    if (!transcript.trim()) { toast.error(t("crm.t_transcript_empty")); return; }
    setTranscriptBusy(true);
    const tid = toast.loading(t("crm.t_generating_quote"));
    try {
      const { data } = await api.post("/documents/from-text", { text: transcript, images: transcriptPhotos });
      toast.success(
        data.priced_lines > 0
          ? t("crm.t_quote_created_lines").replace("{n}", data.priced_lines)
          : t("crm.t_quote_created"), { id: tid });
      setTranscriptDialog(false);
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_gen_quote_fail"), { id: tid });
    } finally { setTranscriptBusy(false); }
  };

  const downloadPdf = async (internal = false) => {
    const d = docId ? { doc_id: docId } : await save();
    if (!d) return;
    if (internal && docId) await save();
    try {
      const path = internal ? `/documents/${d.doc_id}/pdf-internal` : `/documents/${d.doc_id}/pdf`;
      const res = await api.get(path, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = internal ? `devis-INTERNE.pdf` : `devis.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success(internal ? "Versão interna (custos & margens) descarregada" : t("crm.pdf_ok"));
    } catch { toast.error(t("crm.pdf_fail")); }
  };

  const [sendOpen, setSendOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendEmail, setSendEmail] = useState("");
  const [sendName, setSendName] = useState("");
  const [sendMsg, setSendMsg] = useState("");
  const [attach3d, setAttach3d] = useState(true);
  const [preview3d, setPreview3d] = useState(null);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState(null);
  const [emailPreviewHtml, setEmailPreviewHtml] = useState(null);
  const [loadingEmailPreview, setLoadingEmailPreview] = useState(false);
  const [renderUrl, setRenderUrl] = useState("");
  const [doneRenders, setDoneRenders] = useState([]);
  const [sendFiles, setSendFiles] = useState([]);

  const fileToB64 = (file) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
    r.onerror = reject;
    r.readAsDataURL(file);
  });

  const addSendFiles = (fileList) => {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;
    setSendFiles((prev) => {
      const merged = [...prev, ...incoming].slice(0, 5);
      const total = merged.reduce((s, f) => s + f.size, 0);
      if (total > 15 * 1024 * 1024) {
        toast.error(t("crm.t_attach_too_big"));
        return prev;
      }
      if (prev.length + incoming.length > 5) toast.error(t("crm.t_attach_max5"));
      return merged;
    });
  };
  const removeSendFile = (idx) => setSendFiles((prev) => prev.filter((_, i) => i !== idx));

  const pickRender = async (rid) => {
    if (!rid) { setRenderUrl(""); return; }
    try {
      const { data } = await api.post(`/runway/renders/${rid}/share`);
      setRenderUrl(data.share_url || "");
      toast.success(t("crm.t_render_attached"));
    } catch { toast.error(t("crm.t_render_attach_fail")); }
  };

  const loadEmailPreview = async () => {
    let id = docId;
    if (!id) { const d = await save(); if (!d) return; id = d.doc_id; }
    setLoadingEmailPreview(true);
    try {
      const { data } = await api.post(`/documents/${id}/email-preview`, {
        message: sendMsg, client_name: sendName, render_url: renderUrl,
      });
      setEmailPreviewHtml(data?.html || "");
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_preview_unavailable"));
    } finally { setLoadingEmailPreview(false); }
  };

  const openSend = async () => {
    const targetPct = targetMargin || 0;
    if (totals.marginPct != null && targetPct > 0 && totals.marginPct < targetPct) {
      const ok = window.confirm(`⚠️ Marge faible : ${totals.marginPct.toFixed(1)} % neste orçamento, abaixo do seu objetivo de ${targetPct} %${lossLines ? ` (${lossLines} ouvrage${lossLines > 1 ? "s" : ""} com prejuízo)` : ""}.\n\nEnviar mesmo assim?`);
      if (!ok) return;
    } else if (lossLines > 0 && !window.confirm(`⚠️ ${lossLines} ouvrage${lossLines > 1 ? "s" : ""} orçamentado${lossLines > 1 ? "s" : ""} com prejuízo neste orçamento.\n\nEnviar mesmo assim?`)) {
      return;
    }
    const c = clients.find((x) => x.client_id === clientId);
    const nm = [c?.first_name, c?.last_name].filter(Boolean).join(" ") || c?.company || c?.name || "";
    setSendEmail(c?.email || "");
    setSendName(nm);
    setSendMsg("");
    setPreview3d(null);
    setPdfPreviewUrl(null);
    setEmailPreviewHtml(null);
    setRenderUrl("");
    setSendFiles([]);
    setSendOpen(true);
    let id = docId;
    if (!id) { const d = await save(); if (!d) return; id = d.doc_id; }
    // Message type pré-rempli (selon type de document + taux de TVA)
    api.get(`/documents/${id}/email-template`, { params: { client_name: nm } })
      .then(({ data }) => { if (data?.message) setSendMsg(data.message); })
      .catch(() => {});
    // Rendus IA avant/après disponibles (prêts) à joindre
    api.get("/runway/renders")
      .then(({ data }) => setDoneRenders((data.renders || []).filter((r) => r.status === "done")))
      .catch(() => {});
    // Aperçu rendu 3D
    api.get(`/documents/${id}`).then(({ data }) => {
      if (data?.attachment_image_b64) setPreview3d(data.attachment_image_b64);
    }).catch(() => {});
    // Aperçu PDF
    api.get(`/documents/${id}/pdf`, { responseType: "blob" })
      .then((res) => setPdfPreviewUrl(URL.createObjectURL(res.data)))
      .catch(() => {});
  };

  const closeSend = (v) => {
    setSendOpen(v);
    if (!v && pdfPreviewUrl) { URL.revokeObjectURL(pdfPreviewUrl); setPdfPreviewUrl(null); }
  };

  const sendNow = async () => {
    const _mails = sendEmail.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean);
    if (_mails.length === 0 || _mails.some((e) => !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e))) {
      toast.error(t("crm.t_email_invalid")); return;
    }
    setSending(true);
    try {
      let id = docId;
      if (!id) { const d = await save(); if (!d) { setSending(false); return; } id = d.doc_id; }
      const attachments = await Promise.all(sendFiles.map(async (f) => ({
        filename: f.name, content_type: f.type || "application/octet-stream",
        content_b64: await fileToB64(f),
      })));
      const { data } = await api.post(`/documents/${id}/send`, { client_email: sendEmail, client_name: sendName, message: sendMsg, attach_3d: attach3d, render_url: renderUrl, attachments });
      toast.success(data?.attached_3d ? t("crm.t_quote_sent_3d") : t("crm.t_quote_sent"));
      closeSend(false);
      setStatus("sent");
      // Vérification de la remise réelle (envoi en arrière-plan) : alerte si l'e-mail n'est pas parti
      if (data?.log_id) {
        for (let i = 0; i < 12; i++) {
          await new Promise((r) => setTimeout(r, 4000));
          try {
            const { data: st } = await api.get(`/documents/send-status/${data.log_id}`);
            if (st.email_status === "sent") break;
            if (st.email_status === "failed") {
              toast.error((isPT ? "E-mail NÃO entregue ao cliente : " : "E-mail NÃO entregue ao cliente: ") + (st.error || ""), { duration: 15000 });
              break;
            }
          } catch { break; }
        }
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_send_fail"));
    } finally { setSending(false); }
  };

  if (!user) return <div className="surface p-10 text-center">{t("crm.login")}</div>;
  if (loading) return <div className="surface p-10 text-center animate-pulse">{t("crm.loading")}</div>;

  const filteredLib = library.filter((i) =>
    !pickerQ.trim() || (i.designation + " " + i.category).toLowerCase().includes(pickerQ.toLowerCase()));

  const _docLabel = { quote: "ORÇAMENTO", invoice: "FATURA", credit_note: "NOTA DE CRÉDITO" }[docType] || "ORÇAMENTO";
  const _clientObj = clients.find((c) => c.client_id === clientId);
  const _clientName = _clientObj
    ? ([_clientObj.first_name, _clientObj.last_name].filter(Boolean).join(" ") || _clientObj.company || _clientObj.email)
    : (sendName || "");
  const _aggPhotos = (l) => [...(l.photos || []), ...((l.components || []).flatMap((c) => c.photos || []))]
    .filter((p) => p && p.photo_id).slice(0, 9);

  const previewNode = (
    <div className="xl:sticky xl:top-4">
      <div className="flex justify-end mb-2 print:hidden">
        <Button type="button" size="sm" variant="outline" onClick={() => window.print()} className="rounded-sm gap-2" data-testid="preview-print-btn">
          <Printer className="h-4 w-4" /> Imprimir a pré-visualização
        </Button>
      </div>
    <div id="quote-print-root" className="quote-paper rounded-sm border border-border bg-white text-[#1a1f2b] shadow-sm overflow-hidden" data-testid="quote-preview">
      <div className="bg-[#0f172a] text-white px-6 py-5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-lg font-bold tracking-tight">{_docLabel} {number || ""}</p>
          <p className="text-xs opacity-80 mt-0.5 truncate">{title || "Sem título"}</p>
        </div>
        <div className="text-right text-[11px] opacity-80 shrink-0">
          <p className="font-semibold">{user?.company_name || user?.company || user?.name || ""}</p>
          <p>{new Date().toLocaleDateString("pt-PT")}</p>
        </div>
      </div>
      <div className="px-6 py-3 border-b border-border text-xs flex flex-wrap gap-x-6 gap-y-1">
        <span><span className="font-semibold text-muted-foreground">Cliente: </span>{_clientName || "—"}</span>
        {projectAddress ? <span><span className="font-semibold text-muted-foreground">Morada: </span>{projectAddress}</span> : null}
      </div>
      <div className="px-4 py-3 overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="text-[10px] uppercase tracking-wide text-muted-foreground border-b border-border">
              <th className="text-left py-1.5 pl-1 w-8">N°</th>
              <th className="text-left py-1.5">Designação</th>
              <th className="text-right py-1.5 w-12">Qtd.</th>
              <th className="text-left py-1.5 w-12 pl-2">Un.</th>
              <th className="text-right py-1.5 w-20">PU HT</th>
              <th className="text-right py-1.5 w-14">Rem.</th>
              <th className="text-right py-1.5 w-24 pr-1">Total s/ IVA</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l, i) => {
              const num = blockNumbers[i] || "";
              if (l.kind === "section") return (
                <tr key={i} className="bg-[#0f172a]/[0.06] border-t border-border" data-testid={`preview-section-${i}`}>
                  <td className="py-1.5 pl-1 font-bold">{num}</td>
                  <td className="py-1.5 font-bold uppercase text-[11px]" colSpan={5}>{l.title || "Secção"}</td>
                  <td className="py-1.5 pr-1 text-right num font-bold whitespace-nowrap">{eur(sectionSubtotals[i] || 0)}</td>
                </tr>
              );
              if (l.kind === "subsection") return (
                <tr key={i} className="border-t border-border/60">
                  <td className="py-1 pl-1 font-semibold">{num}</td>
                  <td className="py-1 font-semibold text-[11px]" colSpan={6}>{l.title || "Subsecção"}</td>
                </tr>
              );
              if (l.kind === "text") return (
                <tr key={i}><td /><td className="py-1 italic text-muted-foreground whitespace-pre-line" colSpan={6}>{l.text || ""}</td></tr>
              );
              if (l.kind === "pagebreak") return (
                <tr key={i}><td colSpan={7} className="py-1"><div className="border-t border-dashed border-border text-[9px] text-center text-muted-foreground pt-0.5">— quebra de página —</div></td></tr>
              );
              const q = Number(l.qty) || 0, pu = Number(l.unit_price_ht) || 0, disc = Number(l.discount_pct) || 0;
              const lh = q * pu * (1 - disc / 100);
              const photos = _aggPhotos(l);
              return (
                <tr key={i} className="border-t border-border/50 align-top" data-testid={`preview-line-${i}`}>
                  <td className="py-1.5 pl-1 num text-muted-foreground">{num}</td>
                  <td className="py-1.5">
                    <div className="font-semibold">{l.designation || <span className="text-muted-foreground italic font-normal">(sem designação)</span>}</div>
                    {l.description ? <div className="text-[11px] text-muted-foreground whitespace-pre-line">{l.description}</div> : null}
                    {photos.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5" data-testid={`preview-photos-${i}`}>
                        {photos.map((p, pi) => (
                          <img key={`${i}-${pi}-${p.photo_id}`} src={`${API}/document-photos/${p.photo_id}/raw`} alt=""
                               onClick={() => setZoomSrc(`${API}/document-photos/${p.photo_id}/raw`)}
                               className="h-12 w-12 object-cover rounded-sm border border-border cursor-zoom-in" />
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="py-1.5 text-right num">{q}</td>
                  <td className="py-1.5 pl-2">{l.unit || ""}</td>
                  <td className="py-1.5 text-right num whitespace-nowrap">{eur(pu)}</td>
                  <td className="py-1.5 text-right num">{disc ? `-${disc}%` : ""}</td>
                  <td className="py-1.5 pr-1 text-right num font-semibold whitespace-nowrap">{eur(lh)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="px-6 py-4 border-t border-border flex justify-end">
        <div className="w-64 text-xs grid gap-1">
          <div className="flex justify-between"><span className="text-muted-foreground">Total s/ IVA</span><span className="num font-semibold">{eur(totals.ht)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">IVA</span><span className="num">{eur(totals.tvaTotal)}</span></div>
          <div className="flex justify-between text-sm border-t border-border pt-1 mt-0.5"><span className="font-bold">Total c/ IVA</span><span className="num font-bold text-primary">{eur(totals.ttc)}</span></div>
          {Number(depositPct) > 0 && (
            <div className="flex justify-between text-[11px] text-muted-foreground"><span>Adiantamento ({depositPct} %)</span><span className="num">{eur(totals.dep)}</span></div>
          )}
        </div>
      </div>
      {notes ? <div className="px-6 pb-4 text-[11px] text-muted-foreground whitespace-pre-line"><span className="font-semibold">Notes : </span>{notes}</div> : null}
    </div>
    </div>
  );

  return (
    <div className="quote-editor grid gap-6 min-w-0" data-testid="quote-editor-page">
      <ChantierContextBar chantierId={chantierId} chantier={ctxChantier} />
      <QuoteCheckPanel open={checkOpen} onOpenChange={setCheckOpen} buildPayload={buildCheckPayload}
                       onFocusLine={focusLine} onApplyFix={applyCheckFix} docId={docId} />
      {cadFile && <CadUnitPicker file={cadFile} onChoose={unit => addPlanFromFile(cadFile, unit)} onCancel={() => setCadFile(null)} />}
      <div className="quote-editor-heading">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <button onClick={() => nav("/devis")} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1" data-testid="editor-back">
              <ArrowLeft className="h-3 w-3" /> {t("crm.ed_back")}
            </button>
            {srcPlanId && (
              <button onClick={() => nav(`/plan?open=${srcPlanId}&auto=1`)}
                      className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
                      data-testid="editor-back-to-plan">
                <Ruler className="h-3 w-3" /> {t("crm.ed_back_plan")}
              </button>
            )}
            {docType === "quote" && docId && (
              <button onClick={() => nav(`/assistant?intent=quote&resumeQuote=${docId}`)}
                      className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
                      title="Retomar este orçamento com o Assistente Construção"
                      data-testid="editor-back-to-assistant">
                <Sparkles className="h-3 w-3" /> Voltar ao assistente
              </button>
            )}
          </div>
          <p className="quote-eyebrow">CONSTRUPILOT · DOCUMENTS</p>
          <h1 className="quote-editor-title">{number ? `${_docLabel} ${number}` : `${t("crm.ed_new")} ${_docLabel.toLowerCase()}`}</h1>
          <p className="quote-editor-subtitle">{t("crm.ed_sub")}</p>
          <div className="mt-2"><VerifiedProBadge status={user?.kyc_status} /></div>
        </div>
        <div className="quote-editor-command-area">
          <div className="quote-editor-actions" data-testid="quote-editor-actions">
            <input type="file" accept="image/*,application/pdf,.dxf" className="hidden" id="qe-plan-input"
                 onChange={(e) => { addPlanFromFile(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-add-plan-input" />
            <input type="file" accept="image/*" multiple className="hidden" id="qe-photo-input"
                 onChange={(e) => { addPhotosFromFiles(e.target.files); e.target.value = ""; }}
                 data-testid="editor-photo-input" />
            <input type="file" accept="image/*" capture="environment" multiple className="hidden" id="qe-photo-cam-input"
                 onChange={(e) => { addPhotosFromFiles(e.target.files); e.target.value = ""; }}
                 data-testid="editor-photo-cam-input" />
            <input type="file" accept="application/pdf" className="hidden" id="qe-cctp-input"
                 onChange={(e) => { importCctp(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-cctp-input" />
            <input type="file" accept="video/*" className="hidden" id="qe-video-input"
                 onChange={(e) => { reviewVideo(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-video-input" />
            <input type="file" accept="audio/*" className="hidden" id="qe-audio-input"
                 onChange={(e) => { reviewVideo(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-audio-input" />
            <QuoteEditorMenu label="Importar" icon={Upload} testId="editor-import-menu">
            <DropdownMenuItem onSelect={() => document.getElementById("qe-plan-input").click()}
                  disabled={planBusy} data-testid="editor-add-plan-btn">
            {planBusy ? <Loader2 className="animate-spin" /> : <Ruler />} {t("crm.ed_add_plan")}
          </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => document.getElementById("qe-photo-input").click()}
                  disabled={photoBusy} data-testid="editor-photo-gallery-btn">
            {photoBusy ? <Loader2 className="animate-spin" /> : <Images />} {t("crm.ed_photos_gallery")}
          </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => document.getElementById("qe-photo-cam-input").click()}
                  disabled={photoBusy} data-testid="editor-photo-cam-btn">
            {photoBusy ? <Loader2 className="animate-spin" /> : <Camera />} {t("crm.ed_photo_to_quote")}
          </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => document.getElementById("qe-cctp-input").click()}
                  disabled={cctpBusy}
                  title="Ler um CCTP: trabalhos e materiais impostos adicionados ao orçamento" data-testid="editor-cctp-btn">
            {cctpBusy ? <Loader2 className="animate-spin" /> : <FileText />} {cctpBusy ? "Leitura do CCTP…" : "Ler um caderno de encargos"}
          </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => document.getElementById("qe-video-input").click()}
                  disabled={videoBusy} data-testid="editor-video-gallery-btn">
            {videoBusy ? <Loader2 className="animate-spin" /> : <Images />} {t("crm.ed_video_gallery")}
          </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => openRecorder("video")}
                  disabled={videoBusy} data-testid="editor-video-record-btn">
            {videoBusy ? <Loader2 className="animate-spin" /> : <Video />} {t("crm.ed_film_to_quote")}
          </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => document.getElementById("qe-audio-input").click()}
                  disabled={videoBusy} data-testid="editor-audio-gallery-btn">
            {videoBusy ? <Loader2 className="animate-spin" /> : <Music />} {t("crm.ed_audio_gallery")}
          </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => openRecorder("audio")}
                  disabled={videoBusy} data-testid="editor-audio-record-btn">
            {videoBusy ? <Loader2 className="animate-spin" /> : <Mic />} {t("crm.ed_dictate")}
          </DropdownMenuItem>
            </QuoteEditorMenu>
            <QuoteEditorMenu label="Mais" icon={MoreHorizontal} testId="editor-more-menu">
            <DropdownMenuItem onSelect={openTemplates} disabled={saving} data-testid="editor-templates-btn">
            <LayoutTemplate /> Modelos
          </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => downloadPdf(true)}
                  title="PDF com custos de produção e margens por lote — reservado à empresa" data-testid="editor-pdf-internal-btn">
            <Download /> PDF interno (margens)
          </DropdownMenuItem>
              {docType === "quote" && docId && (
            <DropdownMenuItem onSelect={() => nav(`/assistant?intent=quote&resumeQuote=${docId}`)}
                    title="Retomar este orçamento com o Assistente Construção (orçamentação, adição de linhas, correções)"
                    data-testid="editor-resume-assistant-btn">
              <Sparkles /> Continuar com o assistente
            </DropdownMenuItem>
              )}
              {user?.role === "admin" && (
            <DropdownMenuItem onSelect={saveAsAiExample} disabled={aiExampleBusy}
                    title="Guardar este orçamento como exemplo de referência para a IA (aprendizagem global)"
                    data-testid="editor-ai-example-btn">
              {aiExampleBusy ? <Loader2 className="animate-spin" /> : <GraduationCap />} Exemplo IA
            </DropdownMenuItem>
              )}
            </QuoteEditorMenu>
            {docType === "quote" && (
            <Button variant="outline" onClick={() => setCheckOpen(true)} className="rounded-sm gap-2 border-primary/40 text-primary"
                    title="Controlar o orçamento antes do envio" data-testid="editor-check-btn">
              <ShieldCheck className="h-4 w-4" /> Verificar
            </Button>
            )}
            <Button variant="outline" onClick={() => downloadPdf(false)} className="rounded-sm gap-2" data-testid="editor-pdf-btn">
            <Download className="h-4 w-4" /> {t("crm.pdf")}
          </Button>
            <Button onClick={save} disabled={saving} variant="outline" className="rounded-sm gap-2" data-testid="editor-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} {t("crm.save")}
          </Button>
            <Button onClick={openSend} disabled={saving} className="rounded-sm gap-2 bg-primary" data-testid="editor-send-btn">
            <Send className="h-4 w-4" /> {docType === "invoice" ? t("crm.ed_send_invoice") : docType === "credit_note" ? t("crm.ed_send_credit") : t("crm.ed_send_quote")}
          </Button>
          </div>
          <span className={`text-xs self-center ${saveState === "error" ? "text-red-500" : "text-muted-foreground"}`} data-testid="editor-save-state" aria-live="polite">
            {saveState === "saving" ? "A guardar…" : saveState === "saved" ? "Guardado" : saveState === "error" ? "Falha — tentar novamente" : saveState === "dirty" ? "Alterações não guardadas" : ""}
          </span>
        </div>
      </div>

      <div className="quote-overview">
      <div className="quote-view-switch" role="group" aria-label="Apresentação do documento" data-testid="editor-view-toggle">
        {[["editor", "Editor", Pencil], ["split", "Lado a lado", Columns2], ["preview", "Pré-visualização", Eye]].map(([m, label, Ic]) => (
          <button key={m} type="button" onClick={() => setViewMode(m)} aria-pressed={viewMode === m} data-testid={`editor-view-${m}`}
            className={`inline-flex items-center gap-1.5 rounded-[4px] px-3 py-1.5 text-xs font-semibold transition-colors ${viewMode === m ? "bg-primary text-white" : "text-muted-foreground hover:text-foreground"}`}>
            <Ic className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>

        <div className="quote-overview-totals" aria-label="Resumo do documento">
          <span>{totals.coverage.total} ligne{totals.coverage.total > 1 ? "s" : ""}</span>
          <span>Total s/ IVA <strong>{eur(totals.ht)}</strong></span>
          <span className="quote-overview-grandtotal">{totals.vatUnset > 0 ? "c/ IVA a completar" : "Total c/ IVA"} <strong>{eur(totals.ttc)}</strong></span>
        </div>
      </div>

      <Dialog open={tplOpen} onOpenChange={setTplOpen}>
        <DialogContent className="max-w-lg" data-testid="templates-dialog">
          <DialogHeader><DialogTitle>Modelos de orçamento</DialogTitle>
            <DialogDescription>Guarde o orçamento atual como modelo ou aplique um modelo existente.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-sm border border-border p-3 bg-muted/30">
              <p className="text-xs font-semibold mb-2">Guardar o orçamento atual como modelo</p>
              <div className="flex gap-2">
                <Input value={tplName} onChange={(e) => setTplName(e.target.value)} placeholder="Nome do modelo (ex.: Remodelação WC)" className="rounded-sm h-9 text-sm" data-testid="template-name-input" />
                <Button onClick={saveTemplate} disabled={tplBusy || !tplName.trim()} className="rounded-sm gap-2 shrink-0" data-testid="template-save-btn">
                  {tplBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Guardar
                </Button>
              </div>
            </div>
            <div>
              <p className="text-xs font-semibold mb-2 text-muted-foreground">Os meus modelos ({templates.length})</p>
              {templates.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center" data-testid="templates-empty">Nenhum modelo por agora.</p>
              ) : (
                <div className="grid gap-1.5 max-h-72 overflow-y-auto" data-testid="templates-list">
                  {templates.map((tpl) => (
                    <div key={tpl.template_id} className="flex items-center gap-2 rounded-sm border border-border px-3 py-2" data-testid={`template-item-${tpl.template_id}`}>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold truncate">{tpl.name}</p>
                        <p className="text-[11px] text-muted-foreground">{(tpl.lines || []).length} linha(s)</p>
                      </div>
                      <Button size="sm" onClick={() => applyTemplate(tpl)} className="rounded-sm h-8" data-testid={`template-use-${tpl.template_id}`}>Utilizar</Button>
                      <Button size="icon" variant="ghost" onClick={() => deleteTemplate(tpl.template_id)} className="h-8 w-8 text-destructive" data-testid={`template-del-${tpl.template_id}`}><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <div className={viewMode === "split" ? "quote-editor-layout is-split" : "quote-editor-layout"}>
      <div className={viewMode === "preview" ? "hidden" : "quote-editor-form grid gap-6 min-w-0"}>

      <Dialog open={sendOpen} onOpenChange={closeSend}>
        <DialogContent data-testid="send-quote-dialog">
          <DialogHeader>
            <DialogTitle>{docType === "invoice" ? t("crm.ed_send_invoice_to") : docType === "credit_note" ? t("crm.ed_send_credit_to") : t("crm.ed_send_quote_to")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 max-h-[70vh] overflow-y-auto pr-1">
            {(pdfPreviewUrl || preview3d) && (
              <div className="grid gap-2" data-testid="send-preview">
                <p className="text-xs font-semibold text-muted-foreground">{t("crm.ed_preview_before")}</p>
                <div className="grid grid-cols-2 gap-2">
                  {pdfPreviewUrl ? (
                    <iframe title="Pré-visualização PDF" src={pdfPreviewUrl} data-testid="send-preview-pdf"
                            className="w-full h-40 rounded-sm border border-border bg-white" />
                  ) : (
                    <div className="w-full h-40 rounded-sm border border-border grid place-items-center text-[10px] text-muted-foreground">PDF…</div>
                  )}
                  {preview3d ? (
                    <img src={preview3d} alt="Renderização 3D" data-testid="send-preview-3d"
                         className="w-full h-40 object-contain rounded-sm border border-border bg-secondary/30" />
                  ) : (
                    <div className="w-full h-40 rounded-sm border border-dashed border-border grid place-items-center text-[10px] text-muted-foreground text-center px-2">{t("crm.ed_no_render3d")}</div>
                  )}
                </div>
              </div>
            )}
            <div className="grid gap-1.5">
              <Label htmlFor="send-name">{t("crm.ed_client_name")}</Label>
              <Input id="send-name" value={sendName} onChange={(e) => setSendName(e.target.value)}
                     placeholder={t("crm.ed_client_name")} data-testid="send-quote-name" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="send-email">{t("crm.ed_client_email_req")}</Label>
              <Input id="send-email" type="text" value={sendEmail} onChange={(e) => setSendEmail(e.target.value)}
                     placeholder="client@email.com, associe@email.com" data-testid="send-quote-email" />
              <p className="text-[11px] text-muted-foreground mt-1">Vários destinatários possíveis — separe os endereços por vírgula.</p>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="send-msg">{t("crm.ed_msg_optional")}</Label>
              <Textarea id="send-msg" rows={3} value={sendMsg} onChange={(e) => setSendMsg(e.target.value)}
                        placeholder={t("crm.ed_msg_ph")} data-testid="send-quote-msg" />
            </div>
            <div className="grid gap-2">
              <Button type="button" variant="outline" size="sm"
                      className="rounded-sm gap-2 justify-self-start"
                      onClick={loadEmailPreview} disabled={loadingEmailPreview}
                      data-testid="send-email-preview-btn">
                {loadingEmailPreview ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                {t("crm.ed_email_preview_btn")}
              </Button>
              {emailPreviewHtml && (
                <div className="rounded-sm border border-border overflow-hidden" data-testid="send-email-preview">
                  <iframe title="Pré-visualização e-mail" srcDoc={emailPreviewHtml}
                          className="w-full h-72 bg-white" />
                </div>
              )}
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="send-quote-attach3d">
              <input type="checkbox" checked={attach3d} onChange={(e) => setAttach3d(e.target.checked)}
                     className="h-4 w-4 rounded border-input accent-primary" />
              {t("crm.ed_attach_3d")}
            </label>
            <div className="grid gap-1.5" data-testid="send-attachments-block">
              <Label className="flex items-center gap-1.5"><Paperclip className="h-3.5 w-3.5" /> {t("crm.ed_attachments")}</Label>
              <input type="file" multiple
                     onChange={(e) => { addSendFiles(e.target.files); e.target.value = ""; }}
                     className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-sm file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm file:cursor-pointer hover:file:bg-secondary/80"
                     data-testid="send-attachments-input" />
              {sendFiles.length > 0 && (
                <ul className="grid gap-1 mt-1">
                  {sendFiles.map((f, i) => (
                    <li key={i} className="flex items-center justify-between gap-2 text-xs surface px-2.5 py-1.5 rounded-sm"
                        data-testid={`send-attachment-item-${i}`}>
                      <span className="truncate">{f.name} · {(f.size / 1024).toFixed(0)} Ko</span>
                      <button type="button" onClick={() => removeSendFile(i)}
                              className="text-muted-foreground hover:text-destructive shrink-0"
                              data-testid={`send-attachment-remove-${i}`}><X className="h-3.5 w-3.5" /></button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {doneRenders.length > 0 && (
              <div className="grid gap-1.5" data-testid="send-quote-render-block">
                <Label htmlFor="send-render">{t("crm.ed_ai_render_opt")}</Label>
                <select id="send-render" onChange={(e) => pickRender(e.target.value)}
                        className="rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
                        data-testid="send-quote-render-select">
                  <option value="">{t("crm.ed_none")}</option>
                  {doneRenders.map((r) => (
                    <option key={r.render_id} value={r.render_id}>
                      {(r.kind === "video" ? "🎬 " : "🖼️ ") + (r.prompt ? r.prompt.slice(0, 40) : "Renderização") + " · " + new Date(r.created_at).toLocaleDateString("pt-PT")}
                    </option>
                  ))}
                </select>
                {renderUrl && <p className="text-[11px] text-primary">{t("crm.ed_link_added")}</p>}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => closeSend(false)} className="rounded-sm" data-testid="send-quote-cancel">{t("crm.cancel")}</Button>
              <Button onClick={sendNow} disabled={sending} className="rounded-sm gap-2" data-testid="send-quote-confirm">
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} {t("crm.ed_send")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {frozenInfo && !frozenInfo.draft && (
        <div className="rounded-sm border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm flex flex-wrap items-center gap-2" data-testid="editor-frozen-banner">
          <Lock className="h-4 w-4 text-amber-600" />
          <span className="font-medium">{frozenInfo.doc_type === "quote" ? "Orçamento assinado — conteúdo bloqueado." : "Documento emitido — conteúdo bloqueado."}</span>
          <span className="text-muted-foreground">
            {frozenInfo.doc_type === "quote"
              ? "Qualquer alteração das linhas, do cliente ou das condições criará uma nova revisão em rascunho (a voltar a assinar); esta versão continua consultável."
              : "Uma correção é feita através de uma nota de crédito: o conteúdo deste documento já não pode mudar."}
            {frozenInfo.hash ? ` Implantação ${String(frozenInfo.hash).slice(0, 10)}…` : ""}
          </span>
          {frozenInfo.superseded_by && (
            <Button size="sm" variant="outline" className="rounded-sm h-7 text-xs" onClick={() => nav(`/devis-editeur/${frozenInfo.superseded_by}`)} data-testid="editor-open-revision-btn">
              Abrir a revisão em curso
            </Button>
          )}
        </div>
      )}
      {frozenInfo?.draft && (
        <div className="rounded-sm border border-border bg-muted/40 px-3 py-2 text-xs flex flex-wrap items-center gap-2" data-testid="editor-revision-banner">
          <span>Revisão {frozenInfo.revision} (rascunho, não assinada) do documento</span>
          <button type="button" className="underline" onClick={() => nav(`/devis-editeur/${frozenInfo.revision_of}`)} data-testid="editor-open-original-btn">versão assinada original</button>
        </div>
      )}

      {versionConflict && <DocumentVersionNotice onReload={async () => {
        try { const { data } = await api.get(`/documents/${docId}`); applyDoc(data); }
        catch { toast.error(t("crm.save_fail")); }
      }} />}
      {/* Meta : client, titre, statut */}
      <div className="quote-document-meta surface p-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 min-w-0">
        <div className="min-w-0">
          <Label className="flex items-center gap-1"><User className="h-3 w-3" /> {t("crm.client_lbl")}</Label>
          <div className="flex gap-2 mt-1 min-w-0">
            <select value={clientId} onChange={(e) => setClientId(e.target.value)} aria-label={t("crm.client_lbl")} data-testid="editor-client-select"
                    className="flex-1 min-w-0 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
              <option value="">{t("crm.no_client")}</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {[c.first_name, c.last_name].filter(Boolean).join(" ") || c.company || c.email}
                </option>
              ))}
            </select>
            <Button type="button" variant="outline" size="sm"
                    onClick={() => setNewClientOpen(true)} data-testid="editor-new-client-btn"
                    className="rounded-sm gap-1 whitespace-nowrap" title={t("crm.ed_add_unreg_title")}>
              <Plus className="h-3.5 w-3.5" /> {t("crm.ed_new")}
            </Button>
          </div>
        </div>
        <div>
          <Label>{t("crm.title_lbl")}</Label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} className="rounded-sm mt-1"
                 placeholder={t("crm.title_ph")} aria-label={t("crm.title_lbl")} data-testid="editor-title" />
        </div>
        <div>
          <Label>{t("crm.status_lbl")}</Label>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("crm.status_lbl")} data-testid="editor-status"
                  className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
            {STATUSES.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
          </select>
        </div>
      </div>

      {/* P2 — Dialog création client à la volée */}
      <Dialog open={newClientOpen} onOpenChange={setNewClientOpen}>
        <DialogContent className="max-w-md" data-testid="new-client-dialog">
          <DialogHeader>
            <DialogTitle>{t("crm.new_client")}</DialogTitle>
            <DialogDescription>{t("crm.ed_new_client_desc")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t("crm.firstname")}</Label>
                <Input value={nc.first_name} onChange={(e) => setNc({ ...nc, first_name: e.target.value })}
                       className="rounded-sm mt-1" data-testid="nc-first-name" placeholder="João" />
              </div>
              <div>
                <Label>{t("crm.lastname")}</Label>
                <Input value={nc.last_name} onChange={(e) => setNc({ ...nc, last_name: e.target.value })}
                       className="rounded-sm mt-1" data-testid="nc-last-name" placeholder="Silva" />
              </div>
            </div>
            <div>
              <Label>{t("crm.ed_company_opt")}</Label>
              <Input value={nc.company} onChange={(e) => setNc({ ...nc, company: e.target.value })}
                     className="rounded-sm mt-1" data-testid="nc-company" placeholder="SCI Dupont" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t("crm.email")}</Label>
                <Input value={nc.email} onChange={(e) => setNc({ ...nc, email: e.target.value })}
                       className="rounded-sm mt-1" data-testid="nc-email" placeholder="jean@email.com" />
              </div>
              <div>
                <Label>{t("crm.phone")}</Label>
                <Input value={nc.phone} onChange={(e) => setNc({ ...nc, phone: e.target.value })}
                       className="rounded-sm mt-1" data-testid="nc-phone" placeholder="06 12 34 56 78" />
              </div>
            </div>
            <div>
              <Label>{t("crm.address")}</Label>
              <Input value={nc.address} onChange={(e) => setNc({ ...nc, address: e.target.value })}
                     className="rounded-sm mt-1" data-testid="nc-address" placeholder="Rua das Obras, 12, 1000-001 Lisboa" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setNewClientOpen(false)} className="rounded-sm" data-testid="nc-cancel">
                {t("crm.cancel")}
              </Button>
              <Button onClick={createClientInline} disabled={ncBusy} className="rounded-sm gap-1" data-testid="nc-save">
                {ncBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} {t("crm.ed_add")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {photoPreviews.length > 0 && (
        <div className="surface p-3" data-testid="photo-preview">
          <div className="flex items-center justify-between mb-2">
            <div className="min-w-0">
              <p className="text-xs font-semibold">{t("crm.ed_photos_read").replace("{n}", photoPreviews.length)}</p>
              <p className="text-[11px] text-muted-foreground">{t("crm.ed_photos_read_sub")}</p>
            </div>
            <button onClick={() => setPhotoPreviews([])} className="text-muted-foreground hover:text-foreground" data-testid="photo-preview-close">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {photoPreviews.map((p, i) => (
              <div key={i} className="relative" data-testid={`photo-thumb-${i}`}>
                <img src={p.src} alt={`Fotografia ${i + 1}`} className="h-16 w-16 object-cover rounded-sm border border-border" />
                <span className="absolute bottom-0 right-0 bg-primary text-primary-foreground text-[10px] px-1 rounded-tl-sm">
                  {p.count}
                </span>
                <button onClick={() => setPhotoPreviews((prev) => prev.filter((_, j) => j !== i))}
                        className="absolute -top-1 -right-1 bg-background border border-border rounded-full h-4 w-4 flex items-center justify-center text-muted-foreground hover:text-foreground"
                        data-testid={`photo-thumb-remove-${i}`}>×</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Lignes */}
      <div className="quote-lines surface p-3 sm:p-4 grid gap-3 min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3 min-w-0" data-testid="editor-lines-toolbar">
          <p className="font-display font-bold text-sm">{t("crm.lines_title")}</p>
          <div className="flex flex-wrap gap-2 items-center min-w-0 max-w-full">
            <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={() => setPickerOpen(true)} data-testid="editor-add-from-lib">
              <BookOpen className="h-3.5 w-3.5" /> {t("crm.from_lib")}
            </Button>
          </div>
        </div>

        <div className="quote-add-toolbar" data-testid="editor-add-toolbar">
          <Button size="sm" variant="outline" className="rounded-sm gap-1 h-8 text-primary border-primary/40" onClick={() => addBlock("fourniture")} data-testid="editor-add-fourniture">
            <Plus className="h-3.5 w-3.5" /> Adicionar uma linha
          </Button>
          <QuoteEditorMenu label="Secções e outras linhas" icon={Layers} testId="editor-block-menu">
          <DropdownMenuItem onSelect={() => addBlock("main_oeuvre")} data-testid="editor-add-mainoeuvre">
            <Plus /> Mão de obra
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => addBlock("ouvrage")} data-testid="editor-add-ouvrage">
            <Plus /> Artigo
          </DropdownMenuItem>

          <DropdownMenuItem onSelect={() => addBlock("section")} data-testid="editor-add-section">
            <Layers /> Secção
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => addBlock("subsection")} data-testid="editor-add-subsection">
            Subsecção
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => addBlock("text")} data-testid="editor-add-text">
            <FileText /> Texto
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => addBlock("pagebreak")} data-testid="editor-add-pagebreak">
            Quebra de página
          </DropdownMenuItem>

          </QuoteEditorMenu>
        </div>
        <details className="quote-settings" data-testid="editor-pricing-settings">
          <summary><span>Definições de orçamentação</span><small>IVA, preços automáticos e margens</small><ChevronDown size={15} aria-hidden="true" /></summary>
          <div className="quote-settings-content">
            <div className="flex flex-wrap items-center gap-1 mr-1 min-w-0 max-w-full" data-testid="bulk-vat-control">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold whitespace-nowrap">{isPT ? "IVA todas as linhas" : "IVA todas as linhas"}</span>
              <select
                value=""
                onChange={(e) => { if (e.target.value !== "") setAllVat(Number(e.target.value)); }}
                data-testid="bulk-vat-select"
                className="rounded-sm border border-border bg-background px-2 h-8 text-sm">
                <option value="">{isPT ? "Aplicar…" : "Aplicar…"}</option>
                {vatRates.map((r) => <option key={r} value={r}>{r === 0 ? (isPT ? "0 % (subcontratação)" : "0 % (subcontratação)") : `${r}%`}</option>)}
              </select>
            </div>
            <OuvrageComposeDialog onAdd={(line) => setLines((ls) => [...ls, { ...blankLine(), ...line, line_kind: "ouvrage", _saveToLib: false }])} />
        <div className="flex items-center gap-2 flex-wrap rounded-sm border border-border/60 bg-secondary/30 px-3 py-2 text-xs" data-testid="editor-library-mode">
          <Library className="h-3.5 w-3.5 text-primary" />
          <span className="font-medium">{isPT ? "Preços automáticos" : "Preços automáticos"}</span>
          <select value={libraryMode} onChange={(e) => saveLibraryMode(e.target.value)}
                  className="h-8 min-w-0 w-full sm:w-auto max-w-full rounded-sm border border-input bg-background px-2 text-xs" data-testid="editor-library-mode-select">
            <option value="shared_first">{isPT ? "ConstruPilot → empresa" : "ConstruPilot → entreprise"}</option>
            <option value="company_first">{isPT ? "Empresa → ConstruPilot" : "Entreprise → ConstruPilot"}</option>
            <option value="company_only">{isPT ? "Só empresa" : "Apenas a empresa"}</option>
          </select>
          <span className="text-muted-foreground">{isPT ? "— usado para orçamentos por voz, foto, vídeo, planta e CCTP." : "— utilizado para orçamentos por ditado, foto, vídeo, projeto e caderno de encargos."}</span>
        </div>

        <div className="flex items-center gap-2 flex-wrap rounded-sm border border-border/60 bg-secondary/30 px-3 py-2 text-xs" data-testid="editor-target-margin">
          <TrendingUp className="h-3.5 w-3.5 text-primary" />
          <span className="font-medium">Margem alvo</span>
          <Input type="number" min="0" max="90" step="1" value={targetMargin || ""} placeholder="ex. 30"
                 onChange={(e) => setTargetMargin(Number(e.target.value) || 0)} onBlur={(e) => saveTargetMargin(e.target.value)}
                 className="rounded-sm h-7 w-20 num text-right" data-testid="editor-target-margin-input" />
          <span className="text-muted-foreground">% — o preço de venda calcula-se automaticamente a partir do custo quando uma linha não tem preço.</span>
          <Button size="sm" variant="ghost" className="h-7 rounded-sm gap-1 ml-auto" onClick={() => setShowLotMargins((s) => !s)} data-testid="editor-lot-margins-toggle">
            <Layers className="h-3.5 w-3.5" /> Por lote {Object.keys(lotMargins).length ? `(${Object.keys(lotMargins).length})` : ""}
          </Button>
          <Button size="sm" variant="ghost" className="h-auto min-h-7 max-w-full whitespace-normal text-left py-1 rounded-sm gap-1 text-primary" onClick={applyTargetMargin} data-testid="editor-apply-target-margin">
            <TrendingUp className="h-3.5 w-3.5" /> Aplicar às linhas sem preço
          </Button>
          {showLotMargins && (
            <div className="w-full grid sm:grid-cols-2 lg:grid-cols-3 gap-2 pt-2 border-t border-border/50" data-testid="editor-lot-margins">
              {[...new Set([...Object.keys(lotMargins), ...lotSubtotals.map((s) => s.cat)])].map((cat) => (
                <label key={cat} className="flex items-center gap-2">
                  <span className="flex-1 truncate">{cat}</span>
                  <Input type="number" min="0" max="90" step="1" value={lotMargins[cat] ?? ""} placeholder={`${targetMargin || "—"}`}
                         onChange={(e) => setLotMargins((m) => ({ ...m, [cat]: e.target.value }))}
                         onBlur={(e) => { const v = Number(e.target.value); const next = { ...lotMargins }; if (v > 0) next[cat] = v; else delete next[cat]; saveLotMargins(next); }}
                         className="rounded-sm h-7 w-20 num text-right" data-testid={`editor-lot-margin-input-${cat}`} />
                  <span className="text-muted-foreground">%</span>
                </label>
              ))}
              <label className="flex items-center gap-2">
                <Input list="qe-lots" placeholder="Adicionar uma especialidade…" className="rounded-sm h-7 flex-1"
                       onKeyDown={(e) => { if (e.key === "Enter" && e.currentTarget.value.trim()) { const c = e.currentTarget.value.trim(); setLotMargins((m) => ({ ...m, [c]: m[c] ?? (targetMargin || 30) })); e.currentTarget.value = ""; } }}
                       data-testid="editor-lot-margin-add" />
              </label>
              <p className="text-[10px] text-muted-foreground sm:col-span-2 lg:col-span-3">Deixe vazio para utilizar a margem global. A especialidade de uma linha deduz-se do campo «Especialidade».</p>
            </div>
          )}
        </div>

        {fiscal?.known && fiscal.reduced_hint && (
          <div className="flex items-start gap-2 rounded-sm border border-primary/30 bg-primary/5 px-3 py-2 text-xs" data-testid="fiscal-policy-hint">
            <div className="flex-1">
              <b>Regime de IVA da empresa: {fiscal.country} — taxa normal {fiscal.default_rate} %.</b> {fiscal.reduced_hint}
              {lines.some((l) => l.vat_suggestion) && <span className="block mt-1">Sugestão a partir do texto: {lines.find((l) => l.vat_suggestion).vat_suggestion} % — {lines.find((l) => l.vat_suggestion).vat_suggestion_reason}</span>}
            </div>
            {lines.some((l) => l.vat_suggestion) && (
              <Button size="sm" variant="outline" onClick={() => setAllVat(lines.find((l) => l.vat_suggestion).vat_suggestion)}
                      className="rounded-sm h-7 text-xs shrink-0 text-primary border-primary/40" data-testid="fiscal-apply-suggestion">
                Confirmar {lines.find((l) => l.vat_suggestion).vat_suggestion} %
              </Button>
            )}
          </div>
        )}

          </div>
        </details>

        {lotOrder.length >= 2 && (
          <details className="quote-settings" data-testid="editor-lot-reorder"><summary>Organizar os capítulos<ChevronDown size={15} aria-hidden="true" /></summary><div className="quote-settings-content">
            <div className="flex items-center gap-2 flex-wrap">
              <Layers className="h-3.5 w-3.5 text-primary shrink-0" />
              <span className="font-medium mr-1">Ordem dos capítulos</span>
              {lotOrder.map((cat, k) => (
                <span key={cat} className="inline-flex items-center gap-1 rounded-sm border border-border bg-background pl-2 pr-1 py-0.5" data-testid={`editor-lot-chip-${cat}`}>
                  <span className="truncate max-w-[140px]">{cat}</span>
                  <button type="button" onClick={() => moveLot(cat, -1)} disabled={k === 0}
                          title="Subir o capítulo" className="text-muted-foreground hover:text-primary disabled:opacity-30" data-testid={`editor-lot-up-${cat}`}>
                    <ChevronUp className="h-3.5 w-3.5" />
                  </button>
                  <button type="button" onClick={() => moveLot(cat, 1)} disabled={k === lotOrder.length - 1}
                          title="Descer o capítulo" className="text-muted-foreground hover:text-primary disabled:opacity-30" data-testid={`editor-lot-down-${cat}`}>
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>
                </span>
              ))}
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">Mover um capítulo agrupa e reordena todas as suas linhas de uma vez. Arraste uma linha pela pega para a ordem fina.</p>
          </div></details>
        )}

        {assistantOrigin && <div className="border-l-2 border-primary pl-3 text-sm grid gap-2 mb-4" data-testid="editor-assistant-origin"><p>{quoteText("source")}{assistantOrigin.client ? ` · ${quoteText("client")}: ${assistantOrigin.client}` : ""}</p>{lines.some(l => l.price_missing || l.quantity_missing) && <p className="text-amber-700 dark:text-amber-400" data-testid="editor-partial-total-warning">{quoteText("missing")}</p>}{assistantOrigin.conversation && <button className="text-primary underline text-left w-fit" data-testid="editor-assistant-conversation" onClick={() => nav(`/assistant?conversation=${assistantOrigin.conversation}`)}>{quoteText("source")} →</button>}</div>}
        {lines.map((l, i) => {
          const num = blockNumbers[i];
          const dragProps = {
            onDragOver: (e) => { if (dragIdxRef.current != null) { e.preventDefault(); if (dragOverIdx !== i) setDragOverIdx(i); } },
            onDrop: (e) => { e.preventDefault(); reorderLine(dragIdxRef.current, i); dragIdxRef.current = null; setDragIdx(null); setDragOverIdx(null); },
          };
          const dragCls = `${dragOverIdx === i && dragIdx != null && dragIdx !== i ? "bg-primary/5 border-t-2 border-t-primary" : ""} ${dragIdx === i ? "opacity-50" : ""}`;
          const Actions = () => (
            <div className="flex items-center gap-0.5 shrink-0">
              <span draggable onDragStart={(e) => { dragIdxRef.current = i; setDragIdx(i); e.dataTransfer.effectAllowed = "move"; }}
                    onDragEnd={() => { dragIdxRef.current = null; setDragIdx(null); setDragOverIdx(null); }}
                    title="Arrastar para reordenar" className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-primary touch-none px-0.5"
                    data-testid={`editor-line-drag-${i}`}><GripVertical className="h-4 w-4" /></span>
              <div className="flex flex-col">
                <button type="button" onClick={() => moveLine(i, -1)} disabled={i === 0} title="Subir"
                        className="h-4 flex items-center text-muted-foreground hover:text-primary disabled:opacity-30" aria-label={`Subir a linha ${i + 1}`} data-testid={`editor-line-up-${i}`}><ChevronUp className="h-3.5 w-3.5" /></button>
                <button type="button" onClick={() => moveLine(i, 1)} disabled={i === lines.length - 1} title="Descer"
                        className="h-4 flex items-center text-muted-foreground hover:text-primary disabled:opacity-30" aria-label={`Descer a linha ${i + 1}`} data-testid={`editor-line-down-${i}`}><ChevronDown className="h-3.5 w-3.5" /></button>
              </div>
              <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive" onClick={() => delLine(i)} aria-label={`Eliminar a linha ${i + 1}`} data-testid={`editor-line-del-${i}`}><Trash2 className="h-4 w-4" /></Button>
            </div>
          );
          const wrap = (el) => (<Fragment key={i}>{el}<InlineInserter index={i} onInsert={insertBlock} /></Fragment>);

          if (l.kind === "section" || l.kind === "subsection") {
            const isSec = l.kind === "section";
            return wrap(
              <div key={i} {...dragProps} className={`quote-section-row flex items-center gap-2 rounded-sm px-3 py-2 transition-colors ${isSec ? "bg-primary/10 border border-primary/30" : "bg-secondary/40 ml-4"} ${dragCls}`} data-testid={`editor-line-${i}`}>
                <span className="num text-sm font-bold text-primary w-12 shrink-0">{num}</span>
                <Input value={l.title || ""} onChange={(e) => setLine(i, "title", e.target.value)}
                       placeholder={isSec ? "Título da secção (ex.: Estrutura)" : "Título da subsecção"}
                       className={`rounded-sm border-0 bg-transparent focus-visible:ring-1 ${isSec ? "text-base font-bold" : "text-sm font-semibold"}`}
                       data-testid={`editor-section-title-${i}`} />
                {isSec && sectionSubtotals[i] > 0 && (
                  <span className="num text-sm font-bold text-primary shrink-0" data-testid={`editor-section-subtotal-${i}`}>Subtotal: {eur(sectionSubtotals[i])}</span>
                )}
                <Actions />
              </div>
            );
          }
          if (l.kind === "text") {
            return wrap(
              <div key={i} {...dragProps} className={`flex items-start gap-2 rounded-sm px-3 py-2 border border-dashed border-border ${dragCls}`} data-testid={`editor-line-${i}`}>
                <FileText className="h-4 w-4 text-muted-foreground mt-2 shrink-0" />
                <textarea value={l.text || ""} onChange={(e) => setLine(i, "text", e.target.value)} rows={2} placeholder="Texto livre (parágrafo apresentado no orçamento)…"
                          className="rounded-sm text-sm w-full bg-background border border-input px-3 py-2 resize-y focus:outline-none focus:ring-1 focus:ring-primary" data-testid={`editor-text-${i}`} />
                <div className="pt-1"><Actions /></div>
              </div>
            );
          }
          if (l.kind === "pagebreak") {
            return wrap(
              <div key={i} {...dragProps} className={`flex items-center gap-2 py-1 ${dragCls}`} data-testid={`editor-line-${i}`}>
                <div className="flex-1 border-t-2 border-dashed border-border" />
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Quebra de página</span>
                <div className="flex-1 border-t-2 border-dashed border-border" />
                <Actions />
              </div>
            );
          }

          const KIND_LABEL = { fourniture: "Fornecimento", main_oeuvre: "Mão de obra", ouvrage: "Artigo" };
          const lineHt = (Number(l.qty) || 0) * (Number(l.unit_price_ht) || 0) * (1 - (Number(l.discount_pct) || 0) / 100);
          return wrap(
          <div key={i} {...dragProps}
               className={`quote-line ${dragCls}`}
               data-testid={`editor-line-${i}`}>
            <div className="quote-line-heading">
              <span className="num text-xs font-bold text-muted-foreground w-12 shrink-0" data-testid={`editor-line-num-${i}`}>{num}</span>
              <select value={l.line_kind || "fourniture"} onChange={(e) => setLine(i, "line_kind", e.target.value)}
                      className="rounded-sm border border-border bg-background px-1.5 h-6 text-[11px] font-medium" aria-label={`Tipo de linha ${i + 1}`} data-testid={`editor-line-kind-${i}`}>
                <option value="fourniture">Fornecimento</option>
                <option value="main_oeuvre">Mão de obra</option>
                <option value="ouvrage">Artigo</option>
              </select>
              {l.line_kind === "ouvrage" && (
                <button type="button" onClick={() => setLine(i, "_open", !l._open)}
                        className="inline-flex items-center gap-1 text-[11px] text-primary rounded-sm border border-primary/40 px-1.5 h-6"
                        data-testid={`editor-ouvrage-toggle-${i}`}>
                  {l._open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                  Componentes ({(l.components || []).length})
                </button>
              )}
              <div className="quote-line-actions"><Actions /></div>
            </div>
            <div className="quote-line-fields">
            <label className="quote-field quote-field-designation"><span>{t("crm.col_designation")}</span>
            <Textarea rows={2} value={l.designation} onChange={(e) => setLine(i, "designation", e.target.value)}
                   placeholder={t("crm.col_designation")} className="rounded-sm col-span-2 xl:col-span-4 h-9 min-w-0"
                   data-testid={`editor-line-designation-${i}`} /></label>
            <label className="quote-field"><span>{t("crm.col_qty")}</span>
            <Input type="number" step="0.01" value={l.qty} onChange={(e) => setLine(i, "qty", e.target.value)}
                   className="rounded-sm num h-9 min-w-0 xl:col-span-1 text-right" data-testid={`editor-line-qty-${i}`} /></label>
            <label className="quote-field"><span>{t("crm.col_unit")}</span>
            <select value={l.unit} onChange={(e) => setLine(i, "unit", e.target.value)}
                    className="rounded-sm border border-border bg-background px-2 h-9 text-sm min-w-0 xl:col-span-1" data-testid={`editor-line-unit-${i}`}>
              {[...new Set([...UNITS, l.unit])].filter(Boolean).map((u) => <option key={u} value={u}>{u}</option>)}
            </select></label>
            <label className="quote-field quote-field-price"><span>{t("crm.col_price")}</span>
            <Input type="number" step="0.01" value={l.unit_price_ht} onChange={(e) => setLine(i, "unit_price_ht", e.target.value)}
                   className="rounded-sm num h-9 min-w-0 xl:col-span-2 text-right" data-testid={`editor-line-price-${i}`} /></label>
            <label className="quote-field"><span>Remise (%)</span>
            <div className="xl:col-span-1 relative min-w-0">
              <Input type="number" step="0.01" min="0" max="100" value={l.discount_pct || 0} onChange={(e) => setLine(i, "discount_pct", e.target.value)}
                     className="rounded-sm num h-9 text-right pr-4" title="Remise %" data-testid={`editor-line-discount-${i}`} />
              <span className="absolute right-1.5 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground pointer-events-none">%</span>
            </div></label>
            <label className="quote-field"><span>{t("crm.col_vat")}</span>
            <select value={l.vat_rate ?? ""} onChange={(e) => { const v = e.target.value === "" ? null : Number(e.target.value); setLines((ls) => ls.map((x, j) => (j === i ? { ...x, vat_rate: v, vat_assumed: false, vat_confirmed: v != null } : x))); }}
                    className={`rounded-sm border bg-background px-2 h-9 text-sm min-w-0 xl:col-span-1 ${l.vat_rate == null ? "border-amber-500 text-amber-600" : "border-border"}`} data-testid={`editor-line-vat-${i}`}
                    title={l.vat_suggestion ? `Suggestion : ${l.vat_suggestion} % — ${l.vat_suggestion_reason || "a confirmar"}` : undefined}>
              <option value="">TVA ?</option>
              {[...new Set([...vatRates, ...(l.vat_rate != null ? [Number(l.vat_rate)] : [])])].sort((a, b) => a - b).map((r) => <option key={r} value={r}>{r === 0 ? "0 %" : `${r}%`}</option>)}
            </select></label>
            <div className="quote-field quote-field-total"><span>Total s/ IVA</span>
            <span className="xl:col-span-1 text-right num text-sm font-bold break-words min-w-0" data-testid={`editor-line-total-${i}`}>
              {eur(lineHt)}
            </span>
            </div>
            </div>
            {l.line_kind === "ouvrage" && l._open && (
              <div className="ml-4 rounded-sm border border-primary/20 bg-primary/5 p-2 grid gap-1.5" data-testid={`editor-ouvrage-panel-${i}`}>
                <p className="text-[11px] font-semibold text-muted-foreground">Componentes do artigo — o preço unitário = soma dos componentes</p>
                {(l.components || []).map((c, ci) => (
                  <div key={ci} className={`grid gap-1 rounded-sm transition-colors ${compDragOver === `${i}-${ci}` ? "bg-primary/10 ring-1 ring-primary/40" : ""}`}
                       data-testid={`ouvrage-comp-${i}-${ci}`}
                       onDragOver={(e) => { if (compDragRef.current?.line === i) { e.preventDefault(); if (compDragOver !== `${i}-${ci}`) setCompDragOver(`${i}-${ci}`); } }}
                       onDragLeave={() => { if (compDragOver === `${i}-${ci}`) setCompDragOver(null); }}
                       onDrop={(e) => { e.preventDefault(); const d = compDragRef.current; compDragRef.current = null; setCompDragOver(null); if (d && d.line === i && d.comp !== ci) { const a = [...(l.components || [])]; const [m] = a.splice(d.comp, 1); a.splice(ci, 0, m); setComponents(i, a); } }}>
                    <div className="grid grid-cols-12 gap-1.5 items-center">
                    <select value={c.kind || "fourniture"} onChange={(e) => setComponents(i, (l.components || []).map((x, j) => (j === ci ? { ...x, kind: e.target.value } : x)))}
                            className="col-span-2 rounded-sm border border-border bg-background px-1 h-8 text-[11px]">
                      <option value="fourniture">Fourn.</option>
                      <option value="main_oeuvre">M.O.</option>
                    </select>
                    <Input value={c.designation} onChange={(e) => setComponents(i, (l.components || []).map((x, j) => (j === ci ? { ...x, designation: e.target.value } : x)))}
                           placeholder="Designação do componente" className="col-span-3 rounded-sm h-8 text-xs" data-testid={`ouvrage-comp-desig-${i}-${ci}`} />
                    <Input type="number" step="0.01" value={c.qty} onChange={(e) => setComponents(i, (l.components || []).map((x, j) => (j === ci ? { ...x, qty: e.target.value } : x)))}
                           className="col-span-1 rounded-sm h-8 text-xs num text-right" title="Qtd." />
                    <Input value={c.unit} onChange={(e) => setComponents(i, (l.components || []).map((x, j) => (j === ci ? { ...x, unit: e.target.value } : x)))}
                           className="col-span-1 rounded-sm h-8 text-xs" title="Un." />
                    <Input type="number" step="0.01" value={c.unit_price_ht} onChange={(e) => setComponents(i, (l.components || []).map((x, j) => (j === ci ? { ...x, unit_price_ht: e.target.value } : x)))}
                           className="col-span-2 rounded-sm h-8 text-xs num text-right" title="PU HT" data-testid={`ouvrage-comp-pu-${i}-${ci}`} />
                    <div className="col-span-3 flex items-center justify-end gap-0.5">
                      <span draggable
                            onDragStart={(e) => { compDragRef.current = { line: i, comp: ci }; e.dataTransfer.effectAllowed = "move"; }}
                            onDragEnd={() => { compDragRef.current = null; setCompDragOver(null); }}
                            title="Arrastar para mover" className="cursor-grab text-muted-foreground hover:text-foreground p-0.5" data-testid={`ouvrage-comp-drag-${i}-${ci}`}><GripVertical className="h-3.5 w-3.5" /></span>
                      <button type="button" title="Subir" disabled={ci === 0}
                              onClick={() => { const a = [...(l.components || [])]; [a[ci - 1], a[ci]] = [a[ci], a[ci - 1]]; setComponents(i, a); }}
                              className="text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:pointer-events-none p-0.5" data-testid={`ouvrage-comp-up-${i}-${ci}`}><ChevronUp className="h-3.5 w-3.5" /></button>
                      <button type="button" title="Descer" disabled={ci === (l.components || []).length - 1}
                              onClick={() => { const a = [...(l.components || [])]; [a[ci + 1], a[ci]] = [a[ci], a[ci + 1]]; setComponents(i, a); }}
                              className="text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:pointer-events-none p-0.5" data-testid={`ouvrage-comp-down-${i}-${ci}`}><ChevronDown className="h-3.5 w-3.5" /></button>
                      <button type="button" title="Duplicar"
                              onClick={() => { const a = [...(l.components || [])]; a.splice(ci + 1, 0, { ...c, photos: [...(c.photos || [])] }); setComponents(i, a); toast.success("Componente duplicado"); }}
                              className="text-primary hover:text-primary/70 p-0.5" data-testid={`ouvrage-comp-dup-${i}-${ci}`}><Copy className="h-3.5 w-3.5" /></button>
                      <button type="button" title="Eliminar" onClick={() => setComponents(i, (l.components || []).filter((_, j) => j !== ci))}
                              className="text-destructive hover:text-destructive/70 p-0.5" data-testid={`ouvrage-comp-del-${i}-${ci}`}><Trash2 className="h-3.5 w-3.5" /></button>
                    </div>
                    </div>
                    <div className="flex items-center gap-1.5 pl-2" data-testid={`ouvrage-comp-photos-${i}-${ci}`}>
                      <span className="text-[10px] text-muted-foreground shrink-0">Photos ({(c.photos || []).length}/3)</span>
                      <LinePhotos slug={`comp-${i}-${ci}`} size={38} photos={c.photos} onZoom={setZoomSrc}
                                  onChange={(next) => setComponents(i, (l.components || []).map((x, j) => (j === ci ? { ...x, photos: next } : x)))} />
                    </div>
                  </div>
                ))}
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" className="h-7 rounded-sm gap-1 text-xs" onClick={() => addComponent(i, "fourniture")} data-testid={`ouvrage-add-fourniture-${i}`}><Plus className="h-3 w-3" /> Fornecimento</Button>
                  <Button size="sm" variant="outline" className="h-7 rounded-sm gap-1 text-xs" onClick={() => addComponent(i, "main_oeuvre")} data-testid={`ouvrage-add-mo-${i}`}><Plus className="h-3 w-3" /> Mão de obra</Button>
                  <span className="ms-auto text-xs font-bold num" data-testid={`ouvrage-sum-${i}`}>PU = {eur(Number(l.unit_price_ht) || 0)}</span>
                </div>
              </div>
            )}
            <QuoteLineProvenance line={l} index={i} />
            {l.description && <p className="quote-line-description">{l.description}</p>}
            <details className="quote-line-details">
              <summary>Descrição, fotografias e custos <ChevronDown size={14} aria-hidden="true" /></summary>
              <div className="quote-line-details-content">
            <label className="quote-field"><span>Descrição detalhada</span>
            <textarea value={l.description || ""} onChange={(e) => setLine(i, "description", e.target.value)}
                   placeholder={t("crm.ed_desc_ph")}
                   rows={2}
                   className="rounded-sm text-sm w-full bg-background border border-input px-3 py-2 resize-y focus:outline-none focus:ring-1 focus:ring-primary" data-testid={`editor-line-desc-${i}`} /></label>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] text-muted-foreground shrink-0">Photos ({(l.photos || []).length}/3)</span>
              <LinePhotos slug={String(i)} photos={l.photos} onZoom={setZoomSrc} onChange={(next) => setLine(i, "photos", next)} />
            </div>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[11px] text-muted-foreground">Custo de produção s/ IVA</span>
                <Input type="number" step="0.01" min="0" value={l.cost_price_ht ?? 0}
                       onChange={(e) => setLine(i, "cost_price_ht", e.target.value)}
                       className="rounded-sm h-7 text-xs w-24 num text-right" placeholder="MO + materiais"
                       data-testid={`editor-line-cost-${i}`} />
                {!(Number(l.cost_price_ht) > 0) && (
                  <label className="flex items-center gap-1 text-[11px] text-muted-foreground" title="Assinale se esta linha não tem realmente nenhum custo de produção (caso contrário a margem global continua «custos incompletos»)">
                    <input type="checkbox" checked={!!l.cost_confirmed_zero} onChange={(e) => setLine(i, "cost_confirmed_zero", e.target.checked)} data-testid={`editor-line-cost-zero-${i}`} />
                    custo nulo confirmado
                  </label>
                )}
                {(() => { const m = lineMargin(l); return m ? (
                  <Badge variant="outline" data-testid={`editor-line-margin-${i}`}
                         className={`rounded-sm text-[10px] num h-6 ${m.loss ? "border-red-500 text-red-500 bg-red-500/10" : m.pct < 15 ? "border-amber-500 text-amber-600" : "border-emerald-500 text-emerald-600"}`}>
                    {m.loss ? <><AlertTriangle className="h-3 w-3 mr-1" /> Com prejuízo</> : `marge ${m.pct.toFixed(0)} %`}
                  </Badge>
                ) : null; })()}
              </div>
              <Button size="sm" variant="outline" disabled={aiLineBusy === i || !l.designation.trim()}
                      onClick={() => suggestDescription(i)} data-testid={`editor-line-ai-${i}`}
                      className="rounded-sm gap-1 h-7 text-xs text-primary border-primary/40">
                <Sparkles className={`h-3.5 w-3.5 ${aiLineBusy === i ? "animate-pulse" : ""}`} />
                {aiLineBusy === i ? t("crm.ed_ai_suggesting") : t("crm.ed_ai_suggest")}
              </Button>
            </div>
              </div>
            </details>
          </div>
          );
        })}
        {lines.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">{t("crm.no_lines")}</p>
        )}
        <Dialog open={!!cctpPreview} onOpenChange={(o) => !o && setCctpPreview(null)}>
          <DialogContent className="max-w-lg" data-testid="cctp-lots-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2"><FileText className="h-5 w-5 text-primary" /> Este caderno de encargos cobre várias especialidades</DialogTitle>
              <DialogDescription>Assinale apenas as especialidades que orçamenta. As outras não serão importadas no orçamento.
                {cctpPreview?.remembered > 0 && <span className="block mt-1 text-primary" data-testid="cctp-lots-remembered">Pré-seleção baseada nas suas importações anteriores ({cctpPreview.remembered} lot{cctpPreview.remembered > 1 ? "s" : ""} desmarcado{cctpPreview.remembered > 1 ? "s" : ""} automaticamente).</span>}
              </DialogDescription>
            </DialogHeader>
            {cctpPreview && (
              <>
                <div className="space-y-1 max-h-[50vh] overflow-y-auto">
                  {cctpPreview.lots.map((lot) => {
                    const n = cctpPreview.data.lines.filter((l) => ((l.category || "").trim() || "Outros") === lot).length;
                    const on = cctpPreview.selected.has(lot);
                    return (
                      <label key={lot} className={`flex items-center gap-3 rounded-sm border px-3 py-2 text-sm cursor-pointer ${on ? "border-primary/50 bg-primary/5" : "border-border opacity-70"}`} data-testid={`cctp-lot-${lot}`}>
                        <input type="checkbox" checked={on} className="h-4 w-4 accent-emerald-600"
                               onChange={(e) => setCctpPreview((p) => { const s = new Set(p.selected); e.target.checked ? s.add(lot) : s.delete(lot); return { ...p, selected: s }; })} />
                        <span className="flex-1 truncate">{lot}</span>
                        <Badge variant="outline" className="rounded-sm text-[10px] num">{n} ligne{n > 1 ? "s" : ""}</Badge>
                      </label>
                    );
                  })}
                </div>
                <div className="flex items-center justify-between gap-2 pt-2">
                  <div className="flex gap-2 text-xs">
                    <button type="button" className="underline text-muted-foreground" onClick={() => setCctpPreview((p) => ({ ...p, selected: new Set(p.lots) }))}>Tudo</button>
                    <button type="button" className="underline text-muted-foreground" onClick={() => setCctpPreview((p) => ({ ...p, selected: new Set() }))}>Nenhum</button>
                  </div>
                  <Button onClick={() => applyCctp(cctpPreview.data, cctpPreview.selected, cctpPreview.lots)} disabled={!cctpPreview.selected.size} className="rounded-sm gap-2" data-testid="cctp-lots-confirm">
                    <Plus className="h-4 w-4" /> Importar {cctpPreview.selected.size} lot{cctpPreview.selected.size > 1 ? "s" : ""}
                  </Button>
                </div>
              </>
            )}
          </DialogContent>
        </Dialog>

        <datalist id="qe-lots">
          {knownLots.map((c) => <option key={c} value={c} />)}
        </datalist>
      </div>

      {/* Chantier, validité & échéancier (devis uniquement) */}
      {docType === "quote" && (
        <div className="grid md:grid-cols-2 gap-4" data-testid="editor-quote-extras">
          <div className="surface p-4 grid gap-3 content-start">
            <Label className="flex items-center gap-2 text-sm font-semibold"><MapPin className="h-4 w-4" /> Obra e validade</Label>
            <div>
              <Label className="text-xs text-muted-foreground">Morada da obra</Label>
              <Input value={projectAddress} onChange={(e) => setProjectAddress(e.target.value)} disabled={isFrozen}
                     placeholder="Retomado da obra associada se indicado" className="rounded-sm mt-1" data-testid="editor-project-address" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs text-muted-foreground">Duração das obras</Label>
                <Input value={projectDuration} onChange={(e) => setProjectDuration(e.target.value)} disabled={isFrozen}
                       placeholder="ex.: 3 semanas" className="rounded-sm mt-1" data-testid="editor-project-duration" />
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Arranque</Label>
                <Input value={projectStart} onChange={(e) => setProjectStart(e.target.value)} disabled={isFrozen}
                       placeholder="ex.: A combinar" className="rounded-sm mt-1" data-testid="editor-project-start" />
              </div>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Validade do orçamento</Label>
              <div className="quote-validity-controls flex flex-wrap gap-1 mt-1">
                <Button type="button" size="sm" variant={validityDays > 0 ? "default" : "outline"} disabled={isFrozen}
                        className="rounded-sm h-8 text-xs" onClick={() => setValidityDays(validityDays > 0 ? validityDays : 30)}
                        data-testid="editor-validity-auto">Automático</Button>
                <Button type="button" size="sm" variant={validityDays > 0 ? "outline" : "default"} disabled={isFrozen}
                        className="rounded-sm h-8 text-xs" onClick={() => setValidityDays(0)}
                        data-testid="editor-validity-manual">Data fixa</Button>
                {validityDays > 0 ? (
                  <div className="flex items-center gap-1 text-sm">
                    <Input type="number" min="1" max="365" value={validityDays} onChange={(e) => setValidityDays(e.target.value)} disabled={isFrozen}
                           className="rounded-sm num h-8 w-16" data-testid="editor-validity-days" />
                    <span className="text-xs text-muted-foreground">dias após a emissão</span>
                  </div>
                ) : (
                  <Input type="date" value={validUntil ? validUntil.slice(0, 10) : ""} onChange={(e) => setValidUntil(e.target.value)} disabled={isFrozen}
                         className="rounded-sm h-8" data-testid="editor-validity-date" />
                )}
              </div>
            </div>
          </div>

          <div className="surface p-4 grid gap-2 content-start">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label className="flex items-center gap-2 text-sm font-semibold"><CalendarClock className="h-4 w-4" /> Plano de pagamentos</Label>
              <Button type="button" size="sm" variant="outline" className="rounded-sm h-7 text-[11px]" disabled={isFrozen}
                      onClick={() => setSchedule([{ label: "Na adjudicação", pct: 30 }, { label: "Durante a obra", pct: 40 }, { label: "Na receção", pct: 30 }])}
                      data-testid="editor-schedule-preset">Predefinição 30/40/30</Button>
            </div>
            {(schedule || []).length === 0 && <p className="text-xs text-muted-foreground">Nenhuma prestação. Adicione algumas ou aplique a predefinição 30/40/30.</p>}
            {(schedule || []).map((s, i) => (
              <div key={i} className="flex items-center gap-2" data-testid={`editor-schedule-row-${i}`}>
                <Input value={s.label} disabled={isFrozen} placeholder="Designação (ex.: Na receção)"
                       onChange={(e) => setSchedule((p) => p.map((x, j) => j === i ? { ...x, label: e.target.value } : x))}
                       className="rounded-sm flex-1 h-8 text-sm" data-testid={`editor-schedule-label-${i}`} />
                <Input type="number" min="0" max="100" value={s.pct} disabled={isFrozen}
                       onChange={(e) => setSchedule((p) => p.map((x, j) => j === i ? { ...x, pct: e.target.value } : x))}
                       className="rounded-sm num h-8 w-16" data-testid={`editor-schedule-pct-${i}`} />
                <span className="text-xs text-muted-foreground">%</span>
                <button type="button" disabled={isFrozen} onClick={() => setSchedule((p) => p.filter((_, j) => j !== i))}
                        className="text-muted-foreground hover:text-red-500" data-testid={`editor-schedule-remove-${i}`}><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            ))}
            <div className="flex flex-wrap items-center justify-between gap-2 mt-1">
              <Button type="button" size="sm" variant="ghost" className="rounded-sm h-7 text-xs gap-1 px-2" disabled={isFrozen}
                      onClick={() => setSchedule((p) => [...(p || []), { label: "", pct: 0 }])} data-testid="editor-schedule-add"><Plus className="h-3.5 w-3.5" /> Adicionar uma prestação</Button>
              {(schedule || []).length > 0 && (
                <span className={`text-xs num font-semibold ${scheduleSum === 100 ? "text-emerald-600" : "text-amber-600"}`} data-testid="editor-schedule-sum">
                  Total: {scheduleSum}%{scheduleSum !== 100 ? " (deve somar 100 %)" : ""}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Récap + acompte + notes */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="surface p-4 grid gap-3">
          <div className="flex items-center justify-between gap-2"><Label>{t("crm.notes_cond")}</Label>
            {!isFrozen && <DictateButton testId="editor-notes-dictate" onText={(txt) => setNotes((n) => [n, txt].filter(Boolean).join(" "))} />}</div>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4}
                    className="rounded-sm resize-none" placeholder={t("crm.notes_ph")}
                    data-testid="editor-notes" />
          <div>
            <Label>{t("crm.deposit_pct")}</Label>
            <Input type="number" step="1" min="0" max="100" value={depositPct}
                   onChange={(e) => setDepositPct(e.target.value)} className="rounded-sm num mt-1 max-w-[120px]"
                   data-testid="editor-deposit" />
          </div>
        </div>
        <div className="quote-summary surface p-5 grid gap-2 content-start" data-testid="editor-totals">
          {lotSubtotals.length > 0 && (
            <div className="mb-1 pb-2 border-b border-border" data-testid="editor-lot-subtotals">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5 flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5" /> {t("crm.ed_lot_subtotals")}
              </p>
              {lotSubtotals.map(({ cat, ht, marginPct, loss }) => (
                <div key={cat} className="flex justify-between items-center text-xs py-0.5 gap-2" data-testid={`editor-lot-subtotal-${cat}`}>
                  <span className="text-muted-foreground truncate">{cat}</span>
                  <span className="flex items-center gap-2 shrink-0">
                    {marginPct != null && (
                      <span data-testid={`editor-lot-margin-${cat}`}
                            className={`num text-[10px] px-1.5 rounded-sm ${loss > 0 || marginPct < 0 ? "bg-red-500/10 text-red-500" : marginPct < 15 ? "bg-amber-500/10 text-amber-600" : "bg-emerald-500/10 text-emerald-600"}`}>
                        {loss > 0 ? `${loss} com prejuízo · ` : ""}marge {marginPct.toFixed(0)} %
                      </span>
                    )}
                    <span className="num font-semibold">{eur(ht)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
          {totals.vatUnset > 0 && (
            <p className="rounded-sm px-3 py-2 mb-1 text-xs bg-amber-500/10 border border-amber-500/40 text-amber-700" data-testid="editor-vat-unset-alert">
              {totals.vatUnset} ligne{totals.vatUnset > 1 ? "s" : ""} sem taxa de IVA escolhida — o total c/ IVA é calculado sem IVA nestas linhas.
              {fiscal?.known ? ` Taxa normal ${fiscal.country} : ${fiscal.default_rate} %.` : " Indique o país da empresa no seu perfil para obter as taxas propostas."}
            </p>
          )}
          {totals.margin == null && totals.coverage.known > 0 && (
            <div className="rounded-sm px-3 py-2 mb-1 text-xs bg-amber-500/10 border border-amber-500/40" data-testid="editor-margin-incomplete">
              <div className="flex justify-between font-bold"><span>Custos incompletos</span><span>{totals.coverage.known}/{totals.coverage.total} linhas preenchidas</span></div>
              <div className="flex justify-between text-muted-foreground"><span>Margem nas linhas cobertas ({eur(totals.coverage.coveredHt)} HT)</span><span className="num">{eur(totals.partialMargin)}</span></div>
              <p className="mt-1 text-muted-foreground">A margem global não é apresentada enquanto faltar um custo: introduza-o ou assinale «custo nulo confirmado».</p>
            </div>
          )}
          {totals.margin != null && (
            <div className={`rounded-sm px-3 py-2 mb-1 text-xs ${lossLines > 0 ? "bg-red-500/10 border border-red-500/40" : "bg-emerald-500/10 border border-emerald-500/30"}`} data-testid="editor-margin-block">
              <div className="flex justify-between"><span className="text-muted-foreground">Custo de produção</span><span className="num">{eur(totals.cost)}</span></div>
              <div className="flex justify-between font-bold"><span>Margem previsional</span>
                <span className="num" data-testid="editor-margin-total">{eur(totals.margin)} · {totals.marginPct.toFixed(1)} %</span></div>
              {lossLines > 0 && (
                <p className="flex items-center gap-1 text-red-500 mt-1" data-testid="editor-loss-alert">
                  <AlertTriangle className="h-3.5 w-3.5" /> {lossLines} ouvrage{lossLines > 1 ? "s" : ""} orçamentado{lossLines > 1 ? "s" : ""} com prejuízo
                </p>
              )}
            </div>
          )}
          <div className="flex justify-between text-sm"><span className="text-muted-foreground">{t("crm.total_ht")}</span><span className="num font-bold">{eur(totals.ht)}</span></div>
          {Object.entries(totals.tva).sort((a, b) => a[0] - b[0]).map(([r, v]) => (
            <div key={r} className="flex justify-between text-xs"><span className="text-muted-foreground">{t("crm.col_vat")} {r}%</span><span className="num">{eur(v)}</span></div>
          ))}
          <div className="flex justify-between text-lg border-t border-border pt-2 mt-1">
            <span className="font-display font-bold">{t("crm.total_ttc")}</span>
            <span className="num font-extrabold text-primary" data-testid="editor-ttc">{eur(totals.ttc)}</span>
          </div>
          {Number(depositPct) > 0 && (
            <>
              <div className="flex justify-between text-sm"><span className="text-muted-foreground">{t("crm.deposit")} {depositPct}%</span><span className="num">{eur(totals.dep)}</span></div>
              <div className="flex justify-between text-sm"><span className="text-muted-foreground">{t("crm.remaining")}</span><span className="num font-bold">{eur(totals.remaining)}</span></div>
            </>
          )}
        </div>
      </div>

      {/* Library picker */}
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="max-w-xl" data-testid="editor-library-picker">
          <DialogHeader><DialogTitle>{t("crm.add_from_lib_title")}</DialogTitle></DialogHeader>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input value={pickerQ} onChange={(e) => setPickerQ(e.target.value)} autoFocus
                   placeholder={t("crm.picker_ph")} className="pl-9 rounded-sm"
                   data-testid="editor-picker-search" />
          </div>
          <div className="max-h-[50vh] overflow-y-auto divide-y divide-border mt-2">
            {filteredLib.map((it) => (
              <button key={it.item_id} onClick={() => addFromLib(it)}
                      className="w-full text-left px-2 py-2.5 hover:bg-secondary/30 flex items-center justify-between gap-2"
                      data-testid={`editor-picker-item-${it.item_id}`}>
                <span className="min-w-0">
                  <span className="text-sm font-medium truncate block">{it.designation}</span>
                  <span className="text-[11px] text-muted-foreground">{it.category} · {it.unit}</span>
                </span>
                <Badge variant="outline" className="rounded-sm num shrink-0">{eur(it.unit_price_ht)}</Badge>
              </button>
            ))}
            {filteredLib.length === 0 && <p className="text-sm text-muted-foreground text-center py-6">{t("crm.no_result")}</p>}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={reviewOpen} onOpenChange={(v) => { if (!v) closeReview(); }}>
        <DialogContent className="max-w-md" data-testid="video-review-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><FileVideo className="h-5 w-5 text-primary" /> {t("crm.ed_check_video")}</DialogTitle>
          </DialogHeader>
          {reviewInfo.url && (
            <video src={reviewInfo.url} controls playsInline className="w-full rounded-sm bg-black aspect-video object-contain" data-testid="video-review-preview" />
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-sm border border-border p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1"><FileVideo className="h-3 w-3" /> {t("crm.ed_size")}</p>
              <p className="text-lg font-semibold" data-testid="video-review-size">{reviewInfo.sizeMB.toFixed(1)} Mo</p>
            </div>
            <div className="rounded-sm border border-border p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1"><Clock className="h-3 w-3" /> {t("crm.ed_duration")}</p>
              <p className="text-lg font-semibold" data-testid="video-review-duration">
                {reviewInfo.duration > 0 ? fmtSecs(Math.round(reviewInfo.duration)) : "—"}
              </p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground -mt-1" data-testid="video-review-esttime">
            <Clock className="h-3 w-3 inline mr-1" />
            {t("crm.ed_est_time").replace("{s}", Math.max(12, Math.round((reviewInfo.duration || reviewInfo.sizeMB * 5) * 0.8) + 8))}
          </p>
          {(reviewInfo.duration > 90 || reviewInfo.sizeMB > 30) && (
            <div className="rounded-sm border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-600 flex gap-2" data-testid="video-review-warning">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{t("crm.ed_video_warn")}</span>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeReview} className="rounded-sm" data-testid="video-review-restart">{t("crm.ed_change_video")}</Button>
            <Button onClick={confirmTranscribe} disabled={videoBusy} className="rounded-sm gap-2 bg-primary" data-testid="video-review-transcribe">
              {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} {t("crm.ed_transcribe_now")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={recOpen} onOpenChange={(v) => { if (!v) closeRecorder(); }}>
        <DialogContent className="max-w-lg" data-testid="video-recorder-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {recMode === "audio" ? <Mic className="h-5 w-5 text-primary" /> : <Camera className="h-5 w-5 text-primary" />}
              {recMode === "audio" ? t("crm.ed_dictate_quote") : t("crm.ed_film_site")}
            </DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-1">
            {recMode === "audio"
              ? t("crm.ed_audio_hint")
              : t("crm.ed_video_hint")}
          </p>
          {recMode === "audio" ? (
            <div className="relative bg-secondary/40 rounded-sm overflow-hidden h-40 flex flex-col items-center justify-center gap-3" data-testid="audio-recorder-visual">
              <Mic className={`h-12 w-12 ${recording ? "text-red-500 animate-pulse" : "text-muted-foreground"}`} />
              <div className="text-sm font-mono" data-testid="audio-recorder-timer">{fmtSecs(recSecs)}</div>
              {recording && <div className="text-xs text-muted-foreground">{t("crm.ed_saving")}</div>}
            </div>
          ) : (
            <div className="relative bg-black rounded-sm overflow-hidden aspect-video">
              <video ref={videoElRef} muted playsInline autoPlay className="w-full h-full object-contain" data-testid="video-recorder-preview" />
              {recording && (
                <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/60 text-white text-xs px-2 py-1 rounded-full" data-testid="video-recorder-timer">
                  <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" /> {fmtSecs(recSecs)}
                </div>
              )}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeRecorder} className="rounded-sm" data-testid="video-recorder-cancel">{t("crm.cancel")}</Button>
            {!recording ? (
              <Button onClick={startRec} disabled={!streamReady} className="rounded-sm gap-2 bg-red-600 hover:bg-red-700" data-testid="video-recorder-start">
                {recMode === "audio" ? <Mic className="h-4 w-4" /> : <Video className="h-4 w-4" />} {streamReady ? t("crm.ed_start") : t("crm.ed_initializing")}
              </Button>
            ) : (
              <Button onClick={stopRec} className="rounded-sm gap-2 bg-primary" data-testid="video-recorder-stop">
                <Square className="h-4 w-4" /> {t("crm.ed_stop_gen")}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={transcriptDialog} onOpenChange={setTranscriptDialog}>
        <DialogContent className="max-w-xl" data-testid="video-transcript-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Video className="h-5 w-5 text-primary" /> {t("crm.ed_reread_transcript")}</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-1">
            {t("crm.ed_transcript_hint")}
          </p>
          <Textarea value={transcript} onChange={(e) => setTranscript(e.target.value)} rows={7}
                    data-testid="video-transcript-text" className="rounded-sm text-sm" />
          <div>
            <div className="flex items-center justify-between mb-1">
              <Label className="text-xs">{t("crm.ed_site_photos")}</Label>
              <input type="file" accept="image/*" capture="environment" multiple className="hidden" id="qe-transcript-photos"
                     onChange={(e) => { addTranscriptPhotos(e.target.files); e.target.value = ""; }}
                     data-testid="video-transcript-photo-input" />
              <Button size="sm" variant="outline" onClick={() => document.getElementById("qe-transcript-photos").click()}
                      disabled={transcriptPhotos.length >= 6} className="rounded-sm h-7 text-xs gap-1"
                      data-testid="video-transcript-add-photo">
                <Plus className="h-3 w-3" /> {t("crm.ed_add_photos")}
              </Button>
            </div>
            {transcriptPhotos.length > 0 && (
              <div className="flex flex-wrap gap-2" data-testid="video-transcript-photos">
                {transcriptPhotos.map((src, i) => (
                  <div key={i} className="relative">
                    <img src={src} alt={`photo-${i}`} className="h-14 w-14 object-cover rounded-sm border border-border" />
                    <button onClick={() => setTranscriptPhotos((p) => p.filter((_, k) => k !== i))}
                            className="absolute -top-1.5 -right-1.5 bg-destructive text-white rounded-full h-4 w-4 grid place-items-center text-[10px]"
                            data-testid={`video-transcript-photo-remove-${i}`}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setTranscriptDialog(false)}
                    className="rounded-sm" data-testid="video-transcript-cancel">{t("crm.cancel")}</Button>
            <Button onClick={generateFromTranscript} disabled={transcriptBusy || !transcript.trim()}
                    className="rounded-sm gap-2" data-testid="video-transcript-generate">
              {transcriptBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} {t("crm.ed_gen_quote")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      </div>
      {viewMode !== "editor" && (
        <div className="min-w-0" data-testid="editor-preview-pane">{previewNode}</div>
      )}
      </div>
      {zoomSrc && (
        <div onClick={() => setZoomSrc(null)} data-testid="photo-zoom-overlay"
             className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-6 cursor-zoom-out">
          <img src={zoomSrc} alt="" className="max-h-full max-w-full object-contain rounded shadow-2xl" />
          <button onClick={() => setZoomSrc(null)} data-testid="photo-zoom-close"
                  className="absolute top-4 right-4 text-white/90 hover:text-white"><X className="h-7 w-7" /></button>
        </div>
      )}
    </div>
  );
}

