import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, Alert as RNAlert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Button } from '../src/components/Button';
import { StairPlan } from '../src/drawing/StairPlan';
import { colors, radius, spacing, typography } from '../src/theme';
import type { OptimizeApiResult, OptimizeSolution, StairType } from '../src/types';
import { saveProject } from '../src/storage';

const OPTIMIZE_CACHE_KEY = 'stairpilot_optimize_result_v1';
const OPTIMIZE_INPUT_KEY = 'stairpilot_optimize_input_v1';

const TYPE_TO_STAIRTYPE: Record<string, StairType> = {
  'straight': 'straight',
  'quarter_turn_bottom': 'quarter-turn-bottom',
  'quarter_turn_top': 'quarter-turn-top',
  'half_turn': 'half-turn',
  'helicoidal': 'helicoidal',
};

const TYPE_LABELS: Record<string, string> = {
  'straight': 'Droit',
  'quarter_turn_bottom': 'QT bas',
  'quarter_turn_top': 'QT haut',
  'half_turn': 'Demi-tournant',
  'helicoidal': 'Hélicoïdal',
};

/**
 * Reconstruit l'input complet pour une solution :
 * - fields communs viennent du body d'optimisation (les mêmes utilisés pour tous les types)
 * - fields spécifiques déduits de la variante (balancing pour QT/DT, sweep_angle pour hélico)
 * - num_winders pour balanced = "auto" par défaut (l'auto reproduira le même nombre)
 */
function reconstructInput(sol: OptimizeSolution, optInput: any): any {
  const stype = TYPE_TO_STAIRTYPE[sol.type] || 'straight';
  const base = {
    floor_height_mm: optInput.floor_height_mm,
    available_length_mm: optInput.available_length_mm,
    available_width_mm: optInput.available_width_mm,
    stair_width_mm: optInput.stair_width_mm ?? 900,
    stairwell_length_mm: optInput.stairwell_length_mm ?? null,
    stairwell_width_mm: optInput.stairwell_width_mm ?? null,
    stairwell_offset_mm: null,
    slab_thickness_mm: optInput.slab_thickness_mm ?? 200,
    ceiling_height_mm: optInput.ceiling_height_mm ?? null,
    tread_thickness_mm: optInput.tread_thickness_mm ?? 30,
    has_risers: optInput.has_risers ?? true,
    direction: 'right' as const,
  };
  if (stype === 'straight') return base;
  if (stype === 'helicoidal') {
    // variant = "sweep_360" etc. — extraire le sweep
    const sweep = parseInt(sol.variant.replace('sweep_', ''), 10) || 360;
    const outerRadius = (sol.result.required_stairwell_mm?.diameter_mm ?? 1500) / 2;
    return {
      floor_height_mm: base.floor_height_mm,
      inner_radius_mm: 150,
      outer_radius_mm: outerRadius,
      sweep_angle_deg: sweep,
      direction: 'cw',
      walkline_offset_mm: 500,
      slab_thickness_mm: base.slab_thickness_mm,
      ceiling_height_mm: base.ceiling_height_mm,
      tread_thickness_mm: base.tread_thickness_mm,
      has_risers: base.has_risers,
    };
  }
  // QT bas / QT haut / demi-tournant : variant = "balanced" | "straight"
  return {
    ...base,
    balancing: sol.variant === 'straight' ? 'straight' : 'balanced',
    num_winders: 'auto' as const,
    walkline_offset_mm: 500,
    inner_radius_mm: 0,
    landing_length_mm: null,
    landing_width_mm: null,
  };
}

