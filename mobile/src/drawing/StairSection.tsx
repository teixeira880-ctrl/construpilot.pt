import React from 'react';
import Svg, { Line, Rect, Path, Text as SvgText, G } from 'react-native-svg';
import type { StairResult, StairInput } from '../types';
import { makeScale, tx, ty, len, fmtMm } from './scale';

interface Props {
  input: StairInput;
  result: StairResult;
  width: number;
  height: number;
}

const COLOR_STROKE = '#1A1D22';
const COLOR_LIGHT = '#9AA1AC';
const COLOR_DIM = '#5A6270';
const COLOR_BG = '#FFFFFF';
const COLOR_FLOOR = '#D6D9DE';
const COLOR_DANGER = '#D64545';
const COLOR_TEXT = '#1A1D22';
const COLOR_WALKLINE = '#0B5FFF';

/**
 * Coupe verticale dans l'axe de la volée.
 * X = distance horizontale depuis pied de l'escalier (mm)
 * Y = hauteur depuis sol bas (mm)
 */
export function StairSection({ input, result, width, height }: Props) {
  const H = input.floor_height_mm;
  const g = result.tread_depth_mm;
  const h = result.riser_height_mm;
  const n = result.num_steps;
  const numTreads = result.num_treads;
  const ceilingH = input.ceiling_height_mm ?? H + 800;
  const slabTh = input.slab_thickness_mm ?? 200;
  const swL = input.stairwell_length_mm;

  // Bounding box
  const maxX = numTreads * g + 500;
  const maxY = ceilingH + slabTh + 300;
  const minX = -500;
  const minY = -300;
  const s = makeScale(minX, minY, maxX, maxY, width, height, 30);

  // Position trémie
  const stairRun = numTreads * g;
  let x_start = 0, x_end = stairRun;
  if (swL) {
    if (input.stairwell_offset_mm != null) {
      x_start = g + input.stairwell_offset_mm;
      x_end = x_start + swL;
    } else {
      x_end = stairRun;
      x_start = x_end - swL;
    }
  }

  return (
    <Svg width={width} height={height}>
      <Rect x={0} y={0} width={width} height={height} fill={COLOR_BG} />

      {/* Sol bas */}
      <Line x1={tx(minX + 50, s)} y1={ty(0, s)} x2={tx(0, s)} y2={ty(0, s)}
        stroke={COLOR_STROKE} strokeWidth={1.5} />
      {hatches(minX + 50, 0, 100, 60, s)}

      {/* Sol haut + dalle */}
      <Rect
        x={tx(swL ? x_end : stairRun, s)}
        y={ty(ceilingH + slabTh, s)}
        width={len(maxX - (swL ? x_end : stairRun), s)}
        height={len(slabTh, s)}
        fill={COLOR_FLOOR} stroke={COLOR_STROKE} strokeWidth={1}
      />
      <Line
        x1={tx(swL ? x_end : stairRun, s)}
        y1={ty(H, s)}
        x2={tx(maxX, s)}
        y2={ty(H, s)}
        stroke={COLOR_STROKE} strokeWidth={1.5}
      />

      {/* Marches (profil) */}
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
        return <Path d={path.join(' ')} stroke={COLOR_STROKE} strokeWidth={1.5} fill="none" />;
      })()}

      {/* Trémie (retrait de la dalle du haut) - déjà pris en compte par le début du sol haut */}

      {/* Ligne échappée mini 1900mm en pointillés rouges si applicable */}
      {swL && input.ceiling_height_mm && result.headroom_mm > 0 && result.headroom_mm < 1900 && (() => {
        // Position marche critique : la 1ère marche sous la dalle → hauteur = h
        // Ligne verticale à x_start indiquant hauteur = h + 1900
        return (
          <G>
            <Line
              x1={tx(x_start, s)} y1={ty(0, s)}
              x2={tx(x_start, s)} y2={ty(ceilingH, s)}
              stroke={COLOR_DANGER} strokeWidth={0.8} strokeDasharray="3 3"
            />
            <SvgText
              x={tx(x_start + 20, s)} y={ty(ceilingH - 100, s)}
              fontSize="9" fill={COLOR_DANGER}
            >Échappée min. 1900</SvgText>
          </G>
        );
      })()}

      {/* Cotes */}
      {dimVertical(tx(-100, s), ty(0, s), ty(H, s), `H=${fmtMm(H)}`, 11)}
      {dimHorizontal(tx(0, s), tx(stairRun, s), ty(-150, s), fmtMm(stairRun), 11)}
      {/* Hauteur marche */}
      {dimVertical(tx(-40, s), ty(0, s), ty(h, s), `h=${fmtMm(h)}`, 9)}
      {/* Giron */}
      {dimHorizontal(tx(0, s), tx(g, s), ty(-60, s), `g=${fmtMm(g)}`, 9)}
      {/* Échappée */}
      {input.ceiling_height_mm && result.headroom_mm > 0 && (
        <G>
          <Line
            x1={tx(x_start, s)} y1={ty(ceilingH, s)}
            x2={tx(x_start, s)} y2={ty(ceilingH - result.headroom_mm, s)}
            stroke={result.headroom_mm < 1900 ? COLOR_DANGER : COLOR_DIM}
            strokeWidth={0.8}
          />
          <SvgText
            x={tx(x_start + 12, s)} y={ty(ceilingH - result.headroom_mm / 2, s)}
            fontSize="10" fill={result.headroom_mm < 1900 ? COLOR_DANGER : COLOR_DIM}
          >
            échappée {fmtMm(result.headroom_mm)}
          </SvgText>
        </G>
      )}

      {/* Repères niveaux */}
      <SvgText x={tx(minX + 20, s)} y={ty(0, s) - 4} fontSize="9" fill={COLOR_TEXT}>0.00</SvgText>
      <SvgText x={tx(minX + 20, s)} y={ty(H, s) - 4} fontSize="9" fill={COLOR_TEXT}>+{fmtMm(H)}</SvgText>
    </Svg>
  );

  function hatches(xStartMm: number, yMm: number, widthMm: number, count: number, s: any) {
    const arr = [];
    const step = widthMm / count;
    for (let i = 0; i < count; i++) {
      arr.push(
        <Line
          key={i}
          x1={tx(xStartMm + i * step, s)} y1={ty(yMm, s)}
          x2={tx(xStartMm + i * step - 30, s)} y2={ty(yMm - 40, s)}
          stroke={COLOR_LIGHT} strokeWidth={0.4}
        />
      );
    }
    return arr;
  }

  function dimHorizontal(x1: number, x2: number, y: number, label: string, fontSize = 11) {
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
  function dimVertical(x: number, y1: number, y2: number, label: string, fontSize = 11) {
    return (
      <G>
        <Line x1={x} y1={y1} x2={x} y2={y2} stroke={COLOR_DIM} strokeWidth={0.6} />
        <Line x1={x - 4} y1={y1} x2={x + 4} y2={y1} stroke={COLOR_DIM} strokeWidth={0.6} />
        <Line x1={x - 4} y1={y2} x2={x + 4} y2={y2} stroke={COLOR_DIM} strokeWidth={0.6} />
        <SvgText
          x={x - 6} y={(y1 + y2) / 2}
          fontSize={fontSize} fill={COLOR_DIM} textAnchor="end"
        >{label}</SvgText>
      </G>
    );
  }
}
