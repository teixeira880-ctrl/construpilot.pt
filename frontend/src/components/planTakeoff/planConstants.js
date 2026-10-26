// Constantes partagées du module Plan 2D (iter66 — découpage PlanTakeoff)

export const TOOLS = {
  SELECT: "select", DIST: "distance", POLY: "polyline",
  ROOM: "room", CALIB: "calibrate", AUTOROOM: "autoroom",
  OPENING: "opening", SURFACE: "surface",
  // Iter 57 — QuoterPlan-like tools
  COUNTER: "counter", NOTE: "note", ANGLE: "angle", PITCH: "pitch",
};

export const TOOL_LABELS = {
  select: "Seleção",
  calibrate: "Calibrar",
  distance: "Distância",
  polyline: "Perímetro",
  surface: "Superfície",
  room: "Divisão",
  autoroom: "Auto-divisão",
  opening: "Vão",
  counter: "Contador",
  note: "Nota",
  angle: "Ângulo",
  pitch: "Inclinação da cobertura",
};

export const CALIB_METHOD_LABELS = {
  auto_pdf_scale: "escala do PDF",
  two_points: "2 pontos",
  known_dimension: "cota conhecida",
  auto_cotes: "auto (cotas IA)",
  reconcile_surfaces: "reajustada (áreas escritas)",
  ai_scale_text: "escala escrita",
};

export const COUNTER_COLORS = [
  "#f97316", // orange
  "#22c55e", // green
  "#3b82f6", // blue
  "#a855f7", // purple
  "#ec4899", // pink
  "#eab308", // yellow
  "#06b6d4", // cyan
];

export const ROOM_COLORS = [
  "rgba(255,140,0,0.22)", "rgba(0,180,140,0.22)", "rgba(80,120,255,0.22)",
  "rgba(220,60,120,0.22)", "rgba(160,80,220,0.22)", "rgba(50,180,200,0.22)",
];

// Distance point → segment (espace image) — hit-test générique
export function pointSegDist(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  const l2 = dx * dx + dy * dy;
  if (l2 === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / l2));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}
