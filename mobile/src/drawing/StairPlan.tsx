import React from 'react';
import Svg, { Line, Rect, Path, Text as SvgText, G, Polygon } from 'react-native-svg';
import type { StairResult, StairType, StairInput, QuarterTurnInput, HalfTurnInput } from '../types';
import { makeScale, tx, ty, len, fmtMm } from './scale';

interface PlanProps {
  type: StairType;
  input: StairInput | QuarterTurnInput | HalfTurnInput;
  result: StairResult;
  width: number;
  height: number;
}

const COLOR_STROKE = '#1A1D22';
const COLOR_LIGHT = '#9AA1AC';
const COLOR_DIM = '#5A6270';
const COLOR_BG = '#FFFFFF';
const COLOR_FLOOR = '#F5F6F8';
const COLOR_WALKLINE = '#0B5FFF';
const COLOR_TEXT = '#1A1D22';

/**
 * Vue en plan (top-down) — 4 types d'escalier.
 * Convention : X = longueur horizontale (mm), Y = largeur (mm).
 * Origine (0,0) = coin bas-gauche de l'emprise.
 */
export function StairPlan({ type, input, result, width, height }: PlanProps) {
  const g = input.stair_width_mm;
  const tread = result.tread_depth_mm;
  const riser = result.riser_height_mm;
  const numTreads = result.num_treads;

  if (type === 'straight') {
    return renderStraightPlan(input, result, width, height);
  } else if (type === 'quarter-turn-bottom') {
    return renderQTBottomPlan(input as QuarterTurnInput, result, width, height);
  } else if (type === 'quarter-turn-top') {
    return renderQTTopPlan(input as QuarterTurnInput, result, width, height);
  } else if (type === 'helicoidal') {
    return renderHelicoidalPlan(input as any, result, width, height);
  } else {
    return renderHalfTurnPlan(input as HalfTurnInput, result, width, height);
  }
}

// -------------- HELICOIDAL --------------
function renderHelicoidalPlan(inp: any, r: StairResult, W: number, H: number) {
  const inner = inp.inner_radius_mm ?? 150;
  const outer = inp.outer_radius_mm ?? 750;
  const sweep = inp.sweep_angle_deg ?? 360;
  const n = r.num_treads || r.num_steps;
  const walkline = Math.min((inp.walkline_offset_mm ?? 500) + inner, outer - 30);
  const cx = W / 2;
  const cy = H / 2;
  const s = Math.min((W - 60) / (2 * outer), (H - 60) / (2 * outer));
  const rInner = inner * s;
  const rOuter = outer * s;
  const rWalk = walkline * s;

  const anglePer = sweep / n;
  const wedges: React.ReactNode[] = [];
  for (let i = 0; i < n; i++) {
    const a1 = (i * anglePer - 90) * Math.PI / 180;  // start at top
    const a2 = ((i + 1) * anglePer - 90) * Math.PI / 180;
    const x1i = cx + rInner * Math.cos(a1);
    const y1i = cy + rInner * Math.sin(a1);
    const x1o = cx + rOuter * Math.cos(a1);
    const y1o = cy + rOuter * Math.sin(a1);
    const x2i = cx + rInner * Math.cos(a2);
    const y2i = cy + rInner * Math.sin(a2);
    const x2o = cx + rOuter * Math.cos(a2);
    const y2o = cy + rOuter * Math.sin(a2);
    const large = anglePer > 180 ? 1 : 0;
    const path = `M ${x1i},${y1i} L ${x1o},${y1o} A ${rOuter},${rOuter} 0 ${large} 1 ${x2o},${y2o} L ${x2i},${y2i} A ${rInner},${rInner} 0 ${large} 0 ${x1i},${y1i} Z`;
    wedges.push(
      <Path key={i} d={path} stroke={COLOR_STROKE} strokeWidth={0.8}
        fill={i % 2 === 0 ? '#FFFFFF' : '#F5F6F8'} />
    );
    // Numéro sur la ligne de foulée
    const midA = (a1 + a2) / 2;
    wedges.push(
      <SvgText key={`t${i}`}
        x={cx + rWalk * Math.cos(midA)}
        y={cy + rWalk * Math.sin(midA) + 3}
        fontSize="9" fill={COLOR_DIM} textAnchor="middle"
      >{i + 1}</SvgText>
    );
  }

  return (
    <Svg width={W} height={H}>
      <Rect x={0} y={0} width={W} height={H} fill={COLOR_BG} />
      {wedges}
      {/* Fût central */}
      <Path d={`M ${cx + rInner},${cy} A ${rInner},${rInner} 0 1 1 ${cx - rInner},${cy} A ${rInner},${rInner} 0 1 1 ${cx + rInner},${cy}`}
        fill="#D6D9DE" stroke={COLOR_STROKE} strokeWidth={1.2} />
      {/* Ligne de foulée */}
      <Path d={`M ${cx + rWalk},${cy} A ${rWalk},${rWalk} 0 1 1 ${cx - rWalk},${cy} A ${rWalk},${rWalk} 0 1 1 ${cx + rWalk},${cy}`}
        stroke={COLOR_WALKLINE} strokeWidth={0.8} strokeDasharray="3 3" fill="none" />
      {/* Cotes */}
      <SvgText x={cx} y={H - 12} fontSize="10" fill={COLOR_DIM} textAnchor="middle">
        ⌀ext {2 * outer}mm · ⌀int {2 * inner}mm · {sweep}° · {anglePer.toFixed(1)}°/marche
      </SvgText>
      <SvgText x={cx} y={20} fontSize="10" fill={COLOR_WALKLINE} textAnchor="middle" fontWeight="bold">
        MONTÉE {inp.direction === 'ccw' ? '↺' : '↻'}
      </SvgText>
    </Svg>
  );
}

