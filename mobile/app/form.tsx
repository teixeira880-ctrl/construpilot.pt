import React, { useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, KeyboardAvoidingView, Platform,
  TouchableOpacity, ActivityIndicator, Alert as RNAlert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Button } from '../src/components/Button';
import { InputField } from '../src/components/InputField';
import { colors, radius, spacing, typography } from '../src/theme';
import type { StairType, QuarterTurnInput, HalfTurnInput, StairInput } from '../src/types';
import { STAIR_TYPE_LABELS } from '../src/types';
import { computeStair } from '../src/api';
import { saveProject } from '../src/storage';

interface FormState {
  name: string;
  floor_height_mm: string;
  ceiling_height_mm: string;
  slab_thickness_mm: string;
  available_length_mm: string;
  available_width_mm: string;
  stair_width_mm: string;
  tread_thickness_mm: string;
  has_risers: boolean;
  stairwell_length_mm: string;
  stairwell_width_mm: string;
  stairwell_offset_mm: string;
  direction: 'left' | 'right';
  balancing: 'balanced' | 'straight';
  num_winders: string; // 'auto' or number
  walkline_offset_mm: string;
  landing_length_mm: string;
  landing_width_mm: string;
}

const DEFAULT_STATE: FormState = {
  name: '',
  floor_height_mm: '2800',
  ceiling_height_mm: '2800',
  slab_thickness_mm: '200',
  available_length_mm: '4500',
  available_width_mm: '1500',
  stair_width_mm: '900',
  tread_thickness_mm: '30',
  has_risers: true,
  stairwell_length_mm: '3200',
  stairwell_width_mm: '1000',
  stairwell_offset_mm: '',
  direction: 'right',
  balancing: 'balanced',
  num_winders: 'auto',
  walkline_offset_mm: '500',
  landing_length_mm: '',
  landing_width_mm: '',
};

function parseNum(v: string): number | undefined {
  if (!v || !v.trim()) return undefined;
  const n = Number(v.replace(',', '.'));
  return Number.isFinite(n) ? n : undefined;
}

