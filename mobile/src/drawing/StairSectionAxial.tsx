import React from 'react';
import Svg, { Rect, Line, Path, Text as SvgText, G, Defs, Pattern } from 'react-native-svg';
import type { StairInput, StairResult } from '../types';
import { makeScale, tx, ty, len, fmtMm } from './scale';

/**
 * Coupe dans l'axe (coupe structurelle) — vue latérale de la volée béton
 * mettant en avant la paillasse inclinée, l'assise (attentes en pied),
 * l'appui haut sur la trémie et la disposition des aciers principaux.
 *
 * Différente de la "coupe longitudinale" architecturale : ici on ne dessine
 * pas les niveaux fini / trémie, on isole le squelette béton armé.
 */
interface Props {
  input: StairInput;
  result: StairResult;
  width: number;
  height: number;
}

const COLOR_STROKE = '#1A1D22';
const COLOR_DIM = '#5A6270';
const COLOR_MUTED = '#9AA1AC';
const COLOR_BG = '#FFFFFF';
const COLOR_CONCRETE = '#F5F6F8';
const COLOR_MAIN_STEEL = '#0B5FFF';
const COLOR_TOP_STEEL = '#D64545';
const COLOR_STIRRUP = '#2F8F55';

export function StairSectionAxial({ input, result, width, height }: Props) {
  const H = input.floor_height_mm;
  const g = result.tread_depth_mm;
  const h = result.riser_height_mm;
  const n = result.num_steps;
  const numTreads = result.num_treads;
  // Épaisseur paillasse : indicative L/25, borné à [140, 220]
  const paillasse = Math.max(140, Math.min(220, Math.round(result.stair_length_mm / 25 / 10) * 10));

  const stairRun = numTreads * g;
  const angle = (result.slope_deg * Math.PI) / 180;

  // Bounding box
  const minX = -300;
  const maxX = stairRun + 400;
  const minY = -paillasse - 200;
  const maxY = H + 300;
  const s = makeScale(minX, minY, maxX, maxY, width, height, 25);

  // Ligne de fibre inférieure de la paillasse : décalée de "paillasse" perpendiculairement
  const dx = paillasse * Math.sin(angle);
  const dy = paillasse * Math.cos(angle);

  return (
    <Svg width={width} height={height}>
      <Defs>
        <Pattern id="concreteA" patternUnits="userSpaceOnUse" width="5" height="5">
          <Line x1="0" y1="5" x2="5" y2="0" stroke={COLOR_MUTED} strokeWidth={0.3} />
        </Pattern>
      </Defs>
      <Rect x={0} y={0} width={width} height={height} fill={COLOR_BG} />

      {/* Appui bas (radier / fondation) */}
      <Rect
        x={tx(-250, s)} y={ty(-paillasse, s)}
        width={len(400, s)} height={len(paillasse, s)}
        fill={COLOR_CONCRETE} stroke={COLOR_STROKE} strokeWidth={1.2}
      />
      {/* Appui haut (dalle trémie) */}
      <Rect
        x={tx(stairRun - 100, s)} y={ty(H, s)}
        width={len(500, s)} height={len(paillasse, s)}
        fill={COLOR_CONCRETE} stroke={COLOR_STROKE} strokeWidth={1.2}
      />

      {/* Paillasse inclinée (rectangle en biais) */}
      {(() => {
        // 4 sommets
        const A = { x: 0, y: 0 };
        const B = { x: stairRun, y: H };
        const C = { x: stairRun + dx, y: H - dy };
        const D = { x: dx, y: -dy };
        return (
          <G>
            <Path
              d={`M ${tx(A.x, s)},${ty(A.y, s)} L ${tx(B.x, s)},${ty(B.y, s)} L ${tx(C.x, s)},${ty(C.y, s)} L ${tx(D.x, s)},${ty(D.y, s)} Z`}
              fill="url(#concreteA)" stroke={COLOR_STROKE} strokeWidth={1.4}
            />
          </G>
        );
      })()}

      {/* Marches sur la paillasse (profil dents-de-scie) */}
      {(() => {
        const path: string[] = [];
        path.push(`M ${tx(0, s)},${ty(0, s)}`);
        for (let i = 1; i <= n; i++) {
          const x = (i - 1) * g;
          const yLow = (i - 1) * h;
          const yHigh = i * h;
          path.push(`L ${tx(x, s)},${ty(yLow, s)}`);
          path.push(`L ${tx(x, s)},${ty(yHigh, s)}`);
          const xNext = i === n ? x : i * g;
          path.push(`L ${tx(xNext, s)},${ty(yHigh, s)}`);
        }
        return <Path d={path.join(' ')} stroke={COLOR_STROKE} strokeWidth={1.4} fill="none" />;
      })()}

      {/* Acier principal fibre inférieure (bleu, longitudinal) */}
      {(() => {
        // Ligne de la fibre inférieure décalée de ~30mm d'enrobage vers l'intérieur
        const cover = 30;
        const nx = Math.sin(angle);
        const ny = Math.cos(angle);
        const Ax = dx - cover * (-nx);
        const Ay = -dy - cover * ny;
        const Bx = stairRun + dx - cover * (-nx);
        const By = H - dy - cover * ny;
        // Attentes en pied (courbes de 20cm)
        return (
          <G>
            <Path
              d={`M ${tx(-100, s)},${ty(0, s)} L ${tx(-30, s)},${ty(-30, s)} L ${tx(Ax, s)},${ty(Ay, s)} L ${tx(Bx, s)},${ty(By, s)} L ${tx(Bx + 30, s)},${ty(By + 30, s)} L ${tx(Bx + 60, s)},${ty(By + 30, s)}`}
              stroke={COLOR_MAIN_STEEL} strokeWidth={2.2} fill="none"
            />
            <SvgText
              x={tx(stairRun / 2 + 40, s)} y={ty(H / 2 - 40, s)}
              fontSize="9" fill={COLOR_MAIN_STEEL} textAnchor="middle"
            >HA principaux (fibre inf.)</SvgText>
          </G>
        );
      })()}

      {/* Chapeaux (rouge) sur appui haut */}
      {(() => {
        const cover = 25;
        // Ligne au-dessus, courant sur 1/4 supérieur
        const L1 = { x: stairRun * 0.7, y: H * 0.7 };
        const L2 = { x: stairRun + 150, y: H };
        return (
          <G>
            <Path
              d={`M ${tx(L1.x, s)},${ty(L1.y + cover, s)} L ${tx(L2.x, s)},${ty(L2.y + cover, s)}`}
              stroke={COLOR_TOP_STEEL} strokeWidth={2} fill="none"
            />
            <SvgText
              x={tx((L1.x + L2.x) / 2, s)} y={ty(L2.y + cover + 30, s)}
              fontSize="9" fill={COLOR_TOP_STEEL} textAnchor="middle"
            >chapeaux appui haut</SvgText>
          </G>
        );
      })()}

      {/* Étriers/répartition (verts, transversaux — tirets courts sur la paillasse) */}
      {(() => {
        const arr: React.ReactNode[] = [];
        const N = 6;
        for (let i = 1; i <= N; i++) {
          const t = i / (N + 1);
          const px = t * stairRun;
          const py = t * H;
          const nx = -Math.sin(angle);
          const ny = Math.cos(angle);
          const a = { x: px + nx * 20, y: py + ny * 20 };
          const b = { x: px + nx * (paillasse - 20), y: py + ny * (paillasse - 20) };
          arr.push(
            <Line
              key={`stir${i}`}
              x1={tx(a.x, s)} y1={ty(a.y, s)}
              x2={tx(b.x, s)} y2={ty(b.y, s)}
              stroke={COLOR_STIRRUP} strokeWidth={0.8} strokeDasharray="3 2"
            />
          );
        }
        return <G>{arr}</G>;
      })()}

      {/* Cotes */}
      {/* Longueur paillasse (inclinée) - projetée horizontal */}
      {(() => {
        const y_c = ty(-paillasse - 60, s);
        return dimHoriz(tx(0, s), tx(stairRun, s), y_c, `L≈${fmtMm(result.stair_length_mm)}`, 11);
      })()}
      {/* Hauteur totale */}
      {dimVert(tx(-180, s), ty(0, s), ty(H, s), `H=${fmtMm(H)}`, 11)}
      {/* Épaisseur paillasse */}
      {(() => {
        // repère perpendiculaire à mi-parcours
        const mx = stairRun / 2;
        const my = H / 2;
        const nx = -Math.sin(angle);
        const ny = Math.cos(angle);
        const p1 = { x: mx + nx * 0, y: my + ny * 0 };
        const p2 = { x: mx + nx * paillasse, y: my + ny * paillasse };
        return (
          <G>
            <Line
              x1={tx(p1.x, s)} y1={ty(p1.y, s)}
              x2={tx(p2.x, s)} y2={ty(p2.y, s)}
              stroke={COLOR_DIM} strokeWidth={0.6}
            />
            <SvgText
              x={tx(p2.x + 8, s)} y={ty(p2.y - 4, s)}
              fontSize="9" fill={COLOR_DIM}
            >ép≈{fmtMm(paillasse)}</SvgText>
          </G>
        );
      })()}

      {/* Titre */}
      <SvgText x={tx(minX + 40, s)} y={ty(H + 100, s)} fontSize="9" fill={COLOR_DIM}>
        {"Coupe dans l'axe · vue béton armé indicative"}
      </SvgText>
    </Svg>
  );
}

