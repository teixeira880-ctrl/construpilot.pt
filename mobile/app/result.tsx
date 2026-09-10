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
import { StairSectionTransverse } from '../src/drawing/StairSectionTransverse';
import { StairSectionAxial } from '../src/drawing/StairSectionAxial';
import { colors, radius, spacing, typography } from '../src/theme';
import type { StoredProject, StairType } from '../src/types';
import { getProject, duplicateProject } from '../src/storage';
import { analyzeConcrete } from '../src/api';
import { generateAndSharePDF } from '../src/pdf';

type SectionKind = 'long' | 'trans' | 'axial';

export default function ResultScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ projectId: string }>();
  const [project, setProject] = useState<StoredProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [sectionKind, setSectionKind] = useState<SectionKind>('long');
  const [exporting, setExporting] = useState(false);

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

  const nonBlockerReds = r.alerts.filter((a) => a.level === 'red');
  const orangeAlerts = r.alerts.filter((a) => a.level === 'orange');

  const statusColor = !r.is_buildable
    ? colors.danger
    : nonBlockerReds.length > 0
      ? colors.warn
      : orangeAlerts.length > 0
        ? colors.warn
        : colors.ok;
  const statusBg = !r.is_buildable
    ? colors.dangerBg
    : nonBlockerReds.length > 0 || orangeAlerts.length > 0
      ? colors.warnBg
      : colors.okBg;
  const statusLabel = !r.is_buildable ? 'Non constructible' : 'Constructible';
  const statusSubtitle = !r.is_buildable
    ? (r.alerts.find((a) => a.level === 'red')?.code ?? '—')
    : nonBlockerReds.length > 0
      ? `Constructible mais non-conforme DTU · ${nonBlockerReds.length} alerte${nonBlockerReds.length > 1 ? 's' : ''} rouge${nonBlockerReds.length > 1 ? 's' : ''}`
      : orangeAlerts.length > 0
        ? `${orangeAlerts.length} avertissement${orangeAlerts.length > 1 ? 's' : ''}`
        : 'Toutes les cotes respectent les seuils DTU 36.3';

  const handleDuplicate = async () => {
    const dup = await duplicateProject(project.id);
    if (dup) {
      router.replace({ pathname: '/result', params: { projectId: dup.id } });
    }
  };

  const handleExportPDF = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      // Récupère (optionnellement) l'analyse béton pour enrichir le PDF
      let concrete: any = null;
      try {
        concrete = await analyzeConcrete({
          stair_result: r,
          stair_type: project.type,
          concrete_class: 'C25/30',
          steel_grade: 'B500B',
          exposure_class: 'XC1',
          live_load_kN_m2: 2.5,
        });
      } catch {
        // Non bloquant : on génère quand même le PDF sans analyse béton
      }
      const filename = await generateAndSharePDF({
        project_name: project.name,
        stair_input: input,
        stair_result: r,
        concrete_analysis: concrete,
      });
      RNAlert.alert('Dossier PDF prêt', `Fichier généré : ${filename}`);
    } catch (e: any) {
      RNAlert.alert('Export impossible', e?.message ?? 'Erreur inconnue');
    } finally {
      setExporting(false);
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
            <Text style={styles.bannerSub}>{statusSubtitle}</Text>
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

        {/* Coupe (3 onglets) */}
        <SectionTitle>Coupes</SectionTitle>
        <View style={styles.tabs} testID="section-tabs">
          <SectionTab
            active={sectionKind === 'long'} label="Coupe long."
            onPress={() => setSectionKind('long')} testID="tab-section-long"
          />
          <SectionTab
            active={sectionKind === 'trans'} label="Coupe trans."
            onPress={() => setSectionKind('trans')} testID="tab-section-trans"
          />
          <SectionTab
            active={sectionKind === 'axial'} label="Coupe axe"
            onPress={() => setSectionKind('axial')} testID="tab-section-axial"
          />
        </View>
        <View style={styles.svgWrap} testID="section-svg">
          {sectionKind === 'long' && (
            <StairSection input={input} result={r} width={screenW} height={280} />
          )}
          {sectionKind === 'trans' && (
            <StairSectionTransverse input={input} result={r} width={screenW} height={280} />
          )}
          {sectionKind === 'axial' && (
            <StairSectionAxial input={input} result={r} width={screenW} height={280} />
          )}
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
            testID="concrete-btn"
            label="Analyse béton armé"
            variant="primary"
            onPress={() => router.push({ pathname: '/concrete', params: { projectId: project.id } })}
            fullWidth
          />
          <View style={{ height: spacing.s }} />
          <Button
            testID="export-pdf-btn"
            label={exporting ? 'Génération…' : 'Exporter dossier PDF'}
            variant="secondary"
            onPress={handleExportPDF}
            loading={exporting}
            disabled={exporting}
            fullWidth
          />
          <View style={{ height: spacing.s }} />
          <Button
            testID="edit-btn"
            label="Modifier dimensions"
            variant="secondary"
            onPress={() => router.push({ pathname: '/form', params: { type: project.type, projectId: project.id } })}
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
    'helicoidal': 'Hélicoïdal',
  };
  return M[t];
}
function SectionTitle({ children }: { children: string }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

function SectionTab({
  active, label, onPress, testID,
}: { active: boolean; label: string; onPress: () => void; testID: string }) {
  return (
    <TouchableOpacity
      testID={testID}
      onPress={onPress}
      style={[styles.tab, active && styles.tabActive]}
      activeOpacity={0.8}
    >
      <Text style={[styles.tabText, active && styles.tabTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
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
  tabs: {
    flexDirection: 'row',
    marginBottom: spacing.s,
    borderRadius: radius.s,
    backgroundColor: colors.bgSubtle,
    padding: 3,
  },
  tab: {
    flex: 1,
    paddingVertical: spacing.s,
    paddingHorizontal: spacing.s,
    alignItems: 'center',
    borderRadius: radius.s - 1,
  },
  tabActive: {
    backgroundColor: colors.bg,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  tabText: { ...typography.small, color: colors.textMuted, fontWeight: '600' },
  tabTextActive: { color: colors.primary },
  actions: { marginTop: spacing.l },
});
