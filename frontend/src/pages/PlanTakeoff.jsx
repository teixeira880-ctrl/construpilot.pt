import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { BrandingDialog } from "@/components/BrandingDialog";
import { QuoteDialog } from "@/components/planTakeoff/QuoteDialog";
import { Render3dDialog } from "@/components/planTakeoff/Render3dDialog";
import { EstimateDialog } from "@/components/planTakeoff/EstimateDialog";
import { MultiPlanDialog } from "@/components/planTakeoff/MultiPlanDialog";
import {
  Upload, Ruler, Square, Move, Trash2, RotateCw,
  ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight, Sparkles,
  MousePointer2, Layers, Undo2, Save, Home, Calculator, Search,
  Wand2, Zap, FileDown, History, Film,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api, eur, num } from "@/lib/api";

const TOOLS = {
  SELECT: "select", DIST: "distance", POLY: "polyline",
  ROOM: "room", CALIB: "calibrate", AUTOROOM: "autoroom",
};

const ROOM_COLORS = [
  "rgba(255,140,0,0.22)", "rgba(0,180,140,0.22)", "rgba(80,120,255,0.22)",
  "rgba(220,60,120,0.22)", "rgba(160,80,220,0.22)", "rgba(50,180,200,0.22)",
];

// ============ VIEWER / CANVAS ============

