import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator,
  TouchableOpacity, Alert as RNAlert,
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

export default function CompareScreen() {
  const router = useRouter();
  const [data, setData] = useState<OptimizeApiResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const raw = await AsyncStorage.getItem(OPTIMIZE_CACHE_KEY);
      if (raw) setData(JSON.parse(raw));
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

  const saveSolution = async (sol: OptimizeSolution) => {
    const stype = TYPE_TO_STAIRTYPE[sol.type] || 'straight';
    const project = await saveProject({
      name: `Optimisation — ${TYPE_LABELS[sol.type]} (score ${sol.score_global})`,
      type: stype,
      input: {} as any,  // input non reconstruit — l'utilisateur peut re-saisir
      result: sol.result,
    });
    RNAlert.alert('Projet sauvegardé', `« ${project.name} » ajouté à la liste.`);
  };

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title} testID="compare-title">
          {data.solutions.length} solution{data.solutions.length > 1 ? 's' : ''} trouvée{data.solutions.length > 1 ? 's' : ''}
        </Text>
        <Text style={styles.subtitle}>Triées par score global (confort + encombrement + faisabilité + esthétique)</Text>

        {data.solutions.map((sol, i) => (
          <SolutionCard key={i} sol={sol} onSave={() => saveSolution(sol)} />
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

function SolutionCard({ sol, onSave }: { sol: OptimizeSolution; onSave: () => void }) {
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

      <View style={{ marginTop: spacing.s }}>
        <Button label="Sauvegarder ce projet" variant="secondary" onPress={onSave} fullWidth testID={`save-solution-${sol.rank}`} />
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
    paddingHorizontal: spacing.m, paddingVertical: spacing.s,
    borderRadius: radius.m,
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
  scoreRow: {
    flexDirection: 'row', alignItems: 'center',
    marginBottom: 4,
  },
  scoreRowLabel: { ...typography.small, color: colors.textMuted, width: 90 },
  scoreBarBg: { flex: 1, height: 6, backgroundColor: colors.bgSubtle, borderRadius: 3, marginHorizontal: spacing.s },
  scoreBarFg: { height: 6, backgroundColor: colors.primary, borderRadius: 3 },
  scoreRowValue: { ...typography.monoSmall, color: colors.textMuted, width: 30, textAlign: 'right' },
  sectionTitle: { ...typography.caption, color: colors.textMuted, textTransform: 'uppercase', marginTop: spacing.l, marginBottom: spacing.s },
  excluded: { marginTop: spacing.l },
  excludedRow: {
    borderTopWidth: 1, borderTopColor: colors.border,
    paddingVertical: spacing.s,
  },
  excludedType: { ...typography.bodyStrong, color: colors.text },
  excludedReason: { ...typography.small, color: colors.textMuted },
});