// -------------- STRAIGHT --------------
function renderStraightPlan(inp: StairInput, r: StairResult, W: number, H: number) {
  const g = inp.stair_width_mm;
  const tread = r.tread_depth_mm;
  const totalLen = r.stair_run_mm;
  const bboxW = totalLen + 600;
  const bboxH = g + 500;
  const s = makeScale(-300, -250, totalLen + 300, g + 250, W, H, 30);

  const treads = r.treads;

  return (
    <Svg width={W} height={H}>
      <Rect x={0} y={0} width={W} height={H} fill={COLOR_BG} />
      {/* Contour trémie si donnée */}
      {inp.stairwell_length_mm && inp.stairwell_width_mm && (() => {
        const swL = inp.stairwell_length_mm;
        const swW = inp.stairwell_width_mm;
        const xEnd = totalLen;
        const xStart = xEnd - swL;
        const yStart = (g - swW) / 2;
        return (
          <Rect
            x={tx(xStart, s)} y={ty(yStart + swW, s)}
            width={len(swL, s)} height={len(swW, s)}
            stroke={COLOR_LIGHT} strokeWidth={1.5} strokeDasharray="6 4"
            fill="none"
          />
        );
      })()}

      {/* Contour escalier */}
      <Rect
        x={tx(0, s)} y={ty(g, s)}
        width={len(totalLen, s)} height={len(g, s)}
        stroke={COLOR_STROKE} strokeWidth={1.5} fill={COLOR_BG}
      />

      {/* Marches */}
      {treads.map((t, i) => {
        const x1 = i * tread;
        return (
          <G key={t.index}>
            <Line
              x1={tx(x1, s)} y1={ty(0, s)}
              x2={tx(x1, s)} y2={ty(g, s)}
              stroke={COLOR_STROKE} strokeWidth={1}
            />
            <SvgText
              x={tx(x1 + tread / 2, s)} y={ty(g / 2, s) + 4}
              fontSize="10" fill={COLOR_DIM} textAnchor="middle"
            >
              {t.index}
            </SvgText>
          </G>
        );
      })}
      {/* Contremarche fin de volée */}
      <Line
        x1={tx(totalLen, s)} y1={ty(0, s)}
        x2={tx(totalLen, s)} y2={ty(g, s)}
        stroke={COLOR_STROKE} strokeWidth={2}
      />

      {/* Ligne de foulée */}
      <Line
        x1={tx(0, s)} y1={ty(g / 2, s)}
        x2={tx(totalLen, s)} y2={ty(g / 2, s)}
        stroke={COLOR_WALKLINE} strokeWidth={0.8} strokeDasharray="3 3"
      />
      {/* Flèche MONTÉE */}
      <G>
        <Line
          x1={tx(50, s)} y1={ty(g / 2, s)}
          x2={tx(totalLen - 50, s)} y2={ty(g / 2, s)}
          stroke={COLOR_WALKLINE} strokeWidth={1.5}
        />
        <Polygon
          points={`${tx(totalLen - 50, s)},${ty(g / 2, s)} ${tx(totalLen - 90, s)},${ty(g / 2 - 30, s)} ${tx(totalLen - 90, s)},${ty(g / 2 + 30, s)}`}
          fill={COLOR_WALKLINE}
        />
        <SvgText
          x={tx(totalLen / 2, s)} y={ty(g / 2, s) - 8}
          fontSize="9" fill={COLOR_WALKLINE} textAnchor="middle"
          fontWeight="bold"
        >
          MONTÉE
        </SvgText>
      </G>

      {/* Cote longueur totale (en bas) */}
      {dimHorizontal(tx(0, s), tx(totalLen, s), ty(-80, s), fmtMm(totalLen), s)}
      {/* Cote largeur (à droite) */}
      {dimVertical(tx(totalLen + 80, s), ty(0, s), ty(g, s), fmtMm(g), s)}
      {/* Cote giron marche 1 */}
      {dimHorizontal(tx(0, s), tx(tread, s), ty(-30, s), `g=${fmtMm(tread)}`, s, 10)}

      {/* Repère niveaux */}
      <SvgText x={tx(0, s)} y={ty(-120, s)} fontSize="10" fill={COLOR_TEXT} textAnchor="start">
        0.00
      </SvgText>
      <SvgText x={tx(totalLen, s)} y={ty(-120, s)} fontSize="10" fill={COLOR_TEXT} textAnchor="end">
        +{fmtMm(inp.floor_height_mm)}
      </SvgText>
    </Svg>
  );
}

