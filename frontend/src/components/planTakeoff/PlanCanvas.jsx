// PlanCanvas — canvas de dessin du Plan 2D (extrait de PlanTakeoff.jsx, iter66)
import { useEffect, useRef, useState, useCallback } from "react";
import { TOOLS, ROOM_COLORS, pointSegDist } from "./planConstants";

export default function PlanCanvas({
  pageData, tool, points, rooms, calibration, zoom, offset, rotation,
  onCanvasClick, onZoomChange, onOffsetChange, onAutoRotate,
  detectedWalls, showWalls, pixelsPerMeter, orthoSnap = true, locked = false,
  structure = null, showStructure = false, selectedStruct = null,
  onStructSelect = null, onStructDrag = null, onStructDragEnd = null,
  dimensionLines = [], showDimensionLines = false,
  annotations = { counters: [], notes: [], angles: [], pitched_surfaces: [] },
  measurements = [],
  activeCounterId = null,
  focusRequest = null,  // {px, py, ts} — quand ts change, centrer sur (px, py)
  selectedCoteIndex = null,
  onCoteClick = null,
  onCanvasDoubleClick = null,
  showDeltas = true,
}) {
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const dragRef = useRef(null);
  const movedRef = useRef(false);
  const structDragRef = useRef(null);
  const [hoverPoint, setHoverPoint] = useState(null);

  // Wall endpoint snap : magnetic attraction to detected wall endpoints (within 15px screen)
  const applyWallSnap = (x, y) => {
    if (!detectedWalls?.segments?.length) return null;
    const R = 15 / zoom;    // 15px screen radius, image-space adjusted
    let best = null, bestD = Infinity;
    for (const s of detectedWalls.segments) {
      for (const [ex, ey] of [[s.x1, s.y1], [s.x2, s.y2]]) {
        const d = Math.hypot(x - ex, y - ey);
        if (d < R && d < bestD) { best = [ex, ey]; bestD = d; }
      }
    }
    return best;
  };

  // Combined snap : wall endpoint first (magnetic), then ortho for continued draw
  const applySnap = (x, y) => {
    const wall = applyWallSnap(x, y);
    if (wall) return wall;
    return applyOrthoSnap(x, y);
  };

  // Ortho snap : if the segment from lastPoint to (x,y) is within 5° of horizontal/vertical,
  // snap to that axis so the user gets a perfectly straight measurement.
  const applyOrthoSnap = (x, y) => {
    if (!orthoSnap || points.length === 0) return [x, y];
    const [lx, ly] = points[points.length - 1];
    const dx = x - lx, dy = y - ly;
    const abs_dx = Math.abs(dx), abs_dy = Math.abs(dy);
    const ORTHO_DEG = 5;
    const TAN_TOL = Math.tan((ORTHO_DEG * Math.PI) / 180);
    if (abs_dx > 0 && abs_dy / abs_dx < TAN_TOL) return [x, ly]; // horizontal snap
    if (abs_dy > 0 && abs_dx / abs_dy < TAN_TOL) return [lx, y]; // vertical snap
    return [x, y];
  };

  // Charge l'image une fois par page + auto-rotation paysage si portrait
  useEffect(() => {
    if (!pageData?.image_png_b64) return;
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      // Auto-rotate 90° so plan displays in landscape when source is portrait
      if (onAutoRotate && img.height > img.width * 1.1) {
        onAutoRotate();
      }
      redraw();
    };
    img.src = `data:image/png;base64,${pageData.image_png_b64}`;
    // eslint-disable-next-line
  }, [pageData?.image_png_b64]);

  // Focus request (Vague C — zoom & centre sur un objet depuis le Volet Objets)
  useEffect(() => {
    if (!focusRequest || focusRequest.ts == null) return;
    const c = canvasRef.current;
    if (!c) return;
    const rect = c.getBoundingClientRect();
    const targetZoom = Math.max(1.0, Math.min(2.5, focusRequest.zoom ?? 1.5));
    const cx = focusRequest.px ?? 0;
    const cy = focusRequest.py ?? 0;
    // (px*zoom + offset.x) = rect.width/2 => offset.x = rect.width/2 - px*zoom
    const newOffset = {
      x: rect.width / 2 - cx * targetZoom,
      y: rect.height / 2 - cy * targetZoom,
    };
    onZoomChange(targetZoom);
    onOffsetChange(newOffset);
    // eslint-disable-next-line
  }, [focusRequest?.ts]);

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

    // STRUCTURE overlay (IA) — murs rouges + fenêtres jaunes + portes violettes
    if (showStructure && structure && (structure.walls?.length || structure.openings?.length || structure.floors?.length || structure.columns?.length)) {
      ctx.lineCap = "round";
      // Semelles / fondations (jaune)
      (structure.footings || []).forEach((f) => {
        const x0 = Math.min(f.x1, f.x2), y0 = Math.min(f.y1, f.y2);
        const w = Math.max(Math.abs(f.x2 - f.x1), 8 / zoom), h = Math.max(Math.abs(f.y2 - f.y1), 8 / zoom);
        ctx.fillStyle = "rgba(250,204,21,0.35)";
        ctx.fillRect(x0, y0, w, h);
        ctx.strokeStyle = "rgba(202,138,4,0.9)";
        ctx.lineWidth = 1.5 / zoom;
        ctx.strokeRect(x0, y0, w, h);
      });
      // Poteaux (plan de coffrage) — carrés pleins violets
      (structure.columns || []).forEach((c) => {
        const sel = selectedStruct?.type === "column" && selectedStruct?.id === c.column_id;
        const x0 = Math.min(c.x1, c.x2), y0 = Math.min(c.y1, c.y2);
        const w = Math.max(Math.abs(c.x2 - c.x1), 6 / zoom), h = Math.max(Math.abs(c.y2 - c.y1), 6 / zoom);
        ctx.fillStyle = "rgba(126,34,206,0.85)";
        if (sel) { ctx.shadowColor = "rgba(126,34,206,0.9)"; ctx.shadowBlur = 14 / zoom; }
        ctx.fillRect(x0, y0, w, h);
        ctx.shadowBlur = 0;
        ctx.strokeStyle = sel ? "rgba(255,255,255,1)" : "rgba(88,24,145,1)";
        ctx.lineWidth = (sel ? 2 : 1) / zoom;
        ctx.strokeRect(x0, y0, w, h);
        if (c.ref) {
          ctx.fillStyle = "rgba(88,24,145,1)";
          ctx.font = `bold ${Math.max(11, 13 / zoom)}px sans-serif`;
          ctx.fillText(c.ref, x0 + w + 3 / zoom, y0 + h);
        }
      });
      // Planchers (surfaces de sol) — remplissage translucide sous les murs
      (structure.floors || []).forEach((f) => {
        const pts = f.points || [];
        if (pts.length < 3) return;
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
        ctx.closePath();
        ctx.fillStyle = "rgba(16,185,129,0.12)";
        ctx.fill();
        ctx.strokeStyle = "rgba(16,185,129,0.5)";
        ctx.lineWidth = 1.2 / zoom;
        ctx.stroke();
      });
      (structure.walls || []).forEach((w) => {
        const sel = selectedStruct?.type === "wall" && selectedStruct?.id === w.wall_id;
        ctx.strokeStyle = w.type === "porteur" ? "rgba(220,38,38,0.95)" : "rgba(248,113,113,0.95)";
        ctx.lineWidth = (w.type === "porteur" ? 5 : 3) / zoom;
        if (sel) { ctx.shadowColor = "rgba(220,38,38,0.9)"; ctx.shadowBlur = 14 / zoom; }
        ctx.beginPath(); ctx.moveTo(w.x1, w.y1); ctx.lineTo(w.x2, w.y2); ctx.stroke();
        ctx.shadowBlur = 0;
        if (sel) {
          ctx.fillStyle = "rgba(255,255,255,1)";
          [[w.x1, w.y1], [w.x2, w.y2]].forEach(([hx, hy]) => {
            ctx.beginPath(); ctx.arc(hx, hy, 6 / zoom, 0, Math.PI * 2); ctx.fill();
            ctx.strokeStyle = "rgba(220,38,38,1)"; ctx.lineWidth = 2 / zoom; ctx.stroke();
          });
        }
      });
      (structure.openings || []).forEach((o) => {
        const sel = selectedStruct?.type === "opening" && selectedStruct?.id === o.opening_id;
        const isDoor = o.kind === "porte";
        ctx.strokeStyle = isDoor ? "rgba(168,85,247,0.95)" : "rgba(250,204,21,1)";
        ctx.lineWidth = 6 / zoom;
        if (sel) { ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = 14 / zoom; }
        ctx.beginPath(); ctx.moveTo(o.x1, o.y1); ctx.lineTo(o.x2, o.y2); ctx.stroke();
        ctx.shadowBlur = 0;
        // Battement de porte (ligne vers le point d'ouverture)
        if (isDoor && o.swing) {
          ctx.strokeStyle = "rgba(168,85,247,0.5)"; ctx.lineWidth = 2 / zoom;
          ctx.setLineDash([6 / zoom, 4 / zoom]);
          ctx.beginPath(); ctx.moveTo(o.x1, o.y1); ctx.lineTo(o.swing.x, o.swing.y); ctx.stroke();
          ctx.setLineDash([]);
        }
        if (sel) {
          ctx.fillStyle = "rgba(255,255,255,1)";
          [[o.x1, o.y1], [o.x2, o.y2]].forEach(([hx, hy]) => {
            ctx.beginPath(); ctx.arc(hx, hy, 6 / zoom, 0, Math.PI * 2); ctx.fill();
            ctx.strokeStyle = isDoor ? "rgba(168,85,247,1)" : "rgba(202,138,4,1)";
            ctx.lineWidth = 2 / zoom; ctx.stroke();
          });
        }
      });
      (structure.beams || []).forEach((b) => {
        const sel = selectedStruct?.type === "beam" && selectedStruct?.id === b.beam_id;
        ctx.strokeStyle = "rgba(99,40,150,0.95)";
        ctx.lineWidth = 4 / zoom;
        ctx.setLineDash([10 / zoom, 6 / zoom]);
        if (sel) { ctx.shadowColor = "rgba(99,40,150,0.9)"; ctx.shadowBlur = 14 / zoom; }
        ctx.beginPath(); ctx.moveTo(b.x1, b.y1); ctx.lineTo(b.x2, b.y2); ctx.stroke();
        ctx.setLineDash([]); ctx.shadowBlur = 0;
        if (b.ref) {
          ctx.fillStyle = "rgba(99,40,150,1)";
          ctx.font = `bold ${Math.max(10, 12 / zoom)}px sans-serif`;
          ctx.fillText(b.ref, (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2 - 4 / zoom);
        }
        if (sel) {
          ctx.fillStyle = "rgba(255,255,255,1)";
          [[b.x1, b.y1], [b.x2, b.y2]].forEach(([hx, hy]) => {
            ctx.beginPath(); ctx.arc(hx, hy, 6 / zoom, 0, Math.PI * 2); ctx.fill();
            ctx.strokeStyle = "rgba(99,40,150,1)"; ctx.lineWidth = 2 / zoom; ctx.stroke();
          });
        }
      });
    }

    // AI DIMENSION LINES OVERLAY (traits de cote détectés par l'IA)
    // Coordonnées normalisées 0-1 → converties dans l'espace image
    if (showDimensionLines && dimensionLines?.length && imgRef.current) {
      const W = imgRef.current.naturalWidth;
      const H = imgRef.current.naturalHeight;
      ctx.save();
      dimensionLines.forEach((d, di) => {
        const bb = d.bbox_norm;
        if (!Array.isArray(bb) || bb.length !== 4) return;
        const isSel = di === selectedCoteIndex;
        const x1 = bb[0] * W, y1 = bb[1] * H;
        const x2 = bb[2] * W, y2 = bb[3] * H;
        // Trait de cote — magenta (ambre en surbrillance quand sélectionné)
        ctx.strokeStyle = isSel ? "rgba(245, 158, 11, 1)" : "rgba(217, 70, 239, 0.9)";
        ctx.fillStyle = isSel ? "rgba(245, 158, 11, 1)" : "rgba(217, 70, 239, 0.95)";
        ctx.lineWidth = (isSel ? 4 : 2) / zoom;
        if (isSel) {
          ctx.shadowColor = "rgba(245, 158, 11, 0.9)";
          ctx.shadowBlur = 12 / zoom;
        }
        ctx.setLineDash(isSel ? [] : [8 / zoom, 4 / zoom]);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        ctx.setLineDash([]);
        // Tirets aux extrémités (comme une cote architecte)
        const tick = 6 / zoom;
        const dx = x2 - x1, dy = y2 - y1;
        const len = Math.hypot(dx, dy) || 1;
        const nx = -dy / len, ny = dx / len;
        [[x1, y1], [x2, y2]].forEach(([x, y]) => {
          ctx.beginPath();
          ctx.moveTo(x + nx * tick, y + ny * tick);
          ctx.lineTo(x - nx * tick, y - ny * tick);
          ctx.stroke();
        });
        // Étiquette valeur (si présente)
        if (d.value_m != null) {
          const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
          const label = `${Number(d.value_m).toFixed(2)} m`;
          ctx.font = `bold ${(isSel ? 15 : 13) / zoom}px system-ui`;
          const w = ctx.measureText(label).width + 10 / zoom;
          const h = (isSel ? 20 : 18) / zoom;
          ctx.fillStyle = isSel ? "rgba(245, 158, 11, 1)" : "rgba(217, 70, 239, 0.95)";
          ctx.fillRect(cx - w / 2, cy - h / 2, w, h);
          ctx.fillStyle = "#fff";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(label, cx, cy);
          ctx.textBaseline = "alphabetic";
        }
        ctx.shadowBlur = 0;
        ctx.shadowColor = "transparent";
      });
      ctx.restore();
    }

    // ROOMS overlays
    rooms.forEach((r, i) => {
      if (!r.points || r.points.length < 3) return;
      // Écarts surfaces (iter64) : ambre si écart mesuré↔écrit > 5 %, vert sinon
      const delta = showDeltas && r.surface_delta_pct != null ? r.surface_delta_pct : null;
      const deltaBad = delta != null && Math.abs(delta) > 5;
      ctx.beginPath();
      r.points.forEach((p, idx) => {
        idx === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]);
      });
      ctx.closePath();
      ctx.fillStyle = delta == null
        ? ROOM_COLORS[i % ROOM_COLORS.length]
        : deltaBad ? "rgba(245, 158, 11, 0.30)" : "rgba(34, 197, 94, 0.22)";
      ctx.fill();
      ctx.strokeStyle = delta == null
        ? "rgba(255,140,0,0.9)"
        : deltaBad ? "rgba(217, 119, 6, 0.95)" : "rgba(22, 163, 74, 0.9)";
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
      if (delta != null) {
        ctx.font = `bold ${11 / zoom}px system-ui`;
        ctx.fillStyle = deltaBad ? "#b45309" : "#15803d";
        ctx.fillText(
          `écrit ${r.surface_written_m2} m² (${delta > 0 ? "+" : ""}${delta}%)`,
          cx, cy + 32 / zoom
        );
      }
      // DÉDUCTIONS (iter68) — trémies/escaliers en pointillés rouges
      (r.deductions || []).forEach((d) => {
        const dp = d.points || [];
        if (dp.length < 3) return;
        ctx.beginPath();
        dp.forEach((p, idx) => (idx === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])));
        ctx.closePath();
        ctx.strokeStyle = "rgba(239, 68, 68, 0.9)";
        ctx.setLineDash([6 / zoom, 4 / zoom]);
        ctx.lineWidth = 1.5 / zoom;
        ctx.stroke();
        ctx.setLineDash([]);
        const dx = dp.reduce((s, p) => s + p[0], 0) / dp.length;
        const dy = dp.reduce((s, p) => s + p[1], 0) / dp.length;
        ctx.font = `bold ${11 / zoom}px system-ui`;
        ctx.fillStyle = "#dc2626";
        ctx.textAlign = "center";
        ctx.fillText(`− ${d.area_m2} m²`, dx, dy);
      });
    });

    // MESURES ENREGISTRÉES (iter65) — teal, gérées via le volet Objets
    (measurements || []).forEach((m) => {
      const pts = m.points || [];
      if (pts.length < 2) return;
      const isPoly = m.kind === "polygon";
      ctx.strokeStyle = "rgba(13, 148, 136, 0.95)";
      ctx.lineWidth = 2 / zoom;
      ctx.setLineDash([]);
      ctx.beginPath();
      pts.forEach((p, idx) => (idx === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])));
      if (isPoly) {
        ctx.closePath();
        ctx.fillStyle = "rgba(13, 148, 136, 0.16)";
        ctx.fill();
      }
      ctx.stroke();
      ctx.fillStyle = "rgba(13, 148, 136, 1)";
      pts.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p[0], p[1], 3 / zoom, 0, Math.PI * 2);
        ctx.fill();
      });
      let mx, my;
      if (isPoly) {
        mx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
        my = pts.reduce((s, p) => s + p[1], 0) / pts.length;
      } else {
        const midIdx = Math.floor((pts.length - 1) / 2);
        const [ax, ay] = pts[midIdx];
        const [bx, by] = pts[Math.min(midIdx + 1, pts.length - 1)];
        mx = (ax + bx) / 2; my = (ay + by) / 2;
      }
      const val = isPoly
        ? `${Number(m.area_m2 ?? 0).toFixed(2)} m²`
        : `${Number(m.value_m ?? m.length_m ?? 0).toFixed(2)} m`;
      const label = m.label ? `${m.label} · ${val}` : val;
      ctx.font = `bold ${12 / zoom}px system-ui`;
      const w = ctx.measureText(label).width + 8 / zoom;
      ctx.fillStyle = "rgba(13, 148, 136, 0.95)";
      ctx.fillRect(mx - w / 2, my - 9 / zoom, w, 18 / zoom);
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, mx, my);
      ctx.textBaseline = "alphabetic";
    });

    // ============ QUOTERPLAN-LIKE ANNOTATIONS ============

    // 1) PITCHED SURFACES (toitures avec facteur de pente)
    (annotations.pitched_surfaces || []).forEach((s) => {
      if (!s.points || s.points.length < 3) return;
      ctx.beginPath();
      s.points.forEach((p, idx) => {
        idx === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]);
      });
      ctx.closePath();
      ctx.fillStyle = "rgba(59, 130, 246, 0.18)";
      ctx.fill();
      ctx.strokeStyle = "rgba(59, 130, 246, 0.95)";
      ctx.lineWidth = 2 / zoom;
      ctx.setLineDash([6 / zoom, 4 / zoom]);
      ctx.stroke();
      ctx.setLineDash([]);
      const cx = s.points.reduce((a, p) => a + p[0], 0) / s.points.length;
      const cy = s.points.reduce((a, p) => a + p[1], 0) / s.points.length;
      const label = `${s.real_area_m2.toFixed(1)} m² · ${s.pitch_degrees}°`;
      ctx.font = `bold ${13 / zoom}px system-ui`;
      const w = ctx.measureText(label).width + 10 / zoom;
      ctx.fillStyle = "rgba(59, 130, 246, 0.95)";
      ctx.fillRect(cx - w / 2, cy - 9 / zoom, w, 18 / zoom);
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, cx, cy);
      ctx.textBaseline = "alphabetic";
    });

    // 2) COUNTERS (chaque compteur = liste de pastilles de couleur)
    (annotations.counters || []).forEach((c) => {
      const active = c.id === activeCounterId;
      (c.markers || []).forEach((m, idx) => {
        ctx.beginPath();
        ctx.arc(m.x, m.y, (active ? 8 : 6) / zoom, 0, Math.PI * 2);
        ctx.fillStyle = c.color;
        ctx.fill();
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2 / zoom;
        ctx.stroke();
        // Number badge on first marker only (compact)
        if (idx === 0 && c.markers.length > 1) {
          ctx.fillStyle = "#111";
          ctx.font = `bold ${11 / zoom}px system-ui`;
          ctx.textAlign = "left";
          ctx.fillText(`×${c.markers.length}`, m.x + 10 / zoom, m.y - 8 / zoom);
        }
      });
    });

    // 3) NOTES (post-it jaunes déplaçables)
    (annotations.notes || []).forEach((n) => {
      const pad = 6 / zoom;
      ctx.font = `${12 / zoom}px system-ui`;
      const txt = (n.text || "Note vide").slice(0, 60);
      const w = Math.max(ctx.measureText(txt).width + pad * 2, 40 / zoom);
      const h = 22 / zoom;
      // Yellow sticky
      ctx.fillStyle = "rgba(250, 204, 21, 0.95)";
      ctx.fillRect(n.x, n.y, w, h);
      ctx.strokeStyle = "rgba(202, 138, 4, 0.9)";
      ctx.lineWidth = 1 / zoom;
      ctx.strokeRect(n.x, n.y, w, h);
      ctx.fillStyle = "#111";
      ctx.textBaseline = "middle";
      ctx.fillText(txt, n.x + pad, n.y + h / 2);
      ctx.textBaseline = "alphabetic";
    });

    // 4) ANGLES (sommet + 2 branches + arc)
    (annotations.angles || []).forEach((a) => {
      ctx.strokeStyle = "rgba(168, 85, 247, 0.95)";
      ctx.fillStyle = "rgba(168, 85, 247, 0.95)";
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.moveTo(a.ax, a.ay);
      ctx.lineTo(a.vx, a.vy);
      ctx.lineTo(a.bx, a.by);
      ctx.stroke();
      // Arc between the two branches
      const arm1 = Math.atan2(a.ay - a.vy, a.ax - a.vx);
      const arm2 = Math.atan2(a.by - a.vy, a.bx - a.vx);
      ctx.beginPath();
      ctx.arc(a.vx, a.vy, 20 / zoom, arm1, arm2);
      ctx.stroke();
      // Label with degrees + x/12 for roof pitch reading
      const midAng = (arm1 + arm2) / 2;
      const lx = a.vx + Math.cos(midAng) * 40 / zoom;
      const ly = a.vy + Math.sin(midAng) * 40 / zoom;
      const deg = Number(a.degrees).toFixed(1);
      const rise = (Math.tan((a.degrees * Math.PI) / 180) * 12).toFixed(1);
      const label = `${deg}° · ${rise}/12`;
      ctx.font = `bold ${12 / zoom}px system-ui`;
      const w = ctx.measureText(label).width + 8 / zoom;
      ctx.fillStyle = "rgba(168, 85, 247, 0.95)";
      ctx.fillRect(lx - w / 2, ly - 9 / zoom, w, 18 / zoom);
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, lx, ly);
      ctx.textBaseline = "alphabetic";
    });

    // ACTIVE POINTS with QUOTERPLAN-style dimension lines
    const drawDimLine = (x1, y1, x2, y2, meters) => {
      const dx = x2 - x1, dy = y2 - y1;
      const len = Math.hypot(dx, dy);
      if (len < 0.5) return;
      const nx = -dy / len, ny = dx / len;
      const off = 14 / zoom;   // perpendicular offset for the dim line
      // Line
      ctx.strokeStyle = "hsl(24, 96%, 55%)";
      ctx.lineWidth = 1.5 / zoom;
      ctx.beginPath();
      ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      // Arrow heads
      const arr = 8 / zoom;
      const ang = Math.atan2(dy, dx);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x1 + arr * Math.cos(ang - Math.PI / 6), y1 + arr * Math.sin(ang - Math.PI / 6));
      ctx.moveTo(x1, y1);
      ctx.lineTo(x1 + arr * Math.cos(ang + Math.PI / 6), y1 + arr * Math.sin(ang + Math.PI / 6));
      ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - arr * Math.cos(ang - Math.PI / 6), y2 - arr * Math.sin(ang - Math.PI / 6));
      ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - arr * Math.cos(ang + Math.PI / 6), y2 - arr * Math.sin(ang + Math.PI / 6));
      ctx.stroke();
      // Mid label with background
      if (meters != null) {
        const mx = (x1 + x2) / 2 + nx * off;
        const my = (y1 + y2) / 2 + ny * off;
        const txt = `${meters.toFixed(2)} m`;
        ctx.font = `bold ${12 / zoom}px system-ui`;
        const w = ctx.measureText(txt).width + 8 / zoom;
        const h = 16 / zoom;
        ctx.fillStyle = "hsl(24, 96%, 55%)";
        ctx.fillRect(mx - w / 2, my - h / 2, w, h);
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(txt, mx, my);
        ctx.textBaseline = "alphabetic";
      }
    };

    if (points.length > 0) {
      const ppm = pixelsPerMeter || 0;
      // If we're drawing a distance/calib/polyline : render each segment with dim lines
      const showDimLines = tool === TOOLS.DIST || tool === TOOLS.CALIB || tool === TOOLS.POLY || tool === TOOLS.OPENING;
      ctx.strokeStyle = "hsl(24, 96%, 55%)";
      ctx.fillStyle = "hsl(24, 96%, 55%)";
      ctx.lineWidth = 2 / zoom;
      if (!showDimLines) {
        ctx.beginPath();
        points.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]));
        if (hoverPoint && tool !== TOOLS.SELECT) ctx.lineTo(hoverPoint[0], hoverPoint[1]);
        ctx.stroke();
      } else {
        // Segment-by-segment with dim lines
        for (let i = 1; i < points.length; i++) {
          const p1 = points[i - 1], p2 = points[i];
          const px = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
          drawDimLine(p1[0], p1[1], p2[0], p2[1], ppm ? px / ppm : null);
        }
        if (hoverPoint && points.length > 0) {
          const p1 = points[points.length - 1];
          const px = Math.hypot(hoverPoint[0] - p1[0], hoverPoint[1] - p1[1]);
          drawDimLine(p1[0], p1[1], hoverPoint[0], hoverPoint[1], ppm ? px / ppm : null);
        }
      }
      points.forEach((p) => {
        ctx.beginPath();
        ctx.arc(p[0], p[1], 4 / zoom, 0, Math.PI * 2);
        ctx.fill();
        // White ring around each anchor for legibility
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 1.5 / zoom;
        ctx.stroke();
        ctx.strokeStyle = "hsl(24, 96%, 55%)";
      });

      // LIVE AREA readout (QuoterPlan-like) — pour outils polygone/pièce/surface
      const isAreaTool = tool === TOOLS.ROOM || tool === TOOLS.POLY || tool === TOOLS.SURFACE;
      if (isAreaTool && ppm && points.length >= 2) {
        // Polygon area via Shoelace (using current points + hoverPoint as preview)
        const preview = hoverPoint && points.length >= 2 ? [...points, hoverPoint] : points;
        if (preview.length >= 3) {
          let sum = 0;
          for (let i = 0; i < preview.length; i++) {
            const [x1, y1] = preview[i];
            const [x2, y2] = preview[(i + 1) % preview.length];
            sum += x1 * y2 - x2 * y1;
          }
          const area_px2 = Math.abs(sum) / 2;
          const area_m2 = area_px2 / (ppm * ppm);
          // Compute centroid for label placement
          const cx = preview.reduce((s, p) => s + p[0], 0) / preview.length;
          const cy = preview.reduce((s, p) => s + p[1], 0) / preview.length;
          const txt = `${area_m2.toFixed(2)} m²`;
          ctx.font = `bold ${16 / zoom}px system-ui`;
          const w = ctx.measureText(txt).width + 14 / zoom;
          const h = 22 / zoom;
          ctx.fillStyle = "hsl(24, 96%, 55%)";
          ctx.fillRect(cx - w / 2, cy - h / 2, w, h);
          ctx.fillStyle = "#fff";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(txt, cx, cy);
          ctx.textBaseline = "alphabetic";
        }
      }
    }
    // CALIB visualization (only for manual 2-points calibration — auto_pdf_scale has no p1/p2)
    if (calibration?.p1 && calibration?.p2) {
      const dist_m = calibration.distance_m ||
        (pixelsPerMeter ? Math.hypot(
          calibration.p2[0] - calibration.p1[0],
          calibration.p2[1] - calibration.p1[1]
        ) / pixelsPerMeter : null);
      // Reuse the same drawDimLine helper for consistency
      const dx = calibration.p2[0] - calibration.p1[0];
      const dy = calibration.p2[1] - calibration.p1[1];
      const len = Math.hypot(dx, dy);
      if (len > 0.5) {
        const nx = -dy / len, ny = dx / len;
        const off = 14 / zoom;
        ctx.strokeStyle = "rgba(0,180,140,0.95)";
        ctx.lineWidth = 2 / zoom;
        ctx.beginPath();
        ctx.moveTo(calibration.p1[0], calibration.p1[1]);
        ctx.lineTo(calibration.p2[0], calibration.p2[1]);
        ctx.stroke();
        // Small perpendicular ticks at each end
        ctx.beginPath();
        [calibration.p1, calibration.p2].forEach((p) => {
          ctx.moveTo(p[0] - nx * 6 / zoom, p[1] - ny * 6 / zoom);
          ctx.lineTo(p[0] + nx * 6 / zoom, p[1] + ny * 6 / zoom);
        });
        ctx.stroke();
        if (dist_m != null) {
          const mx = (calibration.p1[0] + calibration.p2[0]) / 2 + nx * off;
          const my = (calibration.p1[1] + calibration.p2[1]) / 2 + ny * off;
          const txt = `${dist_m.toFixed(2)} m (calib.)`;
          ctx.font = `bold ${12 / zoom}px system-ui`;
          const w = ctx.measureText(txt).width + 8 / zoom;
          const h = 16 / zoom;
          ctx.fillStyle = "rgba(0,180,140,0.95)";
          ctx.fillRect(mx - w / 2, my - h / 2, w, h);
          ctx.fillStyle = "#fff";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(txt, mx, my);
          ctx.textBaseline = "alphabetic";
        }
      }
    }
    ctx.restore();

    // LÉGENDE ÉCARTS (iter65) — espace écran, coin bas-gauche
    if (showDeltas && rooms.some((r) => r.surface_delta_pct != null)) {
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const lx = 12, ly = c.height - 60;
      ctx.fillStyle = "rgba(15, 18, 25, 0.85)";
      ctx.fillRect(lx, ly, 214, 48);
      ctx.strokeStyle = "rgba(255,255,255,0.15)";
      ctx.lineWidth = 1;
      ctx.strokeRect(lx, ly, 214, 48);
      ctx.font = "600 11px system-ui";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "rgba(34, 197, 94, 0.9)";
      ctx.fillRect(lx + 10, ly + 9, 12, 12);
      ctx.fillStyle = "#e5e7eb";
      ctx.fillText("Conforme (écart ≤ 5 %)", lx + 28, ly + 15);
      ctx.fillStyle = "rgba(245, 158, 11, 0.95)";
      ctx.fillRect(lx + 10, ly + 27, 12, 12);
      ctx.fillStyle = "#e5e7eb";
      ctx.fillText("Écart mesuré ↔ écrit > 5 %", lx + 28, ly + 33);
      ctx.textBaseline = "alphabetic";
      ctx.restore();
    }
  }, [pageData, points, rooms, zoom, offset, rotation, hoverPoint, tool,
       calibration, detectedWalls, showWalls, pixelsPerMeter,
       dimensionLines, showDimensionLines, annotations, activeCounterId,
       selectedCoteIndex, showDeltas, measurements,
       structure, showStructure, selectedStruct]);

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
    if (tool === TOOLS.SELECT) {
      if (movedRef.current) return;
      const [rx, ry] = screenToImage(e.clientX, e.clientY);
      // Priorité à la structure IA (murs / ouvertures) quand elle est affichée
      if (showStructure && onStructSelect && structure) {
        const hit = hitStructItem(rx, ry);
        if (hit) { onStructSelect({ type: hit.type, id: hit.id }); return; }
        onStructSelect(null);
      }
      // Cotes IA cliquables : hit-test au clic (pas au drag)
      if (!onCoteClick) return;
      if (!showDimensionLines || !dimensionLines?.length || !imgRef.current) return;
      const W = imgRef.current.naturalWidth, H = imgRef.current.naturalHeight;
      const tol = 12 / zoom;
      let best = null, bestD = Infinity;
      dimensionLines.forEach((d, i) => {
        const bb = d.bbox_norm;
        if (!Array.isArray(bb) || bb.length !== 4) return;
        const dd = pointSegDist(rx, ry, bb[0] * W, bb[1] * H, bb[2] * W, bb[3] * H);
        if (dd < tol && dd < bestD) { best = i; bestD = dd; }
      });
      onCoteClick(best);
      return;
    }
    if (dragRef.current) return;
    const [rx, ry] = screenToImage(e.clientX, e.clientY);
    const [ix, iy] = applySnap(rx, ry);
    onCanvasClick([ix, iy]);
  };

  // Structure IA — hit-tests
  const _structItems = () => ([
    ...((structure?.walls || []).map((w) => ({ type: "wall", id: w.wall_id, x1: w.x1, y1: w.y1, x2: w.x2, y2: w.y2 }))),
    ...((structure?.openings || []).map((o) => ({ type: "opening", id: o.opening_id, x1: o.x1, y1: o.y1, x2: o.x2, y2: o.y2 }))),
    ...((structure?.beams || []).map((b) => ({ type: "beam", id: b.beam_id, x1: b.x1, y1: b.y1, x2: b.x2, y2: b.y2 }))),
    ...((structure?.columns || []).map((c) => ({ type: "column", id: c.column_id, x1: c.x1, y1: c.y1, x2: c.x2, y2: c.y2 }))),
  ]);
  const hitStructEndpoint = (rx, ry) => {
    const tol = 12 / zoom;
    for (const it of _structItems()) {
      if (Math.hypot(rx - it.x1, ry - it.y1) < tol) return { ...it, ep: 0 };
      if (Math.hypot(rx - it.x2, ry - it.y2) < tol) return { ...it, ep: 1 };
    }
    return null;
  };
  const hitStructItem = (rx, ry) => {
    const tol = 10 / zoom; let best = null, bestD = Infinity;
    for (const it of _structItems()) {
      const d = pointSegDist(rx, ry, it.x1, it.y1, it.x2, it.y2);
      if (d < tol && d < bestD) { best = it; bestD = d; }
    }
    return best;
  };

  const handleWheel = (e) => {
    if (locked) return;
    e.preventDefault();
    const delta = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    onZoomChange(Math.max(0.15, Math.min(6, zoom * delta)));
  };

  const handleMouseDown = (e) => {
    if (locked) return;
    // Glisser un point de la structure IA (murs/ouvertures) en mode Sélection
    if (tool === TOOLS.SELECT && showStructure && onStructDrag && structure && e.button === 0) {
      const [rx, ry] = screenToImage(e.clientX, e.clientY);
      const ep = hitStructEndpoint(rx, ry);
      if (ep) {
        structDragRef.current = ep;
        movedRef.current = false;
        if (onStructSelect) onStructSelect({ type: ep.type, id: ep.id });
        return;
      }
    }
    if (tool !== TOOLS.SELECT && e.button !== 1) return;
    movedRef.current = false;
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: offset.x, oy: offset.y };
  };
  const handleMouseMove = (e) => {
    if (structDragRef.current) {
      movedRef.current = true;
      const [rx, ry] = screenToImage(e.clientX, e.clientY);
      const s = structDragRef.current;
      onStructDrag(s.type, s.id, s.ep, [Math.round(rx), Math.round(ry)]);
      return;
    }
    if (dragRef.current) {
      if (Math.hypot(e.clientX - dragRef.current.sx, e.clientY - dragRef.current.sy) > 3) {
        movedRef.current = true;
      }
      onOffsetChange({ x: dragRef.current.ox + (e.clientX - dragRef.current.sx),
                       y: dragRef.current.oy + (e.clientY - dragRef.current.sy) });
      return;
    }
    if (tool !== TOOLS.SELECT) {
      const [rx, ry] = screenToImage(e.clientX, e.clientY);
      const [ix, iy] = applySnap(rx, ry);
      setHoverPoint([ix, iy]);
    }
  };
  const handleMouseLeave = () => { setHoverPoint(null); };
  const handleMouseUp = () => {
    if (structDragRef.current && onStructDragEnd) onStructDragEnd();
    dragRef.current = null; structDragRef.current = null;
  };

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

  // Double-clic gauche = terminer la mesure en cours (le clic suivant en reprend une nouvelle)
  const handleDoubleClick = (e) => {
    if (locked || tool === TOOLS.SELECT || !onCanvasDoubleClick) return;
    e.preventDefault();
    onCanvasDoubleClick();
  };

  return (
    <canvas
      ref={canvasRef}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => { handleMouseUp(); handleMouseLeave(); }}
      className={`w-full block bg-secondary/30 ${cursorClass} touch-none select-none`}
      style={{ minHeight: 500 }}
      data-testid="plan-canvas"
    />
  );
}
