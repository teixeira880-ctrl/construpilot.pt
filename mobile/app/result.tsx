import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, Dimensions,
  TouchableOpacity, Alert as RNAlert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Button } from '../src/components/Button';
import { AlertRow } from '../src/components/AlertRow';
import { KeyValue } from '../src/components/KeyValue';
import { StairPlan } from '../src/drawing/StairPlan';
import { StairSection } from '../src/drawing/StairSection';
import { colors, radius, spacing, typography } from '../src/theme';
import type { StoredProject, StairType } from '../src/types';
import { getProject, saveProject, duplicateProject } from '../src/storage';

export default function ResultScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ projectId: string }>();
  const [project, setProject] = useState<StoredProject | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      if (params.projectId) {
        const p = await getProject(params.projectId);
        setProject(p);
      }
      setLoading(false);
    })();
  }, [params.projectId]);

  if (loading) {
    return (
      <SafeAreaView edges={['bottom']} style={styles.center}>
        <ActivityIndicator />
      </SafeAreaView>
    );
  }
  if (!project || !project.result) {
    return (
      <SafeAreaView edges={['bottom']} style={styles.center}>
        <Text style={{ color: colors.text }}>Projet introuvable.</Text>
      </SafeAreaView>
    );
  }

  const r = project.result;
  const input = project.input as any;
  const screenW = Dimensions.get('window').width - 2 * spacing.l;

  const globalLevel: 'red' | 'orange' | 'green' =
    r.alerts.some((a) => a.level === 'red')
      ? 'red'
      : r.alerts.some((a) => a.level === 'orange')
        ? 'orange'
        : 'green';

  const statusLabel = r.is_buildable ? 'Constructible' : 'Non constructible';
  const statusColor =
    globalLevel === 'green' ? colors.ok :
      globalLevel === 'orange' ? colors.warn : colors.danger;
  const statusBg =
    globalLevel === 'green' ? colors.okBg :
      globalLevel === 'orange' ? colors.warnBg : colors.dangerBg;

  const handleDuplicate = async () => {
    const dup = await duplicateProject(project.id);
    if (dup) {
      router.replace({ pathname: '/result', params: { projectId: dup.id } });
    }
  };

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Header projet */}
        <Text style={styles.projectName} testID="project-title">{project.name}</Text>
        <Text style={styles.projectType}>{humanType(project.type)}</Text>

        {/* Bandeau statut */}
        <View
          testID="status-banner"
          style={[styles.banner, { backgroundColor: statusBg, borderColor: statusColor }]}
        >
          <View style={[styles.bannerDot, { backgroundColor: statusColor }]} />
          <View style={{ flex: 1 }}>
            <Text style={[styles.bannerStatus, { color: statusColor }]}>{statusLabel}</Text>
            <Text style={styles.bannerSub}>
              {r.alerts[0]?.code || '—'} · {r.alerts.length} alerte{r.alerts.length > 1 ? 's' : ''}
            </Text>
          </View>
        </View>

        {/* Chiffres clés */}
        <SectionTitle>Chiffres clés</SectionTitle>
        <View style={styles.kvGrid}>
          <KeyValue testID="kv-num-steps" label="Marches" value={String(r.num_steps)} suffix="risers" />
          <KeyValue label="Hauteur marche" value={String(r.riser_height_mm)} suffix="mm" />
          <KeyValue label="Giron" value={String(r.tread_depth_mm)} suffix="mm" />
          <KeyValue label="Pente" value={String(r.slope_deg)} suffix="°" />
          <KeyValue label="Blondel (2h+g)" value={String(r.blondel_value_mm)} suffix="mm" />
          <KeyValue label="Échappée" value={r.headroom_mm > 0 ? String(r.headroom_mm) : '—'} suffix="mm" />
          <KeyValue label="Longueur volée" value={String(r.stair_length_mm)} suffix="mm" />
          <KeyValue label="Reculement réel" value={String(r.stair_run_mm)} suffix="mm" />
        </View>

        {/* Plan */}
        <SectionTitle>Vue en plan</SectionTitle>
        <View style={styles.svgWrap} testID="plan-svg">
          <StairPlan
            type={project.type}
            input={input}
            result={r}
            width={screenW}
            height={340}
          />
        </View>

        {/* Coupe */}
        <SectionTitle>Coupe verticale</SectionTitle>
        <View style={styles.svgWrap} testID="section-svg">
          <StairSection input={input} result={r} width={screenW} height={260} />
        </View>

        {/* Alertes */}
        <SectionTitle>Alertes DTU</SectionTitle>
        <View testID="alerts-list">
          {r.alerts.map((a, idx) => (
            <AlertRow key={idx} level={a.level} code={a.code} message={a.message} />
          ))}
        </View>

        {/* Actions */}
        <View style={styles.actions}>
          <Button
            testID="edit-btn"
            label="Modifier dimensions"
            variant="secondary"
            onPress={() => router.push({ pathname: '/form', params: { type: project.type } })}
            fullWidth
          />
          <View style={{ height: spacing.s }} />
          <Button
            testID="duplicate-btn"
            label="Dupliquer"
            variant="secondary"
            onPress={handleDuplicate}
            fullWidth
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function humanType(t: StairType): string {
  const M: Record<StairType, string> = {
    'straight': 'Escalier droit',
    'quarter-turn-bottom': 'Quart tournant bas',
    'quarter-turn-top': 'Quart tournant haut',
    'half-turn': 'Demi-tournant',
  };
  return M[t];
}
function SectionTitle({ children }: { children: string }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll: { padding: spacing.l, paddingBottom: spacing.xxl },

  projectName: { ...typography.h2, color: colors.text },
  projectType: { ...typography.caption, color: colors.textMuted, marginBottom: spacing.m, textTransform: 'uppercase' },

  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.l,
    borderRadius: radius.m,
    borderWidth: 1,
    marginBottom: spacing.l,
  },
  bannerDot: { width: 14, height: 14, borderRadius: 7, marginRight: spacing.m },
  bannerStatus: { ...typography.h3 },
  bannerSub: { ...typography.small, color: colors.textMuted, marginTop: 2 },

  sectionTitle: {
    ...typography.caption,
    color: colors.textMuted,
    textTransform: 'uppercase',
    marginTop: spacing.l,
    marginBottom: spacing.s,
  },
  kvGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.s as any,
  },
  svgWrap: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.m,
    backgroundColor: colors.bg,
    overflow: 'hidden',
  },
  actions: { marginTop: spacing.l },
});