export default function CompareScreen() {
  const router = useRouter();
  const [data, setData] = useState<OptimizeApiResult | null>(null);
  const [optInput, setOptInput] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [raw, rawInp] = await Promise.all([
        AsyncStorage.getItem(OPTIMIZE_CACHE_KEY),
        AsyncStorage.getItem(OPTIMIZE_INPUT_KEY),
      ]);
      if (raw) setData(JSON.parse(raw));
      if (rawInp) setOptInput(JSON.parse(rawInp));
      setLoading(false);
    })();
  }, []);

  if (loading) {
    return (
      <SafeAreaView edges={['bottom']} style={[styles.container, { alignItems: 'center', justifyContent: 'center' }]}>
        <ActivityIndicator />
      </SafeAreaView>
    );
  }
  if (!data) {
    return (
      <SafeAreaView style={styles.container}>
        <Text style={{ color: colors.text, padding: spacing.l }}>Aucun résultat d'optimisation.</Text>
      </SafeAreaView>
    );
  }

  const persistAndGetId = async (sol: OptimizeSolution, name: string): Promise<string> => {
    const stype = TYPE_TO_STAIRTYPE[sol.type] || 'straight';
    const fullInput = reconstructInput(sol, optInput ?? {});
    const project = await saveProject({
      name,
      type: stype,
      input: fullInput,
      result: sol.result,
    });
    return project.id;
  };

  const viewDetail = async (sol: OptimizeSolution) => {
    const name = `Solution optimizer — ${TYPE_LABELS[sol.type]} (score ${sol.score_global})`;
    const id = await persistAndGetId(sol, name);
    router.push({ pathname: '/result', params: { projectId: id } });
  };

  const saveSolution = async (sol: OptimizeSolution) => {
    const name = `Optimisation — ${TYPE_LABELS[sol.type]} (score ${sol.score_global})`;
    await persistAndGetId(sol, name);
    RNAlert.alert('Projet sauvegardé', `« ${name} » ajouté à la liste des projets.`);
  };

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title} testID="compare-title">
          {data.solutions.length} solution{data.solutions.length > 1 ? 's' : ''} trouvée{data.solutions.length > 1 ? 's' : ''}
        </Text>
        <Text style={styles.subtitle}>
          Triées par score global (confort + encombrement + faisabilité + esthétique)
        </Text>

        {data.solutions.map((sol) => (
          <SolutionCard
            key={sol.rank}
            sol={sol}
            onDetail={() => viewDetail(sol)}
            onSave={() => saveSolution(sol)}
          />
        ))}

        {data.excluded.length > 0 && (
          <View style={styles.excluded}>
            <Text style={styles.sectionTitle}>Solutions écartées ({data.excluded.length})</Text>
            {data.excluded.map((e, idx) => (
              <View key={idx} style={styles.excludedRow}>
                <Text style={styles.excludedType}>{TYPE_LABELS[e.type] ?? e.type} · {e.variant}</Text>
                <Text style={styles.excludedReason}>{e.reason}</Text>
              </View>
            ))}
          </View>
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function SolutionCard({
  sol, onDetail, onSave,
}: {
  sol: OptimizeSolution;
  onDetail: () => void;
  onSave: () => void;
}) {
  const scoreColor = sol.score_global >= 75 ? colors.ok : sol.score_global >= 50 ? colors.warn : colors.danger;
  const scoreBg = sol.score_global >= 75 ? colors.okBg : sol.score_global >= 50 ? colors.warnBg : colors.dangerBg;
  const stype = TYPE_TO_STAIRTYPE[sol.type] || 'straight';

  return (
    <View style={styles.card} testID={`solution-${sol.rank}`}>
      <View style={styles.cardHeader}>
        <View style={{ flex: 1 }}>
          <Text style={styles.rank}>#{sol.rank} · {TYPE_LABELS[sol.type] ?? sol.type}</Text>
          <Text style={styles.variant}>{sol.variant}</Text>
        </View>
        <View style={[styles.scoreBadge, { backgroundColor: scoreBg }]}>
          <Text style={[styles.scoreValue, { color: scoreColor }]}>{sol.score_global.toFixed(0)}</Text>
          <Text style={[styles.scoreLabel, { color: scoreColor }]}>/100</Text>
        </View>
      </View>

      <View style={styles.thumbnail}>
        <StairPlan
          type={stype}
          input={{ stair_width_mm: 900, floor_height_mm: sol.result.riser_height_mm * sol.result.num_steps } as any}
          result={sol.result}
          width={340}
          height={160}
        />
      </View>

      <View style={styles.metrics}>
        <Metric label="Marches" value={String(sol.result.num_steps)} />
        <Metric label="Pente" value={`${sol.result.slope_deg}°`} />
        <Metric label="Reculement" value={`${Math.round(sol.result.stair_run_mm)}mm`} />
        <Metric label="Blondel" value={String(sol.result.blondel_value_mm)} />
      </View>

      <View style={styles.scoreBreakdown}>
        <ScoreBar label="Confort" value={sol.scores.confort} />
        <ScoreBar label="Encombrement" value={sol.scores.encombrement} />
        <ScoreBar label="Faisabilité" value={sol.scores.faisabilite} />
        <ScoreBar label="Esthétique" value={sol.scores.esthetique} />
      </View>

      <View style={{ marginTop: spacing.m }}>
        <Button
          testID={`detail-solution-${sol.rank}`}
          label="Voir en détail"
          variant="primary"
          onPress={onDetail}
          fullWidth
        />
        <View style={{ height: spacing.s }} />
        <Button
          testID={`save-solution-${sol.rank}`}
          label="Sauvegarder ce projet"
          variant="secondary"
          onPress={onSave}
          fullWidth
        />
      </View>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.scoreRow}>
      <Text style={styles.scoreRowLabel}>{label}</Text>
      <View style={styles.scoreBarBg}>
        <View style={[styles.scoreBarFg, { width: `${value}%` }]} />
      </View>
      <Text style={styles.scoreRowValue}>{value.toFixed(0)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.l },
  title: { ...typography.h2, color: colors.text },
  subtitle: { ...typography.small, color: colors.textMuted, marginBottom: spacing.l },
  card: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.m,
    padding: spacing.l, marginBottom: spacing.m, backgroundColor: colors.bg,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.m },
  rank: { ...typography.h3, color: colors.text },
  variant: { ...typography.caption, color: colors.textMuted },
  scoreBadge: {
    flexDirection: 'row', alignItems: 'baseline',
    paddingHorizontal: spacing.m, paddingVertical: spacing.s, borderRadius: radius.m,
  },
  scoreValue: { ...typography.mono, fontSize: 20 },
  scoreLabel: { ...typography.monoSmall, marginLeft: 2 },
  thumbnail: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.s,
    backgroundColor: colors.bg, marginBottom: spacing.s, overflow: 'hidden',
  },
  metrics: { flexDirection: 'row', flexWrap: 'wrap' },
  metric: { flex: 1, minWidth: '25%', marginBottom: spacing.s },
  metricLabel: { ...typography.caption, color: colors.textMuted, textTransform: 'uppercase' },
  metricValue: { ...typography.mono, color: colors.text, fontSize: 14 },
  scoreBreakdown: { marginTop: spacing.s },
  scoreRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  scoreRowLabel: { ...typography.small, color: colors.textMuted, width: 90 },
  scoreBarBg: { flex: 1, height: 6, backgroundColor: colors.bgSubtle, borderRadius: 3, marginHorizontal: spacing.s },
  scoreBarFg: { height: 6, backgroundColor: colors.primary, borderRadius: 3 },
  scoreRowValue: { ...typography.monoSmall, color: colors.textMuted, width: 30, textAlign: 'right' },
  sectionTitle: { ...typography.caption, color: colors.textMuted, textTransform: 'uppercase', marginTop: spacing.l, marginBottom: spacing.s },
  excluded: { marginTop: spacing.l },
  excludedRow: { borderTopWidth: 1, borderTopColor: colors.border, paddingVertical: spacing.s },
  excludedType: { ...typography.bodyStrong, color: colors.text },
  excludedReason: { ...typography.small, color: colors.textMuted },
});
