import React from 'react';
import Svg, { Rect, Line, Text as SvgText, G, Pattern, Defs } from 'react-native-svg';
import type { StairInput, StairResult } from '../types';
import { makeScale, tx, ty, len, fmtMm } from './scale';

/**
 * Coupe transversale — vue perpendiculaire à l'axe de la volée, à mi-marche.
 * Montre : largeur de la volée, section paillasse + marche + contremarche,
 * position des garde-corps, mur d'appui éventuel.
 *
 * X = largeur (mm)  |  Y = hauteur (mm) au niveau de la marche coupée
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
const COLOR_CONCRETE = '#E7E9ED';
const COLOR_HANDRAIL = '#0B5FFF';
const COLOR_STEEL = '#D64545';

export function StairSectionTransverse({ input, result, width, height }: Props) {
  const sw = input.stair_width_mm;
  const paillasse = Math.max(150, Math.min(220, Math.round(result.stair_length_mm / 25 / 10) * 10)); // approx L/25
  const treadTh = input.tread_thickness_mm ?? 30;
  const riser = result.riser_height_mm;
  const guardH = 1000; // norme garde-corps 1m

  // Bounding box en mm
  const s = makeScale(-200, -paillasse - 100, sw + 200, guardH + riser + 100, width, height, 25);

  const handRailX_L = 50;
  const handRailX_R = sw - 50;

  return (
    <Svg width={width} height={height}>
      <Defs>
        <Pattern id="concreteHatchT" patternUnits="userSpaceOnUse" width="6" height="6">
          <Line x1="0" y1="6" x2="6" y2="0" stroke={COLOR_MUTED} strokeWidth={0.4} />
        </Pattern>
      </Defs>
      <Rect x={0} y={0} width={width} height={height} fill={COLOR_BG} />

      {/* Paillasse (section rectangulaire sous la marche) */}
      <Rect
        x={tx(0, s)} y={ty(0, s)}
        width={len(sw, s)} height={len(paillasse, s)}
        fill="url(#concreteHatchT)" stroke={COLOR_STROKE} strokeWidth={1.4}
      />
      {/* Fond de la paillasse : hachures béton */}
      <Rect
        x={tx(0, s)} y={ty(0, s)}
        width={len(sw, s)} height={len(paillasse, s)}
        fill={COLOR_CONCRETE} stroke="none" opacity={0.4}
      />
      <Rect
        x={tx(0, s)} y={ty(0, s)}
        width={len(sw, s)} height={len(paillasse, s)}
        fill="none" stroke={COLOR_STROKE} strokeWidth={1.4}
      />

      {/* Marche béton au-dessus (nez + contremarche vue en coupe) */}
      <Rect
        x={tx(0, s)} y={ty(riser, s)}
        width={len(sw, s)} height={len(riser, s)}
        fill={COLOR_CONCRETE} stroke={COLOR_STROKE} strokeWidth={1}
      />

      {/* Revêtement de marche (tread) */}
      <Rect
        x={tx(0, s)} y={ty(riser + treadTh, s)}
        width={len(sw, s)} height={len(treadTh, s)}
        fill="#F5F6F8" stroke={COLOR_STROKE} strokeWidth={0.8}
      />

      {/* Aciers principaux (dans la paillasse — 2 lignes ponctuelles) */}
      <G>
        {[0.15, 0.5, 0.85].map((f, i) => (
          <G key={`main${i}`}>
            <Line
              x1={tx(sw * f - 6, s)} y1={ty(-paillasse + 30, s)}
              x2={tx(sw * f + 6, s)} y2={ty(-paillasse + 30, s)}
              stroke={COLOR_HANDRAIL} strokeWidth={2}
            />
          </G>
        ))}
        <SvgText
          x={tx(sw / 2, s)} y={ty(-paillasse + 55, s)}
          fontSize="8" fill={COLOR_HANDRAIL} textAnchor="middle"
        >aciers principaux (fibre inf.)</SvgText>
      </G>

      {/* Aciers de répartition (en haut de la paillasse) */}
      <G>
        {[0.15, 0.5, 0.85].map((f, i) => (
          <Line key={`rep${i}`}
            x1={tx(sw * f - 4, s)} y1={ty(-30, s)}
            x2={tx(sw * f + 4, s)} y2={ty(-30, s)}
            stroke={COLOR_STEEL} strokeWidth={1.5}
          />
        ))}
        <SvgText
          x={tx(sw / 2, s)} y={ty(-8, s)}
          fontSize="8" fill={COLOR_STEEL} textAnchor="middle"
        >aciers répartition</SvgText>
      </G>

      {/* Garde-corps gauche */}
      <G>
        <Line
          x1={tx(handRailX_L, s)} y1={ty(riser + treadTh, s)}
          x2={tx(handRailX_L, s)} y2={ty(riser + treadTh + guardH, s)}
          stroke={COLOR_HANDRAIL} strokeWidth={2.4}
        />
        <Line
          x1={tx(handRailX_L - 20, s)} y1={ty(riser + treadTh + guardH, s)}
          x2={tx(handRailX_L + 40, s)} y2={ty(riser + treadTh + guardH, s)}
          stroke={COLOR_HANDRAIL} strokeWidth={2.4}
        />
      </G>
      {/* Garde-corps droit */}
      <G>
        <Line
          x1={tx(handRailX_R, s)} y1={ty(riser + treadTh, s)}
          x2={tx(handRailX_R, s)} y2={ty(riser + treadTh + guardH, s)}
          stroke={COLOR_HANDRAIL} strokeWidth={2.4}
        />
        <Line
          x1={tx(handRailX_R - 40, s)} y1={ty(riser + treadTh + guardH, s)}
          x2={tx(handRailX_R + 20, s)} y2={ty(riser + treadTh + guardH, s)}
          stroke={COLOR_HANDRAIL} strokeWidth={2.4}
        />
      </G>

      {/* Cotes */}
      {/* Largeur volée */}
      {dimHoriz(tx(0, s), tx(sw, s), ty(riser + treadTh + guardH + 60, s), `l=${fmtMm(sw)}`, 11)}
      {/* Épaisseur paillasse */}
      {dimVert(tx(-80, s), ty(0, s), ty(-paillasse, s), `ép=${fmtMm(paillasse)}`, 10)}
      {/* Hauteur marche */}
      {dimVert(tx(sw + 60, s), ty(0, s), ty(riser, s), `h=${fmtMm(riser)}`, 10)}
      {/* Hauteur garde-corps */}
      {dimVert(tx(sw + 120, s), ty(riser + treadTh, s), ty(riser + treadTh + guardH, s), `1000`, 10)}

      {/* Légende */}
      <SvgText x={tx(0, s)} y={ty(-paillasse - 30, s)} fontSize="9" fill={COLOR_DIM}>
        Coupe transversale · à mi-volée · vue en montée
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
