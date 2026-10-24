import PlanWorkflowHeader, { PlanAnalysisResults } from "@/components/planTakeoff/PlanWorkflowHeader";
import { CadUnitPicker, CadImportInfo } from "@/components/planTakeoff/CadImportInfo";
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import JSZip from "jszip";
import { toast } from "sonner";
import { BrandingDialog } from "@/components/BrandingDialog";
import { MailboxDialog } from "@/components/MailboxDialog";
import { useBilling } from "@/context/BillingContext";
import { useAuth } from "@/context/AuthContext";
import { Lock, Unlock, ClipboardCheck } from "lucide-react";
import { useConfirm } from "@/components/ConfirmProvider";
import { QuoteDialog } from "@/components/planTakeoff/QuoteDialog";
import { Render3dDialog } from "@/components/planTakeoff/Render3dDialog";
import { EstimateDialog } from "@/components/planTakeoff/EstimateDialog";
import { MultiPlanDialog } from "@/components/planTakeoff/MultiPlanDialog";
import PcStudyDialog from "@/components/planTakeoff/PcStudyDialog";
import StructuralTakeoffDialog from "@/components/planTakeoff/StructuralTakeoffDialog";
import ObjectPanel from "@/components/planTakeoff/ObjectPanel";
import PresetPicker from "@/components/planTakeoff/PresetPicker";
import PromptBar from "@/components/PromptBar";
import PinchZoom from "@/components/mobile/PinchZoom";
import RoomEstimateDialog from "@/components/planTakeoff/RoomEstimateDialog";
import { MeasureHelpDialog } from "@/components/planTakeoff/MeasureHelpDialog";
import CotesCheckPanel from "@/components/planTakeoff/CotesCheckPanel";
import { OuvrageComposeDialog } from "@/components/OuvrageComposeDialog";
import { LiveTotalBar } from "@/components/planTakeoff/LiveTotalBar";
import {
  Upload, Ruler, Square, Move, Trash2, RotateCw,
  ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight, Sparkles,
  MousePointer2, Layers, Undo2, Save, Home, Calculator, Search,
  Wand2, Zap, Droplet, FileDown, History, Film, DoorOpen, Copy,
  Hash, StickyNote, Triangle, MountainSnow, X, Mail, Hexagon, Sheet, FileSearch,
  ArrowLeft, Eraser, Plus, ArrowRight, Bot, Minimize2, Contrast, SunMedium, Scissors,
  ScanLine, GitCompare, FileText, Mic, Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { api, eur, num, uploadPlan, waitPlanJob } from "@/lib/api";
import { ChantierContextBar, useChantierContext } from "@/components/chantiers/ChantierContextBar";
import PlanCanvas from "@/components/planTakeoff/PlanCanvas";
import { TOOLS, TOOL_LABELS, COUNTER_COLORS } from "@/components/planTakeoff/planConstants";


// ============ MAIN PAGE ============

const LEVEL_SUGGESTIONS = ["Fundações", "R/C", "R+1", "R+2", "R+3", "Sótão", "Cave"];


// Annotations isolées par plan/page. Les écritures d'une page sont sérialisées.
const EMPTY_ANNOTATIONS = { counters: [], notes: [], angles: [], pitched_surfaces: [] };
const normalizeAnnotations = (value = {}) => Object.fromEntries(
  Object.keys(EMPTY_ANNOTATIONS).map((key) => [key, Array.isArray(value?.[key]) ? value[key] : []])
);
const finitePositive = (value) => Number.isFinite(Number(value)) && Number(value) > 0;
const decimalNumber = (value) => Number(String(value ?? "").trim().replace(",", "."));
const errorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg || "Dado inválido").join(" · ");
  return error?.message || fallback;
};

function usePlanAnnotations(planId, pageIndex) {
  const sessions = useRef(new Map());
  const activeKey = useRef(null);
  const mounted = useRef(true);
  const [, redraw] = useState(0);
  const key = planId ? `${planId}:${pageIndex}` : null;
  activeKey.current = key;
  const notify = useCallback(() => { if (mounted.current) redraw((n) => n + 1); }, []);

  const persist = useCallback((session) => {
    clearTimeout(session.timer);
    session.timer = null;
    const value = session.value;
    const signature = JSON.stringify(value);
    if (!session.pending && signature === session.saved) return Promise.resolve();
    if (session.pending?.signature === signature) return session.pending.promise;
    const promise = session.queue.catch(() => {}).then(async () => {
      if (signature === session.saved) return;
      await api.patch(`/takeoffs/${session.planId}/annotations`, { page_index: session.pageIndex, ...value });
      session.saved = signature;
      session.savedAt = Date.now();
      session.error = null;
    }).catch((error) => {
      session.error = errorMessage(error, "Falha ao guardar");
      toast.error(`Anotações da página ${session.pageIndex + 1} não guardadas: ${session.error}`);
      throw error;
    }).finally(() => {
      if (session.pending?.promise === promise) session.pending = null;
      notify();
    });
    session.queue = promise;
    session.pending = { signature, promise };
    notify();
    return promise;
  }, [notify]);

  const hydrateAnnotations = useCallback((value, force = false) => {
    if (!key) return;
    let session = sessions.current.get(key);
    // Une réponse de lecture ne doit pas écraser un brouillon local non enregistré.
    if (!session || (force && !session.timer && !session.pending && JSON.stringify(session.value) === session.saved)) {
      const normalized = normalizeAnnotations(value);
      session = { planId, pageIndex, value: normalized, saved: JSON.stringify(normalized),
        savedAt: null, error: null, timer: null, pending: null, queue: Promise.resolve() };
      sessions.current.set(key, session);
    }
    notify();
  }, [key, planId, pageIndex, notify]);

  const setAnnotations = useCallback((update) => {
    const session = sessions.current.get(key);
    if (!session || activeKey.current !== key) return;
    session.value = normalizeAnnotations(typeof update === "function" ? update(session.value) : update);
    clearTimeout(session.timer);
    session.timer = setTimeout(() => { persist(session).catch(() => {}); }, 600);
    notify();
  }, [key, persist, notify]);

  const saveAnnotations = useCallback(async () => {
    const session = sessions.current.get(key);
    if (!session) throw new Error("Aguarde o carregamento da página");
    await persist(session);
  }, [key, persist]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => () => {
    const session = sessions.current.get(key);
    if (session) persist(session).catch(() => {});
  }, [key, persist]);

  const flushPlanAnnotations = useCallback(async () => {
    await Promise.all([...sessions.current.values()].filter((item) => item.planId === planId).map(persist));
  }, [planId, persist]);
  const restoreAnnotations = useCallback((pages) => {
    for (const session of sessions.current.values()) {
      if (session.planId !== planId) continue;
      clearTimeout(session.timer);
      session.timer = null;
      session.value = normalizeAnnotations(pages?.[String(session.pageIndex)]);
      session.saved = JSON.stringify(session.value);
      session.error = null;
    }
    notify();
  }, [planId, notify]);

  const session = sessions.current.get(key);
  return { annotations: session?.value || EMPTY_ANNOTATIONS, setAnnotations, hydrateAnnotations,
    saveAnnotations, flushPlanAnnotations, restoreAnnotations, saving: !!(session?.timer || session?.pending), savedAt: session?.savedAt || null,
    annotationSaveError: session?.error || null };
}

export default function PlanTakeoff() {
  const [cadFile, setCadFile] = useState(null);
  const nav = useNavigate();
  const { chantierId, chantier } = useChantierContext();
  const confirmDialog = useConfirm();
  const { user } = useAuth();
  const defaultMargin = Number(user?.target_margin_pct) || null;
  const { tier, has, loading: billingLoading } = useBilling();
  // S3.1 — Pré-visualização ampliada de plantas recentes com pinch-to-zoom
  const [zoomPlan, setZoomPlan] = useState(null);
  // Hook E2E: `?e2e_zoom=<plan_id>&e2e_zoom_name=<filename>` abre o Dialog ao mount
  // para permitir testes Playwright sem conta populada. Zero impacto em produção.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sp = new URLSearchParams(window.location.search);
    const id = sp.get("e2e_zoom");
    if (id) setZoomPlan({ plan_id: id, filename: sp.get("e2e_zoom_name") || "Teste E2E" });
  }, []);
  const [plan, setPlan] = useState(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageData, setPageData] = useState(null);
  const [pageLoading, setPageLoading] = useState(false);
  const [pageError, setPageError] = useState(null);
  const [pageRetry, setPageRetry] = useState(0);
  const [loadedPageKey, setLoadedPageKey] = useState(null);
  const pageKey = plan?.plan_id ? `${plan.plan_id}:${pageIndex}` : null;
  const currentPageKeyRef = useRef(pageKey);
  currentPageKeyRef.current = pageKey;
  const planRef = useRef(plan);
  planRef.current = plan;
  const cadUnitResolverRef = useRef(null);
  const importBatchRef = useRef(false);
  const [tool, setTool] = useState(TOOLS.SELECT);
  const [points, setPoints] = useState([]);
  const [zoom, setZoom] = useState(0.5);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState(0);
  const [locked, setLocked] = useState(false);
  // Cumul mur : additionner plusieurs tronçons (fenêtres/portes = trous exclus)
  const [cumulMode, setCumulMode] = useState(false);
  const [cumulSegments, setCumulSegments] = useState([]);
  const [cumulColor, setCumulColor] = useState(COUNTER_COLORS[0]);
  const [autoColorIdx, setAutoColorIdx] = useState(0);
  const [cumulLabel, setCumulLabel] = useState("");
  const [cumulPoste, setCumulPoste] = useState("");
  const [posteCatalog, setPosteCatalog] = useState([]);
  const [customPosteOpen, setCustomPosteOpen] = useState(false);
  const [customPostes, setCustomPostes] = useState([]);
  const [cpForm, setCpForm] = useState({ label: "", unit: "m2", pu: "" });
  const [chiffrageDialog, setChiffrageDialog] = useState(null); // measurement
  const [chiffragePoste, setChiffragePoste] = useState("");
  const [chiffrageMargin, setChiffrageMargin] = useState(defaultMargin ?? 10);
  const [chiffrageOpts, setChiffrageOpts] = useState({ with_isolation: false, couches: 2, ep_m: 0.05, nb_marches: 0 });
  const [chiffrageResult, setChiffrageResult] = useState(null);
  const [chiffrageLoading, setChiffrageLoading] = useState(false);
  const [pageChiffrage, setPageChiffrage] = useState(null);
  const [priceLibOpen, setPriceLibOpen] = useState(false);
  const [priceLib, setPriceLib] = useState({ prices: [], ratios: [], default_wall_height: 2.5 });
  const [priceLibTab, setPriceLibTab] = useState("prices");
  const [priceLibSaving, setPriceLibSaving] = useState(false);
  const [ceDefaultHeight, setCeDefaultHeight] = useState(2.5);
  // Presets par pièce (sol + plinthes + peinture murs + plafond)
  const [roomPresetOpen, setRoomPresetOpen] = useState(false);
  const [roomPresetIn, setRoomPresetIn] = useState({ area_m2: "", perimeter_m: "", height_m: "", door_deduction_m: "", margin_pct: defaultMargin ?? 10, couches: 2, sol_poste: "carrelage", plafond_poste: "peinture", sol: true, plinthes: true, peinture_murs: true, plafond: true });
  const [roomPresetResult, setRoomPresetResult] = useState(null);
  const [roomPresetLoading, setRoomPresetLoading] = useState(false);
  // Bibliothèque d'ouvrages (compositions complètes réutilisables)
  const [ouvrages, setOuvrages] = useState([]);
  const [saveOuvrageName, setSaveOuvrageName] = useState("");
  const [saveOuvrageShared, setSaveOuvrageShared] = useState(false);
  // Déduction d'ouverture (fenêtre/porte) sur un mur déjà mesuré
  const [deductDraw, setDeductDraw] = useState(null);   // {measurement_id,label} — dessin armé
  const [deductDialog, setDeductDialog] = useState(null); // {measurement_id,label} — saisie clavier
  const [deductWidth, setDeductWidth] = useState("");
  const [deductHeight, setDeductHeight] = useState("");
  const [deductNature, setDeductNature] = useState("");
  const [deductCount, setDeductCount] = useState(1);
  const [wallHeightInput, setWallHeightInput] = useState("");
  const [lastWallHeight, setLastWallHeight] = useState(() => {
    try { const v = Number(localStorage.getItem("cp_last_wall_height")); return finitePositive(v) ? v : 0; }
    catch { return 0; }
  });
  const [highlightMeasures, setHighlightMeasures] = useState(null);
  const [autoRotated, setAutoRotated] = useState(false);
  // P1 — Plein écran + réglage contraste/luminosité du plan
  const [fullscreen, setFullscreen] = useState(false);
  const [planContrast, setPlanContrast] = useState(1.25);
  const [planBrightness, setPlanBrightness] = useState(1.02);
  const [showImgAdjust, setShowImgAdjust] = useState(false);
  // P2 — type de plan pour l'analyse IA : auto / gros œuvre / maison
  const [planKindChoice, setPlanKindChoice] = useState("auto");
  // P3 — Assistant IA d'édition du plan (barre de commande + aperçu/appliquer)
  const [aiCmdOpen, setAiCmdOpen] = useState(false);
  const [aiCmd, setAiCmd] = useState("");
  const [aiCmdBusy, setAiCmdBusy] = useState(false);
  const [aiCmdProposal, setAiCmdProposal] = useState(null);
  const [aiHistory, setAiHistory] = useState([]);
  const [aiTurns, setAiTurns] = useState([]);
  const [aiJustCreated, setAiJustCreated] = useState(null);
  const [aiListening, setAiListening] = useState(false);
  // Redimensionne le canvas quand on bascule en plein écran + Échap pour sortir
  useEffect(() => {
    const t = setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
    if (!fullscreen) return () => clearTimeout(t);
    const onKey = (e) => { if (e.key === "Escape") setFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => { clearTimeout(t); window.removeEventListener("keydown", onKey); };
  }, [fullscreen]);
  const [showDimensionLines, setShowDimensionLines] = useState(true);
  // Iter 57 — QuoterPlan-like annotations (par page)
  const { annotations, setAnnotations, hydrateAnnotations, saveAnnotations, flushPlanAnnotations,
    restoreAnnotations, saving, savedAt,
    annotationSaveError } = usePlanAnnotations(plan?.plan_id, pageIndex);
  const [activeCounterId, setActiveCounterId] = useState(null);
  const [pitchDegrees, setPitchDegrees] = useState(30);
  // Iter 58 (Vague B) — Volet Objets + Modèles Outils
  const [objectPanelOpen, setObjectPanelOpen] = useState(false);
  const [panelFocus, setPanelFocus] = useState(null);
  const [currentPreset, setCurrentPreset] = useState(null);
  // Iter 59 (Vague C) — Focus zoom + Devis pièce
  const [focusRequest, setFocusRequest] = useState(null);
  const [roomEstimate, setRoomEstimate] = useState(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [pendingFiles, setPendingFiles] = useState([]);
  const [importingBatch, setImportingBatch] = useState(false);
  const [groupImport, setGroupImport] = useState({ enabled: false, mode: "new", name: "", groupId: "" });
  const [calibDialog, setCalibDialog] = useState(false);
  const [calibDist, setCalibDist] = useState("");
  const [pendingRoomName, setPendingRoomName] = useState("");
  const [roomDialog, setRoomDialog] = useState(false);
  const [ceilingH, setCeilingH] = useState("2.5");
  const [aiBusy, setAiBusy] = useState(false);
  const [pendingAuto, setPendingAuto] = useState(false);
  const [cvBusy, setCvBusy] = useState(false);
  const [aiActionBusy, setAiActionBusy] = useState(false);
  const [reconcile, setReconcile] = useState(null);
  const [selectedCote, setSelectedCote] = useState(null);
  const [showDeltas, setShowDeltas] = useState(true);
  const [sendEcartsDialog, setSendEcartsDialog] = useState(false);
  const [ecartsEmail, setEcartsEmail] = useState("");
  const [ecartsMessage, setEcartsMessage] = useState("");
  const [sendingEcarts, setSendingEcarts] = useState(false);
  const [msgTemplates, setMsgTemplates] = useState([]);
  const [detectedWalls, setDetectedWalls] = useState(null);
  const [showWalls, setShowWalls] = useState(true);
  const [structure, setStructure] = useState(null);
  const [showStructure, setShowStructure] = useState(true);
  const [structBusy, setStructBusy] = useState(false);
  const [selectedStruct, setSelectedStruct] = useState(null);
  const [descriptif, setDescriptif] = useState(null);
  const [analysisRecap, setAnalysisRecap] = useState(null);
  const [wallHeight, setWallHeight] = useState(2.5);
  const [araseInf, setAraseInf] = useState("");
  const [araseSup, setAraseSup] = useState("");
  const [dalleEp, setDalleEp] = useState(0.20);
  const [voileEp, setVoileEp] = useState(0.20);
  const [acierRatios, setAcierRatios] = useState({ semelles: 40, poteaux: 130, poutres: 140, dalles: 85, voiles: 60 });
  const [poutreL, setPoutreL] = useState(0.20);
  const [poutreH, setPoutreH] = useState(0.40);
  const [acierPriceKg, setAcierPriceKg] = useState(1.3);
  const [betonPriceM3, setBetonPriceM3] = useState(130);
  const [betonPrices, setBetonPrices] = useState({ semelles: 130, proprete: 90, poteaux: 130, poutres: 130, dalles: 130, voiles: 130 });
  const [propreteEp, setPropreteEp] = useState(0.05);
  const [plancherType, setPlancherType] = useState("auto");
  const [plancherPriceM2, setPlancherPriceM2] = useState(0);
  const [laborPriceM3, setLaborPriceM3] = useState(400);
  const [marginPct, setMarginPct] = useState(defaultMargin ?? 15);
  const [priceLevel, setPriceLevel] = useState("moyen");
  const [pendingOuvrages, setPendingOuvrages] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("construpilot_pending_ouvrages") || "[]").length; }
    catch { return 0; }
  });
  const addOuvrageFromPlan = (line) => {
    let arr = [];
    try { arr = JSON.parse(sessionStorage.getItem("construpilot_pending_ouvrages") || "[]"); } catch { arr = []; }
    arr.push(line);
    sessionStorage.setItem("construpilot_pending_ouvrages", JSON.stringify(arr));
    setPendingOuvrages(arr.length);
  };

  const refreshPosteCatalog = async () => {
    try { const { data } = await api.get("/takeoffs/corps-etat/catalog"); setPosteCatalog(data.postes || []); } catch { /* */ }
  };
  const loadCustomPostes = async () => {
    try { const { data } = await api.get("/takeoffs/corps-etat/custom"); setCustomPostes(data.custom_postes || []); } catch { /* */ }
  };
  const saveCustomPoste = async () => {
    const label = cpForm.label.trim();
    const pu = Number(cpForm.pu);
    if (!label) return toast.error("Dê um nome ao artigo");
    if (!pu || pu <= 0) return toast.error("Preço unitário inválido");
    try {
      await api.post("/takeoffs/corps-etat/custom", { label, unit: cpForm.unit, pu });
      toast.success(`Artigo « ${label} » adicionado ao catálogo`);
      setCpForm({ label: "", unit: "m2", pu: "" });
      await loadCustomPostes();
      await refreshPosteCatalog();
    } catch (e) { toast.error(e?.response?.data?.detail || "Criação impossível"); }
  };
  const deleteCustomPoste = async (key) => {
    try {
      await api.delete(`/takeoffs/corps-etat/custom/${key}`);
      await loadCustomPostes();
      await refreshPosteCatalog();
      toast.success("Artigo eliminado");
    } catch { toast.error("Não foi possível eliminar"); }
  };

  useEffect(() => {
    api.get("/takeoffs/corps-etat/catalog").then(({ data }) => setPosteCatalog(data.postes || [])).catch(() => {});
    api.get("/takeoffs/corps-etat/prefs").then(({ data }) => {
      if (data?.default_wall_height) setCeDefaultHeight(Number(data.default_wall_height));
    }).catch(() => {});
    loadOuvrages();
  }, []);

  const loadOuvrages = async () => {
    try { const { data } = await api.get("/takeoffs/corps-etat/ouvrages"); setOuvrages(data.ouvrages || []); }
    catch { /* noop */ }
  };

  const applyCumulPoste = (key) => {
    setCumulPoste(key);
    const p = posteCatalog.find((x) => x.key === key);
    if (p) { setCumulColor(p.color); if (!cumulLabel.trim()) setCumulLabel(p.label); }
  };

  // Quantité chiffrable d'une mesure : surface nette de mur > aire > longueur
  const measureQty = (m) => {
    if (m.wall_area_net_m2 != null) return { q: Number(m.wall_area_net_m2), unit: "m²", fam: "area" };
    if (m.area_m2 != null) return { q: Number(m.area_m2), unit: "m²", fam: "area" };
    return { q: Number(m.value_m ?? m.length_m ?? 0), unit: "ml", fam: "length" };
  };

  const openChiffrage = (m) => {
    setChiffrageDialog(m);
    setChiffrageResult(null);
    const { fam } = measureQty(m);
    const guess = m.poste || (fam === "length" ? "plinthes" : "carrelage");
    setChiffragePoste(guess);
  };

  const runChiffrage = async () => {
    if (!chiffrageDialog || !chiffragePoste) return;
    const { q } = measureQty(chiffrageDialog);
    if (!(q > 0)) return toast.error("Quantidade nula nesta medição");
    setChiffrageLoading(true);
    try {
      const opts = {};
      if (chiffragePoste === "placo" || chiffragePoste === "plafond") opts.with_isolation = !!chiffrageOpts.with_isolation;
      if (chiffragePoste === "peinture") opts.couches = Math.max(1, parseInt(chiffrageOpts.couches) || 2);
      if (chiffragePoste === "chape") opts.ep_m = parseFloat(String(chiffrageOpts.ep_m).replace(",", ".")) || 0.05;
      if (chiffragePoste === "escalier") opts.nb_marches = Math.max(0, parseInt(chiffrageOpts.nb_marches) || 0);
      const { data } = await api.post("/takeoffs/corps-etat/estimate",
        { poste: chiffragePoste, quantity: q, params: { margin_pct: Number(chiffrageMargin) || 0, ...opts } });
      setChiffrageResult(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Orçamentação impossível"); }
    setChiffrageLoading(false);
  };

  const updateChiffrageLinePu = (idx, pu) => {
    setChiffrageResult((r) => {
      if (!r) return r;
      const lines = r.lines.map((l, i) => i === idx ? { ...l, pu: Number(pu) || 0, total: Math.round((Number(pu) || 0) * l.qty * 100) / 100 } : l);
      const ht = Math.round(lines.reduce((s, l) => s + l.total, 0) * 100) / 100;
      const htm = Math.round(ht * (1 + (r.totals.margin_pct || 0) / 100) * 100) / 100;
      const tva = Math.round(htm * r.totals.tva_rate * 100) / 100;
      return { ...r, lines, totals: { ...r.totals, ht, ht_with_margin: htm, tva, ttc: Math.round((htm + tva) * 100) / 100 } };
    });
  };

  // Le prix de vente transféré au devis DOIT inclure la marge configurée (l.pu est le prix
  // coûtant HT, avant marge ; totals.ht_with_margin = ht * (1 + marge%)). On applique donc
  // la marge au prix unitaire pour que le devis corresponde au total annoncé.
  const sellingPu = (pu, marginPct) =>
    Math.round((Number(pu) || 0) * (1 + (Number(marginPct) || 0) / 100) * 100) / 100;

  const addChiffrageToDevis = () => {
    if (!chiffrageResult) return;
    const cat = chiffrageResult.label;
    const margin = chiffrageResult.totals?.margin_pct || 0;
    chiffrageResult.lines.forEach((l) => {
      addOuvrageFromPlan({ line_kind: "ouvrage", designation: l.designation,
        description: l.detail, qty: l.qty, unit: l.unit === "m²" ? "m2" : l.unit,
        unit_price_ht: sellingPu(l.pu, margin), category: cat });
    });
    toast.success(`${chiffrageResult.lines.length} linha(s) « ${cat} » adicionadas ao orçamento (${chiffrageResult.totals.ht_with_margin} € s/ IVA)`, { duration: 6000 });
    setChiffrageDialog(null); setChiffrageResult(null);
  };

  // Chiffrer la page : propose un poste par cote (auto), l'utilisateur valide, puis chiffrage
  const chiffrerPage = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/corps-etat/suggest-postes`,
        { page_index: pageIndex });
      if (!data.rows?.length) return toast.error("Nenhuma cota orçamentável nesta página (trace áreas ou paredes com altura).");
      setAutoPosteDialog({ rows: data.rows.map((r) => ({ ...r, poste: r.suggested_poste })) });
    } catch (e) { toast.error(e?.response?.data?.detail || "Análise das cotas impossível"); }
  };

  const confirmAutoPoste = async () => {
    if (!autoPosteDialog?.rows?.length || !plan?.plan_id) return;
    try {
      await api.post(`/takeoffs/${plan.plan_id}/corps-etat/assign-postes`,
        { assignments: autoPosteDialog.rows.map((r) => ({ measurement_id: r.measurement_id, poste: r.poste })) });
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/corps-etat/estimate-page`,
        { page_index: pageIndex, margin_pct: Number(chiffrageMargin) || 0 });
      setAutoPosteDialog(null);
      if (!data.count) return toast.error("Orçamentação vazia: verifique os artigos escolhidos.");
      setPageChiffrage(data);
      toast.success(`${data.count} cota(s) orçamentada(s)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Orçamentação impossível"); }
  };

  const addPageChiffrageToDevis = () => {
    if (!pageChiffrage) return;
    let n = 0;
    pageChiffrage.items.forEach((it) => it.lines.forEach((l) => {
      addOuvrageFromPlan({ line_kind: "ouvrage", designation: l.designation,
        description: `${it.label || it.label} — ${l.detail}`, qty: l.qty,
        unit: l.unit === "m²" ? "m2" : l.unit, unit_price_ht: sellingPu(l.pu, it.totals?.margin_pct), category: it.label });
      n++;
    }));
    toast.success(`${n} linha(s) adicionada(s) ao orçamento (${pageChiffrage.totals.ht_with_margin} € s/ IVA) — clique em «Criar um orçamento»`, { duration: 7000 });
    setPageChiffrage(null);
  };

  // Bibliothèque de prix & ratios de l'artisan
  const loadPriceLib = async () => {
    try {
      const { data } = await api.get("/takeoffs/corps-etat/prefs");
      setPriceLib(data);
    } catch { /* noop */ }
  };
  useEffect(() => { if (priceLibOpen) loadPriceLib(); }, [priceLibOpen]);

  const setPriceLibValue = (kind, key, value) => {
    setPriceLib((lib) => ({ ...lib, [kind]: lib[kind].map((r) => r.key === key ? { ...r, value: value } : r) }));
  };
  const savePriceLib = async () => {
    setPriceLibSaving(true);
    try {
      const prices = {}; const ratios = {};
      priceLib.prices.forEach((r) => { const v = parseFloat(String(r.value).replace(",", ".")); if (v >= 0) prices[r.key] = v; });
      priceLib.ratios.forEach((r) => { const v = parseFloat(String(r.value).replace(",", ".")); if (v >= 0) ratios[r.key] = v; });
      const dwh = parseFloat(String(priceLib.default_wall_height).replace(",", ".")) || ceDefaultHeight;
      await api.put("/takeoffs/corps-etat/prefs", { prices, ratios, default_wall_height: dwh });
      setCeDefaultHeight(dwh);
      toast.success("Biblioteca guardada — aplicada em cada orçamentação");
      setPriceLibOpen(false);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar"); }
    setPriceLibSaving(false);
  };

  // ---- Presets par pièce : sol + plinthes + peinture murs + plafond ----
  const openRoomPreset = (m) => {
    // Pré-remplit depuis une mesure si fournie (aire → area, périmètre non dispo → 0)
    const patch = { height_m: "", margin_pct: Number(chiffrageMargin) || 0 };
    if (m) {
      if (m.area_m2 != null) patch.area_m2 = Number(m.area_m2).toFixed(2);
      if (m.perimeter_m != null) patch.perimeter_m = Number(m.perimeter_m).toFixed(2);
    }
    setRoomPresetIn((s) => ({ ...s, ...patch }));
    setRoomPresetResult(null);
    setRoomPresetOpen(true);
  };

  const runRoomPreset = async () => {
    const s = roomPresetIn;
    const area = parseFloat(String(s.area_m2).replace(",", ".")) || 0;
    if (!(area > 0)) return toast.error("Indique a área da divisão (m²)");
    setRoomPresetLoading(true);
    try {
      const body = {
        area_m2: area,
        perimeter_m: parseFloat(String(s.perimeter_m).replace(",", ".")) || 0,
        height_m: s.height_m ? (parseFloat(String(s.height_m).replace(",", ".")) || null) : null,
        door_deduction_m: parseFloat(String(s.door_deduction_m).replace(",", ".")) || 0,
        margin_pct: Number(s.margin_pct) || 0,
        couches: Math.max(1, parseInt(s.couches) || 2),
        sol_poste: s.sol_poste, plafond_poste: s.plafond_poste,
        include: { sol: !!s.sol, plinthes: !!s.plinthes, peinture_murs: !!s.peinture_murs, plafond: !!s.plafond },
      };
      const { data } = await api.post("/takeoffs/corps-etat/room-preset", body);
      if (!data.count) return toast.error("Nenhum artigo a orçamentar (verifique as caixas e as dimensões)");
      setRoomPresetResult(data);
    } catch (e) { toast.error(errorMessage(e, "Cálculo da predefinição impossível")); }
    finally { setRoomPresetLoading(false); }
  };

  const addRoomPresetToDevis = () => {
    if (!roomPresetResult) return;
    let n = 0;
    roomPresetResult.items.forEach((it) => it.lines.forEach((l) => {
      addOuvrageFromPlan({ line_kind: "ouvrage", designation: l.designation,
        description: `${it.slot} (${it.label}) — ${l.detail}`, qty: l.qty,
        unit: l.unit === "m²" ? "m2" : l.unit, unit_price_ht: sellingPu(l.pu, it.totals?.margin_pct), category: it.slot });
      n++;
    }));
    toast.success(`${n} linha(s) adicionada(s) ao orçamento (${roomPresetResult.totals.ht_with_margin} € s/ IVA) — clique em «Criar um orçamento»`, { duration: 7000 });
    setRoomPresetOpen(false); setRoomPresetResult(null);
  };

  // ---- Bibliothèque d'ouvrages : sauver / appliquer une composition complète ----
  const currentChiffrageOpts = () => {
    const opts = {};
    if (chiffragePoste === "placo" || chiffragePoste === "plafond") opts.with_isolation = !!chiffrageOpts.with_isolation;
    if (chiffragePoste === "peinture") opts.couches = Math.max(1, parseInt(chiffrageOpts.couches) || 2);
    if (chiffragePoste === "chape") opts.ep_m = parseFloat(String(chiffrageOpts.ep_m).replace(",", ".")) || 0.05;
    if (chiffragePoste === "escalier") opts.nb_marches = Math.max(0, parseInt(chiffrageOpts.nb_marches) || 0);
    return opts;
  };

  const saveCurrentAsOuvrage = async () => {
    if (!chiffragePoste) return toast.error("Escolha primeiro um artigo");
    const name = saveOuvrageName.trim();
    if (!name) return toast.error("Dê um nome ao artigo");
    try {
      await api.post("/takeoffs/corps-etat/ouvrages", {
        name, poste: chiffragePoste,
        params: currentChiffrageOpts(), margin_pct: Number(chiffrageMargin) || 0,
        shared: saveOuvrageShared });
      toast.success(`Artigo « ${name} » guardado${saveOuvrageShared ? " e partilhado com a equipa" : ""} — reutilizável em todas as suas obras`);
      setSaveOuvrageName("");
      loadOuvrages();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar"); }
  };

  const applyOuvrage = (ov) => {
    setChiffragePoste(ov.poste);
    setChiffrageMargin(ov.margin_pct ?? 10);
    setChiffrageOpts((o) => ({ ...o, ...(ov.params || {}) }));
    toast.success(`Artigo « ${ov.name} » aplicado — clique em «Calcular»`);
  };

  const deleteOuvrage = async (ouvrage_id) => {
    if (!(await confirmDialog({ title: "Eliminar este artigo?", description: "Esta composição guardada será retirada da sua biblioteca." }))) return;
    try { await api.delete(`/takeoffs/corps-etat/ouvrages/${ouvrage_id}`); loadOuvrages(); toast.success("Artigo eliminado"); }
    catch { toast.error("Não foi possível eliminar"); }
  };

  const [marginBeton, setMarginBeton] = useState("");
  const [marginAcier, setMarginAcier] = useState("");
  const [marginLabor, setMarginLabor] = useState("");
  const [betonPresets, setBetonPresets] = useState([]);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareBusy, setCompareBusy] = useState(false);
  const [compareData, setCompareData] = useState(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisMode, setAnalysisMode] = useState("complete");
  const [analysisProgress, setAnalysisProgress] = useState("");
  const analysisLock = useRef(false);
  useEffect(() => {
    if ((plan?.page_count || 1) < 2 && analysisMode === "structure_all") setAnalysisMode("complete");
  }, [plan?.page_count, analysisMode]);
  useEffect(() => {
    if (!plan?.plan_id) { setDescriptif(null); return; }
    const s = plan.structure?.[String(pageIndex)];
    if (!s || !(s.walls?.length || s.openings?.length || s.beams?.length || s.floors?.length || s.columns?.length || s.footings?.length)) { setDescriptif(null); return; }
    let cancel = false;
    const aqa = (araseInf !== "" && araseSup !== "" && Number(araseSup) > Number(araseInf))
      ? `&arase_inf=${araseInf}&arase_sup=${araseSup}` : "";
    const aq = `&acier_semelles=${acierRatios.semelles}&acier_poteaux=${acierRatios.poteaux}&acier_poutres=${acierRatios.poutres}&acier_dalles=${acierRatios.dalles}&acier_voiles=${acierRatios.voiles}&poutre_l=${poutreL}&poutre_h=${poutreH}&proprete_ep=${propreteEp}`;
    api.get(`/takeoffs/${plan.plan_id}/analysis/${pageIndex}?wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${aq}${aqa}`)
      .then(({ data }) => { if (!cancel) setDescriptif(data.descriptif); }).catch(() => {});
    return () => { cancel = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan?.plan_id, plan?.structure, pageIndex, wallHeight, dalleEp, voileEp, acierRatios, poutreL, poutreH, propreteEp, araseInf, araseSup]);
  const [deskewEnabled, setDeskewEnabled] = useState(false);
  const [rightTab, setRightTab] = useState("rooms");
  const [planDefaults, setPlanDefaults] = useState({ ceiling_h_m: 2.5, floor_thickness_m: 0.15 });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [openingsDialog, setOpeningsDialog] = useState(null); // room_id
  const [pendingOpening, setPendingOpening] = useState({
    kind: "fenetre", width_m: 1.2, height_m: 1.0, count: 1, label: "",
  });
  const [takeoff, setTakeoff] = useState(null);
  const [materials, setMaterials] = useState(null);
  const [floorMaterial, setFloorMaterial] = useState("parquet");
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [labelDialog, setLabelDialog] = useState(null); // {snapshot_id, label}
  const [labelValue, setLabelValue] = useState("");
  const [quoteDialog, setQuoteDialog] = useState(false);
  const [quoteFinish, setQuoteFinish] = useState("std");
  const [quoteFloor, setQuoteFloor] = useState("carrelage");
  const [quoteBusy, setQuoteBusy] = useState(false);
  const [quoteMode, setQuoteMode] = useState("download"); // download | send
  const [quoteClientEmail, setQuoteClientEmail] = useState("");
  const [quoteClientName, setQuoteClientName] = useState("");
  const [quoteMessage, setQuoteMessage] = useState("");
  const [quoteSubject, setQuoteSubject] = useState("");
  const [quoteIntro, setQuoteIntro] = useState("");
  const [quoteClientAddress, setQuoteClientAddress] = useState("");
  const [quoteIncludeTva, setQuoteIncludeTva] = useState(true);
  const [quoteAttachVideo, setQuoteAttachVideo] = useState(false);
  const [latestVideo, setLatestVideo] = useState(null);
  const [estimateDialog, setEstimateDialog] = useState(false);
  const [estimateResult, setEstimateResult] = useState(null);
  const [estimateBusy, setEstimateBusy] = useState(false);
  const [estProjectType, setEstProjectType] = useState("renovation_complete");
  const [estFinishLevel, setEstFinishLevel] = useState("standard");
  // 3D render
  const [render3dDialog, setRender3dDialog] = useState(false);
  const [render3dStyle, setRender3dStyle] = useState("isometric");
  const [render3dFurniture, setRender3dFurniture] = useState(true);
  const [render3dBusy, setRender3dBusy] = useState(false);
  const [render3dImg, setRender3dImg] = useState(null);
  const [plan3dSnapshot, setPlan3dSnapshot] = useState(null);
  const [render3dHistory, setRender3dHistory] = useState([]);
  const [render3dMode, setRender3dMode] = useState("ai"); // ai | interactive | video
  const [credits3d, setCredits3d] = useState(null);
  const [creditPaywall, setCreditPaywall] = useState(null);
  // Video Tour (multi-styles) — assemble 4 IA renders into an MP4
  const [videoBusy, setVideoBusy] = useState(false);
  const [videoUrl, setVideoUrl] = useState(null);
  const [videoHistory, setVideoHistory] = useState([]);
  const [currentVideoId, setCurrentVideoId] = useState(null);
  const [videoAddWatermark, setVideoAddWatermark] = useState(true);
  const [videoAddMusic, setVideoAddMusic] = useState(true);
  const [wallsSummary, setWallsSummary] = useState(null);
  const [reclassifyMode, setReclassifyMode] = useState(false);
  const [snapPickA, setSnapPickA] = useState(null);
  const [snapPickB, setSnapPickB] = useState(null);
  const [snapCompareResult, setSnapCompareResult] = useState(null);
  // Templates
  const [templates, setTemplates] = useState([]);
  const [templateName, setTemplateName] = useState("");
  const [templateShared, setTemplateShared] = useState(false);
  // Multi-plan quote
  const [multiDialog, setMultiDialog] = useState(false);
  const [multiSelected, setMultiSelected] = useState([]);
  const [multiProjectName, setMultiProjectName] = useState("");
  const [multiBusy, setMultiBusy] = useState(false);
  const [allPlans, setAllPlans] = useState([]);
  const [planGroups, setPlanGroups] = useState([]);
  const [recentDialog, setRecentDialog] = useState(false);
  const [selectedRecent, setSelectedRecent] = useState([]);
  const [groupBuilder, setGroupBuilder] = useState(null);
  const [groupView, setGroupView] = useState(null);
  const [coverDialog, setCoverDialog] = useState(null);
  const [agentBox, setAgentBox] = useState(null);
  const [autoPosteDialog, setAutoPosteDialog] = useState(null);
  const [metreVerOpen, setMetreVerOpen] = useState(false);
  const [metreVersions, setMetreVersions] = useState([]);
  const [metreLabel, setMetreLabel] = useState("");
  const [metreSel, setMetreSel] = useState([]);
  const [metreCompare, setMetreCompare] = useState(null);
  // Phase A — devis consolidé : sous-traitance (0% TVA) par plan + lien ferraillage
  const [subcontractSel, setSubcontractSel] = useState([]);
  const [consolidatedBusy, setConsolidatedBusy] = useState(false);
  // Quote sends (envois + tracking)
  const [quoteSends, setQuoteSends] = useState([]);
  const fileRef = useRef(null);

  const rawCalibration = plan?.calibrations?.[String(pageIndex)];
  const currentCalib = finitePositive(rawCalibration?.pixels_per_meter) ? rawCalibration : null;
  const pageMeasurements = useMemo(
    () => (plan?.measurements || []).filter((m) => m.page_index === pageIndex),
    [plan, pageIndex]
  );
  // Cumul (mur OU surface) — total en direct
  const cumulValue = useCallback((list, isArea) => {
    const ppm = currentCalib?.pixels_per_meter || 0;
    if (!ppm) return 0;
    if (isArea) {
      let a = 0;
      for (const poly of list) {
        if (poly.length < 3) continue;
        let s = 0;
        for (let i = 0; i < poly.length; i++) {
          const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length];
          s += x1 * y2 - x2 * y1;
        }
        a += Math.abs(s) / 2 / (ppm * ppm);
      }
      return a;
    }
    let t = 0;
    for (const seg of list) {
      for (let i = 1; i < seg.length; i++) {
        t += Math.hypot(seg[i][0] - seg[i - 1][0], seg[i][1] - seg[i - 1][1]) / ppm;
      }
    }
    return t;
  }, [currentCalib]);
  const cumulIsArea = tool === TOOLS.SURFACE;
  const cumulTotal = useMemo(
    () => ({ value: cumulValue(cumulSegments, cumulIsArea), unit: cumulIsArea ? "m²" : "m" }),
    [cumulSegments, cumulValue, cumulIsArea]
  );
  // Fix revue iter63 : les cotes IA ne s'affichent que sur la page analysée
  const aiDimLines = useMemo(() => {
    const ai = plan?.ai_analysis;
    if (!ai || (ai.page_index != null && ai.page_index !== pageIndex)) return [];
    return ai.dimension_lines || [];
  }, [plan, pageIndex]);
  // Contrôle des cotes : cotes contrôlées de la page (dessinées sur le canvas, cliquables)
  const [selectedCheckedCote, setSelectedCheckedCote] = useState(null);
  const checkedCotes = useMemo(() => plan?.cotes_checks?.[String(pageIndex)]?.items || [],
                               [plan, pageIndex]);
  const focusCheckedCote = useCallback((it) => {
    if (!it) return;
    setSelectedCheckedCote(it.index);
    setFocusRequest({ px: (it.x1 + it.x2) / 2, py: (it.y1 + it.y2) / 2, zoom: 2.2, ts: Date.now() });
  }, []);
  useEffect(() => { setSelectedCheckedCote(null); }, [pageIndex]);
  const rooms = useMemo(() => (plan?.rooms || []).filter((r) => r.page_index === pageIndex),
                        [plan, pageIndex]);

  const planVariables = useMemo(() => {
    const surf = rooms.reduce((s, r) => s + (Number(r.surface_m2) || 0), 0);
    const peri = rooms.reduce((s, r) => s + (Number(r.perimeter_m) || 0), 0);
    if (!surf && !peri) return null;
    const rnd = (x) => Math.round(x * 100) / 100;
    return {
      surface_m2: rnd(surf), surface_nette_m2: rnd(surf), surface_toiture_m2: rnd(surf),
      perimetre_ml: rnd(peri), longueur_ml: rnd(peri), hauteur_m: wallHeight,
    };
  }, [rooms, wallHeight]);

  // Charger plans + projets dès l'ouverture (le switcher d'en-tête reste toujours à jour)
  useEffect(() => { loadAllPlans(); loadPlanGroups(); }, []);

  // 2+ plans importés → bascule automatiquement en projet multi-niveaux
  useEffect(() => {
    if (pendingFiles.length >= 2 && !groupImport.enabled) {
      setGroupImport((g) => ({ ...g, enabled: true, mode: "new", name: g.name || "Projeto multinível" }));
    }
  }, [pendingFiles.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Une réponse lente d'une autre page ne doit jamais modifier la page affichée.
  useEffect(() => {
    let cancelled = false;
    setPageData(null); setLoadedPageKey(null); setPageError(null);
    setPoints([]); setCumulSegments([]); setCumulMode(false); setDeductDraw(null);
    setDeductDialog(null); setRoomDialog(false); setCalibDialog(false); setOpeningsDialog(null);
    setOffset({ x: 0, y: 0 }); setZoom(0.5); setRotation(0); setAutoRotated(false);
    setDetectedWalls(null); setSelectedStruct(null); setActiveCounterId(null);
    setSelectedCote(null); setSelectedCheckedCote(null); setReconcile(null);
    setAnalysisRecap(null); setTakeoff(null); setMaterials(null); setEstimateResult(null);
    setPageChiffrage(null); setChiffrageDialog(null); setRoomEstimate(null);
    setAiCmdProposal(null); setAiHistory([]); setAiTurns([]); setAiJustCreated(null); setAiMessages([]);
    setTool(TOOLS.SELECT);
    if (!plan?.plan_id) { setPageLoading(false); return; }
    setPageLoading(true);
    api.get(`/takeoffs/${plan.plan_id}/page/${pageIndex}`).then(({ data }) => {
      if (cancelled || currentPageKeyRef.current !== pageKey) return;
      if (!data || typeof data !== "object") throw new Error("Resposta de página inválida");
      hydrateAnnotations(planRef.current?.annotations?.[String(pageIndex)]);
      setPageData(data); setLoadedPageKey(pageKey);
    }).catch((error) => {
      if (!cancelled && currentPageKeyRef.current === pageKey) {
        setPageError(errorMessage(error, "Impossível carregar esta página"));
      }
    }).finally(() => { if (!cancelled) setPageLoading(false); });
    return () => { cancelled = true; };
  }, [plan?.plan_id, pageIndex, pageKey, pageRetry, hydrateAnnotations]);

  useEffect(() => {
    setStructure(plan?.structure?.[String(pageIndex)] || null);
  }, [plan?.structure, plan?.plan_id, pageIndex]);

  useEffect(() => {
    setPlanDefaults({ ceiling_h_m: plan?.plan_defaults?.ceiling_h_m ?? 2.5,
      floor_thickness_m: plan?.plan_defaults?.floor_thickness_m ?? 0.15 });
  }, [plan?.plan_id, plan?.plan_defaults]);

  const manualSave = useCallback(async () => {
    try { await saveAnnotations(); toast.success("Anotações guardadas"); }
    catch (error) { toast.error(errorMessage(error, "Falha no registo")); }
  }, [saveAnnotations]);

  const refreshPlan = useCallback(async () => {
    const id = plan?.plan_id;
    if (!id) return null;
    const { data } = await api.get(`/takeoffs/${id}`);
    if (planRef.current?.plan_id === id) {
      setPlan(data);
      if (currentPageKeyRef.current === `${id}:${pageIndex}`) hydrateAnnotations(data.annotations?.[String(pageIndex)], true);
    }
    return data;
  }, [plan?.plan_id, pageIndex, hydrateAnnotations]);

  // Deep-link ?open=<plan_id> (depuis le Tableau de bord PC / création de devis)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const pid = params.get("open");
    if (!pid) return;
    api.get(`/takeoffs/${pid}`).then(({ data }) => {
      setPlan(data);
      setPageIndex(0);
      if (data.pc_study || params.get("study") === "1") setPcDialog(true);
      if (params.get("auto") === "1") setPendingAuto(true);
      const hl = params.get("highlight");
      if (hl) {
        const ids = hl.split(",").map((s) => s.trim()).filter(Boolean);
        setHighlightMeasures(new Set(ids));
        if (ids.length) { setObjectPanelOpen(true); toast.message(`${ids.length} artigo(s) com diferença realçado(s) na planta`, { duration: 6000 }); }
      }
    }).catch(() => toast.error("Impossível abrir este plano"));
  }, []);

  const savePlanDefaults = async (next) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/defaults`, next);
      setPlanDefaults(next);
      toast.success(`Definições: parede ${next.ceiling_h_m} m · pavimento ${(next.floor_thickness_m * 100).toFixed(0)} cm`);
    } catch { toast.error("Não foi possível guardar"); }
  };

  const chooseCadUnit = (unit) => {
    const resolve = cadUnitResolverRef.current;
    cadUnitResolverRef.current = null;
    setCadFile(null);
    resolve?.(unit);
  };
  useEffect(() => () => { cadUnitResolverRef.current?.(null); }, []);

  const uploadFile = async (file, cadUnit, displayName) => {
    setCadFile(null);
    if (!file) return null;
    if (file.size > 20 * 1024 * 1024) { toast.error(`« ${displayName || file.name} » demasiado grande (>20 MB)`); return null; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (cadUnit) fd.append("cad_unit", cadUnit);
      if (deskewEnabled) fd.append("deskew", "true");
      if (displayName && displayName.trim()) fd.append("display_name", displayName.trim());
      const data = await uploadPlan(fd, { onStatus: (_j, sec) => sec >= 20 && sec % 10 === 0 && toast.message(`A analisar a planta… ${sec} s (DWG e PDF multipágina: vários minutos possíveis)`, { id: "plan-upload-progress" }) });
      if (chantierId && data?.plan_id) api.post(`/chantiers/${chantierId}/attach`, { kind: "plan", ref_id: data.plan_id }).then(() => toast.success("Planta associada ao processo de obra")).catch(() => toast.error("Planta importada, mas a associação ao processo foi impossível"));
      setPlan(data);
      setPageIndex(0);
      const kind = data.kind === "dxf" ? "DXF" : data.kind === "pdf" ? "PDF" : "image";
      toast.success(`${kind} carregado (${data.page_count} page${data.page_count > 1 ? "s" : ""})`);
      return data;
    } catch (e) {
      if (!cadUnit && typeof e?.response?.data?.detail === "string" && e.response.data.detail.includes("CAD_UNIT_REQUIRED")) {
        const unit = await new Promise((resolve) => {
          cadUnitResolverRef.current = resolve;
          setCadFile(file);
        });
        return unit ? await uploadFile(file, unit, displayName) : null;
      }
      const detail = e?.response?.data?.detail;
      const msg = detail
        || (!e?.response ? "Rede indisponível ou ficheiro demasiado pesado — verifique a sua ligação e tente novamente"
                         : "Não foi possível importar");
      toast.error(`« ${displayName || file.name} » — ${msg}`);
      return null;
    } finally { setUploading(false); }
  };

  // Détection auto du niveau depuis le nom du fichier (RDC, R+1, sous-sol…)
  const detectLevel = (fname, idx) => {
    const n = (fname || "").toLowerCase();
    if (/combl|toitur/.test(n)) return "Sótão";
    if (/fondation|semelle/.test(n)) return "Fundações";
    if (/sous[\s_-]?sol|\bss\b|\bs\.?sol\b/.test(n)) return "Cave";
    if (/\b(rdc|rez)\b|rez[\s_-]?de[\s_-]?chauss|\br0\b/.test(n)) return "R/C";
    const m = n.match(/\br\s*\+?\s*([1-6])\b|(?:etage|étage|niveau|niv)\s*([1-6])|\b([1-6])(?:er|e|eme|ème)\b/);
    if (m) { const d = m[1] || m[2] || m[3]; return `R+${d}`; }
    return LEVEL_SUGGESTIONS[idx] || "";
  };

  const SUPPORTED_RE = /\.(pdf|dxf|dwg|jpe?g|png|webp)$/i;

  // Expande les ZIP côté client puis met en file (dossier/zip/fichiers)
  const ingestFiles = async (fileList) => {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;
    const expanded = [];
    for (const f of incoming) {
      if (/\.zip$/i.test(f.name)) {
        try {
          const zip = await JSZip.loadAsync(f);
          const entries = Object.values(zip.files).filter((e) => !e.dir && SUPPORTED_RE.test(e.name));
          for (const e of entries) {
            const blob = await e.async("blob");
            const base = e.name.split("/").pop();
            expanded.push(new File([blob], base, { type: blob.type || "application/octet-stream" }));
          }
          if (!entries.length) toast.error(`Nenhuma planta suportada em ${f.name}`);
        } catch { toast.error(`ZIP ilegível: ${f.name}`); }
      } else if (SUPPORTED_RE.test(f.name)) {
        expanded.push(f);
      }
    }
    if (expanded.length) queueFiles(expanded);
    else toast.error("Nenhum ficheiro de planta reconhecido");
  };

  // Import multiple : file d'attente avec nom éditable avant import
  const queueFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    const baseName = (f) => (f.name || "plan").replace(/\.[^.]+$/, "");
    // Ajoute à la file existante (permet de charger plusieurs plans en plusieurs sélections)
    setPendingFiles((prev) => {
      const existing = new Set(prev.map((p) => `${p.file?.name}_${p.file?.size}`));
      const added = files
        .filter((f) => !existing.has(`${f.name}_${f.size}`))
        .map((f, i) => ({ id: `${Date.now()}_${prev.length + i}`, file: f, name: baseName(f),
                          level: detectLevel(f.name, prev.length + i) }));
      return [...prev, ...added];
    });
  };

  const importPending = async () => {
    if (!pendingFiles.length || importBatchRef.current) return;
    importBatchRef.current = true;
    setImportingBatch(true);
    const completed = new Set();
    try {
    let ok = 0;
    const uploaded = [];
    for (const item of pendingFiles) {
      const res = await uploadFile(item.file, null, item.name);
      if (res && res.plan_id) { ok++; completed.add(item.id); uploaded.push({ plan_id: res.plan_id, level_label: item.level || "" }); }
    }
    // Option : regrouper les plans en projet multi-niveaux (nouveau ou existant) → 1 rapport
    let createdGroup = null;
    if (groupImport.enabled && uploaded.length >= 1) {
      try {
        if (groupImport.mode === "existing" && groupImport.groupId) {
          const existing = planGroups.find((g) => g.group_id === groupImport.groupId);
          const prevLevels = (existing?.levels || []).map((l) => ({ plan_id: l.plan_id, level_label: l.level_label || "" }));
          const newLevels = uploaded.map((u, i) => ({ plan_id: u.plan_id, level_label: u.level_label || LEVEL_SUGGESTIONS[prevLevels.length + i] || `Piso ${prevLevels.length + i + 1}` }));
          await api.put(`/takeoffs/multilevel/groups/${groupImport.groupId}`, {
            name: existing?.name || "Projeto", chantier_id: existing?.chantier_id || null,
            levels: [...prevLevels, ...newLevels],
          });
          createdGroup = { group_id: groupImport.groupId, name: existing?.name || "Projeto" };
        } else if (groupImport.name.trim()) {
          const { data } = await api.post("/takeoffs/multilevel/groups", {
            name: groupImport.name.trim(),
            levels: uploaded.map((u, i) => ({ plan_id: u.plan_id, level_label: u.level_label || LEVEL_SUGGESTIONS[i] || `Piso ${i + 1}` })),
          });
          const gid = data?.group?.group_id;
          if (gid) createdGroup = { group_id: gid, name: groupImport.name.trim() };
        }
      } catch (e) { toast.error("Plantas importadas, mas a atualização do projeto multinível foi impossível"); }
    }
    setPendingFiles((items) => items.filter((item) => !completed.has(item.id)));
    if (completed.size === pendingFiles.length) setGroupImport({ enabled: false, mode: "new", name: "", groupId: "" });
    else if (createdGroup) setGroupImport((g) => ({ ...g, mode: "existing", groupId: createdGroup.group_id }));
    loadAllPlans();
    loadPlanGroups();
    if (createdGroup) {
      toast.success(`Projeto « ${createdGroup.name} » — ${uploaded.length} piso${uploaded.length > 1 ? "s" : ""} adicionado${uploaded.length > 1 ? "s" : ""}`);
      openGroupConsolidated(createdGroup);
    } else if (ok > 1) toast.success(`${ok} plantas importadas`);
    else if (ok === 0) toast.error("Nenhuma planta importada — os ficheiros continuam disponíveis para tentar novamente");
    } finally { importBatchRef.current = false; setImportingBatch(false); }
  };

  const onCanvasClick = (pt) => {
    if (loadedPageKey !== pageKey || pageLoading || pageError) return;
    // Reclassify mode : cherche le mur le plus proche (distance point-segment)
    if (reclassifyMode && detectedWalls?.segments?.length) {
      const [px, py] = pt;
      let best = -1, bestD = 999;
      detectedWalls.segments.forEach((s, i) => {
        // distance point → segment
        const dx = s.x2 - s.x1, dy = s.y2 - s.y1;
        const len2 = dx * dx + dy * dy;
        const t = len2 ? Math.max(0, Math.min(1, ((px - s.x1) * dx + (py - s.y1) * dy) / len2)) : 0;
        const cx = s.x1 + t * dx, cy = s.y1 + t * dy;
        const d = Math.hypot(px - cx, py - cy);
        if (d < bestD) { bestD = d; best = i; }
      });
      if (best >= 0 && bestD < 15) {
        reclassifyWall(best);
      } else {
        toast.info("Nenhuma parede próxima (clique mais perto)");
      }
      return;
    }
    if (tool === TOOLS.AUTOROOM) {
      autoFillRoom(pt);
      return;
    }
    if (tool === TOOLS.CALIB) {
      const next = [...points, pt];
      if (next.length === 2) {
        setPoints(next);
        setCalibDialog(true);
        return;
      }
      setPoints(next);
    } else if (tool === TOOLS.DIST) {
      setPoints([...points, pt]);
    } else if (tool === TOOLS.POLY || tool === TOOLS.ROOM || tool === TOOLS.SURFACE) {
      setPoints([...points, pt]);
    } else if (tool === TOOLS.OPENING) {
      const next = [...points, pt];
      if (next.length === 2) {
        // Width computed from click distance in meters, opening dialog for kind + height
        if (!currentCalib) return toast.error("Calibre primeiro a planta");
        const ppm = Number(currentCalib.pixels_per_meter);
        const px_dist = Math.hypot(next[1][0] - next[0][0], next[1][1] - next[0][1]);
        const width_m = Math.max(0.05, Math.round((px_dist / ppm) * 100) / 100);
        // Find the closest room to the midpoint
        const mid = [(next[0][0] + next[1][0]) / 2, (next[0][1] + next[1][1]) / 2];
        let bestRoom = null, bestDist = Infinity;
        for (const r of rooms) {
          if (r.page_index !== pageIndex || !Array.isArray(r.points) || !r.points.length) continue;
          const cx = r.points.reduce((a, p) => a + p[0], 0) / r.points.length;
          const cy = r.points.reduce((a, p) => a + p[1], 0) / r.points.length;
          const d = Math.hypot(mid[0] - cx, mid[1] - cy);
          if (d < bestDist) { bestDist = d; bestRoom = r; }
        }
        if (!bestRoom) {
          toast.error("Nenhuma divisão próxima — trace primeiro uma divisão");
          setPoints([]);
          return;
        }
        setOpeningsDialog({ room_id: bestRoom.room_id, room_name: bestRoom.name });
        setPendingOpening({
          kind: "fenetre",
          width_m,
          height_m: 1.2,
          count: 1,
          label: "",
        });
        setPoints(next);
        return;
      }
      setPoints(next);
    } else if (tool === TOOLS.COUNTER) {
      // Ajoute un marqueur au compteur actif (créer un compteur par défaut si aucun)
      let counterId = activeCounterId;
      let list = annotations.counters;
      if (!counterId || !list.find(c => c.id === counterId)) {
        const nb = list.length;
        const newC = {
          id: `cnt_${Date.now()}`,
          label: `Contador ${nb + 1}`,
          color: COUNTER_COLORS[nb % COUNTER_COLORS.length],
          unit: "u",
          markers: [],
        };
        list = [...list, newC];
        counterId = newC.id;
        setActiveCounterId(counterId);
      }
      const updated = list.map(c =>
        c.id === counterId
          ? { ...c, markers: [...c.markers, { x: pt[0], y: pt[1] }] }
          : c
      );
      setAnnotations({ ...annotations, counters: updated });
    } else if (tool === TOOLS.NOTE) {
      const text = window.prompt("Nota (máx. 60 caracteres):", "");
      if (text === null) return;
      const trimmed = (text || "").slice(0, 60);
      setAnnotations({
        ...annotations,
        notes: [...annotations.notes, {
          id: `nt_${Date.now()}`, x: pt[0], y: pt[1], text: trimmed || "Nota"
        }],
      });
      toast.success("Nota adicionada");
    } else if (tool === TOOLS.ANGLE) {
      const next = [...points, pt];
      if (next.length === 3) {
        // Vertex = 2nd click, arms = 1st and 3rd
        const [a, v, b] = next;
        const v1 = [a[0] - v[0], a[1] - v[1]];
        const v2 = [b[0] - v[0], b[1] - v[1]];
        const dot = v1[0] * v2[0] + v1[1] * v2[1];
        const m1 = Math.hypot(...v1), m2 = Math.hypot(...v2);
        const cosT = Math.max(-1, Math.min(1, dot / (m1 * m2 || 1)));
        const deg = (Math.acos(cosT) * 180) / Math.PI;
        setAnnotations({
          ...annotations,
          angles: [...annotations.angles, {
            id: `ang_${Date.now()}`,
            vx: v[0], vy: v[1], ax: a[0], ay: a[1], bx: b[0], by: b[1],
            degrees: deg,
          }],
        });
        toast.success(`Angle : ${deg.toFixed(1)}° · inclinação ${(Math.tan(deg * Math.PI / 180) * 12).toFixed(1)}/12`);
        setPoints([]);
      } else {
        setPoints(next);
      }
    } else if (tool === TOOLS.PITCH) {
      // Same polygon logic as ROOM but applies a pitch factor
      setPoints([...points, pt]);
    }
  };

  const applyCalibration = async () => {
    const dist = parseFloat(calibDist.replace(",", "."));
    if (!finitePositive(dist)) return toast.error("Distância inválida");
    if (!plan?.plan_id || points.length !== 2 || Math.hypot(points[1][0] - points[0][0], points[1][1] - points[0][1]) <= 0) {
      return toast.error("Selecione dois pontos distintos na planta");
    }
    try {
      await api.post(`/takeoffs/${plan.plan_id}/calibrate`, {
        page_index: pageIndex, p1: points[0], p2: points[1],
        real_distance_m: dist, method: "two_points",
      });
      toast.success(`Calibration : ${dist} m em ${num(Math.hypot(points[1][0] - points[0][0], points[1][1] - points[0][1]), 0)} px`);
      setCalibDialog(false);
      setCalibDist("");
      setPoints([]);
      await refreshPlan();
      setTool(TOOLS.SELECT);
    } catch (e) { toast.error(e?.response?.data?.detail || "Calibração falhada"); }
  };

  const submitOpening = async () => {
    if (!openingsDialog) return;
    const w = decimalNumber(pendingOpening.width_m);
    const h = decimalNumber(pendingOpening.height_m);
    if (!finitePositive(w) || !finitePositive(h)) return toast.error("Dimensões inválidas");
    try {
      await api.post(
        `/takeoffs/${plan.plan_id}/rooms/${openingsDialog.room_id}/openings`,
        {
          kind: pendingOpening.kind,
          width_m: w, height_m: h,
          count: Math.max(1, parseInt(pendingOpening.count) || 1),
          label: pendingOpening.label || null,
        }
      );
      toast.success(
        `${pendingOpening.kind === "porte" ? "Porta" : pendingOpening.kind === "baie" ? "Vão" : "Janela"} `
        + `${w}×${h} m adicionada a ${openingsDialog.room_name}`
      );
      setOpeningsDialog(null);
      setPoints([]);
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível adicionar"); }
  };

  const deleteOpening = async (room_id, opening_id) => {
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/rooms/${room_id}/openings/${opening_id}`);
      toast.success("Abertura eliminada");
      await refreshPlan();
    } catch { toast.error("Não foi possível eliminar"); }
  };

  // Couleur auto : chaque mesure reçoit une couleur différente de la palette
  const pickAutoColor = () => {
    const c = COUNTER_COLORS[autoColorIdx % COUNTER_COLORS.length];
    setAutoColorIdx((i) => i + 1);
    return c;
  };

  const finishPolyline = async (pts = points) => {
    if (pts.length < 2) return;
    if (!currentCalib) return toast.error("Calibre primeiro a planta");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polyline", points: pts, color: pickAutoColor(),
      });
      toast.success(`Comprimento: ${data.length_m} m — memorizada`);
      setPoints([]);
      setPanelFocus("measures"); setObjectPanelOpen(true);
      await refreshPlan();
    } catch (e) { toast.error("Medição falhou"); }
  };

  const finishPitchSurface = () => {
    if (points.length < 3) return toast.error("Clique pelo menos 3 pontos");
    if (!currentCalib) return toast.error("Calibre primeiro a planta");
    const ppm = currentCalib.pixels_per_meter;
    // Shoelace formula in pixel space
    let sum = 0;
    for (let i = 0; i < points.length; i++) {
      const [x1, y1] = points[i];
      const [x2, y2] = points[(i + 1) % points.length];
      sum += x1 * y2 - x2 * y1;
    }
    const projected_area_m2 = Math.abs(sum) / (2 * ppm * ppm);
    const pitch = Math.max(0, Math.min(80, pitchDegrees));
    const real_area_m2 = projected_area_m2 / Math.max(0.05, Math.cos((pitch * Math.PI) / 180));
    setAnnotations({
      ...annotations,
      pitched_surfaces: [...annotations.pitched_surfaces, {
        id: `pit_${Date.now()}`,
        points: [...points],
        projected_area_m2: Math.round(projected_area_m2 * 100) / 100,
        pitch_degrees: pitch,
        real_area_m2: Math.round(real_area_m2 * 100) / 100,
      }],
    });
    setPoints([]);
    toast.success(`Cobertura: ${real_area_m2.toFixed(1)} m² reais (a ${pitch}°)`);
  };

  // ============ VAGUE B — Handlers pour le Volet Objets ============

  const renameRoom = async (roomId, newName) => {
    if (!plan?.plan_id || !newName?.trim()) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/rooms/${roomId}`, { name: newName.trim() });
      await refreshPlan();
      toast.success("Divisão renomeada");
    } catch { toast.error("Renomeação impossível"); }
  };

  const attachPresetToRoom = async (roomId, presetId) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/rooms/${roomId}`, { preset_id: presetId });
      await refreshPlan();
      toast.success(presetId ? "Modelo anexado à divisão" : "Modelo removido");
    } catch (e) { toast.error(e?.response?.data?.detail || "Associação impossível"); }
  };

  const deleteRoomFromPanel = async (roomId) => {
    if (!plan?.plan_id) return;
    if (!window.confirm("Eliminar esta divisão?")) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/rooms/${roomId}`);
      await refreshPlan();
      toast.success("Divisão eliminada");
    } catch { toast.error("Não foi possível eliminar"); }
  };

  const deleteMeasureFromPanel = async (measureId) => {
    if (!plan?.plan_id) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/measurements/${measureId}`);
      await refreshPlan();
      toast.success("Medição eliminada");
    } catch { toast.error("Não foi possível eliminar"); }
  };

  const clearMeasures = async () => {
    if (!plan?.plan_id) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/measurements?page_index=${pageIndex}`);
      await refreshPlan();
      toast.success("Medições da página apagadas");
    } catch { toast.error("Impossível apagar"); }
  };

  // Iter66 — libellé personnalisé (ex. « murs parpaing », « murs en brique »)
  const renameMeasure = async (measureId, label) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/measurements/${measureId}`, { label });
      await refreshPlan();
      toast.success(label ? `Medição renomeada: ${label}` : "Designação apagada");
    } catch { toast.error("Renomeação impossível"); }
  };

  // Couleur personnalisable d'une cote (plancher, murs…)
  const colorMeasure = async (measureId, color) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/measurements/${measureId}`, { color });
      await refreshPlan();
    } catch { toast.error("Cor não guardada"); }
  };

  // Export PDF du relevé des cotes (avec nom du projet)
  const downloadCotesPdf = async () => {
    if (!plan?.plan_id) return;
    try {
      const res = await api.get(`/takeoffs/${plan.plan_id}/cotes-pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cotas-${plan.filename || plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("PDF das cotas transferido");
    } catch { toast.error("Exportação PDF das cotas impossível"); }
  };

  // Iter68 — surface mesurée → pièce complète (1 clic)
  const convertMeasureToRoom = async (measureId) => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measurements/${measureId}/to-room`);
      toast.success(`Divisão criada: ${data.room.name} (${data.room.surface_m2} m²) — paredes e volume calculados`, { duration: 6000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Conversão impossível"); }
  };

  // Iter68 — déduction (trémie, escalier…) de la pièce contenante
  const deductMeasure = async (measureId) => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measurements/${measureId}/deduct`);
      toast.success(`− ${data.deduction.area_m2} m² deduzidos de « ${data.room_name} » → área líquida ${data.surface_m2} m²`, { duration: 7000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Dedução impossível"); }
  };

  const removeDeduction = async (roomId, dedId) => {
    try {
      const { data } = await api.delete(`/takeoffs/${plan.plan_id}/rooms/${roomId}/deductions/${dedId}`);
      toast.success(`Dedução removida — área: ${data.surface_m2} m²`);
      await refreshPlan();
    } catch { toast.error("Não foi possível eliminar"); }
  };

  // Iter68 — export Excel (pièces + mesures)
  const downloadXlsx = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/export-xlsx`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `medicao-${plan.plan_id}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Export Excel transferido");
    } catch (e) { toast.error(e.message || "Exportação Excel impossível"); }
  };

  // Iter69 — Étude Permis de Construire (gros œuvre : béton, aciers, isobrique)
  const [pcDialog, setPcDialog] = useState(false);
  const [structDialog, setStructDialog] = useState(false);
  const [pcBusy, setPcBusy] = useState(false);
  const runPcStudy = async (options = {}) => {
    setPcBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/pc-study`, options);
      toast.success("Estudo lançado em segundo plano. Pode mudar de página.");
      return data;
    } catch (e) { toast.error(e?.response?.data?.detail || "Estudo do projeto de licenciamento impossível"); }
    finally { setPcBusy(false); }
  };
  const downloadPcFile = async (fmt, start) => {
    try {
      const qs = start ? `?start=${start}` : "";
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/pc-study/${fmt}${qs}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `estudo-licenciamento-${plan.plan_id}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Estudo licença de construção ${fmt.toUpperCase()} descarregada`);
    } catch (e) { toast.error(e.message || "Impossível exportar"); }
  };
  const comparePcSuppliers = (study) => {
    const t = study?.totals || {};
    const slabArea = Math.round((study?.inputs?.ground_floor_area_m2 || 0) +
                                (study?.inputs?.upper_floors_area_m2 || 0));
    const items = [
      { name: "Tijolo isobrique 20 cm", search: "tijolo isobrique 20 cm", quantity: t.briques_u || 0, unit: "u" },
      { name: "Aço HA varão para betão", search: "varão HA10 barra 6m", quantity: Math.round(t.acier_kg || 0), unit: "kg" },
      { name: "Malha soldada ST25C", search: "rede soldada ST25C painel", quantity: slabArea, unit: "m²" },
      { name: "Betão pronto a usar C25/30", search: "betão pronto a usar C25/30", quantity: t.beton_m3 || 0, unit: "m³" },
    ].filter((it) => it.quantity > 0);
    if (!items.length) return toast.error("Nenhuma quantidade a comparar — lance primeiro o estudo");
    sessionStorage.setItem("construpilot_price_search_batch", JSON.stringify({
      ts: Date.now(), project_name: `Estudo do projeto de licenciamento — ${plan?.filename || "planta"}`,
      total_avg: t.ht || 0, items,
    }));
    nav("/precos");
  };
  const recomputePcStudy = async () => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/pc-study/recompute`);
      await refreshPlan();
      toast.success(`Orçamento recalculado com as suas definições — ${data.totals?.ttc ?? 0} € c/ IVA`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Recálculo impossível"); }
  };

  // Iter67 — modèles de message réutilisables (envoi de rapports)
  useEffect(() => {
    if (!sendEcartsDialog) return;
    api.get("/emails/templates")
      .then(({ data }) => setMsgTemplates(data.templates || []))
      .catch(() => {});
  }, [sendEcartsDialog]);

  const saveMsgTemplate = async () => {
    const body = ecartsMessage.trim();
    if (!body) return toast.error("Escreva primeiro uma mensagem para registar");
    const name = body.split("\n")[0].slice(0, 40) || "Modelo";
    try {
      const { data } = await api.post("/emails/templates", { name, body });
      setMsgTemplates((prev) => [data.template, ...prev]);
      toast.success(`Modelo guardado: ${data.template.name}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    }
  };

  const deleteMsgTemplate = async (templateId) => {
    try {
      await api.delete(`/emails/templates/${templateId}`);
      setMsgTemplates((prev) => prev.filter((t) => t.template_id !== templateId));
    } catch { toast.error("Não foi possível eliminar"); }
  };

  // Iter66 — renvoi 1 clic depuis l'historique des envois
  const resendReport = async (report) => {
    setSendingEcarts(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/ecarts-pdf/send`, {
        page_index: report.page_index ?? pageIndex,
        to_email: report.to_email,
        message: "",
      });
      toast.success(`Relatório reenviado para ${data.sent_to}`);
      await refreshPlan();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível reenviar");
    } finally { setSendingEcarts(false); }
  };

  const deleteAnnotationLocal = (kind, id) => {
    setAnnotations((prev) => ({
      ...prev,
      [kind]: prev[kind].filter((x) => x.id !== id),
    }));
  };

  const updateAnnotationLocal = (kind, id, patch) => {
    setAnnotations((prev) => ({
      ...prev,
      [kind]: prev[kind].map((x) => x.id === id ? { ...x, ...patch } : x),
    }));
  };

  const focusOnObject = ({ kind, data, room, opening }) => {
    // Compute the object's center in image pixel space, then set focusRequest
    // so PlanCanvas can centre & zoom (Vague C — Focus Zoom on Canvas).
    let cx = null, cy = null;
    if (kind === "room" && data?.polygon?.length) {
      cx = data.polygon.reduce((s, p) => s + p[0], 0) / data.polygon.length;
      cy = data.polygon.reduce((s, p) => s + p[1], 0) / data.polygon.length;
    } else if (kind === "counter" && data?.markers?.length) {
      cx = data.markers.reduce((s, m) => s + m.x, 0) / data.markers.length;
      cy = data.markers.reduce((s, m) => s + m.y, 0) / data.markers.length;
    } else if (kind === "note" && data) {
      cx = data.x; cy = data.y;
    } else if (kind === "angle" && data) {
      cx = data.vx; cy = data.vy;
    } else if (kind === "pitched" && data?.points?.length) {
      cx = data.points.reduce((s, p) => s + p[0], 0) / data.points.length;
      cy = data.points.reduce((s, p) => s + p[1], 0) / data.points.length;
    } else if (kind === "opening" && opening?.position) {
      cx = opening.position[0]; cy = opening.position[1];
    } else if (kind === "measure" && data?.points?.length) {
      cx = data.points.reduce((s, p) => s + p[0], 0) / data.points.length;
      cy = data.points.reduce((s, p) => s + p[1], 0) / data.points.length;
    }
    if (cx != null && cy != null) {
      setFocusRequest({ px: cx, py: cy, zoom: 1.5, ts: Date.now() });
      toast.success(`Zoom em ${kind}`);
    } else {
      toast.info("Posição não disponível para este objeto");
    }
  };

  // Vague C — Génération devis pièce (calculators.py)
  const generateRoomEstimate = async (roomId, opts = {}) => {
    if (!plan?.plan_id) return;
    setEstimateLoading(true);
    try {
      const payload = {};
      if (opts.includeMasonry) {
        payload.trades = ["paint", "floor_tile", "drywall", "insulation", "plinths", "masonry"];
        payload.masonry_material = opts.masonryMaterial || "parpaing";
        payload.masonry_bond = opts.masonryBond || null;
        payload.masonry_block = opts.masonryBlock || null;
        payload.masonry_render = !!opts.masonryRender;
      }
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/rooms/${roomId}/estimate`,
        payload
      );
      setRoomEstimate(data);
      toast.success(`Orçamento da divisão gerado: ${data.total_budget?.toFixed(2)} €`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossível gerar");
    } finally {
      setEstimateLoading(false);
    }
  };

  // Preset application — recolle un preset comme label + prix par unité sur le contexte courant
  const applyPresetToTool = (preset) => {
    setCurrentPreset(preset);
    // Si outil compteur : crée un nouveau compteur avec les params du preset
    if (tool === TOOLS.COUNTER) {
      const nb = annotations.counters.length;
      const newC = {
        id: `cnt_${Date.now()}`,
        label: preset.name,
        color: preset.color || COUNTER_COLORS[nb % COUNTER_COLORS.length],
        unit: preset.unit || "u",
        markers: [],
        preset_id: preset.preset_id,
      };
      setAnnotations({ ...annotations, counters: [...annotations.counters, newC] });
      setActiveCounterId(newC.id);
    }
  };

  const finishDistance = async (pts = points) => {
    if (pts.length < 2) return;
    if (!currentCalib) return toast.error("Calibre primeiro a planta");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "distance", points: pts.slice(0, 2), color: pickAutoColor(),
      });
      toast.success(`Distance : ${data.value_m} m — memorizada. Faça duplo clique para terminar cada nova cota.`);
      setPoints([]);
      setPanelFocus("measures"); setObjectPanelOpen(true);
      await refreshPlan();
    } catch { toast.error("Medição falhou"); }
  };

  const finishRoom = (pts = points) => {
    if (pts.length < 3) return toast.error("Uma divisão necessita pelo menos 3 pontos");
    if (!currentCalib) return toast.error("Calibre primeiro a planta");
    setPoints(pts);
    setPendingRoomName(`Divisão ${String(rooms.length + 1).padStart(2, "0")}`);
    setRoomDialog(true);
  };

  // Iter67 — mesure de surface libre (polygone) en m²
  const finishSurface = async (pts = points) => {
    if (pts.length < 3) return toast.error("Uma superfície necessita pelo menos 3 pontos");
    if (!currentCalib) return toast.error("Calibre primeiro a planta");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polygon", points: pts, color: pickAutoColor(),
      });
      toast.success(`Área: ${data.area_m2} m² · perímetro ${data.perimeter_m} m — memorizada`, { duration: 6000 });
      setPoints([]);
      setPanelFocus("measures"); setObjectPanelOpen(true);
      await refreshPlan();
    } catch { toast.error("Medição de superfície falhou"); }
  };

  // Double-clic gauche : termine la cote/mesure en cours — le clic suivant
  // reprend une nouvelle mesure. Nettoie le point dupliqué par les 2 clics.
  const onCanvasDoubleClick = () => {
    if (loadedPageKey !== pageKey || pageLoading || pageError) return;
    let chain = [...points];
    while (chain.length >= 2) {
      const a = chain[chain.length - 1], b = chain[chain.length - 2];
      if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 3) chain = chain.slice(0, -1);
      else break;
    }
    // Déduction d'ouverture dessinée : la fenêtre tracée est soustraite du mur ciblé
    if (deductDraw && tool === TOOLS.DIST && chain.length >= 2) {
      submitDeductDraw(chain);
      return;
    }
    // Cumul : le double-clic mémorise le tronçon/zone et l'ajoute au total,
    // puis on continue (fenêtre/porte = trou non compté pour un mur).
    if (cumulMode && (tool === TOOLS.DIST || tool === TOOLS.SURFACE)) {
      const need = tool === TOOLS.SURFACE ? 3 : 2;
      if (chain.length >= need) {
        const next = [...cumulSegments, chain];
        setCumulSegments(next);
        setPoints([]);
        const isArea = tool === TOOLS.SURFACE;
        const total = cumulValue(next, isArea);
        const noun = isArea ? "Zona" : "Troço";
        const what = isArea ? "Superfície" : "Parede";
        toast.success(`${noun} ${next.length} adicionada${next.length > 1 ? "" : ""} · ${what} em curso: ${total.toFixed(2)} ${isArea ? "m²" : "m"} — continue ou «Terminar»`, { duration: 5000 });
        return;
      }
    }
    if (tool === TOOLS.DIST && chain.length >= 2) {
      finishDistance(chain);
    } else if (tool === TOOLS.POLY && chain.length >= 2) {
      finishPolyline(chain);
    } else if (tool === TOOLS.SURFACE && chain.length >= 3) {
      finishSurface(chain);
    } else if (tool === TOOLS.ROOM && chain.length >= 3) {
      setPoints(chain);
      finishRoom(chain);
    }
  };

  // Cumul — enregistre UNE cote = somme des tronçons (mur) ou zones (surface)
  const finishCumul = async () => {
    const isArea = tool === TOOLS.SURFACE;
    const need = isArea ? 3 : 2;
    let segs = [...cumulSegments];
    if (points.length >= need) segs = [...segs, points];
    segs = segs.filter((s) => s.length >= need);
    if (!segs.length) return toast.error(isArea ? "Nenhuma zona — meça pelo menos uma zona" : "Nenhum troço — meça pelo menos um troço de parede");
    if (!currentCalib) return toast.error("Calibre primeiro a planta");
    try {
      const flat = segs.flat();
      const payload = isArea
        ? { page_index: pageIndex, kind: "cumulative_area", points: flat, polygons: segs, label: cumulLabel.trim() || null, color: cumulColor, poste: cumulPoste || null }
        : { page_index: pageIndex, kind: "cumulative", points: flat, segments: segs, label: cumulLabel.trim() || null, color: cumulColor, poste: cumulPoste || null };
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, payload);
      if (isArea) toast.success(`Área guardada: ${data.area_m2} m² (${segs.length} zone${segs.length > 1 ? "s" : ""})`, { duration: 6000 });
      else toast.success(`Parede guardada: ${data.value_m} m (${segs.length} troço${segs.length > 1 ? "s" : ""}, vãos excluídos)`, { duration: 6000 });
      setCumulSegments([]); setCumulLabel(""); setCumulPoste(""); setPoints([]);
      setCumulMode(false);
      setCumulColor(pickAutoColor());
      setPanelFocus("measures"); setObjectPanelOpen(true);
      await refreshPlan();
    } catch { toast.error("Não foi possível guardar"); }
  };

  const cancelCumulWall = () => {
    setCumulSegments([]); setCumulLabel(""); setPoints([]);
    toast.message("Acumulação anulada");
  };

  // Déduction d'ouverture — dessinée sur le plan (2 points) sur un mur ciblé.
  // Reste armé après chaque déduction pour enchaîner plusieurs ouvertures.
  const submitDeductDraw = async (chain) => {
    const pts = [chain[0], chain[chain.length - 1]];
    const h = parseFloat(String(deductHeight).replace(",", "."));
    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/measurements/${deductDraw.measurement_id}/deduct-opening`,
        { points: pts, ...(h > 0 ? { height_m: h } : {}) });
      toast.success(`Vão deduzido: −${data.opening.width_m} m → parede líquida ${data.value_m} m — desenhe a seguinte ou «Terminar»`, { duration: 6000 });
    } catch (e) { toast.error(e?.response?.data?.detail || "Dedução impossível"); }
    setPoints([]);
    await refreshPlan();
  };

  // Presets de hauteur d'ouverture par nature (mémorisés) — porte ~2,10 m, fenêtre ~1,15 m
  const openingPresetH = (nature) => {
    const def = nature === "porte" ? 2.1 : nature === "fenetre" ? 1.15 : 0;
    const v = parseFloat(localStorage.getItem(`cp_op_h_${nature}`) || "");
    return v > 0 ? v : def;
  };
  const applyOpeningPreset = (nature) => {
    setDeductNature(nature);
    setDeductHeight(String(openingPresetH(nature)));
  };

  // Déduction d'ouverture — largeur (et hauteur) saisies au clavier (× count)
  const submitDeductTyped = async () => {
    if (!deductDialog) return;
    const w = parseFloat(String(deductWidth).replace(",", "."));
    const h = parseFloat(String(deductHeight).replace(",", "."));
    const c = Math.max(1, parseInt(deductCount) || 1);
    if (!(w > 0)) return toast.error("Largura inválida");
    const label = deductNature === "porte" ? "Porta" : deductNature === "fenetre" ? "Janela" : undefined;
    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/measurements/${deductDialog.measurement_id}/deduct-opening`,
        { width_m: w, count: c, ...(h > 0 ? { height_m: h } : {}), ...(label ? { label } : {}) });
      toast.success(`Vão deduzido: −${(w * c).toFixed(2)} m → parede líquida ${data.value_m} m`, { duration: 6000 });
      if (h > 0 && deductNature) localStorage.setItem(`cp_op_h_${deductNature}`, String(h));
      setDeductWidth(""); setDeductCount(1);
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Dedução impossível"); }
  };

  // Hauteur du mur → calcul automatique des m² (mur brut, ouvertures, mur net)
  // Édition directe du m²/ml d'une cote depuis la liste Objets (déterministe côté serveur)
  const setMeasureSurfaceApi = async (measurementId, surfaceM2) => {
    try {
      await api.post(`/takeoffs/${plan.plan_id}/ai-command/apply`, {
        action: "set_measurement_surface",
        params: { measurement_id: measurementId, surface_m2: surfaceM2 }, page_index: pageIndex });
      await refreshPlan();
      toast.success(`Área → ${Number(surfaceM2).toFixed(2)} m²`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Área impossível"); }
  };
  const setMeasureLengthApi = async (measurementId, lengthM) => {
    try {
      await api.post(`/takeoffs/${plan.plan_id}/ai-command/apply`, {
        action: "set_measurement_length",
        params: { measurement_id: measurementId, length_m: lengthM }, page_index: pageIndex });
      await refreshPlan();
      toast.success(`Linear → ${Number(lengthM).toFixed(2)} m`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Linear impossível"); }
  };

  const setWallHeightApi = async (measurementId, heightM) => {    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/measurements/${measurementId}/wall-height`,
        { height_m: heightM > 0 ? heightM : null });
      if (heightM > 0 && data.wall_area_net_m2 != null) {
        setLastWallHeight(heightM);
        localStorage.setItem("cp_last_wall_height", String(heightM));
        toast.success(`Altura ${heightM} m → parede líquida ${data.wall_area_net_m2} m² (brut ${data.wall_area_gross_m2} m² − vãos ${data.openings_area_m2} m²)`, { duration: 7000 });
      } else toast.message("Altura de parede removida");
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Altura impossível"); }
  };

  // Arme le mode « dessiner la fenêtre » pour un mur donné (garde le volet ouvert)
  const armDeductDraw = (m) => {
    setDeductDialog(null);
    setDeductDraw({ measurement_id: m.measurement_id, label: m.label || "Parede" });
    setCumulMode(false); setPoints([]); setTool(TOOLS.DIST);
    toast.info(`Desenhe a janela/porta em « ${m.label || "a parede"} » (2 pontos) e depois duplo clique. Pode encadear várias.`, { duration: 7000 });
  };

  // Report d'une cote vers l'éditeur de devis (ligne d'ouvrage)
  const reportMeasureToDevis = (m) => {
    const isArea = m.kind === "polygon" || m.kind === "cumulative_area";
    const val = isArea ? (m.area_m2 || 0) : (m.value_m ?? m.length_m ?? 0);
    const unit = isArea ? "m2" : "ml";
    const name = m.label || (m.kind === "cumulative" ? "Parede" : m.kind === "cumulative_area" ? "Superfície" : isArea ? "Superfície" : "Medição");
    addOuvrageFromPlan({ line_kind: "ouvrage", designation: name, qty: Number(val) || 0, unit, unit_price_ht: 0 });
    toast.success(`« ${name} » adicionado ao orçamento (${Number(val).toFixed(2)} ${unit}) — clique em «Criar um orçamento»`, { duration: 6000 });
  };

  // Report de la SURFACE de mur nette (m²) au devis — quand une hauteur est saisie
  const reportWallAreaToDevis = (m) => {
    const area = Number(m.wall_area_net_m2 || 0);
    if (!(area > 0)) return toast.error("Introduza primeiro a altura da parede");
    const name = (m.label || "Parede") + " — área (alt. " + Number(m.wall_height_m || 0) + " m)";
    addOuvrageFromPlan({ line_kind: "ouvrage", designation: name, qty: area, unit: "m2", unit_price_ht: 0 });
    toast.success(`Área de parede « ${name} » adicionada ao orçamento (${area.toFixed(2)} m²)`, { duration: 6000 });
  };

  // Report GROUPÉ : toutes les surfaces nettes de murs de la page → devis en une fois
  const reportAllWallAreasToDevis = () => {
    const walls = pageMeasurements.filter((m) => Number(m.wall_area_net_m2 || 0) > 0);
    if (!walls.length) return toast.error("Nenhuma parede com área líquida (introduza primeiro as alturas)");
    walls.forEach((m) => {
      const name = (m.label || "Parede") + " — área (alt. " + Number(m.wall_height_m || 0) + " m)";
      addOuvrageFromPlan({ line_kind: "ouvrage", designation: name,
        qty: Number(m.wall_area_net_m2), unit: "m2", unit_price_ht: 0 });
    });
    const tot = walls.reduce((s, m) => s + Number(m.wall_area_net_m2 || 0), 0);
    toast.success(`${walls.length} parede(s) adicionada(s) ao orçamento — ${tot.toFixed(2)} m² no total`, { duration: 7000 });
  };

  // Fusion de cotes : joint plusieurs mesures en une (la 1re = cible), calcul automatique
  const mergeMeasures = async (ids) => {
    if (!ids || ids.length < 2) return toast.error("Selecione pelo menos 2 cotas");
    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/measurements/merge`, { measurement_ids: ids });
      const m = data.measurement || {};
      const val = m.kind === "cumulative_area" ? `${Number(m.area_m2 || 0).toFixed(2)} m²`
        : `${Number(m.value_m ?? m.length_m ?? 0).toFixed(2)} m`;
      toast.success(`${data.merged_count} cotas fundidas → ${val}`, { duration: 6000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Fusão impossível"); }
  };

  // Édition / suppression d'une ouverture déjà déduite (sans tout refaire)
  const patchOpening = async (openingId, patch) => {
    try {
      const { data } = await api.patch(
        `/takeoffs/${plan.plan_id}/measurements/${deductDialog.measurement_id}/openings/${openingId}`, patch);
      toast.success(`Vão alterado → parede líquida ${data.value_m} m`);
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Alteração impossível"); }
  };
  const removeOpening = async (openingId) => {
    try {
      const { data } = await api.delete(
        `/takeoffs/${plan.plan_id}/measurements/${deductDialog.measurement_id}/openings/${openingId}`);
      toast.success(`Vão eliminado → parede líquida ${data.value_m} m`);
      await refreshPlan();
    } catch { toast.error("Não foi possível eliminar"); }
  };
  const deductLiveMeasure = deductDialog
    ? pageMeasurements.find((x) => x.measurement_id === deductDialog.measurement_id)
    : null;

  const saveRoom = async () => {
    if (!currentCalib || points.length < 3) return toast.error("Trace uma divisão numa planta calibrada");
    const height = decimalNumber(ceilingH);
    if (!finitePositive(height)) return toast.error("Altura da divisão inválida");
    try {
      await api.post(`/takeoffs/${plan.plan_id}/rooms`, {
        page_index: pageIndex, name: pendingRoomName,
        points,
        ceiling_height_m: height,
        floor_thickness_m: planDefaults.floor_thickness_m || 0.15,
        openings: [],
      });
      toast.success("Divisão guardada");
      setRoomDialog(false);
      setPoints([]);
      await refreshPlan();
      setTool(TOOLS.SELECT);
    } catch (e) { toast.error("Não foi possível guardar"); }
  };

  const deleteRoom = async (rid) => {
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/rooms/${rid}`);
      await refreshPlan(); toast.success("Divisão eliminada");
    } catch (error) { toast.error(errorMessage(error, "Não foi possível eliminar")); }
  };

  // Efface TOUTES les mesures/annotations de la page avant de passer au devis
  const clearAllMeasures = async () => {
    if (!plan?.plan_id) return;
    const roomCount = rooms.length;
    if (!window.confirm(
      `Apagar tudo nesta página?\n\n${roomCount} divisão(ões), ${pageMeasurements.length} medição(ões) e as anotações (contadores, notas, ângulos, coberturas) serão eliminadas. A apresentação das paredes detetadas será reinicializada. Esta ação é irreversível.`
    )) return;
    try {
      // Supprime toutes les pièces de la page côté serveur
      await Promise.all(rooms.map((r) => api.delete(`/takeoffs/${plan.plan_id}/rooms/${r.room_id}`)));
      await api.delete(`/takeoffs/${plan.plan_id}/measurements?page_index=${pageIndex}`);
      setAnnotations({ counters: [], notes: [], angles: [], pitched_surfaces: [] });
      await saveAnnotations();
      setDetectedWalls(null);
      setWallsSummary(null);
      setPoints([]);
      setTool(TOOLS.SELECT);
      await refreshPlan();
      toast.success("Todas as medições foram apagadas — pronto para um novo orçamento");
    } catch (e) {
      toast.error("Impossível apagar tudo");
    }
  };

  const importAiRooms = async () => {
    if (!plan?.plan_id || !currentCalib) {
      toast.error("Calibre a planta antes de importar contornos"); return 0;
    }
    const sourceKey = pageKey;
    let data;
    try { ({ data } = await api.post(`/takeoffs/${plan.plan_id}/detect-all-rooms?page_index=${pageIndex}`)); }
    catch (error) { toast.error(errorMessage(error, "Deteção das divisões impossível")); return 0; }
    if (currentPageKeyRef.current !== sourceKey) return 0;
    const validContour = (points) => Array.isArray(points) && points.length >= 3 &&
      points.every((p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1])) &&
      Math.abs(points.reduce((sum, p, i) => {
        const q = points[(i + 1) % points.length]; return sum + p[0] * q[1] - q[0] * p[1];
      }, 0)) > 0;
    const contours = (Array.isArray(data?.rooms) ? data.rooms : []).filter((room) => validContour(room.points));
    if (!contours.length) {
      toast.warning("Nenhum contorno utilizável. As áreas lidas pela IA continuam a ser indicações; trace as divisões na planta.");
      return 0;
    }
    // Comparaison indépendante du point de départ et du sens du contour.
    const signature = (points) => JSON.stringify(points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).sort());
    let latest;
    try { ({ data: latest } = await api.get(`/takeoffs/${plan.plan_id}`)); }
    catch (error) { toast.error(errorMessage(error, "Verificação das divisões existentes impossível")); return 0; }
    if (currentPageKeyRef.current !== sourceKey) return 0;
    const known = new Set((latest.rooms || []).filter((r) => r.page_index === pageIndex && validContour(r.points)).map((r) => signature(r.points)));
    let imported = 0, failed = 0, skipped = 0;
    for (const contour of contours) {
      if (currentPageKeyRef.current !== sourceKey) break;
      const key = signature(contour.points);
      if (known.has(key)) { skipped++; continue; }
      try {
        await api.post(`/takeoffs/${plan.plan_id}/rooms`, {
          page_index: pageIndex, name: contour.name || `Divisão detetada ${imported + 1}`,
          points: contour.points, ceiling_height_m: planDefaults.ceiling_h_m ?? 2.5,
          floor_thickness_m: planDefaults.floor_thickness_m ?? 0.15,
        });
        known.add(key); imported++;
      } catch { failed++; }
    }
    await refreshPlan();
    if (currentPageKeyRef.current === sourceKey) setRightTab("rooms");
    if (imported) toast.success(`${imported} contorno(s) importado(s) — verifique a sua posição e as suas dimensões na planta`);
    if (failed) toast.warning(`${failed} divisão(ões) não importada(s)`);
    if (!imported && skipped) toast.message("Estes contornos já estão presentes na medição");
    return imported;
  };

  const runAI = async () => {
    if (!plan?.plan_id || analysisLock.current) return;
    analysisLock.current = true;
    const sourceKey = pageKey;
    setAiBusy(true);
    setAnalysisRecap(null);
    setAnalysisProgress("A ler os textos, divisões e vãos desta página…");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/analyze?page_index=${pageIndex}`);
      await refreshPlan();
      if (currentPageKeyRef.current !== sourceKey) return;
      setRightTab("ai");
      if (data.error) toast.warning("IA : " + data.error);
      else {
        const n = data.rooms?.length || 0;
        const surf = data.total_surface_written_m2;
        toast.success(
          `Analyse IA — ${n} divisão${n > 1 ? "s" : ""} detetada${n > 1 ? "s" : ""}` +
          (surf ? ` · ${surf} m²` : ""),
          { duration: 6000 }
        );
      }
    } catch (e) { toast.error("Análise IA impossível"); }
    finally { setAiBusy(false); setAnalysisProgress(""); analysisLock.current = false; }
  };

  // --- Iter62 : calibration par cotes / recalage surfaces écrites / textes IA ---
  const calibrateFromCotes = async () => {
    setAiActionBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/calibrate/from-cotes`,
        { page_index: pageIndex });
      toast.success(
        `Escala calibrada pelas cotas: ${data.calibration.pixels_per_meter.toFixed(1)} px/m ` +
        `(${data.calibration.samples_used} cota${data.calibration.samples_used > 1 ? "s" : ""}, ±${data.calibration.spread_pct}%)` +
        (data.rooms_recomputed ? ` · ${data.rooms_recomputed} divisão(ões) recalculada(s)` : ""),
        { duration: 8000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Calibração por cotas impossível"); }
    finally { setAiActionBusy(false); }
  };

  const checkWrittenSurfaces = async (apply = false) => {
    setAiActionBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/calibrate/reconcile`,
        { page_index: pageIndex, apply });
      setReconcile(data);
      if (data.applied) {
        toast.success(
          `Escala reajustada: ${data.calibration.pixels_per_meter.toFixed(1)} px/m · ` +
          `${data.rooms_recomputed} divisão(ões) recalculada(s)`, { duration: 7000 });
        setReconcile(null);
        await refreshPlan();
      } else if (!data.can_reconcile) {
        toast.warning(data.reason || "Sem correspondência com uma superfície escrita");
      }
    } catch (e) { toast.error(e?.response?.data?.detail || "Verificação impossível"); }
    finally { setAiActionBusy(false); }
  };

  const applyAiTexts = async () => {
    setAiActionBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/apply-ai-texts`,
        { page_index: pageIndex });
      const parts = [];
      if (data.renamed?.length) parts.push(`${data.renamed.length} divisão(ões) renomeada(s)`);
      if (data.materials_set?.length) parts.push(`${data.materials_set.length} material(is) de pavimento`);
      if (data.heights_updated?.length) parts.push(`${data.heights_updated.length} altura(s)`);
      if (data.calibration_set) parts.push("escala escrita aplicada");
      if (data.surface_flags?.length) parts.push(`⚠ ${data.surface_flags.length} diferença(s) de área >5%`);
      toast.success(parts.length
        ? `Textos da planta aplicados — ${parts.join(" · ")}`
        : "Textos analisados — nada a modificar", { duration: 9000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Aplicação dos textos impossível"); }
    finally { setAiActionBusy(false); }
  };

  const detectWalls = async (ortho = false) => {
    if (!plan?.plan_id) return;
    setCvBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/detect-walls?page_index=${pageIndex}&orthogonal_only=${ortho}`);
      setDetectedWalls(data);
      setShowWalls(true);
      toast.success(
        `${data.segment_count} segmentos de paredes detetados` +
        (data.filtered_cotes ? ` · ${data.filtered_cotes} traços de cota/textos ignorados` : "") +
        (data.filtered_diagonals ? ` · ${data.filtered_diagonals} diagonais ignoradas` : "")
      );
      if (data.structural_hint && !ortho) {
        toast.warning(
          "Este plano parece um plano de estrutura/betão (aços, cotas, tracejados). A deteção de paredes é pouco fiável — utilize antes as Medições betão.",
          { duration: 14000,
            action: { label: "Ignorar as diagonais", onClick: () => detectWalls(true) } }
        );
      }
      await loadWallsSummary();
    } catch (e) { toast.error("Impossível detetar paredes"); }
    finally { setCvBusy(false); }
  };

  // ===== STRUCTURE IA (murs rouges + ouvertures jaunes/violettes) =====
  const acierQuery = () =>
    `&acier_semelles=${acierRatios.semelles}&acier_poteaux=${acierRatios.poteaux}&acier_poutres=${acierRatios.poutres}&acier_dalles=${acierRatios.dalles}&acier_voiles=${acierRatios.voiles}&poutre_l=${poutreL}&poutre_h=${poutreH}&proprete_ep=${propreteEp}`;

  const betonPriceQuery = () =>
    `&beton_price_semelles=${betonPrices.semelles}&beton_price_proprete=${betonPrices.proprete}&beton_price_poteaux=${betonPrices.poteaux}&beton_price_poutres=${betonPrices.poutres}&beton_price_dalles=${betonPrices.dalles}&beton_price_voiles=${betonPrices.voiles}&plancher_type=${plancherType}&plancher_price_m2=${plancherPriceM2}`;

  const araseQuery = () =>
    (araseInf !== "" && araseSup !== "" && Number(araseSup) > Number(araseInf))
      ? `&arase_inf=${araseInf}&arase_sup=${araseSup}` : "";

  // Charge les réglages béton par défaut + presets, puis applique le dernier preset choisi
  useEffect(() => {
    (async () => {
      let lastPreset = "";
      try {
        const { data } = await api.get("/takeoffs/settings/beton-defaults");
        if (data.wall_height) setWallHeight(data.wall_height);
        if (data.dalle_ep) setDalleEp(data.dalle_ep);
        if (data.voile_ep) setVoileEp(data.voile_ep);
        if (data.poutre_l) setPoutreL(data.poutre_l);
        if (data.poutre_h) setPoutreH(data.poutre_h);
        if (data.acier_price_kg) setAcierPriceKg(data.acier_price_kg);
        if (data.beton_price_m3) setBetonPriceM3(data.beton_price_m3);
        if (data.labor_price_m3) setLaborPriceM3(data.labor_price_m3);
        if (data.margin_pct != null) setMarginPct(data.margin_pct);
        if (data.proprete_ep) setPropreteEp(data.proprete_ep);
        if (data.plancher_type) setPlancherType(data.plancher_type);
        if (data.plancher_price_m2) setPlancherPriceM2(data.plancher_price_m2);
        if (data.beton_prices && Object.keys(data.beton_prices).length) setBetonPrices((r) => ({ ...r, ...data.beton_prices }));
        if (data.acier_ratios) setAcierRatios((r) => ({ ...r, ...data.acier_ratios }));
        lastPreset = data.last_preset || "";
      } catch { /* ignore */ }
      try {
        const { data } = await api.get("/takeoffs/settings/beton-presets");
        const presets = data.presets || [];
        setBetonPresets(presets);
        const pr = presets.find((p) => p.name === lastPreset);
        if (pr) { applyPresetObj(pr, false); setSelectedPreset(lastPreset); }
      } catch { /* ignore */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyPresetObj = (pr, notify = true) => {
    setWallHeight(pr.wall_height ?? 2.5);
    setDalleEp(pr.dalle_ep ?? 0.20);
    setVoileEp(pr.voile_ep ?? 0.20);
    setPoutreL(pr.poutre_l ?? 0.20);
    setPoutreH(pr.poutre_h ?? 0.40);
    setAcierPriceKg(pr.acier_price_kg || 1.3);
    setBetonPriceM3(pr.beton_price_m3 || 130);
    setLaborPriceM3(pr.labor_price_m3 || 400);
    setMarginPct(pr.margin_pct ?? 15);
    if (pr.acier_ratios) setAcierRatios((r) => ({ ...r, ...pr.acier_ratios }));
    if (notify) toast.success(`Definições « ${pr.name} » aplicadas`);
  };

  const applyBetonPreset = (name) => {
    const pr = betonPresets.find((p) => p.name === name);
    if (!pr) return;
    setSelectedPreset(name);
    applyPresetObj(pr);
    api.put("/takeoffs/settings/beton-last-preset", { name }).catch(() => {});
  };

  const deleteBetonPreset = async () => {
    const pr = betonPresets.find((p) => p.name === selectedPreset);
    if (!pr || pr.builtin) return;
    if (!window.confirm(`Eliminar a definição « ${selectedPreset} » ?`)) return;
    try {
      await api.delete(`/takeoffs/settings/beton-presets/${encodeURIComponent(selectedPreset)}`);
      setBetonPresets((list) => list.filter((p) => p.name !== selectedPreset));
      setSelectedPreset("");
      toast.success("Definição removida");
    } catch { toast.error("Não foi possível eliminar"); }
  };

  const runCompare = async () => {
    if (!plan?.plan_id) return;
    setCompareBusy(true);
    setCompareOpen(true);
    try {
      const targets = betonPresets.length ? betonPresets : [];
      const results = await Promise.all(targets.map(async (pr) => {
        const aq = `&acier_semelles=${pr.acier_ratios.semelles}&acier_poteaux=${pr.acier_ratios.poteaux}&acier_poutres=${pr.acier_ratios.poutres}&acier_dalles=${pr.acier_ratios.dalles}&acier_voiles=${pr.acier_ratios.voiles}&poutre_l=${pr.poutre_l}&poutre_h=${pr.poutre_h}`;
        const { data } = await api.get(`/takeoffs/${plan.plan_id}/analysis/${pageIndex}?wall_height=${pr.wall_height}&dalle_ep=${pr.dalle_ep}&voile_ep=${pr.voile_ep}${aq}`);
        return { name: pr.name, d: data.descriptif,
                 beton_price_m3: pr.beton_price_m3 || 0, acier_price_kg: pr.acier_price_kg || 0,
                 labor_price_m3: pr.labor_price_m3 || 0, margin_pct: pr.margin_pct || 0 };
      }));
      setCompareData(results);
    } catch { toast.error("Comparação impossível"); setCompareOpen(false); }
    finally { setCompareBusy(false); }
  };

  const saveBetonPreset = async () => {
    const name = window.prompt("Nome do conjunto de definições (ex. Renovação, Moradia):");
    if (!name || !name.trim()) return;
    try {
      await api.put("/takeoffs/settings/beton-presets", {
        name: name.trim(), wall_height: wallHeight, dalle_ep: dalleEp, voile_ep: voileEp,
        poutre_l: poutreL, poutre_h: poutreH, acier_price_kg: acierPriceKg,
        beton_price_m3: betonPriceM3, labor_price_m3: laborPriceM3, margin_pct: marginPct,
        acier_ratios: acierRatios,
      });
      const { data } = await api.get("/takeoffs/settings/beton-presets");
      setBetonPresets(data.presets || []);
      setSelectedPreset(name.trim());
      toast.success(`Definição « ${name.trim()} » guardado`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gravação da definição impossível"); }
  };

  const saveBetonDefaults = async () => {
    try {
      await api.put("/takeoffs/settings/beton-defaults", {
        wall_height: wallHeight, dalle_ep: dalleEp, voile_ep: voileEp,
        poutre_l: poutreL, poutre_h: poutreH, acier_price_kg: acierPriceKg,
        beton_price_m3: betonPriceM3, labor_price_m3: laborPriceM3, margin_pct: marginPct,
        proprete_ep: propreteEp, beton_prices: betonPrices,
        plancher_type: plancherType, plancher_price_m2: plancherPriceM2,
        acier_ratios: acierRatios,
      });
      toast.success("Definições de betão guardadas como valores predefinidos da empresa");
    } catch { toast.error("Impossível guardar definições"); }
  };

  const loadDescriptif = async (height = wallHeight) => {
    const sourceKey = pageKey;
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/analysis/${pageIndex}?wall_height=${height}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}${araseQuery()}`);
      if (currentPageKeyRef.current === sourceKey) setDescriptif(data.descriptif);
      return data.descriptif;
    } catch { return null; }
  };

  // Bouton principal : « Analyser le plan » — enchaîne TOUT automatiquement :
  // 1) structure (murs/poteaux/poutres/dalles) 2) pièces IA + import au métré
  // 3) chiffrage/descriptif béton 4) estimation globale.
  // P3 — Assistant IA : proposer une action (aperçu, sans appliquer)
  const aiProposeCommand = async () => {
    const cmd = aiCmd.trim();
    if (!cmd || !plan?.plan_id) return;
    setAiCmdBusy(true);
    setAiCmdProposal(null);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/ai-command`, {
        command: cmd, page_index: pageIndex, history: aiTurns,
      });
      if (!data || data.action === "none") {
        toast.error(data?.summary || "Não compreendi este comando.");
      } else {
        setAiCmdProposal({ ...data, _cmd: cmd });
        if (data.action === "answer" && data.answer) {
          aiSpeak(data.answer.length > 600 ? data.answer.slice(0, 600) : data.answer);
        }
      }    } catch (e) {
      toast.error(e?.response?.data?.detail || "Assistente indisponível");
    } finally { setAiCmdBusy(false); }
  };

  // P3 — Assistant IA : appliquer l'action validée + auto-save
  const aiComputeInverse = (action, params) => {
    const ms = plan?.measurements || [];
    const rms = plan?.rooms || [];
    const fM = (id) => ms.find((m) => m.measurement_id === id);
    const fR = (id) => rms.find((r) => r.room_id === id);
    if (action === "rename_measurement") { const m = fM(params.measurement_id); return m?.label ? { action, params: { measurement_id: params.measurement_id, new_label: m.label } } : null; }
    if (action === "delete_measurement") { const m = fM(params.measurement_id); return m ? { action: "restore_measurement", params: { measurement: m } } : null; }
    if (action === "set_measurement_height") { const m = fM(params.measurement_id); return m ? { action, params: { measurement_id: params.measurement_id, wall_height_m: m.wall_height_m || 0 } } : null; }
    if (action === "set_measurement_surface") { const m = fM(params.measurement_id); return m?.area_m2 != null ? { action, params: { measurement_id: params.measurement_id, surface_m2: m.area_m2 } } : null; }
    if (action === "adjust_measurement_surface") { return params?.delta_m2 != null ? { action, params: { measurement_id: params.measurement_id, delta_m2: -Number(params.delta_m2) } } : null; }
    if (action === "set_measurement_length") { const m = fM(params.measurement_id); const l = m?.length_m ?? m?.value_m; return l != null ? { action, params: { measurement_id: params.measurement_id, length_m: l } } : null; }
    if (action === "set_measurement_poste") { const m = fM(params.measurement_id); return m?.poste ? { action, params: { measurement_id: params.measurement_id, poste: m.poste } } : null; }
    if (action === "rename_room") { const r = fR(params.room_id); return r?.name ? { action, params: { room_id: params.room_id, new_name: r.name } } : null; }
    if (action === "set_room_surface") { const r = fR(params.room_id); return r?.surface_m2 != null ? { action, params: { room_id: params.room_id, surface_m2: r.surface_m2 } } : null; }
    if (action === "set_room_height") { const r = fR(params.room_id); const h = r?.ceiling_height_m || r?.height_m; return h ? { action, params: { room_id: params.room_id, height_m: h } } : null; }
    return null; // non réversible (suppression, chiffrage de masse, note…)
  };

  const aiInjectPrice = async (ps) => {
    if (!ps?.amount || !plan?.plan_id) return;
    const unit = ps.unit === "m2" ? "m2" : (ps.unit === "ml" ? "ml" : "u");
    const label = (aiCmd || "Preço do material").trim().slice(0, 60) || "Preço do material";
    setAiCmdBusy(true);
    try {
      await api.post(`/takeoffs/corps-etat/custom`, {
        label, unit, pu: ps.amount, color: "#0ea5e9",
      });
      toast.success(`Artigo personalizado criado: ${label} à ${ps.amount.toLocaleString("pt-PT", { minimumFractionDigits: 2 })} €/${unit === "m2" ? "m²" : unit}. Disponível na orçamentação.`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Criação do artigo impossível");
    } finally { setAiCmdBusy(false); }
  };


  const aiSpeak = (text) => {
    try {
      if (!window.speechSynthesis) return;
      const u = new window.SpeechSynthesisUtterance(text);
      u.lang = "pt-PT"; u.rate = 1;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    } catch { /* non supporté */ }
  };

  const aiApplyCommand = async () => {
    if (!aiCmdProposal || !plan?.plan_id) return;
    const { action, params = {}, summary, _cmd } = aiCmdProposal;
    const inverse = aiComputeInverse(action, params);
    setAiCmdBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/ai-command/apply`, {
        action, params, page_index: pageIndex,
      });
      await refreshPlan();
      let turnResult = summary || action;
      let turnMid = data?.measurement_id || params?.measurement_id || null;
      if (action === "estimate_page") {
        const ttc = Number(data?.totals?.ttc || 0);
        const ht = Number(data?.totals?.ht_with_margin || 0);
        const msg = `Estimativa da página: ${ht.toLocaleString("pt-PT", { maximumFractionDigits: 0 })} euros sem IVA, ou seja ${ttc.toLocaleString("pt-PT", { maximumFractionDigits: 0 })} euros com IVA.`;
        toast.success(`Total da página: ${ht.toLocaleString("pt-PT", { minimumFractionDigits: 2 })} € s/ IVA · ${ttc.toLocaleString("pt-PT", { minimumFractionDigits: 2 })} € c/ IVA`);
        aiSpeak(msg);
        turnResult = `Página orçamentada: ${ht.toFixed(0)} € s/ IVA`;
      } else {
        toast.success("Ação aplicada e guardada");
        let hist = inverse;
        if ((action === "create_measurement" || action === "duplicate_measurement") && data?.measurement_id) {
          hist = { action: "delete_measurement", params: { measurement_id: data.measurement_id } };
          if (action === "create_measurement") {
            setAiJustCreated({ measurement_id: data.measurement_id, label: data.label || "cote", value: data.value });
          }
          turnResult = `Criada: ${data.label || "cote"} (${data.value || ""})`;
        } else if (action === "create_measurements_bulk" && Array.isArray(data?.created)) {
          hist = { bulkDeleteIds: data.created.map((c) => c.measurement_id) };
          toast.success(`${data.count} medições criadas`);
          turnResult = `${data.count} cotas criadas`;
        } else if (action === "deduct_measurement_areas") {
          turnResult = `Área → ${Number(data?.surface_m2 || 0).toFixed(2)} m² (−${Number(data?.total_deducted_m2 || 0).toFixed(2)} m²)`;
        } else if (action === "adjust_measurement_surface") {
          turnResult = `Área → ${Number(data?.surface_m2 || 0).toFixed(2)} m²`;
        }
        setAiHistory((h) => [{ id: Date.now(), summary: summary || action, inverse: hist }, ...h].slice(0, 20));
      }
      if (_cmd) {
        setAiTurns((t) => [...t, { command: _cmd, result: turnResult, measurement_id: turnMid }].slice(-8));
      }
      setAiCmdProposal(null);
      setAiCmd("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aplicação impossível");
    } finally { setAiCmdBusy(false); }
  };

  const aiUndo = async (entry) => {
    if (!entry?.inverse || !plan?.plan_id) return;
    setAiCmdBusy(true);
    try {
      if (Array.isArray(entry.inverse.bulkDeleteIds)) {
        for (const mid of entry.inverse.bulkDeleteIds) {
          await api.post(`/takeoffs/${plan.plan_id}/ai-command/apply`, {
            action: "delete_measurement", params: { measurement_id: mid }, page_index: pageIndex,
          });
        }
      } else {
        await api.post(`/takeoffs/${plan.plan_id}/ai-command/apply`, {
          action: entry.inverse.action, params: entry.inverse.params, page_index: pageIndex,
        });
      }
      await refreshPlan();
      setAiHistory((h) => h.filter((x) => x.id !== entry.id));
      toast.success("Ação anulada");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Anulação impossível");
    } finally { setAiCmdBusy(false); }
  };

  const aiVoiceDictate = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast.error("O ditado por voz não é suportado por este navegador (experimente o Chrome)."); return; }
    const rec = new SR();
    rec.lang = "pt-PT"; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onstart = () => setAiListening(true);
    rec.onerror = () => { setAiListening(false); toast.error("Microfone indisponível ou permissão recusada."); };
    rec.onend = () => setAiListening(false);
    rec.onresult = (ev) => {
      const text = ev.results?.[0]?.[0]?.transcript || "";
      if (text) setAiCmd((prev) => (prev ? prev + " " : "") + text);
    };
    try { rec.start(); } catch { setAiListening(false); }
  };

  const analyzePlanFull = async () => {
    if (!plan?.plan_id || analysisLock.current) return;
    if (!currentCalib) {
      toast.error("Calibre primeiro a planta: a escala é indispensável para calcular as quantidades.");
      setTool(TOOLS.CALIB);
      return;
    }
    analysisLock.current = true;
    setAnalysisBusy(true);
    setAnalysisRecap(null);
    setAnalysisProgress("1 / 5 · A identificar paredes, pilares, vigas e lajes…");
    const sourceKey = pageKey;
    const warnings = [];
    const tid = toast.loading("Análise completa em curso… estrutura, divisões, medições e estimativa.");
    try {
      // 1) Structure béton (murs, poteaux, poutres, dalles)
      let struct = null;
      try {
        const _pk = planKindChoice !== "auto" ? `&plan_kind=${planKindChoice}` : "";
        const { data } = await api.post(`/takeoffs/${plan.plan_id}/detect-structure?page_index=${pageIndex}${_pk}`);
        if (!data.error && currentPageKeyRef.current === sourceKey) {
          struct = data;
          setStructure(data);
          setShowStructure(true);
          setSelectedStruct(null);
        }
        else warnings.push("estrutura: " + data.error);
      } catch (e) { warnings.push("deteção de estrutura indisponível"); }
      if (currentPageKeyRef.current !== sourceKey) return;

      setAnalysisProgress("2 / 5 · A ler as divisões e os vãos…");
      // 2) Pièces (rooms) par IA vision
      let aiRooms = [];
      try {
        const { data } = await api.post(`/takeoffs/${plan.plan_id}/analyze?page_index=${pageIndex}`);
        aiRooms = data?.rooms || [];
        if (data?.error) warnings.push("análise das divisões: " + data.error);
      } catch (e) { warnings.push("análise das divisões indisponível"); }
      if (currentPageKeyRef.current !== sourceKey) return;

      setAnalysisProgress("3 / 5 · A importar os contornos e a calcular as áreas…");
      // 3) Rafraîchit puis importe les pièces au métré (surfaces + périmètres)
      await refreshPlan();
      if (currentPageKeyRef.current !== sourceKey) return;
      let importedRooms = 0;
      if (aiRooms.length) {
        try { importedRooms = (await importAiRooms()) || 0; }
        catch (e) { warnings.push("importação das divisões falhada"); }
        if (!importedRooms) warnings.push("nenhuma divisão nova importada");
      }

      if (currentPageKeyRef.current !== sourceKey) return;
      const latestPlan = await refreshPlan();
      if (currentPageKeyRef.current !== sourceKey) return;
      const measuredRooms = (latestPlan?.rooms || []).filter((room) => (room.page_index ?? 0) === pageIndex);
      setAnalysisProgress("4 / 5 · A calcular a descrição do betão…");
      // 4) Chiffrage / descriptif béton (métré chiffré)
      const descData = await loadDescriptif();
      if (!descData) warnings.push("descritivo indisponível");
      if (currentPageKeyRef.current !== sourceKey) return;

      setAnalysisProgress("5 / 5 · A preparar a estimativa…");
      // 5) Estimation globale depuis le métré (uniquement si des pièces existent)
      let estData = null;
      if ((latestPlan?.rooms || []).length > 0) {
        try { estData = await runEstimation(); } catch (e) { /* estimation optionnelle */ }
      }

      if ((latestPlan?.rooms || []).length > 0 && !estData) warnings.push("estimativa indisponível");
      if (currentPageKeyRef.current !== sourceKey) return;
      // Récapitulatif instantané (sans dialogue)
      const missingSurface = measuredRooms.some((room) => !finitePositive(room.surface_m2));
      if (missingSurface) warnings.push("área em falta ou inválida para algumas divisões");
      const surfacePieces = measuredRooms.length && !missingSurface
        ? measuredRooms.reduce((sum, room) => sum + Number(room.surface_m2), 0)
        : null;
      const beton = descData?.beton_total_m3 ?? null;
      const acier = descData?.acier_total_kg ?? null;
      const venteBeton = beton != null && acier != null
        && [beton, acier, betonPriceM3, acierPriceKg, laborPriceM3, marginPct].every((value) => Number.isFinite(Number(value)) && Number(value) >= 0)
        ? Math.round(((beton * betonPriceM3 + acier * acierPriceKg) + beton * laborPriceM3) * (1 + marginPct / 100))
        : null;
      setAnalysisRecap({
        warnings,
        rooms: measuredRooms.length,
        imported_rooms: importedRooms,
        surface_pieces_m2: surfacePieces == null ? null : Math.round(surfacePieces * 100) / 100,
        walls: struct?.wall_count || 0,
        columns: struct?.column_count || 0,
        beams: struct?.beam_count || 0,
        floors: struct?.floor_count || 0,
        beton_m3: beton,
        acier_kg: acier,
        estimation_beton_eur: venteBeton,
        estimation_globale_eur: estData?.estimation?.total_avg ?? null,
        estimation_surface_m2: estData?.surface_m2 || 0,
      });

      toast.dismiss(tid);
      const parts = [];
      if (struct) parts.push(`${struct.wall_count || 0} paredes · ${struct.column_count || 0} pilares · ${struct.beam_count || 0} vigas · ${struct.floor_count || 0} lajes`);
      if (aiRooms.length) parts.push(`${aiRooms.length} divisão(ões)`);
      if (warnings.length) toast.warning(`Análise parcial: ${warnings.join("; ")}. Verifique os resultados antes de exportar.`, { duration: 10000 });
      else toast.success(`Análise concluída — ${parts.join(" · ") || "nenhum elemento detetado"}. Verifique os resultados na planta.`, { duration: 8000 });
    } catch (e) {
      toast.dismiss(tid);
      toast.error(e?.response?.data?.detail || "Análise impossível");
    } finally { toast.dismiss(tid); setAnalysisBusy(false); setAnalysisProgress(""); analysisLock.current = false; }
  };

  const analyzeAllPages = async () => {
    if (!plan?.plan_id || analysisLock.current) return;
    analysisLock.current = true;
    const sourceKey = pageKey;
    setAnalysisBusy(true);
    setAnalysisRecap(null);
    setAnalysisProgress("A preparar a deteção de estrutura em todas as páginas…");
    try {
      const { data: job } = await api.post(`/takeoffs/${plan.plan_id}/detect-structure-all`);
      const data = await waitPlanJob(job.job_id, { onProgress: (j) => {
        if (currentPageKeyRef.current === sourceKey && j.total > 0) {
          setAnalysisProgress(`Estrutura · ${j.progress || 0} / ${j.total} páginas tratadas…`);
        }
      } });
      await refreshPlan();
      if (currentPageKeyRef.current !== sourceKey) return;
      setAnalysisRecap(null);
      toast.success(`Structure : ${data.page_count} página(s) analisada(s). Verifique cada página antes da medição.`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Análise multipágina impossível");
    } finally { setAnalysisBusy(false); setAnalysisProgress(""); analysisLock.current = false; }
  };

  const _hasStructure = () => !!(structure && ((structure.walls || []).length || (structure.openings || []).length || (structure.beams || []).length || (structure.floors || []).length || (structure.columns || []).length));

  const sendToQuote = async () => {
    if (!currentCalib) { toast.error("Calibre primeiro a planta"); return; }
    if (!_hasStructure()) { toast.error("Analise primeiro a planta"); return; }
    try {
      const body = plan3dSnapshot ? { snapshot_png: plan3dSnapshot } : {};
      const mq = (marginBeton !== "" ? `&margin_beton=${marginBeton}` : "")
        + (marginAcier !== "" ? `&margin_acier=${marginAcier}` : "")
        + (marginLabor !== "" ? `&margin_labor=${marginLabor}` : "");
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/quote?beton_only=true&wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&acier_price_kg=${acierPriceKg}&beton_price_m3=${betonPriceM3}${betonPriceQuery()}&labor_price_m3=${laborPriceM3}&margin_pct=${marginPct}&price_level=${priceLevel}${araseQuery()}${mq}`, body);
      const n = data.priced_lines || 0;
      toast.success((n > 0 ? `Orçamento criado — ${n} linha(s) orçamentada(s) a partir da sua biblioteca` : "Orçamento criado a partir do descritivo") + (plan3dSnapshot ? " · vista 3D anexa" : ""));
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível gerar o orçamento");
    }
  };

  const estimateAndDownloadQuote = async () => {
    if (!currentCalib) { toast.error("Calibre primeiro a planta"); return; }
    if (!_hasStructure()) { toast.error("Analise primeiro a planta"); return; }
    setQuoteBusy(true);
    try {
      const body = plan3dSnapshot ? { snapshot_png: plan3dSnapshot } : {};
      const mq = (marginBeton !== "" ? `&margin_beton=${marginBeton}` : "")
        + (marginAcier !== "" ? `&margin_acier=${marginAcier}` : "")
        + (marginLabor !== "" ? `&margin_labor=${marginLabor}` : "");
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/quote?beton_only=true&wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&acier_price_kg=${acierPriceKg}&beton_price_m3=${betonPriceM3}${betonPriceQuery()}&labor_price_m3=${laborPriceM3}&margin_pct=${marginPct}&price_level=${priceLevel}${araseQuery()}${mq}`, body);
      const res = await api.get(`/documents/${data.doc_id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `orcamento-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      const ttc = data.totals?.ttc || 0;
      toast.success(`Orçamento estimado transferido — ${ttc.toLocaleString("pt-PT")} € c/ IVA · ${data.priced_lines || 0} artigo(s) orçamentado(s)`, { duration: 6000 });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Estimativa impossível");
    } finally { setQuoteBusy(false); }
  };

  const exportAnnotatedPdf = async () => {
    if (!_hasStructure()) { toast.error("Analise primeiro a planta"); return; }
    try {
      const res = await api.post(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/pdf?wall_height=${wallHeight}`,
        {}, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `planta-anotada-${plan.plan_id}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("PDF da planta anotada descarregado");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossível exportar PDF");
    }
  };

  // Analyse automatique à l'ouverture depuis "Ajouter un plan" (?auto=1)
  useEffect(() => {
    if (!pendingAuto || !plan?.plan_id) return;
    setPendingAuto(false);
    toast.info("Análise automática da planta em curso…");
    analyzePlanFull();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAuto, plan?.plan_id]);

  const exportBetonXlsx = async () => {
    if (!_hasStructure()) { toast.error("Analise primeiro a planta"); return; }
    try {
      const q = `wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&beton_price_m3=${betonPriceM3}&acier_price_kg=${acierPriceKg}${betonPriceQuery()}`;
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/beton-xlsx?${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `medicao-betao-${plan.plan_id}.xlsx`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Medições betão (Excel) descarregado");
    } catch (e) { toast.error(e.message || "Exportação Excel do betão impossível"); }
  };

  const exportBetonPdf = async () => {
    if (!_hasStructure()) { toast.error("Analise primeiro a planta"); return; }
    try {
      const q = `wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&beton_price_m3=${betonPriceM3}&acier_price_kg=${acierPriceKg}&labor_price_m3=${laborPriceM3}&margin_pct=${marginPct}`;
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/beton-pdf?${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `medicao-betao-${plan.plan_id}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Medições betão (PDF) descarregado");
    } catch (e) { toast.error(e.message || "Exportação PDF do betão impossível"); }
  };

  // Assistant IA — corriger / guider la détection en langage naturel
  const [aiChatOpen, setAiChatOpen] = useState(false);
  const [aiMessages, setAiMessages] = useState([]);
  const [aiInput, setAiInput] = useState("");
  const [aiChatBusy, setAiChatBusy] = useState(false);

  const sendAiInstruction = async () => {
    const msg = aiInput.trim();
    if (!msg) return;
    if (!plan?.plan_id) return;
    const history = aiMessages.filter((m) => m.role === "user").map((m) => m.text);
    setAiMessages((prev) => [...prev, { role: "user", text: msg }]);
    setAiInput("");
    setAiChatBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/ai-refine`,
        { message: msg, history });
      if (data.structure) {
        setStructure(data.structure);
        setShowStructure(true);
        setSelectedStruct(null);
        await loadDescriptif();
      }
      setAiMessages((prev) => [...prev, { role: "assistant", text: data.reply || "Análise atualizada.", ok: data.ok }]);
      if (data.ok) toast.success("Planta atualizada pela IA");
    } catch (e) {
      const err = e?.response?.data?.detail || "A IA não conseguiu responder";
      setAiMessages((prev) => [...prev, { role: "assistant", text: err, ok: false }]);
      toast.error(err);
    } finally { setAiChatBusy(false); }
  };

  const persistStructure = async (next) => {
    const sourceKey = pageKey;
    setStructure(next);
    try {
      await api.put(`/takeoffs/${plan.plan_id}/structure/${pageIndex}`, {
        walls: next.walls || [], openings: next.openings || [], beams: next.beams || [],
        floors: next.floors || [], columns: next.columns || [], footings: next.footings || [],
        image_width: next.image_width, image_height: next.image_height,
      });
      if (currentPageKeyRef.current === sourceKey) setPlan((prev) => prev ? {
        ...prev, structure: { ...prev.structure, [String(pageIndex)]: next },
      } : prev);
    } catch { toast.error("Estrutura não guardada — tente novamente antes de mudar de página"); }
  };

  const commitStructure = () => {
    if (structure && plan?.plan_id) return persistStructure(structure);
  };

  const dragStructPoint = (type, id, ep, [ix, iy]) => {
    setStructure((prev) => {
      if (!prev) return prev;
      const key = { wall: "walls", beam: "beams", column: "columns", opening: "openings", footing: "footings" }[type];
      const idKey = { wall: "wall_id", beam: "beam_id", column: "column_id", opening: "opening_id", footing: "footing_id" }[type];
      const arr = (prev[key] || []).map((it) => {
        if (it[idKey] !== id) return it;
        return ep === 0 ? { ...it, x1: ix, y1: iy } : { ...it, x2: ix, y2: iy };
      });
      return { ...prev, [key]: arr };
    });
  };

  const deleteStructItem = () => {
    if (!selectedStruct || !structure) return;
    const key = { wall: "walls", beam: "beams", column: "columns", opening: "openings", footing: "footings" }[selectedStruct.type];
    const idKey = { wall: "wall_id", beam: "beam_id", column: "column_id", opening: "opening_id", footing: "footing_id" }[selectedStruct.type];
    const next = { ...structure, [key]: (structure[key] || []).filter((it) => it[idKey] !== selectedStruct.id) };
    setSelectedStruct(null);
    persistStructure(next).then(() => loadDescriptif());
  };

  const toggleStructType = () => {
    if (!selectedStruct || !structure) return;
    if (selectedStruct.type === "wall") {
      const next = { ...structure, walls: (structure.walls || []).map((w) =>
        w.wall_id === selectedStruct.id ? { ...w, type: w.type === "porteur" ? "cloison" : "porteur" } : w) };
      persistStructure(next).then(() => loadDescriptif());
    } else if (selectedStruct.type === "opening") {
      const cycle = { fenetre: "porte", porte: "baie", baie: "fenetre" };
      const next = { ...structure, openings: (structure.openings || []).map((o) =>
        o.opening_id === selectedStruct.id ? { ...o, kind: cycle[o.kind] || "fenetre" } : o) };
      persistStructure(next).then(() => loadDescriptif());
    }
  };

  const addStructWall = () => {
    const w = structure?.image_width || 1000, h = structure?.image_height || 1000;
    const cx = Math.round(w / 2), cy = Math.round(h / 2);
    const item = { wall_id: "sw_" + Math.random().toString(16).slice(2, 8),
                   x1: cx - 80, y1: cy, x2: cx + 80, y2: cy, type: "cloison" };
    const next = { ...(structure || { walls: [], openings: [], beams: [], image_width: w, image_height: h }) };
    next.walls = [...(next.walls || []), item];
    setSelectedStruct({ type: "wall", id: item.wall_id });
    persistStructure(next).then(() => loadDescriptif());
    toast.info("Parede adicionada — deslize as suas extremidades para a colocar");
  };

  const addStructBeam = () => {
    const w = structure?.image_width || 1000, h = structure?.image_height || 1000;
    const cx = Math.round(w / 2), cy = Math.round(h / 2);
    const item = { beam_id: "sb_" + Math.random().toString(16).slice(2, 8),
                   x1: cx - 100, y1: cy - 40, x2: cx + 100, y2: cy - 40 };
    const next = { ...(structure || { walls: [], openings: [], beams: [], columns: [], floors: [], image_width: w, image_height: h }) };
    next.beams = [...(next.beams || []), item];
    setSelectedStruct({ type: "beam", id: item.beam_id });
    persistStructure(next).then(() => loadDescriptif());
    toast.info("Viga adicionada — deslize as suas extremidades para a posicionar");
  };

  const addStructColumn = () => {
    const w = structure?.image_width || 1000, h = structure?.image_height || 1000;
    const cx = Math.round(w / 2), cy = Math.round(h / 2);
    const s = Math.round(Math.max(w, h) * 0.02);
    const item = { column_id: "sc_" + Math.random().toString(16).slice(2, 8),
                   x1: cx - s, y1: cy - s, x2: cx + s, y2: cy + s };
    const next = { ...(structure || { walls: [], openings: [], beams: [], columns: [], floors: [], image_width: w, image_height: h }) };
    next.columns = [...(next.columns || []), item];
    setSelectedStruct({ type: "column", id: item.column_id });
    persistStructure(next).then(() => loadDescriptif());
    toast.info("Pilar adicionado — deslize os seus cantos para o ajustar");
  };

  const addStructOpening = (kind) => {
    const w = structure?.image_width || 1000, h = structure?.image_height || 1000;
    const cx = Math.round(w / 2), cy = Math.round(h / 2);
    const item = { opening_id: "so_" + Math.random().toString(16).slice(2, 8),
                   kind, x1: cx - 40, y1: cy, x2: cx + 40, y2: cy, swing: null };
    const next = { ...(structure || { walls: [], openings: [], beams: [], image_width: w, image_height: h }) };
    next.openings = [...(next.openings || []), item];
    setSelectedStruct({ type: "opening", id: item.opening_id });
    persistStructure(next).then(() => loadDescriptif());
    toast.info(`${kind === "porte" ? "Porta" : "Janela"} adicionada — arraste as extremidades para a posicionar`);
  };

  const addStructFooting = () => {
    const w = structure?.image_width || 1000, h = structure?.image_height || 1000;
    const cx = Math.round(w / 2), cy = Math.round(h / 2);
    const s = Math.round(Math.max(w, h) * 0.03);
    const item = { footing_id: "sft_" + Math.random().toString(16).slice(2, 8),
                   x1: cx - s, y1: cy - s, x2: cx + s, y2: cy + s };
    const next = { ...(structure || { walls: [], openings: [], beams: [], columns: [], floors: [], footings: [], image_width: w, image_height: h }) };
    next.footings = [...(next.footings || []), item];
    setSelectedStruct({ type: "footing", id: item.footing_id });
    persistStructure(next).then(() => loadDescriptif());
    toast.info("Sapata adicionada — arraste os cantos para ajustar");
  };

  const autoFillRoom = async (pt) => {
    if (!currentCalib) return toast.error("Calibre primeiro a planta");
    setCvBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/room-autofill`, {
        page_index: pageIndex,
        seed_x: Math.round(pt[0]),
        seed_y: Math.round(pt[1]),
        tolerance: 25,
      });
      // Charge les points détectés dans l'état — l'utilisateur peut ajuster puis valider
      setPoints(data.points);
      toast.success(`Contorno detetado (${data.point_count} pontos, ${data.surface_m2} m²)`);
      // Ouvre le dialog de nom immédiatement
      setPendingRoomName(`Divisão ${String(rooms.length + 1).padStart(2, "0")}`);
      setRoomDialog(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Nenhuma divisão detetada neste ponto");
    } finally { setCvBusy(false); }
  };

  const loadTakeoff = async () => {
    if (!plan?.plan_id) return;
    const sourceKey = pageKey;
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/takeoff`);
      if (currentPageKeyRef.current !== sourceKey) return;
      setTakeoff(data);
      const { data: materialData } = await api.post(`/takeoffs/${plan.plan_id}/materials`, { floor_material: floorMaterial });
      if (currentPageKeyRef.current === sourceKey) setMaterials(materialData);
    } catch (error) { toast.error(errorMessage(error, "Cálculo da medição ou dos materiais impossível")); }
  };

  const sendToEstimator = () => {
    if (!takeoff?.totals?.floor_m2) return toast.error("Adicione pelo menos uma divisão");
    // Prefill query params for /estimation with surface
    nav(`/estimation?surface=${Math.round(takeoff.totals.floor_m2)}&from=plan`);
  };

  const sendToPrices = () => {
    if (!materials) return;
    const q = [];
    if (materials.floor) q.push(`${materials.floor.material} ${materials.floor.quantity_m2}m²`);
    if (materials.placo) q.push(`placas de pladur 13 mm`);
    if (materials.paint) q.push(`peinture`);
    nav(`/prix?q=${encodeURIComponent(q.join(" "))}`);
  };

  const downloadPdf = async () => {
    if (!plan?.plan_id) return;
    // Guard : PDF vide si aucune pièce tracée
    if (!rooms.length) {
      toast.error("Adicione primeiro uma divisão (ferramenta Divisão ou Auto-divisão) para gerar medições.", { duration: 5000 });
      setRightTab("rooms");
      return;
    }
    try {
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/pdf?include_materials=true&floor_material=${floorMaterial}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `medicao-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Medições PDF descarregado");
    } catch { toast.error("Impossível exportar PDF"); }
  };

  const downloadPlanMetre = async () => {
    if (!plan?.plan_id) return;
    try {
      const res = await api.post("/takeoffs/metre-multi-pdf",
        { plan_ids: [plan.plan_id], project_name: plan.filename || "Medição" },
        { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `medicao-${(plan.filename || "plan").replace(/[^\w]+/g, "_")}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Medição PDF (sem preços) transferida");
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível exportar"); }
  };
  const downloadEcartsPdf = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/ecarts-pdf?page_index=${pageIndex}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `relatorio-desvios-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Relatório de desvios PDF descarregado");
    } catch (e) { toast.error(e.message || "Exportação do relatório de diferenças impossível"); }
  };

  // Iter63 — détail de la cote IA sélectionnée (clic sur le plan)
  const coteDetail = useMemo(() => {
    if (selectedCote == null) return null;
    const d = aiDimLines[selectedCote];
    if (!d) return null;
    const page = plan?.pages?.[pageIndex];
    const bb = d.bbox_norm;
    let measured = null, deltaPct = null;
    if (Array.isArray(bb) && bb.length === 4 && page?.width_px && page?.height_px) {
      const pxLen = Math.hypot((bb[2] - bb[0]) * page.width_px,
                               (bb[3] - bb[1]) * page.height_px);
      const ppm = currentCalib?.pixels_per_meter;
      if (ppm) {
        measured = pxLen / ppm;
        if (d.value_m) deltaPct = (measured / Number(d.value_m) - 1) * 100;
      }
    }
    return { ...d, measured, deltaPct };
  }, [selectedCote, aiDimLines, plan, pageIndex, currentCalib]);

  useEffect(() => { setSelectedCote(null); }, [pageIndex]);

  // Échap = annule la mesure en cours SANS rien enregistrer (iter64)
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key !== "Escape") return;
      if (e.target?.closest?.('[role="dialog"]')) return;
      if (points.length > 0) {
        setPoints([]);
        toast.info("Medição cancelada");
      } else if (selectedCote != null) {
        setSelectedCote(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [points, selectedCote]);

  // Iter64 — envoi du rapport d'écarts par email au client
  const sendEcartsReport = async () => {
    if (!ecartsEmail.trim()) return toast.error("Indique o email do cliente");
    setSendingEcarts(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/ecarts-pdf/send`, {
        page_index: pageIndex,
        to_email: ecartsEmail.trim(),
        message: ecartsMessage,
      });
      toast.success(`Relatório de diferenças enviado para ${data.sent_to}`, { duration: 7000 });
      setSendEcartsDialog(false);
      setEcartsMessage("");
      await refreshPlan();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Impossível enviar — verifique o email");
    } finally { setSendingEcarts(false); }
  };

  const loadHistory = async () => {
    if (!plan?.plan_id) return;
    setHistoryLoading(true);
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/history`);
      setHistory(data.history || []);
    } finally { setHistoryLoading(false); }
  };

  const restoreSnapshot = async (snapshotId) => {
    if (!plan?.plan_id) return;
    try {
      await flushPlanAnnotations();
      await api.post(`/takeoffs/${plan.plan_id}/history/restore/${snapshotId}`);
      const restored = await refreshPlan();
      if (restored) restoreAnnotations(restored.annotations);
      await loadHistory();
      toast.success("Snapshot restaurado");
    } catch { toast.error("Restauro impossível"); }
  };

  const openLabelDialog = (snap) => {
    setLabelDialog(snap);
    setLabelValue(snap.label || "");
  };

  const saveSnapshotLabel = async () => {
    if (!plan?.plan_id || !labelDialog) return;
    try {
      await api.put(
        `/takeoffs/${plan.plan_id}/history/${labelDialog.snapshot_id}/label`,
        { label: labelValue },
      );
      setLabelDialog(null); setLabelValue("");
      await loadHistory();
      toast.success("Nome guardado");
    } catch { toast.error("Não foi possível guardar"); }
  };

  const downloadQuotePdf = async () => {
    if (!plan?.plan_id) return;
    setQuoteBusy(true);
    try {
      const qs = new URLSearchParams({
        finish: quoteFinish, floor_material: quoteFloor,
      }).toString();
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/quote-pdf?${qs}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `orcamento-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Orçamento PDF descarregado");
      setQuoteDialog(false);
    } catch (e) { toast.error(e.message || "Exportação do orçamento impossível"); }
    finally { setQuoteBusy(false); }
  };

  const sendQuotePdf = async () => {
    if (!plan?.plan_id) return;
    if (!/@/.test(quoteClientEmail)) return toast.error("Email do cliente inválido");
    if (quoteIncludeTva && !quoteClientAddress.trim())
      return toast.error("Morada do cliente necessária para a declaração de IVA");
    setQuoteBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/send-quote`, {
        client_email: quoteClientEmail.trim(),
        client_name: quoteClientName.trim() || null,
        client_address: quoteClientAddress.trim() || null,
        work_address: quoteClientAddress.trim() || null,
        subject: quoteSubject.trim() || null,
        intro: quoteIntro.trim() || null,
        message: quoteMessage.trim() || null,
        finish: quoteFinish, floor_material: quoteFloor, cc_self: true,
        include_tva_attestation: quoteIncludeTva,
        attach_latest_video: quoteAttachVideo,
      });
      if (data.email_status === "sent") {
        const extras = [];
        if (quoteIncludeTva) extras.push("declaração de IVA");
        if (quoteAttachVideo && latestVideo) extras.push("tour vídeo 3D");
        const extra = extras.length ? " + " + extras.join(" + ") + " joint(s)" : "";
        toast.success(`Orçamento enviado a ${quoteClientEmail}${extra} (${data.total_ttc?.toLocaleString("pt-PT")} € c/ IVA)`);
        setQuoteDialog(false);
        setQuoteClientEmail(""); setQuoteClientName(""); setQuoteMessage("");
        setQuoteSubject(""); setQuoteIntro(""); setQuoteClientAddress("");
        await loadQuoteSends();
      } else {
        toast.error("Envio email falhado — verifique a chave Resend");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envio impossível");
    } finally { setQuoteBusy(false); }
  };

  const runEstimation = async () => {
    if (!plan?.plan_id) return;
    const sourceKey = pageKey;
    setEstimateBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/estimate-from-takeoff`, {
        project_type: estProjectType, finish_level: estFinishLevel,
      });
      if (currentPageKeyRef.current !== sourceKey) return null;
      setEstimateResult(data);
      // Si rénovation → coche automatiquement TVA
      if (data.is_renovation) setQuoteIncludeTva(true);
      toast.success(`Estimativa gerada: ${data.surface_m2} m² · ${data.estimation?.total_avg?.toLocaleString("pt-PT")} €`);
      return data;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Estimativa impossível");
      return null;
    } finally { setEstimateBusy(false); }
  };

  const proceedToDevis = () => {
    if (!estimateResult) return;
    // Reprend la finish choisie pour l'estimation dans le dialog devis
    setQuoteFinish(estFinishLevel === "standard" ? "std"
                    : estFinishLevel === "premium" ? "premium" : "eco");
    setEstimateDialog(false);
    setQuoteDialog(true);
    setQuoteMode("send");
    if (estimateResult.is_renovation) setQuoteIncludeTva(true);
    loadTemplates(); loadQuoteSends();
  };

  const loadRender3dHistory = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/renders-3d`);
      setRender3dHistory(data.renders || []);
    } catch { /* ignore */ }
  };

  const loadCredits3d = async () => {
    try {
      const { data } = await api.get("/billing/credits-3d");
      setCredits3d(data);
    } catch { /* ignore */ }
  };

  const buyCredit = async (creditPlanId) => {
    try {
      const { data } = await api.post("/billing/checkout", {
        plan_id: creditPlanId, origin_url: window.location.origin,
      });
      if (data?.url) window.location.href = data.url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Pagamento indisponível (tente novamente)");
    }
  };

  const handle3dError = (e, fallbackMsg) => {
    const d = e?.response?.data?.detail;
    if (e?.response?.status === 402 && d && typeof d === "object" && d.error === "credit_required") {
      setCreditPaywall(d);
      return true;
    }
    toast.error(typeof d === "string" ? d : fallbackMsg);
    return false;
  };

  const selectInteractiveMode = async () => {
    if (!plan?.plan_id) { setRender3dMode("interactive"); return; }
    try {
      await api.post(`/takeoffs/${plan.plan_id}/interactive-3d`);
      setCreditPaywall(null);
      setRender3dMode("interactive");
      loadCredits3d();
    } catch (e) {
      handle3dError(e, "Maqueta interativa indisponível");
    }
  };

  const runRender3d = async () => {
    if (!plan?.plan_id) return;
    setCreditPaywall(null);
    setRender3dBusy(true); setRender3dImg(null);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/render-3d`, {
        page_index: pageIndex,
        style: render3dStyle,
        include_furniture: render3dFurniture,
      }, { timeout: 120000 });
      setRender3dImg(`data:${data.mime_type};base64,${data.image_b64}`);
      toast.success("Renderização 3D gerada!");
      await loadRender3dHistory();
      loadCredits3d();
    } catch (e) {
      handle3dError(e, "Geração 3D falhada (tente novamente)");
    } finally { setRender3dBusy(false); }
  };

  const openRender3dHistory = async (renderId) => {
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/renders-3d/${renderId}`);
      setRender3dImg(`data:${data.mime_type};base64,${data.image_b64}`);
      setRender3dStyle(data.style);
    } catch { toast.error("Não foi possível carregar"); }
  };

  const downloadRender3d = () => {
    if (!render3dImg) return;
    const a = document.createElement("a");
    a.href = render3dImg;
    a.download = `render-3d-${plan.plan_id}-${render3dStyle}.png`;
    document.body.appendChild(a); a.click(); a.remove();
  };

  // ─── Tour vidéo 3D (multi-styles → MP4) ───────────────────────────────
  const loadVideoHistory = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/videos-3d`);
      const videos = data.videos || [];
      setVideoHistory(videos);
      // First (most recent) becomes the "latest" candidate for quote attachment
      setLatestVideo(videos[0] || null);
    } catch { /* ignore */ }
  };

  const videoBlobUrl = (videoId) =>
    `${api.defaults.baseURL}/takeoffs/${plan.plan_id}/videos-3d/${videoId}/mp4`;

  const runRenderVideo = async () => {
    if (!plan?.plan_id) return;
    setCreditPaywall(null);
    setVideoBusy(true); setVideoUrl(null);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/render-video`, {
        page_index: pageIndex,
        include_furniture: render3dFurniture,
        add_watermark: videoAddWatermark,
        add_music: videoAddMusic,
      }, { timeout: 300000 }); // 5 min : 4 renders IA + montage ffmpeg
      setCurrentVideoId(data.video_id);
      setVideoUrl(videoBlobUrl(data.video_id));
      toast.success("Tour vídeo 3D gerado!");
      await loadVideoHistory();
      loadCredits3d();
    } catch (e) {
      handle3dError(e, "Geração de vídeo falhada (tente novamente)");
    } finally { setVideoBusy(false); }
  };

  const openVideoHistory = (videoId) => {
    setCurrentVideoId(videoId);
    setVideoUrl(videoBlobUrl(videoId));
  };

  const downloadVideo = () => {
    if (!currentVideoId) return;
    const a = document.createElement("a");
    a.href = videoBlobUrl(currentVideoId);
    a.download = `tour-3d-${plan.plan_id}.mp4`;
    document.body.appendChild(a); a.click(); a.remove();
  };


  const loadWallsSummary = async () => {
    if (!plan?.plan_id) return;
    try {
      const ppm = currentCalib?.pixels_per_meter;
      const q = ppm ? `?ppm=${ppm}` : "";
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/walls-summary${q}`);
      setWallsSummary(data);
    } catch { /* ignore */ }
  };

  const loadTemplates = async () => {
    try {
      const { data } = await api.get("/quotes/templates");
      setTemplates(data.templates || []);
    } catch { /* ignore */ }
  };

  const applyTemplate = (t) => {
    if (!t) return;
    setQuoteFinish(t.finish || "std");
    setQuoteFloor(t.floor_material || "carrelage");
    toast.success(`Modelo « ${t.name} » aplicado`);
  };

  const saveTemplate = async () => {
    if (templateName.trim().length < 2) return toast.error("Nome do modelo demasiado curto");
    try {
      await api.post("/quotes/templates", {
        name: templateName.trim(),
        finish: quoteFinish, floor_material: quoteFloor,
        is_shared: templateShared,
      });
      toast.success(`Modelo « ${templateName} » guardado`);
      setTemplateName(""); setTemplateShared(false);
      await loadTemplates();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    }
  };

  const deleteTemplate = async (id) => {
    if (!window.confirm("Eliminar este modelo?")) return;
    try {
      await api.delete(`/quotes/templates/${id}`);
      await loadTemplates();
      toast.success("Modelo eliminado");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível eliminar");
    }
  };

  const loadQuoteSends = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/quote-sends`);
      setQuoteSends(data.sends || []);
    } catch { /* ignore */ }
  };

  const loadAllPlans = async () => {
    try {
      const { data } = await api.get("/takeoffs");
      const items = Array.isArray(data) ? data : data?.plans;
      if (!Array.isArray(items)) throw new Error("Lista de plantas inválida");
      setAllPlans(items);
    } catch (error) { toast.error(errorMessage(error, "Carregamento das plantas impossível")); }
  };

  // Projets multi-niveaux (Fondations / RDC / R+1 …)
  const loadPlanGroups = async () => {
    try { const { data } = await api.get("/takeoffs/multilevel/groups"); setPlanGroups(data.groups || []); }
    catch { /* ignore */ }
  };

  const openGroupBuilder = () => {
    loadAllPlans();
    setGroupBuilder({ group_id: null, name: "", levels: [] });
  };

  const editGroup = (g) => {
    setGroupBuilder({ group_id: g.group_id, name: g.name,
      levels: (g.levels || []).map((l) => ({ plan_id: l.plan_id, level_label: l.level_label || "" })) });
  };

  const saveGroup = async () => {
    const gb = groupBuilder;
    if (!gb?.name?.trim()) return toast.error("Dê um nome ao projeto");
    if (!gb.levels.length) return toast.error("Adicione pelo menos uma planta");
    const body = { name: gb.name.trim(), chantier_id: chantierId || null, levels: gb.levels };
    try {
      if (gb.group_id) await api.put(`/takeoffs/multilevel/groups/${gb.group_id}`, body);
      else await api.post("/takeoffs/multilevel/groups", body);
      toast.success(`Projeto « ${gb.name.trim()} » guardado${chantierId ? " e associado ao processo de obra" : ""}`);
      setGroupBuilder(null);
      loadPlanGroups();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar"); }
  };

  const openGroupConsolidated = async (g) => {
    setGroupView({ loading: true, name: g.name, group_id: g.group_id });
    try {
      const { data } = await api.get(`/takeoffs/multilevel/groups/${g.group_id}`, { params: { margin_pct: 0 } });
      setGroupView({ ...data, group_id: g.group_id, loading: false });
    } catch { setGroupView(null); toast.error("Consolidação impossível"); }
  };

  const createGroupQuote = async () => {
    if (!groupView?.group_id) return;
    try {
      const { data } = await api.post(`/takeoffs/multilevel/groups/${groupView.group_id}/to-quote`, { margin_pct: 0 });
      toast.success("Orçamento parcial criado — os artigos não medidos ficam por completar");
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível criar o orçamento"); }
  };

  const openCoverDialog = async () => {
    if (!groupView?.group_id) return;
    setCoverDialog({ loading: true, reference: "", name: "", company: "", address: "", city: "", email: "", phone: "" });
    try {
      const { data } = await api.get(`/takeoffs/multilevel/groups/${groupView.group_id}/cover-info`);
      const c = data.client || {};
      setCoverDialog({ loading: false, reference: data.reference || "",
        name: c.name || "", company: c.company || "", address: c.address || "",
        city: c.city || "", email: c.email || "", phone: c.phone || "" });
    } catch {
      setCoverDialog((d) => d ? { ...d, loading: false } : d);
    }
  };

  // ---- Agents IA (proposer → valider → exécuter → revoir/corriger) ----
  const AGENT_CATALOG = [
    { key: "report", name: "Processo automático", icon: Bot, desc: "Reúne as suas plantas, faz a medição, orçamenta e produz o processo PDF completo." },
    { key: "devis", name: "Orçamento automático", icon: Wand2, desc: "Orçamenta as medições atribuídas e cria um orçamento consolidado editável." },
    { key: "metre", name: "Medição expresso", icon: Ruler, desc: "Síntese da medição: áreas, lineares, medições e plantas a completar." },
    { key: "detect", name: "Deteção automática de paredes", icon: ScanLine, desc: "Deteta paredes + vãos (IA) numa planta não medida. Calibração obrigatória antes da medição." },
    { key: "compare", name: "Comparação de plantas", icon: GitCompare, desc: "Compara 2 versões (antes / depois) e lista as diferenças de divisões e paredes." },
    { key: "dpgf", name: "Mapa de quantidades → orçamento", icon: FileText, desc: "Lê um mapa de quantidades/caderno de encargos importado e prepara o orçamento detalhado (oficina dedicada)." },
  ];
  const [agentHistory, setAgentHistory] = useState(null);
  const openPlanById = async (pid) => {
    try { const { data } = await api.get(`/takeoffs/${pid}`); setPlan(data); setPageIndex(0); setAgentBox(null); }
    catch { toast.error("Abertura da planta impossível"); }
  };
  const loadAgentHistory = async () => {
    try { const { data } = await api.get("/agents/runs"); setAgentHistory(data.runs || []); }
    catch { setAgentHistory([]); }
  };
  const openAgentBox = () => {
    loadAllPlans();
    setAgentBox({ step: "pick", agent: "report", selected: [], prompt: "", loading: false,
      run: null, params: { margin_pct: 0, project_name: "", client_name: "", client_city: "", client_email: "", client_phone: "" }, result: null });
  };
  const agentToggle = (pid) => setAgentBox((a) => ({ ...a, selected: a.selected.includes(pid) ? a.selected.filter((x) => x !== pid) : [...a.selected, pid] }));
  const agentPropose = async () => {
    if (agentBox.agent === "dpgf") { setAgentBox(null); nav("/dpgf"); return; }
    if (!agentBox.selected.length) return toast.error("Selecione pelo menos uma planta");
    if (agentBox.agent === "compare" && agentBox.selected.length !== 2) return toast.error("Selecione exatamente 2 plantas (antes / depois)");
    setAgentBox((a) => ({ ...a, loading: true }));
    try {
      const { data } = await api.post("/agents/plan", { agent: agentBox.agent, plan_ids: agentBox.selected, prompt: agentBox.prompt });
      setAgentBox((a) => ({ ...a, step: "plan", loading: false, run: data.run,
        params: { ...a.params, margin_pct: data.defaults?.margin_pct || 0 } }));
    } catch (e) { setAgentBox((a) => ({ ...a, loading: false })); toast.error(e?.response?.data?.detail || "Proposta impossível"); }
  };
  const agentSetLevel = (pid, level) => setAgentBox((a) => ({ ...a, run: { ...a.run, plan_status: a.run.plan_status.map((s) => s.plan_id === pid ? { ...s, level } : s) } }));
  const agentExecute = async () => {
    setAgentBox((a) => ({ ...a, loading: true }));
    try {
      let runId = agentBox.run.run_id;
      // les corrections de niveaux ne concernent que les agents dossier/devis
      if (agentBox.agent === "report" || agentBox.agent === "devis") {
        const labels = Object.fromEntries(agentBox.run.plan_status.map((s) => [s.plan_id, s.level]));
        const { data: rev } = await api.post(`/agents/${runId}/revise`, { level_labels: labels, margin_pct: agentBox.params.margin_pct });
        runId = rev.run.run_id;
        setAgentBox((a) => ({ ...a, run: rev.run }));
      }
      const { data } = await api.post(`/agents/${runId}/execute`, agentBox.params);
      setAgentBox((a) => ({ ...a, step: "result", loading: false, result: data.result }));
      toast.success("Agente concluído — verifique o resultado");
    } catch (e) { setAgentBox((a) => ({ ...a, loading: false })); toast.error(e?.response?.data?.detail || "Execução impossível"); }
  };
  const agentDownload = async () => {
    const dl = agentBox?.result?.download;
    if (!dl) return;
    try {
      const res = await api.get(dl, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url;
      a.download = agentBox.result.kind === "quote" ? "devis.pdf" : "dossier.pdf";
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { toast.error("Transferência impossível"); }
  };
  const agentFeedback = async (rating) => {
    if (!agentBox?.run?.run_id) return;
    const labels = Object.fromEntries((agentBox.run.plan_status || []).map((s) => [s.plan_id, s.level]));
    try {
      await api.post(`/agents/${agentBox.run.run_id}/feedback`, { rating, level_labels: labels });
      toast.success(rating === "ok" ? "Obrigado — o agente memoriza as suas escolhas" : "Correção guardada — o agente melhora");
      if (rating === "ok") setAgentBox(null);
      else setAgentBox((a) => ({ ...a, step: "plan" }));
    } catch { toast.error("Envio impossível"); }
  };

  const downloadGroupPdf = async () => {
    if (!groupView?.group_id) return;
    const c = coverDialog || {};
    const params = { margin_pct: 0 };
    if (c.name) params.client_name = c.name;
    if (c.company) params.client_company = c.company;
    if (c.address) params.client_address = c.address;
    if (c.city) params.client_city = c.city;
    if (c.email) params.client_email = c.email;
    if (c.phone) params.client_phone = c.phone;
    try {
      const res = await api.get(`/takeoffs/multilevel/groups/${groupView.group_id}/pdf`,
                                { params, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `dossier_${(groupView.name || "multiniveaux").replace(/[^\w]+/g, "_")}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setCoverDialog(null);
      toast.success("Processo de orçamentação PDF transferido");
    } catch { toast.error("Geração do PDF impossível"); }
  };

  const downloadGroupMetrePdf = async () => {
    if (!groupView?.group_id) return;
    try {
      const res = await api.get(`/takeoffs/multilevel/groups/${groupView.group_id}/pdf`,
                                { params: { metre_only: true }, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `medicao_${(groupView.name || "projet").replace(/[^\w]+/g, "_")}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Medição do projeto (sem preços) transferida");
    } catch { toast.error("Geração da medição impossível"); }
  };

  // ---- Métré comparé (versions d'un niveau) ----
  const loadMetreVersions = async () => {
    if (!plan?.plan_id) return;
    try { const { data } = await api.get(`/takeoffs/metre-versions/${plan.plan_id}`); setMetreVersions(data.versions || []); }
    catch { /* noop */ }
  };
  const openMetreVersions = () => { setMetreSel([]); setMetreCompare(null); setMetreVerOpen(true); loadMetreVersions(); };
  const snapshotMetre = async () => {
    try {
      await api.post("/takeoffs/metre-versions", { plan_id: plan.plan_id, label: metreLabel.trim(), margin_pct: 0 });
      toast.success("Versão da medição guardada");
      setMetreLabel(""); loadMetreVersions();
    } catch { toast.error("Não foi possível guardar"); }
  };
  const toggleMetreSel = (id) => setMetreSel((s) => s.includes(id) ? s.filter((x) => x !== id) : (s.length >= 2 ? [s[1], id] : [...s, id]));
  const runMetreCompare = async () => {
    if (metreSel.length !== 2) return toast.error("Selecione duas versões");
    try { const { data } = await api.get(`/takeoffs/metre-versions/compare`, { params: { a: metreSel[0], b: metreSel[1] } }); setMetreCompare(data); }
    catch { toast.error("Comparação impossível"); }
  };
  const deleteMetreVersion = async (id) => {
    try { await api.delete(`/takeoffs/metre-versions/${id}`); setMetreSel((s) => s.filter((x) => x !== id)); loadMetreVersions(); }
    catch { toast.error("Não foi possível eliminar"); }
  };

  const deleteGroup = async (g) => {
    if (!(await confirmDialog({ title: "Eliminar este projeto multinível?", description: `« ${g.name} » — as plantas não são eliminadas.` }))) return;
    try { await api.delete(`/takeoffs/multilevel/groups/${g.group_id}`); loadPlanGroups(); toast.success("Projeto eliminado"); }
    catch { toast.error("Não foi possível eliminar"); }
  };

  const addLevel = (plan_id) => setGroupBuilder((gb) => gb.levels.some((l) => l.plan_id === plan_id) ? gb
    : { ...gb, levels: [...gb.levels, { plan_id, level_label: LEVEL_SUGGESTIONS[gb.levels.length] || "" }] });
  const removeLevel = (plan_id) => setGroupBuilder((gb) => ({ ...gb, levels: gb.levels.filter((l) => l.plan_id !== plan_id) }));
  const setLevelLabel = (plan_id, label) => setGroupBuilder((gb) => ({ ...gb, levels: gb.levels.map((l) => l.plan_id === plan_id ? { ...l, level_label: label } : l) }));

  const trashPlan = async (p) => {
    const ok = await confirmDialog({ title: "Mover esta planta para o lixo?", description: `« ${p.filename || "Plano sem nome"} » e as suas medições continuarão recuperáveis durante 30 dias no lixo.`, confirmLabel: "Mover para o lixo" });
    if (!ok) return;
    try {
      await api.delete(`/takeoffs/${p.plan_id}`);
      toast.success("Planta movida para o lixo — recuperável durante 30 dias", { action: { label: "Lixo", onClick: () => nav("/corbeille") } });
      if (plan?.plan_id === p.plan_id) setPlan(null);
      loadAllPlans();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível eliminar");
    }
  };

  const bulkTrashPlans = async (ids) => {
    if (!ids.length) return;
    const ok = await confirmDialog({ title: `Colocar ${ids.length} planta${ids.length > 1 ? "s" : ""} para o lixo?`, description: "Continuarão recuperáveis durante 30 dias no lixo.", confirmLabel: "Mover para o lixo" });
    if (!ok) return;
    try {
      const { data } = await api.post("/takeoffs/bulk-trash", { plan_ids: ids });
      toast.success(`${data.trashed} planta${data.trashed > 1 ? "s" : ""} movida(s) para o lixo`, { action: { label: "Lixo", onClick: () => nav("/corbeille") } });
      setSelectedRecent([]);
      if (plan && ids.includes(plan.plan_id)) setPlan(null);
      loadAllPlans();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível eliminar"); }
  };

  const trashAllPlans = async () => {
    const ok = await confirmDialog({ title: `Eliminar tudo (${allPlans.length} planta${allPlans.length > 1 ? "s" : ""})?`, description: "Todas as suas plantas serão movidas para o lixo (recuperáveis durante 30 dias).", confirmLabel: "Mover tudo para o lixo" });
    if (!ok) return;
    try {
      const { data } = await api.post("/takeoffs/bulk-trash", { all: true });
      toast.success(`${data.trashed} planta${data.trashed > 1 ? "s" : ""} movida(s) para o lixo`, { action: { label: "Lixo", onClick: () => nav("/corbeille") } });
      setSelectedRecent([]);
      setPlan(null);
      loadAllPlans();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível eliminar"); }
  };

  const applyWallHeightToPage = async () => {
    if (!plan?.plan_id) return;
    const h = Number(planDefaults.ceiling_h_m);
    if (!h || h <= 0) return toast.error("Defina uma altura de parede válida nas definições");
    const ok = await confirmDialog({ title: `Aplicar ${h} m a todas as cotas da página?`, description: "Todas as cotas lineares (paredes / distâncias) desta página passarão a ter esta altura; as áreas em m² são recalculadas automaticamente.", confirmLabel: "Aplicar" });
    if (!ok) return;
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measurements/wall-height-bulk`, { height_m: h, page_index: pageIndex });
      toast.success(`Altura ${h} m aplicada a ${data.updated} cota${data.updated > 1 ? "s" : ""}`);
      const { data: full } = await api.get(`/takeoffs/${plan.plan_id}`);
      setPlan(full);
    } catch (e) { toast.error(e?.response?.data?.detail || "Aplicação impossível"); }
  };

  const duplicatePlan = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/duplicate`);
      toast.success(`Planta duplicada — ${data.rooms} divisão${data.rooms > 1 ? "s" : ""} copiada${data.rooms > 1 ? "s" : ""}`);
      const { data: full } = await api.get(`/takeoffs/${data.plan_id}`);
      setPlan(full);
      setPageIndex(0);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Duplicação impossível");
    }
  };

  const downloadMultiQuote = async () => {
    if (multiSelected.length === 0) return toast.error("Selecione pelo menos 1 planta");
    setMultiBusy(true);
    try {
      const { data: blob } = await api.post("/quotes/multi-pdf", {
        plan_ids: multiSelected, project_name: multiProjectName.trim() || null,
        finish: quoteFinish, floor_material: quoteFloor,
      }, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `orcamento-projeto.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Orçamento do projeto (${multiSelected.length} plantas) transferido`);
      setMultiDialog(false);
    } catch (e) { toast.error(e.message || "Impossível exportar"); }
    finally { setMultiBusy(false); }
  };

  const downloadMultiMetre = async () => {
    if (multiSelected.length === 0) return toast.error("Selecione pelo menos 1 planta");
    setMultiBusy(true);
    try {
      const res = await api.post("/takeoffs/metre-multi-pdf",
        { plan_ids: multiSelected, project_name: multiProjectName.trim() || null },
        { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = "medicao-grupo.pdf";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Medição agrupada (${multiSelected.length} plantas) transferido`);
      setMultiDialog(false);
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível exportar"); }
    finally { setMultiBusy(false); }
  };

  // Phase A — créer UN devis éditable consolidé (gros œuvre + maison + ferraillage)
  const createConsolidatedQuote = async () => {
    if (multiSelected.length === 0) return toast.error("Selecione pelo menos 1 planta");
    setConsolidatedBusy(true);
    try {
      const { data } = await api.post("/documents/from-plans", {
        plan_ids: multiSelected,
        project_name: multiProjectName.trim() || "",
        subcontract_plan_ids: subcontractSel.filter((id) => multiSelected.includes(id)),
      });
      toast.success(`Orçamento consolidado criado — ${data.line_count} linha(s)`);
      setMultiDialog(false);
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Criação do orçamento consolidado impossível");
    } finally { setConsolidatedBusy(false); }
  };

  // Phase A — rattacher des plans de ferraillage à un plan de coffrage (gros œuvre)
  const linkFerraillage = async (coffragePlanId, ferrIds) => {
    try {
      await api.patch(`/takeoffs/${coffragePlanId}/link-ferraillage`, {
        ferraillage_plan_ids: ferrIds,
      });
      setAllPlans((prev) => prev.map((p) =>
        p.plan_id === coffragePlanId ? { ...p, ferraillage_plan_ids: ferrIds } : p));
      toast.success(ferrIds.length ? "Armação associada" : "Associação removida");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Associação impossível");
    }
  };

  const createSignatureLink = async (logId) => {
    const raw = window.prompt(
      "Sinal pedido à assinatura (% do c/ IVA) — 30 por defeito, ou 0 para desativar:",
      "30");
    if (raw === null) return;
    const pct = Math.max(0, Math.min(100, parseFloat(raw) || 0));
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/quote-sends/${logId}/signature-link`,
        { deposit_pct: pct });
      const fullUrl = data.url.startsWith("http") ? data.url
        : `${window.location.origin}${data.url}`;
      await navigator.clipboard.writeText(fullUrl);
      toast.success(pct > 0
        ? `Ligação copiada — sinal ${pct}% na assinatura`
        : "Link de assinatura copiado (sem sinal)");
      await loadQuoteSends();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Geração do link impossível");
    }
  };

  const reclassifyWall = async (segIndex) => {
    if (!plan?.plan_id || !detectedWalls?.segments?.[segIndex]) return;
    const s = detectedWalls.segments[segIndex];
    const order = ["porteur", "cloison", "doublage"];
    const next = order[(order.indexOf(s.wall_type || "cloison") + 1) % order.length];
    try {
      await api.patch(
        `/takeoffs/${plan.plan_id}/walls/${pageIndex}/${s.wall_id}/type`,
        { wall_type: next }
      );
      const updated = [...detectedWalls.segments];
      updated[segIndex] = { ...s, wall_type: next };
      setDetectedWalls({ ...detectedWalls, segments: updated });
      toast.success(`Parede reclassificada: ${next}`);
      await loadWallsSummary();
    } catch { toast.error("Reclassificação impossível"); }
  };

  const runSnapshotCompare = async () => {
    if (!plan?.plan_id || !snapPickA || !snapPickB) return;
    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/history/compare`,
        { before_snapshot_id: snapPickA, after_snapshot_id: snapPickB }
      );
      setSnapCompareResult(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Comparação impossível");
    }
  };

  // ---------- RENDER ----------

  // Gate : Plan 2D + 3D reserved to Pro Business
  if (!billingLoading && !has("plan_takeoff")) {
    return (
      <div className="mx-auto max-w-[900px] px-5 py-16" data-testid="plan-paywall">
        <div className="surface p-10 grid gap-6 text-center">
          <div className="h-16 w-16 grid place-items-center bg-primary/15 rounded-full mx-auto">
            <Lock className="h-8 w-8 text-primary" />
          </div>
          <div>
            <p className="overline text-primary">Funcionalidade Pro Business</p>
            <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mt-3">
              Medir + Renderização 3D
            </h1>
            <p className="text-sm text-muted-foreground mt-3 max-w-lg mx-auto">
              A importação de plantas, a medição automática de áreas, o takeoff calibrado e a geração de renderizações 3D / vídeos 3D estão reservados ao plano
              <b className="text-foreground"> Pro Business</b>. Mude para este plano para desbloquear estas ferramentas profissionais.
            </p>
          </div>
          <div className="grid sm:grid-cols-3 gap-3 max-w-xl mx-auto">
            {[
              "Importação PDF/DXF/foto",
              "Calibragem + medições profissionais",
              "Renderização 3D + vídeo",
            ].map((f) => (
              <div key={f} className="border border-border rounded-sm p-3 text-xs">
                {f}
              </div>
            ))}
          </div>
          <div className="flex items-center justify-center gap-3 flex-wrap">
            <Button
              onClick={() => nav("/planos")}
              data-testid="plan-paywall-upgrade"
              className="rounded-sm h-11 px-6"
            >
              Passar para Pro Business
            </Button>
            <Button
              variant="outline"
              onClick={() => nav("/dashboard")}
              className="rounded-sm h-11 px-6"
            >
              Voltar ao painel
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            O seu plano atual: <b>{tier || "free"}</b>
          </p>
        </div>
      </div>
    );
  }

  // S3.1 fix — Dialog de pré-visualização ampliada partilhado entre o branch
  // pre-upload (!plan) e o branch workspace (post-upload). Renderizado SEMPRE
  // que o componente está montado para que o botão `recent-plan-zoom-<id>`
  // funcione mesmo sem plano carregado.
  const planZoomDialog = (
    <Dialog open={!!zoomPlan} onOpenChange={(o) => !o && setZoomPlan(null)}>
      <DialogContent className="max-w-4xl p-0 overflow-hidden" data-testid="plan-zoom-dialog">
        <DialogHeader className="p-4 pb-2">
          <DialogTitle className="text-base truncate" data-testid="plan-zoom-dialog-title">
            {zoomPlan?.filename || "Pré-visualização"}
          </DialogTitle>
          <DialogDescription className="text-xs">
            Pinch (mobile) ou botões +/-/repor (desktop). Arrasta para deslocar quando ampliado.
          </DialogDescription>
        </DialogHeader>
        {zoomPlan && (
          <PinchZoom
            className="w-full h-[70vh] bg-muted/40 dark:bg-neutral-900"
            testId="plan-zoom-viewer"
            maxScale={5}
          >
            <img
              src={`${String(api.defaults?.baseURL || "/api").replace(/\/$/, "")}/takeoffs/${zoomPlan.plan_id}/thumb`}
              alt={zoomPlan.filename || "Planta"}
              className="w-full h-full object-contain select-none pointer-events-none"
              draggable={false}
              data-testid="plan-zoom-image"
            />
          </PinchZoom>
        )}
        <DialogFooter className="p-4 pt-2">
          <Button variant="outline" onClick={() => setZoomPlan(null)} data-testid="plan-zoom-dialog-close">Fechar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  if (!plan) {
    return (
      <div className="plan-workspace mx-auto max-w-[1100px] px-5 py-10 grid gap-8">
      {cadFile && <CadUnitPicker file={cadFile} onChoose={chooseCadUnit} onCancel={() => chooseCadUnit(null)} />}
      <Dialog open={pendingFiles.length > 0} onOpenChange={(o) => { if (!o && !importingBatch) { setPendingFiles([]); setGroupImport({ enabled: false, mode: "new", name: "", groupId: "" }); } }}>
        <DialogContent className="rounded-sm max-w-lg" data-testid="plan-import-dialog">
          <DialogHeader>
            <DialogTitle>Importar {pendingFiles.length} plan{pendingFiles.length > 1 ? "s" : ""}</DialogTitle>
            <DialogDescription>
              Dê um nome a cada planta antes da importação. Esse nome será apresentado na lista e retomado nas exportações PDF.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 max-h-[50vh] overflow-auto pr-1">
            {pendingFiles.map((it, idx) => (
              <div key={it.id} className="flex items-center gap-2" data-testid={`pending-file-${idx}`}>
                <Input value={it.name} disabled={importingBatch}
                       onChange={(e) => setPendingFiles((prev) => prev.map((p) => p.id === it.id ? { ...p, name: e.target.value } : p))}
                       data-testid={`pending-file-name-${idx}`}
                       className="h-9 flex-1" placeholder="Nome da planta" />
                {groupImport.enabled && (
                  <Input value={it.level || ""} disabled={importingBatch} list="level-suggestions-import"
                         onChange={(e) => setPendingFiles((prev) => prev.map((p) => p.id === it.id ? { ...p, level: e.target.value } : p))}
                         data-testid={`pending-file-level-${idx}`}
                         className="h-9 w-24 shrink-0" placeholder="Piso" />
                )}
                <span className="text-[10px] text-muted-foreground truncate max-w-[120px]" title={it.file.name}>
                  {it.file.name.split(".").pop()?.toUpperCase()} · {(it.file.size / (1024 * 1024)).toFixed(1)} MB
                </span>
                {!importingBatch && pendingFiles.length > 1 && (
                  <button onClick={() => setPendingFiles((prev) => prev.filter((p) => p.id !== it.id))}
                          data-testid={`pending-file-remove-${idx}`}
                          className="text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
                )}
              </div>
            ))}
          </div>
          <div className="pt-1">
            <input id="plan-add-more-input" type="file" multiple accept=".pdf,.dxf,.dwg,.jpg,.jpeg,.png,.webp,.zip" className="hidden"
                   onChange={(e) => { ingestFiles(e.target.files); e.target.value = ""; }} data-testid="plan-add-more-input" />
            <button type="button" disabled={importingBatch}
                    onClick={() => document.getElementById("plan-add-more-input")?.click()}
                    data-testid="plan-add-more-btn"
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:gap-2.5 transition-all disabled:opacity-50">
              <Plus className="h-4 w-4" /> Adicionar outras plantas
            </button>
          </div>
          <datalist id="level-suggestions-import">{LEVEL_SUGGESTIONS.map((s) => <option key={s} value={s} />)}</datalist>
          <div className="rounded-sm border border-border p-3 space-y-2 bg-muted/30">
            <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
              <input type="checkbox" checked={groupImport.enabled} disabled={importingBatch}
                     onChange={(e) => setGroupImport((g) => ({ ...g, enabled: e.target.checked }))}
                     data-testid="group-import-toggle" className="accent-primary h-4 w-4" />
              <Layers className="h-4 w-4 text-primary" /> Agrupar num projeto multinível (um único relatório consolidado)
            </label>
            {groupImport.enabled && (
              <div className="space-y-2">
                <div className="flex gap-2">
                  <button type="button" onClick={() => setGroupImport((g) => ({ ...g, mode: "new" }))}
                          data-testid="group-mode-new"
                          className={`flex-1 text-xs font-semibold rounded-sm border px-2 py-1.5 ${groupImport.mode === "new" ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>
                    Novo projeto
                  </button>
                  <button type="button" disabled={planGroups.length === 0}
                          onClick={() => setGroupImport((g) => ({ ...g, mode: "existing", groupId: g.groupId || planGroups[0]?.group_id || "" }))}
                          data-testid="group-mode-existing"
                          className={`flex-1 text-xs font-semibold rounded-sm border px-2 py-1.5 disabled:opacity-40 ${groupImport.mode === "existing" ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>
                    Projeto existente
                  </button>
                </div>
                {groupImport.mode === "existing" ? (
                  <select value={groupImport.groupId} disabled={importingBatch}
                          onChange={(e) => setGroupImport((g) => ({ ...g, groupId: e.target.value }))}
                          data-testid="group-import-select"
                          className="w-full h-9 rounded-sm border border-border bg-background px-2 text-sm">
                    {planGroups.map((g) => <option key={g.group_id} value={g.group_id}>{g.name} ({(g.levels || []).length} pisos)</option>)}
                  </select>
                ) : (
                  <Input value={groupImport.name} disabled={importingBatch}
                         onChange={(e) => setGroupImport((g) => ({ ...g, name: e.target.value }))}
                         data-testid="group-import-name" className="h-9" placeholder="Nome do projeto (ex.: Moradia Silva)" />
                )}
                <p className="text-[11px] text-muted-foreground">Os pisos (R/C, 1.º andar…) são pré-preenchidos automaticamente. Meça depois cada piso: a medição e a orçamentação são consolidadas num único relatório.</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={importingBatch} onClick={() => { setPendingFiles([]); setGroupImport({ enabled: false, mode: "new", name: "", groupId: "" }); }} className="rounded-sm">Cancelar</Button>
            <Button onClick={importPending} disabled={importingBatch || pendingFiles.some((p) => !p.name.trim()) || (groupImport.enabled && groupImport.mode === "new" && !groupImport.name.trim()) || (groupImport.enabled && groupImport.mode === "existing" && !groupImport.groupId)}
                    data-testid="plan-import-confirm" className="rounded-sm gap-2">
              {importingBatch ? "Importação em curso…" : groupImport.enabled ? (groupImport.mode === "existing" ? "Importar e associar" : "Importar e criar o projeto") : "Importar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
        {chantierId && <ChantierContextBar chantierId={chantierId} chantier={chantier} />}
        <div className="plan-library-hero">
          <p className="plan-eyebrow">PLANTAS & MEDIÇÕES · CONSTRUPILOT</p>
          <h1 className="mt-3 font-display text-4xl lg:text-5xl font-bold tracking-tight">
            Da planta ao orçamento, num mesmo espaço.
          </h1>
          <p className="text-sm text-muted-foreground mt-3 max-w-2xl">
            Importe os seus documentos, indique a escala, analise e verifique as quantidades. Encontre depois as suas medições e a sua orçamentação no mesmo processo.
          </p>
          <div className="mt-4">
            <MeasureHelpDialog />
          </div>
        </div>

        <PromptBar
          appKey="plantas"
          placeholder="Ex.: «Moradia T3 com 2 pisos, pé-direito 2,60 m, habitação»"
          examples="Descreva o edifício antes de carregar a planta — já pré-preenchemos tipologia, pisos e pé-direito."
          onFill={({ params = {} }) => {
            const bits = [];
            if (params.tipo_edificio) bits.push(params.tipo_edificio);
            if (params.tipologia) bits.push(params.tipologia);
            if (params.pisos) bits.push(`${params.pisos} piso(s)`);
            if (params.pe_direito_m) bits.push(`pé-direito ${params.pe_direito_m} m`);
            if (bits.length) toast.success(`Dados aplicados: ${bits.join(" · ")}`);
          }}
        />

        <label
          htmlFor="plan-upload-input"
          className={`surface p-16 grid place-items-center gap-4 cursor-pointer transition-all border-2 ${
            dragActive
              ? "border-primary bg-primary/5 scale-[1.01] shadow-lg"
              : "border-transparent hover:border-primary"
          }`}
          data-testid="plan-upload-dropzone"
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setDragActive(true); }}
          onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); setDragActive(true); }}
          onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); setDragActive(false); }}
          onDrop={(e) => {
            e.preventDefault(); e.stopPropagation();
            setDragActive(false);
            const files = e.dataTransfer?.files;
            if (files?.length) ingestFiles(files);
          }}
        >
          <div className={`h-16 w-16 grid place-items-center rounded-sm transition-colors ${
            dragActive ? "bg-primary/25" : "bg-primary/10"
          }`}>
            <Upload className={`h-8 w-8 text-primary ${dragActive ? "animate-bounce" : ""}`} />
          </div>
          <div className="text-center">
            <p className="font-display text-xl font-bold">
              {uploading ? "Importação em curso…" : dragActive ? "Solte para importar" : "Importar a minha planta"}
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              PDF · DXF · DWG · JPG · PNG · WEBP · ZIP — até 20 MB — selecione vários ficheiros, uma pasta ou um ZIP
            </p>
          </div>
          <Input
            id="plan-upload-input"
            type="file"
            multiple
            accept="application/pdf,image/png,image/jpeg,image/webp,.dxf,.dwg,.zip"
            className="sr-only"
            onChange={(e) => { ingestFiles(e.target.files); e.target.value = ""; }}
            data-testid="plan-upload-input"
          />
          <input
            id="plan-folder-input"
            type="file"
            webkitdirectory=""
            directory=""
            multiple
            className="sr-only"
            onChange={(e) => { ingestFiles(e.target.files); e.target.value = ""; }}
            data-testid="plan-folder-input"
          />
        </label>

        <div className="flex justify-center gap-2 -mt-1 flex-wrap">
          <Button type="button" variant="outline" disabled={uploading}
                  onClick={() => document.getElementById("plan-upload-input")?.click()}
                  data-testid="import-multiple-btn" className="rounded-sm gap-2">
            <Layers className="h-4 w-4" /> Importar várias plantas de uma vez
          </Button>
          <Button type="button" variant="outline" disabled={uploading}
                  onClick={() => document.getElementById("plan-folder-input")?.click()}
                  data-testid="import-folder-btn" className="rounded-sm gap-2">
            <Upload className="h-4 w-4" /> Importar uma pasta / ZIP
          </Button>
        </div>

        <div className="flex items-center gap-4 justify-between flex-wrap">
          <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={deskewEnabled}
              onChange={(e) => setDeskewEnabled(e.target.checked)}
              data-testid="deskew-toggle"
              className="accent-primary h-4 w-4"
            />
            Corrigir a perspetiva (foto smartphone inclinada)
          </label>
          <button
            onClick={() => nav("/plan/compare")}
            data-testid="plan-compare-link"
            className="text-sm text-primary hover:underline gap-1 inline-flex items-center"
          >
            Comparar 2 planos (antes / depois) →
          </button>
        </div>

        <div className="grid sm:grid-cols-3 gap-4">
          {[
            { icon: Ruler, title: "Formatos variados", desc: "PDF · DXF · DWG · JPG · PNG · WEBP — DWG convertido automaticamente" },
            { icon: Wand2, title: "Deteção automática", desc: "Paredes (OpenCV) · divisões flood-fill · deskew foto inclinada" },
            { icon: Calculator, title: "Multi-pisos", desc: "R/C · R+1 · R+2 · águas-furtadas — medições por nível + total" },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="surface p-6">
              <Icon className="h-5 w-5 text-primary" />
              <p className="font-display font-bold mt-3">{title}</p>
              <p className="text-xs text-muted-foreground mt-1">{desc}</p>
            </div>
          ))}
        </div>

        {allPlans.length > 0 && (
          <div className="surface p-6" data-testid="recent-plans-list">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
              <p className="overline flex items-center gap-2">
                <History className="h-4 w-4" /> As minhas plantas recentes
              </p>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-muted-foreground">
                  {allPlans.length} plan{allPlans.length > 1 ? "s" : ""} guardado{allPlans.length > 1 ? "s" : ""}
                </span>
                {selectedRecent.length > 0 && (
                  <Button variant="outline" size="sm" onClick={() => bulkTrashPlans(selectedRecent)}
                          data-testid="trash-selected-plans-btn"
                          className="rounded-sm gap-1 h-8 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
                    <Trash2 className="h-3.5 w-3.5" /> Eliminar a seleção ({selectedRecent.length})
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={trashAllPlans}
                        data-testid="trash-all-plans-btn"
                        className="rounded-sm gap-1 h-8 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
                  <Trash2 className="h-3.5 w-3.5" /> Eliminar tudo
                </Button>
              </div>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {allPlans.slice(0, 6).map((p) => (
                <div key={p.plan_id} className="relative group">
                <input type="checkbox" checked={selectedRecent.includes(p.plan_id)}
                       onChange={() => setSelectedRecent((s) => s.includes(p.plan_id) ? s.filter((x) => x !== p.plan_id) : [...s, p.plan_id])}
                       data-testid={`recent-plan-select-${p.plan_id}`}
                       onClick={(e) => e.stopPropagation()}
                       className="absolute top-2 left-2 z-10 h-4 w-4 accent-destructive cursor-pointer" />
                <button
                  onClick={async () => {
                    try {
                      const { data } = await api.get(`/takeoffs/${p.plan_id}`);
                      setPlan(data);
                      setPageIndex(0);
                    } catch {
                      toast.error("Impossível abrir este plano");
                    }
                  }}
                  data-testid={`recent-plan-${p.plan_id}`}
                  className="text-left surface p-4 pl-8 pr-10 w-full h-full hover:border-primary transition-colors"
                >
                  <img src={`${String(api.defaults?.baseURL || "/api").replace(/\/$/, "")}/takeoffs/${p.plan_id}/thumb`} alt="" loading="lazy"
                       onError={(e) => { e.currentTarget.style.display = "none"; }}
                       className="w-full h-24 object-cover rounded-sm mb-2 bg-muted/40 border border-border"
                       data-testid={`recent-plan-thumb-${p.plan_id}`} />
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-display font-bold text-sm truncate flex-1 group-hover:text-primary">
                      {p.filename || "Plano sem nome"}
                    </p>
                    <Badge variant="outline" className="text-[10px] rounded-sm shrink-0">
                      {p.rooms_count || 0} pce
                    </Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    {p.page_count || 1} page{p.page_count > 1 ? "s" : ""}
                    {p.created_at && (
                      <span> · {new Date(p.created_at).toLocaleDateString("pt-PT")}</span>
                    )}
                  </p>
                </button>
                <button type="button" onClick={() => nav(`/analyse/${p.plan_id}`)} title="Análise rastreável (medição → orçamento)" aria-label="Análise rastreável"
                  className="absolute bottom-2 right-11 h-8 w-8 inline-flex items-center justify-center rounded-sm text-muted-foreground opacity-60 group-hover:opacity-100 hover:text-primary hover:bg-primary/10 transition-colors"
                  data-testid={`recent-plan-analysis-${p.plan_id}`}>
                  <ClipboardCheck className="h-3.5 w-3.5" />
                </button>
                <button type="button" onClick={() => setZoomPlan(p)} title="Pré-visualizar com zoom" aria-label="Ampliar"
                  className="absolute bottom-2 right-[76px] h-8 w-8 inline-flex items-center justify-center rounded-sm text-muted-foreground opacity-60 group-hover:opacity-100 hover:text-primary hover:bg-primary/10 transition-colors"
                  data-testid={`recent-plan-zoom-${p.plan_id}`}>
                  <ZoomIn className="h-3.5 w-3.5" />
                </button>
                <button type="button" onClick={() => trashPlan(p)} title="Mover para o lixo" aria-label="Mover para o lixo"
                  className="absolute bottom-2 right-2 h-8 w-8 inline-flex items-center justify-center rounded-sm text-muted-foreground opacity-60 group-hover:opacity-100 hover:text-destructive hover:bg-destructive/10 transition-colors"
                  data-testid={`recent-plan-delete-${p.plan_id}`}>
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
                </div>
              ))}
            </div>
            {allPlans.length > 6 && (
              <p className="text-xs text-muted-foreground mt-3 text-center">
                + {allPlans.length - 6} outros — use «Comparar 2 plantas» para ver tudo
              </p>
            )}
          </div>
        )}

        {/* PROJETS MULTI-NIVEAUX */}
        <div className="surface p-5" data-testid="plan-groups-section">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="font-display font-bold flex items-center gap-2"><Layers className="h-4 w-4 text-primary" /> Projetos multinível</p>
              <p className="text-[11px] text-muted-foreground">Agrupe Fundações, R/C, 1.º andar… de uma mesma obra — medição e orçamentação consolidadas.</p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={openAgentBox} data-testid="open-agents-btn" className="rounded-sm gap-1">
                <Bot className="h-4 w-4 text-primary" /> Agentes IA
              </Button>
              <Button size="sm" onClick={openGroupBuilder} data-testid="new-plan-group-btn" className="rounded-sm gap-1">
                <Plus className="h-4 w-4" /> Novo projeto
              </Button>
            </div>
          </div>
          {planGroups.length === 0 ? (
            <p className="text-xs text-muted-foreground">Nenhum projeto multinível por agora.</p>
          ) : (
            <div className="grid sm:grid-cols-2 gap-3">
              {planGroups.map((g) => (
                <div key={g.group_id} className="rounded-sm border border-border p-3 hover:border-primary transition-colors" data-testid={`plan-group-${g.group_id}`}>
                  <div className="flex items-start justify-between gap-2">
                    <button onClick={() => openGroupConsolidated(g)} className="text-left flex-1" data-testid={`open-group-${g.group_id}`}>
                      <p className="font-semibold text-sm hover:text-primary">{g.name}</p>
                      <p className="text-[11px] text-muted-foreground">{g.levels.length} niveau{g.levels.length > 1 ? "x" : ""} : {g.levels.map((l) => l.level_label || l.filename || "?").join(" · ")}</p>
                    </button>
                    <div className="flex gap-1 shrink-0">
                      <button onClick={() => editGroup(g)} title="Editar" data-testid={`edit-group-${g.group_id}`} className="text-muted-foreground hover:text-primary"><Search className="h-3.5 w-3.5" /></button>
                      <button onClick={() => deleteGroup(g)} title="Eliminar" data-testid={`delete-group-${g.group_id}`} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* DIALOG — constructeur de projet multi-niveaux */}
        <Dialog open={!!groupBuilder} onOpenChange={(o) => { if (!o) setGroupBuilder(null); }}>
          <DialogContent className="rounded-sm max-w-lg" data-testid="group-builder-dialog">
            <DialogHeader>
              <DialogTitle>{groupBuilder?.group_id ? "Editar o projeto" : "Novo projeto multinível"}</DialogTitle>
              <DialogDescription>Dê um nome ao projeto, adicione as plantas e identifique cada piso.{chantierId ? " As plantas serão associadas ao processo de obra atual." : ""}</DialogDescription>
            </DialogHeader>
            {groupBuilder && (
              <div className="space-y-3">
                <Input value={groupBuilder.name} onChange={(e) => setGroupBuilder((gb) => ({ ...gb, name: e.target.value }))}
                       placeholder="Nome do projeto (ex.: Moradia Silva)" data-testid="group-name-input" className="h-9" />
                <div>
                  <Label className="text-xs">Pisos do projeto ({groupBuilder.levels.length})</Label>
                  <div className="space-y-1.5 mt-1 max-h-40 overflow-auto">
                    {groupBuilder.levels.map((l) => {
                      const p = allPlans.find((x) => x.plan_id === l.plan_id);
                      return (
                        <div key={l.plan_id} className="flex items-center gap-2" data-testid={`group-level-${l.plan_id}`}>
                          <Input value={l.level_label} onChange={(e) => setLevelLabel(l.plan_id, e.target.value)}
                                 list="level-suggestions" placeholder="Piso" className="h-8 w-32 text-xs" data-testid={`group-level-label-${l.plan_id}`} />
                          <span className="text-[11px] flex-1 truncate">{p?.filename || l.plan_id}</span>
                          <button onClick={() => removeLevel(l.plan_id)} className="text-muted-foreground hover:text-destructive"><X className="h-4 w-4" /></button>
                        </div>
                      );
                    })}
                    {groupBuilder.levels.length === 0 && <p className="text-[11px] text-muted-foreground">Adicione plantas a partir da lista abaixo.</p>}
                  </div>
                  <datalist id="level-suggestions">{LEVEL_SUGGESTIONS.map((s) => <option key={s} value={s} />)}</datalist>
                </div>
                <div>
                  <Label className="text-xs">Plantas disponíveis</Label>
                  <div className="flex flex-wrap gap-1.5 mt-1 max-h-32 overflow-auto">
                    {allPlans.filter((p) => !groupBuilder.levels.some((l) => l.plan_id === p.plan_id)).map((p) => (
                      <button key={p.plan_id} onClick={() => addLevel(p.plan_id)}
                              data-testid={`add-plan-${p.plan_id}`}
                              className="rounded-full border border-border px-2 py-0.5 text-[11px] hover:border-primary hover:text-primary">
                        + {p.filename || p.plan_id}
                      </button>
                    ))}
                    {allPlans.length === 0 && <p className="text-[11px] text-muted-foreground">Importe primeiro plantas.</p>}
                  </div>
                </div>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setGroupBuilder(null)} className="rounded-sm">Cancelar</Button>
              <Button onClick={saveGroup} data-testid="group-save-btn" className="rounded-sm gap-2"><Save className="h-4 w-4" /> Guardar</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* DIALOG — vue consolidée */}
        <Dialog open={!!groupView} onOpenChange={(o) => { if (!o) setGroupView(null); }}>
          <DialogContent className="rounded-sm max-w-2xl" data-testid="group-consolidated-dialog">
            <DialogHeader>
              <DialogTitle>Consolidado — {groupView?.name}</DialogTitle>
              <DialogDescription>Medição e orçamentação das medições guardadas. O orçamento completo da obra ainda está por estabelecer.</DialogDescription>
            </DialogHeader>
            {groupView?.loading ? (
              <div className="py-8 text-center text-sm text-muted-foreground">Cálculo em curso…</div>
            ) : groupView && (
              <div className="space-y-2 max-h-[55vh] overflow-auto">
                <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950" data-testid="group-scope-warning">
                  <p className="font-semibold">Estimativa parcial</p>
                  <ul className="mt-1 list-disc space-y-1 pl-4">
                    {(groupView.coverage?.warnings || ["O montante incide apenas sobre as medições guardadas, não sobre todos os edifícios e capítulos."]).map((warning, index) => <li key={index}>{warning}</li>)}
                  </ul>
                </div>
                {(groupView.levels || []).map((lv) => (
                  <div key={lv.plan_id} className="rounded border border-border p-2" data-testid={`consolidated-level-${lv.plan_id}`}>
                    <div className="flex flex-wrap justify-between items-center text-sm font-medium gap-2">
                      <span className="truncate">{lv.level_label || "Piso"} <span className="text-muted-foreground text-xs">· {lv.filename || lv.plan_id}</span></span>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="num">{lv.consolidated?.chiffrage?.priced_measures > 0 ? `${lv.consolidated.chiffrage.ht_with_margin.toFixed(2)} € s/ IVA parcial` : "Não orçamentado"}</span>
                        <Button size="sm" variant="outline" data-testid={`consolidated-open-${lv.plan_id}`}
                                onClick={() => { setGroupView(null); openPlanById(lv.plan_id); }}
                                className="rounded-sm h-7 gap-1 text-xs border-primary/50 text-primary hover:bg-primary hover:text-white">
                          <Pencil className="h-3 w-3" /> Editar
                        </Button>
                      </div>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {lv.consolidated?.metre?.area_m2 || 0} m² · {lv.consolidated?.metre?.length_ml || 0} ml · {lv.consolidated?.metre?.measures || 0} medições ({lv.consolidated?.chiffrage?.priced_measures || 0} orçamentadas)
                    </div>
                  </div>
                ))}
                <div className="flex flex-col gap-2 sm:flex-row sm:justify-between border-t border-border pt-2 text-sm font-semibold">
                  <span>Subtotal medido · {groupView.totals?.area_m2 || 0} m² · {groupView.totals?.length_ml || 0} ml</span>
                  {(groupView.levels || []).some((lv) => lv.consolidated?.chiffrage?.priced_measures > 0) ? <span>s/ IVA <span className="num">{groupView.totals?.ht_with_margin?.toFixed(2)} €</span> · c/ IVA <span className="num text-primary">{groupView.totals?.ttc?.toFixed(2)} €</span></span> : <span>Não orçamentado</span>}
                </div>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setGroupView(null)} className="rounded-sm">Fechar</Button>
              {!groupView?.loading && (
                <>
                  <Button variant="outline" onClick={() => openCoverDialog()} data-testid="group-pdf-btn" className="rounded-sm gap-2">
                    <FileDown className="h-4 w-4" /> Dossier PDF
                  </Button>
                  <Button variant="outline" onClick={downloadGroupMetrePdf} data-testid="group-metre-pdf-btn" className="rounded-sm gap-2">
                    <Ruler className="h-4 w-4" /> Só medição (sem preços)
                  </Button>
                  <Button onClick={createGroupQuote} data-testid="group-create-quote-btn" className="rounded-sm gap-2">
                    <ArrowRight className="h-4 w-4" /> Criar um orçamento parcial
                  </Button>
                </>
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* DIALOG — page de garde (dossier de chiffrage) */}
        <Dialog open={!!coverDialog} onOpenChange={(o) => { if (!o) setCoverDialog(null); }}>
          <DialogContent className="rounded-sm max-w-lg" data-testid="cover-dialog">
            <DialogHeader>
              <DialogTitle>Página de rosto do processo</DialogTitle>
              <DialogDescription>
                Contactos do cliente impressos na capa. Pré-preenchidos a partir da obra, editáveis aqui.
              </DialogDescription>
            </DialogHeader>
            {coverDialog?.loading ? (
              <div className="py-8 text-center text-sm text-muted-foreground">A carregar…</div>
            ) : coverDialog && (
              <div className="space-y-3">
                <div className="text-xs text-muted-foreground">
                  Referência do processo: <span className="font-semibold text-foreground">{coverDialog.reference || "—"}</span>
                  <span className="mx-1">·</span> Logótipo &amp; empresa retomados da sua «Identidade profissional»
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Nome do cliente</Label>
                  <Input value={coverDialog.name} onChange={(e) => setCoverDialog((d) => ({ ...d, name: e.target.value }))}
                    placeholder="Sr. e Sra. Silva" data-testid="cover-client-name" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Empresa (opcional)</Label>
                  <Input value={coverDialog.company} onChange={(e) => setCoverDialog((d) => ({ ...d, company: e.target.value }))}
                    data-testid="cover-client-company" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Morada</Label>
                  <Input value={coverDialog.address} onChange={(e) => setCoverDialog((d) => ({ ...d, address: e.target.value }))}
                    placeholder="Rua das Obras, 12" data-testid="cover-client-address" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Código postal e localidade</Label>
                  <Input value={coverDialog.city} onChange={(e) => setCoverDialog((d) => ({ ...d, city: e.target.value }))}
                    placeholder="1000-001 Lisboa" data-testid="cover-client-city" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">E-mail</Label>
                    <Input value={coverDialog.email} onChange={(e) => setCoverDialog((d) => ({ ...d, email: e.target.value }))}
                      data-testid="cover-client-email" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Telefone</Label>
                    <Input value={coverDialog.phone} onChange={(e) => setCoverDialog((d) => ({ ...d, phone: e.target.value }))}
                      data-testid="cover-client-phone" />
                  </div>
                </div>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setCoverDialog(null)} className="rounded-sm">Cancelar</Button>
              <Button onClick={() => downloadGroupPdf()} disabled={coverDialog?.loading} data-testid="cover-generate-btn" className="rounded-sm gap-2">
                <FileDown className="h-4 w-4" /> Gerar o processo PDF
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* DIALOG — Affectation auto des postes (validation avant chiffrage) */}
        <Dialog open={!!autoPosteDialog} onOpenChange={(o) => { if (!o) setAutoPosteDialog(null); }}>
          <DialogContent className="rounded-sm max-w-xl z-[70]" overlayClassName="z-[70]" data-testid="auto-poste-dialog">
            <DialogHeader>
              <DialogTitle>Orçamentar a página — artigos propostos</DialogTitle>
              <DialogDescription>
                Foi proposto um artigo para cada cota de acordo com o seu título. Verifique e corrija se necessário, e depois orçamente. Os preços vêm da sua biblioteca (cálculo determinístico).
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2 max-h-[55vh] overflow-auto">
              {(autoPosteDialog?.rows || []).map((r, i) => (
                <div key={r.measurement_id} className="flex items-center gap-2 border border-border rounded-sm p-2" data-testid={`auto-poste-row-${i}`}>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium truncate">{r.label}</p>
                    <p className="text-[10px] text-muted-foreground">{r.qty} {r.family === "length" ? "ml" : "m²"}</p>
                  </div>
                  <Select value={r.poste} onValueChange={(v) => setAutoPosteDialog((d) => ({ ...d, rows: d.rows.map((x, j) => j === i ? { ...x, poste: v } : x) }))}>
                    <SelectTrigger className="h-8 w-48 rounded-sm" data-testid={`auto-poste-select-${i}`}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {posteCatalog.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Margem (%)</span>
              <Input type="number" value={chiffrageMargin} onChange={(e) => setChiffrageMargin(e.target.value)} className="h-8 w-20" data-testid="auto-poste-margin" />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setAutoPosteDialog(null)} className="rounded-sm">Cancelar</Button>
              <Button onClick={confirmAutoPoste} className="rounded-sm gap-2" data-testid="auto-poste-confirm"><Calculator className="h-4 w-4" /> Atribuir e orçamentar</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* DIALOG — Agents IA */}
        <Dialog open={!!agentBox} onOpenChange={(o) => { if (!o) setAgentBox(null); }}>          <DialogContent className="rounded-sm max-w-2xl" data-testid="agents-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2"><Bot className="h-5 w-5 text-primary" /> Agentes IA</span>
                <Button variant="ghost" size="sm" className="rounded-sm gap-1 text-xs" data-testid="agent-history-btn"
                  onClick={() => { loadAgentHistory(); setAgentBox((a) => ({ ...a, step: a.step === "history" ? "pick" : "history" })); }}>
                  <History className="h-3.5 w-3.5" /> Histórico
                </Button>
              </DialogTitle>
              <DialogDescription>
                O agente propõe um plano de ações, valida-o e depois ele executa com os seus motores determinísticos. Pode rever e corrigir — ele memoriza as suas correções.
              </DialogDescription>
            </DialogHeader>

            {agentBox?.step === "history" && (
              <div className="space-y-2 max-h-[60vh] overflow-auto" data-testid="agent-history-list">
                {agentHistory === null && <p className="text-sm text-muted-foreground p-4 text-center">A carregar…</p>}
                {agentHistory?.length === 0 && <p className="text-sm text-muted-foreground p-4 text-center">Nenhuma execução de agente por agora.</p>}
                {(agentHistory || []).map((r) => (
                  <div key={r.run_id} className="rounded-lg border border-border p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{(AGENT_CATALOG.find((a) => a.key === r.agent) || {}).name || r.agent}</span>
                      <span className={`text-[11px] px-2 py-0.5 rounded-full ${r.status === "done" ? "bg-green-100 text-green-700" : "bg-muted text-muted-foreground"}`}>{r.status === "done" ? "Executado" : "Proposto"}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-1">{new Date(r.created_at).toLocaleString("pt-PT")}{r.result?.totals ? ` · Total c/ IVA ${(r.result.totals.ttc || 0).toLocaleString("pt-PT")} €` : ""}</p>
                    {r.feedback?.rating && <p className="text-[11px] mt-1">{r.feedback.rating === "ok" ? "✓ Validado por si" : "✎ Correção guardada"}{r.feedback.note ? ` — « ${r.feedback.note} »` : ""}</p>}
                  </div>
                ))}
              </div>
            )}

            {agentBox?.step === "pick" && (
              <div className="space-y-4 max-h-[60vh] overflow-auto">
                <div className="grid sm:grid-cols-3 gap-2">
                  {AGENT_CATALOG.map((ag) => {
                    const Ico = ag.icon || Bot;
                    return (
                    <button key={ag.key} type="button" onClick={() => setAgentBox((a) => ({ ...a, agent: ag.key }))}
                      data-testid={`agent-pick-${ag.key}`}
                      className={`text-left rounded-lg border p-3 transition-all ${agentBox.agent === ag.key ? "border-primary bg-primary/5" : "border-border hover:border-primary/40"}`}>
                      <p className="text-sm font-semibold flex items-center gap-1.5">
                        <Ico className="h-4 w-4 text-primary" /> {ag.name}
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-1">{ag.desc}</p>
                    </button>
                  ); })}
                </div>
                {agentBox.agent === "dpgf" ? (
                  <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                    Este agente abre a oficina <b>Mapa de quantidades → orçamento</b> : importe o seu mapa de quantidades/caderno de encargos, ele lê o mapa, aplica os seus preços e prepara o orçamento detalhado.
                  </div>
                ) : (
                  <>
                    <div className="space-y-1">
                      <Label className="text-xs">O seu pedido (opcional)</Label>
                      <Input value={agentBox.prompt} onChange={(e) => setAgentBox((a) => ({ ...a, prompt: e.target.value }))}
                        placeholder="Ex.: Faz o processo completo desta moradia de 2 pisos" data-testid="agent-prompt" />
                    </div>
                    <div>
                      <Label className="text-xs">Plantas em causa {agentBox.agent === "compare" && <span className="text-primary">(exatamente 2: antes / depois)</span>}</Label>
                      <div className="mt-1 grid gap-1 max-h-48 overflow-auto rounded border border-border p-2">
                        {(allPlans || []).length === 0 && <p className="text-xs text-muted-foreground p-2">Nenhuma planta disponível.</p>}
                        {(allPlans || []).map((p) => (
                          <label key={p.plan_id} className="flex items-center gap-2 text-sm px-2 py-1 rounded hover:bg-muted/50 cursor-pointer" data-testid={`agent-plan-${p.plan_id}`}>
                            <input type="checkbox" checked={agentBox.selected.includes(p.plan_id)} onChange={() => agentToggle(p.plan_id)} />
                            <span className="truncate">{p.filename || p.plan_id}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {agentBox?.step === "plan" && agentBox.run && (
              <div className="space-y-3 max-h-[60vh] overflow-auto">
                <div className="rounded-lg border border-border p-3">
                  <p className="text-xs font-semibold text-primary mb-2">Plano de ações proposto</p>
                  <ol className="space-y-1.5">
                    {agentBox.run.steps.map((s, i) => (
                      <li key={s.key} className="text-sm flex gap-2" data-testid={`agent-step-${s.key}`}>
                        <span className="h-5 w-5 shrink-0 grid place-items-center rounded-full bg-primary/15 text-primary text-[11px] font-bold">{i + 1}</span>
                        <span><span className="font-medium">{s.label}</span><br /><span className="text-[11px] text-muted-foreground">{s.detail}</span></span>
                      </li>
                    ))}
                  </ol>
                </div>
                {!!agentBox.run.warnings?.length && (
                  <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-[12px] text-amber-800">
                    {agentBox.run.warnings.map((w, i) => <p key={i}>⚠ {w}</p>)}
                  </div>
                )}
                {(agentBox.agent === "report" || agentBox.agent === "devis") && (
                <div>
                  <Label className="text-xs">Pisos (corrija se necessário — o agente aprende)</Label>
                  <div className="mt-1 grid gap-1.5">
                    {agentBox.run.plan_status.map((s) => (
                      <div key={s.plan_id} className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground truncate flex-1">{s.filename}</span>
                        <Input value={s.level} onChange={(e) => agentSetLevel(s.plan_id, e.target.value)} className="h-8 w-28" data-testid={`agent-level-${s.plan_id}`} />
                      </div>
                    ))}
                  </div>
                </div>
                )}
                {(agentBox.agent === "report" || agentBox.agent === "devis") && (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs">Margem (%)</Label>
                      <Input type="number" value={agentBox.params.margin_pct} onChange={(e) => setAgentBox((a) => ({ ...a, params: { ...a.params, margin_pct: parseFloat(e.target.value) || 0 } }))} className="h-8" data-testid="agent-margin" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Nome do projeto</Label>
                      <Input value={agentBox.params.project_name} onChange={(e) => setAgentBox((a) => ({ ...a, params: { ...a.params, project_name: e.target.value } }))} className="h-8" data-testid="agent-project-name" />
                    </div>
                  </div>
                )}
                {agentBox.agent === "report" && (
                  <div className="grid grid-cols-2 gap-3">
                    <Input value={agentBox.params.client_name} onChange={(e) => setAgentBox((a) => ({ ...a, params: { ...a.params, client_name: e.target.value } }))} placeholder="Cliente (nome)" className="h-8" data-testid="agent-client-name" />
                    <Input value={agentBox.params.client_city} onChange={(e) => setAgentBox((a) => ({ ...a, params: { ...a.params, client_city: e.target.value } }))} placeholder="Cidade" className="h-8" data-testid="agent-client-city" />
                  </div>
                )}
              </div>
            )}

            {agentBox?.step === "result" && agentBox.result && (
              <div className="space-y-3">
                <div className="rounded-lg border border-green-300 bg-green-50 p-3 text-sm text-green-800" data-testid="agent-result">
                  <p className="font-semibold">✓ Agente concluído</p>
                  {agentBox.result.kind === "pdf" && <p className="text-[12px] mt-1">Processo gerado · {agentBox.result.levels} piso(s) · Total c/ IVA {(agentBox.result.totals?.ttc || 0).toLocaleString("pt-PT")} €</p>}
                  {agentBox.result.kind === "quote" && <p className="text-[12px] mt-1">Orçamento consolidado criado — editável no editor.</p>}
                  {agentBox.result.kind === "summary" && <p className="text-[12px] mt-1">{agentBox.result.total_measures} medições · {agentBox.result.total_openings} vãos em {agentBox.result.plans?.length} planta(s).</p>}
                  {agentBox.result.kind === "detect" && <p className="text-[12px] mt-1">{agentBox.result.total_walls} paredes · {agentBox.result.total_openings} vãos detetados. <b>Calibração necessária</b> : abra a planta e introduza uma cota conhecida antes de qualquer medição.</p>}
                  {agentBox.result.kind === "compare" && (
                    <div className="text-[12px] mt-1 space-y-0.5">
                      <p>Antes: {agentBox.result.diff.before.room_count} divisão(ões) · {agentBox.result.diff.before.total_surface_m2} m² — Depois: {agentBox.result.diff.after.room_count} divisão(ões) · {agentBox.result.diff.after.total_surface_m2} m²</p>
                      <p>Diferença de área: {agentBox.result.diff.delta_surface_m2} m² ({agentBox.result.diff.delta_surface_pct}%)</p>
                      <p>+{agentBox.result.diff.added.length} adicionada(s) · −{agentBox.result.diff.removed.length} removida(s) · {agentBox.result.diff.modified.length} alterada(s)</p>
                    </div>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">Verifique o resultado. {(agentBox.agent === "report" || agentBox.agent === "devis") ? "Se houver um erro, corrija os pisos e volte a lançar — o agente memorizará a correção." : ""}</p>
                <div className="flex flex-wrap gap-2">
                  {agentBox.result.download && <Button onClick={agentDownload} className="rounded-sm gap-2" data-testid="agent-download"><FileDown className="h-4 w-4" /> Descarregar</Button>}
                  {agentBox.result.edit && <Button variant="outline" onClick={() => nav(agentBox.result.edit)} className="rounded-sm gap-2" data-testid="agent-open-quote"><ArrowRight className="h-4 w-4" /> Abrir orçamento</Button>}
                  {agentBox.result.kind === "detect" && agentBox.result.edit_plan_id && <Button onClick={() => openPlanById(agentBox.result.edit_plan_id)} className="rounded-sm gap-2" data-testid="agent-open-plan"><Ruler className="h-4 w-4" /> Abrir a planta para calibrar</Button>}
                  {agentBox.result.kind === "compare" && <Button variant="outline" onClick={() => { setAgentBox(null); nav(`/plan/compare?a=${agentBox.result.before_plan_id}&b=${agentBox.result.after_plan_id}`); }} className="rounded-sm gap-2" data-testid="agent-open-compare"><GitCompare className="h-4 w-4" /> Comparação detalhada</Button>}
                </div>
              </div>
            )}

            <DialogFooter>
              {agentBox?.step === "history" && (
                <Button variant="outline" onClick={() => setAgentBox((a) => ({ ...a, step: "pick" }))} className="rounded-sm">Voltar</Button>
              )}
              {agentBox?.step === "pick" && (
                <>
                  <Button variant="outline" onClick={() => setAgentBox(null)} className="rounded-sm">Cancelar</Button>
                  <Button onClick={agentPropose} disabled={agentBox.loading} className="rounded-sm gap-2" data-testid="agent-propose-btn"><Bot className="h-4 w-4" /> {agentBox.loading ? "Análise…" : agentBox.agent === "dpgf" ? "Abrir a oficina de mapas de quantidades" : "Propor um plano"}</Button>
                </>
              )}
              {agentBox?.step === "plan" && (
                <>
                  <Button variant="outline" onClick={() => setAgentBox((a) => ({ ...a, step: "pick" }))} className="rounded-sm">Voltar</Button>
                  <Button onClick={agentExecute} disabled={agentBox.loading} className="rounded-sm gap-2" data-testid="agent-execute-btn"><Wand2 className="h-4 w-4" /> {agentBox.loading ? "A executar…" : "Validar e executar"}</Button>
                </>
              )}
              {agentBox?.step === "result" && (
                (agentBox.agent === "report" || agentBox.agent === "devis") ? (
                  <>
                    <Button variant="outline" onClick={() => agentFeedback("error")} className="rounded-sm" data-testid="agent-feedback-error">Assinalar um erro / corrigir</Button>
                    <Button onClick={() => agentFeedback("ok")} className="rounded-sm gap-2" data-testid="agent-feedback-ok"><Sparkles className="h-4 w-4" /> Está perfeito</Button>
                  </>
                ) : (
                  <Button onClick={() => setAgentBox(null)} className="rounded-sm" data-testid="agent-close">Fechar</Button>
                )
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* S3.1 — Dialog partilhado para pré-visualização ampliada de plantas recentes */}
        {planZoomDialog}

      </div>
    );
  }

  return (
    <div className="plan-workspace mx-auto w-full min-w-0 max-w-[1600px] px-3 sm:px-5 py-6" data-testid="plan-workspace">
      <div className="mb-4">
        <PromptBar
          appKey="plantas"
          placeholder="Ex.: «Moradia T3 com 2 pisos, pé-direito 2,60 m, habitação»"
          examples="Descreva o edifício; carregamos as cotas e o uso previstos."
          onFill={({ params = {} }) => {
            const bits = [];
            if (params.tipo_edificio) bits.push(params.tipo_edificio);
            if (params.tipologia) bits.push(params.tipologia);
            if (params.pisos) bits.push(`${params.pisos} piso(s)`);
            if (params.pe_direito_m) bits.push(`pé-direito ${params.pe_direito_m} m`);
            if (bits.length) toast.success(`Dados aplicados: ${bits.join(" · ")}`);
          }}
        />
      </div>
      {chantierId && <div className="mb-4"><ChantierContextBar chantierId={chantierId} chantier={chantier} /></div>}
      <CadImportInfo info={plan?.cad_import} />
      {cadFile && <CadUnitPicker file={cadFile} onChoose={chooseCadUnit} onCancel={() => chooseCadUnit(null)} />}
      <Dialog open={customPosteOpen} onOpenChange={setCustomPosteOpen}>
        <DialogContent className="z-[80] max-w-lg" overlayClassName="z-[80]" data-testid="custom-postes-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Plus className="h-4 w-4" /> Artigos personalizados</DialogTitle>
            <DialogDescription>Crie os seus próprios artigos com o seu preço unitário (fornecimento + aplicação). Aparecem no catálogo de orçamentação.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid grid-cols-[1fr_84px_110px] gap-2 items-end">
              <div className="grid gap-1">
                <Label className="text-xs">Nome do artigo</Label>
                <Input value={cpForm.label} onChange={(e) => setCpForm((f) => ({ ...f, label: e.target.value }))}
                       placeholder="Ex.: Teto falso corta-fogo 1 h" maxLength={60}
                       data-testid="custom-poste-label" className="rounded-sm h-9 text-sm" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Un.</Label>
                <select value={cpForm.unit} onChange={(e) => setCpForm((f) => ({ ...f, unit: e.target.value }))}
                        data-testid="custom-poste-unit"
                        className="rounded-sm h-9 border border-border bg-background px-2 text-sm outline-none focus:border-primary">
                  <option value="m2">m²</option><option value="ml">ml</option><option value="u">u</option>
                </select>
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Preço s/ IVA /un. (€)</Label>
                <Input type="number" value={cpForm.pu} onChange={(e) => setCpForm((f) => ({ ...f, pu: e.target.value }))}
                       placeholder="55" data-testid="custom-poste-pu" className="rounded-sm h-9 text-sm" />
              </div>
            </div>
            <Button onClick={saveCustomPoste} data-testid="custom-poste-save" className="rounded-sm gap-2 justify-self-start">
              <Plus className="h-4 w-4" /> Adicionar ao catálogo
            </Button>
            <div className="border-t border-border pt-2">
              <p className="overline mb-2">Os meus artigos ({customPostes.length})</p>
              {customPostes.length === 0 && <p className="text-sm text-muted-foreground">Nenhum artigo personalizado por agora.</p>}
              <div className="grid gap-1 max-h-56 overflow-y-auto">
                {customPostes.map((c) => (
                  <div key={c.key} className="flex items-center justify-between gap-2 surface px-3 py-2 rounded-sm"
                       data-testid={`custom-poste-row-${c.key}`}>
                    <span className="text-sm truncate flex-1">{c.label}</span>
                    <span className="num text-xs text-primary shrink-0">{Number(c.pu).toFixed(2)} € / {c.unit === "m2" ? "m²" : c.unit}</span>
                    <button onClick={() => deleteCustomPoste(c.key)} title="Eliminar"
                            data-testid={`custom-poste-delete-${c.key}`}
                            className="text-muted-foreground hover:text-destructive shrink-0"><X className="h-4 w-4" /></button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={recentDialog} onOpenChange={setRecentDialog}>
        <DialogContent className="z-[80] max-w-3xl" overlayClassName="z-[80]" data-testid="recent-plans-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><History className="h-4 w-4" /> As minhas plantas recentes</DialogTitle>
            <DialogDescription>Abra uma planta ou um projeto multinível sem sair do editor. Assinale plantas para as eliminar em lote.</DialogDescription>
          </DialogHeader>
          <div className="flex items-center justify-end gap-2 flex-wrap pb-1">
            {selectedRecent.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => bulkTrashPlans(selectedRecent)}
                      data-testid="dialog-trash-selected-btn"
                      className="rounded-sm gap-1 h-8 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
                <Trash2 className="h-3.5 w-3.5" /> Eliminar a seleção ({selectedRecent.length})
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={trashAllPlans}
                    data-testid="dialog-trash-all-btn"
                    className="rounded-sm gap-1 h-8 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
              <Trash2 className="h-3.5 w-3.5" /> Eliminar tudo ({allPlans.length})
            </Button>
          </div>
          <div className="space-y-5 max-h-[60vh] overflow-y-auto pr-1">
            <div>
              <p className="overline mb-2">Plantas ({allPlans.length})</p>
              {allPlans.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma planta guardada.</p>}
              <div className="grid sm:grid-cols-2 gap-2">
                {allPlans.map((p) => (
                  <div key={p.plan_id} className="relative">
                    <input type="checkbox" checked={selectedRecent.includes(p.plan_id)}
                           onChange={() => setSelectedRecent((s) => s.includes(p.plan_id) ? s.filter((x) => x !== p.plan_id) : [...s, p.plan_id])}
                           data-testid={`dialog-plan-select-${p.plan_id}`}
                           className="absolute top-2 left-2 z-10 h-4 w-4 accent-destructive cursor-pointer" />
                    <button onClick={() => { openPlanById(p.plan_id); setRecentDialog(false); }}
                            data-testid={`recent-dialog-plan-${p.plan_id}`}
                            className={`text-left surface p-3 pl-8 w-full flex gap-3 items-start hover:border-primary transition-colors ${plan?.plan_id === p.plan_id ? "border-primary" : ""}`}>
                      <img src={`${String(api.defaults?.baseURL || "/api").replace(/\/$/, "")}/takeoffs/${p.plan_id}/thumb`} alt="" loading="lazy"
                           onError={(e) => { e.currentTarget.style.display = "none"; }}
                           className="w-14 h-14 object-cover rounded-sm bg-muted/40 border border-border shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="font-display font-bold text-sm truncate">{p.filename || "Plano sem nome"}</p>
                        <p className="text-[11px] text-muted-foreground mt-1">
                          {(p.page_count || 1)} page{(p.page_count || 1) > 1 ? "s" : ""} · {p.rooms_count || 0} divisão{(p.rooms_count || 0) > 1 ? "s" : ""}
                          {p.created_at && <span> · {new Date(p.created_at).toLocaleDateString("pt-PT")}</span>}
                          {plan?.plan_id === p.plan_id && <span className="text-primary"> · aberto</span>}
                        </p>
                      </div>
                    </button>
                  </div>
                ))}
              </div>
            </div>
            {planGroups.length > 0 && (
              <div>
                <p className="overline mb-2">Projetos multinível ({planGroups.length})</p>
                <div className="grid sm:grid-cols-2 gap-2">
                  {planGroups.map((g) => (
                    <button key={g.group_id} onClick={() => { setRecentDialog(false); setPlan(null); openGroupConsolidated(g); }}
                            data-testid={`recent-dialog-group-${g.group_id}`}
                            className="text-left surface p-3 hover:border-primary transition-colors">
                      <p className="font-display font-bold text-sm truncate">📁 {g.name}</p>
                      <p className="text-[11px] text-muted-foreground mt-1">{(g.levels || []).length} niveau{(g.levels || []).length > 1 ? "x" : ""}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
      <PlanWorkflowHeader filename={plan.filename} pageIndex={pageIndex} pageCount={plan.page_count || 1}
        calibration={currentCalib} busy={analysisBusy || aiBusy} mode={analysisMode} onModeChange={setAnalysisMode}
        planKind={planKindChoice} onPlanKindChange={setPlanKindChoice} progress={analysisProgress} hasRecap={!!analysisRecap}
        onAnalyze={analysisMode === "reading" ? runAI : analysisMode === "structure_all" ? analyzeAllPages : analyzePlanFull}
        onCalibrate={() => { setTool(TOOLS.CALIB); setPoints([]); document.querySelector('[data-testid="plan-canvas-surface"]')?.scrollIntoView({ block: "start" }); }}
        onReview={() => { setRightTab("ai"); document.getElementById("plan-results-panel")?.scrollIntoView({ block: "start" }); }}
        onEstimate={() => { setEstimateDialog(true); setEstimateResult(null); }}
        documentActions={[
          { id: "open-recent-plans-btn", label: "As minhas plantas recentes", run: () => { loadAllPlans(); loadPlanGroups(); setRecentDialog(true); } },
          { id: "plan-back-btn", label: "Importar outra planta", run: () => setPlan(null) },
          { id: "plan-duplicate-btn", label: "Duplicar esta planta", run: duplicatePlan },
          { id: "metre-versions-btn", label: "Versões da medição", run: openMetreVersions },
          { id: "document-danger", separator: true },
          { id: "plan-clear-all-btn", label: "Apagar as medições desta página…", run: clearAllMeasures, danger: true },
        ]}
        exportActions={[
          { id: "plan-pdf-export-btn", label: "Medições PDF", run: downloadPdf },
          { id: "plan-metre-noprice-btn", label: "Medição sem preços", run: downloadPlanMetre },
          { id: "plan-xlsx-export-btn", label: "Folha de cálculo Excel", run: downloadXlsx },
          { id: "plan-quote-pdf-btn", label: "Orçamento PDF", run: () => { setQuoteDialog(true); loadTemplates(); loadQuoteSends(); loadVideoHistory(); } },
          { id: "plan-multi-quote-btn", label: "Consolidar várias plantas", run: () => { setMultiDialog(true); loadAllPlans(); } },
        ]}
        studyActions={[
          { id: "plan-estimate-btn", label: "Estimativa", run: () => { setEstimateDialog(true); setEstimateResult(null); } },
          { id: "plan-review-btn", label: "Controlo das cotas desta página", run: () => { setRightTab("ai"); document.getElementById("plan-results-panel")?.scrollIntoView({ block: "start" }); } },
          { id: "plan-pc-study-btn", label: "Estudo do projeto de licenciamento", run: () => setPcDialog(true) },
          (plan.structural_metre || plan.kind === "dxf") && { id: "plan-structural-btn", label: "Medição a partir das camadas CAD", run: () => setStructDialog(true) },
          { id: "plan-render-3d-btn", label: "Visualização 3D", run: () => { setRender3dDialog(true); setRender3dImg(null); setVideoUrl(null); setCreditPaywall(null); loadRender3dHistory(); loadVideoHistory(); loadCredits3d(); } },
          { id: "plan-tools-separator", separator: true },
          { id: "plan-pro-tools", label: "Plantas BIM / Autodesk", run: () => nav("/plans-pro") },
          { id: "plan-bet-reader", label: "Leitura especializada de engenharia", run: () => nav("/structuro/lecture-plan") },
        ]}>
          <Select value={plan?.plan_id || ""} onValueChange={(v) => {
                    if (!v) return;
                    if (v.startsWith("group:")) { const g = planGroups.find((x) => x.group_id === v.slice(6)); if (g) { setPlan(null); openGroupConsolidated(g); } }
                    else openPlanById(v);
                  }}>
            <SelectTrigger disabled={analysisBusy || aiBusy} aria-label="Mudar de planta" className="h-9 w-[210px] rounded-sm" data-testid="plan-switcher-trigger"
                           title="Mudar para outra planta sem sair do editor">
              <SelectValue placeholder="Mudar de planta" />
            </SelectTrigger>
            <SelectContent data-testid="plan-switcher-content" className="z-[80] max-h-80">
              {allPlans.map((p) => (
                <SelectItem key={p.plan_id} value={p.plan_id} data-testid={`plan-switcher-item-${p.plan_id}`}>
                  {(p.filename || "Plano sem nome")}{(p.page_count || 1) > 1 ? ` · ${p.page_count}p` : ""}
                </SelectItem>
              ))}
              {planGroups.map((g) => (
                <SelectItem key={g.group_id} value={`group:${g.group_id}`} data-testid={`plan-switcher-group-${g.group_id}`}>
                  📁 {g.name} ({(g.levels || []).length} pisos)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
      </PlanWorkflowHeader>
      {!!plan.pages?.[pageIndex]?.reading_warnings?.length && (
        <div className="mx-3 my-3 rounded-xl border border-amber-300/60 bg-amber-50/80 p-4 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-100" role="status" data-testid="plan-reading-warnings">
          <p className="font-semibold mb-2">Leitura a verificar antes da medição</p>
          <ul className="list-disc pl-5 space-y-1">
            {plan.pages[pageIndex].reading_warnings.map((warning, index) => <li key={index}>{warning}</li>)}
          </ul>
        </div>
      )}
          <PcStudyDialog open={pcDialog} onClose={() => setPcDialog(false)}
                         study={plan?.pc_study || null} busy={pcBusy}
                         onRun={runPcStudy} onDownload={downloadPcFile} onRefresh={refreshPlan}
                         onDownloadXlsx={downloadXlsx}
                         planId={plan?.plan_id} onSent={refreshPlan}
                         onCompareSuppliers={comparePcSuppliers}
                         sentReports={(plan?.sent_reports || []).filter((s) => s.kind === "pc_study")}
                         ordersReports={(plan?.sent_reports || []).filter((s) => s.kind === "purchase_order")}
                         onRecompute={recomputePcStudy} />
          <StructuralTakeoffDialog open={structDialog} onClose={() => setStructDialog(false)}
                                   planId={plan?.plan_id} />
      <details className="plan-advanced-tools">
        <summary>Artigos, personalização e mensagens</summary>
        <div className="plan-advanced-content">
          <BrandingDialog />
          <MailboxDialog />
          <OuvrageComposeDialog onAdd={addOuvrageFromPlan} planVariables={planVariables} />
          <Button variant="outline" onClick={() => { setCustomPosteOpen(true); loadCustomPostes(); }}
                  data-testid="open-custom-postes-btn" className="rounded-sm gap-2">
            <Plus className="h-4 w-4" /> Artigos personalizados
          </Button>
          {pendingOuvrages > 0 && (
            <Button variant="outline" onClick={() => nav("/devis-editeur")}
                    className="rounded-sm gap-2 border-primary text-primary" data-testid="plan-create-quote-ouvrages">
              <ArrowRight className="h-4 w-4" /> Criar um orçamento ({pendingOuvrages})
            </Button>
          )}
        </div>
      </details>
      {analysisRecap && <PlanAnalysisResults recap={analysisRecap} onClose={() => setAnalysisRecap(null)}
        onReview={() => { setRightTab("ai"); document.getElementById("plan-results-panel")?.scrollIntoView({ block: "start" }); }}
        onQuote={sendToQuote} />}

      <div className="surface p-3 flex items-center gap-4 flex-wrap" data-testid="plan-settings-bar">
        <div className="flex items-center gap-2">
          <span className="text-xs overline">Definições da planta</span>
          <button
            onClick={() => setSettingsOpen((v) => !v)}
            className="text-primary text-xs hover:underline"
            data-testid="toggle-plan-settings"
          >
            {settingsOpen ? "Ocultar" : "Editar"}
          </button>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Altura paredes</span>
          <b className="num text-primary">{planDefaults.ceiling_h_m} m</b>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Espessura pavimento</span>
          <b className="num text-primary">{(planDefaults.floor_thickness_m * 100).toFixed(0)} cm</b>
        </div>
        <Button size="sm" variant="outline" onClick={applyWallHeightToPage} data-testid="apply-wall-height-page-btn"
                title="Aplicar a altura de parede acima a todas as cotas lineares da página (recalcula os m²)"
                className="rounded-sm h-7 gap-1 text-xs border-primary/50 text-primary hover:bg-primary hover:text-white">
          <Ruler className="h-3.5 w-3.5" /> Aplicar a altura a todas as cotas
        </Button>
        {settingsOpen && (
          <div className="flex items-center gap-3 flex-1 justify-end flex-wrap">
            <label className="flex items-center gap-2 text-xs">
              <span>Altura das paredes (m):</span>
              <Input
                type="number" step="0.05" min="1.5" max="6"
                value={planDefaults.ceiling_h_m}
                onChange={(e) => setPlanDefaults((d) => ({ ...d, ceiling_h_m: parseFloat(e.target.value) || 2.5 }))}
                className="h-8 w-20 text-xs num"
                data-testid="settings-ceiling-h"
              />
            </label>
            <label className="flex items-center gap-2 text-xs">
              <span>Espessura pavimento (cm):</span>
              <Input
                type="number" step="1" min="2" max="100"
                value={Math.round(planDefaults.floor_thickness_m * 100)}
                onChange={(e) => setPlanDefaults((d) => ({ ...d, floor_thickness_m: (parseFloat(e.target.value) || 15) / 100 }))}
                className="h-8 w-20 text-xs num"
                data-testid="settings-floor-thickness"
              />
            </label>
            <Button
              size="sm"
              onClick={() => savePlanDefaults(planDefaults)}
              className="rounded-sm h-8"
              data-testid="settings-save-btn"
            >
              Guardar
            </Button>
          </div>
        )}
        <p className="text-[10px] text-muted-foreground w-full">
          Estes valores aplicam-se às novas divisões criadas ou importadas via IA (podem ser ajustados por divisão).
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[180px_minmax(0,1fr)_320px] gap-4 min-w-0">
        {/* SIDEBAR PAGES */}
        <div className="surface p-3 max-h-[80vh] overflow-auto min-w-0 xl:col-span-2 2xl:col-span-1">
          <p className="overline mb-3">Páginas ({plan.page_count})</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-6 2xl:grid-cols-1 gap-2">
            {plan.pages.map((pg, i) => (
              <div key={i}>
                <button
                  data-testid={`plan-page-${i}`}
                  disabled={analysisBusy || aiBusy}
                  onClick={() => setPageIndex(i)}
                  className={`w-full border rounded-sm p-2 text-xs text-left transition-colors ${i === pageIndex ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-bold">Página {i + 1}</p>
                    {pg.level_label && (
                      <Badge variant="outline" className="text-[10px] rounded-sm num h-5">
                        {pg.level_label}
                      </Badge>
                    )}
                  </div>
                  <p className="text-muted-foreground num">{pg.width_px}×{pg.height_px}</p>
                  {plan.calibrations?.[String(i)] && (
                    <Badge variant="outline" className="mt-1 text-[10px] rounded-sm">Calibrada</Badge>
                  )}
                </button>
                <Select
                  value={pg.level_index != null ? String(pg.level_index) : "none"}
                  onValueChange={async (v) => {
                    const payload = v === "none"
                      ? { level_index: null, level_label: null }
                      : v === "99" ? { level_index: 99, level_label: "Sótão" }
                      : v === "-1" ? { level_index: -1, level_label: "Cave" }
                      : v === "0" ? { level_index: 0, level_label: "R/C" }
                      : { level_index: Number(v), level_label: `R+${v}` };
                    await api.patch(`/takeoffs/${plan.plan_id}/pages/${i}/level`, payload);
                    await refreshPlan();
                    toast.success("Nível atualizado");
                  }}
                >
                  <SelectTrigger className="rounded-sm h-6 text-[10px] mt-1" data-testid={`page-level-select-${i}`}>
                    <SelectValue placeholder="Nível…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Sem nível</SelectItem>
                    <SelectItem value="-1">Cave</SelectItem>
                    <SelectItem value="0">R/C</SelectItem>
                    <SelectItem value="1">R+1</SelectItem>
                    <SelectItem value="2">R+2</SelectItem>
                    <SelectItem value="3">R+3</SelectItem>
                    <SelectItem value="99">Sótão</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        </div>

        {/* MAIN CANVAS */}
        <div className={fullscreen
          ? "fixed inset-0 z-[60] p-3 bg-background overflow-auto"
          : "surface p-3 min-w-0"} data-testid="plan-canvas-surface">
          {/* TOOLBAR */}
          <div className="flex flex-wrap gap-2 mb-3 pb-3 border-b border-border">
            <MeasureHelpDialog />
            <ToolButton icon={MousePointer2} label="Seleção" testId="tool-select" active={tool === TOOLS.SELECT} onClick={() => { setDeductDraw(null); setTool(TOOLS.SELECT); setPoints([]); }} />
            <ToolButton icon={Ruler} label="Calibrar" testId="tool-calibrate" active={tool === TOOLS.CALIB} onClick={() => { setDeductDraw(null); setTool(TOOLS.CALIB); setPoints([]); }} />
            <ToolButton icon={Move} label="Distância" testId="tool-distance" active={tool === TOOLS.DIST} onClick={() => { setDeductDraw(null); setTool(TOOLS.DIST); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Layers} label="Perímetro" testId="tool-polyline" active={tool === TOOLS.POLY} onClick={() => { setDeductDraw(null); setTool(TOOLS.POLY); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Hexagon} label="Superfície" testId="tool-surface" active={tool === TOOLS.SURFACE} onClick={() => { setDeductDraw(null); setTool(TOOLS.SURFACE); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Square} label="Divisão" testId="tool-room" active={tool === TOOLS.ROOM} onClick={() => { setDeductDraw(null); setTool(TOOLS.ROOM); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Wand2} label="Auto-divisão" testId="tool-autoroom" active={tool === TOOLS.AUTOROOM} onClick={() => { setDeductDraw(null); setTool(TOOLS.AUTOROOM); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={DoorOpen} label="Vão" testId="tool-opening" active={tool === TOOLS.OPENING} onClick={() => { setTool(TOOLS.OPENING); setPoints([]); }} disabled={!currentCalib || rooms.length === 0} />
            {/* Iter 57 — QuoterPlan-like tools */}
            <ToolButton icon={Hash} label="Contador" testId="tool-counter" active={tool === TOOLS.COUNTER} onClick={() => { setTool(TOOLS.COUNTER); setPoints([]); }} />
            <ToolButton icon={StickyNote} label="Nota" testId="tool-note" active={tool === TOOLS.NOTE} onClick={() => { setTool(TOOLS.NOTE); setPoints([]); }} />
            <ToolButton icon={Triangle} label="Ângulo" testId="tool-angle" active={tool === TOOLS.ANGLE} onClick={() => { setTool(TOOLS.ANGLE); setPoints([]); }} />
            <ToolButton icon={MountainSnow} label="Inclinação da cobertura" testId="tool-pitch" active={tool === TOOLS.PITCH} onClick={() => { setTool(TOOLS.PITCH); setPoints([]); }} disabled={!currentCalib} />
            <div className="flex-1" />
            {rooms.some((r) => r.page_index === pageIndex && r.surface_delta_pct != null) && (
              <Button size="sm" variant={showDeltas ? "default" : "outline"}
                      onClick={() => setShowDeltas(!showDeltas)}
                      data-testid="toggle-deltas-overlay"
                      className="rounded-sm gap-1 h-8">
                <Square className="h-3 w-3" /> Desvios
              </Button>
            )}
            {detectedWalls && (
              <>
                <Button size="sm" variant={showWalls ? "default" : "outline"} onClick={() => setShowWalls(!showWalls)}
                        data-testid="toggle-walls-overlay"
                        className="rounded-sm gap-1 h-8">
                  <Layers className="h-3 w-3" /> Paredes ({detectedWalls.segment_count})
                </Button>
                <Button size="sm" variant={reclassifyMode ? "default" : "outline"}
                        onClick={() => setReclassifyMode(v => !v)}
                        data-testid="toggle-reclassify-mode"
                        className={`rounded-sm gap-1 h-8 ${reclassifyMode ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
                  {reclassifyMode ? "Reclassificar (ativo)" : "Reclassificar"}
                </Button>
              </>
            )}
            <Button size="sm" variant="ghost" onClick={() => setPoints(points.slice(0, -1))} disabled={!points.length} className="rounded-sm gap-1" title="Cancelar o último ponto colocado">
              <Undo2 className="h-3 w-3" /> Cancelar o último ponto
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setZoom(z => Math.max(0.15, z / 1.2))} className="rounded-sm">
              <ZoomOut className="h-3 w-3" />
            </Button>
            <Badge variant="outline" className="rounded-sm num">{Math.round(zoom * 100)}%</Badge>
            <Button size="sm" variant="ghost" onClick={() => setZoom(z => Math.min(6, z * 1.2))} className="rounded-sm">
              <ZoomIn className="h-3 w-3" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setRotation((r) => (r + 90) % 360)} className="rounded-sm" data-testid="tool-rotate">
              <RotateCw className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant={locked ? "default" : "outline"}
              onClick={() => {
                setLocked(l => !l);
                toast.info(locked ? "Planta desbloqueada — zoom e deslocação ativos"
                                  : "Planta bloqueada — escala calibrada");
              }}
              data-testid="tool-lock"
              className={`rounded-sm gap-1 h-8 ${locked ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title={locked ? "Desbloquear (permitir zoom + deslocação)"
                            : "Bloquear a planta (bloquear zoom + deslocação para cliques precisos)"}
            >
              {locked ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
              {locked ? "Bloqueado" : "Bloquear"}
            </Button>
            <Button
              size="sm"
              variant={objectPanelOpen ? "default" : "outline"}
              onClick={() => { setPanelFocus(null); setObjectPanelOpen((o) => !o); }}
              data-testid="tool-objects-panel"
              className={`rounded-sm gap-1 h-8 ${objectPanelOpen ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title="Abrir o Painel Objetos (edição & salto para)"
            >
              <Layers className="h-3 w-3" />
              Objetos
            </Button>
            {/* P1 — Statut d'enregistrement automatique + enregistrement manuel */}
            <span data-testid="autosave-status"
                  className={`inline-flex items-center gap-1 text-xs px-2 h-8 rounded-sm ${saving ? "text-amber-500" : "text-emerald-600"}`}
                  title="As suas medições e modificações são guardadas automaticamente">
              <span className={`h-1.5 w-1.5 rounded-full ${saving ? "bg-amber-500 animate-pulse" : "bg-emerald-500"}`} />
              {saving ? "A guardar…" : annotationSaveError ? "Falha ao guardar" : savedAt ? "Anotações guardadas ✓" : "Gravação das anotações ativa"}
            </span>
            <Button size="sm" variant="outline" onClick={manualSave} disabled={saving}
                    data-testid="plan-save-btn" className="rounded-sm gap-1 h-8"
                    title="Forçar o registo agora">
              <Save className="h-3 w-3" /> Guardar
            </Button>
            {/* P1 — Réglage contraste/luminosité du plan */}
            <div className="relative">
              <Button
                size="sm"
                variant={showImgAdjust ? "default" : "outline"}
                onClick={() => setShowImgAdjust((v) => !v)}
                data-testid="tool-img-adjust"
                className={`rounded-sm gap-1 h-8 ${showImgAdjust ? "bg-primary text-white hover:bg-orange-600" : ""}`}
                title="Ajustar o contraste e o brilho da planta"
              >
                <Contrast className="h-3 w-3" /> Contraste
              </Button>
              {showImgAdjust && (
                <div className="absolute right-0 top-9 z-[70] w-64 border border-border bg-background/98 backdrop-blur rounded-md p-3 shadow-xl grid gap-3"
                     data-testid="img-adjust-panel">
                  <div className="grid gap-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-1 text-muted-foreground"><Contrast className="h-3 w-3" /> Contraste</span>
                      <b className="num">{Math.round(planContrast * 100)}%</b>
                    </div>
                    <input type="range" min="0.6" max="2.5" step="0.05" value={planContrast}
                           onChange={(e) => setPlanContrast(parseFloat(e.target.value))}
                           data-testid="img-contrast-slider" className="w-full accent-primary" />
                  </div>
                  <div className="grid gap-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-1 text-muted-foreground"><SunMedium className="h-3 w-3" /> Luminosidade</span>
                      <b className="num">{Math.round(planBrightness * 100)}%</b>
                    </div>
                    <input type="range" min="0.6" max="1.8" step="0.05" value={planBrightness}
                           onChange={(e) => setPlanBrightness(parseFloat(e.target.value))}
                           data-testid="img-brightness-slider" className="w-full accent-primary" />
                  </div>
                  <Button size="sm" variant="ghost" className="rounded-sm h-7 text-xs"
                          onClick={() => { setPlanContrast(1); setPlanBrightness(1); }}
                          data-testid="img-adjust-reset">
                    Reiniciar
                  </Button>
                </div>
              )}
            </div>
            {/* P1 — Plein écran */}
            <Button
              size="sm"
              variant={fullscreen ? "default" : "outline"}
              onClick={() => setFullscreen((v) => !v)}
              data-testid="tool-fullscreen"
              className={`rounded-sm gap-1 h-8 ${fullscreen ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title={fullscreen ? "Sair do ecrã inteiro (Esc)" : "Mostrar a planta em ecrã completo"}
            >
              {fullscreen ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
              {fullscreen ? "Sair" : "Ecrã completo"}
            </Button>
            {/* P3 — Assistant IA d'édition du plan */}
            <Button
              size="sm"
              variant={aiCmdOpen ? "default" : "outline"}
              onClick={() => setAiCmdOpen((v) => !v)}
              data-testid="tool-ai-assistant"
              className={`rounded-sm gap-1 h-8 ${aiCmdOpen ? "bg-primary text-white hover:bg-orange-600" : "border-primary/60 text-primary"}`}
              title="Assistente IA: modifique a planta em linguagem natural"
            >
              <Bot className="h-3 w-3" /> Assistente IA
            </Button>
          </div>

          {/* CANVAS */}
          <div className={fullscreen ? "relative h-[calc(100vh-92px)]" : "relative"}>
          {(pageLoading || loadedPageKey !== pageKey || pageError) && (
            <div role={pageError ? "alert" : "status"} className="min-h-[300px] grid place-content-center gap-3 text-center p-6">
              <p>{pageError || "A carregar a planta…"}</p>
              {pageError && <Button onClick={() => setPageRetry((n) => n + 1)}>Tentar novamente</Button>}
            </div>
          )}
          {annotationSaveError && <p role="alert" className="p-3 text-destructive">
            Anotações não guardadas. Clique em «Guardar» para tentar novamente.
          </p>}
          {loadedPageKey === pageKey && !pageError && <PlanCanvas
            key={pageKey}
            pageData={pageData} tool={tool} points={points} rooms={rooms}
            calibration={currentCalib} zoom={zoom} offset={offset} rotation={rotation}
            onCanvasClick={onCanvasClick} onZoomChange={setZoom} onOffsetChange={setOffset}
            onAutoRotate={() => {
              if (!autoRotated) {
                setRotation(90);
                setAutoRotated(true);
                toast.success("Planta rodada em paisagem para facilitar as medições");
              }
            }}
            detectedWalls={detectedWalls} showWalls={showWalls}
            pixelsPerMeter={currentCalib?.pixels_per_meter || 0}
            orthoSnap={true}
            locked={locked}
            dimensionLines={aiDimLines}
            showDimensionLines={showDimensionLines}
            annotations={annotations}
            activeCounterId={activeCounterId}
            focusRequest={focusRequest}
            selectedCoteIndex={selectedCote}
            onCoteClick={setSelectedCote}
            checkedCotes={checkedCotes}
            selectedCheckedIndex={selectedCheckedCote}
            onCheckedCoteClick={setSelectedCheckedCote}
            onCanvasDoubleClick={onCanvasDoubleClick}
            showDeltas={showDeltas}
            contrast={planContrast}
            brightness={planBrightness}
            measurements={pageMeasurements}
            highlightIds={highlightMeasures}
            cumulSegments={cumulSegments}
            cumulColor={cumulColor}
            structure={structure}
            showStructure={showStructure}
            selectedStruct={selectedStruct}
            onStructSelect={setSelectedStruct}
            onStructDrag={dragStructPoint}
            onStructDragEnd={commitStructure}
          />}

          {/* P3 — Panneau Assistant IA (barre de commande + aperçu/appliquer) */}
          {aiCmdOpen && (
            <div className="absolute bottom-3 left-3 z-30 w-[340px] max-w-[calc(100%-24px)] border border-primary/50 bg-background/97 backdrop-blur rounded-md p-3 shadow-xl grid gap-2"
                 data-testid="ai-assistant-panel">
              <div className="flex items-center justify-between">
                <p className="overline text-primary flex items-center gap-1"><Bot className="h-3.5 w-3.5" /> Assistente IA da planta</p>
                <div className="flex items-center gap-2">
                  {aiTurns.length > 0 && (
                    <button onClick={() => { setAiTurns([]); setAiJustCreated(null); toast.message("Nova conversa"); }}
                            className="text-[10px] text-muted-foreground hover:text-foreground inline-flex items-center gap-0.5"
                            title={`Memória da conversa: ${aiTurns.length} troca(s). Reinicializar.`}
                            data-testid="ai-reset-conversation">
                      <History className="h-3 w-3" /> Nova conversa ({aiTurns.length})
                    </button>
                  )}
                  <button onClick={() => { setAiCmdOpen(false); setAiCmdProposal(null); }}
                          className="text-muted-foreground hover:text-foreground" data-testid="ai-assistant-close">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <p className="text-xs text-muted-foreground leading-snug">
                Ex.: «adiciona um teto inclinado a 26% de 15 m² de pavimento», «adiciona uma área de 20 m² de mosaico», «duplica a medição X», «orçamenta a página toda», «põe as paredes exteriores a 2,70 m», «qual é o preço indicativo do pladur 13 mm?» (pesquisa web com fontes).
              </p>
              <div className="flex gap-2">
                <Input
                  value={aiCmd}
                  onChange={(e) => setAiCmd(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !aiCmdBusy) aiProposeCommand(); }}
                  placeholder="A sua encomenda…"
                  className="rounded-sm h-9 text-sm"
                  data-testid="ai-command-input"
                />
                <Button size="sm" variant="outline" onClick={aiVoiceDictate} disabled={aiCmdBusy}
                        title="Ditar o comando (microfone)" data-testid="ai-command-mic"
                        className={`rounded-sm h-9 w-9 p-0 shrink-0 ${aiListening ? "bg-red-500 text-white border-red-500 animate-pulse" : ""}`}>
                  <Mic className="h-4 w-4" />
                </Button>
                <Button size="sm" onClick={aiProposeCommand} disabled={aiCmdBusy || !aiCmd.trim()}
                        className="rounded-sm gap-1 h-9" data-testid="ai-command-propose">
                  {aiCmdBusy && !aiCmdProposal ? <Sparkles className="h-3.5 w-3.5 animate-pulse" /> : <Sparkles className="h-3.5 w-3.5" />}
                  Propor
                </Button>
              </div>
              {aiCmdProposal && aiCmdProposal.action === "answer" && (
                <div className="border border-border rounded-sm p-2.5 grid gap-2 bg-secondary/40" data-testid="ai-command-answer">
                  <p className="text-xs whitespace-pre-wrap leading-snug">{aiCmdProposal.answer}</p>
                  {Array.isArray(aiCmdProposal.sources) && aiCmdProposal.sources.length > 0 && (
                    <div className="border-t border-border pt-1.5 grid gap-0.5">
                      <p className="overline text-[10px]">Fontes</p>
                      {aiCmdProposal.sources.map((s, i) => (
                        <a key={i} href={s.url} target="_blank" rel="noreferrer"
                           className="text-[11px] text-primary hover:underline truncate"
                           data-testid={`ai-answer-source-${i}`}>
                          {s.title || s.url}
                        </a>
                      ))}
                    </div>
                  )}
                  {aiCmdProposal.price_suggestion && aiCmdProposal.price_suggestion.amount > 0 && (
                    <div className="border-t border-border pt-1.5 flex items-center justify-between gap-2">
                      <span className="text-[11px] text-muted-foreground">
                        Preço detetado: <b className="text-foreground">{aiCmdProposal.price_suggestion.amount.toLocaleString("pt-PT", { minimumFractionDigits: 2 })} €/{aiCmdProposal.price_suggestion.unit === "m2" ? "m²" : aiCmdProposal.price_suggestion.unit}</b>
                      </span>
                      <Button size="sm" onClick={() => aiInjectPrice(aiCmdProposal.price_suggestion)}
                              disabled={aiCmdBusy}
                              className="rounded-sm h-7 text-xs gap-1" data-testid="ai-answer-inject-price">
                        <Plus className="h-3 w-3" /> Criar um artigo personalizado
                      </Button>
                    </div>
                  )}
                  <div className="flex justify-end">
                    <Button size="sm" variant="ghost" onClick={() => { setAiCmdProposal(null); setAiCmd(""); }}
                            className="rounded-sm h-7 text-xs" data-testid="ai-answer-close">
                      Fechar
                    </Button>
                  </div>
                </div>
              )}
              {aiCmdProposal && aiCmdProposal.action !== "answer" && (
                <div className="border border-border rounded-sm p-2.5 grid gap-2 bg-secondary/40" data-testid="ai-command-proposal">
                  <p className="text-xs"><b className="text-primary">Pré-visualização: </b>{aiCmdProposal.summary}</p>
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="ghost" onClick={() => setAiCmdProposal(null)}
                            className="rounded-sm h-7 text-xs" data-testid="ai-command-cancel">
                      Cancelar
                    </Button>
                    <Button size="sm" onClick={aiApplyCommand} disabled={aiCmdBusy}
                            className="rounded-sm h-7 text-xs gap-1" data-testid="ai-command-apply">
                      <Save className="h-3 w-3" /> Aplicar
                    </Button>
                  </div>
                </div>
              )}
              {aiJustCreated && (
                <div className="border border-primary/40 rounded-sm p-2.5 flex items-center justify-between gap-2 bg-primary/5" data-testid="ai-chiffrer-created">
                  <span className="text-[11px] text-muted-foreground truncate">
                    « {aiJustCreated.label} » criada{aiJustCreated.value ? ` (${aiJustCreated.value})` : ""} — orçamentá-la?
                  </span>
                  <div className="flex gap-1 shrink-0">
                    <Button size="sm" variant="ghost" onClick={() => setAiJustCreated(null)}
                            className="rounded-sm h-7 text-xs" data-testid="ai-chiffrer-created-skip">Mais tarde</Button>
                    <Button size="sm" onClick={() => {
                              const m = (plan?.measurements || []).find((x) => x.measurement_id === aiJustCreated.measurement_id);
                              if (m) openChiffrage(m); else toast.error("Cota não encontrada");
                              setAiJustCreated(null);
                            }} disabled={aiCmdBusy}
                            className="rounded-sm h-7 text-xs gap-1" data-testid="ai-chiffrer-created-go">
                      € Orçamentar
                    </Button>
                  </div>
                </div>
              )}
              {aiHistory.length > 0 && (
                <div className="border-t border-border pt-2 mt-1" data-testid="ai-command-history">
                  <p className="overline text-[10px] mb-1 flex items-center gap-1"><History className="h-3 w-3" /> Comandos aplicados</p>
                  <div className="grid gap-1 max-h-32 overflow-y-auto">
                    {aiHistory.map((h) => (
                      <div key={h.id} className="flex items-center justify-between gap-2 text-[11px] bg-muted/40 rounded-sm px-2 py-1"
                           data-testid={`ai-history-item-${h.id}`}>
                        <span className="truncate flex-1 text-muted-foreground">{h.summary}</span>
                        {h.inverse ? (
                          <button onClick={() => aiUndo(h)} disabled={aiCmdBusy}
                                  className="text-primary hover:underline shrink-0 inline-flex items-center gap-0.5"
                                  data-testid={`ai-history-undo-${h.id}`}>
                            <Undo2 className="h-3 w-3" /> Cancelar
                          </button>
                        ) : (
                          <span className="text-[10px] text-muted-foreground/60 shrink-0">não anulável</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          {/* Iter63 — panneau détail de la cote IA sélectionnée */}
          {coteDetail && (
            <div className="absolute top-3 right-3 z-20 w-64 border border-fuchsia-500/50 bg-background/95 backdrop-blur rounded-sm p-3 grid gap-1.5 shadow-lg"
                 data-testid="cote-detail-panel">
              <div className="flex items-center justify-between">
                <p className="overline text-fuchsia-500">Cota IA #{selectedCote + 1}</p>
                <button onClick={() => setSelectedCote(null)}
                        className="text-muted-foreground hover:text-foreground"
                        data-testid="cote-detail-close">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Valor escrito</span>
                <b className="num" data-testid="cote-written-value">
                  {coteDetail.value_m != null ? `${Number(coteDetail.value_m).toFixed(2)} m` : "—"}
                </b>
              </div>
              {coteDetail.measured != null ? (
                <>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Medida (escala atual)</span>
                    <b className="num" data-testid="cote-measured-value">
                      {coteDetail.measured.toFixed(2)} m
                    </b>
                  </div>
                  {coteDetail.deltaPct != null && (
                    <div className={`flex justify-between text-xs ${Math.abs(coteDetail.deltaPct) > 3 ? "text-amber-500" : "text-green-600"}`}
                         data-testid="cote-delta">
                      <span>Desvio</span>
                      <b className="num">
                        {coteDetail.deltaPct > 0 ? "+" : ""}{coteDetail.deltaPct.toFixed(1)}%
                        {Math.abs(coteDetail.deltaPct) > 3 ? " ⚠" : " ✓"}
                      </b>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">
                  Calibre a página para comparar a medida ao valor escrito.
                </p>
              )}
              {coteDetail.location && (
                <p className="text-[10px] text-muted-foreground">{coteDetail.location}</p>
              )}
              <div className="flex gap-1 flex-wrap">
                {coteDetail.orientation && (
                  <Badge variant="outline" className="rounded-sm text-[10px]">{coteDetail.orientation}</Badge>
                )}
                {coteDetail.confidence != null && (
                  <Badge variant="outline" className="rounded-sm text-[10px] num">
                    conf. {Math.round(Number(coteDetail.confidence) * 100)}%
                  </Badge>
                )}
              </div>
            </div>
          )}
          </div>

          <ObjectPanel
            open={objectPanelOpen}
            focusTab={panelFocus}
            onClose={() => setObjectPanelOpen(false)}
            rooms={rooms}
            measurements={pageMeasurements}
            annotations={annotations}
            onFocusObject={focusOnObject}
            onRenameRoom={renameRoom}
            onDeleteRoom={deleteRoomFromPanel}
            onEstimateRoom={generateRoomEstimate}
            onAttachPreset={attachPresetToRoom}
            onDeleteMeasure={deleteMeasureFromPanel}
            onClearMeasures={clearMeasures}
            onRenameMeasure={renameMeasure}
            onColorMeasure={colorMeasure}
            onExportCotesPdf={downloadCotesPdf}
            onConvertMeasure={convertMeasureToRoom}
            onDeductMeasure={deductMeasure}
            onDeductOpening={(m) => { setDeductWidth(""); setDeductCount(1); setDeductDialog({ measurement_id: m.measurement_id, label: m.label || "Parede" }); }}
            onReportToDevis={reportMeasureToDevis}
            onMergeMeasures={mergeMeasures}
            onReportAllWallAreas={reportAllWallAreasToDevis}
            onChiffrer={openChiffrage}
            onSetWallHeight={(id, h) => setWallHeightApi(id, h)}
            onSetMeasureSurface={setMeasureSurfaceApi}
            onSetMeasureLength={setMeasureLengthApi}
            onChiffrerPage={chiffrerPage}
            onOpenPriceLib={() => setPriceLibOpen(true)}
            onOpenRoomPreset={() => openRoomPreset(null)}
            onDeleteCounter={(id) => deleteAnnotationLocal("counters", id)}
            onRenameCounter={(id, name) => updateAnnotationLocal("counters", id, { label: name })}
            onDeleteNote={(id) => deleteAnnotationLocal("notes", id)}
            onEditNote={(id, text) => updateAnnotationLocal("notes", id, { text })}
            onDeleteAngle={(id) => deleteAnnotationLocal("angles", id)}
            onDeletePitched={(id) => deleteAnnotationLocal("pitched_surfaces", id)}
          />

          {/* Déduction d'ouverture — choix dessiner OU saisir */}
          <Dialog open={!!deductDialog} onOpenChange={(o) => { if (!o) setDeductDialog(null); }}>
            <DialogContent className="z-[70]" overlayClassName="z-[70]" data-testid="deduct-opening-dialog">
              <DialogHeader>
                <DialogTitle>Deduzir um vão — {deductDialog?.label}</DialogTitle>
                <DialogDescription>
                  Subtraia uma janela ou uma porta do total da parede. Pode desenhá-la na planta ou introduzir a sua largura.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4">
                {/* Hauteur du mur → surfaces automatiques (m²) */}
                <div className="rounded-sm border border-primary/30 bg-primary/5 p-3" data-testid="wall-height-block">
                  <div className="flex items-end gap-3">
                    <div className="grid gap-1">
                      <Label className="text-xs">Altura da parede (m)</Label>
                      <Input key={`wh-${deductDialog?.measurement_id}`}
                             defaultValue={deductLiveMeasure?.wall_height_m || (lastWallHeight || "")}
                             placeholder="2.50" inputMode="decimal" data-testid="wall-height-input"
                             className="h-9 w-28"
                             onBlur={(e) => {
                               const h = parseFloat(String(e.target.value).replace(",", "."));
                               if ((h || 0) !== (deductLiveMeasure?.wall_height_m || 0))
                                 setWallHeightApi(deductDialog.measurement_id, h || 0);
                             }} />
                    </div>
                    <p className="flex-1 text-[11px] text-muted-foreground">
                      Introduza a altura para calcular automaticamente os m² de parede (bruto = comprimento × altura) e os vãos a deduzir.
                    </p>
                  </div>
                  {deductLiveMeasure?.wall_area_net_m2 != null && (
                    <div className="mt-2 grid grid-cols-3 gap-2 text-center" data-testid="wall-area-summary">
                      <div className="rounded-sm bg-background p-2">
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Parede bruta</p>
                        <p className="num text-sm font-semibold">{Number(deductLiveMeasure.wall_area_gross_m2 || 0).toFixed(2)} m²</p>
                      </div>
                      <div className="rounded-sm bg-background p-2">
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Vãos</p>
                        <p className="num text-sm font-semibold text-destructive">−{Number(deductLiveMeasure.openings_area_m2 || 0).toFixed(2)} m²</p>
                      </div>
                      <div className="rounded-sm bg-primary/10 p-2">
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Parede líquida</p>
                        <p className="num text-sm font-bold text-primary">{Number(deductLiveMeasure.wall_area_net_m2 || 0).toFixed(2)} m²</p>
                      </div>
                    </div>
                  )}
                  {deductLiveMeasure?.wall_area_net_m2 > 0 && (
                    <Button size="sm" variant="outline" className="mt-2 w-full rounded-sm gap-2"
                            data-testid="report-wall-area-devis"
                            onClick={() => reportWallAreaToDevis(deductLiveMeasure)}>
                      <ArrowRight className="h-3.5 w-3.5" /> Transferir a área líquida para o orçamento (m²)
                    </Button>
                  )}
                </div>
                {deductLiveMeasure?.openings?.length > 0 && (
                  <div className="rounded-sm border border-border p-2" data-testid="deduct-openings-list">
                    <div className="mb-1 flex items-center justify-between text-[11px] font-semibold text-muted-foreground">
                      <span>Vãos deduzidos</span>
                      <span className="num">
                        brut {Number(deductLiveMeasure.gross_m ?? deductLiveMeasure.value_m ?? 0).toFixed(2)} m → net {Number(deductLiveMeasure.value_m ?? 0).toFixed(2)} m
                      </span>
                    </div>
                    <div className="space-y-1">
                      {deductLiveMeasure.openings.map((op, oi) => (
                        <div key={op.opening_id} className="flex items-center gap-2" data-testid={`deduct-opening-${oi}`}>
                          <span className="w-4 text-[11px] text-muted-foreground">{oi + 1}.</span>
                          <span className="flex-1 truncate text-xs">{op.label || "Vão"}</span>
                          <Input defaultValue={op.width_m} inputMode="decimal"
                                 title="Largura (m)"
                                 data-testid={`deduct-opening-${oi}-width`}
                                 className="h-8 w-16 text-xs"
                                 onBlur={(e) => {
                                   const w = parseFloat(String(e.target.value).replace(",", "."));
                                   if (w > 0 && w !== op.width_m) patchOpening(op.opening_id, { width_m: w });
                                 }} />
                          <span className="text-[11px] text-muted-foreground">×</span>
                          <Input defaultValue={op.height_m || ""} inputMode="decimal"
                                 title="Altura (m) — para o cálculo dos m²" placeholder="haut."
                                 data-testid={`deduct-opening-${oi}-height`}
                                 className="h-8 w-16 text-xs"
                                 onBlur={(e) => {
                                   const h = parseFloat(String(e.target.value).replace(",", "."));
                                   if (h > 0 && h !== op.height_m) patchOpening(op.opening_id, { height_m: h });
                                 }} />
                          <span className="text-[11px] text-muted-foreground">m ×</span>
                          <Input type="number" min={1} defaultValue={op.count || 1}
                                 title="Número"
                                 data-testid={`deduct-opening-${oi}-count`}
                                 className="h-8 w-16 text-xs"
                                 onBlur={(e) => {
                                   const c = Math.max(1, parseInt(e.target.value) || 1);
                                   if (c !== (op.count || 1)) patchOpening(op.opening_id, { count: c });
                                 }} />
                          <Button size="icon" variant="ghost"
                                  data-testid={`deduct-opening-${oi}-remove`}
                                  onClick={() => removeOpening(op.opening_id)}
                                  className="h-7 w-7 text-destructive hover:bg-destructive/10">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      ))}
                    </div>
                    <p className="mt-1 text-[10px] text-muted-foreground">Altere uma largura/um número e depois clique fora para guardar.</p>
                  </div>
                )}
                <Button variant="outline" className="rounded-sm gap-2 justify-start"
                        data-testid="deduct-choose-draw"
                        onClick={() => armDeductDraw({ measurement_id: deductDialog.measurement_id, label: deductDialog.label })}>
                  <DoorOpen className="h-4 w-4" /> Desenhar a janela na planta (2 pontos)
                </Button>
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="flex-1 border-t border-border" /> ou introduzir <span className="flex-1 border-t border-border" />
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] text-muted-foreground">Type :</span>
                  <Button type="button" size="sm" variant={deductNature === "porte" ? "default" : "outline"}
                          className="h-7 rounded-sm text-[11px]" data-testid="opening-preset-porte"
                          onClick={() => applyOpeningPreset("porte")}>
                    Porta ({openingPresetH("porte")} m)
                  </Button>
                  <Button type="button" size="sm" variant={deductNature === "fenetre" ? "default" : "outline"}
                          className="h-7 rounded-sm text-[11px]" data-testid="opening-preset-fenetre"
                          onClick={() => applyOpeningPreset("fenetre")}>
                    Janela ({openingPresetH("fenetre")} m)
                  </Button>
                </div>
                <div className="flex items-end gap-3 flex-wrap">
                  <div className="grid gap-1">
                    <Label className="text-xs">Largura (m)</Label>
                    <Input value={deductWidth} onChange={(e) => setDeductWidth(e.target.value)}
                           placeholder="1.20" inputMode="decimal" data-testid="deduct-width-input"
                           className="h-9 w-24" />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Altura (m)</Label>
                    <Input value={deductHeight} onChange={(e) => setDeductHeight(e.target.value)}
                           placeholder="1.00" inputMode="decimal" data-testid="deduct-height-input"
                           className="h-9 w-24" />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Número</Label>
                    <Input type="number" min={1} value={deductCount}
                           onChange={(e) => setDeductCount(e.target.value)}
                           data-testid="deduct-count-input" className="h-9 w-20" />
                  </div>
                  <Button onClick={submitDeductTyped} data-testid="deduct-typed-submit"
                          className="rounded-sm gap-2 h-9">
                    <Scissors className="h-4 w-4" /> Deduzir
                  </Button>
                </div>
                <p className="text-[10px] text-muted-foreground -mt-2">
                  A altura é opcional: sem ela, só a largura é deduzida (em ml). Com ela, o vão também é deduzido em m².
                </p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDeductDialog(null)}
                        data-testid="deduct-dialog-close" className="rounded-sm">Fechar</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <RoomEstimateDialog
            open={roomEstimate !== null}
            estimate={roomEstimate}
            planId={plan?.plan_id}
            busy={estimateLoading}
            onRecompute={(opts) => {
              const rid = roomEstimate?.room?.room_id;
              if (rid) generateRoomEstimate(rid, opts);
            }}
            onClose={() => setRoomEstimate(null)}
            onAddToQuote={(est) => {
              // Injecte tous les matériaux des métiers dans le batch PriceSearch
              const items = [];
              Object.values(est.trades || {}).forEach((t) => {
                (t.materials || []).forEach((m) => items.push(m));
              });
              if (items.length === 0) return toast.info("Nenhum material a comparar");
              sessionStorage.setItem("construpilot_price_search_batch", JSON.stringify({
                items,
                source: "room_estimate",
                project_name: `Divisão ${est.room?.name || "-"} — ${plan?.filename || "Planta"}`,
                total_avg: est.total_budget || 0,
                ts: Date.now(),
              }));
              toast.success(`${items.length} material${items.length > 1 ? "x" : ""} adicionada${items.length > 1 ? "s" : ""} no orçamento`);
              setRoomEstimate(null);
              // Navigate to /prix
              window.location.href = "/precos?from=room-estimate";
            }}
          />

          <LiveTotalBar
            planId={plan?.plan_id}
            rooms={rooms}
            onOpenEstimate={generateRoomEstimate}
          />

          {/* ACTIVE TOOL BAR — Retour + Annuler le dernier point (tous les outils de mesure) */}
          {tool !== TOOLS.SELECT && (
            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-sm border border-primary/30 bg-primary/5 px-3 py-2"
                 data-testid="active-tool-bar">
              <Badge variant="outline" className="rounded-sm gap-1 border-primary/40 text-primary font-semibold">
                Ferramenta ativa: {TOOL_LABELS[tool] || tool}
              </Badge>
              {(tool === TOOLS.DIST || tool === TOOLS.SURFACE) && (
                <Button size="sm" variant={cumulMode ? "default" : "outline"}
                        onClick={() => { setCumulMode((v) => !v); setPoints([]); if (cumulMode) { setCumulSegments([]); setCumulLabel(""); } }}
                        data-testid="tool-cumul-toggle"
                        className={`rounded-sm gap-1 h-8 ${cumulMode ? "bg-primary text-white" : ""}`}
                        title={cumulIsArea ? "Somar várias zonas de pavimento numa única área" : "Somar vários troços de uma mesma parede (janelas/portas = vãos excluídos)"}>
                  <Layers className="h-3 w-3" /> Acumulado {cumulIsArea ? "surface" : "parede"} {cumulMode ? "ON" : "OFF"}
                </Button>
              )}
              <span className="flex-1" />
              <Button size="sm" variant="outline" onClick={() => setPoints(points.slice(0, -1))}
                      disabled={!points.length} data-testid="tool-undo-point"
                      className="rounded-sm gap-1 h-8">
                <Undo2 className="h-3 w-3" /> Cancelar o último ponto
              </Button>
              <Button size="sm" variant="secondary" onClick={() => { setTool(TOOLS.SELECT); setPoints([]); }}
                      data-testid="tool-back-select" className="rounded-sm gap-1 h-8">
                <ArrowLeft className="h-3 w-3" /> Voltar
              </Button>
            </div>
          )}

          {/* CUMUL (mur OU surface) — barre dédiée : total en direct + terminer / annuler */}
          {(tool === TOOLS.DIST || tool === TOOLS.SURFACE) && cumulMode && (
            <div className="mt-3 flex flex-wrap items-center gap-3 rounded-sm border-2 border-dashed px-3 py-2"
                 style={{ borderColor: cumulColor, background: `${cumulColor}12` }}
                 data-testid="cumul-wall-bar">
              <div className="flex items-center gap-2">
                <input type="color" value={cumulColor}
                       onChange={(e) => setCumulColor(e.target.value)}
                       data-testid="cumul-wall-color"
                       className="h-7 w-7 shrink-0 cursor-pointer rounded border border-border bg-transparent p-0" />
                <select value={cumulPoste} onChange={(e) => applyCumulPoste(e.target.value)}
                        data-testid="cumul-poste-select"
                        className="h-8 rounded-md border border-border bg-background px-2 text-xs max-w-[190px]">
                  <option value="">Artigo a orçamentar…</option>
                  {posteCatalog.filter((p) => cumulIsArea ? p.family !== "length" : p.family !== "area").map((p) => (
                    <option key={p.key} value={p.key}>{p.label}</option>
                  ))}
                </select>
                <Input value={cumulLabel} onChange={(e) => setCumulLabel(e.target.value)}
                       placeholder={cumulIsArea ? "Nome da área (ex.: Pavimento R/C)" : "Nome da parede (ex.: Parede fachada norte)"}
                       data-testid="cumul-wall-label"
                       className="h-8 text-xs w-44" />
              </div>
              <Badge variant="outline" className="rounded-sm num font-semibold"
                     style={{ borderColor: cumulColor, color: cumulColor }}
                     data-testid="cumul-wall-total">
                {cumulSegments.length} {cumulIsArea ? "zone" : "troço"}{cumulSegments.length > 1 ? "s" : ""} · {cumulTotal.value.toFixed(2)} {cumulTotal.unit}
              </Badge>
              <span className="text-[10px] text-muted-foreground">
                {cumulIsArea
                  ? "Meça uma zona (≥3 pontos) → duplo clique para a adicionar → recomece"
                  : "Meça um troço → duplo clique para o adicionar → continue depois da janela"}
              </span>
              <span className="flex-1" />
              <Button size="sm" variant="outline" onClick={cancelCumulWall}
                      disabled={!cumulSegments.length && points.length < 2}
                      data-testid="cumul-wall-cancel" className="rounded-sm gap-1 h-8">
                <X className="h-3 w-3" /> Cancelar
              </Button>
              <Button size="sm" onClick={finishCumul}
                      disabled={!cumulSegments.length && points.length < (cumulIsArea ? 3 : 2)}
                      data-testid="cumul-wall-finish"
                      className="rounded-sm gap-2 h-8 text-white"
                      style={{ background: cumulColor }}>
                <Save className="h-3 w-3" /> {cumulIsArea ? "Terminar a superfície" : "Terminar a parede"} ({cumulTotal.value.toFixed(2)} {cumulTotal.unit})
              </Button>
            </div>
          )}

          {/* DÉDUCTION D'OUVERTURE — dessin armé sur un mur ciblé */}
          {deductDraw && (
            <div className="mt-3 flex flex-wrap items-center gap-3 rounded-sm border-2 border-dashed border-amber-500 bg-amber-50 px-3 py-2"
                 data-testid="deduct-draw-bar">
              <Badge variant="outline" className="rounded-sm gap-1 border-amber-500 text-amber-700 font-semibold">
                <DoorOpen className="h-3 w-3" /> Deduzir vãos — {deductDraw.label}
              </Badge>
              <span className="text-[10px] text-muted-foreground">
                Desenhe cada janela/porta (2 pontos) e depois duplo clique — encadeie várias e depois «Terminar»
              </span>
              <span className="flex-1" />
              {points.length === 2 && (
                <Button size="sm" onClick={() => submitDeductDraw(points)}
                        data-testid="deduct-draw-finish"
                        className="rounded-sm gap-2 h-8 bg-amber-600 text-white hover:bg-amber-700">
                  <Save className="h-3 w-3" /> Deduzir este vão
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => { setDeductDraw(null); setPoints([]); setTool(TOOLS.SELECT); }}
                      data-testid="deduct-draw-cancel" className="rounded-sm gap-1 h-8">
                <X className="h-3 w-3" /> Terminar
              </Button>
            </div>
          )}

          {/* CONTEXT ACTIONS */}
          {points.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 items-center">
              <Badge variant="outline" className="rounded-sm num" data-testid="points-count">{points.length} point{points.length > 1 ? "s" : ""}</Badge>
              {(tool === TOOLS.DIST || tool === TOOLS.POLY || tool === TOOLS.ROOM || tool === TOOLS.SURFACE) && (
                <span className="text-[10px] text-muted-foreground" data-testid="dblclick-hint">
                  duplo clique = terminar · clique seguinte = nova medição
                </span>
              )}
              {tool === TOOLS.DIST && !cumulMode && points.length === 2 && (
                <Button size="sm" onClick={() => finishDistance()} data-testid="tool-finish-distance" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Medir
                </Button>
              )}
              {tool === TOOLS.DIST && cumulMode && points.length === 2 && (
                <Button size="sm" onClick={onCanvasDoubleClick} data-testid="cumul-add-segment"
                        className="rounded-sm gap-2 text-white" style={{ background: cumulColor }}>
                  <Plus className="h-3 w-3" /> Adicionar este troço
                </Button>
              )}
              {tool === TOOLS.POLY && points.length >= 2 && (
                <Button size="sm" onClick={() => finishPolyline()} data-testid="tool-finish-polyline" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Terminar polilinha
                </Button>
              )}
              {tool === TOOLS.SURFACE && !cumulMode && points.length >= 3 && (
                <Button size="sm" onClick={() => finishSurface()} data-testid="tool-finish-surface" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Terminar superfície
                </Button>
              )}
              {tool === TOOLS.SURFACE && cumulMode && points.length >= 3 && (
                <Button size="sm" onClick={onCanvasDoubleClick} data-testid="cumul-add-zone"
                        className="rounded-sm gap-2 text-white" style={{ background: cumulColor }}>
                  <Plus className="h-3 w-3" /> Adicionar esta zona
                </Button>
              )}
              {tool === TOOLS.ROOM && points.length >= 3 && (
                <>
                  <PresetPicker
                    kinds={["floor", "paint", "insulation", "wall"]}
                    onApply={(p) => setCurrentPreset(p)}
                    currentSelection={{ unit: "m²" }}
                    testIdPrefix="room-preset"
                  />
                  {currentPreset && (
                    <Badge variant="outline" className="text-[10px] rounded-sm gap-1">
                      <span className="h-2 w-2 rounded-full" style={{ background: currentPreset.color }} />
                      {currentPreset.name}
                    </Badge>
                  )}
                  <Button size="sm" onClick={() => finishRoom()} data-testid="tool-finish-room" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                    <Save className="h-3 w-3" /> Fechar divisão
                  </Button>
                </>
              )}
              {tool === TOOLS.PITCH && points.length >= 3 && (
                <>
                  <Input
                    type="number" min={0} max={80} step={1}
                    value={pitchDegrees}
                    onChange={(e) => setPitchDegrees(Math.max(0, Math.min(80, Number(e.target.value) || 0)))}
                    data-testid="pitch-degrees-input"
                    className="rounded-sm num h-8 w-20 text-xs"
                    title="Ângulo de inclinação em graus (0° = plano)"
                  />
                  <span className="text-xs text-muted-foreground">°</span>
                  <Button size="sm" onClick={finishPitchSurface} data-testid="tool-finish-pitch"
                          className="rounded-sm gap-2 hover:bg-blue-600 hover:text-white">
                    <Save className="h-3 w-3" /> Fechar cobertura
                  </Button>
                </>
              )}
              {tool === TOOLS.ANGLE && points.length < 3 && (
                <span className="text-xs text-muted-foreground">
                  {points.length === 0 && "Clique na 1.ª aresta do ângulo"}
                  {points.length === 1 && "Clique no vértice do ângulo"}
                  {points.length === 2 && "Clique na 2.ª aresta"}
                </span>
              )}
              <Button size="sm" variant="ghost" onClick={() => setPoints([])} className="rounded-sm" title="Apagar todos os pontos da medição em curso">Cancelar tudo</Button>
            </div>
          )}

          {/* COUNTER ACTIVE PANEL (chip per counter with markers total) */}
          {tool === TOOLS.COUNTER && (
            <div className="mt-3 flex flex-wrap gap-2 items-center" data-testid="counter-panel">
              {annotations.counters.map(c => (
                <button
                  key={c.id}
                  onClick={() => setActiveCounterId(c.id)}
                  data-testid={`counter-chip-${c.id}`}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs ${
                    activeCounterId === c.id ? "border-primary bg-primary/10" : "border-border"
                  }`}
                  style={{ borderColor: activeCounterId === c.id ? c.color : undefined }}
                >
                  <span className="h-3 w-3 rounded-full" style={{ background: c.color }} />
                  <span className="font-medium">{c.label}</span>
                  <Badge variant="outline" className="text-[10px] rounded-sm num">{c.markers.length}</Badge>
                </button>
              ))}
              <Button
                size="sm" variant="outline" onClick={() => {
                  const nb = annotations.counters.length;
                  const label = window.prompt(`Nome do contador ${nb + 1} (ex.: Tomadas, Focos, Radiadores):`, `Contador ${nb + 1}`);
                  if (!label) return;
                  const newC = {
                    id: `cnt_${Date.now()}`,
                    label,
                    color: COUNTER_COLORS[nb % COUNTER_COLORS.length],
                    unit: "u",
                    markers: [],
                  };
                  setAnnotations({ ...annotations, counters: [...annotations.counters, newC] });
                  setActiveCounterId(newC.id);
                }}
                data-testid="counter-add-new"
                className="rounded-sm gap-1 h-8 text-xs"
              >
                + Novo contador
              </Button>
              <PresetPicker
                kinds={["counter", "opening"]}
                onApply={applyPresetToTool}
                currentSelection={{ unit: "u" }}
                testIdPrefix="counter-preset"
              />
              {activeCounterId && (
                <Button
                  size="sm" variant="ghost"
                  onClick={() => {
                    if (!window.confirm("Eliminar este contador e os seus marcadores?")) return;
                    setAnnotations({
                      ...annotations,
                      counters: annotations.counters.filter(c => c.id !== activeCounterId),
                    });
                    setActiveCounterId(null);
                  }}
                  data-testid="counter-delete-active"
                  className="rounded-sm text-destructive text-xs"
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              )}
            </div>
          )}

          {/* WALLS SUMMARY CARD */}
          {detectedWalls && wallsSummary?.totals && (
            <div className="mt-3 border border-border rounded-sm p-3 bg-secondary/30"
                 data-testid="walls-summary-card">
              <div className="flex items-center justify-between mb-2">
                <p className="overline">Paredes detetadas {reclassifyMode && (
                  <span className="text-primary">· clique numa parede para alternar o seu tipo</span>
                )}</p>
                <Badge variant="outline" className="rounded-sm text-[10px] num">
                  {detectedWalls.segment_count} segments
                </Badge>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[
                  ["porteur",  "text-red-500 border-red-500/40 bg-red-500/5",   "Estrutural"],
                  ["cloison",  "text-primary border-primary/40 bg-primary/5",   "Divisória"],
                  ["doublage", "text-blue-500 border-blue-500/40 bg-blue-500/5", "Isolamento térmico interior"],
                ].map(([key, cls, label]) => {
                  const t = wallsSummary.totals[key] || { count: 0, ml: 0 };
                  return (
                    <div key={key} className={`border rounded-sm p-2 ${cls}`}
                         data-testid={`walls-${key}`}>
                      <p className="text-[10px] uppercase font-bold tracking-wider">{label}</p>
                      <p className="num text-lg font-extrabold">{t.count}</p>
                      <p className="text-[10px] num">{t.ml} ml</p>
                    </div>
                  );
                })}
              </div>
              {/* Distinction matériau porteur détectée par l'IA (brique / parpaing / béton) */}
              {plan?.ai_analysis?.wall_types && (
                <div className="mt-2 flex flex-wrap gap-1.5 items-center" data-testid="walls-material-hint">
                  <span className="text-[10px] text-muted-foreground">Material das paredes resistentes (IA):</span>
                  {plan.ai_analysis.wall_types.hatching_present &&
                   plan.ai_analysis.wall_types.hatching_present !== "nenhum" ? (
                    <Badge variant="outline" className="rounded-sm text-[10px] capitalize border-red-500/40 text-red-500">
                      {plan.ai_analysis.wall_types.hatching_present}
                    </Badge>
                  ) : (
                    <span className="text-[10px] text-muted-foreground italic">
                      não detetado — execute « Ler a planta (IA) »
                    </span>
                  )}
                  {plan.ai_analysis.wall_types.load_bearing_visible && (
                    <Badge variant="outline" className="rounded-sm text-[10px] border-red-500/40 text-red-500">estruturais visíveis</Badge>
                  )}
                  {plan.ai_analysis.wall_types.partition_visible && (
                    <Badge variant="outline" className="rounded-sm text-[10px] border-primary/40 text-primary">divisórias visíveis</Badge>
                  )}
                </div>
              )}
            </div>
          )}

          {/* STRUCTURE IA — édition murs / ouvertures */}
          {structure && (structure.walls?.length > 0 || structure.openings?.length > 0 || structure.beams?.length > 0 || structure.floors?.length > 0 || structure.columns?.length > 0) && (
            <div className="mt-3 border border-red-500/30 rounded-sm p-3 bg-red-500/5" data-testid="structure-card">
              <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
                <p className="overline flex items-center gap-2">
                  <Sparkles className="h-3 w-3 text-red-500" /> Estrutura IA
                </p>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] text-muted-foreground">
                    <span className="text-red-500 font-bold">■</span> paredes ·
                    <span className="text-yellow-500 font-bold"> ■</span> janelas ·
                    <span className="text-purple-500 font-bold"> ■</span> portes
                  </span>
                  <Button size="sm" variant={showStructure ? "default" : "outline"}
                          onClick={() => setShowStructure((v) => !v)}
                          data-testid="toggle-structure-overlay" className="rounded-sm gap-1 h-7 text-xs">
                    <Layers className="h-3 w-3" /> {showStructure ? "Ocultar" : "Mostrar"}
                  </Button>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2 mb-2">
                <div className="border border-red-500/40 rounded-sm p-2 text-red-500" data-testid="structure-wall-count">
                  <p className="text-[10px] uppercase font-bold tracking-wider">Paredes</p>
                  <p className="num text-lg font-extrabold">{structure.walls?.length || 0}</p>
                </div>
                <div className="border border-yellow-500/40 rounded-sm p-2 text-yellow-600" data-testid="structure-opening-count">
                  <p className="text-[10px] uppercase font-bold tracking-wider">Aberto.</p>
                  <p className="num text-lg font-extrabold">{structure.openings?.length || 0}</p>
                </div>
                <div className="border border-purple-800/40 rounded-sm p-2 text-purple-800" data-testid="structure-beam-count">
                  <p className="text-[10px] uppercase font-bold tracking-wider">Vigas</p>
                  <p className="num text-lg font-extrabold">{structure.beams?.length || 0}</p>
                </div>
                <div className="border border-purple-600/40 rounded-sm p-2 text-purple-600" data-testid="structure-column-count">
                  <p className="text-[10px] uppercase font-bold tracking-wider">Pilares</p>
                  <p className="num text-lg font-extrabold">{structure.columns?.length || 0}</p>
                </div>
              </div>

              {/* Descriptif chiffré */}
              {descriptif && (
                <div className="mb-2 border border-border rounded-sm p-2 bg-background" data-testid="structure-descriptif">
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="overline">Descritivo orçamentado</p>
                    <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      Altura paredes
                      <input type="number" step="0.1" min="1" max="6" value={wallHeight}
                             onChange={(e) => setWallHeight(parseFloat(e.target.value) || 2.5)}
                             data-testid="structure-wall-height"
                             className="w-14 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> m
                    </label>
                  </div>
                  {/* Hauteur par arases NGF (AS - AI) — prioritaire sur la hauteur murs */}
                  <div className="flex items-center gap-2 mb-1.5 text-[10px] text-muted-foreground">
                    <span className="whitespace-nowrap">Arases NGF:</span>
                    <label className="flex items-center gap-1">AI
                      <input type="number" step="0.01" value={araseInf}
                             onChange={(e) => setAraseInf(e.target.value)}
                             data-testid="structure-arase-inf" placeholder="inf."
                             className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />
                    </label>
                    <label className="flex items-center gap-1">AS
                      <input type="number" step="0.01" value={araseSup}
                             onChange={(e) => setAraseSup(e.target.value)}
                             data-testid="structure-arase-sup" placeholder="sup."
                             className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />
                    </label>
                    {araseInf !== "" && araseSup !== "" && Number(araseSup) > Number(araseInf) && (
                      <span className="text-emerald-600" data-testid="structure-arase-height">
                        H = {(Number(araseSup) - Number(araseInf)).toFixed(2)} m
                      </span>
                    )}
                  </div>
                  {/* Type de bâtiment — visible : pilote le type de plancher */}
                  <div className="flex items-center gap-1.5 mb-1.5" data-testid="batiment-type-toggle">
                    <span className="text-[10px] text-muted-foreground whitespace-nowrap">Edifício:</span>
                    {[
                      { v: "dalle_pleine", label: "🏢 Edifício (laje maciça)" },
                      { v: "poutrelles_hourdis", label: "🏠 Moradia (abobadilha)" },
                      { v: "auto", label: "Auto" },
                    ].map((o) => (
                      <button key={o.v} type="button"
                              onClick={() => setPlancherType(o.v)}
                              data-testid={`batiment-${o.v}`}
                              className={`text-[10px] px-2 py-0.5 rounded-sm border transition-colors ${
                                plancherType === o.v
                                  ? "bg-primary text-primary-foreground border-primary"
                                  : "bg-background border-input text-muted-foreground hover:border-primary/50"}`}>
                        {o.label}
                      </button>
                    ))}
                  </div>
                  {/* Presets de réglages béton par chantier */}
                  <div className="flex items-center gap-2 mb-1.5">
                    <select value={selectedPreset}
                            onChange={(e) => { if (e.target.value) applyBetonPreset(e.target.value); else setSelectedPreset(""); }}
                            data-testid="beton-preset-select"
                            className="flex-1 h-7 text-[11px] rounded-sm border border-input bg-background px-1">
                      <option value="">Escolher uma configuração (obra)…</option>
                      {betonPresets.map((p) => (
                        <option key={p.name} value={p.name}>{p.name}{p.builtin ? " (type)" : ""}</option>
                      ))}
                    </select>
                    {selectedPreset && !betonPresets.find((p) => p.name === selectedPreset)?.builtin && (
                      <Button size="sm" variant="outline" onClick={deleteBetonPreset}
                              data-testid="beton-preset-delete" className="rounded-sm h-7 w-7 p-0 text-destructive">
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={saveBetonPreset}
                            data-testid="beton-preset-save" className="rounded-sm h-7 text-[10px] gap-1">
                      <Save className="h-3 w-3" /> Sob…
                    </Button>
                    <Button size="sm" variant="outline" onClick={runCompare}
                            data-testid="beton-preset-compare" className="rounded-sm h-7 text-[10px] gap-1">
                      Comparar
                    </Button>
                  </div>
                  {!descriptif.calibrated && (
                    <p className="text-[10px] text-destructive mb-1">⚠️ Planta não calibrada — quantidades indisponíveis.</p>
                  )}
                  {/* Épaisseurs réglables pour le métré béton */}
                  <div className="flex items-center gap-3 mb-1.5 text-[10px] text-muted-foreground">
                    <label className="flex items-center gap-1">Esp. laje
                      <input type="number" step="0.05" min="0.05" max="1" value={dalleEp}
                             onChange={(e) => setDalleEp(parseFloat(e.target.value) || 0.20)}
                             data-testid="structure-dalle-ep"
                             className="w-12 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> m
                    </label>
                    <label className="flex items-center gap-1">Esp. parede
                      <input type="number" step="0.05" min="0.05" max="1" value={voileEp}
                             onChange={(e) => setVoileEp(parseFloat(e.target.value) || 0.20)}
                             data-testid="structure-voile-ep"
                             className="w-12 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> m
                    </label>
                    <label className="flex items-center gap-1">Viga b×h
                      <input type="number" step="0.05" min="0.1" max="1" value={poutreL}
                             onChange={(e) => setPoutreL(parseFloat(e.target.value) || 0.20)}
                             data-testid="structure-poutre-l"
                             className="w-11 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />×
                      <input type="number" step="0.05" min="0.1" max="1.5" value={poutreH}
                             onChange={(e) => setPoutreH(parseFloat(e.target.value) || 0.40)}
                             data-testid="structure-poutre-h"
                             className="w-11 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> m
                    </label>
                  </div>
                  {/* Ratios de ferraillage ajustables (kg/m³) */}
                  <details className="mb-1.5" data-testid="acier-ratios">
                    <summary className="text-[10px] font-semibold cursor-pointer text-orange-600">Rácios de aço (kg/m³) — ajustáveis</summary>
                    <div className="grid grid-cols-3 gap-2 mt-1 text-[10px] text-muted-foreground">
                      {[["semelles", "Sapatas"], ["poteaux", "Pilares"], ["poutres", "Vigas"], ["dalles", "Lajes"], ["voiles", "Paredes"]].map(([k, lbl]) => (
                        <label key={k} className="flex flex-col gap-0.5">{lbl}
                          <input type="number" step="5" min="0" max="400" value={acierRatios[k]}
                                 onChange={(e) => setAcierRatios((r) => ({ ...r, [k]: parseFloat(e.target.value) || 0 }))}
                                 data-testid={`acier-ratio-${k}`}
                                 className="w-full rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />
                        </label>
                      ))}
                    </div>
                    <label className="flex items-center gap-1 mt-1.5 text-[10px] text-muted-foreground">Preço aço
                      <input type="number" step="0.1" min="0" max="10" value={acierPriceKg}
                             onChange={(e) => setAcierPriceKg(parseFloat(e.target.value) || 0)}
                             data-testid="acier-price-kg"
                             className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> €/kg
                      <span className="ml-2">Preço betão</span>
                      <input type="number" step="5" min="0" max="500" value={betonPriceM3}
                             onChange={(e) => setBetonPriceM3(parseFloat(e.target.value) || 0)}
                             data-testid="beton-price-m3"
                             className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> €/m³
                    </label>
                    <label className="flex items-center gap-1 mt-1.5 text-[10px] text-muted-foreground">Mão de obra
                      <input type="number" step="10" min="0" max="2000" value={laborPriceM3}
                             onChange={(e) => setLaborPriceM3(parseFloat(e.target.value) || 0)}
                             data-testid="labor-price-m3"
                             className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> €/m³
                      <span className="ml-2">Margem</span>
                      <input type="number" step="1" min="0" max="100" value={marginPct}
                             onChange={(e) => setMarginPct(parseFloat(e.target.value) || 0)}
                             data-testid="margin-pct"
                             className="w-14 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> %
                    </label>
                    <div className="flex items-center gap-1.5 mt-1.5 text-[10px] text-muted-foreground" data-testid="plan-price-level">
                      <span>Gama (biblio. partilhada):</span>
                      {["bas", "moyen", "haut"].map((lvl) => (
                        <button key={lvl} type="button" onClick={() => setPriceLevel(lvl)}
                                data-testid={`plan-price-level-${lvl}`}
                                className={`rounded-sm px-2 py-0.5 border transition-colors capitalize ${
                                  priceLevel === lvl ? "border-primary bg-primary text-white"
                                                     : "border-input hover:border-primary/40"}`}>
                          {lvl}
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 mt-1.5 text-[10px] text-muted-foreground">
                      <span>Margem/artigo:</span>
                      <label className="flex items-center gap-0.5">Betão
                        <input type="number" step="1" min="0" max="100" placeholder="—" value={marginBeton}
                               onChange={(e) => setMarginBeton(e.target.value)} data-testid="margin-beton"
                               className="w-11 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />%
                      </label>
                      <label className="flex items-center gap-0.5">Aços
                        <input type="number" step="1" min="0" max="100" placeholder="—" value={marginAcier}
                               onChange={(e) => setMarginAcier(e.target.value)} data-testid="margin-acier"
                               className="w-11 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />%
                      </label>
                      <label className="flex items-center gap-0.5">MO
                        <input type="number" step="1" min="0" max="100" placeholder="—" value={marginLabor}
                               onChange={(e) => setMarginLabor(e.target.value)} data-testid="margin-labor"
                               className="w-11 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />%
                      </label>
                    </div>
                    <Button size="sm" variant="outline" onClick={saveBetonDefaults}
                            data-testid="save-beton-defaults"
                            className="rounded-sm h-6 text-[10px] gap-1 mt-1.5">
                      <Save className="h-3 w-3" /> Guardar como predefinições
                    </Button>
                  </details>
                  {/* Prix béton par poste (€/m³) — chiffrage plus fin */}
                  <details className="mb-1.5" data-testid="beton-prices-poste">
                    <summary className="text-[10px] font-semibold cursor-pointer text-sky-600">Preço betão por item (€/m³) — opcional</summary>
                    <div className="grid grid-cols-3 gap-2 mt-1 text-[10px] text-muted-foreground">
                      {[["semelles", "Sapatas"], ["proprete", "Limpeza"], ["poteaux", "Pilares"], ["poutres", "Vigas"], ["voiles", "Paredes"]].map(([k, lbl]) => (
                        <label key={k} className="flex flex-col gap-0.5">{lbl}
                          <input type="number" step="5" min="0" max="500" value={betonPrices[k]}
                                 onChange={(e) => setBetonPrices((r) => ({ ...r, [k]: parseFloat(e.target.value) || 0 }))}
                                 data-testid={`beton-price-${k}`}
                                 className="w-full rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />
                        </label>
                      ))}
                    </div>
                    <p className="text-[9px] text-muted-foreground mt-1">Deixar a 0 para usar o preço betão global ({betonPriceM3} €/m³).</p>
                    <div className="mt-2 pt-2 border-t border-border grid gap-1.5">
                      <p className="text-[10px] font-semibold text-sky-600">Pavimento (orçamentado ao m²)</p>
                      <label className="flex items-center justify-between gap-1 text-[10px] text-muted-foreground">Tipo de pavimento
                        <select value={plancherType} onChange={(e) => setPlancherType(e.target.value)}
                                data-testid="plancher-type"
                                className="rounded-sm border border-input bg-background px-1 py-0.5 text-[10px]">
                          <option value="auto">Auto (segundo plano)</option>
                          <option value="dalle_pleine">Laje maciça BA (edifício)</option>
                          <option value="poutrelles_hourdis">Vigotas-abobadilhas (casa)</option>
                        </select>
                      </label>
                      <label className="flex items-center justify-between gap-1 text-[10px] text-muted-foreground">Preço pavimento (€/m²)
                        <input type="number" step="5" min="0" max="500" value={plancherPriceM2}
                               onChange={(e) => setPlancherPriceM2(parseFloat(e.target.value) || 0)}
                               data-testid="plancher-price-m2"
                               className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />
                      </label>
                      <p className="text-[9px] text-muted-foreground">0 = tabela automática segundo a espessura: ≤16 cm → 120 € · 17–20 cm → 140 € · &gt;20 cm → 160 €/m².</p>
                    </div>
                    <label className="flex items-center gap-1 mt-1.5 text-[10px] text-muted-foreground">Espessura betão de limpeza
                      <input type="number" step="1" min="0" max="30"
                             value={Math.round(propreteEp * 100)}
                             onChange={(e) => setPropreteEp((parseFloat(e.target.value) || 0) / 100)}
                             data-testid="proprete-ep-cm"
                             className="w-14 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> cm
                    </label>
                  </details>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                    <span className="text-muted-foreground flex items-center gap-1">Pavimentos (chão)
                      {descriptif.planchers_source === "auto" && (
                        <span className="text-[9px] px-1 rounded-sm bg-emerald-500/15 text-emerald-600 font-bold" data-testid="planchers-auto-badge">AUTO IA</span>
                      )}
                    </span><span className="num text-right">{descriptif.planchers_m2} m²</span>
                    <span className="text-muted-foreground">Paredes portantes</span><span className="num text-right">{descriptif.murs_porteurs_ml} ml</span>
                    <span className="text-muted-foreground">Divisórias</span><span className="num text-right">{descriptif.cloisons_ml} ml</span>
                    <span className="text-muted-foreground">Paredes (superfície)</span><span className="num text-right">{descriptif.murs_surface_m2} m²</span>
                    <span className="text-muted-foreground">Portas / Janelas / Vãos</span><span className="num text-right">{descriptif.portes} / {descriptif.fenetres} / {descriptif.baies}</span>
                    <span className="text-muted-foreground">Vigas</span><span className="num text-right">{descriptif.poutres_ml} ml</span>
                    <span className="text-muted-foreground">Pilares</span><span className="num text-right">{descriptif.poteaux || 0} u</span>
                    <span className="text-muted-foreground">Sapatas</span><span className="num text-right">{descriptif.semelles || 0} u</span>
                    {descriptif.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Betão total</span>
                        <span className="num text-right font-semibold" data-testid="descriptif-beton">{descriptif.beton_total_m3} m³</span>
                      </>
                    )}
                    {descriptif.acier_total_kg > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Aço (armadura)</span>
                        <span className="num text-right font-semibold text-orange-600" data-testid="descriptif-acier">{descriptif.acier_total_kg} kg</span>
                      </>
                    )}
                    {(betonPriceM3 > 0 || acierPriceKg > 0) && descriptif.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Custo material (betão + aços)</span>
                        <span className="num text-right font-semibold text-emerald-700" data-testid="descriptif-cout-matiere">
                          {Math.round((descriptif.beton_total_m3 || 0) * betonPriceM3 + (descriptif.acier_total_kg || 0) * acierPriceKg).toLocaleString("pt-PT")} €
                        </span>
                      </>
                    )}
                    {(betonPriceM3 > 0 || acierPriceKg > 0 || laborPriceM3 > 0) && descriptif.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Preço de venda estimado{marginPct > 0 ? ` (margem ${marginPct}%)` : ""}</span>
                        <span className="num text-right font-bold text-primary" data-testid="descriptif-prix-vente">
                          {Math.round((((descriptif.beton_total_m3 || 0) * betonPriceM3 + (descriptif.acier_total_kg || 0) * acierPriceKg) + (descriptif.beton_total_m3 || 0) * laborPriceM3) * (1 + marginPct / 100)).toLocaleString("pt-PT")} €
                        </span>
                      </>
                    )}
                  </div>
                  {descriptif.beton_total_m3 > 0 && (
                    <details className="mt-2" open data-testid="detail-par-poste">
                      <summary className="text-[11px] font-semibold cursor-pointer text-primary">Detalhe por rubrica (betão + aços)</summary>
                      <div className="mt-1 border border-border rounded-sm overflow-hidden">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60"><tr>
                            <th className="text-left px-1.5 py-1">Artigo</th>
                            <th className="text-right px-1.5 py-1">Betão</th>
                            <th className="text-right px-1.5 py-1">Aços</th>
                          </tr></thead>
                          <tbody>
                            {[
                              { k: "semelles", label: `Sapatas (${descriptif.semelles || 0} u)`, b: descriptif.beton_semelles_m3, a: descriptif.acier_semelles_kg },
                              { k: "proprete", label: "Betão de limpeza (esp. 5 cm)", b: descriptif.beton_proprete_m3, a: 0 },
                              { k: "poteaux", label: `Pilares (${descriptif.poteaux || 0} u)`, b: descriptif.beton_poteaux_m3, a: descriptif.acier_poteaux_kg },
                              { k: "poutres", label: `Vigas (${descriptif.poutres_ml || 0} ml)`, b: descriptif.beton_poutres_m3, a: descriptif.acier_poutres_kg },
                              { k: "dalles", label: `Lajes / pavimentos (${descriptif.planchers_m2 || 0} m²)`, b: descriptif.beton_dalles_m3, a: descriptif.acier_dalles_kg },
                              { k: "voiles", label: `Paredes resistentes (${descriptif.murs_porteurs_ml || 0} ml)`, b: descriptif.beton_voiles_m3, a: descriptif.acier_voiles_kg },
                            ].filter((r) => (r.b || 0) > 0).map((r) => (
                              <tr key={r.k} className="border-t border-border" data-testid={`poste-row-${r.k}`}>
                                <td className="px-1.5 py-0.5">{r.label}</td>
                                <td className="px-1.5 py-0.5 num text-right">{r.b} m³</td>
                                <td className="px-1.5 py-0.5 num text-right text-orange-600">{r.a ? `${r.a} kg` : "—"}</td>
                              </tr>
                            ))}
                            <tr className="border-t-2 border-border bg-muted/40 font-bold">
                              <td className="px-1.5 py-1">Total</td>
                              <td className="px-1.5 py-1 num text-right">{descriptif.beton_total_m3} m³</td>
                              <td className="px-1.5 py-1 num text-right text-orange-600">{descriptif.acier_total_kg} kg</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </details>
                  )}
                  {descriptif.poteaux_table?.length > 0 && (
                    <details className="mt-2" data-testid="poteaux-table">
                      <summary className="text-[11px] font-semibold cursor-pointer text-purple-600">Tabela dos pilares ({descriptif.poteaux_table.length})</summary>
                      <div className="mt-1 max-h-40 overflow-auto border border-border rounded-sm">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60 sticky top-0"><tr>
                            <th className="text-left px-1.5 py-1">Referência</th><th className="text-left px-1.5 py-1">Secção</th><th className="text-right px-1.5 py-1">Betão</th>
                          </tr></thead>
                          <tbody>
                            {descriptif.poteaux_table.map((p) => (
                              <tr key={p.ref} className="border-t border-border">
                                <td className="px-1.5 py-0.5 font-bold text-purple-600">{p.ref}</td>
                                <td className="px-1.5 py-0.5 num">{p.section}</td>
                                <td className="px-1.5 py-0.5 num text-right">{p.volume_m3} m³</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  )}
                  {descriptif.beams_table?.length > 0 && (
                    <details className="mt-2" data-testid="poutres-table">
                      <summary className="text-[11px] font-semibold cursor-pointer text-purple-800">Tabela das vigas ({descriptif.beams_table.length})</summary>
                      <div className="mt-1 max-h-40 overflow-auto border border-border rounded-sm">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60 sticky top-0"><tr>
                            <th className="text-left px-1.5 py-1">Referência</th><th className="text-right px-1.5 py-1">Âmbito</th><th className="text-right px-1.5 py-1">Betão</th>
                          </tr></thead>
                          <tbody>
                            {descriptif.beams_table.map((b) => (
                              <tr key={b.ref} className="border-t border-border">
                                <td className="px-1.5 py-0.5 font-bold text-purple-800">{b.ref}</td>
                                <td className="px-1.5 py-0.5 num text-right">{b.portee_m} m</td>
                                <td className="px-1.5 py-0.5 num text-right">{b.volume_m3} m³</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  )}
                  <Button size="sm" onClick={estimateAndDownloadQuote} disabled={quoteBusy} data-testid="structure-estimate-quote"
                          className="w-full rounded-sm h-9 text-sm font-bold gap-1.5 mt-2 bg-primary hover:bg-primary/90">
                    <FileDown className="h-4 w-4" /> {quoteBusy ? "Estimativa em curso…" : "Estimar o orçamento (PDF)"}
                  </Button>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Estrutura / betão apenas — paredes, pilares, vigas, lajes, sapatas + aços (área = lajes) · betão {betonPriceM3} €/m³ · aços {acierPriceKg} €/kg · mão de obra {laborPriceM3} €/m³ · margem {marginPct}%
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <Button size="sm" variant="outline" onClick={sendToQuote} data-testid="structure-to-quote"
                            className="rounded-sm h-7 text-xs gap-1 flex-1">
                      <ArrowRight className="h-3 w-3" /> Abrir no editor
                    </Button>
                    <Button size="sm" variant="outline" onClick={exportAnnotatedPdf} data-testid="structure-export-pdf"
                            className="rounded-sm h-7 text-xs gap-1">
                      <FileDown className="h-3 w-3" /> PDF anotado
                    </Button>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <Button size="sm" variant="outline" onClick={exportBetonXlsx} data-testid="structure-export-beton-xlsx"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-emerald-700 border-emerald-600/40">
                      <Sheet className="h-3 w-3" /> Medições Excel
                    </Button>
                    <Button size="sm" variant="outline" onClick={exportBetonPdf} data-testid="structure-export-beton-pdf"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-red-700 border-red-600/40">
                      <FileDown className="h-3 w-3" /> Medições PDF
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setAiChatOpen(true)} data-testid="structure-ai-assistant"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-primary border-primary/40">
                      <Bot className="h-3 w-3" /> Assistente IA
                    </Button>
                  </div>
                </div>
              )}
              <p className="text-[10px] text-muted-foreground mb-2">
                Clique numa parede/abertura para a selecionar, depois arraste as suas extremidades (pontos brancos) para a ajustar.
              </p>
              {selectedStruct && (
                <div className="flex items-center gap-2 flex-wrap mb-2 p-2 rounded-sm bg-background border border-border" data-testid="structure-selected-actions">
                  <Badge variant="outline" className="rounded-sm text-[10px]">
                    {selectedStruct.type === "wall" ? "Parede selecionada"
                      : selectedStruct.type === "beam" ? "Viga selecionada"
                      : selectedStruct.type === "column" ? "Pilar selecionado"
                      : selectedStruct.type === "footing" ? "Sapata selecionada" : "Abertura selecionada"}
                  </Badge>
                  {(selectedStruct.type === "wall" || selectedStruct.type === "opening") && (
                    <Button size="sm" variant="outline" onClick={toggleStructType}
                            data-testid="structure-toggle-type" className="rounded-sm h-7 text-xs gap-1">
                      {selectedStruct.type === "wall" ? "Resistente ↔ Divisória" : "Porta ↔ Janela ↔ Vão"}
                    </Button>
                  )}
                  <Button size="sm" variant="outline" onClick={deleteStructItem}
                          data-testid="structure-delete" className="rounded-sm h-7 text-xs gap-1 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
                    <Trash2 className="h-3 w-3" /> Eliminar
                  </Button>
                </div>
              )}
              <div className="flex items-center gap-2 flex-wrap">
                <Button size="sm" variant="outline" onClick={addStructWall}
                        data-testid="structure-add-wall" className="rounded-sm h-7 text-xs gap-1">
                  <Plus className="h-3 w-3" /> Parede
                </Button>
                <Button size="sm" variant="outline" onClick={() => addStructOpening("fenetre")}
                        data-testid="structure-add-window" className="rounded-sm h-7 text-xs gap-1 text-yellow-600 border-yellow-500/40">
                  <Plus className="h-3 w-3" /> Janela
                </Button>
                <Button size="sm" variant="outline" onClick={() => addStructOpening("porte")}
                        data-testid="structure-add-door" className="rounded-sm h-7 text-xs gap-1 text-purple-600 border-purple-500/40">
                  <Plus className="h-3 w-3" /> Porta
                </Button>
                <Button size="sm" variant="outline" onClick={addStructBeam}
                        data-testid="structure-add-beam" className="rounded-sm h-7 text-xs gap-1 text-purple-800 border-purple-800/40">
                  <Plus className="h-3 w-3" /> Viga
                </Button>
                <Button size="sm" variant="outline" onClick={addStructColumn}
                        data-testid="structure-add-column" className="rounded-sm h-7 text-xs gap-1 text-purple-600 border-purple-600/40">
                  <Plus className="h-3 w-3" /> Pilar
                </Button>
                <Button size="sm" variant="outline" onClick={addStructFooting}
                        data-testid="structure-add-footing" className="rounded-sm h-7 text-xs gap-1 text-yellow-700 border-yellow-600/40">
                  <Plus className="h-3 w-3" /> Sapata
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT PANEL — Métré */}
        <div id="plan-results-panel" className="surface p-4 max-h-[80vh] overflow-auto min-w-0">
          <Tabs value={rightTab} onValueChange={setRightTab}>
            <TabsList className="w-full rounded-sm">
              <TabsTrigger value="rooms" className="flex-1 rounded-sm" data-testid="tab-rooms">Divisões</TabsTrigger>
              <TabsTrigger value="materials" className="flex-1 rounded-sm" data-testid="tab-materials">Materiais</TabsTrigger>
              <TabsTrigger value="ai" className="flex-1 rounded-sm" data-testid="tab-ai">Controlo</TabsTrigger>
              <TabsTrigger value="history" className="flex-1 rounded-sm" data-testid="tab-history" onClick={loadHistory}>
                <History className="h-3 w-3" />
              </TabsTrigger>
            </TabsList>

            <TabsContent value="rooms" className="mt-3 grid gap-3">
              {rooms.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Calibre a planta e depois utilize a ferramenta <b>Divisão</b> para traçar um contorno.
                </p>
              )}
              {rooms.map((r) => (
                <div key={r.room_id} className="border border-border p-3 rounded-sm" data-testid={`room-item-${r.room_id}`}>
                  <div className="flex items-center justify-between">
                    <p className="font-bold text-sm">{r.name}</p>
                    <Button size="icon" variant="ghost" onClick={() => deleteRoom(r.room_id)} className="h-6 w-6 rounded-sm">
                      <Trash2 className="h-3 w-3 text-destructive" />
                    </Button>
                  </div>
                  {(r.floor_material || r.surface_delta_pct != null || (r.deductions || []).length > 0) && (
                    <div className="flex gap-1 flex-wrap mt-1">
                      {r.floor_material && (
                        <Badge variant="outline" className="rounded-sm text-[10px] capitalize"
                               title={r.floor_note_text || undefined}
                               data-testid={`room-floor-material-${r.room_id}`}>
                          {r.floor_material}
                        </Badge>
                      )}
                      {r.surface_delta_pct != null && (
                        <Badge variant="outline"
                               className={`rounded-sm text-[10px] num ${Math.abs(r.surface_delta_pct) > 5 ? "border-amber-500 text-amber-500" : "border-green-600 text-green-600"}`}
                               title={`Área escrita na planta: ${r.surface_written_m2} m²`}
                               data-testid={`room-surface-delta-${r.room_id}`}>
                          escrito {r.surface_written_m2} m² ({r.surface_delta_pct > 0 ? "+" : ""}{r.surface_delta_pct}%)
                        </Badge>
                      )}
                      {(r.deductions || []).map((d) => (
                        <Badge key={d.deduction_id} variant="outline"
                               className="rounded-sm text-[10px] num border-red-400 text-red-500 gap-1"
                               title={`Área bruta: ${r.surface_gross_m2} m²`}
                               data-testid={`room-deduction-${d.deduction_id}`}>
                          − {d.area_m2} m² {d.label}
                          <button onClick={() => removeDeduction(r.room_id, d.deduction_id)}
                                  className="hover:text-destructive"
                                  data-testid={`room-deduction-remove-${d.deduction_id}`}>
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-2 mt-2 text-xs num">
                    <span>Superfície</span><span className="text-right font-bold">{r.surface_m2} m²</span>
                    <span>Perímetro</span><span className="text-right">{r.perimeter_m} m</span>
                    <span>Paredes brutas</span><span className="text-right">{r.wall_area_gross_m2} m²</span>
                    <span>Vãos</span><span className="text-right text-destructive">-{r.openings_area_m2 || 0} m²</span>
                    <span>Paredes líquidas</span><span className="text-right font-bold">{r.wall_area_net_m2} m²</span>
                    {r.volume_m3 != null && (<><span>Volume</span><span className="text-right">{r.volume_m3} m³</span></>)}
                  </div>
                  {(r.openings || []).length > 0 && (
                    <div className="mt-2 pt-2 border-t border-border/60 space-y-1">
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Aberturas ({r.openings.length})</p>
                      {r.openings.map((o) => (
                        <div key={o.opening_id} className="flex items-center justify-between text-xs">
                          <span className="truncate">
                            <span className="text-primary font-semibold capitalize">{o.kind}</span>
                            {o.label ? ` · ${o.label}` : ""} · <span className="num">{o.width_m}×{o.height_m}m{o.count > 1 ? ` ×${o.count}` : ""}</span>
                          </span>
                          <button
                            onClick={() => deleteOpening(r.room_id, o.opening_id)}
                            className="text-destructive hover:text-red-600 ml-2"
                            title="Eliminar"
                            data-testid={`delete-opening-${o.opening_id}`}
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {rooms.length > 0 && (
                <Button onClick={loadTakeoff} data-testid="load-takeoff-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Calculator className="h-4 w-4" /> Calcular as medições totais
                </Button>
              )}
              {takeoff && (
                <div className="border-t border-border pt-3 grid gap-1 text-xs num" data-testid="takeoff-totals">
                  <p className="overline mb-2">Totais</p>
                  <div className="flex justify-between"><span>Pavimento total</span><b>{takeoff.totals.floor_m2} m²</b></div>
                  <div className="flex justify-between"><span>Tetos</span><b>{takeoff.totals.ceiling_m2} m²</b></div>
                  <div className="flex justify-between"><span>Paredes líquidas</span><b>{takeoff.totals.walls_net_m2} m²</b></div>
                  <div className="flex justify-between"><span>Perímetro</span><b>{takeoff.totals.perimeter_m} m</b></div>

                  {takeoff.levels?.length > 1 && (
                    <div className="mt-3" data-testid="takeoff-by-level">
                      <p className="overline mb-2">Por nível</p>
                      {takeoff.levels.map((lvl) => (
                        <div key={String(lvl.level_index)} className="border-l-2 border-primary pl-2 mb-2">
                          <p className="font-bold text-primary">{lvl.level_label} · {lvl.rooms.length} divisão{lvl.rooms.length > 1 ? "s" : ""}</p>
                          <div className="flex justify-between"><span>Pavimento</span><span>{lvl.totals.floor_m2} m²</span></div>
                          <div className="flex justify-between"><span>Paredes líquidas</span><span>{lvl.totals.walls_net_m2} m²</span></div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex gap-2 mt-3">
                    <Button size="sm" onClick={sendToEstimator} data-testid="send-to-estimator" className="flex-1 rounded-sm hover:bg-orange-600 hover:text-white">
                      <Calculator className="h-3 w-3 mr-1" /> Orçamentar
                    </Button>
                    <Button size="sm" variant="outline" onClick={sendToPrices} data-testid="send-to-prices" className="flex-1 rounded-sm">
                      <Search className="h-3 w-3 mr-1" /> Preço
                    </Button>
                  </div>
                </div>
              )}
            </TabsContent>

            <TabsContent value="materials" className="mt-3 grid gap-3">
              <div className="grid gap-2">
                <Label>Material do pavimento</Label>
                <Select value={floorMaterial} onValueChange={setFloorMaterial}>
                  <SelectTrigger className="rounded-sm h-9" data-testid="floor-material-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["parquet", "carrelage", "stratifie", "vinyle", "moquette", "beton_cire"].map(m => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={loadTakeoff} disabled={rooms.length === 0} data-testid="compute-materials-btn"
                      className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                <Calculator className="h-4 w-4" /> Calcular materiais
              </Button>
              {materials && (
                <div className="grid gap-3 text-xs" data-testid="materials-result">
                  {materials.floor && <MatCard label={`Sol (${materials.floor.material})`}
                    lines={[[`Superfície`, `${materials.floor.surface_m2} m²`], [`+${materials.floor.waste_pct}% perdas`, `${materials.floor.quantity_m2} m² a encomendar`]]} />}
                  {materials.paint && <MatCard label="Pintura" lines={[
                    [`Superfície`, `${materials.paint.surface_m2} m²`],
                    [`${materials.paint.coats} demãos, margem ${materials.paint.margin_pct}%`, `${materials.paint.liters_recommended} L`],
                  ]} />}
                  {materials.placo && <MatCard label="Pladur BA13" lines={[
                    [`Superfície`, `${materials.placo.surface_m2} m²`],
                    [`+${materials.placo.waste_pct}% perdas`, `${materials.placo.plates} plaques`],
                  ]} />}
                  {materials.skirting && <MatCard label="Rodapés" lines={[
                    [`Perímetro - portas`, `${materials.skirting.net_m} m`],
                    [`+ perdas`, `${materials.skirting.quantity_m} m`],
                  ]} />}
                </div>
              )}
            </TabsContent>

            <TabsContent value="ai" className="mt-3 grid gap-3">
              <CotesCheckPanel plan={plan} pageIndex={pageIndex} refreshPlan={refreshPlan}
                               selectedIndex={selectedCheckedCote} onFocusCote={focusCheckedCote} />
              {!plan.ai_analysis && (
                <p className="text-xs text-muted-foreground">
                  Escolha uma análise no topo e depois clique em <b>Analisar a planta</b>. Verifique aqui as divisões, vãos e áreas lidas.
                </p>
              )}
              {plan.ai_analysis && (
                <div className="grid gap-3 text-xs" data-testid="ai-analysis-result">
                  {plan.ai_analysis.error && <p className="text-destructive">{plan.ai_analysis.error}</p>}
                  {plan.ai_analysis.plan_type && (
                    <div className="flex gap-2 flex-wrap">
                      <Badge variant="outline" className="rounded-sm">{plan.ai_analysis.plan_type}</Badge>
                      {plan.ai_analysis.quality && <Badge variant="outline" className="rounded-sm">{plan.ai_analysis.quality}</Badge>}
                      {plan.ai_analysis.detected_scale && <Badge variant="outline" className="rounded-sm num">{plan.ai_analysis.detected_scale}</Badge>}
                      {plan.ai_analysis.confidence !== undefined && (
                        <Badge variant="outline" className="rounded-sm num">
                          conf. {Math.round((plan.ai_analysis.confidence || 0) * 100)}%
                        </Badge>
                      )}
                    </div>
                  )}

                  {/* --- SYMBOLES DÉTECTÉS PAR L'IA (électricité + plomberie) --- */}
                  {!plan.ai_analysis.error && (plan.ai_analysis.electrical || plan.ai_analysis.plumbing) && (
                    <div className="border border-border p-2 rounded-sm grid gap-2" data-testid="ai-symbols">
                      <p className="overline">Símbolos detetados</p>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                            <Zap className="h-3 w-3 text-primary" /> Eletricidade
                          </p>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {[["Tomadas", "outlets"], ["Inter.", "switches"], ["Pts ilum.", "light_points"], ["Focos", "spots"], ["Tabela", "panels"], ["RJ45/TV", "network_tv"]]
                              .map(([lbl, k]) => (plan.ai_analysis.electrical?.[k] ? (
                                <Badge key={k} variant="outline" className="rounded-sm num text-[10px]">
                                  {plan.ai_analysis.electrical[k]} {lbl}
                                </Badge>) : null))}
                            {!Object.values(plan.ai_analysis.electrical || {}).some((v) => typeof v === "number" && v > 0) && (
                              <span className="text-[10px] text-muted-foreground">Nenhum símbolo</span>
                            )}
                          </div>
                        </div>
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                            <Droplet className="h-3 w-3 text-primary" /> Canalização
                          </p>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {[["WC", "wc"], ["Lavatórios", "washbasins"], ["Duches", "showers"], ["Banheiras", "bathtubs"], ["Lava-loiças", "kitchen_sinks"], ["Esquentador", "water_heaters"], ["Máquina de lavar roupa", "washing_machines"]]
                              .map(([lbl, k]) => (plan.ai_analysis.plumbing?.[k] ? (
                                <Badge key={k} variant="outline" className="rounded-sm num text-[10px]">
                                  {plan.ai_analysis.plumbing[k]} {lbl}
                                </Badge>) : null))}
                            {!Object.values(plan.ai_analysis.plumbing || {}).some((v) => typeof v === "number" && v > 0) && (
                              <span className="text-[10px] text-muted-foreground">Nenhum símbolo</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {!plan.ai_analysis.error && plan.ai_analysis.client_info?.detected &&
                    (plan.ai_analysis.client_info.last_name || plan.ai_analysis.client_info.address) && (
                    <div className="border border-primary/30 bg-primary/5 p-2 rounded-sm grid gap-2" data-testid="ai-client-info">
                      <p className="overline flex items-center gap-1">
                        <Wand2 className="h-3 w-3 text-primary" /> Cliente detetado na planta
                      </p>
                      <p className="text-xs font-bold">
                        {[plan.ai_analysis.client_info.first_name, plan.ai_analysis.client_info.last_name].filter(Boolean).join(" ")}
                        {plan.ai_analysis.client_info.company ? ` · ${plan.ai_analysis.client_info.company}` : ""}
                      </p>
                      {(plan.ai_analysis.client_info.address || plan.ai_analysis.client_info.city) && (
                        <p className="text-[11px] text-muted-foreground">
                          {[plan.ai_analysis.client_info.address, plan.ai_analysis.client_info.postal_code, plan.ai_analysis.client_info.city].filter(Boolean).join(", ")}
                        </p>
                      )}
                      <Button size="sm" variant="outline"
                        className="rounded-sm gap-1 h-7 text-[11px] border-primary/40 text-primary hover:bg-primary hover:text-primary-foreground"
                        data-testid="ai-create-client-btn"
                        onClick={async () => {
                          try {
                            const { data } = await api.post(`/clients/from-plan/${plan.plan_id}`);
                            toast.success(data.duplicate ? "Ficha cliente já existente — abertura do orçamento" : "Ficha de cliente criada — preparação do orçamento");
                            nav(`/devis-editeur?plan=${plan.plan_id}&client=${data.client_id}`);
                          } catch (e) {
                            toast.error(e?.response?.data?.detail || "Criação impossível");
                          }
                        }}>
                        <Wand2 className="h-3 w-3" /> Criar cliente + orçamento
                      </Button>
                    </div>
                  )}

                  {/* --- ACTIONS COTES & TEXTES (iter62) --- */}
                  {!plan.ai_analysis.error && (
                    <div className="border border-primary/30 bg-primary/5 p-2 rounded-sm grid gap-2"
                         data-testid="ai-text-actions">
                      <p className="overline text-primary">Ações cotas & textos</p>
                      {(plan.ai_analysis.dimension_lines || []).some((d) => d.bbox_norm) && (
                        <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                disabled={aiActionBusy} onClick={calibrateFromCotes}
                                data-testid="calibrate-from-cotes-btn">
                          <Ruler className="h-3.5 w-3.5" />
                          Calibrar pelas cotas ({(plan.ai_analysis.dimension_lines || []).filter((d) => d.bbox_norm).length})
                        </Button>
                      )}
                      <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                              disabled={aiActionBusy} onClick={applyAiTexts}
                              data-testid="apply-ai-texts-btn">
                        <Sparkles className="h-3.5 w-3.5" />
                        Aplicar os textos da planta
                      </Button>
                      {currentCalib && rooms.some((r) => r.page_index === pageIndex) &&
                        (plan.ai_analysis.rooms || []).some((r) => r.surface_written_m2) && (
                        <>
                          <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                  disabled={aiActionBusy} onClick={() => checkWrittenSurfaces(false)}
                                  data-testid="reconcile-check-btn">
                            <Square className="h-3.5 w-3.5" />
                            Verificar as superfícies escritas
                          </Button>
                          <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                  disabled={aiActionBusy} onClick={downloadEcartsPdf}
                                  data-testid="ecarts-pdf-btn">
                            <FileDown className="h-3.5 w-3.5" />
                            Relatório de desvios (PDF)
                          </Button>
                          <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                  disabled={aiActionBusy}
                                  onClick={() => setSendEcartsDialog(true)}
                                  data-testid="send-ecarts-btn">
                            <Mail className="h-3.5 w-3.5" />
                            Enviar ao cliente
                          </Button>
                        </>
                      )}
                      {(plan.sent_reports || []).some((s) => s.kind === "ecarts") && (
                        <div className="grid gap-0.5 pt-1.5 border-t border-border/50"
                             data-testid="sent-reports-list">
                          <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">
                            Relatórios enviados
                          </p>
                          {(plan.sent_reports || [])
                            .filter((s) => s.kind === "ecarts")
                            .slice(-3).reverse().map((s, i) => (
                            <div key={i} className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground"
                                 data-testid={`sent-report-${i}`}>
                              <span className="truncate">✉ {s.to_email}</span>
                              <span className="flex items-center gap-1.5 shrink-0">
                                <span className="num">
                                  {new Date(s.sent_at).toLocaleDateString("pt-PT")}{" "}
                                  {new Date(s.sent_at).toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}
                                </span>
                                <button onClick={() => resendReport(s)} disabled={sendingEcarts}
                                        className="text-primary hover:text-orange-600 disabled:opacity-40 transition"
                                        title={`Reenviar para ${s.to_email}`}
                                        data-testid={`resend-report-${i}`}>
                                  <RotateCw className="h-3 w-3" />
                                </button>
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                      {reconcile && !reconcile.applied && reconcile.can_reconcile && (
                        <div className="border border-amber-500/40 bg-amber-500/10 rounded-sm p-2 grid gap-1"
                             data-testid="reconcile-result">
                          <p className="text-[11px]">
                            Desvio mediano medido ↔ escrito: <b className="num">{reconcile.deviation_pct}%</b>
                            {" "}({reconcile.matches.length} divisão{reconcile.matches.length > 1 ? "s" : ""} comparada{reconcile.matches.length > 1 ? "s" : ""})
                          </p>
                          {reconcile.matches.slice(0, 4).map((m, i) => (
                            <div key={i} className="flex justify-between text-[10px] text-muted-foreground">
                              <span>{m.room_name}</span>
                              <span className="num">{m.measured_m2} → {m.written_m2} m² ({m.delta_pct > 0 ? "+" : ""}{m.delta_pct}%)</span>
                            </div>
                          ))}
                          {reconcile.needs_recalib ? (
                            <Button size="sm" className="w-full mt-1 rounded-sm" disabled={aiActionBusy}
                                    onClick={() => checkWrittenSurfaces(true)}
                                    data-testid="reconcile-apply-btn">
                              Reajustar a escala ({reconcile.current_ppm?.toFixed(1)} → {reconcile.proposed_ppm?.toFixed(1)} px/m)
                            </Button>
                          ) : (
                            <p className="text-[10px] text-green-600">
                              ✓ Calibração coerente (desvio ≤ 5%) — nenhum reajuste necessário
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* --- TOTAUX GROS ŒUVRE --- */}
                  {plan.ai_analysis.totals_gros_oeuvre && Object.keys(plan.ai_analysis.totals_gros_oeuvre).length > 0 && (
                    <div className="border-2 border-primary/40 bg-primary/5 p-3 rounded-sm space-y-1"
                         data-testid="ai-gros-oeuvre-totals">
                      <p className="overline text-primary">Totais estrutura</p>
                      {plan.ai_analysis.totals_gros_oeuvre.linear_walls_m != null && (
                        <div className="flex justify-between"><span>Linear paredes total</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.linear_walls_m} ml</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.facade_walls_area_net_m2 != null && (
                        <div className="flex justify-between"><span>Fachadas (líquido)</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.facade_walls_area_net_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.interior_walls_area_m2 != null && (
                        <div className="flex justify-between"><span>Divisórias interiores</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.interior_walls_area_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.openings_area_m2 != null && (
                        <div className="flex justify-between"><span>Vãos</span>
                          <b className="num text-destructive">-{plan.ai_analysis.totals_gros_oeuvre.openings_area_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.floor_slab_area_m2 != null && (
                        <div className="flex justify-between"><span>Pavimentos/lajes</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.floor_slab_area_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.concrete_volume_m3_estimated != null && (
                        <div className="flex justify-between"><span>Volume betão estimado</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.concrete_volume_m3_estimated} m³</b></div>
                      )}
                    </div>
                  )}

                  {/* --- PIÈCES --- */}
                  {(plan.ai_analysis.rooms || []).length > 0 && (
                    <div className="border border-border p-2 rounded-sm">
                      <p className="overline mb-2">Peças ({plan.ai_analysis.rooms.length})</p>
                      {plan.ai_analysis.rooms.map((r, i) => (
                        <div key={i} className="flex justify-between border-b last:border-b-0 border-border/50 py-1">
                          <span>{r.name}{r.level ? <span className="text-muted-foreground"> · {r.level}</span> : null}</span>
                          <span className="num">{r.surface_written_m2 ?? r.estimated_surface_m2 ?? "—"} m²</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* --- FAÇADES --- */}
                  {(plan.ai_analysis.facade_walls || []).length > 0 && (
                    <div className="border border-border p-2 rounded-sm" data-testid="ai-facades">
                      <p className="overline mb-2">Fachadas ({plan.ai_analysis.facade_walls.length})</p>
                      {plan.ai_analysis.facade_walls.map((f, i) => (
                        <div key={i} className="text-xs py-1 border-b last:border-b-0 border-border/50">
                          <div className="flex justify-between">
                            <span><b className="uppercase">{f.orientation || "?"}</b> · {f.material_guess || "?"} · {f.wall_type || "?"}</span>
                            <span className="num">{f.area_net_m2 ?? f.area_gross_m2} m²</span>
                          </div>
                          {(f.length_m || f.height_m) && (
                            <div className="text-muted-foreground text-[10px] num">
                              {f.length_m} × {f.height_m} m {f.openings_area_m2 ? `· -${f.openings_area_m2} m² ouv.` : ""}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* --- ESCALIERS --- */}
                  {(plan.ai_analysis.stairwells || []).length > 0 && (
                    <div className="border border-border p-2 rounded-sm" data-testid="ai-stairwells">
                      <p className="overline mb-2">Escadas ({plan.ai_analysis.stairwells.length})</p>
                      {plan.ai_analysis.stairwells.map((s, i) => (
                        <div key={i} className="text-xs py-1 border-b last:border-b-0 border-border/50">
                          <div className="flex justify-between">
                            <span>{s.type || "?"} · {(s.connects_levels || []).join(" → ") || "?"}</span>
                            <span className="num">{s.footprint_m2} m²</span>
                          </div>
                          {s.steps && (
                            <div className="text-muted-foreground text-[10px] num">
                              {s.steps} degraus · caixa de escada {s.trémie_area_m2 || "?"} m²
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* --- OUVERTURES DÉTAIL --- */}
                  {plan.ai_analysis.openings?.details?.length > 0 && (
                    <div className="border border-border p-2 rounded-sm">
                      <p className="overline mb-2">Aberturas detalhadas ({plan.ai_analysis.openings.details.length})</p>
                      {plan.ai_analysis.openings.details.map((o, i) => (
                        <div key={i} className="flex justify-between text-xs py-0.5">
                          <span>{o.kind}{o.location ? ` · ${o.location}` : ""}</span>
                          <span className="num">{o.width_m}×{o.height_m}m × {o.count || 1}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {plan.ai_analysis.total_surface_written_m2 && (
                    <div className="border-t border-border pt-2 flex justify-between font-bold">
                      <span>Total superfícies habitáveis</span>
                      <span className="num text-primary">{plan.ai_analysis.total_surface_written_m2} m²</span>
                    </div>
                  )}
                  {(plan.ai_analysis.warnings || []).length > 0 && (
                    <div className="text-amber-500 text-xs">
                      ⚠ {plan.ai_analysis.warnings.join(" · ")}
                    </div>
                  )}
                  {(plan.ai_analysis.rooms || []).some((r) => r.surface_written_m2 || r.estimated_surface_m2) && (
                    <Button
                      size="sm"
                      className="w-full mt-1"
                      onClick={importAiRooms}
                      data-testid="import-ai-rooms-btn"
                    >
                      Importar estas divisões nas medições →
                    </Button>
                  )}
                </div>
              )}
            </TabsContent>
            <TabsContent value="history" className="mt-3 grid gap-2">
              {historyLoading ? (
                <p className="text-xs text-muted-foreground">A carregar…</p>
              ) : history.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Nenhum histórico — a app regista automaticamente as modificações (calibração, divisões, níveis).
                </p>
              ) : (
                <div className="grid gap-2 text-xs" data-testid="history-list">
                  {/* Compare toolbar */}
                  <div className="border border-border rounded-sm p-2 bg-secondary/30 flex items-center justify-between gap-2 flex-wrap">
                    <p className="text-[10px] text-muted-foreground">
                      Selecione 2 snapshots para comparar (A depois B):
                    </p>
                    <div className="flex gap-1 items-center">
                      <Badge variant={snapPickA ? "default" : "outline"}
                             className={`rounded-sm text-[10px] ${snapPickA ? "bg-primary text-white" : ""}`}
                             data-testid="snap-pick-a">
                        A {snapPickA ? "✓" : "?"}
                      </Badge>
                      <Badge variant={snapPickB ? "default" : "outline"}
                             className={`rounded-sm text-[10px] ${snapPickB ? "bg-primary text-white" : ""}`}
                             data-testid="snap-pick-b">
                        B {snapPickB ? "✓" : "?"}
                      </Badge>
                      <Button size="sm" onClick={runSnapshotCompare}
                              disabled={!snapPickA || !snapPickB || snapPickA === snapPickB}
                              data-testid="snap-compare-btn"
                              className="rounded-sm gap-1 h-6 text-[10px] hover:bg-orange-600 hover:text-white">
                        Comparar
                      </Button>
                      {(snapPickA || snapPickB || snapCompareResult) && (
                        <Button size="sm" variant="ghost"
                                onClick={() => { setSnapPickA(null); setSnapPickB(null); setSnapCompareResult(null); }}
                                data-testid="snap-compare-clear"
                                className="rounded-sm gap-1 h-6 text-[10px]">
                          Repor
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Compare result panel */}
                  {snapCompareResult && (
                    <div className="border border-primary/40 bg-primary/5 rounded-sm p-3"
                         data-testid="snap-compare-result">
                      <p className="font-bold text-primary mb-2">
                        Dif.: {snapCompareResult.before.label || snapCompareResult.before.action}
                        {" → "}
                        {snapCompareResult.after.label || snapCompareResult.after.action}
                      </p>
                      <div className="grid grid-cols-4 gap-2 text-[10px]">
                        <div className="text-emerald-500">+{snapCompareResult.added.length} adicionadas</div>
                        <div className="text-destructive">−{snapCompareResult.removed.length} retiradas</div>
                        <div className="text-amber-500">~{snapCompareResult.modified.length} modificadas</div>
                        <div className="num">
                          {snapCompareResult.delta_surface_m2 >= 0 ? "+" : ""}
                          {snapCompareResult.delta_surface_m2} m²
                        </div>
                      </div>
                      {snapCompareResult.added.length > 0 && (
                        <p className="text-[10px] mt-2 text-emerald-600" data-testid="snap-compare-added">
                          + {snapCompareResult.added.map(r => r.name).join(", ")}
                        </p>
                      )}
                      {snapCompareResult.removed.length > 0 && (
                        <p className="text-[10px] mt-1 text-destructive" data-testid="snap-compare-removed">
                          − {snapCompareResult.removed.map(r => r.name).join(", ")}
                        </p>
                      )}
                      {snapCompareResult.modified.length > 0 && (
                        <p className="text-[10px] mt-1 text-amber-600" data-testid="snap-compare-modified">
                          ~ {snapCompareResult.modified.map(r => `${r.name} (${r.delta_m2 >= 0 ? "+" : ""}${r.delta_m2} m²)`).join(", ")}
                        </p>
                      )}
                    </div>
                  )}

                  {history.map((s, idx) => {
                    // Diff avec le snapshot précédent (idx+1 car trié DESC)
                    const prev = history[idx + 1];
                    const diff = computeSnapshotDiff(prev, s);
                    const isA = snapPickA === s.snapshot_id;
                    const isB = snapPickB === s.snapshot_id;
                    const pickSnap = () => {
                      if (isA) { setSnapPickA(null); return; }
                      if (isB) { setSnapPickB(null); return; }
                      if (!snapPickA) setSnapPickA(s.snapshot_id);
                      else if (!snapPickB) setSnapPickB(s.snapshot_id);
                      else { setSnapPickA(snapPickB); setSnapPickB(s.snapshot_id); }
                    };
                    return (
                      <div key={s.snapshot_id}
                           className={`border p-2 rounded-sm group relative ${isA || isB ? "border-primary bg-primary/5" : "border-border"}`}
                           title={diff.summary}
                           data-testid={`history-item-${s.snapshot_id}`}>
                        <div className="flex items-center justify-between">
                          <div className="min-w-0">
                            {s.label ? (
                              <p className="font-bold text-primary truncate" title={s.label}
                                 data-testid={`history-label-${s.snapshot_id}`}>{s.label}</p>
                            ) : (
                              <p className="font-bold capitalize">{s.action.replace(/_/g, " ")}</p>
                            )}
                            <p className="num text-muted-foreground text-[10px]">
                              {s.label && <span className="capitalize">{s.action.replace(/_/g, " ")} · </span>}
                              {new Date(s.created_at).toLocaleString("pt-PT")} · {s.rooms?.length || 0} divisões
                            </p>
                            {diff.summary && (
                              <p className="text-[10px] mt-1 text-primary" data-testid={`history-diff-${s.snapshot_id}`}>
                                {diff.summary}
                              </p>
                            )}
                          </div>
                          <div className="flex gap-1 shrink-0">
                            <Button size="sm" variant={isA || isB ? "default" : "ghost"} onClick={pickSnap}
                                    data-testid={`pick-${s.snapshot_id}`}
                                    className={`rounded-sm gap-1 text-xs h-6 ${isA || isB ? "bg-primary text-white" : ""}`}>
                              {isA ? "A" : isB ? "B" : "◯"}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => openLabelDialog(s)}
                                    data-testid={`label-${s.snapshot_id}`}
                                    className="rounded-sm gap-1 text-xs h-6">
                              {s.label ? "Renomear" : "Nomear"}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => restoreSnapshot(s.snapshot_id)}
                                    data-testid={`restore-${s.snapshot_id}`}
                                    className="rounded-sm gap-1 text-xs h-6">
                              Restaurar
                            </Button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* SEND ECARTS DIALOG (iter64) */}
      <Dialog open={sendEcartsDialog} onOpenChange={setSendEcartsDialog}>
        <DialogContent className="rounded-sm" data-testid="send-ecarts-dialog">
          <DialogHeader>
            <DialogTitle>Enviar o relatório de desvios ao cliente</DialogTitle>
            <DialogDescription>
              O PDF de controlo das superfícies (medidas vs escritas) será anexado ao email.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="ecarts-email">Email do cliente</Label>
              <Input id="ecarts-email" type="email" placeholder="client@exemple.fr"
                     value={ecartsEmail} onChange={(e) => setEcartsEmail(e.target.value)}
                     data-testid="ecarts-email-input" className="rounded-sm" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="ecarts-message">Palavra personalizada (opcional)</Label>
              {msgTemplates.length > 0 && (
                <div className="flex flex-wrap gap-1.5" data-testid="msg-templates-row">
                  {msgTemplates.map((t) => (
                    <span key={t.template_id}
                          className="inline-flex items-center gap-1 border border-primary/40 bg-primary/5 rounded-sm px-2 py-0.5 text-[11px]">
                      <button onClick={() => setEcartsMessage(t.body)}
                              className="hover:text-primary transition max-w-[160px] truncate"
                              title={t.body}
                              data-testid={`msg-template-${t.template_id}`}>
                        {t.name}
                      </button>
                      <button onClick={() => deleteMsgTemplate(t.template_id)}
                              className="text-muted-foreground hover:text-destructive transition"
                              title="Eliminar este modelo"
                              data-testid={`msg-template-delete-${t.template_id}`}>
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <Textarea id="ecarts-message" rows={4}
                        placeholder="Olá, encontrará em anexo o relatório de controlo de superfícies do seu projeto…"
                        value={ecartsMessage} onChange={(e) => setEcartsMessage(e.target.value)}
                        data-testid="ecarts-message-input" className="rounded-sm" />
              {ecartsMessage.trim() && (
                <button onClick={saveMsgTemplate}
                        className="justify-self-start text-[11px] text-primary hover:text-orange-600 transition underline underline-offset-2"
                        data-testid="save-msg-template-btn">
                  + Guardar esta mensagem como modelo
                </button>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSendEcartsDialog(false)}
                    className="rounded-sm" data-testid="ecarts-send-cancel">Cancelar</Button>
            <Button onClick={sendEcartsReport} disabled={sendingEcarts}
                    className="rounded-sm gap-2" data-testid="ecarts-send-confirm">
              <Mail className="h-3.5 w-3.5" />
              {sendingEcarts ? "A enviar…" : "Enviar o relatório"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CALIB DIALOG */}
      <Dialog open={calibDialog} onOpenChange={setCalibDialog}>
        <DialogContent className="rounded-sm z-[70]" overlayClassName="z-[70]" data-testid="calib-dialog">
          <DialogHeader>
            <DialogTitle>Distância real entre os 2 pontos?</DialogTitle>
            <DialogDescription>
              Introduza uma cota conhecida da planta (ex: 4,25 m). ConstruPilot recalibrará tudo automaticamente.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="calib-dist">Distância em metros</Label>
            <Input
              id="calib-dist" value={calibDist} onChange={(e) => setCalibDist(e.target.value)}
              placeholder="4.25" data-testid="calib-distance-input"
              className="rounded-sm num h-11" autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCalibDialog(false); setPoints([]); }} className="rounded-sm">Cancelar</Button>
            <Button onClick={applyCalibration} data-testid="calib-confirm-btn"
                    className="rounded-sm hover:bg-orange-600 hover:text-white">Calibrar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* OPENING DIALOG */}
      <Dialog open={!!openingsDialog} onOpenChange={(o) => { if (!o) { setOpeningsDialog(null); setPoints([]); } }}>
        <DialogContent className="rounded-sm" data-testid="opening-dialog">
          <DialogHeader>
            <DialogTitle>Abertura em {openingsDialog?.room_name}</DialogTitle>
            <DialogDescription>
              Largura medida a partir dos seus 2 cliques. Ajuste o tipo e a altura abaixo. A área será automaticamente deduzida das paredes líquidas.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid grid-cols-3 gap-2">
              {[["porte", "Porta"], ["fenetre", "Janela"], ["baie", "Vão"]].map(([k, l]) => (
                <Button
                  key={k}
                  variant={pendingOpening.kind === k ? "default" : "outline"}
                  onClick={() => setPendingOpening((o) => ({ ...o, kind: k }))}
                  className="rounded-sm h-9"
                  data-testid={`opening-kind-${k}`}
                >{l}</Button>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <Label className="text-[10px] uppercase">Largura (m)</Label>
                <Input
                  type="number" step="0.05" min="0.05" max="10"
                  value={pendingOpening.width_m}
                  onChange={(e) => setPendingOpening((o) => ({ ...o, width_m: parseFloat(e.target.value) || 0 }))}
                  className="rounded-sm num h-10"
                  data-testid="opening-width"
                />
              </div>
              <div>
                <Label className="text-[10px] uppercase">Altura (m)</Label>
                <Input
                  type="number" step="0.05" min="0.05" max="6"
                  value={pendingOpening.height_m}
                  onChange={(e) => setPendingOpening((o) => ({ ...o, height_m: parseFloat(e.target.value) || 0 }))}
                  className="rounded-sm num h-10"
                  data-testid="opening-height"
                  autoFocus
                />
              </div>
              <div>
                <Label className="text-[10px] uppercase">Número</Label>
                <Input
                  type="number" step="1" min="1" max="100"
                  value={pendingOpening.count}
                  onChange={(e) => setPendingOpening((o) => ({ ...o, count: parseInt(e.target.value) || 1 }))}
                  className="rounded-sm num h-10"
                  data-testid="opening-count"
                />
              </div>
            </div>
            <div>
              <Label className="text-[10px] uppercase">Descrição (opcional)</Label>
              <Input
                value={pendingOpening.label}
                onChange={(e) => setPendingOpening((o) => ({ ...o, label: e.target.value }))}
                placeholder="Porta de entrada sul"
                className="rounded-sm h-10"
                data-testid="opening-label"
              />
            </div>
            <div className="text-xs text-muted-foreground border border-border rounded-sm p-2 bg-secondary/30">
              Superfície total deduzida: <b className="text-primary num">
                {(pendingOpening.width_m * pendingOpening.height_m * (pendingOpening.count || 1)).toFixed(2)} m²
              </b>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setOpeningsDialog(null); setPoints([]); }} className="rounded-sm">Cancelar</Button>
            <Button onClick={submitOpening} data-testid="opening-submit-btn"
                    className="rounded-sm">Adicionar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ROOM DIALOG */}
      <Dialog open={roomDialog} onOpenChange={setRoomDialog}>
        <DialogContent className="rounded-sm" data-testid="room-dialog">
          <DialogHeader>
            <DialogTitle>Nova peça</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-2">
              <Label>Nome</Label>
              <Input value={pendingRoomName} onChange={(e) => setPendingRoomName(e.target.value)}
                     data-testid="room-name-input" className="rounded-sm h-10" autoFocus />
            </div>
            <div className="grid gap-2">
              <Label>Pé-direito (m)</Label>
              <Input type="number" step="0.1" value={ceilingH} onChange={(e) => setCeilingH(e.target.value)}
                     data-testid="room-ceiling-input" className="rounded-sm h-10 num" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRoomDialog(false)} className="rounded-sm">Cancelar</Button>
            <Button onClick={saveRoom} data-testid="room-save-btn" className="rounded-sm hover:bg-orange-600 hover:text-white">Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CHIFFRAGE PAR CORPS D'ÉTAT — composition + estimation (comme le gros œuvre) */}
      <Dialog open={!!chiffrageDialog} onOpenChange={(o) => { if (!o) { setChiffrageDialog(null); setChiffrageResult(null); } }}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" overlayClassName="z-[70]" data-testid="chiffrage-dialog">
          <DialogHeader>
            <DialogTitle>Orçamentar um artigo — {chiffrageDialog?.label || "mesure"}</DialogTitle>
            <DialogDescription>
              Decomposição determinística (materiais + mão de obra) aplicada à quantidade medida. Preços por omissão editáveis.
            </DialogDescription>
          </DialogHeader>
          {chiffrageDialog && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="grid gap-1">
                  <Label className="text-xs">Artigo (especialidade)</Label>
                  <select value={chiffragePoste} onChange={(e) => setChiffragePoste(e.target.value)}
                          data-testid="chiffrage-poste-select"
                          className="h-9 rounded-md border border-border bg-background px-2 text-sm min-w-[220px]">
                    {posteCatalog.map((p) => (<option key={p.key} value={p.key}>{p.label}</option>))}
                  </select>
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Quantidade</Label>
                  <div className="h-9 flex items-center px-2 rounded-md border border-border bg-muted/40 text-sm num" data-testid="chiffrage-qty">
                    {measureQty(chiffrageDialog).q.toFixed(2)} {measureQty(chiffrageDialog).unit}
                  </div>
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Margem (%)</Label>
                  <Input type="number" value={chiffrageMargin} onChange={(e) => setChiffrageMargin(e.target.value)}
                         data-testid="chiffrage-margin" className="h-9 w-20" />
                </div>
                <Button onClick={runChiffrage} disabled={chiffrageLoading} data-testid="chiffrage-run"
                        className="h-9 rounded-sm gap-2">
                  <Calculator className="h-4 w-4" /> {chiffrageLoading ? "Cálculo…" : "Calcular"}
                </Button>
              </div>

              {/* Options de composition selon le poste */}
              <div className="flex flex-wrap items-end gap-3" data-testid="chiffrage-options">
                {(chiffragePoste === "placo" || chiffragePoste === "plafond") && (
                  <label className="flex items-center gap-2 text-xs" data-testid="opt-isolation">
                    <input type="checkbox" checked={!!chiffrageOpts.with_isolation}
                           onChange={(e) => setChiffrageOpts((o) => ({ ...o, with_isolation: e.target.checked }))} />
                    Com isolamento
                  </label>
                )}
                {chiffragePoste === "peinture" && (
                  <div className="grid gap-1">
                    <Label className="text-xs">Número de camadas</Label>
                    <Input type="number" min={1} value={chiffrageOpts.couches} data-testid="opt-couches"
                           onChange={(e) => setChiffrageOpts((o) => ({ ...o, couches: e.target.value }))} className="h-9 w-24" />
                  </div>
                )}
                {chiffragePoste === "chape" && (
                  <div className="grid gap-1">
                    <Label className="text-xs">Espessura da betonilha (m)</Label>
                    <Input type="number" step="0.01" value={chiffrageOpts.ep_m} data-testid="opt-ep"
                           onChange={(e) => setChiffrageOpts((o) => ({ ...o, ep_m: e.target.value }))} className="h-9 w-24" />
                  </div>
                )}
                {chiffragePoste === "escalier" && (
                  <div className="grid gap-1">
                    <Label className="text-xs">Número de degraus</Label>
                    <Input type="number" min={0} value={chiffrageOpts.nb_marches} data-testid="opt-marches"
                           onChange={(e) => setChiffrageOpts((o) => ({ ...o, nb_marches: e.target.value }))} className="h-9 w-24" />
                  </div>
                )}
              </div>

              {/* Bibliothèque d'ouvrages : appliquer / enregistrer une composition */}
              <div className="rounded-sm border border-dashed border-border p-2 space-y-2" data-testid="ouvrages-lib">
                <div className="flex items-center justify-between">
                  <Label className="text-xs font-medium">Biblioteca de artigos</Label>
                  <span className="text-[10px] text-muted-foreground">reutilizável em todas as suas obras</span>
                </div>
                {ouvrages.length > 0 && (
                  <div className="flex flex-wrap gap-1.5" data-testid="ouvrages-list">
                    {ouvrages.map((ov) => (
                      <span key={ov.ouvrage_id} className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 pl-2 pr-1 py-0.5 text-[11px]">
                        <button type="button" onClick={() => applyOuvrage(ov)}
                                data-testid={`apply-ouvrage-${ov.ouvrage_id}`}
                                className="hover:text-primary" title="Aplicar este artigo">
                          {ov.name} <span className="text-muted-foreground">· {ov.poste}</span>
                          {ov.is_shared && <span className="ml-1 rounded-full bg-primary/15 text-primary px-1 text-[9px]" title={`Partilhado por ${ov.owner_name || "a equipa"}`}>equipa</span>}
                        </button>
                        {ov.is_mine !== false && (
                          <button type="button" onClick={() => deleteOuvrage(ov.ouvrage_id)}
                                  data-testid={`delete-ouvrage-${ov.ouvrage_id}`}
                                  className="text-muted-foreground hover:text-destructive px-1" title="Eliminar">×</button>
                        )}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <Input value={saveOuvrageName} onChange={(e) => setSaveOuvrageName(e.target.value)}
                         placeholder="Nome do artigo (ex.: Divisória em pladur com isolamento)"
                         data-testid="ouvrage-name-input" className="h-8 flex-1 text-xs" />
                  <label className="flex items-center gap-1 text-[11px] whitespace-nowrap" data-testid="ouvrage-shared-toggle" title="Visível por toda a equipa da empresa">
                    <input type="checkbox" checked={saveOuvrageShared} onChange={(e) => setSaveOuvrageShared(e.target.checked)} /> Equipa
                  </label>
                  <Button size="sm" variant="outline" onClick={saveCurrentAsOuvrage}
                          data-testid="save-ouvrage-btn" className="h-8 rounded-sm gap-1 text-[11px]">
                    <Save className="h-3 w-3" /> Guardar
                  </Button>
                </div>
              </div>

              {chiffrageResult && (
                <div className="space-y-2" data-testid="chiffrage-result">
                  <div className="rounded border border-border overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50 text-xs">
                        <tr><th className="p-2 text-left">Designação</th><th className="p-2 text-right">Qtd.</th><th className="p-2">Un.</th><th className="p-2 text-right">PU s/ IVA (€)</th><th className="p-2 text-right">Total s/ IVA</th></tr>
                      </thead>
                      <tbody>
                        {chiffrageResult.lines.map((l, i) => (
                          <tr key={i} className="border-t border-border" data-testid={`chiffrage-line-${i}`}>
                            <td className="p-2"><div className="font-medium">{l.designation}</div><div className="text-[11px] text-muted-foreground">{l.detail}</div></td>
                            <td className="p-2 text-right num">{l.qty}</td>
                            <td className="p-2 text-center text-xs">{l.unit}</td>
                            <td className="p-2 text-right">
                              <Input type="number" value={l.pu} onChange={(e) => updateChiffrageLinePu(i, e.target.value)}
                                     data-testid={`chiffrage-line-${i}-pu`} className="h-7 w-24 text-right num ml-auto" />
                            </td>
                            <td className="p-2 text-right num font-semibold">{l.total.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex flex-wrap justify-end gap-4 text-sm">
                    <span>Total s/ IVA: <b className="num">{chiffrageResult.totals.ht.toFixed(2)} €</b></span>
                    <span>+ Margem {chiffrageResult.totals.margin_pct}% : <b className="num">{chiffrageResult.totals.ht_with_margin.toFixed(2)} €</b></span>
                    <span>c/ IVA: <b className="num text-primary">{chiffrageResult.totals.ttc.toFixed(2)} €</b></span>
                  </div>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setChiffrageDialog(null); setChiffrageResult(null); }} className="rounded-sm">Fechar</Button>
            <Button onClick={addChiffrageToDevis} disabled={!chiffrageResult} data-testid="chiffrage-add-devis" className="rounded-sm gap-2">
              <ArrowRight className="h-4 w-4" /> Adicionar ao orçamento
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>


      {/* CHIFFRAGE DE PAGE — récapitulatif multi-postes */}
      <Dialog open={!!pageChiffrage} onOpenChange={(o) => { if (!o) setPageChiffrage(null); }}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" overlayClassName="z-[70]" data-testid="page-chiffrage-dialog">
          <DialogHeader>
            <DialogTitle>Orçamentação da página — {pageChiffrage?.count} artigo(s)</DialogTitle>
            <DialogDescription>
              Estimativa de todas as medições com um artigo definido, com os seus preços/rácios guardados.
            </DialogDescription>
          </DialogHeader>
          {pageChiffrage && (
            <div className="space-y-2 max-h-[55vh] overflow-auto">
              {pageChiffrage.items.map((it) => (
                <div key={it.measurement_id} className="rounded border border-border p-2" data-testid={`page-chiffrage-item-${it.measurement_id}`}>
                  <div className="flex justify-between text-sm font-medium">
                    <span>{it.label || it.label} <span className="text-muted-foreground">· {it.label !== it.poste ? it.label : ""}</span></span>
                    <span className="num">{it.totals.ht_with_margin.toFixed(2)} € s/ IVA</span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">{it.quantity} {it.unit} — {it.lines.length} lignes</div>
                </div>
              ))}
              {pageChiffrage.skipped > 0 && (
                <p className="text-[11px] text-muted-foreground">{pageChiffrage.skipped} medição(ões) ignorada(s) (sem artigo).</p>
              )}
              <div className="flex justify-end gap-4 text-sm font-semibold border-t border-border pt-2">
                <span>Total s/ IVA: <span className="num">{pageChiffrage.totals.ht_with_margin.toFixed(2)} €</span></span>
                <span>c/ IVA: <span className="num text-primary">{pageChiffrage.totals.ttc.toFixed(2)} €</span></span>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPageChiffrage(null)} className="rounded-sm">Fechar</Button>
            <Button onClick={addPageChiffrageToDevis} data-testid="page-chiffrage-add-devis" className="rounded-sm gap-2">
              <ArrowRight className="h-4 w-4" /> Adicionar tudo ao orçamento
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* BIBLIOTHÈQUE DE PRIX & RATIOS */}
      <Dialog open={priceLibOpen} onOpenChange={setPriceLibOpen}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" overlayClassName="z-[70]" data-testid="price-lib-dialog">
          <DialogHeader>
            <DialogTitle>A minha biblioteca — preços e rácios</DialogTitle>
            <DialogDescription>
              Guarde os seus preços unitários e os seus rácios de composição: pré-preenchem automaticamente cada orçamentação.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-3 rounded-sm border border-border bg-muted/30 p-2 mb-2">
            <Label className="text-xs flex-1">Pé-direito por omissão da obra (m)
              <span className="block text-[10px] text-muted-foreground font-normal">Utilizado pelas predefinições «pintura de paredes» e «parede líquida m²»</span>
            </Label>
            <Input type="number" step="0.05" value={priceLib.default_wall_height ?? ""}
                   onChange={(e) => setPriceLib((lib) => ({ ...lib, default_wall_height: e.target.value }))}
                   data-testid="price-lib-default-height" className="h-8 w-24 text-right num" />
          </div>
          <div className="flex gap-2 mb-2">
            <Button size="sm" variant={priceLibTab === "prices" ? "default" : "outline"}
                    onClick={() => setPriceLibTab("prices")} data-testid="price-lib-tab-prices" className="rounded-sm">Preços unitários</Button>
            <Button size="sm" variant={priceLibTab === "ratios" ? "default" : "outline"}
                    onClick={() => setPriceLibTab("ratios")} data-testid="price-lib-tab-ratios" className="rounded-sm">Rácios</Button>
          </div>
          <div className="grid grid-cols-2 gap-2 max-h-[50vh] overflow-auto pr-1">
            {(priceLib[priceLibTab] || []).map((r) => (
              <div key={r.key} className="flex items-center gap-2">
                <label className="flex-1 text-[11px] text-muted-foreground truncate" title={r.label}>{r.label}</label>
                <Input type="number" step="any" value={r.value}
                       onChange={(e) => setPriceLibValue(priceLibTab, r.key, e.target.value)}
                       data-testid={`price-lib-${priceLibTab}-${r.key}`}
                       className="h-7 w-24 text-right num" />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPriceLibOpen(false)} className="rounded-sm">Cancelar</Button>
            <Button onClick={savePriceLib} disabled={priceLibSaving} data-testid="price-lib-save" className="rounded-sm gap-2">
              <Save className="h-4 w-4" /> {priceLibSaving ? "A guardar…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* PRESET PIÈCE — sol + plinthes + peinture murs + plafond en un clic */}
      <Dialog open={roomPresetOpen} onOpenChange={(o) => { if (!o) { setRoomPresetOpen(false); setRoomPresetResult(null); } }}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" overlayClassName="z-[70]" data-testid="room-preset-dialog">
          <DialogHeader>
            <DialogTitle>Predefinição de divisão — orçamentação num clique</DialogTitle>
            <DialogDescription>
              Indique a área, o perímetro e a altura: pavimento, rodapés, pintura de paredes e teto são orçamentados automaticamente com os seus preços/rácios. A altura por omissão ({ceDefaultHeight} m) é utilizada se ficar vazia.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="grid gap-1">
                <Label className="text-xs">Área (m²)</Label>
                <Input type="number" step="0.01" value={roomPresetIn.area_m2} data-testid="preset-area"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, area_m2: e.target.value }))} className="h-9" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Perímetro (m)</Label>
                <Input type="number" step="0.01" value={roomPresetIn.perimeter_m} data-testid="preset-perimeter"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, perimeter_m: e.target.value }))} className="h-9" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Altura (m)</Label>
                <Input type="number" step="0.05" value={roomPresetIn.height_m} data-testid="preset-height"
                       placeholder={String(ceDefaultHeight)}
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, height_m: e.target.value }))} className="h-9" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Dedução de portas (m)</Label>
                <Input type="number" step="0.01" value={roomPresetIn.door_deduction_m} data-testid="preset-door-deduction"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, door_deduction_m: e.target.value }))} className="h-9" />
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-4">
              <label className="flex items-center gap-2 text-xs" data-testid="preset-inc-sol">
                <input type="checkbox" checked={roomPresetIn.sol} onChange={(e) => setRoomPresetIn((s) => ({ ...s, sol: e.target.checked }))} /> Pavimento
              </label>
              <select value={roomPresetIn.sol_poste} disabled={!roomPresetIn.sol} data-testid="preset-sol-poste"
                      onChange={(e) => setRoomPresetIn((s) => ({ ...s, sol_poste: e.target.value }))}
                      className="h-8 rounded-md border border-border bg-background px-2 text-xs">
                <option value="carrelage">Revestimento cerâmico</option>
                <option value="parquet">Soalho</option>
                <option value="chape">Betonilha</option>
              </select>
              <label className="flex items-center gap-2 text-xs" data-testid="preset-inc-plinthes">
                <input type="checkbox" checked={roomPresetIn.plinthes} onChange={(e) => setRoomPresetIn((s) => ({ ...s, plinthes: e.target.checked }))} /> Rodapés
              </label>
              <label className="flex items-center gap-2 text-xs" data-testid="preset-inc-peinture">
                <input type="checkbox" checked={roomPresetIn.peinture_murs} onChange={(e) => setRoomPresetIn((s) => ({ ...s, peinture_murs: e.target.checked }))} /> Pintura de paredes
              </label>
              <label className="flex items-center gap-2 text-xs" data-testid="preset-inc-plafond">
                <input type="checkbox" checked={roomPresetIn.plafond} onChange={(e) => setRoomPresetIn((s) => ({ ...s, plafond: e.target.checked }))} /> Teto
              </label>
              <select value={roomPresetIn.plafond_poste} disabled={!roomPresetIn.plafond} data-testid="preset-plafond-poste"
                      onChange={(e) => setRoomPresetIn((s) => ({ ...s, plafond_poste: e.target.value }))}
                      className="h-8 rounded-md border border-border bg-background px-2 text-xs">
                <option value="peinture">Pintura de teto</option>
                <option value="plafond">Teto em pladur</option>
              </select>
              <div className="grid gap-1">
                <Label className="text-xs">Demãos de tinta</Label>
                <Input type="number" min={1} value={roomPresetIn.couches} data-testid="preset-couches"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, couches: e.target.value }))} className="h-8 w-20" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Margem (%)</Label>
                <Input type="number" value={roomPresetIn.margin_pct} data-testid="preset-margin"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, margin_pct: e.target.value }))} className="h-8 w-20" />
              </div>
              <Button onClick={runRoomPreset} disabled={roomPresetLoading} data-testid="preset-run" className="h-9 rounded-sm gap-2">
                <Calculator className="h-4 w-4" /> {roomPresetLoading ? "Cálculo…" : "Orçamentar a divisão"}
              </Button>
            </div>

            {roomPresetResult && (
              <div className="space-y-2 max-h-[45vh] overflow-auto" data-testid="preset-result">
                {roomPresetResult.items.map((it, i) => (
                  <div key={i} className="rounded border border-border p-2" data-testid={`preset-item-${it.slot}`}>
                    <div className="flex justify-between text-sm font-medium">
                      <span>{it.slot} <span className="text-muted-foreground">· {it.label}</span></span>
                      <span className="num">{it.totals.ht_with_margin.toFixed(2)} € s/ IVA</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">{it.quantity} {it.unit} — {it.lines.length} lignes</div>
                  </div>
                ))}
                <div className="flex justify-end gap-4 text-sm font-semibold border-t border-border pt-2">
                  <span>Total s/ IVA: <span className="num">{roomPresetResult.totals.ht_with_margin.toFixed(2)} €</span></span>
                  <span>c/ IVA: <span className="num text-primary">{roomPresetResult.totals.ttc.toFixed(2)} €</span></span>
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setRoomPresetOpen(false); setRoomPresetResult(null); }} className="rounded-sm">Fechar</Button>
            <Button onClick={addRoomPresetToDevis} disabled={!roomPresetResult} data-testid="preset-add-devis" className="rounded-sm gap-2">
              <ArrowRight className="h-4 w-4" /> Adicionar tudo ao orçamento
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* MÉTRÉ COMPARÉ — versions d'un niveau */}
      <Dialog open={metreVerOpen} onOpenChange={setMetreVerOpen}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" data-testid="metre-versions-dialog">
          <DialogHeader>
            <DialogTitle>Medição comparada — versões do piso</DialogTitle>
            <DialogDescription>Fixe o estado da medição num instante T e depois compare duas versões (antes / depois da alteração).</DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2">
            <Input value={metreLabel} onChange={(e) => setMetreLabel(e.target.value)}
                   placeholder="Nome da versão (ex.: Antes da alteração do cliente)" data-testid="metre-version-label" className="h-9 flex-1" />
            <Button size="sm" onClick={snapshotMetre} data-testid="metre-snapshot-btn" className="rounded-sm gap-1"><Save className="h-4 w-4" /> Fixar</Button>
          </div>
          <div className="space-y-1.5 max-h-48 overflow-auto">
            {metreVersions.length === 0 && <p className="text-xs text-muted-foreground">Nenhuma versão guardada.</p>}
            {metreVersions.map((v) => (
              <div key={v.version_id} className={`flex items-center gap-2 rounded border p-2 text-sm ${metreSel.includes(v.version_id) ? "border-primary bg-primary/5" : "border-border"}`} data-testid={`metre-version-${v.version_id}`}>
                <input type="checkbox" checked={metreSel.includes(v.version_id)} onChange={() => toggleMetreSel(v.version_id)} data-testid={`metre-pick-${v.version_id}`} />
                <span className="flex-1">{v.label} <span className="text-[11px] text-muted-foreground">· {v.summary?.area_m2 || 0} m² · {v.summary?.ht || 0} € s/ IVA</span></span>
                <button onClick={() => deleteMetreVersion(v.version_id)} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            ))}
          </div>
          <Button variant="outline" onClick={runMetreCompare} disabled={metreSel.length !== 2} data-testid="metre-compare-btn" className="rounded-sm w-full">Comparar as 2 versões selecionadas</Button>
          {metreCompare && (
            <div className="rounded border border-border p-3 space-y-2" data-testid="metre-compare-result">
              <div className="flex justify-between text-sm font-medium">
                <span>{metreCompare.a.label} → {metreCompare.b.label}</span>
                <span className={metreCompare.delta.ht >= 0 ? "text-emerald-600" : "text-red-600"}>{metreCompare.delta.ht >= 0 ? "+" : ""}{metreCompare.delta.ht.toFixed(2)} € s/ IVA</span>
              </div>
              <div className="text-[11px] text-muted-foreground">Δ área {metreCompare.delta.area_m2} m² · Δ linear {metreCompare.delta.length_ml} ml · Δ medições {metreCompare.delta.measures}</div>
              {metreCompare.by_poste.length > 0 && (
                <table className="w-full text-xs">
                  <thead className="text-muted-foreground"><tr><th className="text-left">Artigo</th><th className="text-right">Qtd. A→B</th><th className="text-right">Δ s/ IVA</th></tr></thead>
                  <tbody>
                    {metreCompare.by_poste.map((p) => (
                      <tr key={p.poste} className="border-t border-border">
                        <td className="py-1">{p.poste}</td>
                        <td className="text-right num">{p.qty_a} → {p.qty_b}</td>
                        <td className={`text-right num ${p.ht_delta >= 0 ? "text-emerald-600" : "text-red-600"}`}>{p.ht_delta >= 0 ? "+" : ""}{p.ht_delta.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* LABEL DIALOG (snapshot naming) */}
      <Dialog open={!!labelDialog} onOpenChange={(o) => { if (!o) setLabelDialog(null); }}>
        <DialogContent className="rounded-sm" data-testid="label-dialog">
          <DialogHeader>
            <DialogTitle>Nomear esta versão</DialogTitle>
            <DialogDescription>
              Dê a este snapshot um nome significativo (ex: «Versão cliente 12/02», «Antes modificação divisória»).
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="snap-label">Nome do snapshot</Label>
            <Input id="snap-label" value={labelValue}
                   onChange={(e) => setLabelValue(e.target.value)}
                   placeholder="Versão cliente · 12/02"
                   maxLength={80} autoFocus
                   data-testid="label-input" className="rounded-sm h-11" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLabelDialog(null)} className="rounded-sm">
              Cancelar
            </Button>
            <Button onClick={saveSnapshotLabel} data-testid="label-save-btn"
                    className="rounded-sm hover:bg-orange-600 hover:text-white">
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* COMPARAISON DE RÉGLAGES (Maison vs Immeuble) */}
      <Dialog open={compareOpen} onOpenChange={setCompareOpen}>
        <DialogContent className="sm:max-w-lg" data-testid="beton-compare-dialog">
          <DialogHeader>
            <DialogTitle>Comparar as definições betão</DialogTitle>
            <DialogDescription>Medições da planta atual segundo cada tipo de obra — para ajudar na escolha.</DialogDescription>
          </DialogHeader>
          {compareBusy && <p className="text-sm text-primary animate-pulse">Cálculo em curso…</p>}
          {!compareBusy && compareData && (
            <table className="w-full text-xs" data-testid="beton-compare-table">
              <thead className="bg-muted/60"><tr>
                <th className="text-left px-2 py-1">Artigo</th>
                {compareData.map((c) => <th key={c.name} className="text-right px-2 py-1">{c.name}</th>)}
              </tr></thead>
              <tbody>
                {[["Betão total", "beton_total_m3", "m³"], ["Aços", "acier_total_kg", "kg"],
                  ["Pilares (betão)", "beton_poteaux_m3", "m³"], ["Vigas (betão)", "beton_poutres_m3", "m³"],
                  ["Lajes (betão)", "beton_dalles_m3", "m³"], ["Paredes (betão)", "beton_voiles_m3", "m³"]].map(([lbl, k, u]) => (
                  <tr key={k} className="border-t border-border">
                    <td className="px-2 py-1 text-muted-foreground">{lbl}</td>
                    {compareData.map((c) => <td key={c.name} className="px-2 py-1 num text-right">{c.d?.[k] ?? 0} {u}</td>)}
                  </tr>
                ))}
                {(betonPriceM3 > 0 || acierPriceKg > 0) && (
                  <tr className="border-t border-border font-semibold">
                    <td className="px-2 py-1">Custo de materiais</td>
                    {compareData.map((c) => (
                      <td key={c.name} className="px-2 py-1 num text-right text-emerald-700">
                        {Math.round((c.d?.beton_total_m3 || 0) * (c.beton_price_m3 || betonPriceM3) + (c.d?.acier_total_kg || 0) * (c.acier_price_kg || acierPriceKg)).toLocaleString("pt-PT")} €
                      </td>
                    ))}
                  </tr>
                )}
                {(betonPriceM3 > 0 || acierPriceKg > 0 || laborPriceM3 > 0) && (
                  <tr className="border-t border-border font-bold">
                    <td className="px-2 py-1">Preço de venda estimado</td>
                    {compareData.map((c) => {
                      const bp = c.beton_price_m3 || betonPriceM3, ap = c.acier_price_kg || acierPriceKg;
                      const lp = c.labor_price_m3 || laborPriceM3, mg = c.margin_pct || marginPct;
                      const pv = (((c.d?.beton_total_m3 || 0) * bp + (c.d?.acier_total_kg || 0) * ap) + (c.d?.beton_total_m3 || 0) * lp) * (1 + mg / 100);
                      return <td key={c.name} className="px-2 py-1 num text-right text-primary">{Math.round(pv).toLocaleString("pt-PT")} €</td>;
                    })}
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </DialogContent>
      </Dialog>

      {/* ASSISTANT IA — guider / corriger la détection en langage naturel */}
      <Dialog open={aiChatOpen} onOpenChange={setAiChatOpen}>
        <DialogContent className="sm:max-w-lg" data-testid="ai-assistant-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Bot className="h-5 w-5 text-primary" /> Assistente IA — corrigir a planta</DialogTitle>
            <DialogDescription>
              Descreva o que a IA deve corrigir ou adicionar. Ex: «faltam 2 pilares em baixo à direita», «as sapatas têm 1,2×1,2 m», «ignora as linhas de cota», «adiciona uma viga entre P3 e P4».
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-72 overflow-auto space-y-2 rounded-sm border border-border p-2 bg-muted/30" data-testid="ai-assistant-messages">
            {aiMessages.length === 0 && (
              <p className="text-xs text-muted-foreground">Nenhuma troca por enquanto. Dê a sua primeira instrução abaixo.</p>
            )}
            {aiMessages.map((m, i) => (
              <div key={i} className={`text-xs rounded-sm px-2 py-1.5 ${m.role === "user" ? "bg-primary/10 ml-6" : m.ok === false ? "bg-destructive/10 mr-6" : "bg-background border border-border mr-6"}`}>
                <span className="font-semibold">{m.role === "user" ? "Você" : "IA"} : </span>{m.text}
              </div>
            ))}
            {aiChatBusy && <p className="text-xs text-primary animate-pulse">A IA analisa a planta…</p>}
          </div>
          <div className="flex items-end gap-2">
            <Textarea value={aiInput} onChange={(e) => setAiInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAiInstruction(); } }}
                      placeholder="A sua indicação para a IA…" rows={2}
                      data-testid="ai-assistant-input" className="rounded-sm text-sm resize-none" />
            <Button onClick={sendAiInstruction} disabled={aiChatBusy || !aiInput.trim()}
                    data-testid="ai-assistant-send" className="rounded-sm gap-1 shrink-0">
              <ArrowRight className="h-4 w-4" /> Enviar
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* QUOTE / RENDER 3D / ESTIMATE / MULTI-PLAN dialogs — extracted subcomponents */}
      <QuoteDialog
        open={quoteDialog} onOpenChange={setQuoteDialog}
        quoteMode={quoteMode} setQuoteMode={setQuoteMode}
        templates={templates} applyTemplate={applyTemplate} deleteTemplate={deleteTemplate}
        quoteFinish={quoteFinish} setQuoteFinish={setQuoteFinish}
        quoteFloor={quoteFloor} setQuoteFloor={setQuoteFloor}
        quoteSubject={quoteSubject} setQuoteSubject={setQuoteSubject}
        quoteIntro={quoteIntro} setQuoteIntro={setQuoteIntro}
        quoteClientEmail={quoteClientEmail} setQuoteClientEmail={setQuoteClientEmail}
        quoteClientName={quoteClientName} setQuoteClientName={setQuoteClientName}
        quoteClientAddress={quoteClientAddress} setQuoteClientAddress={setQuoteClientAddress}
        quoteMessage={quoteMessage} setQuoteMessage={setQuoteMessage}
        quoteIncludeTva={quoteIncludeTva} setQuoteIncludeTva={setQuoteIncludeTva}
        quoteAttachVideo={quoteAttachVideo} setQuoteAttachVideo={setQuoteAttachVideo}
        latestVideo={latestVideo}
        quoteSends={quoteSends} createSignatureLink={createSignatureLink}
        templateName={templateName} setTemplateName={setTemplateName}
        templateShared={templateShared} setTemplateShared={setTemplateShared}
        saveTemplate={saveTemplate}
        quoteBusy={quoteBusy} downloadQuotePdf={downloadQuotePdf} sendQuotePdf={sendQuotePdf}
      />

      <Render3dDialog
        open={render3dDialog} onOpenChange={setRender3dDialog}
        render3dMode={render3dMode} setRender3dMode={setRender3dMode}
        plan={plan} detectedWalls={detectedWalls} pageIndex={pageIndex}
        structure={structure} dalleEp={dalleEp} voileEp={voileEp} wallHeight={wallHeight}
        poutreL={poutreL} poutreH={poutreH}
        onAttach3d={(png) => { setPlan3dSnapshot(png); toast.success("Vista 3D anexa — será adicionada ao próximo orçamento gerado a partir desta planta"); }}
        render3dStyle={render3dStyle} setRender3dStyle={setRender3dStyle}
        render3dFurniture={render3dFurniture} setRender3dFurniture={setRender3dFurniture}
        render3dBusy={render3dBusy} render3dImg={render3dImg}
        runRender3d={runRender3d} downloadRender3d={downloadRender3d}
        render3dHistory={render3dHistory} openRender3dHistory={openRender3dHistory}
        videoBusy={videoBusy} videoUrl={videoUrl}
        runRenderVideo={runRenderVideo} downloadVideo={downloadVideo}
        videoHistory={videoHistory} openVideoHistory={openVideoHistory}
        videoAddWatermark={videoAddWatermark} setVideoAddWatermark={setVideoAddWatermark}
        videoAddMusic={videoAddMusic} setVideoAddMusic={setVideoAddMusic}
        credits3d={credits3d} creditPaywall={creditPaywall} setCreditPaywall={setCreditPaywall}
        buyCredit={buyCredit} onInteractiveMode={selectInteractiveMode}
      />

      <EstimateDialog
        open={estimateDialog} onOpenChange={setEstimateDialog}
        estProjectType={estProjectType} setEstProjectType={setEstProjectType}
        estFinishLevel={estFinishLevel} setEstFinishLevel={setEstFinishLevel}
        estimateBusy={estimateBusy} estimateResult={estimateResult}
        runEstimation={runEstimation} proceedToDevis={proceedToDevis}
      />

      <MultiPlanDialog
        open={multiDialog} onOpenChange={setMultiDialog}
        multiProjectName={multiProjectName} setMultiProjectName={setMultiProjectName}
        multiSelected={multiSelected} setMultiSelected={setMultiSelected}
        allPlans={allPlans} plan={plan}
        quoteFinish={quoteFinish} quoteFloor={quoteFloor}
        multiBusy={multiBusy} downloadMultiQuote={downloadMultiQuote}
        downloadMultiMetre={downloadMultiMetre}
        subcontractSel={subcontractSel} setSubcontractSel={setSubcontractSel}
        consolidatedBusy={consolidatedBusy} createConsolidatedQuote={createConsolidatedQuote}
        linkFerraillage={linkFerraillage}
      />

      {/* S3.1 — Dialog partilhado para pré-visualização ampliada de plantas recentes */}
      {planZoomDialog}

    </div>
  );
}

function ToolButton({ icon: Icon, label, active, onClick, testId, disabled }) {
  return (
    <Button size="sm" variant={active ? "default" : "outline"} onClick={onClick}
            disabled={disabled} data-testid={testId}
            className="rounded-sm gap-1 h-8">
      <Icon className="h-3 w-3" /> {label}
    </Button>
  );
}

function MatCard({ label, lines }) {
  return (
    <div className="border border-border p-3 rounded-sm">
      <p className="overline mb-2">{label}</p>
      {lines.map(([k, v], i) => (
        <div key={i} className={`flex justify-between text-xs num ${i === lines.length - 1 ? "font-bold text-primary mt-1" : ""}`}>
          <span>{k}</span><span>{v}</span>
        </div>
      ))}
    </div>
  );
}

/** Calcule un diff compact entre 2 snapshots (précédent → actuel). */
function computeSnapshotDiff(prev, curr) {
  if (!prev) return { summary: "Estado inicial" };
  const byRoomIdPrev = new Map((prev.rooms || []).map(r => [r.room_id, r]));
  const byRoomIdCurr = new Map((curr.rooms || []).map(r => [r.room_id, r]));
  const added = [];
  const removed = [];
  const modified = [];
  for (const [id, r] of byRoomIdCurr) {
    if (!byRoomIdPrev.has(id)) added.push(r.name);
    else {
      const p = byRoomIdPrev.get(id);
      if (Math.abs((p.surface_m2 || 0) - (r.surface_m2 || 0)) > 0.01) {
        modified.push(`${r.name} ${p.surface_m2}→${r.surface_m2} m²`);
      }
    }
  }
  for (const [id, r] of byRoomIdPrev) {
    if (!byRoomIdCurr.has(id)) removed.push(r.name);
  }
  const calibPrev = Object.keys(prev.calibrations || {}).length;
  const calibCurr = Object.keys(curr.calibrations || {}).length;
  const calibDelta = calibCurr - calibPrev;
  const parts = [];
  if (added.length) parts.push(`+${added.length} (${added.slice(0, 2).join(", ")}${added.length > 2 ? "…" : ""})`);
  if (removed.length) parts.push(`−${removed.length} (${removed.slice(0, 2).join(", ")}${removed.length > 2 ? "…" : ""})`);
  if (modified.length) parts.push(`~${modified.length} (${modified[0]}${modified.length > 1 ? "…" : ""})`);
  if (calibDelta > 0) parts.push(`+${calibDelta} calibration`);
  return { summary: parts.join(" · ") || "Sem alterações" };
}

