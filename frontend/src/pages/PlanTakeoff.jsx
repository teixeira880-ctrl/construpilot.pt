import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { BrandingDialog } from "@/components/BrandingDialog";
import { MailboxDialog } from "@/components/MailboxDialog";
import { useBilling } from "@/context/BillingContext";
import { Lock, Unlock } from "lucide-react";
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
import { OuvrageComposeDialog } from "@/components/OuvrageComposeDialog";
import { LiveTotalBar } from "@/components/planTakeoff/LiveTotalBar";
import {
  Upload, Ruler, Square, Move, Trash2, RotateCw,
  ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight, Sparkles,
  MousePointer2, Layers, Undo2, Save, Home, Calculator, Search,
  Wand2, Zap, Droplet, FileDown, History, Film, DoorOpen, Copy,
  Hash, StickyNote, Triangle, MountainSnow, X, Mail, Hexagon, Sheet, FileSearch,
  ArrowLeft, Eraser, Plus, ArrowRight, Bot, Minimize2, Contrast, SunMedium,
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
import { api, eur, num } from "@/lib/api";
import PlanCanvas from "@/components/planTakeoff/PlanCanvas";
import { TOOLS, TOOL_LABELS, CALIB_METHOD_LABELS, COUNTER_COLORS } from "@/components/planTakeoff/planConstants";


// ============ MAIN PAGE ============

export default function PlanTakeoff() {
  const nav = useNavigate();
  const { tier, has, loading: billingLoading } = useBilling();
  const [plan, setPlan] = useState(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageData, setPageData] = useState(null);
  const [tool, setTool] = useState(TOOLS.SELECT);
  const [points, setPoints] = useState([]);
  const [zoom, setZoom] = useState(0.5);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState(0);
  const [locked, setLocked] = useState(false);
  const [autoRotated, setAutoRotated] = useState(false);
  // P1 — Ecrã inteiro + definição contraste/luminosité du plan
  const [fullscreen, setFullscreen] = useState(false);
  const [planContrast, setPlanContrast] = useState(1.25);
  const [planBrightness, setPlanBrightness] = useState(1.02);
  const [showImgAdjust, setShowImgAdjust] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  // P2 — type de plan pour l'análise IA : auto / gros œuvre / maison
  const [planKindChoice, setPlanKindChoice] = useState("auto");
  // P3 — Assistant IA d'edição du plan (barre de encomenda + aperçu/appliquer)
  const [aiCmdOpen, setAiCmdOpen] = useState(false);
  const [aiCmd, setAiCmd] = useState("");
  const [aiCmdBusy, setAiCmdBusy] = useState(false);
  const [aiCmdProposal, setAiCmdProposal] = useState(null);
  // Redimensionne le canvas quand on bascule en ecrã inteiro + Échap pour sortir
  useEffect(() => {
    const t = setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
    if (!fullscreen) return () => clearTimeout(t);
    const onKey = (e) => { if (e.key === "Escape") setFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => { clearTimeout(t); window.removeEventListener("keydown", onKey); };
  }, [fullscreen]);
  const [showDimensionLines, setShowDimensionLines] = useState(true);
  // Iter 57 — QuoterPlan-like annotations (par page)
  const [annotations, setAnnotations] = useState({
    counters: [], notes: [], angles: [], pitched_surfaces: [],
  });
  const [activeCounterId, setActiveCounterId] = useState(null);
  const [pitchDegrees, setPitchDegrees] = useState(30);
  // Iter 58 (Vague B) — Painel Objetos + Modelos Outils
  const [objectPanelOpen, setObjectPanelOpen] = useState(false);
  const [currentPreset, setCurrentPreset] = useState(null);
  // Iter 59 (Vague C) — Focus zoom + Orçamento compartimento
  const [focusRequest, setFocusRequest] = useState(null);
  const [roomEstimate, setRoomEstimate] = useState(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
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
  const [descritivo, setDescriptif] = useState(null);
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
  const [marginPct, setMarginPct] = useState(15);
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
  const [marginBeton, setMarginBeton] = useState("");
  const [marginAcier, setMarginAcier] = useState("");
  const [marginLabor, setMarginLabor] = useState("");
  const [betonPresets, setBetonPresets] = useState([]);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareBusy, setCompareBusy] = useState(false);
  const [compareData, setCompareData] = useState(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  useEffect(() => {
    if (!plan?.plan_id) { setDescriptif(null); return; }
    const s = plan.structure?.[String(pageIndex)];
    if (!s || !(s.walls?.length || s.openings?.length || s.beams?.length || s.floors?.length || s.columns?.length)) { setDescriptif(null); return; }
    let cancel = false;
    const aqa = (araseInf !== "" && araseSup !== "" && Number(araseSup) > Number(araseInf))
      ? `&arase_inf=${araseInf}&arase_sup=${araseSup}` : "";
    const aq = `&acier_semelles=${acierRatios.semelles}&acier_poteaux=${acierRatios.poteaux}&acier_poutres=${acierRatios.poutres}&acier_dalles=${acierRatios.dalles}&acier_voiles=${acierRatios.voiles}&poutre_l=${poutreL}&poutre_h=${poutreH}`;
    api.get(`/takeoffs/${plan.plan_id}/analysis/${pageIndex}?wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${aq}${aqa}`)
      .then(({ data }) => { if (!cancel) setDescriptif(data.descritivo); }).catch(() => {});
    return () => { cancel = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan?.plan_id, pageIndex, wallHeight, dalleEp, voileEp, acierRatios, poutreL, poutreH, propreteEp, araseInf, araseSup]);
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
  // Phase A — devis consolidado : sous-traitance (0% TVA) par plan + lien ferraillage
  const [subcontractSel, setSubcontractSel] = useState([]);
  const [consolidatedBusy, setConsolidatedBusy] = useState(false);
  // Quote sends (envois + tracking)
  const [quoteSends, setQuoteSends] = useState([]);
  const fileRef = useRef(null);

  const currentCalib = plan?.calibrations?.[String(pageIndex)];
  const pageMeasurements = useMemo(
    () => (plan?.measurements || []).filter((m) => m.page_index === pageIndex),
    [plan, pageIndex]
  );
  // Fix revue iter63 : les cotes IA ne s'affichent que sur la page analysée
  const aiDimLines = useMemo(() => {
    const ai = plan?.ai_analysis;
    if (!ai || (ai.page_index != null && ai.page_index !== pageIndex)) return [];
    return ai.dimension_lines || [];
  }, [plan, pageIndex]);
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

  // Load page image on demand
  useEffect(() => {
    if (!plan?.plan_id) {
      // Idle state — charger la liste des plans récents pour permettre de rouvrir
      loadAllPlans();
      return;
    }
    api.get(`/takeoffs/${plan.plan_id}/page/${pageIndex}`).then(({ data }) => {
      setPageData(data);
      setPoints([]);
      setOffset({ x: 0, y: 0 });
      setZoom(0.5);
      setRotation(0);
      setAutoRotated(false);
      setDetectedWalls(null);
      setStructure(plan.structure?.[String(pageIndex)] || null);
      setSelectedStruct(null);
      // Load annotations for this page (QuoterPlan-like tools)
      const pageAnnotations = plan.annotations?.[String(pageIndex)] || {};
      setAnnotations({
        counters: pageAnnotations.counters || [],
        notes: pageAnnotations.notes || [],
        angles: pageAnnotations.angles || [],
        pitched_surfaces: pageAnnotations.pitched_surfaces || [],
      });
      setActiveCounterId(null);
    });
  }, [plan?.plan_id, pageIndex]);

  // Auto-save annotations (debounced) whenever they change
  useEffect(() => {
    if (!plan?.plan_id || !pageData) return;
    const total = annotations.counters.length + annotations.notes.length
                + annotations.angles.length + annotations.pitched_surfaces.length;
    if (total === 0) return;
    setSaving(true);
    const t = setTimeout(() => {
      api.patch(`/takeoffs/${plan.plan_id}/annotations`, {
        page_index: pageIndex, ...annotations,
      }).then(() => setSavedAt(Date.now()))
        .catch(() => { /* silent */ })
        .finally(() => setSaving(false));
    }, 600);
    return () => clearTimeout(t);
  }, [annotations, plan?.plan_id, pageIndex, pageData]);

  // Enregistrement manuel — force la persistance immédiate de l'état de la page
  const manualSave = useCallback(async () => {
    if (!plan?.plan_id) return;
    setSaving(true);
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/annotations`, {
        page_index: pageIndex, ...annotations,
      });
      setSavedAt(Date.now());
      toast.success("Plano guardado");
    } catch {
      toast.error("Falha ao guardar");
    } finally {
      setSaving(false);
    }
  }, [plan?.plan_id, pageIndex, annotations]);

  const refreshPlan = useCallback(async () => {
    if (!plan?.plan_id) return;
    const { data } = await api.get(`/takeoffs/${plan.plan_id}`);
    setPlan(data);
    if (data.plan_defaults) {
      setPlanDefaults({
        ceiling_h_m: data.plan_defaults.ceiling_h_m ?? 2.5,
        floor_thickness_m: data.plan_defaults.floor_thickness_m ?? 0.15,
      });
    }
  }, [plan?.plan_id]);

  // Deep-link ?open=<plan_id> (desde le Painel PC / création de devis)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const pid = params.get("open");
    if (!pid) return;
    api.get(`/takeoffs/${pid}`).then(({ data }) => {
      setPlan(data);
      setPageIndex(0);
      if (data.pc_study) setPcDialog(true);
      if (params.get("auto") === "1") setPendingAuto(true);
    }).catch(() => toast.error("Não foi possível abrir este plano"));
  }, []);

  const savePlanDefaults = async (next) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/defaults`, next);
      setPlanDefaults(next);
      toast.success(`Definições : parede ${next.ceiling_h_m} m · plancher ${(next.floor_thickness_m * 100).toFixed(0)} cm`);
    } catch { toast.error("Não foi possível guardar"); }
  };

  const uploadFile = async (file) => {
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) return toast.error("Fichier trop volumineux (>20 Mo)");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (deskewEnabled) fd.append("deskew", "true");
      const { data } = await api.post("/takeoffs/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPlan(data);
      setPageIndex(0);
      const kind = data.kind === "dxf" ? "DXF" : data.kind === "pdf" ? "PDF" : "image";
      toast.success(`${kind} chargé (${data.page_count} page${data.page_count > 1 ? "s" : ""})`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const msg = detail
        || (!e?.response ? "Rede indisponível ou ficheiro demasiado pesado — verifique a sua ligação e tente novamente"
                         : "Importação impossível");
      toast.error(msg);
    } finally { setUploading(false); }
  };

  const onCanvasClick = (pt) => {
    // Reclassify mode : cherche le parede le plus proche (distance point-segment)
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
        const ppm = currentCalib?.pixels_per_meter || 60;
        const px_dist = Math.hypot(next[1][0] - next[0][0], next[1][1] - next[0][1]);
        const width_m = Math.max(0.05, Math.round((px_dist / ppm) * 100) / 100);
        // Find the closest room to the midpoint
        const mid = [(next[0][0] + next[1][0]) / 2, (next[0][1] + next[1][1]) / 2];
        let bestRoom = null, bestDist = Infinity;
        for (const r of rooms) {
          if (r.page_index !== pageIndex) continue;
          const cx = r.points.reduce((a, p) => a + p[0], 0) / r.points.length;
          const cy = r.points.reduce((a, p) => a + p[1], 0) / r.points.length;
          const d = Math.hypot(mid[0] - cx, mid[1] - cy);
          if (d < bestDist) { bestDist = d; bestRoom = r; }
        }
        if (!bestRoom) {
          toast.error("Nenhuma divisão por perto — desenhe primeiro uma divisão");
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
      // Ajoute un marqueur au compteur actif (créer un compteur par défaut si nenhum)
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
      const text = window.prompt("Note (max 60 caractères) :", "");
      if (text === null) return;
      const trimmed = (text || "").slice(0, 60);
      setAnnotations({
        ...annotations,
        notes: [...annotations.notes, {
          id: `nt_${Date.now()}`, x: pt[0], y: pt[1], text: trimmed || "Note"
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
        toast.success(`Ângulo : ${deg.toFixed(1)}° · pente ${(Math.tan(deg * Math.PI / 180) * 12).toFixed(1)}/12`);
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
    if (!(dist > 0)) return toast.error("Distância inválida");
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
    } catch (e) { toast.error(e?.response?.data?.detail || "Calibração falhou"); }
  };

  const submitOpening = async () => {
    if (!openingsDialog) return;
    const w = parseFloat(pendingOpening.width_m);
    const h = parseFloat(pendingOpening.height_m);
    if (!(w > 0) || !(h > 0)) return toast.error("Dimensões inválidas");
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
        `${pendingOpening.kind === "porte" ? "Porta" : pendingOpening.kind === "baie" ? "Vão de sacada" : "Janela"} `
        + `${w}×${h} m ajoutée à ${openingsDialog.room_name}`
      );
      setOpeningsDialog(null);
      setPoints([]);
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível adicionar"); }
  };

  const deleteOpening = async (room_id, opening_id) => {
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/rooms/${room_id}/openings/${opening_id}`);
      toast.success("Vão eliminado");
      await refreshPlan();
    } catch { toast.error("Não foi possível eliminar"); }
  };

  const finishPolyline = async (pts = points) => {
    if (pts.length < 2) return;
    if (!currentCalib) return toast.error("Calibre primeiro o plano");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polyline", points: pts,
      });
      toast.success(`Comprimento : ${data.length_m} m`);
      setPoints([]);
      await refreshPlan();
    } catch (e) { toast.error("Medição falhou"); }
  };

  const finishPitchSurface = () => {
    if (points.length < 3) return toast.error("Clique em pelo menos 3 pontos");
    if (!currentCalib) return toast.error("Calibre primeiro o plano");
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

  // ============ VAGUE B — Handlers pour le Painel Objetos ============

  const renameRoom = async (roomId, newName) => {
    if (!plan?.plan_id || !newName?.trim()) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/rooms/${roomId}`, { name: newName.trim() });
      await refreshPlan();
      toast.success("Divisão renomeada");
    } catch { toast.error("Não foi possível renomear"); }
  };

  const attachPresetToRoom = async (roomId, presetId) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/rooms/${roomId}`, { preset_id: presetId });
      await refreshPlan();
      toast.success(presetId ? "Modelo atribuído à divisão" : "Modelo removido");
    } catch (e) { toast.error(e?.response?.data?.detail || "Atribuição impossível"); }
  };

  const deleteRoomFromPanel = async (roomId) => {
    if (!plan?.plan_id) return;
    if (!window.confirm("Eliminar cette compartimento ?")) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/rooms/${roomId}`);
      await refreshPlan();
      toast.success("Compartimento supprimée");
    } catch { toast.error("Não foi possível eliminar"); }
  };

  const deleteMeasureFromPanel = async (measureId) => {
    if (!plan?.plan_id) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/measurements/${measureId}`);
      await refreshPlan();
      toast.success("Mesure supprimée");
    } catch { toast.error("Não foi possível eliminar"); }
  };

  const clearMeasures = async () => {
    if (!plan?.plan_id) return;
    try {
      await api.delete(`/takeoffs/${plan.plan_id}/measurements?page_index=${pageIndex}`);
      await refreshPlan();
      toast.success("Medições da página apagadas");
    } catch { toast.error("Effacement impossível"); }
  };

  // Iter66 — libellé personnalisé (ex. « paredes parpaing », « paredes en brique »)
  const renameMeasure = async (measureId, label) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/measurements/${measureId}`, { label });
      await refreshPlan();
      toast.success(label ? `Mesure renommée : ${label}` : "Libellé effacé");
    } catch { toast.error("Não foi possível renomear"); }
  };

  // Iter68 — surface mesurée → compartimento complète (1 clic)
  const convertMeasureToRoom = async (measureId) => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measurements/${measureId}/to-room`);
      toast.success(`Compartimento créée : ${data.room.name} (${data.room.surface_m2} m²) — paredes et volume calculés`, { duration: 6000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Conversion impossível"); }
  };

  // Iter68 — déduction (trémie, escalier…) de la compartimento contenante
  const deductMeasure = async (measureId) => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measurements/${measureId}/deduct`);
      toast.success(`− ${data.deduction.area_m2} m² déduits de « ${data.room_name} » → surface nette ${data.surface_m2} m²`, { duration: 7000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Déduction impossível"); }
  };

  const removeDeduction = async (roomId, dedId) => {
    try {
      const { data } = await api.delete(`/takeoffs/${plan.plan_id}/rooms/${roomId}/deductions/${dedId}`);
      toast.success(`Déduction removida — surface : ${data.surface_m2} m²`);
      await refreshPlan();
    } catch { toast.error("Não foi possível eliminar"); }
  };

  // Iter68 — export Excel (compartimentos + mesures)
  const downloadXlsx = async () => {
    if (!plan?.plan_id) return;
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const res = await fetch(`${base}/api/takeoffs/${plan.plan_id}/export-xlsx`,
        { headers: { Authorization: `Bearer ${token}` }, credentials: "include" });
      if (!res.ok) throw new Error("Exportação impossível");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-${plan.plan_id}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Exportação Excel descarregada");
    } catch (e) { toast.error(e.message || "Export Excel impossível"); }
  };

  // Iter69 — Estudo Permis de Construire (gros œuvre : béton, aços, isobrique)
  const [pcDialog, setPcDialog] = useState(false);
  const [structDialog, setStructDialog] = useState(false);
  const [pcBusy, setPcBusy] = useState(false);
  const runPcStudy = async () => {
    setPcBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/pc-study`, {});
      await refreshPlan();
      toast.success(
        `Estudo PC terminée — ${data.totals?.beton_m3 ?? 0} m³ béton · ${data.totals?.acier_kg ?? 0} kg aços · ${data.totals?.ttc ?? 0} € TTC`,
        { duration: 8000 });
    } catch (e) { toast.error(e?.response?.data?.detail || "Estudo PC impossível"); }
    finally { setPcBusy(false); }
  };
  const downloadPcFile = async (fmt, start) => {
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const qs = start ? `?start=${start}` : "";
      const res = await fetch(`${base}/api/takeoffs/${plan.plan_id}/pc-study/${fmt}${qs}`,
        { headers: { Authorization: `Bearer ${token}` }, credentials: "include" });
      if (!res.ok) throw new Error("Exportação impossível");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `etude-pc-${plan.plan_id}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Estudo PC ${fmt.toUpperCase()} descarregada`);
    } catch (e) { toast.error(e.message || "Exportação impossível"); }
  };
  const comparePcSuppliers = (study) => {
    const t = study?.totals || {};
    const slabArea = Math.round((study?.inputs?.ground_floor_area_m2 || 0) +
                                (study?.inputs?.upper_floors_area_m2 || 0));
    const items = [
      { name: "Brique isobrique 20 cm", search: "brique isobrique 20 cm", quantity: t.briques_u || 0, unit: "u" },
      { name: "Acier HA fer à béton", search: "fer à béton HA10 barre 6m", quantity: Math.round(t.acier_kg || 0), unit: "kg" },
      { name: "Treillis soudé ST25C", search: "treillis soudé ST25C panneau", quantity: slabArea, unit: "m²" },
      { name: "Betão pronto a aplicar C25/30", search: "béton pronto à l'emploi C25/30", quantity: t.beton_m3 || 0, unit: "m³" },
    ].filter((it) => it.quantity > 0);
    if (!items.length) return toast.error("Nenhuma quantidade a comparar — lance primeiro o estudo");
    sessionStorage.setItem("construpilot_price_search_batch", JSON.stringify({
      ts: Date.now(), project_name: `Estudo PC — ${plan?.filename || "plan"}`,
      total_avg: t.ht || 0, items,
    }));
    nav("/prix");
  };
  const recomputePcStudy = async () => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/pc-study/recompute`);
      await refreshPlan();
      toast.success(`Orçamento recalculé avec vos definições — ${data.totals?.ttc ?? 0} € TTC`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Recálculo impossível"); }
  };

  // Iter67 — modelos de message réutilisables (envoi de rapports)
  useEffect(() => {
    if (!sendEcartsDialog) return;
    api.get("/emails/templates")
      .then(({ data }) => setMsgTemplates(data.templates || []))
      .catch(() => {});
  }, [sendEcartsDialog]);

  const saveMsgTemplate = async () => {
    const body = ecartsMessage.trim();
    if (!body) return toast.error("Escreva primeiro uma mensagem a gravar");
    const name = body.split("\n")[0].slice(0, 40) || "Modelo";
    try {
      const { data } = await api.post("/emails/templates", { name, body });
      setMsgTemplates((prev) => [data.template, ...prev]);
      toast.success(`Modelo enregistré : ${data.template.name}`);
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

  // Iter66 — renvoi 1 clic desde l'historique des envois
  const resendReport = async (report) => {
    setSendingEcarts(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/ecarts-pdf/send`, {
        page_index: report.page_index ?? pageIndex,
        to_email: report.to_email,
        message: "",
      });
      toast.success(`Relatório renvoyé à ${data.sent_to}`);
      await refreshPlan();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Renvoi impossível");
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
      toast.info("Posição não disponível para este objeto");
    }
  };

  // Vague C — Geração devis compartimento (calculators.py)
  const generateRoomEstimate = async (roomId) => {
    if (!plan?.plan_id) return;
    setEstimateLoading(true);
    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/rooms/${roomId}/estimate`,
        {}
      );
      setRoomEstimate(data);
      toast.success(`Orçamento compartimento généré : ${data.total_budget?.toFixed(2)} €`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Geração impossível");
    } finally {
      setEstimateLoading(false);
    }
  };

  // Preset application — recolle un preset comme label + prix par unité sur le contexte courant
  const applyPresetToTool = (preset) => {
    setCurrentPreset(preset);
    // Si outil compteur : crée un novo compteur avec les params du preset
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
    if (!currentCalib) return toast.error("Calibre primeiro o plano");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "distance", points: pts.slice(0, 2),
      });
      toast.success(`Distance : ${data.value_m} m`);
      setPoints([]);
      await refreshPlan();
    } catch { toast.error("Medição falhou"); }
  };

  const finishRoom = (pts = points) => {
    if (pts.length < 3) return toast.error("Um compartimento necessita de pelo menos 3 pontos");
    if (!currentCalib) return toast.error("Calibre primeiro o plano");
    setPendingRoomName(`Compartimento ${String(rooms.length + 1).padStart(2, "0")}`);
    setRoomDialog(true);
  };

  // Iter67 — mesure de surface libre (polygone) en m²
  const finishSurface = async (pts = points) => {
    if (pts.length < 3) return toast.error("Uma superfície necessita de pelo menos 3 pontos");
    if (!currentCalib) return toast.error("Calibre primeiro o plano");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polygon", points: pts,
      });
      toast.success(`Superfície : ${data.area_m2} m² · périmètre ${data.perimeter_m} m`, { duration: 6000 });
      setPoints([]);
      await refreshPlan();
    } catch { toast.error("Mesure de surface échouée"); }
  };

  // Double-clic gauche : termine la cote/mesure en cours — le clic suivant
  // reprend une nouvelle mesure. Nettoie le point dupliqué par les 2 clics.
  const onCanvasDoubleClick = () => {
    let chain = [...points];
    while (chain.length >= 2) {
      const a = chain[chain.length - 1], b = chain[chain.length - 2];
      if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 3) chain = chain.slice(0, -1);
      else break;
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

  const saveRoom = async () => {
    try {
      await api.post(`/takeoffs/${plan.plan_id}/rooms`, {
        page_index: pageIndex, name: pendingRoomName,
        points,
        ceiling_height_m: parseFloat(ceilingH) || planDefaults.ceiling_h_m || 2.5,
        floor_thickness_m: planDefaults.floor_thickness_m || 0.15,
        openings: [],
      });
      toast.success("Compartimento enregistrée");
      setRoomDialog(false);
      setPoints([]);
      await refreshPlan();
      setTool(TOOLS.SELECT);
    } catch (e) { toast.error("Não foi possível guardar"); }
  };

  const deleteRoom = async (rid) => {
    await api.delete(`/takeoffs/${plan.plan_id}/rooms/${rid}`);
    await refreshPlan();
    toast.success("Compartimento supprimée");
  };

  // Efface TOUTES les mesures/annotations de la page avant de passer au devis
  const clearAllMeasures = async () => {
    if (!plan?.plan_id) return;
    const roomCount = rooms.length;
    if (!window.confirm(
      `Apagar tudo nesta página?\n\n${roomCount} compartimento(s), as anotações (contadores, notas, ângulos, coberturas) e as paredes detetadas serão removidas. Esta ação é irreversível.`
    )) return;
    try {
      // Supprime toutes les compartimentos de la page côté serveur
      await Promise.all(rooms.map((r) => api.delete(`/takeoffs/${plan.plan_id}/rooms/${r.room_id}`)));
      // Vide les annotations (persistées via l'auto-save)
      setAnnotations({ counters: [], notes: [], angles: [], pitched_surfaces: [] });
      setDetectedWalls(null);
      setWallsSummary(null);
      setPoints([]);
      setTool(TOOLS.SELECT);
      await refreshPlan();
      toast.success("Todas as medições foram apagadas — pronto para um novo orçamento");
    } catch (e) {
      toast.error("Impossível de tout apagar");
    }
  };

  const importAiRooms = async (aiRoomsOverride = null) => {
    const aiRooms = Array.isArray(aiRoomsOverride) ? aiRoomsOverride : (plan?.ai_analysis?.rooms || []);
    if (!aiRooms.length) return toast.error("Nenhum compartimento IA para importar");

    // Try CV auto-detection first : real contours matched by surface
    let cvRooms = [];
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/detect-all-rooms?page_index=${pageIndex}`);
      cvRooms = (data?.rooms || []).filter((r) => r.surface_m2);
    } catch (e) { /* fall back to square approximation */ }

    // Match AI rooms to CV contours by closest surface_m2 (greedy)
    const usedCvIdx = new Set();
    const matches = aiRooms.map((ai) => {
      const targetSurf = Number(ai.surface_written_m2) || 0;
      if (!targetSurf || !cvRooms.length) return { ai, cv: null };
      let best = -1, bestDelta = Infinity;
      cvRooms.forEach((cv, i) => {
        if (usedCvIdx.has(i)) return;
        const delta = Math.abs(cv.surface_m2 - targetSurf);
        // Only match if the CV contour is within ±30% of the AI-written surface
        if (delta < bestDelta && delta <= targetSurf * 0.3) {
          best = i; bestDelta = delta;
        }
      });
      if (best >= 0) { usedCvIdx.add(best); return { ai, cv: cvRooms[best] }; }
      return { ai, cv: null };
    });

    // Fallback grid layout for AI rooms without a CV match
    const ppm = currentCalib?.pixels_per_meter || 60;
    const unmatched = matches.filter((m) => !m.cv);
    const cols = Math.max(1, Math.ceil(Math.sqrt(unmatched.length)));

    let imported = 0, matchedCount = 0, fallbackCount = 0;
    for (let i = 0; i < matches.length; i++) {
      const { ai, cv } = matches[i];
      let points;
      if (cv?.points?.length >= 3) {
        points = cv.points;
        matchedCount++;
      } else {
        const surf = Number(ai.surface_written_m2) || 0;
        if (!surf) continue;
        const sidePx = Math.sqrt(surf) * ppm;
        const gap = sidePx * 0.15;
        const col = fallbackCount % cols;
        const row = Math.floor(fallbackCount / cols);
        const x0 = 200 + col * (sidePx + gap);
        const y0 = 200 + row * (sidePx + gap);
        points = [
          [x0, y0], [x0 + sidePx, y0],
          [x0 + sidePx, y0 + sidePx], [x0, y0 + sidePx],
        ];
        fallbackCount++;
      }
      try {
        await api.post(`/takeoffs/${plan.plan_id}/rooms`, {
          page_index: pageIndex,
          name: ai.name || `Compartimento ${imported + 1}`,
          points,
          ceiling_height_m: ai.ceiling_height_m || planDefaults.ceiling_h_m || 2.5,
          floor_thickness_m: planDefaults.floor_thickness_m || 0.15,
        });
        imported++;
      } catch (e) { /* keep going */ }
    }
    await refreshPlan();
    setRightTab("rooms");
    if (imported > 0) {
      const detail = matchedCount > 0
        ? `${matchedCount} contour${matchedCount > 1 ? "s" : ""} detetado${matchedCount > 1 ? "s" : ""} par CV`
        : "carrés approximatifs — ajustez si besoin";
      toast.success(`${imported} compartimentos IA importées · ${detail}`, { duration: 6000 });
    }
    else toast.error("Nenhum compartimento importável (superfícies IA em falta)");
    return imported;
  };

  const runAI = async () => {
    setAiBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/analyze?page_index=${pageIndex}`);
      await refreshPlan();
      // Switch to IA tab so the user sees the result immediately
      setRightTab("ai");
      if (data.error) toast.warning("IA : " + data.error);
      else {
        const n = data.rooms?.length || 0;
        const surf = data.total_surface_written_m2;
        toast.success(
          `Análise IA — ${n} compartimento${n > 1 ? "s" : ""} detetada${n > 1 ? "s" : ""}` +
          (surf ? ` · ${surf} m²` : ""),
          { duration: 6000 }
        );
      }
    } catch (e) { toast.error("Análise IA impossível"); }
    finally { setAiBusy(false); }
  };

  // --- Iter62 : calibration par cotes / recalage superfícies écrites / textes IA ---
  const calibrateFromCotes = async () => {
    setAiActionBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/calibrate/from-cotes`,
        { page_index: pageIndex });
      toast.success(
        `Échelle calibrée par les cotes : ${data.calibration.pixels_per_meter.toFixed(1)} px/m ` +
        `(${data.calibration.samples_used} cote${data.calibration.samples_used > 1 ? "s" : ""}, ±${data.calibration.spread_pct}%)` +
        (data.rooms_recomputed ? ` · ${data.rooms_recomputed} compartimento(s) recalculée(s)` : ""),
        { duration: 8000 });
      await refreshPlan();
    } catch (e) { toast.error(e?.response?.data?.detail || "Calibration par cotes impossível"); }
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
          `${data.rooms_recomputed} compartimento(s) recalculée(s)`, { duration: 7000 });
        setReconcile(null);
        await refreshPlan();
      } else if (!data.can_reconcile) {
        toast.warning(data.reason || "Sem correspondência com uma superfície escrita");
      }
    } catch (e) { toast.error(e?.response?.data?.detail || "Vérification impossível"); }
    finally { setAiActionBusy(false); }
  };

  const applyAiTexts = async () => {
    setAiActionBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/apply-ai-texts`,
        { page_index: pageIndex });
      const parts = [];
      if (data.renamed?.length) parts.push(`${data.renamed.length} compartimento(s) renommée(s)`);
      if (data.materials_set?.length) parts.push(`${data.materials_set.length} matériau(x) sol`);
      if (data.heights_updated?.length) parts.push(`${data.heights_updated.length} altura(s)`);
      if (data.calibration_set) parts.push("échelle écrite appliquée");
      if (data.surface_flags?.length) parts.push(`⚠ ${data.surface_flags.length} écart(s) de surface >5%`);
      toast.success(parts.length
        ? `Textes du plan appliqués — ${parts.join(" · ")}`
        : "Textos analisados — nada a alterar", { duration: 9000 });
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
        `${data.segment_count} segments de paredes detetados` +
        (data.filtered_cotes ? ` · ${data.filtered_cotes} traits de cote/textes ignorés` : "") +
        (data.filtered_diagonals ? ` · ${data.filtered_diagonals} diagonales ignorées` : "")
      );
      if (data.structural_hint && !ortho) {
        toast.warning(
          "Este plano assemelha-se a um plano de estrutura/betão (aços, cotas, tramas). A deteção de paredes é pouco fiável — use antes a Medição de betão.",
          { duration: 14000,
            action: { label: "Ignorar as diagonais", onClick: () => detectWalls(true) } }
        );
      }
      await loadWallsSummary();
    } catch (e) { toast.error("Deteção de paredes impossível"); }
    finally { setCvBusy(false); }
  };

  // ===== STRUCTURE IA (paredes rouges + ouvertures jaunes/violettes) =====
  const acierQuery = () =>
    `&acier_semelles=${acierRatios.semelles}&acier_poteaux=${acierRatios.poteaux}&acier_poutres=${acierRatios.poutres}&acier_dalles=${acierRatios.dalles}&acier_voiles=${acierRatios.voiles}&poutre_l=${poutreL}&poutre_h=${poutreH}&proprete_ep=${propreteEp}`;

  const betonPriceQuery = () =>
    `&beton_price_semelles=${betonPrices.semelles}&beton_price_proprete=${betonPrices.proprete}&beton_price_poteaux=${betonPrices.poteaux}&beton_price_poutres=${betonPrices.poutres}&beton_price_dalles=${betonPrices.dalles}&beton_price_voiles=${betonPrices.voiles}&plancher_type=${plancherType}&plancher_price_m2=${plancherPriceM2}`;

  const araseQuery = () =>
    (araseInf !== "" && araseSup !== "" && Number(araseSup) > Number(araseInf))
      ? `&arase_inf=${araseInf}&arase_sup=${araseSup}` : "";

  // Charge les definições béton par défaut + presets, puis applique le dernier preset choisi
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
        if (data.margin_pct) setMarginPct(data.margin_pct);
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
    setMarginPct(pr.margin_pct || 15);
    if (pr.acier_ratios) setAcierRatios((r) => ({ ...r, ...pr.acier_ratios }));
    if (notify) toast.success(`Definições « ${pr.name} » appliqués`);
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
    if (!window.confirm(`Eliminar le definição « ${selectedPreset} » ?`)) return;
    try {
      await api.delete(`/takeoffs/settings/beton-presets/${encodeURIComponent(selectedPreset)}`);
      setBetonPresets((list) => list.filter((p) => p.name !== selectedPreset));
      setSelectedPreset("");
      toast.success("Definição supprimé");
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
        return { name: pr.name, d: data.descritivo,
                 beton_price_m3: pr.beton_price_m3 || 0, acier_price_kg: pr.acier_price_kg || 0,
                 labor_price_m3: pr.labor_price_m3 || 0, margin_pct: pr.margin_pct || 0 };
      }));
      setCompareData(results);
    } catch { toast.error("Comparaison impossível"); setCompareOpen(false); }
    finally { setCompareBusy(false); }
  };

  const saveBetonPreset = async () => {
    const name = window.prompt("Nome do conjunto de definições (ex.: Reabilitação, Moradia):");
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
      toast.success(`Definição « ${name.trim()} » enregistré`);
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
      toast.success("Definições béton enregistrés comme valeurs par défaut de l'entreprise");
    } catch { toast.error("Gravação das definições impossível"); }
  };

  const loadDescriptif = async (height = wallHeight) => {
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/analysis/${pageIndex}?wall_height=${height}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}`);
      setDescriptif(data.descritivo);
      return data.descritivo;
    } catch { return null; }
  };

  // Bouton principal : « Analisar le plan » — enchaîne TOUT automatiquement :
  // 1) structure (paredes/poteaux/poutres/dalles) 2) compartimentos IA + import au medição
  // 3) chiffrage/descritivo béton 4) estimation globale.
  // P3 — Assistant IA : proposer une action (aperçu, sans appliquer)
  const aiProposeCommand = async () => {
    const cmd = aiCmd.trim();
    if (!cmd || !plan?.plan_id) return;
    setAiCmdBusy(true);
    setAiCmdProposal(null);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/ai-command`, {
        command: cmd, page_index: pageIndex,
      });
      if (!data || data.action === "none") {
        toast.error(data?.summary || "Je n'ai pas compris cette encomenda.");
      } else {
        setAiCmdProposal(data);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Assistente indisponível");
    } finally { setAiCmdBusy(false); }
  };

  // P3 — Assistant IA : appliquer l'action validée + auto-save
  const aiApplyCommand = async () => {
    if (!aiCmdProposal || !plan?.plan_id) return;
    setAiCmdBusy(true);
    try {
      await api.post(`/takeoffs/${plan.plan_id}/ai-command/apply`, {
        action: aiCmdProposal.action,
        params: aiCmdProposal.params || {},
        page_index: pageIndex,
      });
      await refreshPlan();
      setSavedAt(Date.now());
      toast.success("Action appliquée et enregistrée");
      setAiCmdProposal(null);
      setAiCmd("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Application impossível");
    } finally { setAiCmdBusy(false); }
  };

  const analyzePlanFull = async () => {    if (!plan?.plan_id) return;
    if (!currentCalib) {
      toast.error("Calibre primeiro o plano: a escala é indispensável para calcular as quantidades.");
      setTool(TOOLS.CALIB);
      return;
    }
    setAnalysisBusy(true);
    const tid = toast.loading("Análise complète en cours… structure, compartimentos, medição et estimation.");
    try {
      // 1) Structure béton (paredes, poteaux, poutres, dalles)
      let struct = null;
      try {
        const _pk = planKindChoice !== "auto" ? `&plan_kind=${planKindChoice}` : "";
        const { data } = await api.post(`/takeoffs/${plan.plan_id}/detect-structure?page_index=${pageIndex}${_pk}`);
        if (!data.error) {
          struct = data;
          setStructure(data);
          setShowStructure(true);
          setSelectedStruct(null);
        }
      } catch (e) { /* on continue même si la structure échoue */ }

      // 2) Compartimentos (rooms) par IA vision
      let aiRooms = [];
      try {
        const { data } = await api.post(`/takeoffs/${plan.plan_id}/analyze?page_index=${pageIndex}`);
        aiRooms = data?.rooms || [];
      } catch (e) { /* pas de compartimentos detetadas */ }

      // 3) Rafraîchit puis importe les compartimentos au medição (superfícies + périmètres)
      await refreshPlan();
      let importedRooms = 0;
      if (aiRooms.length) {
        try { importedRooms = (await importAiRooms(aiRooms)) || aiRooms.length; }
        catch (e) { /* import best-effort */ }
      }

      // 4) Chiffrage / descritivo béton (medição chiffré)
      const descData = await loadDescriptif();

      // 5) Estimativa globale desde le medição (uniquement si des compartimentos existent)
      let estData = null;
      if (importedRooms > 0) {
        try { estData = await runEstimation(); } catch (e) { /* estimation optionnelle */ }
      }

      // Récapitulatif instantané (sans dialogue)
      const surfacePieces = aiRooms.reduce((s, r) => s + (Number(r.surface_written_m2) || Number(r.estimated_surface_m2) || 0), 0);
      const beton = descData?.beton_total_m3 || 0;
      const acier = descData?.acier_total_kg || 0;
      const venteBeton = beton > 0
        ? Math.round(((beton * betonPriceM3 + acier * acierPriceKg) + beton * laborPriceM3) * (1 + marginPct / 100))
        : 0;
      setAnalysisRecap({
        rooms: aiRooms.length,
        imported_rooms: importedRooms,
        surface_pieces_m2: Math.round(surfacePieces * 10) / 10,
        walls: struct?.wall_count || 0,
        columns: struct?.column_count || 0,
        beams: struct?.beam_count || 0,
        floors: struct?.floor_count || 0,
        beton_m3: beton,
        acier_kg: acier,
        estimation_beton_eur: venteBeton,
        estimation_globale_eur: estData?.estimation?.total_avg || 0,
        estimation_surface_m2: estData?.surface_m2 || 0,
      });

      toast.dismiss(tid);
      const parts = [];
      if (struct) parts.push(`${struct.wall_count || 0} paredes · ${struct.column_count || 0} poteaux · ${struct.beam_count || 0} poutres · ${struct.floor_count || 0} dalles`);
      if (aiRooms.length) parts.push(`${aiRooms.length} compartimento(s)`);
      toast.success(`Plan analysé automatiquement — ${parts.join(" · ") || "terminé"}. Medição, compartimentos et estimation prêts.`, { duration: 8000 });
    } catch (e) {
      toast.dismiss(tid);
      toast.error(e?.response?.data?.detail || "Análise impossível");
    } finally { setAnalysisBusy(false); }
  };

  const analyzeAllPages = async () => {
    if (!plan?.plan_id) return;
    setAnalysisBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/detect-structure-all`);
      await refreshPlan();
      toast.success(`${data.page_count} page(s) analysée(s)`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Análise multi-pages impossível");
    } finally { setAnalysisBusy(false); }
  };

  const _hasStructure = () => !!(structure && ((structure.walls || []).length || (structure.openings || []).length || (structure.beams || []).length || (structure.floors || []).length || (structure.columns || []).length));

  const sendToQuote = async () => {
    if (!currentCalib) { toast.error("Calibre primeiro o plano"); return; }
    if (!_hasStructure()) { toast.error("Analise primeiro o plano"); return; }
    try {
      const body = plan3dSnapshot ? { snapshot_png: plan3dSnapshot } : {};
      const mq = (marginBeton !== "" ? `&margin_beton=${marginBeton}` : "")
        + (marginAcier !== "" ? `&margin_acier=${marginAcier}` : "")
        + (marginLabor !== "" ? `&margin_labor=${marginLabor}` : "");
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/quote?beton_only=true&wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&acier_price_kg=${acierPriceKg}&beton_price_m3=${betonPriceM3}${betonPriceQuery()}&labor_price_m3=${laborPriceM3}&margin_pct=${marginPct}&price_level=${priceLevel}${araseQuery()}${mq}`, body);
      const n = data.priced_lines || 0;
      toast.success((n > 0 ? `Orçamento créé — ${n} ligne(s) chiffrée(s) desde votre bibliothèque` : "Orçamento criado a partir do descritivo") + (plan3dSnapshot ? " · vue 3D jointe" : ""));
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Geração do orçamento impossível");
    }
  };

  const estimateAndDownloadQuote = async () => {
    if (!currentCalib) { toast.error("Calibre primeiro o plano"); return; }
    if (!_hasStructure()) { toast.error("Analise primeiro o plano"); return; }
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
      URL.revokeObjectURL(url);
      const ttc = data.totals?.ttc || 0;
      toast.success(`Orçamento estimé descarregado — ${ttc.toLocaleString("pt-PT")} € TTC · ${data.priced_lines || 0} poste(s) chiffré(s)`, { duration: 6000 });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Estimativa impossível");
    } finally { setQuoteBusy(false); }
  };

  const exportAnnotatedPdf = async () => {
    if (!_hasStructure()) { toast.error("Analise primeiro o plano"); return; }
    try {
      const res = await api.post(`/takeoffs/${plan.plan_id}/structure/${pageIndex}/pdf?wall_height=${wallHeight}`,
        {}, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `plan-annote-${plan.plan_id}.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success("PDF do plano anotado descarregado");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Export PDF impossível");
    }
  };

  const detectStructure = analyzePlanFull;

  // Análise automatique à l'ouverture desde "Adicionar um plano" (?auto=1)
  useEffect(() => {
    if (!pendingAuto || !plan?.plan_id) return;
    setPendingAuto(false);
    toast.info("Análise automática do plano em curso…");
    analyzePlanFull();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingAuto, plan?.plan_id]);

  const exportBetonXlsx = async () => {
    if (!_hasStructure()) { toast.error("Analise primeiro o plano"); return; }
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const q = `wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&beton_price_m3=${betonPriceM3}&acier_price_kg=${acierPriceKg}${betonPriceQuery()}`;
      const res = await fetch(`${base}/api/takeoffs/${plan.plan_id}/structure/${pageIndex}/beton-xlsx?${q}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error("Exportação impossível");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-beton-${plan.plan_id}.xlsx`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Medição betão (Excel) descarregada");
    } catch (e) { toast.error(e.message || "Export Excel béton impossível"); }
  };

  const exportBetonPdf = async () => {
    if (!_hasStructure()) { toast.error("Analise primeiro o plano"); return; }
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const q = `wall_height=${wallHeight}&dalle_ep=${dalleEp}&voile_ep=${voileEp}${acierQuery()}&beton_price_m3=${betonPriceM3}&acier_price_kg=${acierPriceKg}&labor_price_m3=${laborPriceM3}&margin_pct=${marginPct}`;
      const res = await fetch(`${base}/api/takeoffs/${plan.plan_id}/structure/${pageIndex}/beton-pdf?${q}`,
        { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error("Exportação impossível");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-beton-${plan.plan_id}.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Medição betão (PDF) descarregada");
    } catch (e) { toast.error(e.message || "Export PDF béton impossível"); }
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
      setAiMessages((prev) => [...prev, { role: "assistant", text: data.reply || "Análise mise à jour.", ok: data.ok }]);
      if (data.ok) toast.success("Plan mis à jour par l'IA");
    } catch (e) {
      const err = e?.response?.data?.detail || "L'IA n'a pas pu répondre";
      setAiMessages((prev) => [...prev, { role: "assistant", text: err, ok: false }]);
      toast.error(err);
    } finally { setAiChatBusy(false); }
  };

  const persistStructure = async (next) => {
    setStructure(next);
    try {
      await api.put(`/takeoffs/${plan.plan_id}/structure/${pageIndex}`, {
        walls: next.walls || [], openings: next.openings || [], beams: next.beams || [],
        floors: next.floors || [], columns: next.columns || [], footings: next.footings || [],
        image_width: next.image_width, image_height: next.image_height,
      });
    } catch { toast.error("Gravação da estrutura impossível"); }
  };

  const commitStructure = () => setStructure((prev) => {
    if (prev && plan?.plan_id) {
      api.put(`/takeoffs/${plan.plan_id}/structure/${pageIndex}`, {
        walls: prev.walls || [], openings: prev.openings || [], beams: prev.beams || [],
        floors: prev.floors || [], columns: prev.columns || [], footings: prev.footings || [],
        image_width: prev.image_width, image_height: prev.image_height,
      }).catch(() => {});
    }
    return prev;
  });

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
    toast.info("Parede adicionada — arraste as extremidades para a posicionar");
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
    toast.info("Viga adicionada — arraste as extremidades para a posicionar");
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
    toast.info("Pilar adicionado — arraste os cantos para ajustar");
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
    toast.info(`${kind === "porte" ? "Porta" : "Janela"} adicionada — arrasta as extremidades para a colocar`);
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
    if (!currentCalib) return toast.error("Calibre primeiro o plano");
    setCvBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/room-autofill`, {
        page_index: pageIndex,
        seed_x: Math.round(pt[0]),
        seed_y: Math.round(pt[1]),
        tolerance: 25,
      });
      // Charge les points detetados dans l'état — l'utilizador peut ajuster puis valider
      setPoints(data.points);
      toast.success(`Contour detetado (${data.point_count} points, ${data.surface_m2} m²)`);
      // Ouvre le dialog de nom immédiatement
      setPendingRoomName(`Compartimento ${String(rooms.length + 1).padStart(2, "0")}`);
      setRoomDialog(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Nenhum compartimento detetado neste ponto");
    } finally { setCvBusy(false); }
  };

  const loadTakeoff = async () => {
    const { data } = await api.get(`/takeoffs/${plan.plan_id}/takeoff`);
    setTakeoff(data);
    const { data: m } = await api.post(`/takeoffs/${plan.plan_id}/materials`,
                                        { floor_material: floorMaterial });
    setMaterials(m);
  };

  const sendToEstimator = () => {
    if (!takeoff?.totals?.floor_m2) return toast.error("Adicione pelo menos um compartimento");
    // Prefill query params for /estimation with surface
    nav(`/estimation?surface=${Math.round(takeoff.totals.floor_m2)}&from=plan`);
  };

  const sendToPrices = () => {
    if (!materials) return;
    const q = [];
    if (materials.floor) q.push(`${materials.floor.material} ${materials.floor.quantity_m2}m²`);
    if (materials.placo) q.push(`placas de Pladur`);
    if (materials.paint) q.push(`peinture`);
    nav(`/prix?q=${encodeURIComponent(q.join(" "))}`);
  };

  const downloadPdf = async () => {
    if (!plan?.plan_id) return;
    // Guard : PDF vide si aucune compartimento tracée
    if (!rooms.length) {
      toast.error("Adicione primeiro um compartimento (ferramenta Compartimento ou Auto-compartimento) para gerar uma medição.", { duration: 5000 });
      setRightTab("rooms");
      return;
    }
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const res = await fetch(
        `${base}/api/takeoffs/${plan.plan_id}/pdf?include_materials=true&floor_material=${floorMaterial}`,
        { headers: { Authorization: `Bearer ${token}` }, credentials: "include" }
      );
      if (!res.ok) throw new Error("PDF error");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Medição PDF descarregada");
    } catch { toast.error("Export PDF impossível"); }
  };

  // Iter63 — Relatório PDF des écarts superfícies mesurées ↔ écrites
  const downloadEcartsPdf = async () => {
    if (!plan?.plan_id) return;
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const res = await fetch(
        `${base}/api/takeoffs/${plan.plan_id}/ecarts-pdf?page_index=${pageIndex}`,
        { headers: { Authorization: `Bearer ${token}` }, credentials: "include" }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "PDF error");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `relatório-ecarts-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Relatório d'écarts PDF descarregado");
    } catch (e) { toast.error(e.message || "Export relatório écarts impossível"); }
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

  // Iter64 — envoi du relatório d'écarts par email au client
  const sendEcartsReport = async () => {
    if (!ecartsEmail.trim()) return toast.error("Indique o email do cliente");
    setSendingEcarts(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/ecarts-pdf/send`, {
        page_index: pageIndex,
        to_email: ecartsEmail.trim(),
        message: ecartsMessage,
      });
      toast.success(`Relatório d'écarts envoyé à ${data.sent_to}`, { duration: 7000 });
      setSendEcartsDialog(false);
      setEcartsMessage("");
      await refreshPlan();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Envoi impossível — verifique l'email");
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
      await api.post(`/takeoffs/${plan.plan_id}/history/restore/${snapshotId}`);
      await refreshPlan();
      await loadHistory();
      toast.success("Snapshot restauré");
    } catch { toast.error("Restauration impossível"); }
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
    } catch { toast.error("Não foi possível guardar"); }
  };

  const downloadQuotePdf = async () => {
    if (!plan?.plan_id) return;
    setQuoteBusy(true);
    try {
      const backend = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const qs = new URLSearchParams({
        finish: quoteFinish, floor_material: quoteFloor,
      }).toString();
      const res = await fetch(`${backend}/api/takeoffs/${plan.plan_id}/quote-pdf?${qs}`,
        { headers: { Authorization: `Bearer ${token}` }, credentials: "include" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "PDF error");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `devis-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Orçamento PDF descarregado");
      setQuoteDialog(false);
    } catch (e) { toast.error(e.message || "Export Orçamento impossível"); }
    finally { setQuoteBusy(false); }
  };

  const sendQuotePdf = async () => {
    if (!plan?.plan_id) return;
    if (!/@/.test(quoteClientEmail)) return toast.error("Email client invalide");
    if (quoteIncludeTva && !quoteClientAddress.trim())
      return toast.error("Morada do cliente obrigatória para o certificado de IVA");
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
        if (quoteIncludeTva) extras.push("certificado TVA");
        if (quoteAttachVideo && latestVideo) extras.push("tour vidéo 3D");
        const extra = extras.length ? " + " + extras.join(" + ") + " joint(s)" : "";
        toast.success(`Orçamento envoyé à ${quoteClientEmail}${extra} (${data.total_ttc?.toLocaleString("pt-PT")} € TTC)`);
        setQuoteDialog(false);
        setQuoteClientEmail(""); setQuoteClientName(""); setQuoteMessage("");
        setQuoteSubject(""); setQuoteIntro(""); setQuoteClientAddress("");
        await loadQuoteSends();
      } else {
        toast.error("Envio de email falhou — verifique a chave Resend");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi impossível");
    } finally { setQuoteBusy(false); }
  };

  const runEstimation = async () => {
    if (!plan?.plan_id) return;
    setEstimateBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/estimate-from-takeoff`, {
        project_type: estProjectType, finish_level: estFinishLevel,
      });
      setEstimateResult(data);
      // Si reabilitação → coche automatiquement TVA
      if (data.is_renovation) setQuoteIncludeTva(true);
      toast.success(`Estimativa générée : ${data.surface_m2} m² · ${data.estimation.total_avg?.toLocaleString("pt-PT")} €`);
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
      toast.success("Render 3D gerado!");
      await loadRender3dHistory();
      loadCredits3d();
    } catch (e) {
      handle3dError(e, "Geração 3D échouée (tente novamente)");
    } finally { setRender3dBusy(false); }
  };

  const openRender3dHistory = async (renderId) => {
    try {
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/renders-3d/${renderId}`);
      setRender3dImg(`data:${data.mime_type};base64,${data.image_b64}`);
      setRender3dStyle(data.style);
    } catch { toast.error("Carregamento impossível"); }
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
      toast.success("Visita em vídeo 3D gerada!");
      await loadVideoHistory();
      loadCredits3d();
    } catch (e) {
      handle3dError(e, "Geração vidéo échouée (tente novamente)");
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
    toast.success(`Modelo « ${t.name} » appliqué`);
  };

  const saveTemplate = async () => {
    if (templateName.trim().length < 2) return toast.error("Nome do modelo demasiado curto");
    try {
      await api.post("/quotes/templates", {
        name: templateName.trim(),
        finish: quoteFinish, floor_material: quoteFloor,
        is_shared: templateShared,
      });
      toast.success(`Modelo « ${templateName} » enregistré`);
      setTemplateName(""); setTemplateShared(false);
      await loadTemplates();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    }
  };

  const deleteTemplate = async (id) => {
    if (!window.confirm("Eliminar ce modelo ?")) return;
    try {
      await api.delete(`/quotes/templates/${id}`);
      await loadTemplates();
      toast.success("Modelo supprimé");
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
      setAllPlans(data.plans || data || []);
    } catch { /* ignore */ }
  };

  const duplicatePlan = async () => {
    if (!plan?.plan_id) return;
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/duplicate`);
      toast.success(`Plan dupliqué — ${data.rooms} compartimento${data.rooms > 1 ? "s" : ""} copiée${data.rooms > 1 ? "s" : ""}`);
      const { data: full } = await api.get(`/takeoffs/${data.plan_id}`);
      setPlan(full);
      setPageIndex(0);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Duplication impossível");
    }
  };

  const downloadMultiQuote = async () => {
    if (multiSelected.length === 0) return toast.error("Selecione pelo menos 1 plano");
    setMultiBusy(true);
    try {
      const backend = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const res = await fetch(`${backend}/api/quotes/multi-pdf`, {
        method: "POST", credentials: "include",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          plan_ids: multiSelected,
          project_name: multiProjectName.trim() || null,
          finish: quoteFinish, floor_material: quoteFloor,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "PDF Multi-Plans error");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `devis-projet.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Orçamento projet (${multiSelected.length} plans) descarregado`);
      setMultiDialog(false);
    } catch (e) { toast.error(e.message || "Exportação impossível"); }
    finally { setMultiBusy(false); }
  };

  // Phase A — créer UN devis éditable consolidado (gros œuvre + maison + ferraillage)
  const createConsolidatedQuote = async () => {
    if (multiSelected.length === 0) return toast.error("Selecione pelo menos 1 plano");
    setConsolidatedBusy(true);
    try {
      const { data } = await api.post("/documents/from-plans", {
        plan_ids: multiSelected,
        project_name: multiProjectName.trim() || "",
        subcontract_plan_ids: subcontractSel.filter((id) => multiSelected.includes(id)),
      });
      toast.success(`Orçamento consolidado créé — ${data.line_count} lignes`);
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
      toast.success(ferrIds.length ? "Ferraillage rattaché" : "Rattachement removido");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Rattachement impossível");
    }
  };

  const createSignatureLink = async (logId) => {
    const raw = window.prompt(
      "Sinal pedido na assinatura (% do total c/ IVA) — 30 por omissão, ou 0 para desativar:",
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
        ? `Lien copiado — sinal ${pct}% à la signature`
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
      toast.success(`Parede reclassé : ${next}`);
      await loadWallsSummary();
    } catch { toast.error("Reclassement impossível"); }
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
      toast.error(e?.response?.data?.detail || "Comparaison impossível");
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
              Mesurer + Render 3D
            </h1>
            <p className="text-sm text-muted-foreground mt-3 max-w-lg mx-auto">
              L'import de plans, la mesure automatique des superfícies, le takeoff calibré et
              la geração de renders 3D / vidéos 3D sont réservés au plan
              <b className="text-foreground"> Pro Business</b>.
              Passez sur ce plan pour débloquer ces outils métier.
            </p>
          </div>
          <div className="grid sm:grid-cols-3 gap-3 max-w-xl mx-auto">
            {[
              "Import PDF/DXF/photo",
              "Calibration + mesures pro",
              "Render 3D + vidéo",
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
              Voltar tableau de bord
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
      <div className="mx-auto max-w-[1100px] px-5 py-10 grid gap-8">
        <div>
          <p className="overline text-primary">ConstruPilot PLAN — Takeoff 2D</p>
          <h1 className="mt-3 font-display text-4xl lg:text-5xl font-bold tracking-tight">
            Importe o seu plano. Meça automaticamente. Orce.
          </h1>
          <p className="text-sm text-muted-foreground mt-3 max-w-2xl">
            PDF de arquitecto, plano digitalizado, foto de telemóvel: o ConstruPilot calibra a escala,
            extrai as medidas e transfere tudo para a estimativa ou a pesquisa de preços.
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
            const f = e.dataTransfer?.files?.[0];
            if (f) uploadFile(f);
          }}
        >
          <div className={`h-16 w-16 grid place-items-center rounded-sm transition-colors ${
            dragActive ? "bg-primary/25" : "bg-primary/10"
          }`}>
            <Upload className={`h-8 w-8 text-primary ${dragActive ? "animate-bounce" : ""}`} />
          </div>
          <div className="text-center">
            <p className="font-display text-xl font-bold">
              {uploading ? "A importar…" : dragActive ? "Solte para importar" : "Importar o meu plano"}
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              PDF · DXF · DWG · JPG · PNG · WEBP — jusqu'à 20 Mo — drag & drop ou clic
            </p>
          </div>
          <Input
            id="plan-upload-input"
            type="file"
            accept="application/pdf,image/png,image/jpeg,image/webp,.dxf,.dwg"
            className="sr-only"
            onChange={(e) => uploadFile(e.target.files?.[0])}
            data-testid="plan-upload-input"
          />
        </label>

        <div className="flex items-center gap-4 justify-between flex-wrap">
          <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={deskewEnabled}
              onChange={(e) => setDeskewEnabled(e.target.checked)}
              data-testid="deskew-toggle"
              className="accent-primary h-4 w-4"
            />
            Corrigir a perspetiva (foto de telemóvel inclinada)
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
            { icon: Wand2, title: "Deteção automática", desc: "Paredes (OpenCV) · compartimentos flood-fill · deskew photo inclinée" },
            { icon: Calculator, title: "Multi-pisos", desc: "R/C · 1.º · 2.º · sótão — medição por piso + total" },
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
            <div className="flex items-center justify-between mb-4">
              <p className="overline flex items-center gap-2">
                <History className="h-4 w-4" /> Mes plans récents
              </p>
              <span className="text-xs text-muted-foreground">
                {allPlans.length} plan{allPlans.length > 1 ? "s" : ""} enregistré{allPlans.length > 1 ? "s" : ""}
              </span>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {allPlans.slice(0, 6).map((p) => (
                <button
                  key={p.plan_id}
                  onClick={async () => {
                    try {
                      const { data } = await api.get(`/takeoffs/${p.plan_id}`);
                      setPlan(data);
                      setPageIndex(0);
                    } catch {
                      toast.error("Não foi possível abrir este plano");
                    }
                  }}
                  data-testid={`recent-plan-${p.plan_id}`}
                  className="text-left surface p-4 hover:border-primary transition-colors group"
                >
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
              ))}
            </div>
            {allPlans.length > 6 && (
              <p className="text-xs text-muted-foreground mt-3 text-center">
                + {allPlans.length - 6} outros — use «Comparar 2 planos» para ver tudo
              </p>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1600px] px-5 py-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <p className="overline">Plan · {plan.filename}</p>
          <h1 className="font-display text-2xl font-bold">
            {rooms.length} compartimento{rooms.length > 1 ? "s" : ""}
            {currentCalib && (
              <Badge variant="outline" className="ml-3 num text-xs rounded-sm" data-testid="calib-badge">
                {currentCalib.pixels_per_meter.toFixed(1)} px/m · {CALIB_METHOD_LABELS[currentCalib.method] || currentCalib.method}
                {currentCalib.samples_used ? ` (${currentCalib.samples_used} cotes)` : ""}
              </Badge>
            )}
            {!currentCalib && (
              <Badge variant="outline" className="ml-3 text-xs rounded-sm border-destructive text-destructive">
                Calibration nécessaire
              </Badge>
            )}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setPlan(null)} data-testid="plan-back-btn" className="rounded-sm gap-2">
            <Home className="h-4 w-4" /> Novo plan
          </Button>
          <Button variant="outline" onClick={clearAllMeasures} data-testid="plan-clear-all-btn"
                  title="Apagar todos os compartimentos, anotações e paredes desta página antes de começar um novo orçamento"
                  className="rounded-sm gap-2 border-destructive/50 text-destructive hover:bg-destructive hover:text-white">
            <Eraser className="h-4 w-4" /> Apagar tudo
          </Button>
          <Button variant="outline" onClick={duplicatePlan} data-testid="plan-duplicate-btn" className="rounded-sm gap-2"
                  title="Criar uma cópia deste plano (compartimentos, aberturas, calibrações)">
            <Copy className="h-4 w-4" /> Dupliquer
          </Button>
          <div className="flex items-center gap-1 border border-border rounded-sm px-1 h-9" data-testid="analyze-kind-toggle"
               title="Tipo de plano para a análise IA">
            {[
              { v: "auto", label: "Auto" },
              { v: "gros_oeuvre", label: "🏢 Estrutura" },
              { v: "maison", label: "🏠 Maison" },
            ].map((o) => (
              <button key={o.v} onClick={() => setPlanKindChoice(o.v)}
                      data-testid={`analyze-kind-${o.v}`}
                      className={`text-xs px-2 py-1 rounded-sm transition-colors ${
                        planKindChoice === o.v ? "bg-primary text-white" : "text-muted-foreground hover:text-foreground"}`}>
                {o.label}
              </button>
            ))}
          </div>
          <Button variant="outline" onClick={analyzePlanFull} disabled={analysisBusy} data-testid="plan-analyze-btn"
                  title="Análise TOUT automatiquement : structure (paredes/poteaux/poutres/dalles), compartimentos, medição et estimation chiffrée. Calibration obrigatória."
                  className="rounded-sm gap-2 border-red-500/60 text-red-500 hover:bg-red-500 hover:text-white font-semibold">
            <Sparkles className={`h-4 w-4 ${analysisBusy ? "animate-pulse" : ""}`} />
            {analysisBusy ? "Análise complète…" : "Analisar o plano (tudo)"}
          </Button>
          {(plan?.page_count || 1) > 1 && (
            <Button variant="outline" onClick={analyzeAllPages} disabled={analysisBusy} data-testid="plan-analyze-all-btn"
                    title="Inicia a análise IA em todas as páginas do PDF"
                    className="rounded-sm gap-2 border-red-500/40 text-red-500 hover:bg-red-500 hover:text-white">
              <Layers className="h-4 w-4" /> Toutes les pages
            </Button>
          )}
          <Button variant="outline" onClick={downloadPdf} data-testid="plan-pdf-export-btn"
                  className="rounded-sm gap-2">
            <FileDown className="h-4 w-4" /> Medição PDF
          </Button>
          <Button variant="outline" onClick={downloadXlsx} data-testid="plan-xlsx-export-btn"
                  className="rounded-sm gap-2">
            <Sheet className="h-4 w-4" /> Excel
          </Button>
          <Button variant="outline" onClick={() => setPcDialog(true)} data-testid="plan-pc-study-btn"
                  title="Estudo Licença de Construção (LC) — betão, aço, orçamentação regulamentar"
                  className="rounded-sm gap-2 border-emerald-500/60 text-emerald-600 hover:bg-emerald-500 hover:text-white">
            <FileSearch className="h-4 w-4" /> Estudo PC
          </Button>
          <PcStudyDialog open={pcDialog} onClose={() => setPcDialog(false)}
                         study={plan?.pc_study || null} busy={pcBusy}
                         onRun={runPcStudy} onDownload={downloadPcFile}
                         onDownloadXlsx={downloadXlsx}
                         planId={plan?.plan_id} onSent={refreshPlan}
                         onCompareSuppliers={comparePcSuppliers}
                         sentReports={(plan?.sent_reports || []).filter((s) => s.kind === "pc_study")}
                         ordersReports={(plan?.sent_reports || []).filter((s) => s.kind === "purchase_order")}
                         onRecompute={recomputePcStudy} />
          {(plan?.structural_metre || plan?.kind === "dxf") && (
            <Button variant="outline" onClick={() => setStructDialog(true)} data-testid="plan-structural-btn"
                    title="Medição da estrutura de betão a partir das camadas do DWG/DXF"
                    className="rounded-sm gap-2 border-amber-500/60 text-amber-600 hover:bg-amber-500 hover:text-white">
              <Ruler className="h-4 w-4" /> Medição structure
            </Button>
          )}
          <StructuralTakeoffDialog open={structDialog} onClose={() => setStructDialog(false)}
                                   planId={plan?.plan_id} />
          <Button variant="outline"
                  onClick={() => { setEstimateDialog(true); setEstimateResult(null); }}
                  data-testid="plan-estimate-btn"
                  className="rounded-sm gap-2 border-primary/60 text-primary hover:bg-primary hover:text-white">
            <Sparkles className="h-4 w-4" /> Estimativa
          </Button>
          <Button variant="outline"
                  onClick={() => { setRender3dDialog(true); setRender3dImg(null); setVideoUrl(null); setCreditPaywall(null); loadRender3dHistory(); loadVideoHistory(); loadCredits3d(); }}
                  data-testid="plan-render-3d-btn"
                  className="rounded-sm gap-2 border-primary/60 text-primary hover:bg-primary hover:text-white">
            <Sparkles className="h-4 w-4" /> Ver en 3D
          </Button>
          <Button variant="outline" onClick={() => { setQuoteDialog(true); loadTemplates(); loadQuoteSends(); loadVideoHistory(); }}
                  data-testid="plan-quote-pdf-btn"
                  className="rounded-sm gap-2 border-primary/60 text-primary hover:bg-primary hover:text-white">
            <FileDown className="h-4 w-4" /> Orçamento PDF
          </Button>
          <Button variant="outline" onClick={() => { setMultiDialog(true); loadAllPlans(); }}
                  data-testid="plan-multi-quote-btn"
                  className="rounded-sm gap-2">
            <FileDown className="h-4 w-4" /> Multi-plans
          </Button>
          <BrandingDialog />
          <MailboxDialog />
          <OuvrageComposeDialog onAdd={addOuvrageFromPlan} planVariables={planVariables} />
          {pendingOuvrages > 0 && (
            <Button variant="outline" onClick={() => nav("/devis-editeur")}
                    className="rounded-sm gap-2 border-primary text-primary" data-testid="plan-create-quote-ouvrages">
              <ArrowRight className="h-4 w-4" /> Criar um orçamento ({pendingOuvrages})
            </Button>
          )}
          <Button onClick={runAI} disabled={aiBusy} data-testid="plan-ai-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white"
                  title="Leitura do plano pela IA: compartimentos, cotas, superfícies, aberturas e tipos de parede">
            <Sparkles className={`h-4 w-4 ${aiBusy ? "animate-pulse" : ""}`} />
            {aiBusy ? "Leitura do plano…" : "Ler o plano (IA)"}
          </Button>
        </div>
      </div>

      {/* Pré-visualização medição instantané — récap après « Analisar o plano (tudo) » */}
      {analysisRecap && (
        <div className="surface p-4 border-2 border-primary/40 bg-primary/5" data-testid="analysis-recap">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              <span className="font-display font-bold text-base">Pré-visualização du medição</span>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-primary/10 text-primary px-2 py-0.5 rounded-full">Análise terminée</span>
            </div>
            <button onClick={() => setAnalysisRecap(null)} className="text-muted-foreground hover:text-foreground text-xs" data-testid="recap-close">Masquer</button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="rounded-sm bg-background border border-border p-3" data-testid="recap-rooms">
              <p className="text-[11px] text-muted-foreground">Compartimentos</p>
              <p className="num text-xl font-extrabold">{analysisRecap.rooms}</p>
            </div>
            <div className="rounded-sm bg-background border border-border p-3" data-testid="recap-surface">
              <p className="text-[11px] text-muted-foreground">Superfície compartimentos</p>
              <p className="num text-xl font-extrabold">{analysisRecap.surface_pieces_m2 || 0} m²</p>
            </div>
            <div className="rounded-sm bg-background border border-border p-3" data-testid="recap-structure">
              <p className="text-[11px] text-muted-foreground">Structure</p>
              <p className="num text-sm font-bold">{analysisRecap.walls} paredes · {analysisRecap.columns} pot. · {analysisRecap.beams} pou.</p>
            </div>
            <div className="rounded-sm bg-background border border-border p-3" data-testid="recap-beton">
              <p className="text-[11px] text-muted-foreground">Béton total</p>
              <p className="num text-xl font-extrabold">{analysisRecap.beton_m3 || 0} m³</p>
            </div>
            <div className="rounded-sm bg-background border border-border p-3" data-testid="recap-acier">
              <p className="text-[11px] text-muted-foreground">Aços</p>
              <p className="num text-xl font-extrabold text-orange-600">{analysisRecap.acier_kg || 0} kg</p>
            </div>
            <div className="rounded-sm bg-primary/10 border border-primary/30 p-3" data-testid="recap-estimation">
              <p className="text-[11px] text-muted-foreground">Estimativa</p>
              <p className="num text-xl font-extrabold text-primary">
                {(analysisRecap.estimation_globale_eur || analysisRecap.estimation_beton_eur || 0).toLocaleString("pt-PT")} €
              </p>
              <p className="text-[10px] text-muted-foreground">{analysisRecap.estimation_globale_eur ? "reabilitação (moy.)" : "gros œuvre béton"}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <Button size="sm" onClick={sendToQuote} className="rounded-sm gap-2" data-testid="recap-to-quote">
              <ArrowRight className="h-3.5 w-3.5" /> Gerar orçamento
            </Button>
            <Button size="sm" variant="outline" onClick={() => { setRightTab("rooms"); }} className="rounded-sm gap-2" data-testid="recap-see-rooms">
              Ver les compartimentos
            </Button>
          </div>
          {(analysisRecap.rooms === 0 && analysisRecap.walls === 0) && (
            <p className="mt-2 text-[11px] text-muted-foreground">Nenhum élément detetado automatiquement — verifique la calibration ou tracez les compartimentos manuellement.</p>
          )}
        </div>
      )}


      <div className="surface p-3 flex items-center gap-4 flex-wrap" data-testid="plan-settings-bar">
        <div className="flex items-center gap-2">
          <span className="text-xs overline">Definições du plan</span>
          <button
            onClick={() => setSettingsOpen((v) => !v)}
            className="text-primary text-xs hover:underline"
            data-testid="toggle-plan-settings"
          >
            {settingsOpen ? "Masquer" : "Editar"}
          </button>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Altura paredes</span>
          <b className="num text-primary">{planDefaults.ceiling_h_m} m</b>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Espessura plancher</span>
          <b className="num text-primary">{(planDefaults.floor_thickness_m * 100).toFixed(0)} cm</b>
        </div>
        {settingsOpen && (
          <div className="flex items-center gap-3 flex-1 justify-end flex-wrap">
            <label className="flex items-center gap-2 text-xs">
              <span>Altura paredes (m) :</span>
              <Input
                type="number" step="0.05" min="1.5" max="6"
                value={planDefaults.ceiling_h_m}
                onChange={(e) => setPlanDefaults((d) => ({ ...d, ceiling_h_m: parseFloat(e.target.value) || 2.5 }))}
                className="h-8 w-20 text-xs num"
                data-testid="settings-ceiling-h"
              />
            </label>
            <label className="flex items-center gap-2 text-xs">
              <span>Espessura plancher (cm) :</span>
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
          Estes valores aplicam-se aos novos compartimentos criados ou importados pela IA (podem ser ajustados por compartimento).
        </p>
      </div>

      <div className="grid lg:grid-cols-[240px_1fr_360px] gap-4">
        {/* SIDEBAR PAGES */}
        <div className="surface p-3 max-h-[80vh] overflow-auto">
          <p className="overline mb-3">Pages ({plan.page_count})</p>
          <div className="grid gap-2">
            {plan.pages.map((pg, i) => (
              <div key={i}>
                <button
                  data-testid={`plan-page-${i}`}
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
          : "surface p-3"} data-testid="plan-canvas-surface">
          {/* TOOLBAR */}
          <div className="flex flex-wrap gap-2 mb-3 pb-3 border-b border-border">
            <MeasureHelpDialog />
            <ToolButton icon={MousePointer2} label="Sélection" testId="tool-select" active={tool === TOOLS.SELECT} onClick={() => { setTool(TOOLS.SELECT); setPoints([]); }} />
            <ToolButton icon={Ruler} label="Calibrer" testId="tool-calibrate" active={tool === TOOLS.CALIB} onClick={() => { setTool(TOOLS.CALIB); setPoints([]); }} />
            <ToolButton icon={Move} label="Distance" testId="tool-distance" active={tool === TOOLS.DIST} onClick={() => { setTool(TOOLS.DIST); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Layers} label="Perímetro" testId="tool-polyline" active={tool === TOOLS.POLY} onClick={() => { setTool(TOOLS.POLY); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Hexagon} label="Superfície" testId="tool-surface" active={tool === TOOLS.SURFACE} onClick={() => { setTool(TOOLS.SURFACE); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Square} label="Compartimento" testId="tool-room" active={tool === TOOLS.ROOM} onClick={() => { setTool(TOOLS.ROOM); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Wand2} label="Auto-compartimento" testId="tool-autoroom" active={tool === TOOLS.AUTOROOM} onClick={() => { setTool(TOOLS.AUTOROOM); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={DoorOpen} label="Ouverture" testId="tool-opening" active={tool === TOOLS.OPENING} onClick={() => { setTool(TOOLS.OPENING); setPoints([]); }} disabled={!currentCalib || rooms.length === 0} />
            {/* Iter 57 — QuoterPlan-like tools */}
            <ToolButton icon={Hash} label="Contador" testId="tool-counter" active={tool === TOOLS.COUNTER} onClick={() => { setTool(TOOLS.COUNTER); setPoints([]); }} />
            <ToolButton icon={StickyNote} label="Note" testId="tool-note" active={tool === TOOLS.NOTE} onClick={() => { setTool(TOOLS.NOTE); setPoints([]); }} />
            <ToolButton icon={Triangle} label="Ângulo" testId="tool-angle" active={tool === TOOLS.ANGLE} onClick={() => { setTool(TOOLS.ANGLE); setPoints([]); }} />
            <ToolButton icon={MountainSnow} label="Inclinação cobertura" testId="tool-pitch" active={tool === TOOLS.PITCH} onClick={() => { setTool(TOOLS.PITCH); setPoints([]); }} disabled={!currentCalib} />
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
                  <Layers className="h-3 w-3" /> Paredes ({detectedWalls.segment_count})
                </Button>
                <Button size="sm" variant={reclassifyMode ? "default" : "outline"}
                        onClick={() => setReclassifyMode(v => !v)}
                        data-testid="toggle-reclassify-mode"
                        className={`rounded-sm gap-1 h-8 ${reclassifyMode ? "bg-primary text-white hover:bg-orange-600" : ""}`}>
                  {reclassifyMode ? "Reclasser (actif)" : "Reclasser"}
                </Button>
              </>
            )}
            <Button size="sm" variant="ghost" onClick={() => setPoints(points.slice(0, -1))} disabled={!points.length} className="rounded-sm gap-1" title="Cancelar o último ponto colocado">
              <Undo2 className="h-3 w-3" /> Cancelar último ponto
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
                                  : "Plan verrouillé — mesures précises garanties");
              }}
              data-testid="tool-lock"
              className={`rounded-sm gap-1 h-8 ${locked ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title={locked ? "Desbloquear (autoriser zoom + déplacement)"
                            : "Bloquear o plano (bloquear zoom + deslocação para cliques precisos)"}
            >
              {locked ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
              {locked ? "Verrouillé" : "Bloquear"}
            </Button>
            <Button
              size="sm"
              variant={objectPanelOpen ? "default" : "outline"}
              onClick={() => setObjectPanelOpen((o) => !o)}
              data-testid="tool-objects-panel"
              className={`rounded-sm gap-1 h-8 ${objectPanelOpen ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title="Abrir o Painel Objetos (edição & jump-to)"
            >
              <Layers className="h-3 w-3" />
              Objetos
            </Button>
            {/* P1 — Estado d'enregistrement automatique + enregistrement manuel */}
            <span data-testid="autosave-status"
                  className={`inline-flex items-center gap-1 text-xs px-2 h-8 rounded-sm ${saving ? "text-amber-500" : "text-emerald-600"}`}
                  title="Vos mesures et modifications sont enregistrées automatiquement">
              <span className={`h-1.5 w-1.5 rounded-full ${saving ? "bg-amber-500 animate-pulse" : "bg-emerald-500"}`} />
              {saving ? "A guardar…" : savedAt ? "Guardado ✓" : "Guardar automático ativo"}
            </span>
            <Button size="sm" variant="outline" onClick={manualSave} disabled={saving}
                    data-testid="plan-save-btn" className="rounded-sm gap-1 h-8"
                    title="Forcer l'enregistrement maintenant">
              <Save className="h-3 w-3" /> Guardar
            </Button>
            {/* P1 — Definição contraste/luminosité du plan */}
            <div className="relative">
              <Button
                size="sm"
                variant={showImgAdjust ? "default" : "outline"}
                onClick={() => setShowImgAdjust((v) => !v)}
                data-testid="tool-img-adjust"
                className={`rounded-sm gap-1 h-8 ${showImgAdjust ? "bg-primary text-white hover:bg-orange-600" : ""}`}
                title="Ajustar o contraste e a luminosidade do plano"
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
                    Reinicializar
                  </Button>
                </div>
              )}
            </div>
            {/* P1 — Ecrã inteiro */}
            <Button
              size="sm"
              variant={fullscreen ? "default" : "outline"}
              onClick={() => setFullscreen((v) => !v)}
              data-testid="tool-fullscreen"
              className={`rounded-sm gap-1 h-8 ${fullscreen ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title={fullscreen ? "Sair do ecrã inteiro (Esc)" : "Mostrar o plano em ecrã inteiro"}
            >
              {fullscreen ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
              {fullscreen ? "Quitter" : "Ecrã inteiro"}
            </Button>
            {/* P3 — Assistant IA d'edição du plan */}
            <Button
              size="sm"
              variant={aiCmdOpen ? "default" : "outline"}
              onClick={() => setAiCmdOpen((v) => !v)}
              data-testid="tool-ai-assistant"
              className={`rounded-sm gap-1 h-8 ${aiCmdOpen ? "bg-primary text-white hover:bg-orange-600" : "border-primary/60 text-primary"}`}
              title="Assistente IA: modifique o plano em linguagem natural"
            >
              <Bot className="h-3 w-3" /> Assistant IA
            </Button>
          </div>

          {/* CANVAS */}
          <div className={fullscreen ? "relative h-[calc(100vh-92px)]" : "relative"}>
          <PlanCanvas
            pageData={pageData} tool={tool} points={points} rooms={rooms}
            calibration={currentCalib} zoom={zoom} offset={offset} rotation={rotation}
            onCanvasClick={onCanvasClick} onZoomChange={setZoom} onOffsetChange={setOffset}
            onAutoRotate={() => {
              if (!autoRotated) {
                setRotation(90);
                setAutoRotated(true);
                toast.success("Plano rodado para paisagem para facilitar as medições");
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
            onCanvasDoubleClick={onCanvasDoubleClick}
            showDeltas={showDeltas}
            contrast={planContrast}
            brightness={planBrightness}
            measurements={pageMeasurements}
            structure={structure}
            showStructure={showStructure}
            selectedStruct={selectedStruct}
            onStructSelect={setSelectedStruct}
            onStructDrag={dragStructPoint}
            onStructDragEnd={commitStructure}
          />

          {/* P3 — Panneau Assistant IA (barre de encomenda + aperçu/appliquer) */}
          {aiCmdOpen && (
            <div className="absolute bottom-3 left-3 z-30 w-[340px] max-w-[calc(100%-24px)] border border-primary/50 bg-background/97 backdrop-blur rounded-md p-3 shadow-xl grid gap-2"
                 data-testid="ai-assistant-panel">
              <div className="flex items-center justify-between">
                <p className="overline text-primary flex items-center gap-1"><Bot className="h-3.5 w-3.5" /> Assistant IA du plan</p>
                <button onClick={() => { setAiCmdOpen(false); setAiCmdProposal(null); }}
                        className="text-muted-foreground hover:text-foreground" data-testid="ai-assistant-close">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <p className="text-xs text-muted-foreground leading-snug">
                Ex : « renomme Chambre en Bureau », « corrige la surface de la cuisine à 14 m² »,
                « supprime la compartimento SDB », « reclasse ce parede en cloison ».
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
                <Button size="sm" onClick={aiProposeCommand} disabled={aiCmdBusy || !aiCmd.trim()}
                        className="rounded-sm gap-1 h-9" data-testid="ai-command-propose">
                  {aiCmdBusy && !aiCmdProposal ? <Sparkles className="h-3.5 w-3.5 animate-pulse" /> : <Sparkles className="h-3.5 w-3.5" />}
                  Proposer
                </Button>
              </div>
              {aiCmdProposal && (
                <div className="border border-border rounded-sm p-2.5 grid gap-2 bg-secondary/40" data-testid="ai-command-proposal">
                  <p className="text-xs"><b className="text-primary">Pré-visualização : </b>{aiCmdProposal.summary}</p>
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="ghost" onClick={() => setAiCmdProposal(null)}
                            className="rounded-sm h-7 text-xs" data-testid="ai-command-cancel">
                      Cancelar
                    </Button>
                    <Button size="sm" onClick={aiApplyCommand} disabled={aiCmdBusy}
                            className="rounded-sm h-7 text-xs gap-1" data-testid="ai-command-apply">
                      <Save className="h-3 w-3" /> Appliquer
                    </Button>
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
                  Calibra a página para comparar a medida com o valor escrito.
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
            onConvertMeasure={convertMeasureToRoom}
            onDeductMeasure={deductMeasure}
            onDeleteCounter={(id) => deleteAnnotationLocal("counters", id)}
            onRenameCounter={(id, name) => updateAnnotationLocal("counters", id, { label: name })}
            onDeleteNote={(id) => deleteAnnotationLocal("notes", id)}
            onEditNote={(id, text) => updateAnnotationLocal("notes", id, { text })}
            onDeleteAngle={(id) => deleteAnnotationLocal("angles", id)}
            onDeletePitched={(id) => deleteAnnotationLocal("pitched_surfaces", id)}
          />

          <RoomEstimateDialog
            open={roomEstimate !== null}
            estimate={roomEstimate}
            planId={plan?.plan_id}
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
                project_name: `Compartimento ${est.room?.name || "-"} — ${plan?.filename || "Plan"}`,
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

          {/* ACTIVE TOOL BAR — Voltar + Cancelar último ponto (todas as ferramentas de medição) */}
          {tool !== TOOLS.SELECT && (
            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-sm border border-primary/30 bg-primary/5 px-3 py-2"
                 data-testid="active-tool-bar">
              <Badge variant="outline" className="rounded-sm gap-1 border-primary/40 text-primary font-semibold">
                Outil actif : {TOOL_LABELS[tool] || tool}
              </Badge>
              <span className="flex-1" />
              <Button size="sm" variant="outline" onClick={() => setPoints(points.slice(0, -1))}
                      disabled={!points.length} data-testid="tool-undo-point"
                      className="rounded-sm gap-1 h-8">
                <Undo2 className="h-3 w-3" /> Cancelar último ponto
              </Button>
              <Button size="sm" variant="secondary" onClick={() => { setTool(TOOLS.SELECT); setPoints([]); }}
                      data-testid="tool-back-select" className="rounded-sm gap-1 h-8">
                <ArrowLeft className="h-3 w-3" /> Voltar
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
              {tool === TOOLS.DIST && points.length === 2 && (
                <Button size="sm" onClick={() => finishDistance()} data-testid="tool-finish-distance" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Mesurer
                </Button>
              )}
              {tool === TOOLS.POLY && points.length >= 2 && (
                <Button size="sm" onClick={() => finishPolyline()} data-testid="tool-finish-polyline" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Terminar polyligne
                </Button>
              )}
              {tool === TOOLS.SURFACE && points.length >= 3 && (
                <Button size="sm" onClick={() => finishSurface()} data-testid="tool-finish-surface" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Terminar surface
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
                    <Save className="h-3 w-3" /> Fermer compartimento
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
                    title="Ângulo de pente en degrés (0° = plat)"
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
                  {points.length === 0 && "Clique na 1.ª aresta do ângulo"}
                  {points.length === 1 && "Clique no vértice do ângulo"}
                  {points.length === 2 && "Clique na 2.ª aresta"}
                </span>
              )}
              <Button size="sm" variant="ghost" onClick={() => setPoints([])} className="rounded-sm" title="Apagar tous les points de la mesure en cours">Cancelar tout</Button>
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
                  const label = window.prompt(`Nome do contador ${nb + 1} (ex: Tomadas, Focos, Radiadores):`, `Contador ${nb + 1}`);
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
                + Novo compteur
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
                    if (!window.confirm("Eliminar ce compteur et ses marqueurs ?")) return;
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
                <p className="overline">Paredes detetados {reclassifyMode && (
                  <span className="text-primary">· cliquez sur un parede pour cycler son type</span>
                )}</p>
                <Badge variant="outline" className="rounded-sm text-[10px] num">
                  {detectedWalls.segment_count} segments
                </Badge>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[
                  ["porteur",  "text-red-500 border-red-500/40 bg-red-500/5",   "Resistente"],
                  ["cloison",  "text-primary border-primary/40 bg-primary/5",   "Divisória"],
                  ["doublage", "text-blue-500 border-blue-500/40 bg-blue-500/5", "Forro"],
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
              {/* Distinção material resistente detetada pela IA (tijolo / bloco / betão) */}
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
                      não detetado — executa «Ler a planta (IA)»
                    </span>
                  )}
                  {plan.ai_analysis.wall_types.load_bearing_visible && (
                    <Badge variant="outline" className="rounded-sm text-[10px] border-red-500/40 text-red-500">resistentes visíveis</Badge>
                  )}
                  {plan.ai_analysis.wall_types.partition_visible && (
                    <Badge variant="outline" className="rounded-sm text-[10px] border-primary/40 text-primary">divisórias visíveis</Badge>
                  )}
                </div>
              )}
            </div>
          )}

          {/* STRUCTURE IA — edição paredes / aberturas */}
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
                    <span className="text-purple-500 font-bold"> ■</span> portas
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
                  <p className="text-[10px] uppercase font-bold tracking-wider">Abert.</p>
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

              {/* Descritivo chiffré */}
              {descritivo && (
                <div className="mb-2 border border-border rounded-sm p-2 bg-background" data-testid="structure-descritivo">
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="overline">Descritivo chiffré</p>
                    <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      Altura paredes
                      <input type="number" step="0.1" min="1" max="6" value={wallHeight}
                             onChange={(e) => setWallHeight(parseFloat(e.target.value) || 2.5)}
                             data-testid="structure-wall-height"
                             className="w-14 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> m
                    </label>
                  </div>
                  {/* Altura par arases NGF (AS - AI) — prioritaire sur la altura paredes */}
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
                  {/* Presets de definições béton par chantier */}
                  <div className="flex items-center gap-2 mb-1.5">
                    <select value={selectedPreset}
                            onChange={(e) => { if (e.target.value) applyBetonPreset(e.target.value); else setSelectedPreset(""); }}
                            data-testid="beton-preset-select"
                            className="flex-1 h-7 text-[11px] rounded-sm border border-input bg-background px-1">
                      <option value="">Escolher un definição (chantier)…</option>
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
                  {!descritivo.calibrated && (
                    <p className="text-[10px] text-destructive mb-1">⚠️ Plan non calibré — quantités indisponibles.</p>
                  )}
                  {/* Épaisseurs réglables pour le medição béton */}
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
                    <summary className="text-[10px] font-semibold cursor-pointer text-orange-600">Ratios aços (kg/m³) — ajustables</summary>
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
                      <Save className="h-3 w-3" /> Guardar comme definições par défaut
                    </Button>
                  </details>
                  {/* Prix béton par poste (€/m³) — chiffrage plus fin */}
                  <details className="mb-1.5" data-testid="beton-prices-poste">
                    <summary className="text-[10px] font-semibold cursor-pointer text-sky-600">Prix béton par poste (€/m³) — optionnel</summary>
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
                      <p className="text-[9px] text-muted-foreground">0 = barème auto selon l'espessura : ≤16 cm → 120 € · 17–20 cm → 140 € · &gt;20 cm → 160 €/m².</p>
                    </div>
                    <label className="flex items-center gap-1 mt-1.5 text-[10px] text-muted-foreground">Espessura béton de propreté
                      <input type="number" step="1" min="0" max="30"
                             value={Math.round(propreteEp * 100)}
                             onChange={(e) => setPropreteEp((parseFloat(e.target.value) || 0) / 100)}
                             data-testid="proprete-ep-cm"
                             className="w-14 rounded-sm border border-input bg-background px-1 py-0.5 text-right num" /> cm
                    </label>
                  </details>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                    <span className="text-muted-foreground flex items-center gap-1">Planchers (sol)
                      {descritivo.planchers_source === "auto" && (
                        <span className="text-[9px] px-1 rounded-sm bg-emerald-500/15 text-emerald-600 font-bold" data-testid="planchers-auto-badge">AUTO IA</span>
                      )}
                    </span><span className="num text-right">{descritivo.planchers_m2} m²</span>
                    <span className="text-muted-foreground">Paredes resistentes</span><span className="num text-right">{descritivo.murs_porteurs_ml} ml</span>
                    <span className="text-muted-foreground">Divisórias</span><span className="num text-right">{descritivo.cloisons_ml} ml</span>
                    <span className="text-muted-foreground">Paredes (área)</span><span className="num text-right">{descritivo.murs_surface_m2} m²</span>
                    <span className="text-muted-foreground">Portas / Janelas / Vãos de sacada</span><span className="num text-right">{descritivo.portes} / {descritivo.fenetres} / {descritivo.baies}</span>
                    <span className="text-muted-foreground">Vigas</span><span className="num text-right">{descritivo.poutres_ml} ml</span>
                    <span className="text-muted-foreground">Pilares</span><span className="num text-right">{descritivo.poteaux || 0} u</span>
                    <span className="text-muted-foreground">Sapatas</span><span className="num text-right">{descritivo.semelles || 0} u</span>
                    {descritivo.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Betão total</span>
                        <span className="num text-right font-semibold" data-testid="descritivo-beton">{descritivo.beton_total_m3} m³</span>
                      </>
                    )}
                    {descritivo.acier_total_kg > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Aço (armadura)</span>
                        <span className="num text-right font-semibold text-orange-600" data-testid="descritivo-acier">{descritivo.acier_total_kg} kg</span>
                      </>
                    )}
                    {(betonPriceM3 > 0 || acierPriceKg > 0) && descritivo.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Custo de material (betão + aço)</span>
                        <span className="num text-right font-semibold text-emerald-700" data-testid="descritivo-cout-matiere">
                          {Math.round((descritivo.beton_total_m3 || 0) * betonPriceM3 + (descritivo.acier_total_kg || 0) * acierPriceKg).toLocaleString("pt-PT")} €
                        </span>
                      </>
                    )}
                    {(betonPriceM3 > 0 || acierPriceKg > 0 || laborPriceM3 > 0) && descritivo.beton_total_m3 > 0 && (
                      <>
                        <span className="text-muted-foreground font-semibold">Preço de venda estimado{marginPct > 0 ? ` (margem ${marginPct}%)` : ""}</span>
                        <span className="num text-right font-bold text-primary" data-testid="descritivo-prix-vente">
                          {Math.round((((descritivo.beton_total_m3 || 0) * betonPriceM3 + (descritivo.acier_total_kg || 0) * acierPriceKg) + (descritivo.beton_total_m3 || 0) * laborPriceM3) * (1 + marginPct / 100)).toLocaleString("pt-PT")} €
                        </span>
                      </>
                    )}
                  </div>
                  {descritivo.beton_total_m3 > 0 && (
                    <details className="mt-2" open data-testid="detail-par-poste">
                      <summary className="text-[11px] font-semibold cursor-pointer text-primary">Detalhe por rubrica (betão + aço)</summary>
                      <div className="mt-1 border border-border rounded-sm overflow-hidden">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60"><tr>
                            <th className="text-left px-1.5 py-1">Rubrica</th>
                            <th className="text-right px-1.5 py-1">Betão</th>
                            <th className="text-right px-1.5 py-1">Aço</th>
                          </tr></thead>
                          <tbody>
                            {[
                              { k: "semelles", label: `Sapatas (${descritivo.semelles || 0} u)`, b: descritivo.beton_semelles_m3, a: descritivo.acier_semelles_kg },
                              { k: "proprete", label: "Betão de limpeza (esp. 5 cm)", b: descritivo.beton_proprete_m3, a: 0 },
                              { k: "poteaux", label: `Pilares (${descritivo.poteaux || 0} u)`, b: descritivo.beton_poteaux_m3, a: descritivo.acier_poteaux_kg },
                              { k: "poutres", label: `Vigas (${descritivo.poutres_ml || 0} ml)`, b: descritivo.beton_poutres_m3, a: descritivo.acier_poutres_kg },
                              { k: "dalles", label: `Lajes / pavimentos (${descritivo.planchers_m2 || 0} m²)`, b: descritivo.beton_dalles_m3, a: descritivo.acier_dalles_kg },
                              { k: "voiles", label: `Paredes betão / resistentes (${descritivo.murs_porteurs_ml || 0} ml)`, b: descritivo.beton_voiles_m3, a: descritivo.acier_voiles_kg },
                            ].filter((r) => (r.b || 0) > 0).map((r) => (
                              <tr key={r.k} className="border-t border-border" data-testid={`poste-row-${r.k}`}>
                                <td className="px-1.5 py-0.5">{r.label}</td>
                                <td className="px-1.5 py-0.5 num text-right">{r.b} m³</td>
                                <td className="px-1.5 py-0.5 num text-right text-orange-600">{r.a ? `${r.a} kg` : "—"}</td>
                              </tr>
                            ))}
                            <tr className="border-t-2 border-border bg-muted/40 font-bold">
                              <td className="px-1.5 py-1">Total</td>
                              <td className="px-1.5 py-1 num text-right">{descritivo.beton_total_m3} m³</td>
                              <td className="px-1.5 py-1 num text-right text-orange-600">{descritivo.acier_total_kg} kg</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </details>
                  )}
                    <details className="mt-2" data-testid="poteaux-table">
                      <summary className="text-[11px] font-semibold cursor-pointer text-purple-600">Tableau des poteaux ({descritivo.poteaux_table.length})</summary>
                      <div className="mt-1 max-h-40 overflow-auto border border-border rounded-sm">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60 sticky top-0"><tr>
                            <th className="text-left px-1.5 py-1">Repère</th><th className="text-left px-1.5 py-1">Section</th><th className="text-right px-1.5 py-1">Béton</th>
                          </tr></thead>
                          <tbody>
                            {descritivo.poteaux_table.map((p) => (
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
                  {descritivo.beams_table?.length > 0 && (
                    <details className="mt-2" data-testid="poutres-table">
                      <summary className="text-[11px] font-semibold cursor-pointer text-purple-800">Tableau des poutres ({descritivo.beams_table.length})</summary>
                      <div className="mt-1 max-h-40 overflow-auto border border-border rounded-sm">
                        <table className="w-full text-[10px]">
                          <thead className="bg-muted/60 sticky top-0"><tr>
                            <th className="text-left px-1.5 py-1">Repère</th><th className="text-right px-1.5 py-1">Portée</th><th className="text-right px-1.5 py-1">Béton</th>
                          </tr></thead>
                          <tbody>
                            {descritivo.beams_table.map((b) => (
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
                    <FileDown className="h-4 w-4" /> {quoteBusy ? "Estimativa en cours…" : "Estimar o orçamento (PDF)"}
                  </Button>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Estrutura / betão apenas — paredes, pilares, vigas, lajes, sapatas + aço (área = lajes) · betão {betonPriceM3} €/m³ · aço {acierPriceKg} €/kg · mão de obra {laborPriceM3} €/m³ · margem {marginPct}%
                  </p>
                  <div className="flex items-center gap-2 mt-2">
                    <Button size="sm" variant="outline" onClick={sendToQuote} data-testid="structure-to-quote"
                            className="rounded-sm h-7 text-xs gap-1 flex-1">
                      <ArrowRight className="h-3 w-3" /> Ouvrir dans l'editor
                    </Button>
                    <Button size="sm" variant="outline" onClick={exportAnnotatedPdf} data-testid="structure-export-pdf"
                            className="rounded-sm h-7 text-xs gap-1">
                      <FileDown className="h-3 w-3" /> PDF anotado
                    </Button>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <Button size="sm" variant="outline" onClick={exportBetonXlsx} data-testid="structure-export-beton-xlsx"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-emerald-700 border-emerald-600/40">
                      <Sheet className="h-3 w-3" /> Medição Excel
                    </Button>
                    <Button size="sm" variant="outline" onClick={exportBetonPdf} data-testid="structure-export-beton-pdf"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-red-700 border-red-600/40">
                      <FileDown className="h-3 w-3" /> Medição PDF
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setAiChatOpen(true)} data-testid="structure-ai-assistant"
                            className="rounded-sm h-7 text-xs gap-1 flex-1 text-primary border-primary/40">
                      <Bot className="h-3 w-3" /> Assistant IA
                    </Button>
                  </div>
                </div>
              )}
              <p className="text-[10px] text-muted-foreground mb-2">
                Clica numa parede/abertura para a selecionar e depois arrasta as extremidades (pontos brancos) para a ajustar.
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
                      {selectedStruct.type === "wall" ? "Resistente ↔ Divisória" : "Porta ↔ Janela ↔ Vão de sacada"}
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

        {/* RIGHT PANEL — Medição */}
        <div className="surface p-4 max-h-[80vh] overflow-auto">
          <Tabs value={rightTab} onValueChange={setRightTab}>
            <TabsList className="w-full rounded-sm">
              <TabsTrigger value="rooms" className="flex-1 rounded-sm" data-testid="tab-rooms">Compartimentos</TabsTrigger>
              <TabsTrigger value="materials" className="flex-1 rounded-sm" data-testid="tab-materials">Materiais</TabsTrigger>
              <TabsTrigger value="ai" className="flex-1 rounded-sm" data-testid="tab-ai">IA</TabsTrigger>
              <TabsTrigger value="history" className="flex-1 rounded-sm" data-testid="tab-history" onClick={loadHistory}>
                <History className="h-3 w-3" />
              </TabsTrigger>
            </TabsList>

            <TabsContent value="rooms" className="mt-3 grid gap-3">
              {rooms.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Calibra a planta e depois usa a ferramenta <b>Compartimento</b> para desenhar um contorno.
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
                               title={`Superfície écrite sur le plan : ${r.surface_written_m2} m²`}
                               data-testid={`room-surface-delta-${r.room_id}`}>
                          écrit {r.surface_written_m2} m² ({r.surface_delta_pct > 0 ? "+" : ""}{r.surface_delta_pct}%)
                        </Badge>
                      )}
                      {(r.deductions || []).map((d) => (
                        <Badge key={d.deduction_id} variant="outline"
                               className="rounded-sm text-[10px] num border-red-400 text-red-500 gap-1"
                               title={`Superfície brute : ${r.surface_gross_m2} m²`}
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
                    <span>Paredes bruts</span><span className="text-right">{r.wall_area_gross_m2} m²</span>
                    <span>Aberturas</span><span className="text-right text-destructive">-{r.openings_area_m2 || 0} m²</span>
                    <span>Paredes nets</span><span className="text-right font-bold">{r.wall_area_net_m2} m²</span>
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
                  <Calculator className="h-4 w-4" /> Calculer le medição total
                </Button>
              )}
              {takeoff && (
                <div className="border-t border-border pt-3 grid gap-1 text-xs num" data-testid="takeoff-totals">
                  <p className="overline mb-2">Totaux</p>
                  <div className="flex justify-between"><span>Sol total</span><b>{takeoff.totals.floor_m2} m²</b></div>
                  <div className="flex justify-between"><span>Plafonds</span><b>{takeoff.totals.ceiling_m2} m²</b></div>
                  <div className="flex justify-between"><span>Paredes nets</span><b>{takeoff.totals.walls_net_m2} m²</b></div>
                  <div className="flex justify-between"><span>Perímetro</span><b>{takeoff.totals.perimeter_m} m</b></div>

                  {takeoff.levels?.length > 1 && (
                    <div className="mt-3" data-testid="takeoff-by-level">
                      <p className="overline mb-2">Par niveau</p>
                      {takeoff.levels.map((lvl) => (
                        <div key={String(lvl.level_index)} className="border-l-2 border-primary pl-2 mb-2">
                          <p className="font-bold text-primary">{lvl.level_label} · {lvl.rooms.length} compartimento{lvl.rooms.length > 1 ? "s" : ""}</p>
                          <div className="flex justify-between"><span>Sol</span><span>{lvl.totals.floor_m2} m²</span></div>
                          <div className="flex justify-between"><span>Paredes nets</span><span>{lvl.totals.walls_net_m2} m²</span></div>
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
                    lines={[[`Superfície`, `${materials.floor.surface_m2} m²`], [`+${materials.floor.waste_pct}% pertes`, `${materials.floor.quantity_m2} m² à commander`]]} />}
                  {materials.paint && <MatCard label="Peinture" lines={[
                    [`Superfície`, `${materials.paint.surface_m2} m²`],
                    [`${materials.paint.coats} couches, marge ${materials.paint.margin_pct}%`, `${materials.paint.liters_recommended} L`],
                  ]} />}
                  {materials.placo && <MatCard label="Pladur" lines={[
                    [`Superfície`, `${materials.placo.surface_m2} m²`],
                    [`+${materials.placo.waste_pct}% pertes`, `${materials.placo.plates} plaques`],
                  ]} />}
                  {materials.skirting && <MatCard label="Plinthes" lines={[
                    [`Perímetro - portas`, `${materials.skirting.net_m} m`],
                    [`+ pertes`, `${materials.skirting.quantity_m} m`],
                  ]} />}
                </div>
              )}
            </TabsContent>

            <TabsContent value="ai" className="mt-3 grid gap-3">
              {!plan.ai_analysis && (
                <p className="text-xs text-muted-foreground">
                  Clique sur <b>Análise IA du plan</b> en haut pour détecter automatiquement les compartimentos, ouvertures et superfícies écrites.
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
                      <p className="overline">Symboles detetados</p>
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
                              <span className="text-[10px] text-muted-foreground">Nenhum symbole</span>
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
                              <span className="text-[10px] text-muted-foreground">Nenhum symbole</span>
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
                        <Wand2 className="h-3 w-3 text-primary" /> Cliente detetado sur le plan
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
                            toast.success(data.duplicate ? "Ficha de cliente já existente — a abrir o orçamento" : "Ficha de cliente criada — a preparar o orçamento");
                            nav(`/devis-editeur?plan=${plan.plan_id}&client=${data.client_id}`);
                          } catch (e) {
                            toast.error(e?.response?.data?.detail || "Création impossível");
                          }
                        }}>
                        <Wand2 className="h-3 w-3" /> Criar client + devis
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
                            Verificar les superfícies écrites
                          </Button>
                          <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                  disabled={aiActionBusy} onClick={downloadEcartsPdf}
                                  data-testid="ecarts-pdf-btn">
                            <FileDown className="h-3.5 w-3.5" />
                            Relatório écarts (PDF)
                          </Button>
                          <Button size="sm" variant="outline" className="w-full justify-start gap-2 rounded-sm"
                                  disabled={aiActionBusy}
                                  onClick={() => setSendEcartsDialog(true)}
                                  data-testid="send-ecarts-btn">
                            <Mail className="h-3.5 w-3.5" />
                            Enviar au client
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
                                  {new Date(s.sent_at).toLocaleDateString("pt-PT")}{" "}
                                  {new Date(s.sent_at).toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}
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
                            {" "}({reconcile.matches.length} compartimento{reconcile.matches.length > 1 ? "s" : ""} comparée{reconcile.matches.length > 1 ? "s" : ""})
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
                              ✓ Calibration cohérente (écart ≤ 5%) — nenhum recalage nécessaire
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
                        <div className="flex justify-between"><span>Linéaire paredes total</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.linear_walls_m} ml</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.facade_walls_area_net_m2 != null && (
                        <div className="flex justify-between"><span>Façades (net)</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.facade_walls_area_net_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.interior_walls_area_m2 != null && (
                        <div className="flex justify-between"><span>Divisórias interiores</span>
                          <b className="num">{plan.ai_analysis.totals_gros_oeuvre.interior_walls_area_m2} m²</b></div>
                      )}
                      {plan.ai_analysis.totals_gros_oeuvre.openings_area_m2 != null && (
                        <div className="flex justify-between"><span>Aberturas</span>
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
                      <p className="overline mb-2">Compartimentos ({plan.ai_analysis.rooms.length})</p>
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

                  {/* --- DETALHE ABERTURAS --- */}
                  {plan.ai_analysis.openings?.details?.length > 0 && (
                    <div className="border border-border p-2 rounded-sm">
                      <p className="overline mb-2">Aberturas détaillées ({plan.ai_analysis.openings.details.length})</p>
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
                      <span>Total superfícies habitables</span>
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
                      Importer ces compartimentos dans le medição →
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
                  Nenhum historique — l'app enregistre automatiquement les modifications (calibration, compartimentos, niveaux).
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
                              {new Date(s.created_at).toLocaleString("pt-PT")} · {s.rooms?.length || 0} compartimentos
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
            <DialogTitle>Enviar o relatório d'écarts au client</DialogTitle>
            <DialogDescription>
              Le PDF de controlo des superfícies (mesurées vs écrites) sera joint à l'email.
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
                              title="Eliminar ce modelo"
                              data-testid={`msg-template-delete-${t.template_id}`}>
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <Textarea id="ecarts-message" rows={4}
                        placeholder="Olá, junto envio o relatório de controlo das superfícies do seu projeto…"
                        value={ecartsMessage} onChange={(e) => setEcartsMessage(e.target.value)}
                        data-testid="ecarts-message-input" className="rounded-sm" />
              {ecartsMessage.trim() && (
                <button onClick={saveMsgTemplate}
                        className="justify-self-start text-[11px] text-primary hover:text-orange-600 transition underline underline-offset-2"
                        data-testid="save-msg-template-btn">
                  + Guardar ce message comme modelo
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
              {sendingEcarts ? "Envoi…" : "Enviar o relatório"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CALIB DIALOG */}
      <Dialog open={calibDialog} onOpenChange={setCalibDialog}>
        <DialogContent className="rounded-sm" data-testid="calib-dialog">
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
            <Button variant="outline" onClick={() => { setCalibDialog(false); setPoints([]); }} className="rounded-sm">Cancelar</Button>
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
              Largura mesurée desde vos 2 clics. Ajustez le type et la altura ci-dessous.
              La surface sera automatiquement déduite des paredes nets.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid grid-cols-3 gap-2">
              {[["porte", "Porta"], ["fenetre", "Janela"], ["baie", "Vão de sacada"]].map(([k, l]) => (
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
                placeholder="Porta de entrada sul"
                className="rounded-sm h-10"
                data-testid="opening-label"
              />
            </div>
            <div className="text-xs text-muted-foreground border border-border rounded-sm p-2 bg-secondary/30">
              Superfície totale déduite : <b className="text-primary num">
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
            <DialogTitle>Nova compartimento</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-2">
              <Label>Nom</Label>
              <Input value={pendingRoomName} onChange={(e) => setPendingRoomName(e.target.value)}
                     data-testid="room-name-input" className="rounded-sm h-10" autoFocus />
            </div>
            <div className="grid gap-2">
              <Label>Altura sous plafond (m)</Label>
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
            <DialogTitle>Comparer les definições béton</DialogTitle>
            <DialogDescription>Medição du plan courant selon chaque type de chantier — pour aider au choix.</DialogDescription>
          </DialogHeader>
          {compareBusy && <p className="text-sm text-primary animate-pulse">Calcul en cours…</p>}
          {!compareBusy && compareData && (
            <table className="w-full text-xs" data-testid="beton-compare-table">
              <thead className="bg-muted/60"><tr>
                <th className="text-left px-2 py-1">Rubrica</th>
                {compareData.map((c) => <th key={c.name} className="text-right px-2 py-1">{c.name}</th>)}
              </tr></thead>
              <tbody>
                {[["Betão total", "beton_total_m3", "m³"], ["Aço", "acier_total_kg", "kg"],
                  ["Pilares (betão)", "beton_poteaux_m3", "m³"], ["Vigas (betão)", "beton_poutres_m3", "m³"],
                  ["Lajes (betão)", "beton_dalles_m3", "m³"], ["Paredes (betão)", "beton_voiles_m3", "m³"]].map(([lbl, k, u]) => (
                  <tr key={k} className="border-t border-border">
                    <td className="px-2 py-1 text-muted-foreground">{lbl}</td>
                    {compareData.map((c) => <td key={c.name} className="px-2 py-1 num text-right">{c.d?.[k] ?? 0} {u}</td>)}
                  </tr>
                ))}
                {(betonPriceM3 > 0 || acierPriceKg > 0) && (
                  <tr className="border-t border-border font-semibold">
                    <td className="px-2 py-1">Custo de material</td>
                    {compareData.map((c) => (
                      <td key={c.name} className="px-2 py-1 num text-right text-emerald-700">
                        {Math.round((c.d?.beton_total_m3 || 0) * (c.beton_price_m3 || betonPriceM3) + (c.d?.acier_total_kg || 0) * (c.acier_price_kg || acierPriceKg)).toLocaleString("pt-PT")} €
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
            <DialogTitle className="flex items-center gap-2"><Bot className="h-5 w-5 text-primary" /> Assistant IA — corriger le plan</DialogTitle>
            <DialogDescription>
              Décrivez ce que l'IA doit corriger ou adicionar. Ex : « il manque 2 poteaux en bas à droite »,
              « les semelles font 1,2×1,2 m », « ignore les traits de cote », « ajoute une poutre entre P3 et P4 ».
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-72 overflow-auto space-y-2 rounded-sm border border-border p-2 bg-muted/30" data-testid="ai-assistant-messages">
            {aiMessages.length === 0 && (
              <p className="text-xs text-muted-foreground">Nenhum échange pour l'instant. Donnez votre première instrução ci-dessous.</p>
            )}
            {aiMessages.map((m, i) => (
              <div key={i} className={`text-xs rounded-sm px-2 py-1.5 ${m.role === "user" ? "bg-primary/10 ml-6" : m.ok === false ? "bg-destructive/10 mr-6" : "bg-background border border-border mr-6"}`}>
                <span className="font-semibold">{m.role === "user" ? "Você" : "IA"} : </span>{m.text}
              </div>
            ))}
            {aiChatBusy && <p className="text-xs text-primary animate-pulse">L'IA análise le plan…</p>}
          </div>
          <div className="flex items-end gap-2">
            <Textarea value={aiInput} onChange={(e) => setAiInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAiInstruction(); } }}
                      placeholder="A sua instrução para a IA…" rows={2}
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
        onAttach3d={(png) => { setPlan3dSnapshot(png); toast.success("Vista 3D anexada — será adicionada ao próximo orçamento gerado a partir deste plano"); }}
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
  return { summary: parts.join(" · ") || "Sem alterações" };
}

