import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, Dimensions, TouchableOpacity,
  Alert as RNAlert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams } from 'expo-router';
import Svg, { Rect, Line, Path, Circle, Text as SvgText, G } from 'react-native-svg';
import { colors, radius, spacing, typography } from '../src/theme';
import { KeyValue } from '../src/components/KeyValue';
import { AlertRow } from '../src/components/AlertRow';
import { analyzeConcrete } from '../src/api';
import { getProject } from '../src/storage';

const CLASSES = ['C20/25', 'C25/30', 'C30/37'];
const STEELS = ['B500A', 'B500B'];
const EXPOSURES = ['XC1', 'XC2', 'XC3', 'XC4'];
const LIVE_LOADS = [2.5, 4.0, 5.0];

export default function ConcreteScreen() {
  const params = useLocalSearchParams<{ projectId: string }>();
  const [proj, setProj] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [concreteClass, setConcreteClass] = useState('C25/30');
  const [steel, setSteel] = useState('B500B');
  const [exposure, setExposure] = useState('XC1');
  const [liveLoad, setLiveLoad] = useState(2.5);
  const [section, setSection] = useState<'metre' | 'structure' | 'ferraillage'>('metre');

  const compute = useCallback(async (p: any) => {
    if (!p?.result) return;
    setLoading(true);
    try {
      const res = await analyzeConcrete({
        stair_result: p.result,
        stair_type: p.type ?? 'straight',
        concrete_class: concreteClass,
        steel_grade: steel,
        exposure_class: exposure,
        live_load_kN_m2: liveLoad,
      });
      setData(res);
    } catch (e: any) {
      RNAlert.alert('Erreur', e?.message ?? 'Erreur analyse béton');
    } finally {
      setLoading(false);
    }
  }, [concreteClass, steel, exposure, liveLoad]);

  useEffect(() => {
    (async () => {
      if (params.projectId) {
        const p = await getProject(params.projectId);
        setProj(p);
        if (p) await compute(p);
      }
    })();
  }, [params.projectId]);

  useEffect(() => { if (proj) compute(proj); }, [concreteClass, steel, exposure, liveLoad]);

  if (loading && !data) {
    return <SafeAreaView style={styles.center}><ActivityIndicator /></SafeAreaView>;
  }
  if (!data) {
    return <SafeAreaView style={styles.center}><Text>Aucun projet</Text></SafeAreaView>;
  }

  const q = data.quantities;
  const p = data.paillasse;
  const rf = data.reinforcement;
  const load = data.load_breakdown_kN_m2;

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      {/* Disclaimer permanent non-dismissible */}
      <View style={styles.disclaimer} testID="concrete-disclaimer">
        <Text style={styles.disclaimerTag}>⚠ AVERTISSEMENT</Text>
        <Text style={styles.disclaimerText}>{data.disclaimer.message_fr}</Text>
      </View>

      {/* Tabs */}
      <View style={styles.tabs}>
        {(['metre', 'structure', 'ferraillage'] as const).map((s) => (
          <TouchableOpacity
            key={s}
            testID={`tab-${s}`}
            onPress={() => setSection(s)}
            style={[styles.tab, section === s && styles.tabActive]}
          >
            <Text style={[styles.tabText, section === s && styles.tabTextActive]}>
              {s === 'metre' ? 'Métré' : s === 'structure' ? 'Structure' : 'Ferraillage'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {section === 'metre' && (
          <View testID="section-metre">
            <SectionTitle>Chiffres clés</SectionTitle>
            <View style={styles.grid}>
              <KeyValue label="Volume béton" value={String(q.concrete_volume_m3)} suffix="m³" />
              <KeyValue label="Surface coffrage" value={String(q.formwork_area_m2)} suffix="m²" />
              <KeyValue label="Marches" value={String(Math.round(q.tread_count))} suffix="" />
              <KeyValue label="Contremarches" value={String(Math.round(q.riser_count))} suffix="" />
            </View>
            <SectionTitle>Détail géométrique</SectionTitle>
            <Row k="Paillasse (L × l × ép)" v={`${q.paillasse_length_mm} × ${q.width_mm} × ${q.paillasse_thickness_mm} mm`} />
            <Row k="Surface paillasse" v={`${q.paillasse_area_m2} m²`} />
            <Row k="Volume paillasse" v={`${q.paillasse_volume_m3} m³`} />
            <Row k="Volume marches" v={`${q.tread_volume_m3} m³`} />
          </View>
        )}

        {section === 'structure' && (
          <View testID="section-structure">
            <SelectorRow label="Classe béton" value={concreteClass} options={CLASSES} onChange={setConcreteClass} testID="sel-concrete" />
            <SelectorRow label="Nuance acier" value={steel} options={STEELS} onChange={setSteel} testID="sel-steel" />
            <SelectorRow label="Exposition" value={exposure} options={EXPOSURES} onChange={setExposure} testID="sel-exposure" />
            <SelectorRow label="Charge variable (kN/m²)" value={String(liveLoad)} options={LIVE_LOADS.map(String)} onChange={(v) => setLiveLoad(Number(v))} testID="sel-load" />

            <SectionTitle>Charges (ELS)</SectionTitle>
            <Row k="Charge variable" v={`${load.live_load} kN/m²`} />
            <Row k="Charge permanente extra" v={`${load.dead_load_extra} kN/m²`} />
            <Row k="Poids propre paillasse" v={`${load.self_weight} kN/m²`} />
            <Row k="Total ELS" v={`${load.total_ELS} kN/m²`} />
            <Row k="Total ELU (1.35G + 1.5Q)" v={`${load.total_ELU} kN/m²`} />

            <SectionTitle>Paillasse</SectionTitle>
            <Row k="Portée" v={`${p.span_mm} mm`} />
            <Row k="Épaisseur mini L/25" v={`${p.thickness_min_L25_mm} mm`} />
            <Row k="Épaisseur recommandée" v={`${p.thickness_recommended_mm} mm`} />
            <Row k="Abaque utilisé" v={p.abaque_used} />
            <Row k="Enrobage" v={`${rf.cover_mm} mm`} />
          </View>
        )}

        {section === 'ferraillage' && (
          <View testID="section-ferraillage">
            <ReinforcementSchema data={data} width={Dimensions.get('window').width - 2 * spacing.l} />
            <SectionTitle>Nomenclature aciers</SectionTitle>
            <View style={styles.nomHeader}>
              <Text style={[styles.nomCell, { flex: 0.4 }]}>Rep</Text>
              <Text style={[styles.nomCell, { flex: 1.8 }]}>Désignation</Text>
              <Text style={[styles.nomCell, { flex: 0.8 }]}>Ø</Text>
              <Text style={[styles.nomCell, { flex: 0.6 }]}>Nb</Text>
              <Text style={[styles.nomCell, { flex: 0.8, textAlign: 'right' }]}>Poids</Text>
            </View>
            {data.nomenclature.map((row: any) => (
              <View key={row.repere} style={styles.nomRow}>
                <Text style={[styles.nomCell, { flex: 0.4 }]}>{row.repere}</Text>
                <Text style={[styles.nomCell, { flex: 1.8, fontSize: 12 }]}>{row.designation}</Text>
                <Text style={[styles.nomCell, { flex: 0.8 }]}>{row.diameter}</Text>
                <Text style={[styles.nomCell, { flex: 0.6 }]}>{row.count}</Text>
                <Text style={[styles.nomCell, { flex: 0.8, textAlign: 'right' }]}>{row.weight_kg} kg</Text>
              </View>
            ))}
            <View style={styles.totalRow}>
              <Text style={styles.totalLabel}>Total acier HA</Text>
              <Text style={styles.totalValue}>{rf.total_steel_kg} kg</Text>
            </View>
          </View>
        )}

        <SectionTitle>Alertes</SectionTitle>
        {data.alerts.map((a: any, i: number) => (
          <AlertRow key={i} level={a.level} code={a.code} message={a.message} />
        ))}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function ReinforcementSchema({ data, width }: { data: any; width: number }) {
  const rf = data.reinforcement;
  const q = data.quantities;
  const W = width;
  const H = 200;
  const L = q.paillasse_length_mm;
  const T = q.paillasse_thickness_mm;
  const scale = Math.min((W - 60) / L, (H - 40) / (T * 4));
  const x0 = 30;
  const y0 = H - 30;
  const pl = L * scale;
  const pt = T * scale * 3;

  return (
    <View testID="reinforcement-svg" style={styles.svgWrap}>
      <Svg width={W} height={H}>
        <Rect x={0} y={0} width={W} height={H} fill="#FFFFFF" />
        {/* Paillasse (coupe) */}
        <Rect x={x0} y={y0 - pt} width={pl} height={pt}
          stroke={colors.text} strokeWidth={1.2} fill="none" />
        {/* Armatures principales (fibre inférieure - bleu) */}
        <Line x1={x0 + 5} y1={y0 - 8} x2={x0 + pl - 5} y2={y0 - 8}
          stroke="#0B5FFF" strokeWidth={2.2} />
        <SvgText x={x0 + pl / 2} y={y0 - 12} fontSize="9" fill="#0B5FFF" textAnchor="middle">
          Rep 1 · HA{rf.main_bars.diameter_mm} @ {rf.main_bars.spacing_mm}mm
        </SvgText>
        {/* Chapeaux (rouge) sur les appuis */}
        <Line x1={x0} y1={y0 - pt + 8} x2={x0 + pl * 0.28} y2={y0 - pt + 8}
          stroke="#D64545" strokeWidth={2} />
        <Line x1={x0 + pl * 0.72} y1={y0 - pt + 8} x2={x0 + pl} y2={y0 - pt + 8}
          stroke="#D64545" strokeWidth={2} />
        <SvgText x={x0 + pl / 2} y={y0 - pt + 5} fontSize="9" fill="#D64545" textAnchor="middle">
          Rep 3 · HA{rf.upper_bars.diameter_mm} chapeaux
        </SvgText>
        {/* Répartition (verts) - petits traits transversaux */}
        {Array.from({ length: 8 }).map((_, i) => (
          <Line key={i}
            x1={x0 + (pl * (i + 1)) / 9} y1={y0 - 12}
            x2={x0 + (pl * (i + 1)) / 9} y2={y0 - pt + 12}
            stroke="#2F8F55" strokeWidth={0.7} strokeDasharray="2 2" />
        ))}
        {/* Attentes en pied (bleu courbé) */}
        <Path d={`M ${x0 + 5} ${y0 - 8} L ${x0 + 5} ${y0 + 10} L ${x0 - 15} ${y0 + 10}`}
          stroke="#0B5FFF" strokeWidth={2} fill="none" />
        {/* Légende */}
        <G>
          <Rect x={W - 130} y={10} width={125} height={54} stroke={colors.border} strokeWidth={0.5} fill="#F5F6F8" />
          <Line x1={W - 122} y1={22} x2={W - 108} y2={22} stroke="#0B5FFF" strokeWidth={2} />
          <SvgText x={W - 104} y={25} fontSize="9" fill={colors.text}>Principales</SvgText>
          <Line x1={W - 122} y1={36} x2={W - 108} y2={36} stroke="#D64545" strokeWidth={2} />
          <SvgText x={W - 104} y={39} fontSize="9" fill={colors.text}>Chapeaux</SvgText>
          <Line x1={W - 122} y1={50} x2={W - 108} y2={50} stroke="#2F8F55" strokeWidth={2} strokeDasharray="2 2" />
          <SvgText x={W - 104} y={53} fontSize="9" fill={colors.text}>Répartition</SvgText>
        </G>
      </Svg>
    </View>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowKey}>{k}</Text>
      <Text style={styles.rowVal}>{v}</Text>
    </View>
  );
}
function SectionTitle({ children }: { children: string }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}
function SelectorRow({ label, value, options, onChange, testID }: any) {
  return (
    <View style={{ marginBottom: spacing.m }} testID={testID}>
      <Text style={styles.selLabel}>{label.toUpperCase()}</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.s as any }}>
        {options.map((opt: string) => {
          const active = opt === value;
          return (
            <TouchableOpacity key={opt}
              testID={`${testID}-${opt}`}
              onPress={() => onChange(opt)}
              style={[styles.selBtn, active && styles.selBtnActive]}
            >
              <Text style={[styles.selText, active && styles.selTextActive]}>{opt}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  disclaimer: {
    backgroundColor: colors.warnBg, borderBottomWidth: 2, borderBottomColor: colors.warn,
    padding: spacing.m,
  },
  disclaimerTag: { ...typography.caption, color: colors.warn, marginBottom: 2 },
  disclaimerText: { ...typography.small, color: colors.text, lineHeight: 17 },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: colors.border },
  tab: { flex: 1, paddingVertical: spacing.m, alignItems: 'center' },
  tabActive: { borderBottomWidth: 2, borderBottomColor: colors.primary },
  tabText: { ...typography.bodyStrong, color: colors.textMuted },
  tabTextActive: { color: colors.primary },
  scroll: { padding: spacing.l },
  sectionTitle: { ...typography.caption, color: colors.textMuted, textTransform: 'uppercase', marginTop: spacing.m, marginBottom: spacing.s },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.s as any },
  row: { flexDirection: 'row', paddingVertical: spacing.s, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowKey: { ...typography.small, color: colors.textMuted, flex: 1 },
  rowVal: { ...typography.mono, color: colors.text, fontSize: 13 },
  selLabel: { ...typography.caption, color: colors.textMuted, marginBottom: spacing.xs },
  selBtn: { borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.m, paddingVertical: spacing.s, borderRadius: radius.s, marginRight: spacing.xs },
  selBtnActive: { borderColor: colors.primary, backgroundColor: colors.primaryBg },
  selText: { ...typography.small, color: colors.textMuted },
  selTextActive: { color: colors.primary, fontWeight: '700' },
  svgWrap: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.m, backgroundColor: colors.bg, marginBottom: spacing.m, overflow: 'hidden' },
  nomHeader: { flexDirection: 'row', paddingVertical: spacing.s, borderBottomWidth: 2, borderBottomColor: colors.text },
  nomRow: { flexDirection: 'row', paddingVertical: spacing.s, borderBottomWidth: 1, borderBottomColor: colors.border },
  nomCell: { ...typography.mono, fontSize: 12, color: colors.text },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: spacing.m, borderTopWidth: 2, borderTopColor: colors.text, marginTop: spacing.s },
  totalLabel: { ...typography.bodyStrong, color: colors.text },
  totalValue: { ...typography.mono, fontSize: 16, color: colors.primary },
});