// -------------- QT BOTTOM --------------
function renderQTBottomPlan(inp: QuarterTurnInput, r: StairResult, W: number, H: number) {
  const sw = inp.stair_width_mm;
  const balancing = inp.balancing || 'balanced';
  const treads = r.treads;
  const winders = treads.filter((t) => t.type === 'winder');
  const straights = treads.filter((t) => t.type === 'straight');
  const numStraight = straights.length;
  const tread = r.tread_depth_mm;

  // Emprise : carré du quart tournant en bas-gauche (sw × sw),
  // puis volée droite qui part à droite sur numStraight * tread.
  const totalLen = sw + numStraight * tread;
  const totalWid = sw;
  const s = makeScale(-300, -300, totalLen + 300, totalWid + 300, W, H, 30);

  return (
    <Svg width={W} height={H}>
      <Rect x={0} y={0} width={W} height={H} fill={COLOR_BG} />

      {/* Emprise globale */}
      <Rect
        x={tx(0, s)} y={ty(sw, s)}
        width={len(totalLen, s)} height={len(sw, s)}
        stroke={COLOR_STROKE} strokeWidth={1.5} fill="none"
      />

      {/* Zone quart tournant */}
      <Rect
        x={tx(0, s)} y={ty(sw, s)}
        width={len(sw, s)} height={len(sw, s)}
        stroke={COLOR_LIGHT} strokeWidth={1} fill={COLOR_FLOOR}
      />

      {balancing === 'balanced' ? (
        <G>{drawWinders(winders, 0, 0, sw, s, 'bottom')}</G>
      ) : (
        <SvgText
          x={tx(sw / 2, s)} y={ty(sw / 2, s)}
          fontSize="10" fill={COLOR_DIM} textAnchor="middle"
        >
          PALIER
        </SvgText>
      )}

      {/* Marches droites après le tour */}
      {straights.map((t, i) => (
        <G key={t.index}>
          <Line
            x1={tx(sw + i * tread, s)} y1={ty(0, s)}
            x2={tx(sw + i * tread, s)} y2={ty(sw, s)}
            stroke={COLOR_STROKE} strokeWidth={1}
          />
          <SvgText
            x={tx(sw + i * tread + tread / 2, s)} y={ty(sw / 2, s) + 4}
            fontSize="9" fill={COLOR_DIM} textAnchor="middle"
          >
            {t.index}
          </SvgText>
        </G>
      ))}
      <Line
        x1={tx(totalLen, s)} y1={ty(0, s)}
        x2={tx(totalLen, s)} y2={ty(sw, s)}
        stroke={COLOR_STROKE} strokeWidth={2}
      />

      {/* Ligne de foulée */}
      <Path
        d={`M ${tx(inp.walkline_offset_mm || 500, s)},${ty(0, s)} L ${tx(inp.walkline_offset_mm || 500, s)},${ty(sw / 2, s)} L ${tx(totalLen, s)},${ty(sw / 2, s)}`}
        stroke={COLOR_WALKLINE} strokeWidth={0.8} strokeDasharray="3 3" fill="none"
      />

      {/* Flèche montée */}
      <SvgText
        x={tx(sw + numStraight * tread / 2, s)} y={ty(sw / 2, s) - 8}
        fontSize="9" fill={COLOR_WALKLINE} textAnchor="middle" fontWeight="bold"
      >
        MONTÉE →
      </SvgText>

      {/* Cotes */}
      {dimHorizontal(tx(0, s), tx(totalLen, s), ty(-100, s), fmtMm(totalLen), s)}
      {dimVertical(tx(totalLen + 100, s), ty(0, s), ty(sw, s), fmtMm(sw), s)}
      {dimHorizontal(tx(sw, s), tx(sw + tread, s), ty(-30, s), `g=${fmtMm(tread)}`, s, 10)}

      <SvgText x={tx(0, s)} y={ty(-180, s)} fontSize="10" fill={COLOR_TEXT}>0.00</SvgText>
      <SvgText x={tx(totalLen, s)} y={ty(-180, s)} fontSize="10" fill={COLOR_TEXT} textAnchor="end">
        +{fmtMm(inp.floor_height_mm)}
      </SvgText>
    </Svg>
  );
}

