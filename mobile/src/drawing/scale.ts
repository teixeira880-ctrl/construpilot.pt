/**
 * Helpers pour dessiner à l'échelle : convertit des mm en pixels SVG,
 * calcule les marges, positionnement des cotes, etc.
 */

export interface Scale {
  minX: number; minY: number;
  scale: number;                    // px per mm
  offsetX: number; offsetY: number; // in mm space
  width: number; height: number;
}

export function makeScale(
  bboxMinX: number,
  bboxMinY: number,
  bboxMaxX: number,
  bboxMaxY: number,
  svgWidth: number,
  svgHeight: number,
  margin = 40
): Scale {
  const w = bboxMaxX - bboxMinX;
  const h = bboxMaxY - bboxMinY;
  const availW = svgWidth - 2 * margin;
  const availH = svgHeight - 2 * margin;
  const sx = availW / Math.max(1, w);
  const sy = availH / Math.max(1, h);
  const scale = Math.min(sx, sy);
  const drawW = w * scale;
  const drawH = h * scale;
  const offsetX = (svgWidth - drawW) / 2;
  const offsetY = (svgHeight - drawH) / 2;
  return {
    minX: bboxMinX, minY: bboxMinY,
    scale,
    offsetX, offsetY,
    width: svgWidth, height: svgHeight,
  };
}

export function tx(x: number, s: Scale): number {
  return s.offsetX + (x - s.minX) * s.scale;
}

export function ty(y: number, s: Scale, flipY = true): number {
  // par défaut, Y augmente vers le haut en dessin technique → on inverse pour SVG
  if (flipY) return s.height - (s.offsetY + (y - s.minY) * s.scale);
  return s.offsetY + (y - s.minY) * s.scale;
}

export function len(mm: number, s: Scale): number {
  return mm * s.scale;
}

export function fmtMm(v: number): string {
  return `${Math.round(v)}`;
}
