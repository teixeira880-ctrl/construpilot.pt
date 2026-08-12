import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Upload, Ruler, Square, Move, Trash2, RotateCw,
  ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight, Sparkles,
  MousePointer2, Layers, Undo2, Save, Home, Calculator, Search,
  Wand2, Zap,
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

    // DETECTED WALLS overlay (Phase B)
    if (showWalls && detectedWalls?.segments?.length) {
      ctx.strokeStyle = "rgba(0, 200, 255, 0.85)";
      ctx.lineWidth = 3 / zoom;
      ctx.lineCap = "round";
      detectedWalls.segments.forEach((s) => {
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
    // CALIB visualization
    if (calibration) {
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
  const [takeoff, setTakeoff] = useState(null);
  const [materials, setMaterials] = useState(null);
  const [floorMaterial, setFloorMaterial] = useState("parquet");
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

  const runAI = async () => {
    setAiBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/analyze?page_index=${pageIndex}`);
      await refreshPlan();
      if (data.error) toast.warning("IA : " + data.error);
      else toast.success(`Analyse IA — ${data.rooms?.length || 0} pièces détectées`);
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
          className="surface p-16 grid place-items-center gap-4 cursor-pointer hover:border-primary transition-colors"
          data-testid="plan-upload-dropzone"
        >
          <div className="h-16 w-16 grid place-items-center bg-primary/10 rounded-sm">
            <Upload className="h-8 w-8 text-primary" />
          </div>
          <div className="text-center">
            <p className="font-display text-xl font-bold">
              {uploading ? "Import en cours…" : "Importer mon plan"}
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

        <div className="flex items-center gap-3 justify-center">
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
              <Button size="sm" variant={showWalls ? "default" : "outline"} onClick={() => setShowWalls(!showWalls)}
                      data-testid="toggle-walls-overlay"
                      className="rounded-sm gap-1 h-8">
                <Layers className="h-3 w-3" /> Murs ({detectedWalls.segment_count})
              </Button>
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
        </div>

        {/* RIGHT PANEL — Métré */}
        <div className="surface p-4 max-h-[80vh] overflow-auto">
          <Tabs defaultValue="rooms">
            <TabsList className="w-full rounded-sm">
              <TabsTrigger value="rooms" className="flex-1 rounded-sm" data-testid="tab-rooms">Pièces</TabsTrigger>
              <TabsTrigger value="materials" className="flex-1 rounded-sm" data-testid="tab-materials">Matériaux</TabsTrigger>
              <TabsTrigger value="ai" className="flex-1 rounded-sm" data-testid="tab-ai">IA</TabsTrigger>
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