export default function FormScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ type: StairType }>();
  const type = (params.type ?? 'straight') as StairType;
  const isQt = type === 'quarter-turn-bottom' || type === 'quarter-turn-top';
  const isHalf = type === 'half-turn';
  const isTurn = isQt || isHalf;

  const [state, setState] = useState<FormState>(DEFAULT_STATE);
  const [loading, setLoading] = useState(false);

  const setField = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setState((s) => ({ ...s, [k]: v }));

  const validationError = useMemo(() => validate(state), [state]);

  const onCompute = async () => {
    if (validationError) {
      RNAlert.alert('Champs incomplets', validationError);
      return;
    }
    setLoading(true);
    try {
      const input = buildInput(type, state);
      const result = await computeStair(type, input);
      const project = await saveProject({
        name: state.name || `${STAIR_TYPE_LABELS[type]} — ${state.floor_height_mm} mm`,
        type,
        input,
        result,
      });
      router.replace({ pathname: '/result', params: { projectId: project.id } });
    } catch (e: any) {
      RNAlert.alert('Erreur de calcul', e?.message ?? 'Erreur inconnue');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.pageType}>{STAIR_TYPE_LABELS[type]}</Text>

          <Section title="Identification">
            <InputField
              testID="input-name"
              label="Nom du projet"
              value={state.name}
              onChangeText={(v) => setField('name', v)}
              placeholder="Ex : maison Dupont — RDC"
              unit="" keyboardType="default"
              optional
            />
          </Section>

          <Section title="Hauteurs">
            <InputField
              testID="input-floor-height"
              label="Hauteur sol à sol"
              value={state.floor_height_mm}
              onChangeText={(v) => setField('floor_height_mm', v)}
            />
            <InputField
              testID="input-ceiling-height"
              label="Hauteur sous plafond"
              value={state.ceiling_height_mm}
              onChangeText={(v) => setField('ceiling_height_mm', v)}
              helper="Sol bas → sous-face de la dalle haute"
            />
            <InputField
              testID="input-slab"
              label="Épaisseur dalle"
              value={state.slab_thickness_mm}
              onChangeText={(v) => setField('slab_thickness_mm', v)}
            />
          </Section>

          <Section title="Espace disponible">
            <InputField
              testID="input-length"
              label="Longueur"
              value={state.available_length_mm}
              onChangeText={(v) => setField('available_length_mm', v)}
            />
            <InputField
              testID="input-width"
              label="Largeur"
              value={state.available_width_mm}
              onChangeText={(v) => setField('available_width_mm', v)}
            />
          </Section>

          <Section title="Escalier">
            <InputField
              testID="input-stair-width"
              label="Largeur souhaitée"
              value={state.stair_width_mm}
              onChangeText={(v) => setField('stair_width_mm', v)}
              helper="Recommandé ≥ 700 mm"
            />
            <InputField
              testID="input-tread-thickness"
              label="Épaisseur marches"
              value={state.tread_thickness_mm}
              onChangeText={(v) => setField('tread_thickness_mm', v)}
            />
            <TwoOptions
              label="Contremarches"
              options={[{ v: true, l: 'Oui' }, { v: false, l: 'Non' }]}
              value={state.has_risers}
              onChange={(v) => setField('has_risers', v as boolean)}
              testID="toggle-risers"
            />
          </Section>

          <Section title="Trémie (optionnel)">
            <InputField
              testID="input-tremie-length"
              label="Longueur trémie"
              value={state.stairwell_length_mm}
              onChangeText={(v) => setField('stairwell_length_mm', v)}
              optional
            />
            <InputField
              testID="input-tremie-width"
              label="Largeur trémie"
              value={state.stairwell_width_mm}
              onChangeText={(v) => setField('stairwell_width_mm', v)}
              optional
            />
            <InputField
              testID="input-tremie-offset"
              label="Offset depuis départ"
              value={state.stairwell_offset_mm}
              onChangeText={(v) => setField('stairwell_offset_mm', v)}
              helper="Distance horizontale nez marche 1 → bord bas trémie"
              optional
            />
          </Section>

          {isTurn && (
            <Section title="Options tournant">
              <TwoOptions
                label="Sens de montée"
                options={[{ v: 'right', l: 'Droite' }, { v: 'left', l: 'Gauche' }]}
                value={state.direction}
                onChange={(v) => setField('direction', v as any)}
                testID="toggle-direction"
              />
              <TwoOptions
                label="Mode balancement"
                options={[
                  { v: 'balanced', l: 'Marches balancées' },
                  { v: 'straight', l: 'Palier rectangulaire' },
                ]}
                value={state.balancing}
                onChange={(v) => setField('balancing', v as any)}
                testID="toggle-balancing"
              />
              {state.balancing === 'balanced' && (
                <>
                  <InputField
                    testID="input-num-winders"
                    label="Nombre de balancées"
                    value={state.num_winders}
                    onChangeText={(v) => setField('num_winders', v)}
                    unit=""
                    keyboardType="default"
                    helper="'auto' ou un entier entre 3 et 9 (12 pour DT)"
                  />
                  <InputField
                    testID="input-walkline"
                    label="Ligne de foulée"
                    value={state.walkline_offset_mm}
                    onChangeText={(v) => setField('walkline_offset_mm', v)}
                    helper="Distance depuis limon intérieur"
                  />
                </>
              )}
              {state.balancing === 'straight' && (
                <>
                  <InputField
                    testID="input-landing-length"
                    label="Longueur palier"
                    value={state.landing_length_mm}
                    onChangeText={(v) => setField('landing_length_mm', v)}
                    optional
                  />
                  <InputField
                    testID="input-landing-width"
                    label="Largeur palier"
                    value={state.landing_width_mm}
                    onChangeText={(v) => setField('landing_width_mm', v)}
                    optional
                  />
                </>
              )}
            </Section>
          )}

          <View style={{ height: 100 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      <View style={styles.ctaBar}>
        <Button
          testID="compute-btn"
          label={loading ? 'Calcul en cours…' : 'Calculer'}
          onPress={onCompute}
          loading={loading}
          fullWidth
        />
      </View>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={sectionStyles.section}>
      <Text style={sectionStyles.title}>{title}</Text>
      {children}
    </View>
  );
}

function TwoOptions<T>({
  label, options, value, onChange, testID,
}: {
  label: string;
  options: { v: T; l: string }[];
  value: T;
  onChange: (v: T) => void;
  testID?: string;
}) {
  return (
    <View style={{ marginBottom: spacing.m }} testID={testID}>
      <Text style={sectionStyles.optLabel}>{label.toUpperCase()}</Text>
      <View style={sectionStyles.optRow}>
        {options.map((o, idx) => {
          const active = o.v === value;
          return (
            <TouchableOpacity
              key={idx}
              onPress={() => onChange(o.v)}
              testID={`${testID}-${String(o.v)}`}
              style={[sectionStyles.optBtn, active && sectionStyles.optBtnActive]}
              activeOpacity={0.85}
            >
              <Text style={[sectionStyles.optText, active && sectionStyles.optTextActive]}>
                {o.l}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

function validate(s: FormState): string | null {
  const req = (v: string) => v && v.trim().length > 0;
  if (!req(s.floor_height_mm) || !parseNum(s.floor_height_mm)) return 'Hauteur sol à sol requise.';
  if (!req(s.available_length_mm)) return 'Longueur disponible requise.';
  if (!req(s.available_width_mm)) return 'Largeur disponible requise.';
  if (!req(s.stair_width_mm)) return 'Largeur d\'escalier requise.';
  return null;
}

function buildInput(type: StairType, s: FormState): StairInput | QuarterTurnInput | HalfTurnInput {
  const base: StairInput = {
    floor_height_mm: parseNum(s.floor_height_mm)!,
    available_length_mm: parseNum(s.available_length_mm)!,
    available_width_mm: parseNum(s.available_width_mm)!,
    stair_width_mm: parseNum(s.stair_width_mm)!,
    stairwell_length_mm: parseNum(s.stairwell_length_mm) ?? null,
    stairwell_width_mm: parseNum(s.stairwell_width_mm) ?? null,
    stairwell_offset_mm: parseNum(s.stairwell_offset_mm) ?? null,
    slab_thickness_mm: parseNum(s.slab_thickness_mm) ?? 200,
    ceiling_height_mm: parseNum(s.ceiling_height_mm) ?? null,
    tread_thickness_mm: parseNum(s.tread_thickness_mm) ?? 30,
    has_risers: s.has_risers,
    direction: s.direction,
  };
  if (type === 'straight') return base;

  const nw = s.num_winders.trim().toLowerCase();
  const num_winders: number | 'auto' = nw === 'auto' || nw === '' ? 'auto' : (parseInt(nw, 10) || 'auto');

  const extended: QuarterTurnInput | HalfTurnInput = {
    ...base,
    balancing: s.balancing,
    num_winders,
    walkline_offset_mm: parseNum(s.walkline_offset_mm) ?? 500,
    inner_radius_mm: 0,
    landing_length_mm: parseNum(s.landing_length_mm) ?? null,
    ...(type !== 'half-turn' ? { landing_width_mm: parseNum(s.landing_width_mm) ?? null } : {}),
  } as any;
  return extended;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.l, paddingBottom: 40 },
  pageType: {
    ...typography.caption,
    color: colors.primary,
    marginBottom: spacing.m,
    textTransform: 'uppercase',
  },
  ctaBar: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    padding: spacing.l, backgroundColor: colors.bg,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
});
const sectionStyles = StyleSheet.create({
  section: { marginBottom: spacing.l },
  title: { ...typography.h3, color: colors.text, marginBottom: spacing.m },
  optLabel: {
    ...typography.caption,
    color: colors.textMuted,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
  },
  optRow: { flexDirection: 'row', gap: spacing.s as any },
  optBtn: {
    flex: 1,
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.m,
    paddingVertical: spacing.m,
    alignItems: 'center',
    marginRight: spacing.s,
  },
  optBtnActive: { borderColor: colors.primary, backgroundColor: colors.primaryBg },
  optText: { ...typography.bodyStrong, color: colors.textMuted },
  optTextActive: { color: colors.primary },
});
