/**
 * Types TS miroirs du backend Python (stair_engine/models.py).
 */

export type StairType =
  | 'straight'
  | 'quarter-turn-bottom'
  | 'quarter-turn-top'
  | 'half-turn'
  | 'helicoidal';

export type BalancingMode = 'straight' | 'balanced';
export type Direction = 'left' | 'right';
export type AlertLevel = 'red' | 'orange' | 'green';
export type TreadType = 'straight' | 'winder';

export interface StairInput {
  floor_height_mm: number;
  available_length_mm: number;
  available_width_mm: number;
  stair_width_mm: number;
  stairwell_length_mm?: number | null;
  stairwell_width_mm?: number | null;
  stairwell_offset_mm?: number | null;
  slab_thickness_mm?: number;
  ceiling_height_mm?: number | null;
  tread_thickness_mm?: number;
  has_risers?: boolean;
  direction?: Direction;
}

export interface QuarterTurnInput extends StairInput {
  balancing?: BalancingMode;
  landing_length_mm?: number | null;
  landing_width_mm?: number | null;
  steps_before_landing?: number;
  num_winders?: number | 'auto';
  walkline_offset_mm?: number;
  inner_radius_mm?: number;
}

export interface HalfTurnInput extends StairInput {
  balancing?: BalancingMode;
  landing_length_mm?: number | null;
  num_winders?: number | 'auto';
  walkline_offset_mm?: number;
  inner_radius_mm?: number;
}

export interface Alert {
  level: AlertLevel;
  code: string;
  message: string;
  message_fr: string;
  metric?: string | null;
  value?: number | null;
  threshold?: number | null;
  tread_index?: number | null;
}

export interface TreadDetail {
  index: number;
  type: TreadType;
  depth_walkline_mm: number;
  depth_inner_mm: number;
  depth_outer_mm: number;
  angle_deg: number;
  cumulative_height_mm: number;
}

export interface StairResult {
  stair_type: string;
  num_steps: number;
  num_treads: number;
  riser_height_mm: number;
  tread_depth_mm: number;
  blondel_value_mm: number;
  slope_deg: number;
  stair_run_mm: number;
  stair_length_mm: number;
  headroom_mm: number;
  required_stairwell_mm: Record<string, number>;
  steps_per_flight: number[];
  treads: TreadDetail[];
  alerts: Alert[];
  is_buildable: boolean;
  computed_at?: string;
}

export interface StoredProject {
  id: string;
  name: string;
  type: StairType;
  input: StairInput | QuarterTurnInput | HalfTurnInput;
  result: StairResult | null;
  created_at: string;
  updated_at: string;
}

export const STAIR_TYPE_LABELS: Record<StairType, string> = {
  'straight': 'Droit',
  'quarter-turn-bottom': 'Quart tournant bas',
  'quarter-turn-top': 'Quart tournant haut',
  'half-turn': 'Demi-tournant',
  'helicoidal': 'Hélicoïdal',
};

export const STAIR_TYPE_DESCRIPTIONS: Record<StairType, string> = {
  'straight': 'Une seule volée rectiligne du sol bas au sol haut.',
  'quarter-turn-bottom': 'Départ tournant à 90° puis volée droite.',
  'quarter-turn-top': 'Volée droite puis arrivée tournante à 90°.',
  'half-turn': 'Deux volées en aller-retour avec palier ou marches balancées à 180°.',
  'helicoidal': 'Escalier colimaçon autour d\'un fût central (giron variable).',
};

export interface OptimizeSolution {
  rank: number;
  type: string;
  variant: string;
  score_global: number;
  scores: { confort: number; encombrement: number; faisabilite: number; esthetique: number };
  result: StairResult;
}

export interface OptimizeApiResult {
  solutions: OptimizeSolution[];
  excluded: { type: string; variant: string; reason: string }[];
  computed_at?: string;
}
