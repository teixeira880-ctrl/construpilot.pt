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

const LEVEL_SUGGESTIONS = ["Fondations", "RDC", "R+1", "R+2", "R+3", "Combles", "Sous-sol"];


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
  if (Array.isArray(detail)) return detail.map((item) => item?.msg || "Donnée invalide").join(" · ");
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
      session.error = errorMessage(error, "Échec de la sauvegarde");
      toast.error(`Annotations de la page ${session.pageIndex + 1} non enregistrées : ${session.error}`);
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
    if (!session) throw new Error("Attendez le chargement de la page");
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
    if (!label) return toast.error("Donnez un nom à l'ouvrage");
    if (!pu || pu <= 0) return toast.error("Prix unitaire invalide");
    try {
      await api.post("/takeoffs/corps-etat/custom", { label, unit: cpForm.unit, pu });
      toast.success(`Ouvrage « ${label} » ajouté au catalogue`);
      setCpForm({ label: "", unit: "m2", pu: "" });
      await loadCustomPostes();
      await refreshPosteCatalog();
    } catch (e) { toast.error(e?.response?.data?.detail || "Création impossible"); }
  };
  const deleteCustomPoste = async (key) => {
    try {
      await api.delete(`/takeoffs/corps-etat/custom/${key}`);
      await loadCustomPostes();
      await refreshPosteCatalog();
      toast.success("Ouvrage supprimé");
    } catch { toast.error("Suppression impossible"); }
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
    if (!(q > 0)) return toast.error("Quantité nulle sur cette mesure");
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
    } catch (e) { toast.error(e?.response?.data?.detail || "Chiffrage impossible"); }
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
    toast.success(`${chiffrageResult.lines.length} ligne(s) « ${cat} » ajoutées au devis (${chiffrageResult.totals.ht_with_margin} € HT)`, { duration: 6000 });
    setChiffrageDialog(null); setChiffrageResult(null);
  };

  // Chiffrer la page : propose un poste par cote (auto), l'utilisateur valide, puis chiffrage
  const chiffrerPage = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/corps-etat/suggest-postes`,
        { page_index: pageIndex });
      if (!data.rows?.length) return toast.error("Aucune cote chiffrable sur cette page (tracez des surfaces ou des murs avec hauteur).");
      setAutoPosteDialog({ rows: data.rows.map((r) => ({ ...r, poste: r.suggested_poste })) });
    } catch (e) { toast.error(e?.response?.data?.detail || "Analyse des cotes impossible"); }
  };

  const confirmAutoPoste = async () => {
    if (!autoPosteDialog?.rows?.length || !plan?.plan_id) return;
    try {
      await api.post(`/takeoffs/${plan.plan_id}/corps-etat/assign-postes`,
        { assignments: autoPosteDialog.rows.map((r) => ({ measurement_id: r.measurement_id, poste: r.poste })) });
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/corps-etat/estimate-page`,
        { page_index: pageIndex, margin_pct: Number(chiffrageMargin) || 0 });
      setAutoPosteDialog(null);
      if (!data.count) return toast.error("Chiffrage vide : vérifiez les postes choisis.");
      setPageChiffrage(data);
      toast.success(`${data.count} cote(s) chiffrée(s)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Chiffrage impossible"); }
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
    toast.success(`${n} ligne(s) ajoutées au devis (${pageChiffrage.totals.ht_with_margin} € HT) — cliquez « Créer un devis »`, { duration: 7000 });
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
      toast.success("Bibliothèque enregistrée — appliquée à chaque chiffrage");
      setPriceLibOpen(false);
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement impossible"); }
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
    if (!(area > 0)) return toast.error("Renseignez l'aire de la pièce (m²)");
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
      if (!data.count) return toast.error("Aucun poste à chiffrer (vérifiez les cases et les dimensions)");
      setRoomPresetResult(data);
    } catch (e) { toast.error(errorMessage(e, "Calcul du preset impossible")); }
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
    toast.success(`${n} ligne(s) ajoutées au devis (${roomPresetResult.totals.ht_with_margin} € HT) — cliquez « Créer un devis »`, { duration: 7000 });
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
    if (!chiffragePoste) return toast.error("Choisissez d'abord un poste");
    const name = saveOuvrageName.trim();
    if (!name) return toast.error("Donnez un nom à l'ouvrage");
    try {
      await api.post("/takeoffs/corps-etat/ouvrages", {
        name, poste: chiffragePoste,
        params: currentChiffrageOpts(), margin_pct: Number(chiffrageMargin) || 0,
        shared: saveOuvrageShared });
      toast.success(`Ouvrage « ${name} » enregistré${saveOuvrageShared ? " et partagé avec l'équipe" : ""} — réutilisable sur tous vos chantiers`);
      setSaveOuvrageName("");
      loadOuvrages();
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement impossible"); }
  };

  const applyOuvrage = (ov) => {
    setChiffragePoste(ov.poste);
    setChiffrageMargin(ov.margin_pct ?? 10);
    setChiffrageOpts((o) => ({ ...o, ...(ov.params || {}) }));
    toast.success(`Ouvrage « ${ov.name} » appliqué — cliquez « Calculer »`);
  };

  const deleteOuvrage = async (ouvrage_id) => {
    if (!(await confirmDialog({ title: "Supprimer cet ouvrage ?", description: "Cette composition enregistrée sera retirée de votre bibliothèque." }))) return;
    try { await api.delete(`/takeoffs/corps-etat/ouvrages/${ouvrage_id}`); loadOuvrages(); toast.success("Ouvrage supprimé"); }
    catch { toast.error("Suppression impossible"); }
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
      setGroupImport((g) => ({ ...g, enabled: true, mode: "new", name: g.name || "Projet multi-niveaux" }));
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
      if (!data || typeof data !== "object") throw new Error("Réponse de page invalide");
      hydrateAnnotations(planRef.current?.annotations?.[String(pageIndex)]);
      setPageData(data); setLoadedPageKey(pageKey);
    }).catch((error) => {
      if (!cancelled && currentPageKeyRef.current === pageKey) {
        setPageError(errorMessage(error, "Impossible de charger cette page"));
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
    try { await saveAnnotations(); toast.success("Annotations enregistrées"); }
    catch (error) { toast.error(errorMessage(error, "Échec de l'enregistrement")); }
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
        if (ids.length) { setObjectPanelOpen(true); toast.message(`${ids.length} poste(s) en écart mis en évidence sur le plan`, { duration: 6000 }); }
      }
    }).catch(() => toast.error("Impossible d'ouvrir ce plan"));
  }, []);

  const savePlanDefaults = async (next) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/defaults`, next);
      setPlanDefaults(next);
      toast.success(`Réglages : mur ${next.ceiling_h_m} m · plancher ${(next.floor_thickness_m * 100).toFixed(0)} cm`);
    } catch { toast.error("Sauvegarde impossible"); }
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
    if (file.size > 20 * 1024 * 1024) { toast.error(`« ${displayName || file.name} » trop volumineux (>20 Mo)`); return null; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (cadUnit) fd.append("cad_unit", cadUnit);
      if (deskewEnabled) fd.append("deskew", "true");
      if (displayName && displayName.trim()) fd.append("display_name", displayName.trim());
      const data = await uploadPlan(fd, { onStatus: (_j, sec) => sec >= 20 && sec % 10 === 0 && toast.message(`Analyse du plan en cours… ${sec} s (DWG et PDF multi-pages : plusieurs minutes possibles)`, { id: "plan-upload-progress" }) });
      if (chantierId && data?.plan_id) api.post(`/chantiers/${chantierId}/attach`, { kind: "plan", ref_id: data.plan_id }).then(() => toast.success("Plan rattaché au dossier chantier")).catch(() => toast.error("Plan importé, mais rattachement au dossier impossible"));
      setPlan(data);
      setPageIndex(0);
      const kind = data.kind === "dxf" ? "DXF" : data.kind === "pdf" ? "PDF" : "image";
      toast.success(`${kind} chargé (${data.page_count} page${data.page_count > 1 ? "s" : ""})`);
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
        || (!e?.response ? "Réseau indisponible ou fichier trop lourd — vérifiez votre connexion et réessayez"
                         : "Import impossible");
      toast.error(`« ${displayName || file.name} » — ${msg}`);
      return null;
    } finally { setUploading(false); }
  };

  // Détection auto du niveau depuis le nom du fichier (RDC, R+1, sous-sol…)
  const detectLevel = (fname, idx) => {
    const n = (fname || "").toLowerCase();
    if (/combl|toitur/.test(n)) return "Combles";
    if (/fondation|semelle/.test(n)) return "Fondations";
    if (/sous[\s_-]?sol|\bss\b|\bs\.?sol\b/.test(n)) return "Sous-sol";
    if (/\b(rdc|rez)\b|rez[\s_-]?de[\s_-]?chauss|\br0\b/.test(n)) return "RDC";
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
          if (!entries.length) toast.error(`Aucun plan supporté dans ${f.name}`);
        } catch { toast.error(`ZIP illisible : ${f.name}`); }
      } else if (SUPPORTED_RE.test(f.name)) {
        expanded.push(f);
      }
    }
    if (expanded.length) queueFiles(expanded);
    else toast.error("Aucun fichier de plan reconnu");
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
          const newLevels = uploaded.map((u, i) => ({ plan_id: u.plan_id, level_label: u.level_label || LEVEL_SUGGESTIONS[prevLevels.length + i] || `Niveau ${prevLevels.length + i + 1}` }));
          await api.put(`/takeoffs/multilevel/groups/${groupImport.groupId}`, {
            name: existing?.name || "Projet", chantier_id: existing?.chantier_id || null,
            levels: [...prevLevels, ...newLevels],
          });
          createdGroup = { group_id: groupImport.groupId, name: existing?.name || "Projet" };
        } else if (groupImport.name.trim()) {
          const { data } = await api.post("/takeoffs/multilevel/groups", {
            name: groupImport.name.trim(),
            levels: uploaded.map((u, i) => ({ plan_id: u.plan_id, level_label: u.level_label || LEVEL_SUGGESTIONS[i] || `Niveau ${i + 1}` })),
          });
          const gid = data?.group?.group_id;
          if (gid) createdGroup = { group_id: gid, name: groupImport.name.trim() };
        }
      } catch (e) { toast.error("Plans importés, mais mise à jour du projet multi-niveaux impossible"); }
    }
    setPendingFiles((items) => items.filter((item) => !completed.has(item.id)));
    if (completed.size === pendingFiles.length) setGroupImport({ enabled: false, mode: "new", name: "", groupId: "" });
    else if (createdGroup) setGroupImport((g) => ({ ...g, mode: "existing", groupId: createdGroup.group_id }));
    loadAllPlans();
    loadPlanGroups();
    if (createdGroup) {
      toast.success(`Projet « ${createdGroup.name} » — ${uploaded.length} niveau${uploaded.length > 1 ? "x" : ""} ajouté${uploaded.length > 1 ? "s" : ""}`);
      openGroupConsolidated(createdGroup);
    } else if (ok > 1) toast.success(`${ok} plans importés`);
    else if (ok === 0) toast.error("Aucun plan importé — les fichiers restent disponibles pour réessayer");
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
        toast.info("Aucun mur à proximité (cliquez plus près)");
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
        if (!currentCalib) return toast.error("Calibrez d'abord le plan");
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
          toast.error("Aucune pièce à proximité — tracez d'abord une pièce");
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
          label: `Compteur ${nb + 1}`,
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
      const text = window.prompt("Note (max 60 caractères) :", "");
      if (text === null) return;
      const trimmed = (text || "").slice(0, 60);
      setAnnotations({
        ...annotations,
        notes: [...annotations.notes, {
          id: `nt_${Date.now()}`, x: pt[0], y: pt[1], text: trimmed || "Note"
        }],
      });
      toast.success("Note ajoutée");
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
        toast.success(`Angle : ${deg.toFixed(1)}° · pente ${(Math.tan(deg * Math.PI / 180) * 12).toFixed(1)}/12`);
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
    if (!finitePositive(dist)) return toast.error("Distance invalide");
    if (!plan?.plan_id || points.length !== 2 || Math.hypot(points[1][0] - points[0][0], points[1][1] - points[0][1]) <= 0) {
      return toast.error("Sélectionnez deux points distincts sur le plan");
    }
    try {
      await api.post(`/takeoffs/${plan.plan_id}/calibrate`, {
        page_index: pageIndex, p1: points[0], p2: points[1],
        real_distance_m: dist, method: "two_points",
      });
      toast.success(`Calibration : ${dist} m sur ${num(Math.hypot(points[1][0] - points[0][0], points[1][1] - points[0][1]), 0)} px`);
      setCalibDialog(false);
      setCalibDist("");
      setPoints([]);
      await refreshPlan();
      setTool(TOOLS.SELECT);
    } catch (e) { toast.error(e?.response?.data?.detail || "Calibration échouée"); }
  };

  const submitOpening = async () => {
    if (!openingsDialog) return;
    const w = decimalNumber(pendingOpening.width_m);
    const h = decimalNumber(pendingOpening.height_m);
    if (!finitePositive(w) || !finitePositive(h)) return toast.error("Dimensions invalides");
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
        `${pendingOpening.kind === "porte" ? "Porte" : pendingOpening.kind === "baie" ? "Baie" : "Fenêtre"} `
        + `${w}×${h} m ajoutée à ${openingsDialog.room_name}`
      );
      setOpeningsDialog(null);
      setPoints([]);
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Ajout impossible"); }
  };

  const deleteOpening = async (room_id, opening_id) => {
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/rooms/${room_id}/openings/${opening_id}`);
      toast.success("Ouverture supprimée");
      await refreshPlan();
    } catch { toast.error("Suppression impossible"); }
  };

  // Couleur auto : chaque mesure reçoit une couleur différente de la palette
  const pickAutoColor = () => {
    const c = COUNTER_COLORS[autoColorIdx % COUNTER_COLORS.length];
    setAutoColorIdx((i) => i + 1);
    return c;
  };

  const finishPolyline = async (pts = points) => {
    if (pts.length < 2) return;
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polyline", points: pts, color: pickAutoColor(),
      });
      toast.success(`Longueur : ${data.length_m} m — mémorisée`);
      setPoints([]);
      setPanelFocus("measures"); setObjectPanelOpen(true);
      await refreshPlan();
    } catch (e) { toast.error("Mesure échouée"); }
  };

  const finishPitchSurface = () => {
    if (points.length < 3) return toast.error("Cliquez au moins 3 points");
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
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
    toast.success(`Toiture : ${real_area_m2.toFixed(1)} m² réels (à ${pitch}°)`);
  };

  // ============ VAGUE B — Handlers pour le Volet Objets ============

  const renameRoom = async (roomId, newName) => {
    if (!plan?.plan_id || !newName?.trim()) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/rooms/${roomId}`, { name: newName.trim() });
      await refreshPlan();
      toast.success("Pièce renommée");
    } catch { toast.error("Renommage impossible"); }
  };

  const attachPresetToRoom = async (roomId, presetId) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/rooms/${roomId}`, { preset_id: presetId });
      await refreshPlan();
      toast.success(presetId ? "Modèle attaché à la pièce" : "Modèle retiré");
    } catch (e) { toast.error(e?.response?.data?.detail || "Attachement impossible"); }
  };

  const deleteRoomFromPanel = async (roomId) => {
    if (!plan?.plan_id) return;
    if (!window.confirm("Supprimer cette pièce ?")) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/rooms/${roomId}`);
      await refreshPlan();
      toast.success("Pièce supprimée");
    } catch { toast.error("Suppression impossible"); }
  };

  const deleteMeasureFromPanel = async (measureId) => {
    if (!plan?.plan_id) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/measurements/${measureId}`);
      await refreshPlan();
      toast.success("Mesure supprimée");
    } catch { toast.error("Suppression impossible"); }
  };

  const clearMeasures = async () => {
    if (!plan?.plan_id) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/measurements?page_index=${pageIndex}`);
      await refreshPlan();
      toast.success("Mesures de la page effacées");
    } catch { toast.error("Effacement impossible"); }
  };

  // Iter66 — libellé personnalisé (ex. « murs parpaing », « murs en brique »)
  const renameMeasure = async (measureId, label) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/measurements/${measureId}`, { label });
      await refreshPlan();
      toast.success(label ? `Mesure renommée : ${label}` : "Libellé effacé");
    } catch { toast.error("Renommage impossible"); }
  };

  // Couleur personnalisable d'une cote (plancher, murs…)
  const colorMeasure = async (measureId, color) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/measurements/${measureId}`, { color });
      await refreshPlan();
    } catch { toast.error("Couleur non enregistrée"); }
  };

  // Export PDF du relevé des cotes (avec nom du projet)
  const downloadCotesPdf = async () => {
    if (!plan?.plan_id) return;
    try {
      const res = await api.get(`/takeoffs/${plan.plan_id}/cotes-pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cotes-${plan.filename || plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("PDF des cotes téléchargé");
    } catch { toast.error("Export PDF des cotes impossible"); }
  };

  // Iter68 — surface mesurée → pièce complète (1 clic)
  const convertMeasureToRoom = async (measureId) => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measurements/${measureId}/to-room`);
      toast.success(`Pièce créée : ${data.room.name} (${data.room.surface_m2} m²) — murs et volume calculés`, { duration: 6000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Conversion impossible"); }
  };

  // Iter68 — déduction (trémie, escalier…) de la pièce contenante
  const deductMeasure = async (measureId) => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measurements/${measureId}/deduct`);
      toast.success(`− ${data.deduction.area_m2} m² déduits de « ${data.room_name} » → surface nette ${data.surface_m2} m²`, { duration: 7000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Déduction impossible"); }
  };

  const removeDeduction = async (roomId, dedId) => {
    try {
      const { data } = await api.delete(`/takeoffs/${plan.plan_id}/rooms/${roomId}/deductions/${dedId}`);
      toast.success(`Déduction retirée — surface : ${data.surface_m2} m²`);
      await refreshPlan();
    } catch { toast.error("Suppression impossible"); }
  };

  // Iter68 — export Excel (pièces + mesures)
  const downloadXlsx = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/export-xlsx`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-${plan.plan_id}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Export Excel téléchargé");
    } catch (e) { toast.error(e.message || "Export Excel impossible"); }
  };

  // Iter69 — Étude Permis de Construire (gros œuvre : béton, aciers, isobrique)
  const [pcDialog, setPcDialog] = useState(false);
  const [structDialog, setStructDialog] = useState(false);
  const [pcBusy, setPcBusy] = useState(false);
  const runPcStudy = async (options = {}) => {
    setPcBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/pc-study`, options);
      toast.success("Étude lancée en arrière-plan. Tu peux changer de page.");
      return data;
    } catch (e) { toast.error(e?.response?.data?.detail || "Étude PC impossible"); }
    finally { setPcBusy(false); }
  };
  const downloadPcFile = async (fmt, start) => {
    try {
      const qs = start ? `?start=${start}` : "";
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/pc-study/${fmt}${qs}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `etude-pc-${plan.plan_id}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Étude PC ${fmt.toUpperCase()} téléchargée`);
    } catch (e) { toast.error(e.message || "Export impossible"); }
  };
  const comparePcSuppliers = (study) => {
    const t = study?.totals || {};
    const slabArea = Math.round((study?.inputs?.ground_floor_area_m2 || 0) +
                                (study?.inputs?.upper_floors_area_m2 || 0));
    const items = [
      { name: "Brique isobrique 20 cm", search: "brique isobrique 20 cm", quantity: t.briques_u || 0, unit: "u" },
      { name: "Acier HA fer à béton", search: "fer à béton HA10 barre 6m", quantity: Math.round(t.acier_kg || 0), unit: "kg" },
      { name: "Treillis soudé ST25C", search: "treillis soudé ST25C panneau", quantity: slabArea, unit: "m²" },
      { name: "Béton prêt à l'emploi C25/30", search: "béton prêt à l'emploi C25/30", quantity: t.beton_m3 || 0, unit: "m³" },
    ].filter((it) => it.quantity > 0);
    if (!items.length) return toast.error("Aucune quantité à comparer — lancez d'abord l'étude");
    sessionStorage.setItem("construpilot_price_search_batch", JSON.stringify({
      ts: Date.now(), project_name: `Étude PC — ${plan?.filename || "plan"}`,
      total_avg: t.ht || 0, items,
    }));
    nav("/prix");
  };
  const recomputePcStudy = async () => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/pc-study/recompute`);
      await refreshPlan();
      toast.success(`Devis recalculé avec vos réglages — ${data.totals?.ttc ?? 0} € TTC`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Recalcul impossible"); }
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
    if (!body) return toast.error("Écrivez d'abord un message à enregistrer");
    const name = body.split("\n")[0].slice(0, 40) || "Modèle";
    try {
      const { data } = await api.post("/emails/templates", { name, body });
      setMsgTemplates((prev) => [data.template, ...prev]);
      toast.success(`Modèle enregistré : ${data.template.name}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Enregistrement impossible");
    }
  };

  const deleteMsgTemplate = async (templateId) => {
    try {
      await api.delete(`/emails/templates/${templateId}`);
      setMsgTemplates((prev) => prev.filter((t) => t.template_id !== templateId));
    } catch { toast.error("Suppression impossible"); }
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
      toast.success(`Rapport renvoyé à ${data.sent_to}`);
      await refreshPlan();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Renvoi impossible");
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
      toast.success(`Zoom sur ${kind}`);
    } else {
      toast.info("Position non disponible pour cet objet");
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
      toast.success(`Devis pièce généré : ${data.total_budget?.toFixed(2)} €`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Génération impossible");
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
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "distance", points: pts.slice(0, 2), color: pickAutoColor(),
      });
      toast.success(`Distance : ${data.value_m} m — mémorisée. Double-cliquez pour terminer chaque nouvelle cote.`);
      setPoints([]);
      setPanelFocus("measures"); setObjectPanelOpen(true);
      await refreshPlan();
    } catch { toast.error("Mesure échouée"); }
  };

  const finishRoom = (pts = points) => {
    if (pts.length < 3) return toast.error("Une pièce nécessite au moins 3 points");
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    setPoints(pts);
    setPendingRoomName(`Pièce ${String(rooms.length + 1).padStart(2, "0")}`);
    setRoomDialog(true);
  };

  // Iter67 — mesure de surface libre (polygone) en m²
  const finishSurface = async (pts = points) => {
    if (pts.length < 3) return toast.error("Une surface nécessite au moins 3 points");
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polygon", points: pts, color: pickAutoColor(),
      });
      toast.success(`Surface : ${data.area_m2} m² · périmètre ${data.perimeter_m} m — mémorisée`, { duration: 6000 });
      setPoints([]);
      setPanelFocus("measures"); setObjectPanelOpen(true);
      await refreshPlan();
    } catch { toast.error("Mesure de surface échouée"); }
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
        const noun = isArea ? "Zone" : "Tronçon";
        const what = isArea ? "Surface" : "Mur";
        toast.success(`${noun} ${next.length} ajouté${next.length > 1 ? "" : ""} · ${what} en cours : ${total.toFixed(2)} ${isArea ? "m²" : "m"} — continuez ou « Terminer »`, { duration: 5000 });
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
    if (!segs.length) return toast.error(isArea ? "Aucune zone — mesurez au moins une zone" : "Aucun tronçon — mesurez au moins un tronçon de mur");
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    try {
      const flat = segs.flat();
      const payload = isArea
        ? { page_index: pageIndex, kind: "cumulative_area", points: flat, polygons: segs, label: cumulLabel.trim() || null, color: cumulColor, poste: cumulPoste || null }
        : { page_index: pageIndex, kind: "cumulative", points: flat, segments: segs, label: cumulLabel.trim() || null, color: cumulColor, poste: cumulPoste || null };
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, payload);
      if (isArea) toast.success(`Surface enregistrée : ${data.area_m2} m² (${segs.length} zone${segs.length > 1 ? "s" : ""})`, { duration: 6000 });
      else toast.success(`Mur enregistré : ${data.value_m} m (${segs.length} tronçon${segs.length > 1 ? "s" : ""}, ouvertures exclues)`, { duration: 6000 });
      setCumulSegments([]); setCumulLabel(""); setCumulPoste(""); setPoints([]);
      setCumulMode(false);
      setCumulColor(pickAutoColor());
      setPanelFocus("measures"); setObjectPanelOpen(true);
      await refreshPlan();
    } catch { toast.error("Enregistrement impossible"); }
  };

  const cancelCumulWall = () => {
    setCumulSegments([]); setCumulLabel(""); setPoints([]);
    toast.message("Cumul annulé");
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
      toast.success(`Ouverture déduite : −${data.opening.width_m} m → mur net ${data.value_m} m — dessinez la suivante ou « Terminer »`, { duration: 6000 });
    } catch (e) { toast.error(e?.response?.data?.detail || "Déduction impossible"); }
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
    if (!(w > 0)) return toast.error("Largeur invalide");
    const label = deductNature === "porte" ? "Porte" : deductNature === "fenetre" ? "Fenêtre" : undefined;
    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/measurements/${deductDialog.measurement_id}/deduct-opening`,
        { width_m: w, count: c, ...(h > 0 ? { height_m: h } : {}), ...(label ? { label } : {}) });
      toast.success(`Ouverture déduite : −${(w * c).toFixed(2)} m → mur net ${data.value_m} m`, { duration: 6000 });
      if (h > 0 && deductNature) localStorage.setItem(`cp_op_h_${deductNature}`, String(h));
      setDeductWidth(""); setDeductCount(1);
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Déduction impossible"); }
  };

  // Hauteur du mur → calcul automatique des m² (mur brut, ouvertures, mur net)
  // Édition directe du m²/ml d'une cote depuis la liste Objets (déterministe côté serveur)
  const setMeasureSurfaceApi = async (measurementId, surfaceM2) => {
    try {
      await api.post(`/takeoffs/${plan.plan_id}/ai-command/apply`, {
        action: "set_measurement_surface",
        params: { measurement_id: measurementId, surface_m2: surfaceM2 }, page_index: pageIndex });
      await refreshPlan();
      toast.success(`Surface → ${Number(surfaceM2).toFixed(2)} m²`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Surface impossible"); }
  };
  const setMeasureLengthApi = async (measurementId, lengthM) => {
    try {
      await api.post(`/takeoffs/${plan.plan_id}/ai-command/apply`, {
        action: "set_measurement_length",
        params: { measurement_id: measurementId, length_m: lengthM }, page_index: pageIndex });
      await refreshPlan();
      toast.success(`Linéaire → ${Number(lengthM).toFixed(2)} m`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Linéaire impossible"); }
  };

  const setWallHeightApi = async (measurementId, heightM) => {    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/measurements/${measurementId}/wall-height`,
        { height_m: heightM > 0 ? heightM : null });
      if (heightM > 0 && data.wall_area_net_m2 != null) {
        setLastWallHeight(heightM);
        localStorage.setItem("cp_last_wall_height", String(heightM));
        toast.success(`Hauteur ${heightM} m → mur net ${data.wall_area_net_m2} m² (brut ${data.wall_area_gross_m2} m² − ouvertures ${data.openings_area_m2} m²)`, { duration: 7000 });
      } else toast.message("Hauteur de mur retirée");
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Hauteur impossible"); }
  };

  // Arme le mode « dessiner la fenêtre » pour un mur donné (garde le volet ouvert)
  const armDeductDraw = (m) => {
    setDeductDialog(null);
    setDeductDraw({ measurement_id: m.measurement_id, label: m.label || "Mur" });
    setCumulMode(false); setPoints([]); setTool(TOOLS.DIST);
    toast.info(`Dessinez la fenêtre/porte sur « ${m.label || "le mur"} » (2 points) puis double-clic. Vous pouvez en enchaîner plusieurs.`, { duration: 7000 });
  };

  // Report d'une cote vers l'éditeur de devis (ligne d'ouvrage)
  const reportMeasureToDevis = (m) => {
    const isArea = m.kind === "polygon" || m.kind === "cumulative_area";
    const val = isArea ? (m.area_m2 || 0) : (m.value_m ?? m.length_m ?? 0);
    const unit = isArea ? "m2" : "ml";
    const name = m.label || (m.kind === "cumulative" ? "Mur" : m.kind === "cumulative_area" ? "Surface" : isArea ? "Surface" : "Mesure");
    addOuvrageFromPlan({ line_kind: "ouvrage", designation: name, qty: Number(val) || 0, unit, unit_price_ht: 0 });
    toast.success(`« ${name} » ajouté au devis (${Number(val).toFixed(2)} ${unit}) — cliquez « Créer un devis »`, { duration: 6000 });
  };

  // Report de la SURFACE de mur nette (m²) au devis — quand une hauteur est saisie
  const reportWallAreaToDevis = (m) => {
    const area = Number(m.wall_area_net_m2 || 0);
    if (!(area > 0)) return toast.error("Saisissez d'abord la hauteur du mur");
    const name = (m.label || "Mur") + " — surface (h. " + Number(m.wall_height_m || 0) + " m)";
    addOuvrageFromPlan({ line_kind: "ouvrage", designation: name, qty: area, unit: "m2", unit_price_ht: 0 });
    toast.success(`Surface de mur « ${name} » ajoutée au devis (${area.toFixed(2)} m²)`, { duration: 6000 });
  };

  // Report GROUPÉ : toutes les surfaces nettes de murs de la page → devis en une fois
  const reportAllWallAreasToDevis = () => {
    const walls = pageMeasurements.filter((m) => Number(m.wall_area_net_m2 || 0) > 0);
    if (!walls.length) return toast.error("Aucun mur avec surface nette (saisissez les hauteurs d'abord)");
    walls.forEach((m) => {
      const name = (m.label || "Mur") + " — surface (h. " + Number(m.wall_height_m || 0) + " m)";
      addOuvrageFromPlan({ line_kind: "ouvrage", designation: name,
        qty: Number(m.wall_area_net_m2), unit: "m2", unit_price_ht: 0 });
    });
    const tot = walls.reduce((s, m) => s + Number(m.wall_area_net_m2 || 0), 0);
    toast.success(`${walls.length} mur(s) ajoutés au devis — ${tot.toFixed(2)} m² au total`, { duration: 7000 });
  };

  // Fusion de cotes : joint plusieurs mesures en une (la 1re = cible), calcul automatique
  const mergeMeasures = async (ids) => {
    if (!ids || ids.length < 2) return toast.error("Sélectionnez au moins 2 cotes");
    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/measurements/merge`, { measurement_ids: ids });
      const m = data.measurement || {};
      const val = m.kind === "cumulative_area" ? `${Number(m.area_m2 || 0).toFixed(2)} m²`
        : `${Number(m.value_m ?? m.length_m ?? 0).toFixed(2)} m`;
      toast.success(`${data.merged_count} cotes fusionnées → ${val}`, { duration: 6000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Fusion impossible"); }
  };

  // Édition / suppression d'une ouverture déjà déduite (sans tout refaire)
  const patchOpening = async (openingId, patch) => {
    try {
      const { data } = await api.patch(
        `/takeoffs/${plan.plan_id}/measurements/${deductDialog.measurement_id}/openings/${openingId}`, patch);
      toast.success(`Ouverture modifiée → mur net ${data.value_m} m`);
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Modification impossible"); }
  };
  const removeOpening = async (openingId) => {
    try {
      const { data } = await api.delete(
        `/takeoffs/${plan.plan_id}/measurements/${deductDialog.measurement_id}/openings/${openingId}`);
      toast.success(`Ouverture supprimée → mur net ${data.value_m} m`);
      await refreshPlan();
    } catch { toast.error("Suppression impossible"); }
  };
  const deductLiveMeasure = deductDialog
    ? pageMeasurements.find((x) => x.measurement_id === deductDialog.measurement_id)
    : null;

  const saveRoom = async () => {
    if (!currentCalib || points.length < 3) return toast.error("Tracez une pièce sur un plan calibré");
    const height = decimalNumber(ceilingH);
    if (!finitePositive(height)) return toast.error("Hauteur de pièce invalide");
    try {
      await api.post(`/takeoffs/${plan.plan_id}/rooms`, {
        page_index: pageIndex, name: pendingRoomName,
        points,
        ceiling_height_m: height,
        floor_thickness_m: planDefaults.floor_thickness_m || 0.15,
        openings: [],
      });
      toast.success("Pièce enregistrée");
      setRoomDialog(false);
      setPoints([]);
      await refreshPlan();
      setTool(TOOLS.SELECT);
    } catch (e) { toast.error("Sauvegarde impossible"); }
  };

  const deleteRoom = async (rid) => {
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/rooms/${rid}`);
      await refreshPlan(); toast.success("Pièce supprimée");
    } catch (error) { toast.error(errorMessage(error, "Suppression impossible")); }
  };

  // Efface TOUTES les mesures/annotations de la page avant de passer au devis
  const clearAllMeasures = async () => {
    if (!plan?.plan_id) return;
    const roomCount = rooms.length;
    if (!window.confirm(
      `Tout effacer sur cette page ?\n\n${roomCount} pièce(s), ${pageMeasurements.length} mesure(s) et les annotations (compteurs, notes, angles, toitures) seront supprimés. L'affichage des murs détectés sera réinitialisé. Cette action est irréversible.`
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
      toast.success("Toutes les mesures ont été effacées — prêt pour un nouveau devis");
    } catch (e) {
      toast.error("Impossible de tout effacer");
    }
  };

  const importAiRooms = async () => {
    if (!plan?.plan_id || !currentCalib) {
      toast.error("Calibrez le plan avant d'importer des contours"); return 0;
    }
    const sourceKey = pageKey;
    let data;
    try { ({ data } = await api.post(`/takeoffs/${plan.plan_id}/detect-all-rooms?page_index=${pageIndex}`)); }
    catch (error) { toast.error(errorMessage(error, "Détection des pièces impossible")); return 0; }
    if (currentPageKeyRef.current !== sourceKey) return 0;
    const validContour = (points) => Array.isArray(points) && points.length >= 3 &&
      points.every((p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1])) &&
      Math.abs(points.reduce((sum, p, i) => {
        const q = points[(i + 1) % points.length]; return sum + p[0] * q[1] - q[0] * p[1];
      }, 0)) > 0;
    const contours = (Array.isArray(data?.rooms) ? data.rooms : []).filter((room) => validContour(room.points));
    if (!contours.length) {
      toast.warning("Aucun contour exploitable. Les surfaces lues par l'IA restent des indications ; tracez les pièces sur le plan.");
      return 0;
    }
    // Comparaison indépendante du point de départ et du sens du contour.
    const signature = (points) => JSON.stringify(points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).sort());
    let latest;
    try { ({ data: latest } = await api.get(`/takeoffs/${plan.plan_id}`)); }
    catch (error) { toast.error(errorMessage(error, "Vérification des pièces existantes impossible")); return 0; }
    if (currentPageKeyRef.current !== sourceKey) return 0;
    const known = new Set((latest.rooms || []).filter((r) => r.page_index === pageIndex && validContour(r.points)).map((r) => signature(r.points)));
    let imported = 0, failed = 0, skipped = 0;
    for (const contour of contours) {
      if (currentPageKeyRef.current !== sourceKey) break;
      const key = signature(contour.points);
      if (known.has(key)) { skipped++; continue; }
      try {
        await api.post(`/takeoffs/${plan.plan_id}/rooms`, {
          page_index: pageIndex, name: contour.name || `Pièce détectée ${imported + 1}`,
          points: contour.points, ceiling_height_m: planDefaults.ceiling_h_m ?? 2.5,
          floor_thickness_m: planDefaults.floor_thickness_m ?? 0.15,
        });
        known.add(key); imported++;
      } catch { failed++; }
    }
    await refreshPlan();
    if (currentPageKeyRef.current === sourceKey) setRightTab("rooms");
    if (imported) toast.success(`${imported} contour(s) importé(s) — vérifiez leur position et leurs dimensions sur le plan`);
    if (failed) toast.warning(`${failed} pièce(s) non importée(s)`);
    if (!imported && skipped) toast.message("Ces contours sont déjà présents dans le métré");
    return imported;
  };

  const runAI = async () => {
    if (!plan?.plan_id || analysisLock.current) return;
    analysisLock.current = true;
    const sourceKey = pageKey;
    setAiBusy(true);
    setAnalysisRecap(null);
    setAnalysisProgress("Lecture des textes, pièces et ouvertures de cette page…");
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
          `Analyse IA — ${n} pièce${n > 1 ? "s" : ""} détectée${n > 1 ? "s" : ""}` +
          (surf ? ` · ${surf} m²` : ""),
          { duration: 6000 }
        );
      }
    } catch (e) { toast.error("Analyse IA impossible"); }
    finally { setAiBusy(false); setAnalysisProgress(""); analysisLock.current = false; }
  };

  // --- Iter62 : calibration par cotes / recalage surfaces écrites / textes IA ---
  const calibrateFromCotes = async () => {
    setAiActionBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/calibrate/from-cotes`,
        { page_index: pageIndex });
      toast.success(
        `Échelle calibrée par les cotes : ${data.calibration.pixels_per_meter.toFixed(1)} px/m ` +
        `(${data.calibration.samples_used} cote${data.calibration.samples_used > 1 ? "s" : ""}, ±${data.calibration.spread_pct}%)` +
        (data.rooms_recomputed ? ` · ${data.rooms_recomputed} pièce(s) recalculée(s)` : ""),
        { duration: 8000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Calibration par cotes impossible"); }
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
          `Échelle recalée : ${data.calibration.pixels_per_meter.toFixed(1)} px/m · ` +
          `${data.rooms_recomputed} pièce(s) recalculée(s)`, { duration: 7000 });
        setReconcile(null);
        await refreshPlan();
      } else if (!data.can_reconcile) {
        toast.warning(data.reason || "Aucune correspondance avec une surface écrite");
      }
    } catch (e) { toast.error(e?.response?.data?.detail || "Vérification impossible"); }
    finally { setAiActionBusy(false); }
  };

  const applyAiTexts = async () => {
    setAiActionBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/apply-ai-texts`,
        { page_index: pageIndex });
      const parts = [];
      if (data.renamed?.length) parts.push(`${data.renamed.length} pièce(s) renommée(s)`);
      if (data.materials_set?.length) parts.push(`${data.materials_set.length} matériau(x) sol`);
      if (data.heights_updated?.length) parts.push(`${data.heights_updated.length} hauteur(s)`);
      if (data.calibration_set) parts.push("échelle écrite appliquée");
      if (data.surface_flags?.length) parts.push(`⚠ ${data.surface_flags.length} écart(s) de surface >5%`);
      toast.success(parts.length
        ? `Textes du plan appliqués — ${parts.join(" · ")}`
        : "Textes analysés — rien à modifier", { duration: 9000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Application des textes impossible"); }
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
        `${data.segment_count} segments de murs détectés` +
        (data.filtered_cotes ? ` · ${data.filtered_cotes} traits de cote/textes ignorés` : "") +
        (data.filtered_diagonals ? ` · ${data.filtered_diagonals} diagonales ignorées` : "")
      );
      if (data.structural_hint && !ortho) {
        toast.warning(
          "Ce plan ressemble à un plan de structure/béton (aciers, cotes, hachures). La détection de murs y est peu fiable — utilisez plutôt le Métré béton.",
          { duration: 14000,
            action: { label: "Ignorer les diagonales", onClick: () => detectWalls(true) } }
        );
      }
      await loadWallsSummary();
    } catch (e) { toast.error("Détection murs impossible"); }
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
    if (notify) toast.success(`Réglages « ${pr.name} » appliqués`);
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
    if (!window.confirm(`Supprimer le réglage « ${selectedPreset} » ?`)) return;
    try {
      await api.delete(`/takeoffs/settings/beton-presets/${encodeURIComponent(selectedPreset)}`);
      setBetonPresets((list) => list.filter((p) => p.name !== selectedPreset));
      setSelectedPreset("");
      toast.success("Réglage supprimé");
    } catch { toast.error("Suppression impossible"); }
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
    } catch { toast.error("Comparaison impossible"); setCompareOpen(false); }
    finally { setCompareBusy(false); }
  };

  const saveBetonPreset = async () => {
    const name = window.prompt("Nom du jeu de réglages (ex. Rénovation, Villa) :");
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
      toast.success(`Réglage « ${name.trim()} » enregistré`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement du réglage impossible"); }
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
      toast.success("Réglages béton enregistrés comme valeurs par défaut de l'entreprise");
    } catch { toast.error("Enregistrement des réglages impossible"); }
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
        toast.error(data?.summary || "Je n'ai pas compris cette commande.");
      } else {
        setAiCmdProposal({ ...data, _cmd: cmd });
        if (data.action === "answer" && data.answer) {
          aiSpeak(data.answer.length > 600 ? data.answer.slice(0, 600) : data.answer);
        }
      }    } catch (e) {
      toast.error(e?.response?.data?.detail || "Assistant indisponible");
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
    const label = (aiCmd || "Prix matériau").trim().slice(0, 60) || "Prix matériau";
    setAiCmdBusy(true);
    try {
      await api.post(`/takeoffs/corps-etat/custom`, {
        label, unit, pu: ps.amount, color: "#0ea5e9",
      });
      toast.success(`Poste perso créé : ${label} à ${ps.amount.toLocaleString("fr-FR", { minimumFractionDigits: 2 })} €/${unit === "m2" ? "m²" : unit}. Disponible dans le chiffrage.`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Création du poste impossible");
    } finally { setAiCmdBusy(false); }
  };


  const aiSpeak = (text) => {
    try {
      if (!window.speechSynthesis) return;
      const u = new window.SpeechSynthesisUtterance(text);
      u.lang = "fr-FR"; u.rate = 1;
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
        const msg = `Estimation de la page : ${ht.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} euros hors taxes, soit ${ttc.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} euros TTC.`;
        toast.success(`Total page : ${ht.toLocaleString("fr-FR", { minimumFractionDigits: 2 })} € HT · ${ttc.toLocaleString("fr-FR", { minimumFractionDigits: 2 })} € TTC`);
        aiSpeak(msg);
        turnResult = `Page chiffrée : ${ht.toFixed(0)} € HT`;
      } else {
        toast.success("Action appliquée et enregistrée");
        let hist = inverse;
        if ((action === "create_measurement" || action === "duplicate_measurement") && data?.measurement_id) {
          hist = { action: "delete_measurement", params: { measurement_id: data.measurement_id } };
          if (action === "create_measurement") {
            setAiJustCreated({ measurement_id: data.measurement_id, label: data.label || "cote", value: data.value });
          }
          turnResult = `Créée : ${data.label || "cote"} (${data.value || ""})`;
        } else if (action === "create_measurements_bulk" && Array.isArray(data?.created)) {
          hist = { bulkDeleteIds: data.created.map((c) => c.measurement_id) };
          toast.success(`${data.count} mesures créées`);
          turnResult = `${data.count} cotes créées`;
        } else if (action === "deduct_measurement_areas") {
          turnResult = `Surface → ${Number(data?.surface_m2 || 0).toFixed(2)} m² (−${Number(data?.total_deducted_m2 || 0).toFixed(2)} m²)`;
        } else if (action === "adjust_measurement_surface") {
          turnResult = `Surface → ${Number(data?.surface_m2 || 0).toFixed(2)} m²`;
        }
        setAiHistory((h) => [{ id: Date.now(), summary: summary || action, inverse: hist }, ...h].slice(0, 20));
      }
      if (_cmd) {
        setAiTurns((t) => [...t, { command: _cmd, result: turnResult, measurement_id: turnMid }].slice(-8));
      }
      setAiCmdProposal(null);
      setAiCmd("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Application impossible");
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
      toast.success("Action annulée");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Annulation impossible");
    } finally { setAiCmdBusy(false); }
  };

  const aiVoiceDictate = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast.error("La dictée vocale n'est pas supportée par ce navigateur (essayez Chrome)."); return; }
    const rec = new SR();
    rec.lang = "fr-FR"; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onstart = () => setAiListening(true);
    rec.onerror = () => { setAiListening(false); toast.error("Micro indisponible ou permission refusée."); };
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
      toast.error("Calibrez d'abord le plan : l'échelle est indispensable pour calculer les quantités.");
      setTool(TOOLS.CALIB);
      return;
    }
    analysisLock.current = true;
    setAnalysisBusy(true);
    setAnalysisRecap(null);
    setAnalysisProgress("1 / 5 · Repérage des murs, poteaux, poutres et dalles…");
    const sourceKey = pageKey;
    const warnings = [];
    const tid = toast.loading("Analyse complète en cours… structure, pièces, métré et estimation.");
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
        else warnings.push("structure : " + data.error);
      } catch (e) { warnings.push("détection de structure indisponible"); }
      if (currentPageKeyRef.current !== sourceKey) return;

      setAnalysisProgress("2 / 5 · Lecture des pièces et ouvertures…");
      // 2) Pièces (rooms) par IA vision
      let aiRooms = [];
      try {
        const { data } = await api.post(`/takeoffs/${plan.plan_id}/analyze?page_index=${pageIndex}`);
        aiRooms = data?.rooms || [];
        if (data?.error) warnings.push("analyse des pièces : " + data.error);
      } catch (e) { warnings.push("analyse des pièces indisponible"); }
      if (currentPageKeyRef.current !== sourceKey) return;

      setAnalysisProgress("3 / 5 · Import des contours et calcul des surfaces…");
      // 3) Rafraîchit puis importe les pièces au métré (surfaces + périmètres)
      await refreshPlan();
      if (currentPageKeyRef.current !== sourceKey) return;
      let importedRooms = 0;
      if (aiRooms.length) {
        try { importedRooms = (await importAiRooms()) || 0; }
        catch (e) { warnings.push("import des pièces échoué"); }
        if (!importedRooms) warnings.push("aucune nouvelle pièce importée");
      }

      if (currentPageKeyRef.current !== sourceKey) return;
      const latestPlan = await refreshPlan();
      if (currentPageKeyRef.current !== sourceKey) return;
      const measuredRooms = (latestPlan?.rooms || []).filter((room) => (room.page_index ?? 0) === pageIndex);
      setAnalysisProgress("4 / 5 · Calcul du descriptif béton…");
      // 4) Chiffrage / descriptif béton (métré chiffré)
      const descData = await loadDescriptif();
      if (!descData) warnings.push("descriptif indisponible");
      if (currentPageKeyRef.current !== sourceKey) return;

      setAnalysisProgress("5 / 5 · Préparation de l’estimation…");
      // 5) Estimation globale depuis le métré (uniquement si des pièces existent)
      let estData = null;
      if ((latestPlan?.rooms || []).length > 0) {
        try { estData = await runEstimation(); } catch (e) { /* estimation optionnelle */ }
      }

      if ((latestPlan?.rooms || []).length > 0 && !estData) warnings.push("estimation indisponible");
      if (currentPageKeyRef.current !== sourceKey) return;
      // Récapitulatif instantané (sans dialogue)
      const missingSurface = measuredRooms.some((room) => !finitePositive(room.surface_m2));
      if (missingSurface) warnings.push("surface manquante ou invalide pour certaines pièces");
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
      if (struct) parts.push(`${struct.wall_count || 0} murs · ${struct.column_count || 0} poteaux · ${struct.beam_count || 0} poutres · ${struct.floor_count || 0} dalles`);
      if (aiRooms.length) parts.push(`${aiRooms.length} pièce(s)`);
      if (warnings.length) toast.warning(`Analyse partielle : ${warnings.join(" ; ")}. Vérifiez les résultats avant export.`, { duration: 10000 });
      else toast.success(`Analyse terminée — ${parts.join(" · ") || "aucun élément détecté"}. Vérifiez les résultats sur le plan.`, { duration: 8000 });
    } catch (e) {
      toast.dismiss(tid);
      toast.error(e?.response?.data?.detail || "Analyse impossible");
    } finally { toast.dismiss(tid); setAnalysisBusy(false); setAnalysisProgress(""); analysisLock.current = false; }
  };

  const analyzeAllPages = async () => {
    if (!plan?.plan_id || analysisLock.current) return;
    analysisLock.current = true;
    const sourceKey = pageKey;
    setAnalysisBusy(true);
    setAnalysisRecap(null);
    setAnalysisProgress("Préparation de la détection de structure sur toutes les pages…");
    try {
      const { data: job } = await api.post(`/takeoffs/${plan.plan_id}/detect-structure-all`);
      const data = await waitPlanJob(job.job_id, { onProgress: (j) => {
        if (currentPageKeyRef.current === sourceKey && j.total > 0) {
          setAnalysisProgress(`Structure · ${j.progress || 0} / ${j.total} pages traitées…`);
        }
      } });
      await refreshPlan();
      if (currentPageKeyRef.current !== sourceKey) return;
      setAnalysisRecap(null);
      toast.success(`Structure : ${data.page_count} page(s) analysée(s). Vérifiez chaque page avant le métré.`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Analyse multi-pages impossible");
    } finally { setAnalysisBusy(false); setAnalysisProgress(""); analysisLock.current = false; }
  };

  const _hasStructure = () => !!(structure && ((structure.walls || []).length || (structure.openings || []).length || (structure.beams || []).length || (structure.floors || []).length || (structure.columns || []).length));

  const sendToQuote = async () => {
    if (!currentCalib) { toast.error("Calibrez d'abord le plan"); return; }
    if (!_hasStructure()) { toast.error("Analysez d'abord le plan"); return; }
    try {
      const body = plan3dSnapshot ? { snapshot_png: plan3dSnapshot } : {};
      const mq = (marginBeton !== "" ? `&margin_beton=${marginBeton}` : "")
        + (marginAcier !== "" ? `&margin_acier=${marginAcier}` : "")
        + (marginLabor !== "" ? `&margin_labor=${marginLabor}` : "");
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/quote?beton_only=true&wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&acier_price_kg=${acierPriceKg}&beton_price_m3=${betonPriceM3}${betonPriceQuery()}&labor_price_m3=${laborPriceM3}&margin_pct=${marginPct}&price_level=${priceLevel}${araseQuery()}${mq}`, body);
      const n = data.priced_lines || 0;
      toast.success((n > 0 ? `Devis créé — ${n} ligne(s) chiffrée(s) depuis votre bibliothèque` : "Devis créé depuis le descriptif") + (plan3dSnapshot ? " · vue 3D jointe" : ""));
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Génération du devis impossible");
    }
  };

  const estimateAndDownloadQuote = async () => {
    if (!currentCalib) { toast.error("Calibrez d'abord le plan"); return; }
    if (!_hasStructure()) { toast.error("Analysez d'abord le plan"); return; }
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
      a.href = url; a.download = `devis-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      const ttc = data.totals?.ttc || 0;
      toast.success(`Devis estimé téléchargé — ${ttc.toLocaleString("fr-FR")} € TTC · ${data.priced_lines || 0} poste(s) chiffré(s)`, { duration: 6000 });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Estimation impossible");
    } finally { setQuoteBusy(false); }
  };

  const exportAnnotatedPdf = async () => {
    if (!_hasStructure()) { toast.error("Analysez d'abord le plan"); return; }
    try {
      const res = await api.post(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/pdf?wall_height=${wallHeight}`,
        {}, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `plan-annote-${plan.plan_id}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("PDF du plan annoté téléchargé");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Export PDF impossible");
    }
  };

  // Analyse automatique à l'ouverture depuis "Ajouter un plan" (?auto=1)
  useEffect(() => {
    if (!pendingAuto || !plan?.plan_id) return;
    setPendingAuto(false);
    toast.info("Analyse automatique du plan en cours…");
    analyzePlanFull();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAuto, plan?.plan_id]);

  const exportBetonXlsx = async () => {
    if (!_hasStructure()) { toast.error("Analysez d'abord le plan"); return; }
    try {
      const q = `wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&beton_price_m3=${betonPriceM3}&acier_price_kg=${acierPriceKg}${betonPriceQuery()}`;
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/beton-xlsx?${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-beton-${plan.plan_id}.xlsx`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Métré béton (Excel) téléchargé");
    } catch (e) { toast.error(e.message || "Export Excel béton impossible"); }
  };

  const exportBetonPdf = async () => {
    if (!_hasStructure()) { toast.error("Analysez d'abord le plan"); return; }
    try {
      const q = `wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&beton_price_m3=${betonPriceM3}&acier_price_kg=${acierPriceKg}&labor_price_m3=${laborPriceM3}&margin_pct=${marginPct}`;
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/beton-pdf?${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-beton-${plan.plan_id}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Métré béton (PDF) téléchargé");
    } catch (e) { toast.error(e.message || "Export PDF béton impossible"); }
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
      setAiMessages((prev) => [...prev, { role: "assistant", text: data.reply || "Analyse mise à jour.", ok: data.ok }]);
      if (data.ok) toast.success("Plan mis à jour par l'IA");
    } catch (e) {
      const err = e?.response?.data?.detail || "L'IA n'a pas pu répondre";
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
    } catch { toast.error("Structure non enregistrée — réessayez avant de changer de page"); }
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
    toast.info("Mur ajouté — glissez ses extrémités pour le placer");
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
    toast.info("Poutre ajoutée — glissez ses extrémités pour la placer");
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
    toast.info("Poteau ajouté — glissez ses coins pour l'ajuster");
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
    toast.info(`${kind === "porte" ? "Porte" : "Fenêtre"} ajoutée — glissez ses extrémités pour la placer`);
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
    toast.info("Semelle ajoutée — glissez ses coins pour l'ajuster");
  };

  const autoFillRoom = async (pt) => {
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
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
      toast.success(`Contour détecté (${data.point_count} points, ${data.surface_m2} m²)`);
      // Ouvre le dialog de nom immédiatement
      setPendingRoomName(`Pièce ${String(rooms.length + 1).padStart(2, "0")}`);
      setRoomDialog(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aucune pièce détectée à ce point");
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
    } catch (error) { toast.error(errorMessage(error, "Calcul du métré ou des matériaux impossible")); }
  };

  const sendToEstimator = () => {
    if (!takeoff?.totals?.floor_m2) return toast.error("Ajoutez au moins une pièce");
    // Prefill query params for /estimation with surface
    nav(`/estimation?surface=${Math.round(takeoff.totals.floor_m2)}&from=plan`);
  };

  const sendToPrices = () => {
    if (!materials) return;
    const q = [];
    if (materials.floor) q.push(`${materials.floor.material} ${materials.floor.quantity_m2}m²`);
    if (materials.placo) q.push(`plaques BA13`);
    if (materials.paint) q.push(`peinture`);
    nav(`/prix?q=${encodeURIComponent(q.join(" "))}`);
  };

  const downloadPdf = async () => {
    if (!plan?.plan_id) return;
    // Guard : PDF vide si aucune pièce tracée
    if (!rooms.length) {
      toast.error("Ajoutez d'abord une pièce (outil Pièce ou Auto-pièce) pour générer un métré.", { duration: 5000 });
      setRightTab("rooms");
      return;
    }
    try {
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/pdf?include_materials=true&floor_material=${floorMaterial}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Métré PDF téléchargé");
    } catch { toast.error("Export PDF impossible"); }
  };

  const downloadPlanMetre = async () => {
    if (!plan?.plan_id) return;
    try {
      const res = await api.post("/takeoffs/metre-multi-pdf",
        { plan_ids: [plan.plan_id], project_name: plan.filename || "Métré" },
        { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-${(plan.filename || "plan").replace(/[^\w]+/g, "_")}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Métré PDF (sans prix) téléchargé");
    } catch (e) { toast.error(e?.response?.data?.detail || "Export impossible"); }
  };
  const downloadEcartsPdf = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data: blob } = await api.get(`/takeoffs/${plan.plan_id}/ecarts-pdf?page_index=${pageIndex}`, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `rapport-ecarts-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Rapport d'écarts PDF téléchargé");
    } catch (e) { toast.error(e.message || "Export rapport écarts impossible"); }
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
        toast.info("Mesure annulée");
      } else if (selectedCote != null) {
        setSelectedCote(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [points, selectedCote]);

  // Iter64 — envoi du rapport d'écarts par email au client
  const sendEcartsReport = async () => {
    if (!ecartsEmail.trim()) return toast.error("Renseignez l'email du client");
    setSendingEcarts(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/ecarts-pdf/send`, {
        page_index: pageIndex,
        to_email: ecartsEmail.trim(),
        message: ecartsMessage,
      });
      toast.success(`Rapport d'écarts envoyé à ${data.sent_to}`, { duration: 7000 });
      setSendEcartsDialog(false);
      setEcartsMessage("");
      await refreshPlan();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Envoi impossible — vérifiez l'email");
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
      toast.success("Snapshot restauré");
    } catch { toast.error("Restauration impossible"); }
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
      toast.success("Nom enregistré");
    } catch { toast.error("Enregistrement impossible"); }
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
      a.href = url; a.download = `devis-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Devis PDF téléchargé");
      setQuoteDialog(false);
    } catch (e) { toast.error(e.message || "Export Devis impossible"); }
    finally { setQuoteBusy(false); }
  };

  const sendQuotePdf = async () => {
    if (!plan?.plan_id) return;
    if (!/@/.test(quoteClientEmail)) return toast.error("Email client invalide");
    if (quoteIncludeTva && !quoteClientAddress.trim())
      return toast.error("Adresse client requise pour l'attestation TVA");
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
        if (quoteIncludeTva) extras.push("attestation TVA");
        if (quoteAttachVideo && latestVideo) extras.push("tour vidéo 3D");
        const extra = extras.length ? " + " + extras.join(" + ") + " joint(s)" : "";
        toast.success(`Devis envoyé à ${quoteClientEmail}${extra} (${data.total_ttc?.toLocaleString("fr-FR")} € TTC)`);
        setQuoteDialog(false);
        setQuoteClientEmail(""); setQuoteClientName(""); setQuoteMessage("");
        setQuoteSubject(""); setQuoteIntro(""); setQuoteClientAddress("");
        await loadQuoteSends();
      } else {
        toast.error("Envoi email échoué — vérifiez la clé Resend");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi impossible");
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
      toast.success(`Estimation générée : ${data.surface_m2} m² · ${data.estimation?.total_avg?.toLocaleString("fr-FR")} €`);
      return data;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Estimation impossible");
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
      toast.error(e?.response?.data?.detail || "Paiement indisponible (réessayez)");
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
      handle3dError(e, "Maquette interactive indisponible");
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
      toast.success("Rendu 3D généré !");
      await loadRender3dHistory();
      loadCredits3d();
    } catch (e) {
      handle3dError(e, "Génération 3D échouée (réessayez)");
    } finally { setRender3dBusy(false); }
  };

  const openRender3dHistory = async (renderId) => {
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/renders-3d/${renderId}`);
      setRender3dImg(`data:${data.mime_type};base64,${data.image_b64}`);
      setRender3dStyle(data.style);
    } catch { toast.error("Chargement impossible"); }
  };

  const downloadRender3d = () => {
    if (!render3dImg) return;
    const a = document.createElement("a");
    a.href = render3dImg;
    a.download = `rendu-3d-${plan.plan_id}-${render3dStyle}.png`;
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
      toast.success("Tour vidéo 3D généré !");
      await loadVideoHistory();
      loadCredits3d();
    } catch (e) {
      handle3dError(e, "Génération vidéo échouée (réessayez)");
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
    toast.success(`Modèle « ${t.name} » appliqué`);
  };

  const saveTemplate = async () => {
    if (templateName.trim().length < 2) return toast.error("Nom du modèle trop court");
    try {
      await api.post("/quotes/templates", {
        name: templateName.trim(),
        finish: quoteFinish, floor_material: quoteFloor,
        is_shared: templateShared,
      });
      toast.success(`Modèle « ${templateName} » enregistré`);
      setTemplateName(""); setTemplateShared(false);
      await loadTemplates();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Enregistrement impossible");
    }
  };

  const deleteTemplate = async (id) => {
    if (!window.confirm("Supprimer ce modèle ?")) return;
    try {
      await api.delete(`/quotes/templates/${id}`);
      await loadTemplates();
      toast.success("Modèle supprimé");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suppression impossible");
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
      if (!Array.isArray(items)) throw new Error("Liste des plans invalide");
      setAllPlans(items);
    } catch (error) { toast.error(errorMessage(error, "Chargement des plans impossible")); }
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
    if (!gb?.name?.trim()) return toast.error("Nommez le projet");
    if (!gb.levels.length) return toast.error("Ajoutez au moins un plan");
    const body = { name: gb.name.trim(), chantier_id: chantierId || null, levels: gb.levels };
    try {
      if (gb.group_id) await api.put(`/takeoffs/multilevel/groups/${gb.group_id}`, body);
      else await api.post("/takeoffs/multilevel/groups", body);
      toast.success(`Projet « ${gb.name.trim()} » enregistré${chantierId ? " et rattaché au dossier chantier" : ""}`);
      setGroupBuilder(null);
      loadPlanGroups();
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement impossible"); }
  };

  const openGroupConsolidated = async (g) => {
    setGroupView({ loading: true, name: g.name, group_id: g.group_id });
    try {
      const { data } = await api.get(`/takeoffs/multilevel/groups/${g.group_id}`, { params: { margin_pct: 0 } });
      setGroupView({ ...data, group_id: g.group_id, loading: false });
    } catch { setGroupView(null); toast.error("Consolidation impossible"); }
  };

  const createGroupQuote = async () => {
    if (!groupView?.group_id) return;
    try {
      const { data } = await api.post(`/takeoffs/multilevel/groups/${groupView.group_id}/to-quote`, { margin_pct: 0 });
      toast.success("Devis partiel créé — les postes non mesurés restent à compléter");
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Création du devis impossible"); }
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
    { key: "report", name: "Dossier automatique", icon: Bot, desc: "Regroupe vos plans, relève le métré, chiffre et produit le dossier PDF complet." },
    { key: "devis", name: "Devis automatique", icon: Wand2, desc: "Chiffre les mesures affectées et crée un devis consolidé modifiable." },
    { key: "metre", name: "Métré express", icon: Ruler, desc: "Synthèse du métré : surfaces, linéaires, mesures et plans à compléter." },
    { key: "detect", name: "Détection murs auto", icon: ScanLine, desc: "Détecte murs + ouvertures (IA) sur un plan non mesuré. Étalonnage obligatoire avant métré." },
    { key: "compare", name: "Comparaison de plans", icon: GitCompare, desc: "Compare 2 versions (avant / après) et liste les écarts pièces et murs." },
    { key: "dpgf", name: "DPGF → devis", icon: FileText, desc: "Lit un DPGF/CCTP importé et prépare le devis chiffré (atelier dédié)." },
  ];
  const [agentHistory, setAgentHistory] = useState(null);
  const openPlanById = async (pid) => {
    try { const { data } = await api.get(`/takeoffs/${pid}`); setPlan(data); setPageIndex(0); setAgentBox(null); }
    catch { toast.error("Ouverture du plan impossible"); }
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
    if (!agentBox.selected.length) return toast.error("Sélectionnez au moins un plan");
    if (agentBox.agent === "compare" && agentBox.selected.length !== 2) return toast.error("Sélectionnez exactement 2 plans (avant / après)");
    setAgentBox((a) => ({ ...a, loading: true }));
    try {
      const { data } = await api.post("/agents/plan", { agent: agentBox.agent, plan_ids: agentBox.selected, prompt: agentBox.prompt });
      setAgentBox((a) => ({ ...a, step: "plan", loading: false, run: data.run,
        params: { ...a.params, margin_pct: data.defaults?.margin_pct || 0 } }));
    } catch (e) { setAgentBox((a) => ({ ...a, loading: false })); toast.error(e?.response?.data?.detail || "Proposition impossible"); }
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
      toast.success("Agent terminé — vérifiez le résultat");
    } catch (e) { setAgentBox((a) => ({ ...a, loading: false })); toast.error(e?.response?.data?.detail || "Exécution impossible"); }
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
    } catch { toast.error("Téléchargement impossible"); }
  };
  const agentFeedback = async (rating) => {
    if (!agentBox?.run?.run_id) return;
    const labels = Object.fromEntries((agentBox.run.plan_status || []).map((s) => [s.plan_id, s.level]));
    try {
      await api.post(`/agents/${agentBox.run.run_id}/feedback`, { rating, level_labels: labels });
      toast.success(rating === "ok" ? "Merci — l'agent retient vos choix" : "Correction enregistrée — l'agent s'améliore");
      if (rating === "ok") setAgentBox(null);
      else setAgentBox((a) => ({ ...a, step: "plan" }));
    } catch { toast.error("Envoi impossible"); }
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
      toast.success("Dossier de chiffrage PDF téléchargé");
    } catch { toast.error("Génération du PDF impossible"); }
  };

  const downloadGroupMetrePdf = async () => {
    if (!groupView?.group_id) return;
    try {
      const res = await api.get(`/takeoffs/multilevel/groups/${groupView.group_id}/pdf`,
                                { params: { metre_only: true }, responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `metre_${(groupView.name || "projet").replace(/[^\w]+/g, "_")}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success("Métré projet (sans prix) téléchargé");
    } catch { toast.error("Génération du métré impossible"); }
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
      toast.success("Version du métré enregistrée");
      setMetreLabel(""); loadMetreVersions();
    } catch { toast.error("Enregistrement impossible"); }
  };
  const toggleMetreSel = (id) => setMetreSel((s) => s.includes(id) ? s.filter((x) => x !== id) : (s.length >= 2 ? [s[1], id] : [...s, id]));
  const runMetreCompare = async () => {
    if (metreSel.length !== 2) return toast.error("Sélectionnez deux versions");
    try { const { data } = await api.get(`/takeoffs/metre-versions/compare`, { params: { a: metreSel[0], b: metreSel[1] } }); setMetreCompare(data); }
    catch { toast.error("Comparaison impossible"); }
  };
  const deleteMetreVersion = async (id) => {
    try { await api.delete(`/takeoffs/metre-versions/${id}`); setMetreSel((s) => s.filter((x) => x !== id)); loadMetreVersions(); }
    catch { toast.error("Suppression impossible"); }
  };

  const deleteGroup = async (g) => {
    if (!(await confirmDialog({ title: "Supprimer ce projet multi-niveaux ?", description: `« ${g.name} » — les plans ne sont pas supprimés.` }))) return;
    try { await api.delete(`/takeoffs/multilevel/groups/${g.group_id}`); loadPlanGroups(); toast.success("Projet supprimé"); }
    catch { toast.error("Suppression impossible"); }
  };

  const addLevel = (plan_id) => setGroupBuilder((gb) => gb.levels.some((l) => l.plan_id === plan_id) ? gb
    : { ...gb, levels: [...gb.levels, { plan_id, level_label: LEVEL_SUGGESTIONS[gb.levels.length] || "" }] });
  const removeLevel = (plan_id) => setGroupBuilder((gb) => ({ ...gb, levels: gb.levels.filter((l) => l.plan_id !== plan_id) }));
  const setLevelLabel = (plan_id, label) => setGroupBuilder((gb) => ({ ...gb, levels: gb.levels.map((l) => l.plan_id === plan_id ? { ...l, level_label: label } : l) }));

  const trashPlan = async (p) => {
    const ok = await confirmDialog({ title: "Mettre ce plan à la corbeille ?", description: `« ${p.filename || "Plan sans nom"} » et ses mesures resteront récupérables 30 jours dans la corbeille.`, confirmLabel: "Mettre à la corbeille" });
    if (!ok) return;
    try {
      await api.delete(`/takeoffs/${p.plan_id}`);
      toast.success("Plan mis à la corbeille — récupérable 30 jours", { action: { label: "Corbeille", onClick: () => nav("/corbeille") } });
      if (plan?.plan_id === p.plan_id) setPlan(null);
      loadAllPlans();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suppression impossible");
    }
  };

  const bulkTrashPlans = async (ids) => {
    if (!ids.length) return;
    const ok = await confirmDialog({ title: `Mettre ${ids.length} plan${ids.length > 1 ? "s" : ""} à la corbeille ?`, description: "Ils resteront récupérables 30 jours dans la corbeille.", confirmLabel: "Mettre à la corbeille" });
    if (!ok) return;
    try {
      const { data } = await api.post("/takeoffs/bulk-trash", { plan_ids: ids });
      toast.success(`${data.trashed} plan${data.trashed > 1 ? "s" : ""} mis à la corbeille`, { action: { label: "Corbeille", onClick: () => nav("/corbeille") } });
      setSelectedRecent([]);
      if (plan && ids.includes(plan.plan_id)) setPlan(null);
      loadAllPlans();
    } catch (e) { toast.error(e?.response?.data?.detail || "Suppression impossible"); }
  };

  const trashAllPlans = async () => {
    const ok = await confirmDialog({ title: `Tout supprimer (${allPlans.length} plan${allPlans.length > 1 ? "s" : ""}) ?`, description: "Tous vos plans seront mis à la corbeille (récupérables 30 jours).", confirmLabel: "Tout mettre à la corbeille" });
    if (!ok) return;
    try {
      const { data } = await api.post("/takeoffs/bulk-trash", { all: true });
      toast.success(`${data.trashed} plan${data.trashed > 1 ? "s" : ""} mis à la corbeille`, { action: { label: "Corbeille", onClick: () => nav("/corbeille") } });
      setSelectedRecent([]);
      setPlan(null);
      loadAllPlans();
    } catch (e) { toast.error(e?.response?.data?.detail || "Suppression impossible"); }
  };

  const applyWallHeightToPage = async () => {
    if (!plan?.plan_id) return;
    const h = Number(planDefaults.ceiling_h_m);
    if (!h || h <= 0) return toast.error("Définissez une hauteur de mur valide dans les réglages");
    const ok = await confirmDialog({ title: `Appliquer ${h} m à toutes les cotes de la page ?`, description: "Toutes les cotes linéaires (murs / distances) de cette page prendront cette hauteur ; les surfaces m² sont recalculées automatiquement.", confirmLabel: "Appliquer" });
    if (!ok) return;
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measurements/wall-height-bulk`, { height_m: h, page_index: pageIndex });
      toast.success(`Hauteur ${h} m appliquée à ${data.updated} cote${data.updated > 1 ? "s" : ""}`);
      const { data: full } = await api.get(`/takeoffs/${plan.plan_id}`);
      setPlan(full);
    } catch (e) { toast.error(e?.response?.data?.detail || "Application impossible"); }
  };

  const duplicatePlan = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/duplicate`);
      toast.success(`Plan dupliqué — ${data.rooms} pièce${data.rooms > 1 ? "s" : ""} copiée${data.rooms > 1 ? "s" : ""}`);
      const { data: full } = await api.get(`/takeoffs/${data.plan_id}`);
      setPlan(full);
      setPageIndex(0);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Duplication impossible");
    }
  };

  const downloadMultiQuote = async () => {
    if (multiSelected.length === 0) return toast.error("Sélectionnez au moins 1 plan");
    setMultiBusy(true);
    try {
      const { data: blob } = await api.post("/quotes/multi-pdf", {
        plan_ids: multiSelected, project_name: multiProjectName.trim() || null,
        finish: quoteFinish, floor_material: quoteFloor,
      }, { responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `devis-projet.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Devis projet (${multiSelected.length} plans) téléchargé`);
      setMultiDialog(false);
    } catch (e) { toast.error(e.message || "Export impossible"); }
    finally { setMultiBusy(false); }
  };

  const downloadMultiMetre = async () => {
    if (multiSelected.length === 0) return toast.error("Sélectionnez au moins 1 plan");
    setMultiBusy(true);
    try {
      const res = await api.post("/takeoffs/metre-multi-pdf",
        { plan_ids: multiSelected, project_name: multiProjectName.trim() || null },
        { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = "metre-groupe.pdf";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Métré groupé (${multiSelected.length} plans) téléchargé`);
      setMultiDialog(false);
    } catch (e) { toast.error(e?.response?.data?.detail || "Export impossible"); }
    finally { setMultiBusy(false); }
  };

  // Phase A — créer UN devis éditable consolidé (gros œuvre + maison + ferraillage)
  const createConsolidatedQuote = async () => {
    if (multiSelected.length === 0) return toast.error("Sélectionnez au moins 1 plan");
    setConsolidatedBusy(true);
    try {
      const { data } = await api.post("/documents/from-plans", {
        plan_ids: multiSelected,
        project_name: multiProjectName.trim() || "",
        subcontract_plan_ids: subcontractSel.filter((id) => multiSelected.includes(id)),
      });
      toast.success(`Devis consolidé créé — ${data.line_count} lignes`);
      setMultiDialog(false);
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Création du devis consolidé impossible");
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
      toast.success(ferrIds.length ? "Ferraillage rattaché" : "Rattachement retiré");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Rattachement impossible");
    }
  };

  const createSignatureLink = async (logId) => {
    const raw = window.prompt(
      "Acompte demandé à la signature (% du TTC) — 30 par défaut, ou 0 pour désactiver :",
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
        ? `Lien copié — acompte ${pct}% à la signature`
        : "Lien de signature copié (sans acompte)");
      await loadQuoteSends();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Génération du lien impossible");
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
      toast.success(`Mur reclassé : ${next}`);
      await loadWallsSummary();
    } catch { toast.error("Reclassement impossible"); }
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
      toast.error(e?.response?.data?.detail || "Comparaison impossible");
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
            <p className="overline text-primary">Fonctionnalité Pro Business</p>
            <h1 className="font-display text-3xl lg:text-4xl font-bold tracking-tight mt-3">
              Mesurer + Rendu 3D
            </h1>
            <p className="text-sm text-muted-foreground mt-3 max-w-lg mx-auto">
              L'import de plans, la mesure automatique des surfaces, le takeoff calibré et
              la génération de rendus 3D / vidéos 3D sont réservés au plan
              <b className="text-foreground"> Pro Business</b>.
              Passez sur ce plan pour débloquer ces outils métier.
            </p>
          </div>
          <div className="grid sm:grid-cols-3 gap-3 max-w-xl mx-auto">
            {[
              "Import PDF/DXF/photo",
              "Calibration + mesures pro",
              "Rendu 3D + vidéo",
            ].map((f) => (
              <div key={f} className="border border-border rounded-sm p-3 text-xs">
                {f}
              </div>
            ))}
          </div>
          <div className="flex items-center justify-center gap-3 flex-wrap">
            <Button
              onClick={() => nav("/tarifs")}
              data-testid="plan-paywall-upgrade"
              className="rounded-sm h-11 px-6"
            >
              Passer sur Pro Business
            </Button>
            <Button
              variant="outline"
              onClick={() => nav("/dashboard")}
              className="rounded-sm h-11 px-6"
            >
              Retour tableau de bord
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Votre plan actuel : <b>{tier || "free"}</b>
          </p>
        </div>
      </div>
    );
  }

  if (!plan) {
    return (
      <div className="plan-workspace mx-auto max-w-[1100px] px-5 py-10 grid gap-8">
      {cadFile && <CadUnitPicker file={cadFile} onChoose={chooseCadUnit} onCancel={() => chooseCadUnit(null)} />}
      <Dialog open={pendingFiles.length > 0} onOpenChange={(o) => { if (!o && !importingBatch) { setPendingFiles([]); setGroupImport({ enabled: false, mode: "new", name: "", groupId: "" }); } }}>
        <DialogContent className="rounded-sm max-w-lg" data-testid="plan-import-dialog">
          <DialogHeader>
            <DialogTitle>Importer {pendingFiles.length} plan{pendingFiles.length > 1 ? "s" : ""}</DialogTitle>
            <DialogDescription>
              Donnez un nom à chaque plan avant l'import. Ce nom sera affiché dans la liste et repris dans les exports PDF.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 max-h-[50vh] overflow-auto pr-1">
            {pendingFiles.map((it, idx) => (
              <div key={it.id} className="flex items-center gap-2" data-testid={`pending-file-${idx}`}>
                <Input value={it.name} disabled={importingBatch}
                       onChange={(e) => setPendingFiles((prev) => prev.map((p) => p.id === it.id ? { ...p, name: e.target.value } : p))}
                       data-testid={`pending-file-name-${idx}`}
                       className="h-9 flex-1" placeholder="Nom du plan" />
                {groupImport.enabled && (
                  <Input value={it.level || ""} disabled={importingBatch} list="level-suggestions-import"
                         onChange={(e) => setPendingFiles((prev) => prev.map((p) => p.id === it.id ? { ...p, level: e.target.value } : p))}
                         data-testid={`pending-file-level-${idx}`}
                         className="h-9 w-24 shrink-0" placeholder="Niveau" />
                )}
                <span className="text-[10px] text-muted-foreground truncate max-w-[120px]" title={it.file.name}>
                  {it.file.name.split(".").pop()?.toUpperCase()} · {(it.file.size / (1024 * 1024)).toFixed(1)} Mo
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
              <Plus className="h-4 w-4" /> Ajouter d'autres plans
            </button>
          </div>
          <datalist id="level-suggestions-import">{LEVEL_SUGGESTIONS.map((s) => <option key={s} value={s} />)}</datalist>
          <div className="rounded-sm border border-border p-3 space-y-2 bg-muted/30">
            <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
              <input type="checkbox" checked={groupImport.enabled} disabled={importingBatch}
                     onChange={(e) => setGroupImport((g) => ({ ...g, enabled: e.target.checked }))}
                     data-testid="group-import-toggle" className="accent-primary h-4 w-4" />
              <Layers className="h-4 w-4 text-primary" /> Regrouper en projet multi-niveaux (un seul rapport consolidé)
            </label>
            {groupImport.enabled && (
              <div className="space-y-2">
                <div className="flex gap-2">
                  <button type="button" onClick={() => setGroupImport((g) => ({ ...g, mode: "new" }))}
                          data-testid="group-mode-new"
                          className={`flex-1 text-xs font-semibold rounded-sm border px-2 py-1.5 ${groupImport.mode === "new" ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>
                    Nouveau projet
                  </button>
                  <button type="button" disabled={planGroups.length === 0}
                          onClick={() => setGroupImport((g) => ({ ...g, mode: "existing", groupId: g.groupId || planGroups[0]?.group_id || "" }))}
                          data-testid="group-mode-existing"
                          className={`flex-1 text-xs font-semibold rounded-sm border px-2 py-1.5 disabled:opacity-40 ${groupImport.mode === "existing" ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>
                    Projet existant
                  </button>
                </div>
                {groupImport.mode === "existing" ? (
                  <select value={groupImport.groupId} disabled={importingBatch}
                          onChange={(e) => setGroupImport((g) => ({ ...g, groupId: e.target.value }))}
                          data-testid="group-import-select"
                          className="w-full h-9 rounded-sm border border-border bg-background px-2 text-sm">
                    {planGroups.map((g) => <option key={g.group_id} value={g.group_id}>{g.name} ({(g.levels || []).length} niveaux)</option>)}
                  </select>
                ) : (
                  <Input value={groupImport.name} disabled={importingBatch}
                         onChange={(e) => setGroupImport((g) => ({ ...g, name: e.target.value }))}
                         data-testid="group-import-name" className="h-9" placeholder="Nom du projet (ex : Maison Dupont)" />
                )}
                <p className="text-[11px] text-muted-foreground">Les niveaux (RDC, R+1…) sont pré-remplis automatiquement. Mesurez ensuite chaque niveau : le métré et le chiffrage sont consolidés en un seul rapport.</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={importingBatch} onClick={() => { setPendingFiles([]); setGroupImport({ enabled: false, mode: "new", name: "", groupId: "" }); }} className="rounded-sm">Annuler</Button>
            <Button onClick={importPending} disabled={importingBatch || pendingFiles.some((p) => !p.name.trim()) || (groupImport.enabled && groupImport.mode === "new" && !groupImport.name.trim()) || (groupImport.enabled && groupImport.mode === "existing" && !groupImport.groupId)}
                    data-testid="plan-import-confirm" className="rounded-sm gap-2">
              {importingBatch ? "Import en cours…" : groupImport.enabled ? (groupImport.mode === "existing" ? "Importer et rattacher" : "Importer et créer le projet") : "Importer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
        {chantierId && <ChantierContextBar chantierId={chantierId} chantier={chantier} />}
        <div className="plan-library-hero">
          <p className="plan-eyebrow">PLANS & MÉTRÉS · CONSTRUPILOT</p>
          <h1 className="mt-3 font-display text-4xl lg:text-5xl font-bold tracking-tight">
            Du plan au devis, dans un même espace.
          </h1>
          <p className="text-sm text-muted-foreground mt-3 max-w-2xl">
            Importez vos documents, renseignez l’échelle, analysez et vérifiez les quantités.
            Retrouvez ensuite vos métrés et votre chiffrage dans le même dossier.
          </p>
          <div className="mt-4">
            <MeasureHelpDialog />
          </div>
        </div>

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
              {uploading ? "Import en cours…" : dragActive ? "Relâchez pour importer" : "Importer mon plan"}
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              PDF · DXF · DWG · JPG · PNG · WEBP · ZIP — jusqu'à 20 Mo — sélectionnez plusieurs fichiers, un dossier ou un ZIP
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
            <Layers className="h-4 w-4" /> Importer plusieurs plans d'un coup
          </Button>
          <Button type="button" variant="outline" disabled={uploading}
                  onClick={() => document.getElementById("plan-folder-input")?.click()}
                  data-testid="import-folder-btn" className="rounded-sm gap-2">
            <Upload className="h-4 w-4" /> Importer un dossier / ZIP
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
            Corriger la perspective (photo smartphone inclinée)
          </label>
          <button
            onClick={() => nav("/plan/compare")}
            data-testid="plan-compare-link"
            className="text-sm text-primary hover:underline gap-1 inline-flex items-center"
          >
            Comparer 2 plans (avant / après) →
          </button>
        </div>

        <div className="grid sm:grid-cols-3 gap-4">
          {[
            { icon: Ruler, title: "Formats variés", desc: "PDF · DXF · DWG · JPG · PNG · WEBP — DWG converti automatiquement" },
            { icon: Wand2, title: "Détection auto", desc: "Murs (OpenCV) · pièces flood-fill · deskew photo inclinée" },
            { icon: Calculator, title: "Multi-étages", desc: "RDC · R+1 · R+2 · combles — métré par niveau + total" },
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
                <History className="h-4 w-4" /> Mes plans récents
              </p>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-muted-foreground">
                  {allPlans.length} plan{allPlans.length > 1 ? "s" : ""} enregistré{allPlans.length > 1 ? "s" : ""}
                </span>
                {selectedRecent.length > 0 && (
                  <Button variant="outline" size="sm" onClick={() => bulkTrashPlans(selectedRecent)}
                          data-testid="trash-selected-plans-btn"
                          className="rounded-sm gap-1 h-8 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
                    <Trash2 className="h-3.5 w-3.5" /> Supprimer la sélection ({selectedRecent.length})
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={trashAllPlans}
                        data-testid="trash-all-plans-btn"
                        className="rounded-sm gap-1 h-8 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
                  <Trash2 className="h-3.5 w-3.5" /> Tout supprimer
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
                      toast.error("Impossible d'ouvrir ce plan");
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
                      {p.filename || "Plan sans nom"}
                    </p>
                    <Badge variant="outline" className="text-[10px] rounded-sm shrink-0">
                      {p.rooms_count || 0} pce
                    </Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    {p.page_count || 1} page{p.page_count > 1 ? "s" : ""}
                    {p.created_at && (
                      <span> · {new Date(p.created_at).toLocaleDateString("fr-FR")}</span>
                    )}
                  </p>
                </button>
                <button type="button" onClick={() => nav(`/analyse/${p.plan_id}`)} title="Analyse traçable (métré → devis)" aria-label="Analyse traçable"
                  className="absolute bottom-2 right-11 h-8 w-8 inline-flex items-center justify-center rounded-sm text-muted-foreground opacity-60 group-hover:opacity-100 hover:text-primary hover:bg-primary/10 transition-colors"
                  data-testid={`recent-plan-analysis-${p.plan_id}`}>
                  <ClipboardCheck className="h-3.5 w-3.5" />
                </button>
                <button type="button" onClick={() => trashPlan(p)} title="Mettre à la corbeille" aria-label="Mettre à la corbeille"
                  className="absolute bottom-2 right-2 h-8 w-8 inline-flex items-center justify-center rounded-sm text-muted-foreground opacity-60 group-hover:opacity-100 hover:text-destructive hover:bg-destructive/10 transition-colors"
                  data-testid={`recent-plan-delete-${p.plan_id}`}>
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
                </div>
              ))}
            </div>
            {allPlans.length > 6 && (
              <p className="text-xs text-muted-foreground mt-3 text-center">
                + {allPlans.length - 6} autres — utilisez « Comparer 2 plans » pour tout voir
              </p>
            )}
          </div>
        )}

        {/* PROJETS MULTI-NIVEAUX */}
        <div className="surface p-5" data-testid="plan-groups-section">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="font-display font-bold flex items-center gap-2"><Layers className="h-4 w-4 text-primary" /> Projets multi-niveaux</p>
              <p className="text-[11px] text-muted-foreground">Regroupez Fondations, RDC, R+1… d'un même chantier — métré et chiffrage consolidés.</p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={openAgentBox} data-testid="open-agents-btn" className="rounded-sm gap-1">
                <Bot className="h-4 w-4 text-primary" /> Agents IA
              </Button>
              <Button size="sm" onClick={openGroupBuilder} data-testid="new-plan-group-btn" className="rounded-sm gap-1">
                <Plus className="h-4 w-4" /> Nouveau projet
              </Button>
            </div>
          </div>
          {planGroups.length === 0 ? (
            <p className="text-xs text-muted-foreground">Aucun projet multi-niveaux pour l'instant.</p>
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
                      <button onClick={() => editGroup(g)} title="Modifier" data-testid={`edit-group-${g.group_id}`} className="text-muted-foreground hover:text-primary"><Search className="h-3.5 w-3.5" /></button>
                      <button onClick={() => deleteGroup(g)} title="Supprimer" data-testid={`delete-group-${g.group_id}`} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
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
              <DialogTitle>{groupBuilder?.group_id ? "Modifier le projet" : "Nouveau projet multi-niveaux"}</DialogTitle>
              <DialogDescription>Nommez le projet, ajoutez les plans et étiquetez chaque niveau.{chantierId ? " Les plans seront rattachés au dossier chantier courant." : ""}</DialogDescription>
            </DialogHeader>
            {groupBuilder && (
              <div className="space-y-3">
                <Input value={groupBuilder.name} onChange={(e) => setGroupBuilder((gb) => ({ ...gb, name: e.target.value }))}
                       placeholder="Nom du projet (ex : Maison Dupont)" data-testid="group-name-input" className="h-9" />
                <div>
                  <Label className="text-xs">Niveaux du projet ({groupBuilder.levels.length})</Label>
                  <div className="space-y-1.5 mt-1 max-h-40 overflow-auto">
                    {groupBuilder.levels.map((l) => {
                      const p = allPlans.find((x) => x.plan_id === l.plan_id);
                      return (
                        <div key={l.plan_id} className="flex items-center gap-2" data-testid={`group-level-${l.plan_id}`}>
                          <Input value={l.level_label} onChange={(e) => setLevelLabel(l.plan_id, e.target.value)}
                                 list="level-suggestions" placeholder="Niveau" className="h-8 w-32 text-xs" data-testid={`group-level-label-${l.plan_id}`} />
                          <span className="text-[11px] flex-1 truncate">{p?.filename || l.plan_id}</span>
                          <button onClick={() => removeLevel(l.plan_id)} className="text-muted-foreground hover:text-destructive"><X className="h-4 w-4" /></button>
                        </div>
                      );
                    })}
                    {groupBuilder.levels.length === 0 && <p className="text-[11px] text-muted-foreground">Ajoutez des plans depuis la liste ci-dessous.</p>}
                  </div>
                  <datalist id="level-suggestions">{LEVEL_SUGGESTIONS.map((s) => <option key={s} value={s} />)}</datalist>
                </div>
                <div>
                  <Label className="text-xs">Plans disponibles</Label>
                  <div className="flex flex-wrap gap-1.5 mt-1 max-h-32 overflow-auto">
                    {allPlans.filter((p) => !groupBuilder.levels.some((l) => l.plan_id === p.plan_id)).map((p) => (
                      <button key={p.plan_id} onClick={() => addLevel(p.plan_id)}
                              data-testid={`add-plan-${p.plan_id}`}
                              className="rounded-full border border-border px-2 py-0.5 text-[11px] hover:border-primary hover:text-primary">
                        + {p.filename || p.plan_id}
                      </button>
                    ))}
                    {allPlans.length === 0 && <p className="text-[11px] text-muted-foreground">Importez d'abord des plans.</p>}
                  </div>
                </div>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setGroupBuilder(null)} className="rounded-sm">Annuler</Button>
              <Button onClick={saveGroup} data-testid="group-save-btn" className="rounded-sm gap-2"><Save className="h-4 w-4" /> Enregistrer</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* DIALOG — vue consolidée */}
        <Dialog open={!!groupView} onOpenChange={(o) => { if (!o) setGroupView(null); }}>
          <DialogContent className="rounded-sm max-w-2xl" data-testid="group-consolidated-dialog">
            <DialogHeader>
              <DialogTitle>Consolidé — {groupView?.name}</DialogTitle>
              <DialogDescription>Métré et chiffrage des mesures enregistrées. Le budget complet du chantier reste à établir.</DialogDescription>
            </DialogHeader>
            {groupView?.loading ? (
              <div className="py-8 text-center text-sm text-muted-foreground">Calcul en cours…</div>
            ) : groupView && (
              <div className="space-y-2 max-h-[55vh] overflow-auto">
                <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950" data-testid="group-scope-warning">
                  <p className="font-semibold">Estimation partielle</p>
                  <ul className="mt-1 list-disc space-y-1 pl-4">
                    {(groupView.coverage?.warnings || ["Le montant porte uniquement sur les mesures enregistrées, pas sur l’ensemble des bâtiments et des lots."]).map((warning, index) => <li key={index}>{warning}</li>)}
                  </ul>
                </div>
                {(groupView.levels || []).map((lv) => (
                  <div key={lv.plan_id} className="rounded border border-border p-2" data-testid={`consolidated-level-${lv.plan_id}`}>
                    <div className="flex flex-wrap justify-between items-center text-sm font-medium gap-2">
                      <span className="truncate">{lv.level_label || "Niveau"} <span className="text-muted-foreground text-xs">· {lv.filename || lv.plan_id}</span></span>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="num">{lv.consolidated?.chiffrage?.priced_measures > 0 ? `${lv.consolidated.chiffrage.ht_with_margin.toFixed(2)} € HT partiel` : "Non chiffré"}</span>
                        <Button size="sm" variant="outline" data-testid={`consolidated-open-${lv.plan_id}`}
                                onClick={() => { setGroupView(null); openPlanById(lv.plan_id); }}
                                className="rounded-sm h-7 gap-1 text-xs border-primary/50 text-primary hover:bg-primary hover:text-white">
                          <Pencil className="h-3 w-3" /> Modifier
                        </Button>
                      </div>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {lv.consolidated?.metre?.area_m2 || 0} m² · {lv.consolidated?.metre?.length_ml || 0} ml · {lv.consolidated?.metre?.measures || 0} mesures ({lv.consolidated?.chiffrage?.priced_measures || 0} chiffrées)
                    </div>
                  </div>
                ))}
                <div className="flex flex-col gap-2 sm:flex-row sm:justify-between border-t border-border pt-2 text-sm font-semibold">
                  <span>Sous-total mesuré · {groupView.totals?.area_m2 || 0} m² · {groupView.totals?.length_ml || 0} ml</span>
                  {(groupView.levels || []).some((lv) => lv.consolidated?.chiffrage?.priced_measures > 0) ? <span>HT <span className="num">{groupView.totals?.ht_with_margin?.toFixed(2)} €</span> · TTC <span className="num text-primary">{groupView.totals?.ttc?.toFixed(2)} €</span></span> : <span>Non chiffré</span>}
                </div>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setGroupView(null)} className="rounded-sm">Fermer</Button>
              {!groupView?.loading && (
                <>
                  <Button variant="outline" onClick={() => openCoverDialog()} data-testid="group-pdf-btn" className="rounded-sm gap-2">
                    <FileDown className="h-4 w-4" /> Dossier PDF
                  </Button>
                  <Button variant="outline" onClick={downloadGroupMetrePdf} data-testid="group-metre-pdf-btn" className="rounded-sm gap-2">
                    <Ruler className="h-4 w-4" /> Métré seul (sans prix)
                  </Button>
                  <Button onClick={createGroupQuote} data-testid="group-create-quote-btn" className="rounded-sm gap-2">
                    <ArrowRight className="h-4 w-4" /> Créer un devis partiel
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
              <DialogTitle>Page de garde du dossier</DialogTitle>
              <DialogDescription>
                Coordonnées client imprimées sur la couverture. Pré-remplies depuis le chantier, modifiables ici.
              </DialogDescription>
            </DialogHeader>
            {coverDialog?.loading ? (
              <div className="py-8 text-center text-sm text-muted-foreground">Chargement…</div>
            ) : coverDialog && (
              <div className="space-y-3">
                <div className="text-xs text-muted-foreground">
                  Référence dossier : <span className="font-semibold text-foreground">{coverDialog.reference || "—"}</span>
                  <span className="mx-1">·</span> Logo &amp; société repris de votre « Identité pro »
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Nom du client</Label>
                  <Input value={coverDialog.name} onChange={(e) => setCoverDialog((d) => ({ ...d, name: e.target.value }))}
                    placeholder="M. et Mme Dupont" data-testid="cover-client-name" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Société (optionnel)</Label>
                  <Input value={coverDialog.company} onChange={(e) => setCoverDialog((d) => ({ ...d, company: e.target.value }))}
                    data-testid="cover-client-company" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Adresse</Label>
                  <Input value={coverDialog.address} onChange={(e) => setCoverDialog((d) => ({ ...d, address: e.target.value }))}
                    placeholder="12 rue des Travaux" data-testid="cover-client-address" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Code postal &amp; ville</Label>
                  <Input value={coverDialog.city} onChange={(e) => setCoverDialog((d) => ({ ...d, city: e.target.value }))}
                    placeholder="75001 Paris" data-testid="cover-client-city" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">E-mail</Label>
                    <Input value={coverDialog.email} onChange={(e) => setCoverDialog((d) => ({ ...d, email: e.target.value }))}
                      data-testid="cover-client-email" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Téléphone</Label>
                    <Input value={coverDialog.phone} onChange={(e) => setCoverDialog((d) => ({ ...d, phone: e.target.value }))}
                      data-testid="cover-client-phone" />
                  </div>
                </div>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setCoverDialog(null)} className="rounded-sm">Annuler</Button>
              <Button onClick={() => downloadGroupPdf()} disabled={coverDialog?.loading} data-testid="cover-generate-btn" className="rounded-sm gap-2">
                <FileDown className="h-4 w-4" /> Générer le dossier PDF
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* DIALOG — Affectation auto des postes (validation avant chiffrage) */}
        <Dialog open={!!autoPosteDialog} onOpenChange={(o) => { if (!o) setAutoPosteDialog(null); }}>
          <DialogContent className="rounded-sm max-w-xl z-[70]" overlayClassName="z-[70]" data-testid="auto-poste-dialog">
            <DialogHeader>
              <DialogTitle>Chiffrer la page — postes proposés</DialogTitle>
              <DialogDescription>
                Un poste a été proposé pour chaque cote d'après son titre. Vérifiez et corrigez si besoin, puis chiffrez. Les prix viennent de votre bibliothèque (calcul déterministe).
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
              <span className="text-muted-foreground">Marge (%)</span>
              <Input type="number" value={chiffrageMargin} onChange={(e) => setChiffrageMargin(e.target.value)} className="h-8 w-20" data-testid="auto-poste-margin" />
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setAutoPosteDialog(null)} className="rounded-sm">Annuler</Button>
              <Button onClick={confirmAutoPoste} className="rounded-sm gap-2" data-testid="auto-poste-confirm"><Calculator className="h-4 w-4" /> Affecter et chiffrer</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* DIALOG — Agents IA */}
        <Dialog open={!!agentBox} onOpenChange={(o) => { if (!o) setAgentBox(null); }}>          <DialogContent className="rounded-sm max-w-2xl" data-testid="agents-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2"><Bot className="h-5 w-5 text-primary" /> Agents IA</span>
                <Button variant="ghost" size="sm" className="rounded-sm gap-1 text-xs" data-testid="agent-history-btn"
                  onClick={() => { loadAgentHistory(); setAgentBox((a) => ({ ...a, step: a.step === "history" ? "pick" : "history" })); }}>
                  <History className="h-3.5 w-3.5" /> Historique
                </Button>
              </DialogTitle>
              <DialogDescription>
                L'agent propose un plan d'actions, vous le validez, puis il exécute avec vos moteurs déterministes. Vous pouvez revoir et corriger — il retient vos corrections.
              </DialogDescription>
            </DialogHeader>

            {agentBox?.step === "history" && (
              <div className="space-y-2 max-h-[60vh] overflow-auto" data-testid="agent-history-list">
                {agentHistory === null && <p className="text-sm text-muted-foreground p-4 text-center">Chargement…</p>}
                {agentHistory?.length === 0 && <p className="text-sm text-muted-foreground p-4 text-center">Aucune exécution d'agent pour l'instant.</p>}
                {(agentHistory || []).map((r) => (
                  <div key={r.run_id} className="rounded-lg border border-border p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{(AGENT_CATALOG.find((a) => a.key === r.agent) || {}).name || r.agent}</span>
                      <span className={`text-[11px] px-2 py-0.5 rounded-full ${r.status === "done" ? "bg-green-100 text-green-700" : "bg-muted text-muted-foreground"}`}>{r.status === "done" ? "Exécuté" : "Proposé"}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-1">{new Date(r.created_at).toLocaleString("fr-FR")}{r.result?.totals ? ` · Total TTC ${(r.result.totals.ttc || 0).toLocaleString("fr-FR")} €` : ""}</p>
                    {r.feedback?.rating && <p className="text-[11px] mt-1">{r.feedback.rating === "ok" ? "✓ Validé par vous" : "✎ Correction enregistrée"}{r.feedback.note ? ` — « ${r.feedback.note} »` : ""}</p>}
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
                    Cet agent ouvre l'atelier <b>DPGF → devis</b> : importez votre DPGF/CCTP, il lit le bordereau, applique vos prix et prépare le devis chiffré.
                  </div>
                ) : (
                  <>
                    <div className="space-y-1">
                      <Label className="text-xs">Votre demande (optionnel)</Label>
                      <Input value={agentBox.prompt} onChange={(e) => setAgentBox((a) => ({ ...a, prompt: e.target.value }))}
                        placeholder="Ex. Fais le dossier complet de cette maison R+1" data-testid="agent-prompt" />
                    </div>
                    <div>
                      <Label className="text-xs">Plans concernés {agentBox.agent === "compare" && <span className="text-primary">(exactement 2 : avant / après)</span>}</Label>
                      <div className="mt-1 grid gap-1 max-h-48 overflow-auto rounded border border-border p-2">
                        {(allPlans || []).length === 0 && <p className="text-xs text-muted-foreground p-2">Aucun plan disponible.</p>}
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
                  <p className="text-xs font-semibold text-primary mb-2">Plan d'actions proposé</p>
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
                  <Label className="text-xs">Niveaux (corrigez si besoin — l'agent apprend)</Label>
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
                      <Label className="text-xs">Marge (%)</Label>
                      <Input type="number" value={agentBox.params.margin_pct} onChange={(e) => setAgentBox((a) => ({ ...a, params: { ...a.params, margin_pct: parseFloat(e.target.value) || 0 } }))} className="h-8" data-testid="agent-margin" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Nom du projet</Label>
                      <Input value={agentBox.params.project_name} onChange={(e) => setAgentBox((a) => ({ ...a, params: { ...a.params, project_name: e.target.value } }))} className="h-8" data-testid="agent-project-name" />
                    </div>
                  </div>
                )}
                {agentBox.agent === "report" && (
                  <div className="grid grid-cols-2 gap-3">
                    <Input value={agentBox.params.client_name} onChange={(e) => setAgentBox((a) => ({ ...a, params: { ...a.params, client_name: e.target.value } }))} placeholder="Client (nom)" className="h-8" data-testid="agent-client-name" />
                    <Input value={agentBox.params.client_city} onChange={(e) => setAgentBox((a) => ({ ...a, params: { ...a.params, client_city: e.target.value } }))} placeholder="Ville" className="h-8" data-testid="agent-client-city" />
                  </div>
                )}
              </div>
            )}

            {agentBox?.step === "result" && agentBox.result && (
              <div className="space-y-3">
                <div className="rounded-lg border border-green-300 bg-green-50 p-3 text-sm text-green-800" data-testid="agent-result">
                  <p className="font-semibold">✓ Agent terminé</p>
                  {agentBox.result.kind === "pdf" && <p className="text-[12px] mt-1">Dossier généré · {agentBox.result.levels} niveau(x) · Total TTC {(agentBox.result.totals?.ttc || 0).toLocaleString("fr-FR")} €</p>}
                  {agentBox.result.kind === "quote" && <p className="text-[12px] mt-1">Devis consolidé créé — modifiable dans l'éditeur.</p>}
                  {agentBox.result.kind === "summary" && <p className="text-[12px] mt-1">{agentBox.result.total_measures} mesures · {agentBox.result.total_openings} ouvertures sur {agentBox.result.plans?.length} plan(s).</p>}
                  {agentBox.result.kind === "detect" && <p className="text-[12px] mt-1">{agentBox.result.total_walls} murs · {agentBox.result.total_openings} ouvertures détectés. <b>Étalonnage requis</b> : ouvrez le plan et saisissez une cote connue avant tout métré.</p>}
                  {agentBox.result.kind === "compare" && (
                    <div className="text-[12px] mt-1 space-y-0.5">
                      <p>Avant : {agentBox.result.diff.before.room_count} pièce(s) · {agentBox.result.diff.before.total_surface_m2} m² — Après : {agentBox.result.diff.after.room_count} pièce(s) · {agentBox.result.diff.after.total_surface_m2} m²</p>
                      <p>Écart surface : {agentBox.result.diff.delta_surface_m2} m² ({agentBox.result.diff.delta_surface_pct}%)</p>
                      <p>+{agentBox.result.diff.added.length} ajoutée(s) · −{agentBox.result.diff.removed.length} retirée(s) · {agentBox.result.diff.modified.length} modifiée(s)</p>
                    </div>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">Vérifiez le résultat. {(agentBox.agent === "report" || agentBox.agent === "devis") ? "S'il y a une erreur, corrigez les niveaux et relancez — l'agent retiendra la correction." : ""}</p>
                <div className="flex flex-wrap gap-2">
                  {agentBox.result.download && <Button onClick={agentDownload} className="rounded-sm gap-2" data-testid="agent-download"><FileDown className="h-4 w-4" /> Télécharger</Button>}
                  {agentBox.result.edit && <Button variant="outline" onClick={() => nav(agentBox.result.edit)} className="rounded-sm gap-2" data-testid="agent-open-quote"><ArrowRight className="h-4 w-4" /> Ouvrir le devis</Button>}
                  {agentBox.result.kind === "detect" && agentBox.result.edit_plan_id && <Button onClick={() => openPlanById(agentBox.result.edit_plan_id)} className="rounded-sm gap-2" data-testid="agent-open-plan"><Ruler className="h-4 w-4" /> Ouvrir le plan pour étalonner</Button>}
                  {agentBox.result.kind === "compare" && <Button variant="outline" onClick={() => { setAgentBox(null); nav(`/plan/compare?a=${agentBox.result.before_plan_id}&b=${agentBox.result.after_plan_id}`); }} className="rounded-sm gap-2" data-testid="agent-open-compare"><GitCompare className="h-4 w-4" /> Comparatif détaillé</Button>}
                </div>
              </div>
            )}

            <DialogFooter>
              {agentBox?.step === "history" && (
                <Button variant="outline" onClick={() => setAgentBox((a) => ({ ...a, step: "pick" }))} className="rounded-sm">Retour</Button>
              )}
              {agentBox?.step === "pick" && (
                <>
                  <Button variant="outline" onClick={() => setAgentBox(null)} className="rounded-sm">Annuler</Button>
                  <Button onClick={agentPropose} disabled={agentBox.loading} className="rounded-sm gap-2" data-testid="agent-propose-btn"><Bot className="h-4 w-4" /> {agentBox.loading ? "Analyse…" : agentBox.agent === "dpgf" ? "Ouvrir l'atelier DPGF" : "Proposer un plan"}</Button>
                </>
              )}
              {agentBox?.step === "plan" && (
                <>
                  <Button variant="outline" onClick={() => setAgentBox((a) => ({ ...a, step: "pick" }))} className="rounded-sm">Retour</Button>
                  <Button onClick={agentExecute} disabled={agentBox.loading} className="rounded-sm gap-2" data-testid="agent-execute-btn"><Wand2 className="h-4 w-4" /> {agentBox.loading ? "Exécution…" : "Valider et exécuter"}</Button>
                </>
              )}
              {agentBox?.step === "result" && (
                (agentBox.agent === "report" || agentBox.agent === "devis") ? (
                  <>
                    <Button variant="outline" onClick={() => agentFeedback("error")} className="rounded-sm" data-testid="agent-feedback-error">Signaler une erreur / corriger</Button>
                    <Button onClick={() => agentFeedback("ok")} className="rounded-sm gap-2" data-testid="agent-feedback-ok"><Sparkles className="h-4 w-4" /> C'est parfait</Button>
                  </>
                ) : (
                  <Button onClick={() => setAgentBox(null)} className="rounded-sm" data-testid="agent-close">Fermer</Button>
                )
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>

      </div>
    );
  }

  return (
    <div className="plan-workspace mx-auto w-full min-w-0 max-w-[1600px] px-3 sm:px-5 py-6" data-testid="plan-workspace">
      {chantierId && <div className="mb-4"><ChantierContextBar chantierId={chantierId} chantier={chantier} /></div>}
      <CadImportInfo info={plan?.cad_import} />
      {cadFile && <CadUnitPicker file={cadFile} onChoose={chooseCadUnit} onCancel={() => chooseCadUnit(null)} />}
      <Dialog open={customPosteOpen} onOpenChange={setCustomPosteOpen}>
        <DialogContent className="z-[80] max-w-lg" overlayClassName="z-[80]" data-testid="custom-postes-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Plus className="h-4 w-4" /> Ouvrages personnalisés</DialogTitle>
            <DialogDescription>Créez vos propres postes avec votre prix unitaire (fourniture + pose). Ils apparaissent dans le catalogue de chiffrage.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid grid-cols-[1fr_84px_110px] gap-2 items-end">
              <div className="grid gap-1">
                <Label className="text-xs">Nom de l'ouvrage</Label>
                <Input value={cpForm.label} onChange={(e) => setCpForm((f) => ({ ...f, label: e.target.value }))}
                       placeholder="Ex : Faux plafond coupe-feu 1h" maxLength={60}
                       data-testid="custom-poste-label" className="rounded-sm h-9 text-sm" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Unité</Label>
                <select value={cpForm.unit} onChange={(e) => setCpForm((f) => ({ ...f, unit: e.target.value }))}
                        data-testid="custom-poste-unit"
                        className="rounded-sm h-9 border border-border bg-background px-2 text-sm outline-none focus:border-primary">
                  <option value="m2">m²</option><option value="ml">ml</option><option value="u">u</option>
                </select>
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Prix HT /u (€)</Label>
                <Input type="number" value={cpForm.pu} onChange={(e) => setCpForm((f) => ({ ...f, pu: e.target.value }))}
                       placeholder="55" data-testid="custom-poste-pu" className="rounded-sm h-9 text-sm" />
              </div>
            </div>
            <Button onClick={saveCustomPoste} data-testid="custom-poste-save" className="rounded-sm gap-2 justify-self-start">
              <Plus className="h-4 w-4" /> Ajouter au catalogue
            </Button>
            <div className="border-t border-border pt-2">
              <p className="overline mb-2">Mes ouvrages ({customPostes.length})</p>
              {customPostes.length === 0 && <p className="text-sm text-muted-foreground">Aucun ouvrage personnalisé pour l'instant.</p>}
              <div className="grid gap-1 max-h-56 overflow-y-auto">
                {customPostes.map((c) => (
                  <div key={c.key} className="flex items-center justify-between gap-2 surface px-3 py-2 rounded-sm"
                       data-testid={`custom-poste-row-${c.key}`}>
                    <span className="text-sm truncate flex-1">{c.label}</span>
                    <span className="num text-xs text-primary shrink-0">{Number(c.pu).toFixed(2)} € / {c.unit === "m2" ? "m²" : c.unit}</span>
                    <button onClick={() => deleteCustomPoste(c.key)} title="Supprimer"
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
            <DialogTitle className="flex items-center gap-2"><History className="h-4 w-4" /> Mes plans récents</DialogTitle>
            <DialogDescription>Ouvrez un plan ou un projet multi-niveaux sans quitter l'éditeur. Cochez des plans pour les supprimer en lot.</DialogDescription>
          </DialogHeader>
          <div className="flex items-center justify-end gap-2 flex-wrap pb-1">
            {selectedRecent.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => bulkTrashPlans(selectedRecent)}
                      data-testid="dialog-trash-selected-btn"
                      className="rounded-sm gap-1 h-8 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
                <Trash2 className="h-3.5 w-3.5" /> Supprimer la sélection ({selectedRecent.length})
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={trashAllPlans}
                    data-testid="dialog-trash-all-btn"
                    className="rounded-sm gap-1 h-8 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
              <Trash2 className="h-3.5 w-3.5" /> Tout supprimer ({allPlans.length})
            </Button>
          </div>
          <div className="space-y-5 max-h-[60vh] overflow-y-auto pr-1">
            <div>
              <p className="overline mb-2">Plans ({allPlans.length})</p>
              {allPlans.length === 0 && <p className="text-sm text-muted-foreground">Aucun plan enregistré.</p>}
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
                        <p className="font-display font-bold text-sm truncate">{p.filename || "Plan sans nom"}</p>
                        <p className="text-[11px] text-muted-foreground mt-1">
                          {(p.page_count || 1)} page{(p.page_count || 1) > 1 ? "s" : ""} · {p.rooms_count || 0} pièce{(p.rooms_count || 0) > 1 ? "s" : ""}
                          {p.created_at && <span> · {new Date(p.created_at).toLocaleDateString("fr-FR")}</span>}
                          {plan?.plan_id === p.plan_id && <span className="text-primary"> · ouvert</span>}
                        </p>
                      </div>
                    </button>
                  </div>
                ))}
              </div>
            </div>
            {planGroups.length > 0 && (
              <div>
                <p className="overline mb-2">Projets multi-niveaux ({planGroups.length})</p>
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
          { id: "open-recent-plans-btn", label: "Mes plans récents", run: () => { loadAllPlans(); loadPlanGroups(); setRecentDialog(true); } },
          { id: "plan-back-btn", label: "Importer un autre plan", run: () => setPlan(null) },
          { id: "plan-duplicate-btn", label: "Dupliquer ce plan", run: duplicatePlan },
          { id: "metre-versions-btn", label: "Versions du métré", run: openMetreVersions },
          { id: "document-danger", separator: true },
          { id: "plan-clear-all-btn", label: "Effacer les mesures de cette page…", run: clearAllMeasures, danger: true },
        ]}
        exportActions={[
          { id: "plan-pdf-export-btn", label: "Métré PDF", run: downloadPdf },
          { id: "plan-metre-noprice-btn", label: "Métré sans prix", run: downloadPlanMetre },
          { id: "plan-xlsx-export-btn", label: "Tableur Excel", run: downloadXlsx },
          { id: "plan-quote-pdf-btn", label: "Devis PDF", run: () => { setQuoteDialog(true); loadTemplates(); loadQuoteSends(); loadVideoHistory(); } },
          { id: "plan-multi-quote-btn", label: "Consolider plusieurs plans", run: () => { setMultiDialog(true); loadAllPlans(); } },
        ]}
        studyActions={[
          { id: "plan-estimate-btn", label: "Estimation", run: () => { setEstimateDialog(true); setEstimateResult(null); } },
          { id: "plan-review-btn", label: "Contrôle des cotes de cette page", run: () => { setRightTab("ai"); document.getElementById("plan-results-panel")?.scrollIntoView({ block: "start" }); } },
          { id: "plan-pc-study-btn", label: "Étude du permis de construire", run: () => setPcDialog(true) },
          (plan.structural_metre || plan.kind === "dxf") && { id: "plan-structural-btn", label: "Métré depuis les calques CAD", run: () => setStructDialog(true) },
          { id: "plan-render-3d-btn", label: "Visualisation 3D", run: () => { setRender3dDialog(true); setRender3dImg(null); setVideoUrl(null); setCreditPaywall(null); loadRender3dHistory(); loadVideoHistory(); loadCredits3d(); } },
          { id: "plan-tools-separator", separator: true },
          { id: "plan-pro-tools", label: "Plans BIM / Autodesk", run: () => nav("/plans-pro") },
          { id: "plan-bet-reader", label: "Lecture spécialisée BET", run: () => nav("/structuro/lecture-plan") },
        ]}>
          <Select value={plan?.plan_id || ""} onValueChange={(v) => {
                    if (!v) return;
                    if (v.startsWith("group:")) { const g = planGroups.find((x) => x.group_id === v.slice(6)); if (g) { setPlan(null); openGroupConsolidated(g); } }
                    else openPlanById(v);
                  }}>
            <SelectTrigger disabled={analysisBusy || aiBusy} aria-label="Changer de plan" className="h-9 w-[210px] rounded-sm" data-testid="plan-switcher-trigger"
                           title="Basculer vers un autre plan sans quitter l'éditeur">
              <SelectValue placeholder="Changer de plan" />
            </SelectTrigger>
            <SelectContent data-testid="plan-switcher-content" className="z-[80] max-h-80">
              {allPlans.map((p) => (
                <SelectItem key={p.plan_id} value={p.plan_id} data-testid={`plan-switcher-item-${p.plan_id}`}>
                  {(p.filename || "Plan sans nom")}{(p.page_count || 1) > 1 ? ` · ${p.page_count}p` : ""}
                </SelectItem>
              ))}
              {planGroups.map((g) => (
                <SelectItem key={g.group_id} value={`group:${g.group_id}`} data-testid={`plan-switcher-group-${g.group_id}`}>
                  📁 {g.name} ({(g.levels || []).length} niveaux)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
      </PlanWorkflowHeader>
      {!!plan.pages?.[pageIndex]?.reading_warnings?.length && (
        <div className="mx-3 my-3 rounded-xl border border-amber-300/60 bg-amber-50/80 p-4 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-100" role="status" data-testid="plan-reading-warnings">
          <p className="font-semibold mb-2">Lecture à vérifier avant le métré</p>
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
        <summary>Ouvrages, personnalisation et messagerie</summary>
        <div className="plan-advanced-content">
          <BrandingDialog />
          <MailboxDialog />
          <OuvrageComposeDialog onAdd={addOuvrageFromPlan} planVariables={planVariables} />
          <Button variant="outline" onClick={() => { setCustomPosteOpen(true); loadCustomPostes(); }}
                  data-testid="open-custom-postes-btn" className="rounded-sm gap-2">
            <Plus className="h-4 w-4" /> Postes perso
          </Button>
          {pendingOuvrages > 0 && (
            <Button variant="outline" onClick={() => nav("/devis-editeur")}
                    className="rounded-sm gap-2 border-primary text-primary" data-testid="plan-create-quote-ouvrages">
              <ArrowRight className="h-4 w-4" /> Créer un devis ({pendingOuvrages})
            </Button>
          )}
        </div>
      </details>
      {analysisRecap && <PlanAnalysisResults recap={analysisRecap} onClose={() => setAnalysisRecap(null)}
        onReview={() => { setRightTab("ai"); document.getElementById("plan-results-panel")?.scrollIntoView({ block: "start" }); }}
        onQuote={sendToQuote} />}

      <div className="surface p-3 flex items-center gap-4 flex-wrap" data-testid="plan-settings-bar">
        <div className="flex items-center gap-2">
          <span className="text-xs overline">Réglages du plan</span>
          <button
            onClick={() => setSettingsOpen((v) => !v)}
            className="text-primary text-xs hover:underline"
            data-testid="toggle-plan-settings"
          >
            {settingsOpen ? "Masquer" : "Modifier"}
          </button>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Hauteur murs</span>
          <b className="num text-primary">{planDefaults.ceiling_h_m} m</b>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Épaisseur plancher</span>
          <b className="num text-primary">{(planDefaults.floor_thickness_m * 100).toFixed(0)} cm</b>
        </div>
        <Button size="sm" variant="outline" onClick={applyWallHeightToPage} data-testid="apply-wall-height-page-btn"
                title="Appliquer la hauteur de mur ci-dessus à toutes les cotes linéaires de la page (recalcule les m²)"
                className="rounded-sm h-7 gap-1 text-xs border-primary/50 text-primary hover:bg-primary hover:text-white">
          <Ruler className="h-3.5 w-3.5" /> Appliquer la hauteur à toutes les cotes
        </Button>
        {settingsOpen && (
          <div className="flex items-center gap-3 flex-1 justify-end flex-wrap">
            <label className="flex items-center gap-2 text-xs">
              <span>Hauteur murs (m) :</span>
              <Input
                type="number" step="0.05" min="1.5" max="6"
                value={planDefaults.ceiling_h_m}
                onChange={(e) => setPlanDefaults((d) => ({ ...d, ceiling_h_m: parseFloat(e.target.value) || 2.5 }))}
                className="h-8 w-20 text-xs num"
                data-testid="settings-ceiling-h"
              />
            </label>
            <label className="flex items-center gap-2 text-xs">
              <span>Épaisseur plancher (cm) :</span>
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
              Enregistrer
            </Button>
          </div>
        )}
        <p className="text-[10px] text-muted-foreground w-full">
          Ces valeurs s'appliquent aux nouvelles pièces créées ou importées via l'IA (peuvent être ajustées par pièce).
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[180px_minmax(0,1fr)_320px] gap-4 min-w-0">
        {/* SIDEBAR PAGES */}
        <div className="surface p-3 max-h-[80vh] overflow-auto min-w-0 xl:col-span-2 2xl:col-span-1">
          <p className="overline mb-3">Pages ({plan.page_count})</p>
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
                    <p className="font-bold">Page {i + 1}</p>
                    {pg.level_label && (
                      <Badge variant="outline" className="text-[10px] rounded-sm num h-5">
                        {pg.level_label}
                      </Badge>
                    )}
                  </div>
                  <p className="text-muted-foreground num">{pg.width_px}×{pg.height_px}</p>
                  {plan.calibrations?.[String(i)] && (
                    <Badge variant="outline" className="mt-1 text-[10px] rounded-sm">Calibrée</Badge>
                  )}
                </button>
                <Select
                  value={pg.level_index != null ? String(pg.level_index) : "none"}
                  onValueChange={async (v) => {
                    const payload = v === "none"
                      ? { level_index: null, level_label: null }
                      : v === "99" ? { level_index: 99, level_label: "Combles" }
                      : v === "-1" ? { level_index: -1, level_label: "Sous-sol" }
                      : v === "0" ? { level_index: 0, level_label: "RDC" }
                      : { level_index: Number(v), level_label: `R+${v}` };
                    await api.patch(`/takeoffs/${plan.plan_id}/pages/${i}/level`, payload);
                    await refreshPlan();
                    toast.success("Niveau mis à jour");
                  }}
                >
                  <SelectTrigger className="rounded-sm h-6 text-[10px] mt-1" data-testid={`page-level-select-${i}`}>
                    <SelectValue placeholder="Niveau…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Sans niveau</SelectItem>
                    <SelectItem value="-1">Sous-sol</SelectItem>
                    <SelectItem value="0">RDC</SelectItem>
                    <SelectItem value="1">R+1</SelectItem>
                    <SelectItem value="2">R+2</SelectItem>
                    <SelectItem value="3">R+3</SelectItem>
                    <SelectItem value="99">Combles</SelectItem>
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
            <ToolButton icon={MousePointer2} label="Sélection" testId="tool-select" active={tool === TOOLS.SELECT} onClick={() => { setDeductDraw(null); setTool(TOOLS.SELECT); setPoints([]); }} />
            <ToolButton icon={Ruler} label="Calibrer" testId="tool-calibrate" active={tool === TOOLS.CALIB} onClick={() => { setDeductDraw(null); setTool(TOOLS.CALIB); setPoints([]); }} />
            <ToolButton icon={Move} label="Distance" testId="tool-distance" active={tool === TOOLS.DIST} onClick={() => { setDeductDraw(null); setTool(TOOLS.DIST); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Layers} label="Périmètre" testId="tool-polyline" active={tool === TOOLS.POLY} onClick={() => { setDeductDraw(null); setTool(TOOLS.POLY); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Hexagon} label="Surface" testId="tool-surface" active={tool === TOOLS.SURFACE} onClick={() => { setDeductDraw(null); setTool(TOOLS.SURFACE); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Square} label="Pièce" testId="tool-room" active={tool === TOOLS.ROOM} onClick={() => { setDeductDraw(null); setTool(TOOLS.ROOM); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Wand2} label="Auto-pièce" testId="tool-autoroom" active={tool === TOOLS.AUTOROOM} onClick={() => { setDeductDraw(null); setTool(TOOLS.AUTOROOM); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={DoorOpen} label="Ouverture" testId="tool-opening" active={tool === TOOLS.OPENING} onClick={() => { setTool(TOOLS.OPENING); setPoints([]); }} disabled={!currentCalib || rooms.length === 0} />
            {/* Iter 57 — QuoterPlan-like tools */}
            <ToolButton icon={Hash} label="Compteur" testId="tool-counter" active={tool === TOOLS.COUNTER} onClick={() => { setTool(TOOLS.COUNTER); setPoints([]); }} />
            <ToolButton icon={StickyNote} label="Note" testId="tool-note" active={tool === TOOLS.NOTE} onClick={() => { setTool(TOOLS.NOTE); setPoints([]); }} />
            <ToolButton icon={Triangle} label="Angle" testId="tool-angle" active={tool === TOOLS.ANGLE} onClick={() => { setTool(TOOLS.ANGLE); setPoints([]); }} />
            <ToolButton icon={MountainSnow} label="Pente toit" testId="tool-pitch" active={tool === TOOLS.PITCH} onClick={() => { setTool(TOOLS.PITCH); setPoints([]); }} disabled={!currentCalib} />
            <div className="flex-1" />
            {rooms.some((r) => r.page_index === pageIndex && r.surface_delta_pct != null) && (
              <Button size="sm" variant={showDeltas ? "default" : "outline"}
                      onClick={() => setShowDeltas(!showDeltas)}
                      data-testid="toggle-deltas-overlay"
                      className="rounded-sm gap-1 h-8">
                <Square className="h-3 w-3" /> Écarts
              </Button>
            )}
            {detectedWalls && (
              <>
                <Button size="sm" variant={showWalls ? "default" : "outline"} onClick={() => setShowWalls(!showWalls)}
                        data-testid="toggle-walls-overlay"
                        className="rounded-sm gap-1 h-8">
                  <Layers className="h-3 w-3" /> Murs ({detectedWalls.segment_count})
                </Button>
                <Button size="sm" variant={reclassifyMode ? "default" : "outline"}
                        onClick={() => setReclassifyMode(v => !v)}
                        data-testid="toggle-reclassify-mode"
                        className={`rounded-sm gap-1 h-8 ${reclassifyMode ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
                  {reclassifyMode ? "Reclasser (actif)" : "Reclasser"}
                </Button>
              </>
            )}
            <Button size="sm" variant="ghost" onClick={() => setPoints(points.slice(0, -1))} disabled={!points.length} className="rounded-sm gap-1" title="Annuler le dernier point placé">
              <Undo2 className="h-3 w-3" /> Annuler le dernier point
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
                toast.info(locked ? "Plan déverrouillé — zoom & déplacement actifs"
                                  : "Plan verrouillé — échelle calibrée");
              }}
              data-testid="tool-lock"
              className={`rounded-sm gap-1 h-8 ${locked ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title={locked ? "Déverrouiller (autoriser zoom + déplacement)"
                            : "Verrouiller le plan (bloquer zoom + déplacement pour des clics précis)"}
            >
              {locked ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
              {locked ? "Verrouillé" : "Verrouiller"}
            </Button>
            <Button
              size="sm"
              variant={objectPanelOpen ? "default" : "outline"}
              onClick={() => { setPanelFocus(null); setObjectPanelOpen((o) => !o); }}
              data-testid="tool-objects-panel"
              className={`rounded-sm gap-1 h-8 ${objectPanelOpen ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title="Ouvrir le Volet Objets (édition & jump-to)"
            >
              <Layers className="h-3 w-3" />
              Objets
            </Button>
            {/* P1 — Statut d'enregistrement automatique + enregistrement manuel */}
            <span data-testid="autosave-status"
                  className={`inline-flex items-center gap-1 text-xs px-2 h-8 rounded-sm ${saving ? "text-amber-500" : "text-emerald-600"}`}
                  title="Vos mesures et modifications sont enregistrées automatiquement">
              <span className={`h-1.5 w-1.5 rounded-full ${saving ? "bg-amber-500 animate-pulse" : "bg-emerald-500"}`} />
              {saving ? "Enregistrement…" : annotationSaveError ? "Échec sauvegarde" : savedAt ? "Annotations enregistrées ✓" : "Sauvegarde des annotations active"}
            </span>
            <Button size="sm" variant="outline" onClick={manualSave} disabled={saving}
                    data-testid="plan-save-btn" className="rounded-sm gap-1 h-8"
                    title="Forcer l'enregistrement maintenant">
              <Save className="h-3 w-3" /> Enregistrer
            </Button>
            {/* P1 — Réglage contraste/luminosité du plan */}
            <div className="relative">
              <Button
                size="sm"
                variant={showImgAdjust ? "default" : "outline"}
                onClick={() => setShowImgAdjust((v) => !v)}
                data-testid="tool-img-adjust"
                className={`rounded-sm gap-1 h-8 ${showImgAdjust ? "bg-primary text-white hover:bg-orange-600" : ""}`}
                title="Régler le contraste et la luminosité du plan"
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
                      <span className="flex items-center gap-1 text-muted-foreground"><SunMedium className="h-3 w-3" /> Luminosité</span>
                      <b className="num">{Math.round(planBrightness * 100)}%</b>
                    </div>
                    <input type="range" min="0.6" max="1.8" step="0.05" value={planBrightness}
                           onChange={(e) => setPlanBrightness(parseFloat(e.target.value))}
                           data-testid="img-brightness-slider" className="w-full accent-primary" />
                  </div>
                  <Button size="sm" variant="ghost" className="rounded-sm h-7 text-xs"
                          onClick={() => { setPlanContrast(1); setPlanBrightness(1); }}
                          data-testid="img-adjust-reset">
                    Réinitialiser
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
              title={fullscreen ? "Quitter le plein écran (Échap)" : "Afficher le plan en plein écran"}
            >
              {fullscreen ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
              {fullscreen ? "Quitter" : "Plein écran"}
            </Button>
            {/* P3 — Assistant IA d'édition du plan */}
            <Button
              size="sm"
              variant={aiCmdOpen ? "default" : "outline"}
              onClick={() => setAiCmdOpen((v) => !v)}
              data-testid="tool-ai-assistant"
              className={`rounded-sm gap-1 h-8 ${aiCmdOpen ? "bg-primary text-white hover:bg-orange-600" : "border-primary/60 text-primary"}`}
              title="Assistant IA : modifiez le plan en langage naturel"
            >
              <Bot className="h-3 w-3" /> Assistant IA
            </Button>
          </div>

          {/* CANVAS */}
          <div className={fullscreen ? "relative h-[calc(100vh-92px)]" : "relative"}>
          {(pageLoading || loadedPageKey !== pageKey || pageError) && (
            <div role={pageError ? "alert" : "status"} className="min-h-[300px] grid place-content-center gap-3 text-center p-6">
              <p>{pageError || "Chargement du plan…"}</p>
              {pageError && <Button onClick={() => setPageRetry((n) => n + 1)}>Réessayer</Button>}
            </div>
          )}
          {annotationSaveError && <p role="alert" className="p-3 text-destructive">
            Annotations non enregistrées. Cliquez sur « Enregistrer » pour réessayer.
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
                toast.success("Plan pivoté en paysage pour faciliter les mesures");
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
                <p className="overline text-primary flex items-center gap-1"><Bot className="h-3.5 w-3.5" /> Assistant IA du plan</p>
                <div className="flex items-center gap-2">
                  {aiTurns.length > 0 && (
                    <button onClick={() => { setAiTurns([]); setAiJustCreated(null); toast.message("Nouveau fil de conversation"); }}
                            className="text-[10px] text-muted-foreground hover:text-foreground inline-flex items-center gap-0.5"
                            title={`Mémoire du fil : ${aiTurns.length} échange(s). Réinitialiser.`}
                            data-testid="ai-reset-conversation">
                      <History className="h-3 w-3" /> Nouveau fil ({aiTurns.length})
                    </button>
                  )}
                  <button onClick={() => { setAiCmdOpen(false); setAiCmdProposal(null); }}
                          className="text-muted-foreground hover:text-foreground" data-testid="ai-assistant-close">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <p className="text-xs text-muted-foreground leading-snug">
                Ex : « ajoute un sous-plafond rampant 26% de 15 m² au sol », « ajoute une surface de 20 m² de carrelage »,
                « duplique la mesure X », « chiffre toute la page », « mets les murs extérieurs à 2,70 m »,
                « quel est le prix indicatif du placo BA13 ? » (recherche web avec sources).
              </p>
              <div className="flex gap-2">
                <Input
                  value={aiCmd}
                  onChange={(e) => setAiCmd(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !aiCmdBusy) aiProposeCommand(); }}
                  placeholder="Votre commande…"
                  className="rounded-sm h-9 text-sm"
                  data-testid="ai-command-input"
                />
                <Button size="sm" variant="outline" onClick={aiVoiceDictate} disabled={aiCmdBusy}
                        title="Dicter la commande (micro)" data-testid="ai-command-mic"
                        className={`rounded-sm h-9 w-9 p-0 shrink-0 ${aiListening ? "bg-red-500 text-white border-red-500 animate-pulse" : ""}`}>
                  <Mic className="h-4 w-4" />
                </Button>
                <Button size="sm" onClick={aiProposeCommand} disabled={aiCmdBusy || !aiCmd.trim()}
                        className="rounded-sm gap-1 h-9" data-testid="ai-command-propose">
                  {aiCmdBusy && !aiCmdProposal ? <Sparkles className="h-3.5 w-3.5 animate-pulse" /> : <Sparkles className="h-3.5 w-3.5" />}
                  Proposer
                </Button>
              </div>
              {aiCmdProposal && aiCmdProposal.action === "answer" && (
                <div className="border border-border rounded-sm p-2.5 grid gap-2 bg-secondary/40" data-testid="ai-command-answer">
                  <p className="text-xs whitespace-pre-wrap leading-snug">{aiCmdProposal.answer}</p>
                  {Array.isArray(aiCmdProposal.sources) && aiCmdProposal.sources.length > 0 && (
                    <div className="border-t border-border pt-1.5 grid gap-0.5">
                      <p className="overline text-[10px]">Sources</p>
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
                        Prix détecté : <b className="text-foreground">{aiCmdProposal.price_suggestion.amount.toLocaleString("fr-FR", { minimumFractionDigits: 2 })} €/{aiCmdProposal.price_suggestion.unit === "m2" ? "m²" : aiCmdProposal.price_suggestion.unit}</b>
                      </span>
                      <Button size="sm" onClick={() => aiInjectPrice(aiCmdProposal.price_suggestion)}
                              disabled={aiCmdBusy}
                              className="rounded-sm h-7 text-xs gap-1" data-testid="ai-answer-inject-price">
                        <Plus className="h-3 w-3" /> Créer un poste perso
                      </Button>
                    </div>
                  )}
                  <div className="flex justify-end">
                    <Button size="sm" variant="ghost" onClick={() => { setAiCmdProposal(null); setAiCmd(""); }}
                            className="rounded-sm h-7 text-xs" data-testid="ai-answer-close">
                      Fermer
                    </Button>
                  </div>
                </div>
              )}
              {aiCmdProposal && aiCmdProposal.action !== "answer" && (
                <div className="border border-border rounded-sm p-2.5 grid gap-2 bg-secondary/40" data-testid="ai-command-proposal">
                  <p className="text-xs"><b className="text-primary">Aperçu : </b>{aiCmdProposal.summary}</p>
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="ghost" onClick={() => setAiCmdProposal(null)}
                            className="rounded-sm h-7 text-xs" data-testid="ai-command-cancel">
                      Annuler
                    </Button>
                    <Button size="sm" onClick={aiApplyCommand} disabled={aiCmdBusy}
                            className="rounded-sm h-7 text-xs gap-1" data-testid="ai-command-apply">
                      <Save className="h-3 w-3" /> Appliquer
                    </Button>
                  </div>
                </div>
              )}
              {aiJustCreated && (
                <div className="border border-primary/40 rounded-sm p-2.5 flex items-center justify-between gap-2 bg-primary/5" data-testid="ai-chiffrer-created">
                  <span className="text-[11px] text-muted-foreground truncate">
                    « {aiJustCreated.label} » créée{aiJustCreated.value ? ` (${aiJustCreated.value})` : ""} — la chiffrer ?
                  </span>
                  <div className="flex gap-1 shrink-0">
                    <Button size="sm" variant="ghost" onClick={() => setAiJustCreated(null)}
                            className="rounded-sm h-7 text-xs" data-testid="ai-chiffrer-created-skip">Plus tard</Button>
                    <Button size="sm" onClick={() => {
                              const m = (plan?.measurements || []).find((x) => x.measurement_id === aiJustCreated.measurement_id);
                              if (m) openChiffrage(m); else toast.error("Cote introuvable");
                              setAiJustCreated(null);
                            }} disabled={aiCmdBusy}
                            className="rounded-sm h-7 text-xs gap-1" data-testid="ai-chiffrer-created-go">
                      € Chiffrer
                    </Button>
                  </div>
                </div>
              )}
              {aiHistory.length > 0 && (
                <div className="border-t border-border pt-2 mt-1" data-testid="ai-command-history">
                  <p className="overline text-[10px] mb-1 flex items-center gap-1"><History className="h-3 w-3" /> Commandes appliquées</p>
                  <div className="grid gap-1 max-h-32 overflow-y-auto">
                    {aiHistory.map((h) => (
                      <div key={h.id} className="flex items-center justify-between gap-2 text-[11px] bg-muted/40 rounded-sm px-2 py-1"
                           data-testid={`ai-history-item-${h.id}`}>
                        <span className="truncate flex-1 text-muted-foreground">{h.summary}</span>
                        {h.inverse ? (
                          <button onClick={() => aiUndo(h)} disabled={aiCmdBusy}
                                  className="text-primary hover:underline shrink-0 inline-flex items-center gap-0.5"
                                  data-testid={`ai-history-undo-${h.id}`}>
                            <Undo2 className="h-3 w-3" /> Annuler
                          </button>
                        ) : (
                          <span className="text-[10px] text-muted-foreground/60 shrink-0">non annulable</span>
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
                <p className="overline text-fuchsia-500">Cote IA #{selectedCote + 1}</p>
                <button onClick={() => setSelectedCote(null)}
                        className="text-muted-foreground hover:text-foreground"
                        data-testid="cote-detail-close">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Valeur écrite</span>
                <b className="num" data-testid="cote-written-value">
                  {coteDetail.value_m != null ? `${Number(coteDetail.value_m).toFixed(2)} m` : "—"}
                </b>
              </div>
              {coteDetail.measured != null ? (
                <>
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Mesure (échelle actuelle)</span>
                    <b className="num" data-testid="cote-measured-value">
                      {coteDetail.measured.toFixed(2)} m
                    </b>
                  </div>
                  {coteDetail.deltaPct != null && (
                    <div className={`flex justify-between text-xs ${Math.abs(coteDetail.deltaPct) > 3 ? "text-amber-500" : "text-green-600"}`}
                         data-testid="cote-delta">
                      <span>Écart</span>
                      <b className="num">
                        {coteDetail.deltaPct > 0 ? "+" : ""}{coteDetail.deltaPct.toFixed(1)}%
                        {Math.abs(coteDetail.deltaPct) > 3 ? " ⚠" : " ✓"}
                      </b>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">
                  Calibrez la page pour comparer la mesure à la valeur écrite.
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
            onDeductOpening={(m) => { setDeductWidth(""); setDeductCount(1); setDeductDialog({ measurement_id: m.measurement_id, label: m.label || "Mur" }); }}
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
                <DialogTitle>Déduire une ouverture — {deductDialog?.label}</DialogTitle>
                <DialogDescription>
                  Soustrayez une fenêtre ou une porte du total du mur. Vous pouvez la dessiner sur le plan
                  ou saisir sa largeur.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4">
                {/* Hauteur du mur → surfaces automatiques (m²) */}
                <div className="rounded-sm border border-primary/30 bg-primary/5 p-3" data-testid="wall-height-block">
                  <div className="flex items-end gap-3">
                    <div className="grid gap-1">
                      <Label className="text-xs">Hauteur du mur (m)</Label>
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
                      Saisissez la hauteur pour calculer automatiquement les m² de mur
                      (brut = longueur × hauteur) et les ouvertures à déduire.
                    </p>
                  </div>
                  {deductLiveMeasure?.wall_area_net_m2 != null && (
                    <div className="mt-2 grid grid-cols-3 gap-2 text-center" data-testid="wall-area-summary">
                      <div className="rounded-sm bg-background p-2">
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Mur brut</p>
                        <p className="num text-sm font-semibold">{Number(deductLiveMeasure.wall_area_gross_m2 || 0).toFixed(2)} m²</p>
                      </div>
                      <div className="rounded-sm bg-background p-2">
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Ouvertures</p>
                        <p className="num text-sm font-semibold text-destructive">−{Number(deductLiveMeasure.openings_area_m2 || 0).toFixed(2)} m²</p>
                      </div>
                      <div className="rounded-sm bg-primary/10 p-2">
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Mur net</p>
                        <p className="num text-sm font-bold text-primary">{Number(deductLiveMeasure.wall_area_net_m2 || 0).toFixed(2)} m²</p>
                      </div>
                    </div>
                  )}
                  {deductLiveMeasure?.wall_area_net_m2 > 0 && (
                    <Button size="sm" variant="outline" className="mt-2 w-full rounded-sm gap-2"
                            data-testid="report-wall-area-devis"
                            onClick={() => reportWallAreaToDevis(deductLiveMeasure)}>
                      <ArrowRight className="h-3.5 w-3.5" /> Reporter la surface nette au devis (m²)
                    </Button>
                  )}
                </div>
                {deductLiveMeasure?.openings?.length > 0 && (
                  <div className="rounded-sm border border-border p-2" data-testid="deduct-openings-list">
                    <div className="mb-1 flex items-center justify-between text-[11px] font-semibold text-muted-foreground">
                      <span>Ouvertures déduites</span>
                      <span className="num">
                        brut {Number(deductLiveMeasure.gross_m ?? deductLiveMeasure.value_m ?? 0).toFixed(2)} m → net {Number(deductLiveMeasure.value_m ?? 0).toFixed(2)} m
                      </span>
                    </div>
                    <div className="space-y-1">
                      {deductLiveMeasure.openings.map((op, oi) => (
                        <div key={op.opening_id} className="flex items-center gap-2" data-testid={`deduct-opening-${oi}`}>
                          <span className="w-4 text-[11px] text-muted-foreground">{oi + 1}.</span>
                          <span className="flex-1 truncate text-xs">{op.label || "Ouverture"}</span>
                          <Input defaultValue={op.width_m} inputMode="decimal"
                                 title="Largeur (m)"
                                 data-testid={`deduct-opening-${oi}-width`}
                                 className="h-8 w-16 text-xs"
                                 onBlur={(e) => {
                                   const w = parseFloat(String(e.target.value).replace(",", "."));
                                   if (w > 0 && w !== op.width_m) patchOpening(op.opening_id, { width_m: w });
                                 }} />
                          <span className="text-[11px] text-muted-foreground">×</span>
                          <Input defaultValue={op.height_m || ""} inputMode="decimal"
                                 title="Hauteur (m) — pour le calcul des m²" placeholder="haut."
                                 data-testid={`deduct-opening-${oi}-height`}
                                 className="h-8 w-16 text-xs"
                                 onBlur={(e) => {
                                   const h = parseFloat(String(e.target.value).replace(",", "."));
                                   if (h > 0 && h !== op.height_m) patchOpening(op.opening_id, { height_m: h });
                                 }} />
                          <span className="text-[11px] text-muted-foreground">m ×</span>
                          <Input type="number" min={1} defaultValue={op.count || 1}
                                 title="Nombre"
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
                    <p className="mt-1 text-[10px] text-muted-foreground">Modifiez une largeur/un nombre puis cliquez ailleurs pour enregistrer.</p>
                  </div>
                )}
                <Button variant="outline" className="rounded-sm gap-2 justify-start"
                        data-testid="deduct-choose-draw"
                        onClick={() => armDeductDraw({ measurement_id: deductDialog.measurement_id, label: deductDialog.label })}>
                  <DoorOpen className="h-4 w-4" /> Dessiner la fenêtre sur le plan (2 points)
                </Button>
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="flex-1 border-t border-border" /> ou saisir <span className="flex-1 border-t border-border" />
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] text-muted-foreground">Type :</span>
                  <Button type="button" size="sm" variant={deductNature === "porte" ? "default" : "outline"}
                          className="h-7 rounded-sm text-[11px]" data-testid="opening-preset-porte"
                          onClick={() => applyOpeningPreset("porte")}>
                    Porte ({openingPresetH("porte")} m)
                  </Button>
                  <Button type="button" size="sm" variant={deductNature === "fenetre" ? "default" : "outline"}
                          className="h-7 rounded-sm text-[11px]" data-testid="opening-preset-fenetre"
                          onClick={() => applyOpeningPreset("fenetre")}>
                    Fenêtre ({openingPresetH("fenetre")} m)
                  </Button>
                </div>
                <div className="flex items-end gap-3 flex-wrap">
                  <div className="grid gap-1">
                    <Label className="text-xs">Largeur (m)</Label>
                    <Input value={deductWidth} onChange={(e) => setDeductWidth(e.target.value)}
                           placeholder="1.20" inputMode="decimal" data-testid="deduct-width-input"
                           className="h-9 w-24" />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Hauteur (m)</Label>
                    <Input value={deductHeight} onChange={(e) => setDeductHeight(e.target.value)}
                           placeholder="1.00" inputMode="decimal" data-testid="deduct-height-input"
                           className="h-9 w-24" />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Nombre</Label>
                    <Input type="number" min={1} value={deductCount}
                           onChange={(e) => setDeductCount(e.target.value)}
                           data-testid="deduct-count-input" className="h-9 w-20" />
                  </div>
                  <Button onClick={submitDeductTyped} data-testid="deduct-typed-submit"
                          className="rounded-sm gap-2 h-9">
                    <Scissors className="h-4 w-4" /> Déduire
                  </Button>
                </div>
                <p className="text-[10px] text-muted-foreground -mt-2">
                  La hauteur est optionnelle : sans elle, seule la largeur est déduite (en ml).
                  Avec elle, l'ouverture est aussi déduite en m².
                </p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDeductDialog(null)}
                        data-testid="deduct-dialog-close" className="rounded-sm">Fermer</Button>
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
              if (items.length === 0) return toast.info("Aucun matériau à comparer");
              sessionStorage.setItem("construpilot_price_search_batch", JSON.stringify({
                items,
                source: "room_estimate",
                project_name: `Pièce ${est.room?.name || "-"} — ${plan?.filename || "Plan"}`,
                total_avg: est.total_budget || 0,
                ts: Date.now(),
              }));
              toast.success(`${items.length} matériau${items.length > 1 ? "x" : ""} ajouté${items.length > 1 ? "s" : ""} au devis`);
              setRoomEstimate(null);
              // Navigate to /prix
              window.location.href = "/prix?from=room-estimate";
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
                Outil actif : {TOOL_LABELS[tool] || tool}
              </Badge>
              {(tool === TOOLS.DIST || tool === TOOLS.SURFACE) && (
                <Button size="sm" variant={cumulMode ? "default" : "outline"}
                        onClick={() => { setCumulMode((v) => !v); setPoints([]); if (cumulMode) { setCumulSegments([]); setCumulLabel(""); } }}
                        data-testid="tool-cumul-toggle"
                        className={`rounded-sm gap-1 h-8 ${cumulMode ? "bg-primary text-white" : ""}`}
                        title={cumulIsArea ? "Additionner plusieurs zones de sol en une seule surface" : "Additionner plusieurs tronçons d'un même mur (fenêtres/portes = trous exclus)"}>
                  <Layers className="h-3 w-3" /> Cumul {cumulIsArea ? "surface" : "mur"} {cumulMode ? "ON" : "OFF"}
                </Button>
              )}
              <span className="flex-1" />
              <Button size="sm" variant="outline" onClick={() => setPoints(points.slice(0, -1))}
                      disabled={!points.length} data-testid="tool-undo-point"
                      className="rounded-sm gap-1 h-8">
                <Undo2 className="h-3 w-3" /> Annuler le dernier point
              </Button>
              <Button size="sm" variant="secondary" onClick={() => { setTool(TOOLS.SELECT); setPoints([]); }}
                      data-testid="tool-back-select" className="rounded-sm gap-1 h-8">
                <ArrowLeft className="h-3 w-3" /> Retour
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
                  <option value="">Poste à chiffrer…</option>
                  {posteCatalog.filter((p) => cumulIsArea ? p.family !== "length" : p.family !== "area").map((p) => (
                    <option key={p.key} value={p.key}>{p.label}</option>
                  ))}
                </select>
                <Input value={cumulLabel} onChange={(e) => setCumulLabel(e.target.value)}
                       placeholder={cumulIsArea ? "Nom de la surface (ex. Sol RDC)" : "Nom du mur (ex. Mur façade nord)"}
                       data-testid="cumul-wall-label"
                       className="h-8 text-xs w-44" />
              </div>
              <Badge variant="outline" className="rounded-sm num font-semibold"
                     style={{ borderColor: cumulColor, color: cumulColor }}
                     data-testid="cumul-wall-total">
                {cumulSegments.length} {cumulIsArea ? "zone" : "tronçon"}{cumulSegments.length > 1 ? "s" : ""} · {cumulTotal.value.toFixed(2)} {cumulTotal.unit}
              </Badge>
              <span className="text-[10px] text-muted-foreground">
                {cumulIsArea
                  ? "Mesurez une zone (≥3 points) → double-clic pour l'ajouter → recommencez"
                  : "Mesurez un tronçon → double-clic pour l'ajouter → continuez après la fenêtre"}
              </span>
              <span className="flex-1" />
              <Button size="sm" variant="outline" onClick={cancelCumulWall}
                      disabled={!cumulSegments.length && points.length < 2}
                      data-testid="cumul-wall-cancel" className="rounded-sm gap-1 h-8">
                <X className="h-3 w-3" /> Annuler
              </Button>
              <Button size="sm" onClick={finishCumul}
                      disabled={!cumulSegments.length && points.length < (cumulIsArea ? 3 : 2)}
                      data-testid="cumul-wall-finish"
                      className="rounded-sm gap-2 h-8 text-white"
                      style={{ background: cumulColor }}>
                <Save className="h-3 w-3" /> {cumulIsArea ? "Terminer la surface" : "Terminer le mur"} ({cumulTotal.value.toFixed(2)} {cumulTotal.unit})
              </Button>
            </div>
          )}

          {/* DÉDUCTION D'OUVERTURE — dessin armé sur un mur ciblé */}
          {deductDraw && (
            <div className="mt-3 flex flex-wrap items-center gap-3 rounded-sm border-2 border-dashed border-amber-500 bg-amber-50 px-3 py-2"
                 data-testid="deduct-draw-bar">
              <Badge variant="outline" className="rounded-sm gap-1 border-amber-500 text-amber-700 font-semibold">
                <DoorOpen className="h-3 w-3" /> Déduire des ouvertures — {deductDraw.label}
              </Badge>
              <span className="text-[10px] text-muted-foreground">
                Dessinez chaque fenêtre/porte (2 points) puis double-clic — enchaînez-en plusieurs, puis « Terminer »
              </span>
              <span className="flex-1" />
              {points.length === 2 && (
                <Button size="sm" onClick={() => submitDeductDraw(points)}
                        data-testid="deduct-draw-finish"
                        className="rounded-sm gap-2 h-8 bg-amber-600 text-white hover:bg-amber-700">
                  <Save className="h-3 w-3" /> Déduire cette ouverture
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={() => { setDeductDraw(null); setPoints([]); setTool(TOOLS.SELECT); }}
                      data-testid="deduct-draw-cancel" className="rounded-sm gap-1 h-8">
                <X className="h-3 w-3" /> Terminer
              </Button>
            </div>
          )}

          {/* CONTEXT ACTIONS */}
          {points.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 items-center">
              <Badge variant="outline" className="rounded-sm num" data-testid="points-count">{points.length} point{points.length > 1 ? "s" : ""}</Badge>
              {(tool === TOOLS.DIST || tool === TOOLS.POLY || tool === TOOLS.ROOM || tool === TOOLS.SURFACE) && (
                <span className="text-[10px] text-muted-foreground" data-testid="dblclick-hint">
                  double-clic = terminer · clic suivant = nouvelle mesure
                </span>
              )}
              {tool === TOOLS.DIST && !cumulMode && points.length === 2 && (
                <Button size="sm" onClick={() => finishDistance()} data-testid="tool-finish-distance" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Mesurer
                </Button>
              )}
              {tool === TOOLS.DIST && cumulMode && points.length === 2 && (
                <Button size="sm" onClick={onCanvasDoubleClick} data-testid="cumul-add-segment"
                        className="rounded-sm gap-2 text-white" style={{ background: cumulColor }}>
                  <Plus className="h-3 w-3" /> Ajouter ce tronçon
                </Button>
              )}
              {tool === TOOLS.POLY && points.length >= 2 && (
                <Button size="sm" onClick={() => finishPolyline()} data-testid="tool-finish-polyline" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Terminer polyligne
                </Button>
              )}
              {tool === TOOLS.SURFACE && !cumulMode && points.length >= 3 && (
                <Button size="sm" onClick={() => finishSurface()} data-testid="tool-finish-surface" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Terminer surface
                </Button>
              )}
              {tool === TOOLS.SURFACE && cumulMode && points.length >= 3 && (
                <Button size="sm" onClick={onCanvasDoubleClick} data-testid="cumul-add-zone"
                        className="rounded-sm gap-2 text-white" style={{ background: cumulColor }}>
                  <Plus className="h-3 w-3" /> Ajouter cette zone
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
                    <Save className="h-3 w-3" /> Fermer pièce
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
                    title="Angle de pente en degrés (0° = plat)"
                  />
                  <span className="text-xs text-muted-foreground">°</span>
                  <Button size="sm" onClick={finishPitchSurface} data-testid="tool-finish-pitch"
                          className="rounded-sm gap-2 hover:bg-blue-600 hover:text-white">
                    <Save className="h-3 w-3" /> Fermer toiture
                  </Button>
                </>
              )}
              {tool === TOOLS.ANGLE && points.length < 3 && (
                <span className="text-xs text-muted-foreground">
                  {points.length === 0 && "Cliquez sur la 1ʳᵉ branche de l'angle"}
                  {points.length === 1 && "Cliquez sur le sommet de l'angle"}
                  {points.length === 2 && "Cliquez sur la 2ᵉ branche"}
                </span>
              )}
              <Button size="sm" variant="ghost" onClick={() => setPoints([])} className="rounded-sm" title="Effacer tous les points de la mesure en cours">Annuler tout</Button>
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
                  const label = window.prompt(`Nom du compteur ${nb + 1} (ex: Prises, Spots, Radiateurs) :`, `Compteur ${nb + 1}`);
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
                + Nouveau compteur
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
                    if (!window.confirm("Supprimer ce compteur et ses marqueurs ?")) return;
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
                <p className="overline">Murs détectés {reclassifyMode && (
                  <span className="text-primary">· cliquez sur un mur pour cycler son type</span>
                )}</p>
                <Badge variant="outline" className="rounded-sm text-[10px] num">
                  {detectedWalls.segment_count} segments
                </Badge>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[
                  ["porteur",  "text-red-500 border-red-500/40 bg-red-500/5",   "Porteur"],
                  ["cloison",  "text-primary border-primary/40 bg-primary/5",   "Cloison"],
                  ["doublage", "text-blue-500 border-blue-500/40 bg-blue-500/5", "Doublage"],
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
                  <span className="text-[10px] text-muted-foreground">Matériau des murs porteurs (IA) :</span>
                  {plan.ai_analysis.wall_types.hatching_present &&
                   plan.ai_analysis.wall_types.hatching_present !== "aucun" ? (
                    <Badge variant="outline" className="rounded-sm text-[10px] capitalize border-red-500/40 text-red-500">
                      {plan.ai_analysis.wall_types.hatching_present}
                    </Badge>
                  ) : (
                    <span className="text-[10px] text-muted-foreground italic">
                      non détecté — lancez « Lire le plan (IA) »
                    </span>
                  )}
                  {plan.ai_analysis.wall_types.load_bearing_visible && (
                    <Badge variant="outline" className="rounded-sm text-[10px] border-red-500/40 text-red-500">porteurs visibles</Badge>
                  )}
                  {plan.ai_analysis.wall_types.partition_visible && (
                    <Badge variant="outline" className="rounded-sm text-[10px] border-primary/40 text-primary">cloisons visibles</Badge>
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
                  <Sparkles className="h-3 w-3 text-red-500" /> Structure IA
                </p>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] text-muted-foreground">
                    <span className="text-red-500 font-bold">■</span> murs ·
                    <span className="text-yellow-500 font-bold"> ■</span> fenêtres ·
                    <span className="text-purple-500 font-bold"> ■</span> portes
                  </span>
                  <Button size="sm" variant={showStructure ? "default" : "outline"}
                          onClick={() => setShowStructure((v) => !v)}
                          data-testid="toggle-structure-overlay" className="rounded-sm gap-1 h-7 text-xs">
                    <Layers className="h-3 w-3" /> {showStructure ? "Masquer" : "Afficher"}
                  </Button>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2 mb-2">
                <div className="border border-red-500/40 rounded-sm p-2 text-red-500" data-testid="structure-wall-count">
                  <p className="text-[10px] uppercase font-bold tracking-wider">Murs</p>
                  <p className="num text-lg font-extrabold">{structure.walls?.length || 0}</p>
                </div>
                <div className="border border-yellow-500/40 rounded-sm p-2 text-yellow-600" data-testid="structure-opening-count">
                  <p className="text-[10px] uppercase font-bold tracking-wider">Ouvert.</p>
                  <p className="num text-lg font-extrabold">{structure.openings?.length || 0}</p>
                </div>
                <div className="border border-purple-800/40 rounded-sm p-2 text-purple-800" data-testid="structure-beam-count">
                  <p className="text-[10px] uppercase font-bold tracking-wider">Poutres</p>
                  <p className="num text-lg font-extrabold">{structure.beams?.length || 0}</p>
                </div>
                <div className="border border-purple-600/40 rounded-sm p-2 text-purple-600" data-testid="structure-column-count">
                  <p className="text-[10px] uppercase font-bold tracking-wider">Poteaux</p>
                  <p className="num text-lg font-extrabold">{structure.columns?.length || 0}</p>
                </div>
              </div>

              {/* Descriptif chiffré */}
              {descriptif && (
                <div className="mb-2 border border-border rounded-sm p-2 bg-background" data-testid="structure-descriptif">
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="overline">Descriptif chiffré</p>
                    <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      Hauteur murs
                      <input type="number" step="0.1" min="1" max="6" value={wallHeight}
                             onChange={(e) => setWallHeight(parseFloat(e.target.value) || 2.5)}
                             data-testid="structure-wall-height"
                             className="w-14 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> m
                    </label>
                  </div>
                  {/* Hauteur par arases NGF (AS - AI) — prioritaire sur la hauteur murs */}
                  <div className="flex items-center gap-2 mb-1.5 text-[10px] text-muted-foreground">
                    <span className="whitespace-nowrap">Arases NGF :</span>
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
                    <span className="text-[10px] text-muted-foreground whitespace-nowrap">Bâtiment :</span>
                    {[
                      { v: "dalle_pleine", label: "🏢 Immeuble (dalle pleine)" },
                      { v: "poutrelles_hourdis", label: "🏠 Maison (hourdis)" },
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
                      <option value="">Choisir un réglage (chantier)…</option>
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
                      <Save className="h-3 w-3" /> Sous…
                    </Button>
                    <Button size="sm" variant="outline" onClick={runCompare}
                            data-testid="beton-preset-compare" className="rounded-sm h-7 text-[10px] gap-1">
                      Comparer
                    </Button>
                  </div>
                  {!descriptif.calibrated && (
                    <p className="text-[10px] text-destructive mb-1">⚠️ Plan non calibré — quantités indisponibles.</p>
                  )}
                  {/* Épaisseurs réglables pour le métré béton */}
                  <div className="flex items-center gap-3 mb-1.5 text-[10px] text-muted-foreground">
                    <label className="flex items-center gap-1">Ép. dalle
                      <input type="number" step="0.05" min="0.05" max="1" value={dalleEp}
                             onChange={(e) => setDalleEp(parseFloat(e.target.value) || 0.20)}
                             data-testid="structure-dalle-ep"
                             className="w-12 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> m
                    </label>
                    <label className="flex items-center gap-1">Ép. voile
                      <input type="number" step="0.05" min="0.05" max="1" value={voileEp}
                             onChange={(e) => setVoileEp(parseFloat(e.target.value) || 0.20)}
                             data-testid="structure-voile-ep"
                             className="w-12 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> m
                    </label>
                    <label className="flex items-center gap-1">Poutre b×h
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
                    <summary className="text-[10px] font-semibold cursor-pointer text-orange-600">Ratios aciers (kg/m³) — ajustables</summary>
                    <div className="grid grid-cols-3 gap-2 mt-1 text-[10px] text-muted-foreground">
                      {[["semelles", "Semelles"], ["poteaux", "Poteaux"], ["poutres", "Poutres"], ["dalles", "Dalles"], ["voiles", "Voiles"]].map(([k, lbl]) => (
                        <label key={k} className="flex flex-col gap-0.5">{lbl}
                          <input type="number" step="5" min="0" max="400" value={acierRatios[k]}
                                 onChange={(e) => setAcierRatios((r) => ({ ...r, [k]: parseFloat(e.target.value) || 0 }))}
                                 data-testid={`acier-ratio-${k}`}
                                 className="w-full rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />
                        </label>
                      ))}
                    </div>
                    <label className="flex items-center gap-1 mt-1.5 text-[10px] text-muted-foreground">Prix acier
                      <input type="number" step="0.1" min="0" max="10" value={acierPriceKg}
                             onChange={(e) => setAcierPriceKg(parseFloat(e.target.value) || 0)}
                             data-testid="acier-price-kg"
                             className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> €/kg
                      <span className="ml-2">Prix béton</span>
                      <input type="number" step="5" min="0" max="500" value={betonPriceM3}
                             onChange={(e) => setBetonPriceM3(parseFloat(e.target.value) || 0)}
                             data-testid="beton-price-m3"
                             className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> €/m³
                    </label>
                    <label className="flex items-center gap-1 mt-1.5 text-[10px] text-muted-foreground">Main d'œuvre
                      <input type="number" step="10" min="0" max="2000" value={laborPriceM3}
                             onChange={(e) => setLaborPriceM3(parseFloat(e.target.value) || 0)}
                             data-testid="labor-price-m3"
                             className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> €/m³
                      <span className="ml-2">Marge</span>
                      <input type="number" step="1" min="0" max="100" value={marginPct}
                             onChange={(e) => setMarginPct(parseFloat(e.target.value) || 0)}
                             data-testid="margin-pct"
                             className="w-14 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> %
                    </label>
                    <div className="flex items-center gap-1.5 mt-1.5 text-[10px] text-muted-foreground" data-testid="plan-price-level">
                      <span>Gamme (biblio. partagée) :</span>
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
                      <span>Marge/poste :</span>
                      <label className="flex items-center gap-0.5">Béton
                        <input type="number" step="1" min="0" max="100" placeholder="—" value={marginBeton}
                               onChange={(e) => setMarginBeton(e.target.value)} data-testid="margin-beton"
                               className="w-11 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />%
                      </label>
                      <label className="flex items-center gap-0.5">Aciers
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
                      <Save className="h-3 w-3" /> Enregistrer comme réglages par défaut
                    </Button>
                  </details>
                  {/* Prix béton par poste (€/m³) — chiffrage plus fin */}
                  <details className="mb-1.5" data-testid="beton-prices-poste">
                    <summary className="text-[10px] font-semibold cursor-pointer text-sky-600">Prix béton par poste (€/m³) — optionnel</summary>
                    <div className="grid grid-cols-3 gap-2 mt-1 text-[10px] text-muted-foreground">
                      {[["semelles", "Semelles"], ["proprete", "Propreté"], ["poteaux", "Poteaux"], ["poutres", "Poutres"], ["voiles", "Voiles"]].map(([k, lbl]) => (
                        <label key={k} className="flex flex-col gap-0.5">{lbl}
                          <input type="number" step="5" min="0" max="500" value={betonPrices[k]}
                                 onChange={(e) => setBetonPrices((r) => ({ ...r, [k]: parseFloat(e.target.value) || 0 }))}
                                 data-testid={`beton-price-${k}`}
                                 className="w-full rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />
                        </label>
                      ))}
                    </div>
                    <p className="text-[9px] text-muted-foreground mt-1">Laisser à 0 pour utiliser le prix béton global ({betonPriceM3} €/m³).</p>
                    <div className="mt-2 pt-2 border-t border-border grid gap-1.5">
                      <p className="text-[10px] font-semibold text-sky-600">Plancher (chiffré au m²)</p>
                      <label className="flex items-center justify-between gap-1 text-[10px] text-muted-foreground">Type de plancher
                        <select value={plancherType} onChange={(e) => setPlancherType(e.target.value)}
                                data-testid="plancher-type"
                                className="rounded-sm border border-input bg-background px-1 py-0.5 text-[10px]">
                          <option value="auto">Auto (selon plan)</option>
                          <option value="dalle_pleine">Dalle pleine BA (immeuble)</option>
                          <option value="poutrelles_hourdis">Poutrelles-hourdis (maison)</option>
                        </select>
                      </label>
                      <label className="flex items-center justify-between gap-1 text-[10px] text-muted-foreground">Prix plancher (€/m²)
                        <input type="number" step="5" min="0" max="500" value={plancherPriceM2}
                               onChange={(e) => setPlancherPriceM2(parseFloat(e.target.value) || 0)}
                               data-testid="plancher-price-m2"
                               className="w-16 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" />
                      </label>
                      <p className="text-[9px] text-muted-foreground">0 = barème auto selon l'épaisseur : ≤16 cm → 120 € · 17–20 cm → 140 € · &gt;20 cm → 160 €/m².</p>
                    </div>
                    <label className="flex items-center gap-1 mt-1.5 text-[10px] text-muted-foreground">Épaisseur béton de propreté
                      <input type="number" step="1" min="0" max="30"
                             value={Math.round(propreteEp * 100)}
                             onChange={(e) => setPropreteEp((parseFloat(e.target.value) || 0) / 100)}
                             data-testid="proprete-ep-cm"
                             className="w-14 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> cm
                    </label>
                  </details>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                    <span className="text-muted-foreground flex items-center gap-1">Planchers (sol)
                      {descriptif.planchers_source === "auto" && (
                        <span className="text-[9px] px-1 rounded-sm bg-emerald-500/15 text-emerald-600 font-bold" data-testid="planchers-auto-badge">AUTO IA</span>
                      )}
                    </span><span className="num text-right">{descriptif.planchers_m2} m²</span>
                    <span className="text-muted-foreground">Murs porteurs</span><span className="num text-right">{descriptif.murs_porteurs_ml} ml</span>
                    <span className="text-muted-foreground">Cloisons</span><span className="num text-right">{descriptif.cloisons_ml} ml</span>
                    <span className="text-muted-foreground">Murs (surface)</span><span className="num text-right">{descriptif.murs_surface_m2} m²</span>
                    <span className="text-muted-foreground">Portes / Fenêtres / Baies</span><span className="num text-right">{descriptif.portes} / {descriptif.fenetres} / {descriptif.baies}</span>
                    <span className="text-muted-foreground">Poutres</span><span className="num text-right">{descriptif.poutres_ml} ml</span>
                    <span className="text-muted-foreground">Poteaux</span><span className="num text-right">{descriptif.poteaux || 0} u</span>
                    <span className="text-muted-foreground">Semelles</span><span className="num text-right">{descriptif.semelles || 0} u</span>
                    {descriptif.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Béton total</span>
                        <span className="num text-right font-semibold" data-testid="descriptif-beton">{descriptif.beton_total_m3} m³</span>
                      </>
                    )}
                    {descriptif.acier_total_kg > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Aciers (ferraillage)</span>
                        <span className="num text-right font-semibold text-orange-600" data-testid="descriptif-acier">{descriptif.acier_total_kg} kg</span>
                      </>
                    )}
                    {(betonPriceM3 > 0 || acierPriceKg > 0) && descriptif.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Coût matière (béton + aciers)</span>
                        <span className="num text-right font-semibold text-emerald-700" data-testid="descriptif-cout-matiere">
                          {Math.round((descriptif.beton_total_m3 || 0) * betonPriceM3 + (descriptif.acier_total_kg || 0) * acierPriceKg).toLocaleString("fr-FR")} €
                        </span>
                      </>
                    )}
                    {(betonPriceM3 > 0 || acierPriceKg > 0 || laborPriceM3 > 0) && descriptif.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Prix de vente estimé{marginPct > 0 ? ` (marge ${marginPct}%)` : ""}</span>
                        <span className="num text-right font-bold text-primary" data-testid="descriptif-prix-vente">
                          {Math.round((((descriptif.beton_total_m3 || 0) * betonPriceM3 + (descriptif.acier_total_kg || 0) * acierPriceKg) + (descriptif.beton_total_m3 || 0) * laborPriceM3) * (1 + marginPct / 100)).toLocaleString("fr-FR")} €
                        </span>
                      </>
                    )}
                  </div>
                  {descriptif.beton_total_m3 > 0 && (
                    <details className="mt-2" open data-testid="detail-par-poste">
                      <summary className="text-[11px] font-semibold cursor-pointer text-primary">Détail par poste (béton + aciers)</summary>
                      <div className="mt-1 border border-border rounded-sm overflow-hidden">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60"><tr>
                            <th className="text-left px-1.5 py-1">Poste</th>
                            <th className="text-right px-1.5 py-1">Béton</th>
                            <th className="text-right px-1.5 py-1">Aciers</th>
                          </tr></thead>
                          <tbody>
                            {[
                              { k: "semelles", label: `Semelles (${descriptif.semelles || 0} u)`, b: descriptif.beton_semelles_m3, a: descriptif.acier_semelles_kg },
                              { k: "proprete", label: "Béton de propreté (ép. 5 cm)", b: descriptif.beton_proprete_m3, a: 0 },
                              { k: "poteaux", label: `Poteaux (${descriptif.poteaux || 0} u)`, b: descriptif.beton_poteaux_m3, a: descriptif.acier_poteaux_kg },
                              { k: "poutres", label: `Poutres (${descriptif.poutres_ml || 0} ml)`, b: descriptif.beton_poutres_m3, a: descriptif.acier_poutres_kg },
                              { k: "dalles", label: `Dalles / planchers (${descriptif.planchers_m2 || 0} m²)`, b: descriptif.beton_dalles_m3, a: descriptif.acier_dalles_kg },
                              { k: "voiles", label: `Voiles / murs porteurs (${descriptif.murs_porteurs_ml || 0} ml)`, b: descriptif.beton_voiles_m3, a: descriptif.acier_voiles_kg },
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
                      <summary className="text-[11px] font-semibold cursor-pointer text-purple-600">Tableau des poteaux ({descriptif.poteaux_table.length})</summary>
                      <div className="mt-1 max-h-40 overflow-auto border border-border rounded-sm">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60 sticky top-0"><tr>
                            <th className="text-left px-1.5 py-1">Repère</th><th className="text-left px-1.5 py-1">Section</th><th className="text-right px-1.5 py-1">Béton</th>
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
                      <summary className="text-[11px] font-semibold cursor-pointer text-purple-800">Tableau des poutres ({descriptif.beams_table.length})</summary>
                      <div className="mt-1 max-h-40 overflow-auto border border-border rounded-sm">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60 sticky top-0"><tr>
                            <th className="text-left px-1.5 py-1">Repère</th><th className="text-right px-1.5 py-1">Portée</th><th className="text-right px-1.5 py-1">Béton</th>
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
                    <FileDown className="h-4 w-4" /> {quoteBusy ? "Estimation en cours…" : "Estimer le devis (PDF)"}
                  </Button>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Gros œuvre / béton uniquement — murs, poteaux, poutres, planchers, semelles + aciers (surface = planchers) · béton {betonPriceM3} €/m³ · aciers {acierPriceKg} €/kg · main d'œuvre {laborPriceM3} €/m³ · marge {marginPct}%
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <Button size="sm" variant="outline" onClick={sendToQuote} data-testid="structure-to-quote"
                            className="rounded-sm h-7 text-xs gap-1 flex-1">
                      <ArrowRight className="h-3 w-3" /> Ouvrir dans l'éditeur
                    </Button>
                    <Button size="sm" variant="outline" onClick={exportAnnotatedPdf} data-testid="structure-export-pdf"
                            className="rounded-sm h-7 text-xs gap-1">
                      <FileDown className="h-3 w-3" /> PDF annoté
                    </Button>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <Button size="sm" variant="outline" onClick={exportBetonXlsx} data-testid="structure-export-beton-xlsx"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-emerald-700 border-emerald-600/40">
                      <Sheet className="h-3 w-3" /> Métré Excel
                    </Button>
                    <Button size="sm" variant="outline" onClick={exportBetonPdf} data-testid="structure-export-beton-pdf"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-red-700 border-red-600/40">
                      <FileDown className="h-3 w-3" /> Métré PDF
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setAiChatOpen(true)} data-testid="structure-ai-assistant"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-primary border-primary/40">
                      <Bot className="h-3 w-3" /> Assistant IA
                    </Button>
                  </div>
                </div>
              )}
              <p className="text-[10px] text-muted-foreground mb-2">
                Cliquez un mur/ouverture pour le sélectionner, puis glissez ses extrémités (points blancs) pour l'ajuster.
              </p>
              {selectedStruct && (
                <div className="flex items-center gap-2 flex-wrap mb-2 p-2 rounded-sm bg-background border border-border" data-testid="structure-selected-actions">
                  <Badge variant="outline" className="rounded-sm text-[10px]">
                    {selectedStruct.type === "wall" ? "Mur sélectionné"
                      : selectedStruct.type === "beam" ? "Poutre sélectionnée"
                      : selectedStruct.type === "column" ? "Poteau sélectionné"
                      : selectedStruct.type === "footing" ? "Semelle sélectionnée" : "Ouverture sélectionnée"}
                  </Badge>
                  {(selectedStruct.type === "wall" || selectedStruct.type === "opening") && (
                    <Button size="sm" variant="outline" onClick={toggleStructType}
                            data-testid="structure-toggle-type" className="rounded-sm h-7 text-xs gap-1">
                      {selectedStruct.type === "wall" ? "Porteur ↔ Cloison" : "Porte ↔ Fenêtre ↔ Baie"}
                    </Button>
                  )}
                  <Button size="sm" variant="outline" onClick={deleteStructItem}
                          data-testid="structure-delete" className="rounded-sm h-7 text-xs gap-1 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
                    <Trash2 className="h-3 w-3" /> Supprimer
                  </Button>
                </div>
              )}
              <div className="flex items-center gap-2 flex-wrap">
                <Button size="sm" variant="outline" onClick={addStructWall}
                        data-testid="structure-add-wall" className="rounded-sm h-7 text-xs gap-1">
                  <Plus className="h-3 w-3" /> Mur
                </Button>
                <Button size="sm" variant="outline" onClick={() => addStructOpening("fenetre")}
                        data-testid="structure-add-window" className="rounded-sm h-7 text-xs gap-1 text-yellow-600 border-yellow-500/40">
                  <Plus className="h-3 w-3" /> Fenêtre
                </Button>
                <Button size="sm" variant="outline" onClick={() => addStructOpening("porte")}
                        data-testid="structure-add-door" className="rounded-sm h-7 text-xs gap-1 text-purple-600 border-purple-500/40">
                  <Plus className="h-3 w-3" /> Porte
                </Button>
                <Button size="sm" variant="outline" onClick={addStructBeam}
                        data-testid="structure-add-beam" className="rounded-sm h-7 text-xs gap-1 text-purple-800 border-purple-800/40">
                  <Plus className="h-3 w-3" /> Poutre
                </Button>
                <Button size="sm" variant="outline" onClick={addStructColumn}
                        data-testid="structure-add-column" className="rounded-sm h-7 text-xs gap-1 text-purple-600 border-purple-600/40">
                  <Plus className="h-3 w-3" /> Poteau
                </Button>
                <Button size="sm" variant="outline" onClick={addStructFooting}
                        data-testid="structure-add-footing" className="rounded-sm h-7 text-xs gap-1 text-yellow-700 border-yellow-600/40">
                  <Plus className="h-3 w-3" /> Semelle
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT PANEL — Métré */}
        <div id="plan-results-panel" className="surface p-4 max-h-[80vh] overflow-auto min-w-0">
          <Tabs value={rightTab} onValueChange={setRightTab}>
            <TabsList className="w-full rounded-sm">
              <TabsTrigger value="rooms" className="flex-1 rounded-sm" data-testid="tab-rooms">Pièces</TabsTrigger>
              <TabsTrigger value="materials" className="flex-1 rounded-sm" data-testid="tab-materials">Matériaux</TabsTrigger>
              <TabsTrigger value="ai" className="flex-1 rounded-sm" data-testid="tab-ai">Contrôle</TabsTrigger>
              <TabsTrigger value="history" className="flex-1 rounded-sm" data-testid="tab-history" onClick={loadHistory}>
                <History className="h-3 w-3" />
              </TabsTrigger>
            </TabsList>

            <TabsContent value="rooms" className="mt-3 grid gap-3">
              {rooms.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Calibrez le plan puis utilisez l'outil <b>Pièce</b> pour tracer un contour.
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
                               title={`Surface écrite sur le plan : ${r.surface_written_m2} m²`}
                               data-testid={`room-surface-delta-${r.room_id}`}>
                          écrit {r.surface_written_m2} m² ({r.surface_delta_pct > 0 ? "+" : ""}{r.surface_delta_pct}%)
                        </Badge>
                      )}
                      {(r.deductions || []).map((d) => (
                        <Badge key={d.deduction_id} variant="outline"
                               className="rounded-sm text-[10px] num border-red-400 text-red-500 gap-1"
                               title={`Surface brute : ${r.surface_gross_m2} m²`}
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
                    <span>Surface</span><span className="text-right font-bold">{r.surface_m2} m²</span>
                    <span>Périmètre</span><span className="text-right">{r.perimeter_m} m</span>
                    <span>Murs bruts</span><span className="text-right">{r.wall_area_gross_m2} m²</span>
                    <span>Ouvertures</span><span className="text-right text-destructive">-{r.openings_area_m2 || 0} m²</span>
                    <span>Murs nets</span><span className="text-right font-bold">{r.wall_area_net_m2} m²</span>
                    {r.volume_m3 != null && (<><span>Volume</span><span className="text-right">{r.volume_m3} m³</span></>)}
                  </div>
                  {(r.openings || []).length > 0 && (
                    <div className="mt-2 pt-2 border-t border-border/60 space-y-1">
                      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Ouvertures ({r.openings.length})</p>
                      {r.openings.map((o) => (
                        <div key={o.opening_id} className="flex items-center justify-between text-xs">
                          <span className="truncate">
                            <span className="text-primary font-semibold capitalize">{o.kind}</span>
                            {o.label ? ` · ${o.label}` : ""} · <span className="num">{o.width_m}×{o.height_m}m{o.count > 1 ? ` ×${o.count}` : ""}</span>
                          </span>
                          <button
                            onClick={() => deleteOpening(r.room_id, o.opening_id)}
                            className="text-destructive hover:text-red-600 ml-2"
                            title="Supprimer"
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
                  <Calculator className="h-4 w-4" /> Calculer le métré total
                </Button>
              )}
              {takeoff && (
                <div className="border-t border-border pt-3 grid gap-1 text-xs num" data-testid="takeoff-totals">
                  <p className="overline mb-2">Totaux</p>
                  <div className="flex justify-between"><span>Sol total</span><b>{takeoff.totals.floor_m2} m²</b></div>
                  <div className="flex justify-between"><span>Plafonds</span><b>{takeoff.totals.ceiling_m2} m²</b></div>
                  <div className="flex justify-between"><span>Murs nets</span><b>{takeoff.totals.walls_net_m2} m²</b></div>
                  <div className="flex justify-between"><span>Périmètre</span><b>{takeoff.totals.perimeter_m} m</b></div>

                  {takeoff.levels?.length > 1 && (
                    <div className="mt-3" data-testid="takeoff-by-level">
                      <p className="overline mb-2">Par niveau</p>
                      {takeoff.levels.map((lvl) => (
                        <div key={String(lvl.level_index)} className="border-l-2 border-primary pl-2 mb-2">
                          <p className="font-bold text-primary">{lvl.level_label} · {lvl.rooms.length} pièce{lvl.rooms.length > 1 ? "s" : ""}</p>
                          <div className="flex justify-between"><span>Sol</span><span>{lvl.totals.floor_m2} m²</span></div>
                          <div className="flex justify-between"><span>Murs nets</span><span>{lvl.totals.walls_net_m2} m²</span></div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex gap-2 mt-3">
                    <Button size="sm" onClick={sendToEstimator} data-testid="send-to-estimator" className="flex-1 rounded-sm hover:bg-orange-600 hover:text-white">
                      <Calculator className="h-3 w-3 mr-1" /> Chiffrer
                    </Button>
                    <Button size="sm" variant="outline" onClick={sendToPrices} data-testid="send-to-prices" className="flex-1 rounded-sm">
                      <Search className="h-3 w-3 mr-1" /> Prix
                    </Button>
                  </div>
                </div>
              )}
            </TabsContent>

            <TabsContent value="materials" className="mt-3 grid gap-3">
              <div className="grid gap-2">
                <Label>Matériau du sol</Label>
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
                <Calculator className="h-4 w-4" /> Calculer matériaux
              </Button>
              {materials && (
                <div className="grid gap-3 text-xs" data-testid="materials-result">
                  {materials.floor && <MatCard label={`Sol (${materials.floor.material})`}
                    lines={[[`Surface`, `${materials.floor.surface_m2} m²`], [`+${materials.floor.waste_pct}% pertes`, `${materials.floor.quantity_m2} m² à commander`]]} />}
                  {materials.paint && <MatCard label="Peinture" lines={[
                    [`Surface`, `${materials.paint.surface_m2} m²`],
                    [`${materials.paint.coats} couches, marge ${materials.paint.margin_pct}%`, `${materials.paint.liters_recommended} L`],
                  ]} />}
                  {materials.placo && <MatCard label="Placo BA13" lines={[
                    [`Surface`, `${materials.placo.surface_m2} m²`],
                    [`+${materials.placo.waste_pct}% pertes`, `${materials.placo.plates} plaques`],
                  ]} />}
                  {materials.skirting && <MatCard label="Plinthes" lines={[
                    [`Périmètre - portes`, `${materials.skirting.net_m} m`],
                    [`+ pertes`, `${materials.skirting.quantity_m} m`],
                  ]} />}
                </div>
              )}
            </TabsContent>

            <TabsContent value="ai" className="mt-3 grid gap-3">
              <CotesCheckPanel plan={plan} pageIndex={pageIndex} refreshPlan={refreshPlan}
                               selectedIndex={selectedCheckedCote} onFocusCote={focusCheckedCote} />
              {!plan.ai_analysis && (
                <p className="text-xs text-muted-foreground">
                  Choisissez une analyse en haut, puis cliquez sur <b>Analyser le plan</b>. Vérifiez ici les pièces, ouvertures et surfaces lues.
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
                      <p className="overline">Symboles détectés</p>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                            <Zap className="h-3 w-3 text-primary" /> Électricité
                          </p>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {[["Prises", "outlets"], ["Inter.", "switches"], ["Pts lum.", "light_points"], ["Spots", "spots"], ["Tableau", "panels"], ["RJ45/TV", "network_tv"]]
                              .map(([lbl, k]) => (plan.ai_analysis.electrical?.[k] ? (
                                <Badge key={k} variant="outline" className="rounded-sm num text-[10px]">
                                  {plan.ai_analysis.electrical[k]} {lbl}
                                </Badge>) : null))}
                            {!Object.values(plan.ai_analysis.electrical || {}).some((v) => typeof v === "number" && v > 0) && (
                              <span className="text-[10px] text-muted-foreground">Aucun symbole</span>
                            )}
                          </div>
                        </div>
                        <div>
                          <p className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                            <Droplet className="h-3 w-3 text-primary" /> Plomberie
                          </p>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {[["WC", "wc"], ["Lavabos", "washbasins"], ["Douches", "showers"], ["Baignoires", "bathtubs"], ["Éviers", "kitchen_sinks"], ["Chauffe-eau", "water_heaters"], ["Lave-linge", "washing_machines"]]
                              .map(([lbl, k]) => (plan.ai_analysis.plumbing?.[k] ? (
                                <Badge key={k} variant="outline" className="rounded-sm num text-[10px]">
                                  {plan.ai_analysis.plumbing[k]} {lbl}
                                </Badge>) : null))}
                            {!Object.values(plan.ai_analysis.plumbing || {}).some((v) => typeof v === "number" && v > 0) && (
                              <span className="text-[10px] text-muted-foreground">Aucun symbole</span>
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
                        <Wand2 className="h-3 w-3 text-primary" /> Client détecté sur le plan
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
                            toast.success(data.duplicate ? "Fiche client déjà existante — ouverture du devis" : "Fiche client créée — préparation du devis");
                            nav(`/devis-editeur?plan=${plan.plan_id}&client=${data.client_id}`);
                          } catch (e) {
                            toast.error(e?.response?.data?.detail || "Création impossible");
                          }
                        }}>
                        <Wand2 className="h-3 w-3" /> Créer client + devis
                      </Button>
                    </div>
                  )}

                  {/* --- ACTIONS COTES & TEXTES (iter62) --- */}
                  {!plan.ai_analysis.error && (
                    <div className="border border-primary/30 bg-primary/5 p-2 rounded-sm grid gap-2"
                         data-testid="ai-text-actions">
                      <p className="overline text-primary">Actions cotes & textes</p>
                      {(plan.ai_analysis.dimension_lines || []).some((d) => d.bbox_norm) && (
                        <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                disabled={aiActionBusy} onClick={calibrateFromCotes}
                                data-testid="calibrate-from-cotes-btn">
                          <Ruler className="h-3.5 w-3.5" />
                          Calibrer par les cotes ({(plan.ai_analysis.dimension_lines || []).filter((d) => d.bbox_norm).length})
                        </Button>
                      )}
                      <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                              disabled={aiActionBusy} onClick={applyAiTexts}
                              data-testid="apply-ai-texts-btn">
                        <Sparkles className="h-3.5 w-3.5" />
                        Appliquer les textes du plan
                      </Button>
                      {currentCalib && rooms.some((r) => r.page_index === pageIndex) &&
                        (plan.ai_analysis.rooms || []).some((r) => r.surface_written_m2) && (
                        <>
                          <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                  disabled={aiActionBusy} onClick={() => checkWrittenSurfaces(false)}
                                  data-testid="reconcile-check-btn">
                            <Square className="h-3.5 w-3.5" />
                            Vérifier les surfaces écrites
                          </Button>
                          <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                  disabled={aiActionBusy} onClick={downloadEcartsPdf}
                                  data-testid="ecarts-pdf-btn">
                            <FileDown className="h-3.5 w-3.5" />
                            Rapport écarts (PDF)
                          </Button>
                          <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                  disabled={aiActionBusy}
                                  onClick={() => setSendEcartsDialog(true)}
                                  data-testid="send-ecarts-btn">
                            <Mail className="h-3.5 w-3.5" />
                            Envoyer au client
                          </Button>
                        </>
                      )}
                      {(plan.sent_reports || []).some((s) => s.kind === "ecarts") && (
                        <div className="grid gap-0.5 pt-1.5 border-t border-border/50"
                             data-testid="sent-reports-list">
                          <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide">
                            Rapports envoyés
                          </p>
                          {(plan.sent_reports || [])
                            .filter((s) => s.kind === "ecarts")
                            .slice(-3).reverse().map((s, i) => (
                            <div key={i} className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground"
                                 data-testid={`sent-report-${i}`}>
                              <span className="truncate">✉ {s.to_email}</span>
                              <span className="flex items-center gap-1.5 shrink-0">
                                <span className="num">
                                  {new Date(s.sent_at).toLocaleDateString("fr-FR")}{" "}
                                  {new Date(s.sent_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                                </span>
                                <button onClick={() => resendReport(s)} disabled={sendingEcarts}
                                        className="text-primary hover:text-orange-600 disabled:opacity-40 transition"
                                        title={`Renvoyer à ${s.to_email}`}
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
                            Écart médian mesuré ↔ écrit : <b className="num">{reconcile.deviation_pct}%</b>
                            {" "}({reconcile.matches.length} pièce{reconcile.matches.length > 1 ? "s" : ""} comparée{reconcile.matches.length > 1 ? "s" : ""})
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
                              Recaler l'échelle ({reconcile.current_ppm?.toFixed(1)} → {reconcile.proposed_ppm?.toFixed(1)} px/m)
                            </Button>
                          ) : (
                            <p className="text-[10px] text-green-600">
                              ✓ Calibration cohérente (écart ≤ 5%) — aucun recalage nécessaire
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
                      <p className="overline text-primary">Totaux gros œuvre</p>
                      {plan.ai_analysis.totals_gros_oeuvre.linear_walls_m != null && (
                        <div className="flex justify-between"><span>Linéaire murs total</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.linear_walls_m} ml</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.facade_walls_area_net_m2 != null && (
                        <div className="flex justify-between"><span>Façades (net)</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.facade_walls_area_net_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.interior_walls_area_m2 != null && (
                        <div className="flex justify-between"><span>Cloisons intérieures</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.interior_walls_area_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.openings_area_m2 != null && (
                        <div className="flex justify-between"><span>Ouvertures</span>
                          <b className="num text-destructive">-{plan.ai_analysis.totals_gros_oeuvre.openings_area_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.floor_slab_area_m2 != null && (
                        <div className="flex justify-between"><span>Planchers/dalles</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.floor_slab_area_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.concrete_volume_m3_estimated != null && (
                        <div className="flex justify-between"><span>Volume béton estimé</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.concrete_volume_m3_estimated} m³</b></div>
                      )}
                    </div>
                  )}

                  {/* --- PIÈCES --- */}
                  {(plan.ai_analysis.rooms || []).length > 0 && (
                    <div className="border border-border p-2 rounded-sm">
                      <p className="overline mb-2">Pièces ({plan.ai_analysis.rooms.length})</p>
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
                      <p className="overline mb-2">Façades ({plan.ai_analysis.facade_walls.length})</p>
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
                      <p className="overline mb-2">Escaliers ({plan.ai_analysis.stairwells.length})</p>
                      {plan.ai_analysis.stairwells.map((s, i) => (
                        <div key={i} className="text-xs py-1 border-b last:border-b-0 border-border/50">
                          <div className="flex justify-between">
                            <span>{s.type || "?"} · {(s.connects_levels || []).join(" → ") || "?"}</span>
                            <span className="num">{s.footprint_m2} m²</span>
                          </div>
                          {s.steps && (
                            <div className="text-muted-foreground text-[10px] num">
                              {s.steps} marches · trémie {s.trémie_area_m2 || "?"} m²
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* --- OUVERTURES DÉTAIL --- */}
                  {plan.ai_analysis.openings?.details?.length > 0 && (
                    <div className="border border-border p-2 rounded-sm">
                      <p className="overline mb-2">Ouvertures détaillées ({plan.ai_analysis.openings.details.length})</p>
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
                      <span>Total surfaces habitables</span>
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
                      Importer ces pièces dans le métré →
                    </Button>
                  )}
                </div>
              )}
            </TabsContent>
            <TabsContent value="history" className="mt-3 grid gap-2">
              {historyLoading ? (
                <p className="text-xs text-muted-foreground">Chargement…</p>
              ) : history.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Aucun historique — l'app enregistre automatiquement les modifications (calibration, pièces, niveaux).
                </p>
              ) : (
                <div className="grid gap-2 text-xs" data-testid="history-list">
                  {/* Compare toolbar */}
                  <div className="border border-border rounded-sm p-2 bg-secondary/30 flex items-center justify-between gap-2 flex-wrap">
                    <p className="text-[10px] text-muted-foreground">
                      Sélectionnez 2 snapshots à comparer (A puis B) :
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
                        Comparer
                      </Button>
                      {(snapPickA || snapPickB || snapCompareResult) && (
                        <Button size="sm" variant="ghost"
                                onClick={() => { setSnapPickA(null); setSnapPickB(null); setSnapCompareResult(null); }}
                                data-testid="snap-compare-clear"
                                className="rounded-sm gap-1 h-6 text-[10px]">
                          Reset
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Compare result panel */}
                  {snapCompareResult && (
                    <div className="border border-primary/40 bg-primary/5 rounded-sm p-3"
                         data-testid="snap-compare-result">
                      <p className="font-bold text-primary mb-2">
                        Diff : {snapCompareResult.before.label || snapCompareResult.before.action}
                        {" → "}
                        {snapCompareResult.after.label || snapCompareResult.after.action}
                      </p>
                      <div className="grid grid-cols-4 gap-2 text-[10px]">
                        <div className="text-emerald-500">+{snapCompareResult.added.length} ajoutées</div>
                        <div className="text-destructive">−{snapCompareResult.removed.length} retirées</div>
                        <div className="text-amber-500">~{snapCompareResult.modified.length} modifiées</div>
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
                              {new Date(s.created_at).toLocaleString("fr-FR")} · {s.rooms?.length || 0} pièces
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
                              {s.label ? "Renommer" : "Nommer"}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => restoreSnapshot(s.snapshot_id)}
                                    data-testid={`restore-${s.snapshot_id}`}
                                    className="rounded-sm gap-1 text-xs h-6">
                              Restaurer
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
            <DialogTitle>Envoyer le rapport d'écarts au client</DialogTitle>
            <DialogDescription>
              Le PDF de contrôle des surfaces (mesurées vs écrites) sera joint à l'email.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="ecarts-email">Email du client</Label>
              <Input id="ecarts-email" type="email" placeholder="client@exemple.fr"
                     value={ecartsEmail} onChange={(e) => setEcartsEmail(e.target.value)}
                     data-testid="ecarts-email-input" className="rounded-sm" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="ecarts-message">Mot personnalisé (optionnel)</Label>
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
                              title="Supprimer ce modèle"
                              data-testid={`msg-template-delete-${t.template_id}`}>
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <Textarea id="ecarts-message" rows={4}
                        placeholder="Bonjour, veuillez trouver ci-joint le rapport de contrôle des surfaces de votre projet…"
                        value={ecartsMessage} onChange={(e) => setEcartsMessage(e.target.value)}
                        data-testid="ecarts-message-input" className="rounded-sm" />
              {ecartsMessage.trim() && (
                <button onClick={saveMsgTemplate}
                        className="justify-self-start text-[11px] text-primary hover:text-orange-600 transition underline underline-offset-2"
                        data-testid="save-msg-template-btn">
                  + Enregistrer ce message comme modèle
                </button>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSendEcartsDialog(false)}
                    className="rounded-sm" data-testid="ecarts-send-cancel">Annuler</Button>
            <Button onClick={sendEcartsReport} disabled={sendingEcarts}
                    className="rounded-sm gap-2" data-testid="ecarts-send-confirm">
              <Mail className="h-3.5 w-3.5" />
              {sendingEcarts ? "Envoi…" : "Envoyer le rapport"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CALIB DIALOG */}
      <Dialog open={calibDialog} onOpenChange={setCalibDialog}>
        <DialogContent className="rounded-sm z-[70]" overlayClassName="z-[70]" data-testid="calib-dialog">
          <DialogHeader>
            <DialogTitle>Distance réelle entre les 2 points ?</DialogTitle>
            <DialogDescription>
              Saisissez une cote connue du plan (ex : 4,25 m). ConstruPilot recalibrera tout automatiquement.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="calib-dist">Distance en mètres</Label>
            <Input
              id="calib-dist" value={calibDist} onChange={(e) => setCalibDist(e.target.value)}
              placeholder="4.25" data-testid="calib-distance-input"
              className="rounded-sm num h-11" autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCalibDialog(false); setPoints([]); }} className="rounded-sm">Annuler</Button>
            <Button onClick={applyCalibration} data-testid="calib-confirm-btn"
                    className="rounded-sm hover:bg-orange-600 hover:text-white">Calibrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* OPENING DIALOG */}
      <Dialog open={!!openingsDialog} onOpenChange={(o) => { if (!o) { setOpeningsDialog(null); setPoints([]); } }}>
        <DialogContent className="rounded-sm" data-testid="opening-dialog">
          <DialogHeader>
            <DialogTitle>Ouverture sur {openingsDialog?.room_name}</DialogTitle>
            <DialogDescription>
              Largeur mesurée depuis vos 2 clics. Ajustez le type et la hauteur ci-dessous.
              La surface sera automatiquement déduite des murs nets.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid grid-cols-3 gap-2">
              {[["porte", "Porte"], ["fenetre", "Fenêtre"], ["baie", "Baie"]].map(([k, l]) => (
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
                <Label className="text-[10px] uppercase">Largeur (m)</Label>
                <Input
                  type="number" step="0.05" min="0.05" max="10"
                  value={pendingOpening.width_m}
                  onChange={(e) => setPendingOpening((o) => ({ ...o, width_m: parseFloat(e.target.value) || 0 }))}
                  className="rounded-sm num h-10"
                  data-testid="opening-width"
                />
              </div>
              <div>
                <Label className="text-[10px] uppercase">Hauteur (m)</Label>
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
                <Label className="text-[10px] uppercase">Nombre</Label>
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
              <Label className="text-[10px] uppercase">Libellé (optionnel)</Label>
              <Input
                value={pendingOpening.label}
                onChange={(e) => setPendingOpening((o) => ({ ...o, label: e.target.value }))}
                placeholder="Porte d'entrée sud"
                className="rounded-sm h-10"
                data-testid="opening-label"
              />
            </div>
            <div className="text-xs text-muted-foreground border border-border rounded-sm p-2 bg-secondary/30">
              Surface totale déduite : <b className="text-primary num">
                {(pendingOpening.width_m * pendingOpening.height_m * (pendingOpening.count || 1)).toFixed(2)} m²
              </b>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setOpeningsDialog(null); setPoints([]); }} className="rounded-sm">Annuler</Button>
            <Button onClick={submitOpening} data-testid="opening-submit-btn"
                    className="rounded-sm">Ajouter</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ROOM DIALOG */}
      <Dialog open={roomDialog} onOpenChange={setRoomDialog}>
        <DialogContent className="rounded-sm" data-testid="room-dialog">
          <DialogHeader>
            <DialogTitle>Nouvelle pièce</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-2">
              <Label>Nom</Label>
              <Input value={pendingRoomName} onChange={(e) => setPendingRoomName(e.target.value)}
                     data-testid="room-name-input" className="rounded-sm h-10" autoFocus />
            </div>
            <div className="grid gap-2">
              <Label>Hauteur sous plafond (m)</Label>
              <Input type="number" step="0.1" value={ceilingH} onChange={(e) => setCeilingH(e.target.value)}
                     data-testid="room-ceiling-input" className="rounded-sm h-10 num" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRoomDialog(false)} className="rounded-sm">Annuler</Button>
            <Button onClick={saveRoom} data-testid="room-save-btn" className="rounded-sm hover:bg-orange-600 hover:text-white">Enregistrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CHIFFRAGE PAR CORPS D'ÉTAT — composition + estimation (comme le gros œuvre) */}
      <Dialog open={!!chiffrageDialog} onOpenChange={(o) => { if (!o) { setChiffrageDialog(null); setChiffrageResult(null); } }}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" overlayClassName="z-[70]" data-testid="chiffrage-dialog">
          <DialogHeader>
            <DialogTitle>Chiffrer un poste — {chiffrageDialog?.label || "mesure"}</DialogTitle>
            <DialogDescription>
              Décomposition déterministe (fournitures + main d'œuvre) appliquée à la quantité mesurée. Prix par défaut éditables.
            </DialogDescription>
          </DialogHeader>
          {chiffrageDialog && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="grid gap-1">
                  <Label className="text-xs">Poste (corps d'état)</Label>
                  <select value={chiffragePoste} onChange={(e) => setChiffragePoste(e.target.value)}
                          data-testid="chiffrage-poste-select"
                          className="h-9 rounded-md border border-border bg-background px-2 text-sm min-w-[220px]">
                    {posteCatalog.map((p) => (<option key={p.key} value={p.key}>{p.label}</option>))}
                  </select>
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Quantité</Label>
                  <div className="h-9 flex items-center px-2 rounded-md border border-border bg-muted/40 text-sm num" data-testid="chiffrage-qty">
                    {measureQty(chiffrageDialog).q.toFixed(2)} {measureQty(chiffrageDialog).unit}
                  </div>
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Marge (%)</Label>
                  <Input type="number" value={chiffrageMargin} onChange={(e) => setChiffrageMargin(e.target.value)}
                         data-testid="chiffrage-margin" className="h-9 w-20" />
                </div>
                <Button onClick={runChiffrage} disabled={chiffrageLoading} data-testid="chiffrage-run"
                        className="h-9 rounded-sm gap-2">
                  <Calculator className="h-4 w-4" /> {chiffrageLoading ? "Calcul…" : "Calculer"}
                </Button>
              </div>

              {/* Options de composition selon le poste */}
              <div className="flex flex-wrap items-end gap-3" data-testid="chiffrage-options">
                {(chiffragePoste === "placo" || chiffragePoste === "plafond") && (
                  <label className="flex items-center gap-2 text-xs" data-testid="opt-isolation">
                    <input type="checkbox" checked={!!chiffrageOpts.with_isolation}
                           onChange={(e) => setChiffrageOpts((o) => ({ ...o, with_isolation: e.target.checked }))} />
                    Avec isolation
                  </label>
                )}
                {chiffragePoste === "peinture" && (
                  <div className="grid gap-1">
                    <Label className="text-xs">Nombre de couches</Label>
                    <Input type="number" min={1} value={chiffrageOpts.couches} data-testid="opt-couches"
                           onChange={(e) => setChiffrageOpts((o) => ({ ...o, couches: e.target.value }))} className="h-9 w-24" />
                  </div>
                )}
                {chiffragePoste === "chape" && (
                  <div className="grid gap-1">
                    <Label className="text-xs">Épaisseur chape (m)</Label>
                    <Input type="number" step="0.01" value={chiffrageOpts.ep_m} data-testid="opt-ep"
                           onChange={(e) => setChiffrageOpts((o) => ({ ...o, ep_m: e.target.value }))} className="h-9 w-24" />
                  </div>
                )}
                {chiffragePoste === "escalier" && (
                  <div className="grid gap-1">
                    <Label className="text-xs">Nombre de marches</Label>
                    <Input type="number" min={0} value={chiffrageOpts.nb_marches} data-testid="opt-marches"
                           onChange={(e) => setChiffrageOpts((o) => ({ ...o, nb_marches: e.target.value }))} className="h-9 w-24" />
                  </div>
                )}
              </div>

              {/* Bibliothèque d'ouvrages : appliquer / enregistrer une composition */}
              <div className="rounded-sm border border-dashed border-border p-2 space-y-2" data-testid="ouvrages-lib">
                <div className="flex items-center justify-between">
                  <Label className="text-xs font-medium">Bibliothèque d'ouvrages</Label>
                  <span className="text-[10px] text-muted-foreground">réutilisable sur tous vos chantiers</span>
                </div>
                {ouvrages.length > 0 && (
                  <div className="flex flex-wrap gap-1.5" data-testid="ouvrages-list">
                    {ouvrages.map((ov) => (
                      <span key={ov.ouvrage_id} className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 pl-2 pr-1 py-0.5 text-[11px]">
                        <button type="button" onClick={() => applyOuvrage(ov)}
                                data-testid={`apply-ouvrage-${ov.ouvrage_id}`}
                                className="hover:text-primary" title="Appliquer cet ouvrage">
                          {ov.name} <span className="text-muted-foreground">· {ov.poste}</span>
                          {ov.is_shared && <span className="ml-1 rounded-full bg-primary/15 text-primary px-1 text-[9px]" title={`Partagé par ${ov.owner_name || "l'équipe"}`}>équipe</span>}
                        </button>
                        {ov.is_mine !== false && (
                          <button type="button" onClick={() => deleteOuvrage(ov.ouvrage_id)}
                                  data-testid={`delete-ouvrage-${ov.ouvrage_id}`}
                                  className="text-muted-foreground hover:text-destructive px-1" title="Supprimer">×</button>
                        )}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <Input value={saveOuvrageName} onChange={(e) => setSaveOuvrageName(e.target.value)}
                         placeholder="Nom de l'ouvrage (ex : Cloison BA13 isolée)"
                         data-testid="ouvrage-name-input" className="h-8 flex-1 text-xs" />
                  <label className="flex items-center gap-1 text-[11px] whitespace-nowrap" data-testid="ouvrage-shared-toggle" title="Visible par toute l'équipe de l'entreprise">
                    <input type="checkbox" checked={saveOuvrageShared} onChange={(e) => setSaveOuvrageShared(e.target.checked)} /> Équipe
                  </label>
                  <Button size="sm" variant="outline" onClick={saveCurrentAsOuvrage}
                          data-testid="save-ouvrage-btn" className="h-8 rounded-sm gap-1 text-[11px]">
                    <Save className="h-3 w-3" /> Enregistrer
                  </Button>
                </div>
              </div>

              {chiffrageResult && (
                <div className="space-y-2" data-testid="chiffrage-result">
                  <div className="rounded border border-border overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50 text-xs">
                        <tr><th className="p-2 text-left">Désignation</th><th className="p-2 text-right">Qté</th><th className="p-2">Unité</th><th className="p-2 text-right">PU HT (€)</th><th className="p-2 text-right">Total HT</th></tr>
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
                    <span>Total HT : <b className="num">{chiffrageResult.totals.ht.toFixed(2)} €</b></span>
                    <span>+ Marge {chiffrageResult.totals.margin_pct}% : <b className="num">{chiffrageResult.totals.ht_with_margin.toFixed(2)} €</b></span>
                    <span>TTC : <b className="num text-primary">{chiffrageResult.totals.ttc.toFixed(2)} €</b></span>
                  </div>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setChiffrageDialog(null); setChiffrageResult(null); }} className="rounded-sm">Fermer</Button>
            <Button onClick={addChiffrageToDevis} disabled={!chiffrageResult} data-testid="chiffrage-add-devis" className="rounded-sm gap-2">
              <ArrowRight className="h-4 w-4" /> Ajouter au devis
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>


      {/* CHIFFRAGE DE PAGE — récapitulatif multi-postes */}
      <Dialog open={!!pageChiffrage} onOpenChange={(o) => { if (!o) setPageChiffrage(null); }}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" overlayClassName="z-[70]" data-testid="page-chiffrage-dialog">
          <DialogHeader>
            <DialogTitle>Chiffrage de la page — {pageChiffrage?.count} poste(s)</DialogTitle>
            <DialogDescription>
              Estimation de toutes les mesures ayant un poste défini, avec vos prix/ratios enregistrés.
            </DialogDescription>
          </DialogHeader>
          {pageChiffrage && (
            <div className="space-y-2 max-h-[55vh] overflow-auto">
              {pageChiffrage.items.map((it) => (
                <div key={it.measurement_id} className="rounded border border-border p-2" data-testid={`page-chiffrage-item-${it.measurement_id}`}>
                  <div className="flex justify-between text-sm font-medium">
                    <span>{it.label || it.label} <span className="text-muted-foreground">· {it.label !== it.poste ? it.label : ""}</span></span>
                    <span className="num">{it.totals.ht_with_margin.toFixed(2)} € HT</span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">{it.quantity} {it.unit} — {it.lines.length} lignes</div>
                </div>
              ))}
              {pageChiffrage.skipped > 0 && (
                <p className="text-[11px] text-muted-foreground">{pageChiffrage.skipped} mesure(s) ignorée(s) (sans poste).</p>
              )}
              <div className="flex justify-end gap-4 text-sm font-semibold border-t border-border pt-2">
                <span>Total HT : <span className="num">{pageChiffrage.totals.ht_with_margin.toFixed(2)} €</span></span>
                <span>TTC : <span className="num text-primary">{pageChiffrage.totals.ttc.toFixed(2)} €</span></span>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPageChiffrage(null)} className="rounded-sm">Fermer</Button>
            <Button onClick={addPageChiffrageToDevis} data-testid="page-chiffrage-add-devis" className="rounded-sm gap-2">
              <ArrowRight className="h-4 w-4" /> Tout ajouter au devis
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* BIBLIOTHÈQUE DE PRIX & RATIOS */}
      <Dialog open={priceLibOpen} onOpenChange={setPriceLibOpen}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" overlayClassName="z-[70]" data-testid="price-lib-dialog">
          <DialogHeader>
            <DialogTitle>Ma bibliothèque — prix & ratios</DialogTitle>
            <DialogDescription>
              Enregistrez vos prix unitaires et vos ratios de composition : ils pré-remplissent automatiquement chaque chiffrage.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-3 rounded-sm border border-border bg-muted/30 p-2 mb-2">
            <Label className="text-xs flex-1">Hauteur sous-plafond par défaut du chantier (m)
              <span className="block text-[10px] text-muted-foreground font-normal">Utilisée par les presets « peinture murs » & « mur net m² »</span>
            </Label>
            <Input type="number" step="0.05" value={priceLib.default_wall_height ?? ""}
                   onChange={(e) => setPriceLib((lib) => ({ ...lib, default_wall_height: e.target.value }))}
                   data-testid="price-lib-default-height" className="h-8 w-24 text-right num" />
          </div>
          <div className="flex gap-2 mb-2">
            <Button size="sm" variant={priceLibTab === "prices" ? "default" : "outline"}
                    onClick={() => setPriceLibTab("prices")} data-testid="price-lib-tab-prices" className="rounded-sm">Prix unitaires</Button>
            <Button size="sm" variant={priceLibTab === "ratios" ? "default" : "outline"}
                    onClick={() => setPriceLibTab("ratios")} data-testid="price-lib-tab-ratios" className="rounded-sm">Ratios</Button>
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
            <Button variant="outline" onClick={() => setPriceLibOpen(false)} className="rounded-sm">Annuler</Button>
            <Button onClick={savePriceLib} disabled={priceLibSaving} data-testid="price-lib-save" className="rounded-sm gap-2">
              <Save className="h-4 w-4" /> {priceLibSaving ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* PRESET PIÈCE — sol + plinthes + peinture murs + plafond en un clic */}
      <Dialog open={roomPresetOpen} onOpenChange={(o) => { if (!o) { setRoomPresetOpen(false); setRoomPresetResult(null); } }}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" overlayClassName="z-[70]" data-testid="room-preset-dialog">
          <DialogHeader>
            <DialogTitle>Preset pièce — chiffrage en un clic</DialogTitle>
            <DialogDescription>
              Renseignez l'aire, le périmètre et la hauteur : sol, plinthes, peinture murs et plafond sont chiffrés
              automatiquement avec vos prix/ratios. La hauteur par défaut ({ceDefaultHeight} m) est utilisée si laissée vide.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="grid gap-1">
                <Label className="text-xs">Aire (m²)</Label>
                <Input type="number" step="0.01" value={roomPresetIn.area_m2} data-testid="preset-area"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, area_m2: e.target.value }))} className="h-9" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Périmètre (m)</Label>
                <Input type="number" step="0.01" value={roomPresetIn.perimeter_m} data-testid="preset-perimeter"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, perimeter_m: e.target.value }))} className="h-9" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Hauteur (m)</Label>
                <Input type="number" step="0.05" value={roomPresetIn.height_m} data-testid="preset-height"
                       placeholder={String(ceDefaultHeight)}
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, height_m: e.target.value }))} className="h-9" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Déduction portes (m)</Label>
                <Input type="number" step="0.01" value={roomPresetIn.door_deduction_m} data-testid="preset-door-deduction"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, door_deduction_m: e.target.value }))} className="h-9" />
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-4">
              <label className="flex items-center gap-2 text-xs" data-testid="preset-inc-sol">
                <input type="checkbox" checked={roomPresetIn.sol} onChange={(e) => setRoomPresetIn((s) => ({ ...s, sol: e.target.checked }))} /> Sol
              </label>
              <select value={roomPresetIn.sol_poste} disabled={!roomPresetIn.sol} data-testid="preset-sol-poste"
                      onChange={(e) => setRoomPresetIn((s) => ({ ...s, sol_poste: e.target.value }))}
                      className="h-8 rounded-md border border-border bg-background px-2 text-xs">
                <option value="carrelage">Carrelage</option>
                <option value="parquet">Parquet</option>
                <option value="chape">Chape</option>
              </select>
              <label className="flex items-center gap-2 text-xs" data-testid="preset-inc-plinthes">
                <input type="checkbox" checked={roomPresetIn.plinthes} onChange={(e) => setRoomPresetIn((s) => ({ ...s, plinthes: e.target.checked }))} /> Plinthes
              </label>
              <label className="flex items-center gap-2 text-xs" data-testid="preset-inc-peinture">
                <input type="checkbox" checked={roomPresetIn.peinture_murs} onChange={(e) => setRoomPresetIn((s) => ({ ...s, peinture_murs: e.target.checked }))} /> Peinture murs
              </label>
              <label className="flex items-center gap-2 text-xs" data-testid="preset-inc-plafond">
                <input type="checkbox" checked={roomPresetIn.plafond} onChange={(e) => setRoomPresetIn((s) => ({ ...s, plafond: e.target.checked }))} /> Plafond
              </label>
              <select value={roomPresetIn.plafond_poste} disabled={!roomPresetIn.plafond} data-testid="preset-plafond-poste"
                      onChange={(e) => setRoomPresetIn((s) => ({ ...s, plafond_poste: e.target.value }))}
                      className="h-8 rounded-md border border-border bg-background px-2 text-xs">
                <option value="peinture">Peinture plafond</option>
                <option value="plafond">Plafond placo</option>
              </select>
              <div className="grid gap-1">
                <Label className="text-xs">Couches peinture</Label>
                <Input type="number" min={1} value={roomPresetIn.couches} data-testid="preset-couches"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, couches: e.target.value }))} className="h-8 w-20" />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Marge (%)</Label>
                <Input type="number" value={roomPresetIn.margin_pct} data-testid="preset-margin"
                       onChange={(e) => setRoomPresetIn((s) => ({ ...s, margin_pct: e.target.value }))} className="h-8 w-20" />
              </div>
              <Button onClick={runRoomPreset} disabled={roomPresetLoading} data-testid="preset-run" className="h-9 rounded-sm gap-2">
                <Calculator className="h-4 w-4" /> {roomPresetLoading ? "Calcul…" : "Chiffrer la pièce"}
              </Button>
            </div>

            {roomPresetResult && (
              <div className="space-y-2 max-h-[45vh] overflow-auto" data-testid="preset-result">
                {roomPresetResult.items.map((it, i) => (
                  <div key={i} className="rounded border border-border p-2" data-testid={`preset-item-${it.slot}`}>
                    <div className="flex justify-between text-sm font-medium">
                      <span>{it.slot} <span className="text-muted-foreground">· {it.label}</span></span>
                      <span className="num">{it.totals.ht_with_margin.toFixed(2)} € HT</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">{it.quantity} {it.unit} — {it.lines.length} lignes</div>
                  </div>
                ))}
                <div className="flex justify-end gap-4 text-sm font-semibold border-t border-border pt-2">
                  <span>Total HT : <span className="num">{roomPresetResult.totals.ht_with_margin.toFixed(2)} €</span></span>
                  <span>TTC : <span className="num text-primary">{roomPresetResult.totals.ttc.toFixed(2)} €</span></span>
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setRoomPresetOpen(false); setRoomPresetResult(null); }} className="rounded-sm">Fermer</Button>
            <Button onClick={addRoomPresetToDevis} disabled={!roomPresetResult} data-testid="preset-add-devis" className="rounded-sm gap-2">
              <ArrowRight className="h-4 w-4" /> Tout ajouter au devis
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* MÉTRÉ COMPARÉ — versions d'un niveau */}
      <Dialog open={metreVerOpen} onOpenChange={setMetreVerOpen}>
        <DialogContent className="rounded-sm max-w-2xl z-[70]" data-testid="metre-versions-dialog">
          <DialogHeader>
            <DialogTitle>Métré comparé — versions du niveau</DialogTitle>
            <DialogDescription>Figez l'état du métré à un instant T, puis comparez deux versions (avant / après modification).</DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2">
            <Input value={metreLabel} onChange={(e) => setMetreLabel(e.target.value)}
                   placeholder="Nom de la version (ex : Avant modif client)" data-testid="metre-version-label" className="h-9 flex-1" />
            <Button size="sm" onClick={snapshotMetre} data-testid="metre-snapshot-btn" className="rounded-sm gap-1"><Save className="h-4 w-4" /> Figer</Button>
          </div>
          <div className="space-y-1.5 max-h-48 overflow-auto">
            {metreVersions.length === 0 && <p className="text-xs text-muted-foreground">Aucune version enregistrée.</p>}
            {metreVersions.map((v) => (
              <div key={v.version_id} className={`flex items-center gap-2 rounded border p-2 text-sm ${metreSel.includes(v.version_id) ? "border-primary bg-primary/5" : "border-border"}`} data-testid={`metre-version-${v.version_id}`}>
                <input type="checkbox" checked={metreSel.includes(v.version_id)} onChange={() => toggleMetreSel(v.version_id)} data-testid={`metre-pick-${v.version_id}`} />
                <span className="flex-1">{v.label} <span className="text-[11px] text-muted-foreground">· {v.summary?.area_m2 || 0} m² · {v.summary?.ht || 0} € HT</span></span>
                <button onClick={() => deleteMetreVersion(v.version_id)} className="text-muted-foreground hover:text-destructive"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            ))}
          </div>
          <Button variant="outline" onClick={runMetreCompare} disabled={metreSel.length !== 2} data-testid="metre-compare-btn" className="rounded-sm w-full">Comparer les 2 versions sélectionnées</Button>
          {metreCompare && (
            <div className="rounded border border-border p-3 space-y-2" data-testid="metre-compare-result">
              <div className="flex justify-between text-sm font-medium">
                <span>{metreCompare.a.label} → {metreCompare.b.label}</span>
                <span className={metreCompare.delta.ht >= 0 ? "text-emerald-600" : "text-red-600"}>{metreCompare.delta.ht >= 0 ? "+" : ""}{metreCompare.delta.ht.toFixed(2)} € HT</span>
              </div>
              <div className="text-[11px] text-muted-foreground">Δ surface {metreCompare.delta.area_m2} m² · Δ linéaire {metreCompare.delta.length_ml} ml · Δ mesures {metreCompare.delta.measures}</div>
              {metreCompare.by_poste.length > 0 && (
                <table className="w-full text-xs">
                  <thead className="text-muted-foreground"><tr><th className="text-left">Poste</th><th className="text-right">Qté A→B</th><th className="text-right">Δ HT</th></tr></thead>
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
            <DialogTitle>Nommer cette version</DialogTitle>
            <DialogDescription>
              Donnez à ce snapshot un nom parlant (ex : « Version client 12/02 »,
              « Avant modification cloison »).
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="snap-label">Nom du snapshot</Label>
            <Input id="snap-label" value={labelValue}
                   onChange={(e) => setLabelValue(e.target.value)}
                   placeholder="Version client · 12/02"
                   maxLength={80} autoFocus
                   data-testid="label-input" className="rounded-sm h-11" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLabelDialog(null)} className="rounded-sm">
              Annuler
            </Button>
            <Button onClick={saveSnapshotLabel} data-testid="label-save-btn"
                    className="rounded-sm hover:bg-orange-600 hover:text-white">
              Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* COMPARAISON DE RÉGLAGES (Maison vs Immeuble) */}
      <Dialog open={compareOpen} onOpenChange={setCompareOpen}>
        <DialogContent className="sm:max-w-lg" data-testid="beton-compare-dialog">
          <DialogHeader>
            <DialogTitle>Comparer les réglages béton</DialogTitle>
            <DialogDescription>Métré du plan courant selon chaque type de chantier — pour aider au choix.</DialogDescription>
          </DialogHeader>
          {compareBusy && <p className="text-sm text-primary animate-pulse">Calcul en cours…</p>}
          {!compareBusy && compareData && (
            <table className="w-full text-xs" data-testid="beton-compare-table">
              <thead className="bg-muted/60"><tr>
                <th className="text-left px-2 py-1">Poste</th>
                {compareData.map((c) => <th key={c.name} className="text-right px-2 py-1">{c.name}</th>)}
              </tr></thead>
              <tbody>
                {[["Béton total", "beton_total_m3", "m³"], ["Aciers", "acier_total_kg", "kg"],
                  ["Poteaux (béton)", "beton_poteaux_m3", "m³"], ["Poutres (béton)", "beton_poutres_m3", "m³"],
                  ["Dalles (béton)", "beton_dalles_m3", "m³"], ["Voiles (béton)", "beton_voiles_m3", "m³"]].map(([lbl, k, u]) => (
                  <tr key={k} className="border-t border-border">
                    <td className="px-2 py-1 text-muted-foreground">{lbl}</td>
                    {compareData.map((c) => <td key={c.name} className="px-2 py-1 num text-right">{c.d?.[k] ?? 0} {u}</td>)}
                  </tr>
                ))}
                {(betonPriceM3 > 0 || acierPriceKg > 0) && (
                  <tr className="border-t border-border font-semibold">
                    <td className="px-2 py-1">Coût matière</td>
                    {compareData.map((c) => (
                      <td key={c.name} className="px-2 py-1 num text-right text-emerald-700">
                        {Math.round((c.d?.beton_total_m3 || 0) * (c.beton_price_m3 || betonPriceM3) + (c.d?.acier_total_kg || 0) * (c.acier_price_kg || acierPriceKg)).toLocaleString("fr-FR")} €
                      </td>
                    ))}
                  </tr>
                )}
                {(betonPriceM3 > 0 || acierPriceKg > 0 || laborPriceM3 > 0) && (
                  <tr className="border-t border-border font-bold">
                    <td className="px-2 py-1">Prix de vente estimé</td>
                    {compareData.map((c) => {
                      const bp = c.beton_price_m3 || betonPriceM3, ap = c.acier_price_kg || acierPriceKg;
                      const lp = c.labor_price_m3 || laborPriceM3, mg = c.margin_pct || marginPct;
                      const pv = (((c.d?.beton_total_m3 || 0) * bp + (c.d?.acier_total_kg || 0) * ap) + (c.d?.beton_total_m3 || 0) * lp) * (1 + mg / 100);
                      return <td key={c.name} className="px-2 py-1 num text-right text-primary">{Math.round(pv).toLocaleString("fr-FR")} €</td>;
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
            <DialogTitle className="flex items-center gap-2"><Bot className="h-5 w-5 text-primary" /> Assistant IA — corriger le plan</DialogTitle>
            <DialogDescription>
              Décrivez ce que l'IA doit corriger ou ajouter. Ex : « il manque 2 poteaux en bas à droite »,
              « les semelles font 1,2×1,2 m », « ignore les traits de cote », « ajoute une poutre entre P3 et P4 ».
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-72 overflow-auto space-y-2 rounded-sm border border-border p-2 bg-muted/30" data-testid="ai-assistant-messages">
            {aiMessages.length === 0 && (
              <p className="text-xs text-muted-foreground">Aucun échange pour l'instant. Donnez votre première consigne ci-dessous.</p>
            )}
            {aiMessages.map((m, i) => (
              <div key={i} className={`text-xs rounded-sm px-2 py-1.5 ${m.role === "user" ? "bg-primary/10 ml-6" : m.ok === false ? "bg-destructive/10 mr-6" : "bg-background border border-border mr-6"}`}>
                <span className="font-semibold">{m.role === "user" ? "Vous" : "IA"} : </span>{m.text}
              </div>
            ))}
            {aiChatBusy && <p className="text-xs text-primary animate-pulse">L'IA analyse le plan…</p>}
          </div>
          <div className="flex items-end gap-2">
            <Textarea value={aiInput} onChange={(e) => setAiInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAiInstruction(); } }}
                      placeholder="Votre consigne pour l'IA…" rows={2}
                      data-testid="ai-assistant-input" className="rounded-sm text-sm resize-none" />
            <Button onClick={sendAiInstruction} disabled={aiChatBusy || !aiInput.trim()}
                    data-testid="ai-assistant-send" className="rounded-sm gap-1 shrink-0">
              <ArrowRight className="h-4 w-4" /> Envoyer
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
        onAttach3d={(png) => { setPlan3dSnapshot(png); toast.success("Vue 3D jointe — elle sera ajoutée au prochain devis généré depuis ce plan"); }}
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
  if (!prev) return { summary: "État initial" };
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
  return { summary: parts.join(" · ") || "Aucun changement" };
}