// -------------- QT TOP --------------
function renderQTTopPlan(inp: QuarterTurnInput, r: StairResult, W: number, H: number) {
  const sw = inp.stair_width_mm;
  const balancing = inp.balancing || 'balanced';
  const treads = r.treads;
  const winders = treads.filter((t) => t.type === 'winder');
  const numStraight = treads.filter((t) => t.type === 'straight').length -
    (balancing === 'straight' ? 1 : 0); // exclude palier de fin
  const tread = r.tread_depth_mm;

  const totalLen = numStraight * tread + sw;
  const totalWid = sw;
  const s = makeScale(-300, -300, totalLen + 300, totalWid + 300, W, H, 30);

  return (
    <Svg width={W} height={H}>
      <Rect x={0} y={0} width={W} height={H} fill={COLOR_BG} />
      <Rect x={tx(0, s)} y={ty(sw, s)} width={len(totalLen, s)} height={len(sw, s)}
        stroke={COLOR_STROKE} strokeWidth={1.5} fill="none" />

      {/* Volée droite au début */}
      {Array.from({ length: numStraight }).map((_, i) => (
        <G key={i}>
          <Line
            x1={tx(i * tread, s)} y1={ty(0, s)}
            x2={tx(i * tread, s)} y2={ty(sw, s)}
            stroke={COLOR_STROKE} strokeWidth={1}
          />
          <SvgText
            x={tx(i * tread + tread / 2, s)} y={ty(sw / 2, s) + 4}
            fontSize="9" fill={COLOR_DIM} textAnchor="middle"
          >
            {i + 1}
          </SvgText>
        </G>
      ))}
      <Line
        x1={tx(numStraight * tread, s)} y1={ty(0, s)}
        x2={tx(numStraight * tread, s)} y2={ty(sw, s)}
        stroke={COLOR_STROKE} strokeWidth={1.5}
      />

      {/* Zone tournant en haut */}
      <Rect x={tx(numStraight * tread, s)} y={ty(sw, s)}
        width={len(sw, s)} height={len(sw, s)}
        stroke={COLOR_LIGHT} strokeWidth={1} fill={COLOR_FLOOR} />
      {balancing === 'balanced' ? (
        drawWinders(winders, numStraight * tread, 0, sw, s, 'top')
      ) : (
        <SvgText
          x={tx(numStraight * tread + sw / 2, s)} y={ty(sw / 2, s)}
          fontSize="10" fill={COLOR_DIM} textAnchor="middle"
        >
          PALIER
        </SvgText>
      )}

      {/* Ligne de foulée */}
      <Path
        d={`M ${tx(tread, s)},${ty(sw / 2, s)} L ${tx(numStraight * tread, s)},${ty(sw / 2, s)} L ${tx(numStraight * tread + (inp.walkline_offset_mm || 500), s)},${ty(sw, s)}`}
        stroke={COLOR_WALKLINE} strokeWidth={0.8} strokeDasharray="3 3" fill="none"
      />
      <SvgText
        x={tx(numStraight * tread / 2, s)} y={ty(sw / 2, s) - 8}
        fontSize="9" fill={COLOR_WALKLINE} textAnchor="middle" fontWeight="bold"
      >
        MONTÉE →
      </SvgText>

      {dimHorizontal(tx(0, s), tx(totalLen, s), ty(-100, s), fmtMm(totalLen), s)}
      {dimVertical(tx(totalLen + 100, s), ty(0, s), ty(sw, s), fmtMm(sw), s)}
      {dimHorizontal(tx(0, s), tx(tread, s), ty(-30, s), `g=${fmtMm(tread)}`, s, 10)}
    </Svg>
  );
}

