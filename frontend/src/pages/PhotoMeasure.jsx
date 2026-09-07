import { useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";
import {
  Ruler, Camera, Images, Trash2, RotateCcw, Square, Move, CheckCircle2, Info, FileText,
} from "lucide-react";

// A4 : 210 mm x 297 mm
const A4 = { long: 297, short: 210 };

function fmtLen(mm) {
  if (mm >= 1000) return `${(mm / 1000).toFixed(2)} m`;
  return `${(mm / 10).toFixed(1)} cm`;
}
function fmtArea(mm2) {
  const m2 = mm2 / 1e6;
  if (m2 >= 0.1) return `${m2.toFixed(2)} m²`;
  return `${(mm2 / 100).toFixed(0)} cm²`;
}
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
function polyArea(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const j = (i + 1) % pts.length;
    s += pts[i].x * pts[j].y - pts[j].x * pts[i].y;
  }
  return Math.abs(s) / 2;
}
function centroid(pts) {
  const x = pts.reduce((a, p) => a + p.x, 0) / pts.length;
  const y = pts.reduce((a, p) => a + p.y, 0) / pts.length;
  return { x, y };
}

export default function PhotoMeasure() {
  const [imgSrc, setImgSrc] = useState(null);
  const [dims, setDims] = useState({ w: 0, h: 0 });
  const [mmPerPx, setMmPerPx] = useState(null);
  const [a4Edge, setA4Edge] = useState("long");
  const [mode, setMode] = useState("calibrate"); // calibrate | distance | area
  const [pending, setPending] = useState([]); // points en cours (coords natives)
  const [measures, setMeasures] = useState([]); // {type, pts, valueMm|valueMm2}
  const svgRef = useRef(null);
  const nav = useNavigate();

  // Envoie les mesures relevées vers l'éditeur de devis (réutilise le mécanisme "ouvrages en attente")
  const sendToQuote = () => {
    if (!measures.length) return;
    const lines = measures.map((m, i) => (
      m.type === "distance"
        ? { designation: `Mesure photo — longueur ${i + 1}`, unit: "ml",
            qty: Number((m.value / 1000).toFixed(2)) || 0, unit_price_ht: 0, category: "Mesure photo" }
        : { designation: `Mesure photo — surface ${i + 1}`, unit: "m²",
            qty: Number((m.value / 1e6).toFixed(2)) || 0, unit_price_ht: 0, category: "Mesure photo" }
    ));
    sessionStorage.setItem("construpilot_pending_ouvrages", JSON.stringify(lines));
    toast.success(`${lines.length} mesure(s) envoyée(s) vers le devis`);
    nav("/devis-editeur");
  };

  const loadFile = (file) => {
    if (!file || !file.type.startsWith("image/")) { toast.error("Choisissez une image (photo)"); return; }
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => {
      setDims({ w: im.naturalWidth, h: im.naturalHeight });
      setImgSrc(url);
      setMmPerPx(null);
      setPending([]);
      setMeasures([]);
      setMode("calibrate");
    };
    im.onerror = () => toast.error("Image illisible");
    im.src = url;
  };

  const toNative = useCallback((evt) => {
    const rect = svgRef.current.getBoundingClientRect();
    const cx = (evt.clientX - rect.left) / rect.width * dims.w;
    const cy = (evt.clientY - rect.top) / rect.height * dims.h;
    return { x: Math.max(0, Math.min(dims.w, cx)), y: Math.max(0, Math.min(dims.h, cy)) };
  }, [dims]);

  const onSvgClick = (evt) => {
    if (!imgSrc) return;
    const p = toNative(evt);
    if (mode === "calibrate") {
      const next = [...pending, p].slice(-2);
      setPending(next);
      if (next.length === 2) {
        const px = dist(next[0], next[1]);
        if (px < 4) { toast.error("Trait trop court — recommencez sur le bord de la feuille"); setPending([]); return; }
        const scale = A4[a4Edge] / px;
        setMmPerPx(scale);
        setPending([]);
        setMode("distance");
        toast.success("Échelle calibrée — vous pouvez mesurer");
      }
      return;
    }
    if (!mmPerPx) { toast.error("Calibra primeiro com a folha A4"); return; }
    if (mode === "distance") {
      const next = [...pending, p];
      if (next.length === 2) {
        if (dist(next[0], next[1]) < 4) { toast.error("Trait trop court — cliquez 2 points distincts"); setPending([]); return; }
        const mm = dist(next[0], next[1]) * mmPerPx;
        setMeasures((m) => [...m, { type: "distance", pts: next, value: mm }]);
        setPending([]);
      } else {
        setPending(next);
      }
      return;
    }
    if (mode === "area") {
      setPending((prev) => [...prev, p]);
    }
  };

  const closePolygon = () => {
    if (pending.length < 3) { toast.error("Cliquez au moins 3 points pour une surface"); return; }
    const area = polyArea(pending) * mmPerPx * mmPerPx;
    setMeasures((m) => [...m, { type: "area", pts: pending, value: area }]);
    setPending([]);
  };

  const resetAll = () => { setPending([]); setMeasures([]); setMmPerPx(null); setMode("calibrate"); };
  const fs = dims.w ? Math.max(dims.w, dims.h) / 55 : 14;
  const r = dims.w ? Math.max(dims.w, dims.h) / 220 : 4;

  return (
    <div className="max-w-5xl mx-auto p-4 space-y-4" data-testid="photo-measure-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Ruler className="h-6 w-6 text-primary" /> Mesurer sur photo
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Posez une feuille <b>A4</b> (21 × 29,7 cm) dans le plan à mesurer (mur ou sol), prenez la photo,
          puis calibrez l'échelle sur un bord de la feuille. Vous pourrez ensuite mesurer distances et surfaces.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <input type="file" accept="image/*" className="hidden" id="pm-gallery"
               onChange={(e) => { loadFile(e.target.files?.[0]); e.target.value = ""; }}
               data-testid="pm-gallery-input" />
        <Button variant="outline" className="gap-2" onClick={() => document.getElementById("pm-gallery").click()}
                data-testid="pm-gallery-btn">
          <Images className="h-4 w-4" /> Galerie
        </Button>
        <input type="file" accept="image/*" capture="environment" className="hidden" id="pm-cam"
               onChange={(e) => { loadFile(e.target.files?.[0]); e.target.value = ""; }}
               data-testid="pm-cam-input" />
        <Button variant="outline" className="gap-2" onClick={() => document.getElementById("pm-cam").click()}
                data-testid="pm-cam-btn">
          <Camera className="h-4 w-4" /> Prendre une photo
        </Button>
        {imgSrc && (
          <Button variant="ghost" className="gap-2 text-muted-foreground" onClick={resetAll} data-testid="pm-reset-btn">
            <RotateCcw className="h-4 w-4" /> Réinitialiser
          </Button>
        )}
      </div>

      {imgSrc && (
        <Card className="p-3 space-y-3">
          {/* Barre d'outils étape */}
          <div className="flex flex-wrap items-center gap-2">
            {mode === "calibrate" && (
              <>
                <span className="text-sm font-semibold">1. Calibrer sur le bord :</span>
                <div className="flex rounded-md overflow-hidden border border-border">
                  <button onClick={() => setA4Edge("long")}
                          className={`px-3 py-1.5 text-sm ${a4Edge === "long" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                          data-testid="pm-edge-long">Grand côté 29,7 cm</button>
                  <button onClick={() => setA4Edge("short")}
                          className={`px-3 py-1.5 text-sm ${a4Edge === "short" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                          data-testid="pm-edge-short">Petit côté 21 cm</button>
                </div>
                <span className="text-xs text-muted-foreground flex items-center gap-1">
                  <Info className="h-3.5 w-3.5" /> Cliquez les 2 coins de ce bord sur la feuille.
                </span>
              </>
            )}
            {mmPerPx && (
              <>
                <span className="flex items-center gap-1 text-sm text-primary font-semibold" data-testid="pm-calibrated">
                  <CheckCircle2 className="h-4 w-4" /> Calibré
                </span>
                <div className="flex rounded-md overflow-hidden border border-border ml-2">
                  <button onClick={() => { setMode("distance"); setPending([]); }}
                          className={`px-3 py-1.5 text-sm flex items-center gap-1 ${mode === "distance" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                          data-testid="pm-mode-distance"><Move className="h-3.5 w-3.5" /> Distance</button>
                  <button onClick={() => { setMode("area"); setPending([]); }}
                          className={`px-3 py-1.5 text-sm flex items-center gap-1 ${mode === "area" ? "bg-primary text-primary-foreground" : "bg-background"}`}
                          data-testid="pm-mode-area"><Square className="h-3.5 w-3.5" /> Surface</button>
                </div>
                <button onClick={() => { setMode("calibrate"); setPending([]); setMmPerPx(null); }}
                        className="text-xs text-muted-foreground underline ml-1" data-testid="pm-recalibrate">
                  Recalibrer
                </button>
                {mode === "area" && (
                  <Button size="sm" className="ml-1" onClick={closePolygon} data-testid="pm-close-polygon">
                    Terminar a área
                  </Button>
                )}
              </>
            )}
          </div>

          {/* Image + overlay SVG */}
          <div className="relative w-full select-none" style={{ touchAction: "none" }}>
            <img src={imgSrc} alt="photo à mesurer" className="w-full h-auto rounded-md block" draggable={false} />
            <svg ref={svgRef} viewBox={`0 0 ${dims.w} ${dims.h}`}
                 onClick={onSvgClick}
                 className="absolute inset-0 w-full h-full cursor-crosshair"
                 data-testid="pm-svg">
              {/* Calibration en cours */}
              {mode === "calibrate" && pending.map((p, i) => (
                <circle key={`c${i}`} cx={p.x} cy={p.y} r={r} fill="#F59E0B" />
              ))}
              {/* Mesures finalisées */}
              {measures.map((m, i) => {
                if (m.type === "distance") {
                  const [a, b] = m.pts;
                  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
                  return (
                    <g key={`m${i}`}>
                      <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#3F7D54" strokeWidth={r * 0.7} />
                      <circle cx={a.x} cy={a.y} r={r} fill="#3F7D54" />
                      <circle cx={b.x} cy={b.y} r={r} fill="#3F7D54" />
                      <text x={mid.x} y={mid.y - r * 2} fontSize={fs} fill="#0A0D14"
                            stroke="#fff" strokeWidth={fs / 6} paintOrder="stroke"
                            textAnchor="middle" fontWeight="700">{fmtLen(m.value)}</text>
                    </g>
                  );
                }
                const c = centroid(m.pts);
                const path = m.pts.map((p, k) => `${k === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ") + " Z";
                return (
                  <g key={`m${i}`}>
                    <path d={path} fill="rgba(63,125,84,0.22)" stroke="#3F7D54" strokeWidth={r * 0.7} />
                    {m.pts.map((p, k) => <circle key={k} cx={p.x} cy={p.y} r={r} fill="#3F7D54" />)}
                    <text x={c.x} y={c.y} fontSize={fs} fill="#0A0D14" stroke="#fff" strokeWidth={fs / 6}
                          paintOrder="stroke" textAnchor="middle" fontWeight="700">{fmtArea(m.value)}</text>
                  </g>
                );
              })}
              {/* Pending distance/area */}
              {(mode === "distance" || mode === "area") && pending.length > 0 && (
                <g>
                  {mode === "area" && pending.length > 1 && (
                    <polyline points={pending.map((p) => `${p.x},${p.y}`).join(" ")}
                              fill="none" stroke="#F59E0B" strokeWidth={r * 0.7} strokeDasharray={`${r * 2},${r * 2}`} />
                  )}
                  {mode === "distance" && pending.length === 1 && null}
                  {pending.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={r} fill="#F59E0B" />)}
                </g>
              )}
            </svg>
          </div>

          {/* Résultats */}
          {measures.length > 0 && (
            <div className="space-y-1" data-testid="pm-results">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">Résultats</p>
                <Button size="sm" className="gap-2" onClick={sendToQuote} data-testid="pm-to-quote-btn">
                  <FileText className="h-4 w-4" /> Ajouter au devis
                </Button>
              </div>
              {measures.map((m, i) => (
                <div key={i} className="flex items-center justify-between text-sm border border-border rounded-sm px-3 py-1.5"
                     data-testid={`pm-result-${i}`}>
                  <span className="flex items-center gap-2">
                    {m.type === "distance" ? <Move className="h-3.5 w-3.5 text-primary" /> : <Square className="h-3.5 w-3.5 text-primary" />}
                    {m.type === "distance" ? "Distance" : "Surface"}
                  </span>
                  <span className="font-semibold">{m.type === "distance" ? fmtLen(m.value) : fmtArea(m.value)}</span>
                  <button onClick={() => setMeasures((arr) => arr.filter((_, j) => j !== i))}
                          className="text-muted-foreground hover:text-destructive" data-testid={`pm-result-del-${i}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {!imgSrc && (
        <Card className="p-8 text-center" data-testid="pm-empty-guide">
          <p className="text-sm font-semibold mb-4">Comment bien préparer votre photo</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-8">
            {/* Repère visuel A4 (proportions 210 × 297) */}
            <div className="relative">
              <div className="mx-auto border-2 border-dashed border-primary rounded-md bg-primary/5 flex items-center justify-center"
                   style={{ width: 105, height: 148 }} data-testid="pm-a4-frame">
                <span className="text-[11px] font-semibold text-primary text-center leading-tight">
                  Feuille A4<br />21 × 29,7 cm
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">Posez-la à plat dans le plan à mesurer</p>
            </div>
            <ol className="text-left text-sm text-muted-foreground space-y-2 max-w-xs list-decimal list-inside">
              <li>Placez une feuille <b>A4</b> sur le mur ou le sol à mesurer.</li>
              <li>Prenez la photo <b>bien en face</b>, sans angle, feuille entièrement visible.</li>
              <li>Calibra a escala clicando nos 2 cantos de uma extremidade da folha.</li>
              <li>Mesurez ensuite distances et surfaces.</li>
            </ol>
          </div>
          <p className="text-xs text-muted-foreground mt-6 flex items-center justify-center gap-1">
            <Info className="h-3.5 w-3.5" /> Plus la feuille est prise de face, plus la mesure est précise.
          </p>
        </Card>
      )}
    </div>
  );
}