function PlanCanvas({
  pageData, tool, points, rooms, calibration, zoom, offset, rotation,
  onCanvasClick, onZoomChange, onOffsetChange, hoverPoint,
  detectedWalls, showWalls,
}) {
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const dragRef = useRef(null);

  // Charge l'image une fois par page
  useEffect(() => {
    if (!pageData?.image_png_b64) return;
    const img = new Image();
    img.onload = () => { imgRef.current = img; redraw(); };
    img.src = `data:image/png;base64,${pageData.image_png_b64}`;
    // eslint-disable-next-line
  }, [pageData?.image_png_b64]);

  const redraw = useCallback(() => {
    const c = canvasRef.current;
    if (!c || !imgRef.current) return;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.save();
    ctx.translate(c.width / 2 + offset.x, c.height / 2 + offset.y);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.scale(zoom, zoom);
    ctx.translate(-imgRef.current.width / 2, -imgRef.current.height / 2);
    ctx.drawImage(imgRef.current, 0, 0);

    // DETECTED WALLS overlay (Phase B) — coloration par type de mur
    if (showWalls && detectedWalls?.segments?.length) {
      const WALL_COLORS = {
        porteur:  "rgba(220, 38, 38, 0.9)",   // rouge
        cloison:  "rgba(255, 149, 0, 0.9)",   // orange
        doublage: "rgba(59, 130, 246, 0.9)",  // bleu
      };
      ctx.lineCap = "round";
      detectedWalls.segments.forEach((s) => {
        const t = s.wall_type || "cloison";
        ctx.strokeStyle = WALL_COLORS[t] || "rgba(0, 200, 255, 0.85)";
        // Épaisseur visuelle proportionnelle
        ctx.lineWidth = (t === "porteur" ? 5 : t === "cloison" ? 3 : 2) / zoom;
        ctx.beginPath();
        ctx.moveTo(s.x1, s.y1);
        ctx.lineTo(s.x2, s.y2);
        ctx.stroke();
      });
    }

    // ROOMS overlays
    rooms.forEach((r, i) => {
      if (!r.points || r.points.length < 3) return;
      ctx.beginPath();
      r.points.forEach((p, idx) => {
        idx === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]);
      });
      ctx.closePath();
      ctx.fillStyle = ROOM_COLORS[i % ROOM_COLORS.length];
      ctx.fill();
      ctx.strokeStyle = "rgba(255,140,0,0.9)";
      ctx.lineWidth = 2 / zoom;
      ctx.stroke();
      // label
      const cx = r.points.reduce((s, p) => s + p[0], 0) / r.points.length;
      const cy = r.points.reduce((s, p) => s + p[1], 0) / r.points.length;
      ctx.font = `bold ${14 / zoom}px system-ui`;
      ctx.fillStyle = "#111";
      ctx.textAlign = "center";
      ctx.fillText(r.name, cx, cy);
      ctx.font = `${12 / zoom}px system-ui`;
      ctx.fillText(`${r.surface_m2} m²`, cx, cy + 16 / zoom);
    });

    // ACTIVE POINTS
    if (points.length > 0) {
      ctx.strokeStyle = "hsl(24, 96%, 55%)";
      ctx.fillStyle = "hsl(24, 96%, 55%)";
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]));
      if (hoverPoint && tool !== TOOLS.SELECT) ctx.lineTo(hoverPoint[0], hoverPoint[1]);
      ctx.stroke();
      points.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p[0], p[1], 4 / zoom, 0, Math.PI * 2);
        ctx.fill();
      });
    }
    // CALIB visualization (only for manual 2-points calibration — auto_pdf_scale has no p1/p2)
    if (calibration?.p1 && calibration?.p2) {
      ctx.strokeStyle = "rgba(0,180,140,0.9)";
      ctx.lineWidth = 2 / zoom;
      ctx.setLineDash([6 / zoom, 4 / zoom]);
      ctx.beginPath();
      ctx.moveTo(calibration.p1[0], calibration.p1[1]);
      ctx.lineTo(calibration.p2[0], calibration.p2[1]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.restore();
  }, [pageData, points, rooms, zoom, offset, rotation, hoverPoint, tool, calibration, detectedWalls, showWalls]);

  useEffect(() => { redraw(); }, [redraw]);

  // Coordonnées → image (inverse transform)
  const screenToImage = (sx, sy) => {
    const c = canvasRef.current;
    if (!c || !imgRef.current) return [0, 0];
    const rect = c.getBoundingClientRect();
    const cx = sx - rect.left - c.width / 2 - offset.x;
    const cy = sy - rect.top - c.height / 2 - offset.y;
    const rad = (-rotation * Math.PI) / 180;
    const rx = cx * Math.cos(rad) - cy * Math.sin(rad);
    const ry = cx * Math.sin(rad) + cy * Math.cos(rad);
    return [rx / zoom + imgRef.current.width / 2, ry / zoom + imgRef.current.height / 2];
  };

  const handleClick = (e) => {
    if (tool === TOOLS.SELECT) return;
    if (dragRef.current) return;
    const [ix, iy] = screenToImage(e.clientX, e.clientY);
    onCanvasClick([ix, iy]);
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    onZoomChange(Math.max(0.15, Math.min(6, zoom * delta)));
  };

  const handleMouseDown = (e) => {
    if (tool !== TOOLS.SELECT && e.button !== 1) return;
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: offset.x, oy: offset.y };
  };
  const handleMouseMove = (e) => {
    if (dragRef.current) {
      onOffsetChange({ x: dragRef.current.ox + (e.clientX - dragRef.current.sx),
                       y: dragRef.current.oy + (e.clientY - dragRef.current.sy) });
    }
  };
  const handleMouseUp = () => { dragRef.current = null; };

  // Auto-size to container
  useEffect(() => {
    const resize = () => {
      const c = canvasRef.current;
      if (!c) return;
      const parent = c.parentElement;
      c.width = parent.clientWidth;
      c.height = Math.max(500, parent.clientHeight);
      redraw();
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [redraw]);

  const cursorClass =
    tool === TOOLS.SELECT ? "cursor-grab" : "cursor-crosshair";

  return (
    <canvas
      ref={canvasRef}
      onClick={handleClick}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      className={`w-full block bg-secondary/30 ${cursorClass} touch-none select-none`}
      style={{ minHeight: 500 }}
      data-testid="plan-canvas"
    />
  );
}

// ============ MAIN PAGE ============

export default function PlanTakeoff() {
  const nav = useNavigate();
  const [plan, setPlan] = useState(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageData, setPageData] = useState(null);
  const [tool, setTool] = useState(TOOLS.SELECT);
  const [points, setPoints] = useState([]);
  const [zoom, setZoom] = useState(0.5);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [calibDialog, setCalibDialog] = useState(false);
  const [calibDist, setCalibDist] = useState("");
  const [pendingRoomName, setPendingRoomName] = useState("");
  const [roomDialog, setRoomDialog] = useState(false);
  const [ceilingH, setCeilingH] = useState("2.5");
  const [aiBusy, setAiBusy] = useState(false);
  const [cvBusy, setCvBusy] = useState(false);
  const [detectedWalls, setDetectedWalls] = useState(null);
  const [showWalls, setShowWalls] = useState(true);
  const [deskewEnabled, setDeskewEnabled] = useState(false);
  const [rightTab, setRightTab] = useState("rooms");
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
  const rooms = useMemo(() => (plan?.rooms || []).filter((r) => r.page_index === pageIndex),
                        [plan, pageIndex]);

  // Load page image on demand
  useEffect(() => {
    if (!plan?.plan_id) return;
    api.get(`/takeoffs/${plan.plan_id}/page/${pageIndex}`).then(({ data }) => {
      setPageData(data);
      setPoints([]);
      setOffset({ x: 0, y: 0 });
      setZoom(0.5);
      setDetectedWalls(null);
    });
  }, [plan?.plan_id, pageIndex]);

  const refreshPlan = useCallback(async () => {
    if (!plan?.plan_id) return;
    const { data } = await api.get(`/takeoffs/${plan.plan_id}`);
    setPlan(data);
  }, [plan?.plan_id]);

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
    } else if (tool === TOOLS.POLY || tool === TOOLS.ROOM) {
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

  const finishPolyline = async () => {
    if (points.length < 2) return;
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "polyline", points,
      });
      toast.success(`Longueur : ${data.length_m} m`);
      setPoints([]);
    } catch (e) { toast.error("Mesure échouée"); }
  };

  const finishDistance = async () => {
    if (points.length !== 2) return;
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/measure`, {
        page_index: pageIndex, kind: "distance", points,
      });
      toast.success(`Distance : ${data.value_m} m`);
      setPoints([]);
    } catch { toast.error("Mesure échouée"); }
  };

  const finishRoom = () => {
    if (points.length < 3) return toast.error("Une pièce nécessite au moins 3 points");
    if (!currentCalib) return toast.error("Calibrez d'abord le plan");
    setPendingRoomName(`Pièce ${String(rooms.length + 1).padStart(2, "0")}`);
    setRoomDialog(true);
  };

  const saveRoom = async () => {
    try {
      await api.post(`/takeoffs/${plan.plan_id}/rooms`, {
        page_index: pageIndex, name: pendingRoomName,
        points, ceiling_height_m: parseFloat(ceilingH) || 2.5, openings: [],
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
          ceiling_h_m: 2.5,
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

  const detectWalls = async () => {
    if (!plan?.plan_id) return;
    setCvBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/detect-walls?page_index=${pageIndex}`);
      setDetectedWalls(data);
      setShowWalls(true);
      toast.success(`${data.segment_count} segments de murs détectés`);
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
              <Badge variant="outline" className="ml-3 num text-xs rounded-sm">
                {currentCalib.pixels_per_meter.toFixed(1)} px/m · {currentCalib.method}
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
          <Button variant="outline" onClick={detectWalls} disabled={cvBusy} data-testid="plan-detect-walls-btn"
                  className="rounded-sm gap-2 border-cyan-500/50 text-cyan-500 hover:bg-cyan-500 hover:text-white">
            <Zap className={`h-4 w-4 ${cvBusy ? "animate-pulse" : ""}`} />
            {cvBusy ? "…" : "Détecter les murs"}
          </Button>
          <Button variant="outline" onClick={downloadPdf} data-testid="plan-pdf-export-btn"
                  className="rounded-sm gap-2">
            <FileDown className="h-4 w-4" /> Métré PDF
          </Button>
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
            <ToolButton icon={Square} label="Pièce" testId="tool-room" active={tool === TOOLS.ROOM} onClick={() => { setTool(TOOLS.ROOM); setPoints([]); }} disabled={!currentCalib} />
            <ToolButton icon={Wand2} label="Auto-pièce" testId="tool-autoroom" active={tool === TOOLS.AUTOROOM} onClick={() => { setTool(TOOLS.AUTOROOM); setPoints([]); }} disabled={!currentCalib} />
            <div className="flex-1" />
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
            <Button size="sm" variant="ghost" onClick={() => setRotation((r) => (r + 90) % 360)} className="rounded-sm">
              <RotateCw className="h-3 w-3" />
            </Button>
          </div>

          {/* CANVAS */}
          <PlanCanvas
            pageData={pageData} tool={tool} points={points} rooms={rooms}
            calibration={currentCalib} zoom={zoom} offset={offset} rotation={rotation}
            onCanvasClick={onCanvasClick} onZoomChange={setZoom} onOffsetChange={setOffset}
            detectedWalls={detectedWalls} showWalls={showWalls}
          />

          {/* CONTEXT ACTIONS */}
          {points.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 items-center">
              <Badge variant="outline" className="rounded-sm num" data-testid="points-count">{points.length} point{points.length > 1 ? "s" : ""}</Badge>
              {tool === TOOLS.DIST && points.length === 2 && (
                <Button size="sm" onClick={finishDistance} data-testid="tool-finish-distance" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Mesurer
                </Button>
              )}
              {tool === TOOLS.POLY && points.length >= 2 && (
                <Button size="sm" onClick={finishPolyline} data-testid="tool-finish-polyline" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Terminer polyligne
                </Button>
              )}
              {tool === TOOLS.ROOM && points.length >= 3 && (
                <Button size="sm" onClick={finishRoom} data-testid="tool-finish-room" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Save className="h-3 w-3" /> Fermer pièce
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => setPoints([])} className="rounded-sm">Annuler</Button>
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
                  <div className="grid grid-cols-2 gap-2 mt-2 text-xs num">
                    <span>Surface</span><span className="text-right font-bold">{r.surface_m2} m²</span>
                    <span>Périmètre</span><span className="text-right">{r.perimeter_m} m</span>
                    <span>Murs bruts</span><span className="text-right">{r.wall_area_gross_m2} m²</span>
                    <span>Murs nets</span><span className="text-right">{r.wall_area_net_m2} m²</span>
                  </div>
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
                    <div className="flex gap-2">
                      <Badge variant="outline" className="rounded-sm">{plan.ai_analysis.plan_type}</Badge>
                      {plan.ai_analysis.quality && <Badge variant="outline" className="rounded-sm">{plan.ai_analysis.quality}</Badge>}
                      {plan.ai_analysis.detected_scale && <Badge variant="outline" className="rounded-sm num">{plan.ai_analysis.detected_scale}</Badge>}
                    </div>
                  )}
                  {(plan.ai_analysis.rooms || []).map((r, i) => (
                    <div key={i} className="border border-border p-2 rounded-sm flex justify-between">
                      <span>{r.name}</span>
                      <span className="num">{r.surface_written_m2 ? `${r.surface_written_m2} m²` : "—"}</span>
                    </div>
                  ))}
                  {plan.ai_analysis.total_surface_written_m2 && (
                    <div className="border-t border-border pt-2 flex justify-between font-bold">
                      <span>Total surfaces écrites</span>
                      <span className="num text-primary">{plan.ai_analysis.total_surface_written_m2} m²</span>
                    </div>
                  )}
                  {(plan.ai_analysis.warnings || []).length > 0 && (
                    <div className="text-amber-500 text-xs">
                      ⚠ {plan.ai_analysis.warnings.join(" · ")}
                    </div>
                  )}
                  {(plan.ai_analysis.rooms || []).some((r) => r.surface_written_m2) && (
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