// -------------- HALF TURN --------------
function renderHalfTurnPlan(inp: HalfTurnInput, r: StairResult, W: number, H: number) {
  const sw = inp.stair_width_mm;
  const tread = r.tread_depth_mm;
  const balancing = inp.balancing || 'balanced';
  const steps_flights = r.steps_per_flight; // [lower, mid, upper]
  const n_lower = steps_flights[0] || 0;
  const n_upper = steps_flights[2] || 0;

  const totalWid = 2 * sw;
  // longueur : max des deux volées + une largeur d'escalier (pour le 180°)
  const totalLen = Math.max(n_lower * tread, n_upper * tread) + sw;
  const s = makeScale(-300, -300, totalLen + 300, totalWid + 300, W, H, 30);

  return (
    <Svg width={W} height={H}>
      <Rect x={0} y={0} width={W} height={H} fill={COLOR_BG} />

      {/* Emprise */}
      <Rect x={tx(0, s)} y={ty(totalWid, s)}
        width={len(totalLen, s)} height={len(totalWid, s)}
        stroke={COLOR_STROKE} strokeWidth={1.5} fill="none" />

      {/* Volée basse (bande basse) */}
      {Array.from({ length: n_lower }).map((_, i) => (
        <G key={`l${i}`}>
          <Line
            x1={tx(i * tread, s)} y1={ty(0, s)}
            x2={tx(i * tread, s)} y2={ty(sw, s)}
            stroke={COLOR_STROKE} strokeWidth={1}
          />
          <SvgText
            x={tx(i * tread + tread / 2, s)} y={ty(sw / 2, s) + 4}
            fontSize="9" fill={COLOR_DIM} textAnchor="middle"
          >{i + 1}</SvgText>
        </G>
      ))}

      {/* Zone 180° à droite */}
      <Rect
        x={tx(n_lower * tread, s)} y={ty(totalWid, s)}
        width={len(sw, s)} height={len(totalWid, s)}
        stroke={COLOR_LIGHT} strokeWidth={1} fill={COLOR_FLOOR}
      />
      {balancing === 'balanced' ? (
        drawWinders(r.treads.filter(t => t.type === 'winder'), n_lower * tread, 0, totalWid, s, 'half')
      ) : (
        <SvgText
          x={tx(n_lower * tread + sw / 2, s)} y={ty(totalWid / 2, s)}
          fontSize="10" fill={COLOR_DIM} textAnchor="middle"
        >PALIER 180°</SvgText>
      )}

      {/* Volée haute (bande haute, sens inverse) */}
      {Array.from({ length: n_upper }).map((_, i) => (
        <G key={`u${i}`}>
          <Line
            x1={tx(n_upper * tread - i * tread, s)} y1={ty(sw, s)}
            x2={tx(n_upper * tread - i * tread, s)} y2={ty(totalWid, s)}
            stroke={COLOR_STROKE} strokeWidth={1}
          />
        </G>
      ))}

      {/* Flèche montée */}
      <Path
        d={`M ${tx(0, s)},${ty(sw / 2, s)} L ${tx(n_lower * tread, s)},${ty(sw / 2, s)} L ${tx(n_lower * tread + sw / 2, s)},${ty(sw + sw / 2, s)} L ${tx(0, s)},${ty(sw + sw / 2, s)}`}
        stroke={COLOR_WALKLINE} strokeWidth={0.8} strokeDasharray="3 3" fill="none"
      />

      {dimHorizontal(tx(0, s), tx(totalLen, s), ty(-100, s), fmtMm(totalLen), s)}
      {dimVertical(tx(totalLen + 100, s), ty(0, s), ty(totalWid, s), fmtMm(totalWid), s)}
    </Svg>
  );
}

