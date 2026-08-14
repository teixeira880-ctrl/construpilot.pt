import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { BrandingDialog } from "@/components/BrandingDialog";
import { useBilling } from "@/context/BillingContext";
import { Lock, Unlock } from "lucide-react";
import { QuoteDialog } from "@/components/planTakeoff/QuoteDialog";
import { Render3dDialog } from "@/components/planTakeoff/Render3dDialog";
import { EstimateDialog } from "@/components/planTakeoff/EstimateDialog";
import { MultiPlanDialog } from "@/components/planTakeoff/MultiPlanDialog";
import PcStudyDialog from "@/components/planTakeoff/PcStudyDialog";
import ObjectPanel from "@/components/planTakeoff/ObjectPanel";
import PresetPicker from "@/components/planTakeoff/PresetPicker";
import RoomEstimateDialog from "@/components/planTakeoff/RoomEstimateDialog";
import { LiveTotalBar } from "@/components/planTakeoff/LiveTotalBar";
import {
  Upload, Ruler, Square, Move, Trash2, RotateCw,
  ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight, Sparkles,
  MousePointer2, Layers, Undo2, Save, Home, Calculator, Search,
  Wand2, Zap, FileDown, History, Film, DoorOpen, Copy,
  Hash, StickyNote, Triangle, MountainSnow, X, Mail, Hexagon, Sheet, FileSearch,
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
import { TOOLS, CALIB_METHOD_LABELS, COUNTER_COLORS } from "@/components/planTakeoff/planConstants";


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
  const [showDimensionLines, setShowDimensionLines] = useState(true);
  // Iter 57 — QuoterPlan-like annotations (par page)
  const [annotations, setAnnotations] = useState({
    counters: [], notes: [], angles: [], pitched_surfaces: [],
  });
  const [activeCounterId, setActiveCounterId] = useState(null);
  const [pitchDegrees, setPitchDegrees] = useState(30);
  // Iter 58 (Vague B) — Volet Objets + Modèles Outils
  const [objectPanelOpen, setObjectPanelOpen] = useState(false);
  const [currentPreset, setCurrentPreset] = useState(null);
  // Iter 59 (Vague C) — Focus zoom + Devis pièce
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
  const [render3dHistory, setRender3dHistory] = useState([]);
  const [render3dMode, setRender3dMode] = useState("ai"); // ai | interactive | video
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
    const t = setTimeout(() => {
      api.patch(`/takeoffs/${plan.plan_id}/annotations`, {
        page_index: pageIndex, ...annotations,
      }).catch(() => { /* silent */ });
    }, 600);
    return () => clearTimeout(t);
  }, [annotations, plan?.plan_id, pageIndex, pageData]);

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

  const savePlanDefaults = async (next) => {
    if (!plan?.plan_id) return;
    try {
      await api.patch(`/takeoffs/${plan.plan_id}/defaults`, next);
      setPlanDefaults(next);
      toast.success(`Réglages : mur ${next.ceiling_h_m} m · plancher ${(next.floor_thickness_m * 100).toFixed(0)} cm`);
    } catch { toast.error("Sauvegarde impossible"); }
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
      toast.error(e?.response?.data?.detail || "Import impossible");
    } finally { setUploading(false); }
  };

  const onCanvasClick = (pt) => {
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
    if (!(dist > 0)) return toast.error("Distance invalide");
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
    const w = parseFloat(pendingOpening.width_m);
    const h = parseFloat(pendingOpening.height_m);
    if (!(w > 0) || !(h > 0)) return toast.error("Dimensions invalides");
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

  const finishPolyline = async (pts = points) => {
    if (pts.length < 2) return;
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polyline", points: pts,
      });
      toast.success(`Longueur : ${data.length_m} m`);
      setPoints([]);
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
      const base = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const res = await fetch(`${base}/api/takeoffs/${plan.plan_id}/export-xlsx`,
        { headers: { Authorization: `Bearer ${token}` }, credentials: "include" });
      if (!res.ok) throw new Error("Export impossible");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `metre-${plan.plan_id}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Export Excel téléchargé");
    } catch (e) { toast.error(e.message || "Export Excel impossible"); }
  };

  // Iter69 — Étude Permis de Construire (gros œuvre : béton, aciers, isobrique)
  const [pcDialog, setPcDialog] = useState(false);
  const [pcBusy, setPcBusy] = useState(false);
  const runPcStudy = async () => {
    setPcBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/pc-study`, {});
      await refreshPlan();
      toast.success(
        `Étude PC terminée — ${data.totals?.beton_m3 ?? 0} m³ béton · ${data.totals?.acier_kg ?? 0} kg aciers · ${data.totals?.ttc ?? 0} € TTC`,
        { duration: 8000 });
    } catch (e) { toast.error(e?.response?.data?.detail || "Étude PC impossible"); }
    finally { setPcBusy(false); }
  };
  const downloadPcFile = async (fmt) => {
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem("construpilot_token");
      const res = await fetch(`${base}/api/takeoffs/${plan.plan_id}/pc-study/${fmt}`,
        { headers: { Authorization: `Bearer ${token}` }, credentials: "include" });
      if (!res.ok) throw new Error("Export impossible");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `etude-pc-${plan.plan_id}.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
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
  const generateRoomEstimate = async (roomId) => {
    if (!plan?.plan_id) return;
    setEstimateLoading(true);
    try {
      const { data } = await api.post(
        `/takeoffs/${plan.plan_id}/rooms/${roomId}/estimate`,
        {}
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
        page_index: pageIndex, kind: "distance", points: pts.slice(0, 2),
      });
      toast.success(`Distance : ${data.value_m} m`);
      setPoints([]);
      await refreshPlan();
    } catch { toast.error("Mesure échouée"); }
  };

  const finishRoom = (pts = points) => {
    if (pts.length < 3) return toast.error("Une pièce nécessite au moins 3 points");
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    setPendingRoomName(`Pièce ${String(rooms.length + 1).padStart(2, "0")}`);
    setRoomDialog(true);
  };

  // Iter67 — mesure de surface libre (polygone) en m²
  const finishSurface = async (pts = points) => {
    if (pts.length < 3) return toast.error("Une surface nécessite au moins 3 points");
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polygon", points: pts,
      });
      toast.success(`Surface : ${data.area_m2} m² · périmètre ${data.perimeter_m} m`, { duration: 6000 });
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
      toast.success("Pièce enregistrée");
      setRoomDialog(false);
      setPoints([]);
      await refreshPlan();
      setTool(TOOLS.SELECT);
    } catch (e) { toast.error("Sauvegarde impossible"); }
  };

  const deleteRoom = async (rid) => {
    await api.delete(`/takeoffs/${plan.plan_id}/rooms/${rid}`);
    await refreshPlan();
    toast.success("Pièce supprimée");
  };

  const importAiRooms = async () => {
    const aiRooms = plan?.ai_analysis?.rooms || [];
    if (!aiRooms.length) return toast.error("Aucune pièce IA à importer");

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
          name: ai.name || `Pièce ${imported + 1}`,
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
        ? `${matchedCount} contour${matchedCount > 1 ? "s" : ""} détecté${matchedCount > 1 ? "s" : ""} par CV`
        : "carrés approximatifs — ajustez si besoin";
      toast.success(`${imported} pièces IA importées · ${detail}`, { duration: 6000 });
    }
    else toast.error("Aucune pièce importable (surfaces IA manquantes)");
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
          `Analyse IA — ${n} pièce${n > 1 ? "s" : ""} détectée${n > 1 ? "s" : ""}` +
          (surf ? ` · ${surf} m²` : ""),
          { duration: 6000 }
        );
      }
    } catch (e) { toast.error("Analyse IA impossible"); }
    finally { setAiBusy(false); }
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

  const detectWalls = async () => {
    if (!plan?.plan_id) return;
    setCvBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/detect-walls?page_index=${pageIndex}`);
      setDetectedWalls(data);
      setShowWalls(true);
      toast.success(
        `${data.segment_count} segments de murs détectés` +
        (data.filtered_cotes ? ` · ${data.filtered_cotes} traits de cote/textes ignorés` : "")
      );
      await loadWallsSummary();
    } catch (e) { toast.error("Détection murs impossible"); }
    finally { setCvBusy(false); }
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
    const { data } = await api.get(`/takeoffs/${plan.plan_id}/takeoff`);
    setTakeoff(data);
    const { data: m } = await api.post(`/takeoffs/${plan.plan_id}/materials`,
                                        { floor_material: floorMaterial });
    setMaterials(m);
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
      toast.success("Métré PDF téléchargé");
    } catch { toast.error("Export PDF impossible"); }
  };

  // Iter63 — Rapport PDF des écarts surfaces mesurées ↔ écrites
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
      a.href = url; a.download = `rapport-ecarts-${plan.plan_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
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
      await api.post(`/takeoffs/${plan.plan_id}/history/restore/${snapshotId}`);
      await refreshPlan();
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
    setEstimateBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/estimate-from-takeoff`, {
        project_type: estProjectType, finish_level: estFinishLevel,
      });
      setEstimateResult(data);
      // Si rénovation → coche automatiquement TVA
      if (data.is_renovation) setQuoteIncludeTva(true);
      toast.success(`Estimation générée : ${data.surface_m2} m² · ${data.estimation.total_avg?.toLocaleString("fr-FR")} €`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Estimation impossible");
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

  const runRender3d = async () => {
    if (!plan?.plan_id) return;
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
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Génération 3D échouée (réessayez)");
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
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Génération vidéo échouée (réessayez)");
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
      const { data } = await api.get(`/takeoffs/${plan.plan_id}/walls-summary`);
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
      setAllPlans(data.plans || data || []);
    } catch { /* ignore */ }
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
      toast.success(`Devis projet (${multiSelected.length} plans) téléchargé`);
      setMultiDialog(false);
    } catch (e) { toast.error(e.message || "Export impossible"); }
    finally { setMultiBusy(false); }
  };

  const createSignatureLink = async (logId) => {
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/quote-sends/${logId}/signature-link`);
      const fullUrl = data.url.startsWith("http") ? data.url
        : `${window.location.origin}${data.url}`;
      await navigator.clipboard.writeText(fullUrl);
      toast.success("Lien de signature copié dans le presse-papier");
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
              Plan 2D takeoff + Rendu 3D
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
      <div className="mx-auto max-w-[1100px] px-5 py-10 grid gap-8">
        <div>
          <p className="overline text-primary">ConstruPilot PLAN — Takeoff 2D</p>
          <h1 className="mt-3 font-display text-4xl lg:text-5xl font-bold tracking-tight">
            Importez votre plan. Mesurez automatiquement. Chiffrez.
          </h1>
          <p className="text-sm text-muted-foreground mt-3 max-w-2xl">
            PDF architecte, plan scanné, photo smartphone : ConstruPilot calibre l'échelle,
            extrait les mesures et bascule le tout dans l'estimation ou la recherche de prix.
          </p>
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
              {uploading ? "Import en cours…" : dragActive ? "Relâchez pour importer" : "Importer mon plan"}
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              PDF · DXF · JPG · PNG · WEBP — jusqu'à 20 Mo — drag & drop ou clic
            </p>
          </div>
          <Input
            id="plan-upload-input"
            type="file"
            accept="application/pdf,image/png,image/jpeg,image/webp,.dxf,.dwg"
            capture="environment"
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
            { icon: Ruler, title: "Formats variés", desc: "PDF · DXF · JPG · PNG · WEBP — DWG à convertir en DXF" },
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
                      toast.error("Impossible d'ouvrir ce plan");
                    }
                  }}
                  data-testid={`recent-plan-${p.plan_id}`}
                  className="text-left surface p-4 hover:border-primary transition-colors group"
                >
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
              ))}
            </div>
            {allPlans.length > 6 && (
              <p className="text-xs text-muted-foreground mt-3 text-center">
                + {allPlans.length - 6} autres — utilisez « Comparer 2 plans » pour tout voir
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
            {rooms.length} pièce{rooms.length > 1 ? "s" : ""}
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
            <Home className="h-4 w-4" /> Nouveau plan
          </Button>
          <Button variant="outline" onClick={duplicatePlan} data-testid="plan-duplicate-btn" className="rounded-sm gap-2"
                  title="Créer une copie de ce plan (pièces, ouvertures, calibrations)">
            <Copy className="h-4 w-4" /> Dupliquer
          </Button>
          <Button variant="outline" onClick={detectWalls} disabled={cvBusy} data-testid="plan-detect-walls-btn"
                  className="rounded-sm gap-2 border-cyan-500/50 text-cyan-500 hover:bg-cyan-500 hover:text-white">
            <Zap className={`h-4 w-4 ${cvBusy ? "animate-pulse" : ""}`} />
            {cvBusy ? "…" : "Détecter les murs"}
          </Button>
          <Button variant="outline" onClick={downloadPdf} data-testid="plan-pdf-export-btn"
                  className="rounded-sm gap-2">
            <FileDown className="h-4 w-4" /> Métré PDF
          </Button>
          <Button variant="outline" onClick={downloadXlsx} data-testid="plan-xlsx-export-btn"
                  className="rounded-sm gap-2">
            <Sheet className="h-4 w-4" /> Excel
          </Button>
          <Button variant="outline" onClick={() => setPcDialog(true)} data-testid="plan-pc-study-btn"
                  className="rounded-sm gap-2 border-emerald-500/60 text-emerald-600 hover:bg-emerald-500 hover:text-white">
            <FileSearch className="h-4 w-4" /> Étude PC
          </Button>
          <PcStudyDialog open={pcDialog} onClose={() => setPcDialog(false)}
                         study={plan?.pc_study || null} busy={pcBusy}
                         onRun={runPcStudy} onDownload={downloadPcFile}
                         onDownloadXlsx={downloadXlsx}
                         planId={plan?.plan_id} onSent={refreshPlan}
                         onCompareSuppliers={comparePcSuppliers} />
          <Button variant="outline"
                  onClick={() => { setEstimateDialog(true); setEstimateResult(null); }}
                  data-testid="plan-estimate-btn"
                  className="rounded-sm gap-2 border-primary/60 text-primary hover:bg-primary hover:text-white">
            <Sparkles className="h-4 w-4" /> Estimation
          </Button>
          <Button variant="outline"
                  onClick={() => { setRender3dDialog(true); setRender3dImg(null); setVideoUrl(null); loadRender3dHistory(); loadVideoHistory(); }}
                  data-testid="plan-render-3d-btn"
                  className="rounded-sm gap-2 border-primary/60 text-primary hover:bg-primary hover:text-white">
            <Sparkles className="h-4 w-4" /> Voir en 3D
          </Button>
          <Button variant="outline" onClick={() => { setQuoteDialog(true); loadTemplates(); loadQuoteSends(); loadVideoHistory(); }}
                  data-testid="plan-quote-pdf-btn"
                  className="rounded-sm gap-2 border-primary/60 text-primary hover:bg-primary hover:text-white">
            <FileDown className="h-4 w-4" /> Devis PDF
          </Button>
          <Button variant="outline" onClick={() => { setMultiDialog(true); loadAllPlans(); }}
                  data-testid="plan-multi-quote-btn"
                  className="rounded-sm gap-2">
            <FileDown className="h-4 w-4" /> Multi-plans
          </Button>
          <BrandingDialog />
          <Button onClick={runAI} disabled={aiBusy} data-testid="plan-ai-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Sparkles className={`h-4 w-4 ${aiBusy ? "animate-pulse" : ""}`} />
            {aiBusy ? "Analyse IA…" : "Analyse IA du plan"}
          </Button>
        </div>
      </div>

      {/* Réglages du plan — hauteur murs + épaisseur plancher */}
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
        <div className="surface p-3">
          {/* TOOLBAR */}
          <div className="flex flex-wrap gap-2 mb-3 pb-3 border-b border-border">
            <ToolButton icon={MousePointer2} label="Sélection" testId="tool-select" active={tool === TOOLS.SELECT} onClick={() => { setTool(TOOLS.SELECT); setPoints([]); }} />
            <ToolButton icon={Ruler} label="Calibrer" testId="tool-calibrate" active={tool === TOOLS.CALIB} onClick={() => { setTool(TOOLS.CALIB); setPoints([]); }} />
            <ToolButton icon={Move} label="Distance" testId="tool-distance" active={tool === TOOLS.DIST} onClick={() => { setTool(TOOLS.DIST); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Layers} label="Polyligne" testId="tool-polyline" active={tool === TOOLS.POLY} onClick={() => { setTool(TOOLS.POLY); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Hexagon} label="Surface" testId="tool-surface" active={tool === TOOLS.SURFACE} onClick={() => { setTool(TOOLS.SURFACE); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Square} label="Pièce" testId="tool-room" active={tool === TOOLS.ROOM} onClick={() => { setTool(TOOLS.ROOM); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Wand2} label="Auto-pièce" testId="tool-autoroom" active={tool === TOOLS.AUTOROOM} onClick={() => { setTool(TOOLS.AUTOROOM); setPoints([]); }} disabled={!currentCalib} />
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
            <Button size="sm" variant="ghost" onClick={() => setPoints(points.slice(0, -1))} disabled={!points.length} className="rounded-sm gap-1">
              <Undo2 className="h-3 w-3" /> Annuler
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
              title={locked ? "Déverrouiller (autoriser zoom + déplacement)"
                            : "Verrouiller le plan (bloquer zoom + déplacement pour des clics précis)"}
            >
              {locked ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
              {locked ? "Verrouillé" : "Verrouiller"}
            </Button>
            <Button
              size="sm"
              variant={objectPanelOpen ? "default" : "outline"}
              onClick={() => setObjectPanelOpen((o) => !o)}
              data-testid="tool-objects-panel"
              className={`rounded-sm gap-1 h-8 ${objectPanelOpen ? "bg-primary text-white hover:bg-orange-600" : ""}`}
              title="Ouvrir le Volet Objets (édition & jump-to)"
            >
              <Layers className="h-3 w-3" />
              Objets
            </Button>
          </div>

          {/* CANVAS */}
          <div className="relative">
          <PlanCanvas
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
            onCanvasDoubleClick={onCanvasDoubleClick}
            showDeltas={showDeltas}
            measurements={pageMeasurements}
          />

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
                  <Save className="h-3 w-3" /> Terminer polyligne
                </Button>
              )}
              {tool === TOOLS.SURFACE && points.length >= 3 && (
                <Button size="sm" onClick={() => finishSurface()} data-testid="tool-finish-surface" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Terminer surface
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
              <Button size="sm" variant="ghost" onClick={() => setPoints([])} className="rounded-sm">Annuler</Button>
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
            </div>
          )}
        </div>

        {/* RIGHT PANEL — Métré */}
        <div className="surface p-4 max-h-[80vh] overflow-auto">
          <Tabs value={rightTab} onValueChange={setRightTab}>
            <TabsList className="w-full rounded-sm">
              <TabsTrigger value="rooms" className="flex-1 rounded-sm" data-testid="tab-rooms">Pièces</TabsTrigger>
              <TabsTrigger value="materials" className="flex-1 rounded-sm" data-testid="tab-materials">Matériaux</TabsTrigger>
              <TabsTrigger value="ai" className="flex-1 rounded-sm" data-testid="tab-ai">IA</TabsTrigger>
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
              {!plan.ai_analysis && (
                <p className="text-xs text-muted-foreground">
                  Cliquez sur <b>Analyse IA du plan</b> en haut pour détecter automatiquement les pièces, ouvertures et surfaces écrites.
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