function dimHoriz(x1: number, x2: number, y: number, label: string, fs = 11) {
  const DIM = '#5A6270';
  return (
    <G>
      <Line x1={x1} y1={y} x2={x2} y2={y} stroke={DIM} strokeWidth={0.6} />
      <Line x1={x1} y1={y - 4} x2={x1} y2={y + 4} stroke={DIM} strokeWidth={0.6} />
      <Line x1={x2} y1={y - 4} x2={x2} y2={y + 4} stroke={DIM} strokeWidth={0.6} />
      <SvgText x={(x1 + x2) / 2} y={y - 4} fontSize={fs} fill={DIM} textAnchor="middle">
        {label}
      </SvgText>
    </G>
  );
}
function dimVert(x: number, y1: number, y2: number, label: string, fs = 11) {
  const DIM = '#5A6270';
  return (
    <G>
      <Line x1={x} y1={y1} x2={x} y2={y2} stroke={DIM} strokeWidth={0.6} />
      <Line x1={x - 4} y1={y1} x2={x + 4} y2={y1} stroke={DIM} strokeWidth={0.6} />
      <Line x1={x - 4} y1={y2} x2={x + 4} y2={y2} stroke={DIM} strokeWidth={0.6} />
      <SvgText x={x - 6} y={(y1 + y2) / 2} fontSize={fs} fill={DIM} textAnchor="end">
        {label}
      </SvgText>
    </G>
  );
}