// ---------- helpers ----------
function drawWinders(
  winders: any[],
  x0: number,
  y0: number,
  size: number,
  s: any,
  mode: 'bottom' | 'top' | 'half'
): React.ReactNode {
  // Winders répartis dans un carré size×size autour d'un pivot au coin (0,0) local
  const n = winders.length;
  if (n === 0) return null;

  // Pivot par convention : coin bas-gauche du carré pour bottom, en haut pour top
  const pivot = mode === 'bottom'
    ? { x: x0, y: y0 }
    : mode === 'top'
      ? { x: x0, y: y0 + size }
      : { x: x0 + size / 2, y: y0 + size / 2 }; // half

  const isHalf = mode === 'half';
  const totalAngle = isHalf ? Math.PI : Math.PI / 2;
  const anglePer = totalAngle / n;

  const elements: React.ReactNode[] = [];
  for (let i = 0; i < n; i++) {
    const a1 = i * anglePer;
    const a2 = (i + 1) * anglePer;
    // rayons (inner à 0, outer à `size`)
    const r_outer = size;
    const p1 = { x: pivot.x + r_outer * Math.cos(a1), y: pivot.y + r_outer * Math.sin(a1) };
    const p2 = { x: pivot.x + r_outer * Math.cos(a2), y: pivot.y + r_outer * Math.sin(a2) };
    const path = `M ${tx(pivot.x, s)},${ty(pivot.y, s)} L ${tx(p1.x, s)},${ty(p1.y, s)} L ${tx(p2.x, s)},${ty(p2.y, s)} Z`;
    elements.push(
      <Path key={`w${i}`} d={path} stroke={COLOR_STROKE} strokeWidth={0.8} fill="none" />
    );
    const midA = (a1 + a2) / 2;
    const midR = r_outer * 0.55;
    elements.push(
      <SvgText
        key={`t${i}`}
        x={tx(pivot.x + midR * Math.cos(midA), s)}
        y={ty(pivot.y + midR * Math.sin(midA), s) + 3}
        fontSize="9" fill={COLOR_DIM} textAnchor="middle"
      >
        {winders[i].index}
      </SvgText>
    );
  }
  return <G>{elements}</G>;
}

function dimHorizontal(x1: number, x2: number, y: number, label: string, s: any, fontSize = 11) {
  return (
    <G>
      <Line x1={x1} y1={y} x2={x2} y2={y} stroke={COLOR_DIM} strokeWidth={0.6} />
      <Line x1={x1} y1={y - 4} x2={x1} y2={y + 4} stroke={COLOR_DIM} strokeWidth={0.6} />
      <Line x1={x2} y1={y - 4} x2={x2} y2={y + 4} stroke={COLOR_DIM} strokeWidth={0.6} />
      <SvgText
        x={(x1 + x2) / 2} y={y - 4}
        fontSize={fontSize} fill={COLOR_DIM} textAnchor="middle"
      >{label}</SvgText>
    </G>
  );
}

function dimVertical(x: number, y1: number, y2: number, label: string, s: any, fontSize = 11) {
  return (
    <G>
      <Line x1={x} y1={y1} x2={x} y2={y2} stroke={COLOR_DIM} strokeWidth={0.6} />
      <Line x1={x - 4} y1={y1} x2={x + 4} y2={y1} stroke={COLOR_DIM} strokeWidth={0.6} />
      <Line x1={x - 4} y1={y2} x2={x + 4} y2={y2} stroke={COLOR_DIM} strokeWidth={0.6} />
      <SvgText
        x={x + 6} y={(y1 + y2) / 2}
        fontSize={fontSize} fill={COLOR_DIM} textAnchor="start"
      >{label}</SvgText>
    </G>
  );
}
