import React, { useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, KeyboardAvoidingView, Platform, Alert as RNAlert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Button } from '../src/components/Button';
import { InputField } from '../src/components/InputField';
import { colors, radius, spacing, typography } from '../src/theme';
import { runOptimize } from '../src/api';
import AsyncStorage from '@react-native-async-storage/async-storage';

const OPTIMIZE_CACHE_KEY = 'stairpilot_optimize_result_v1';

interface OptState {
  floor_height_mm: string;
  available_length_mm: string;
  available_width_mm: string;
  stair_width_mm: string;
  stairwell_length_mm: string;
  stairwell_width_mm: string;
  slab_thickness_mm: string;
  ceiling_height_mm: string;
}

const DEFAULTS: OptState = {
  floor_height_mm: '2800',
  available_length_mm: '3500',
  available_width_mm: '2200',
  stair_width_mm: '900',
  stairwell_length_mm: '2800',
  stairwell_width_mm: '1000',
  slab_thickness_mm: '200',
  ceiling_height_mm: '2800',
};

function n(v: string) {
  if (!v || !v.trim()) return undefined;
  const x = Number(v.replace(',', '.'));
  return Number.isFinite(x) ? x : undefined;
}

export default function OptimizeScreen() {
  const router = useRouter();
  const [s, setS] = useState<OptState>(DEFAULTS);
  const [loading, setLoading] = useState(false);

  const set = <K extends keyof OptState>(k: K, v: OptState[K]) =>
    setS((prev) => ({ ...prev, [k]: v }));

  const search = async () => {
    if (!n(s.floor_height_mm) || !n(s.available_length_mm) || !n(s.available_width_mm)) {
      RNAlert.alert('Champs manquants', 'Hauteur, longueur et largeur disponibles requises.');
      return;
    }
    setLoading(true);
    try {
      const body: any = {
        floor_height_mm: n(s.floor_height_mm),
        available_length_mm: n(s.available_length_mm),
        available_width_mm: n(s.available_width_mm),
        stair_width_mm: n(s.stair_width_mm) ?? 900,
        stairwell_length_mm: n(s.stairwell_length_mm) ?? null,
        stairwell_width_mm: n(s.stairwell_width_mm) ?? null,
        slab_thickness_mm: n(s.slab_thickness_mm) ?? 200,
        ceiling_height_mm: n(s.ceiling_height_mm) ?? null,
        tread_thickness_mm: 30,
        has_risers: true,
        max_solutions: 5,
      };
      const result = await runOptimize(body);
      await AsyncStorage.setItem(OPTIMIZE_CACHE_KEY, JSON.stringify(result));
      router.push('/compare');
    } catch (e: any) {
      RNAlert.alert('Erreur', e?.message ?? 'Erreur inconnue');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <Text style={styles.title}>Optimisation automatique</Text>
          <Text style={styles.subtitle}>
            Saisissez les contraintes du chantier. Le moteur teste 5 typologies et vous propose
            les meilleures solutions triées par score.
          </Text>

          <Section title="Hauteurs">
            <InputField testID="opt-floor-height" label="Hauteur sol à sol" value={s.floor_height_mm} onChangeText={(v) => set('floor_height_mm', v)} />
            <InputField testID="opt-ceiling" label="Hauteur sous plafond" value={s.ceiling_height_mm} onChangeText={(v) => set('ceiling_height_mm', v)} />
            <InputField testID="opt-slab" label="Épaisseur dalle" value={s.slab_thickness_mm} onChangeText={(v) => set('slab_thickness_mm', v)} />
          </Section>
          <Section title="Espace disponible">
            <InputField testID="opt-length" label="Longueur" value={s.available_length_mm} onChangeText={(v) => set('available_length_mm', v)} />
            <InputField testID="opt-width" label="Largeur" value={s.available_width_mm} onChangeText={(v) => set('available_width_mm', v)} />
            <InputField testID="opt-stair-width" label="Largeur escalier souhaitée" value={s.stair_width_mm} onChangeText={(v) => set('stair_width_mm', v)} />
          </Section>
          <Section title="Trémie (optionnel)">
            <InputField testID="opt-tremie-length" label="Longueur trémie" value={s.stairwell_length_mm} onChangeText={(v) => set('stairwell_length_mm', v)} optional />
            <InputField testID="opt-tremie-width" label="Largeur trémie" value={s.stairwell_width_mm} onChangeText={(v) => set('stairwell_width_mm', v)} optional />
          </Section>

          <View style={{ height: 100 }} />
        </ScrollView>
      </KeyboardAvoidingView>
      <View style={styles.ctaBar}>
        <Button
          testID="opt-search-btn"
          label={loading ? 'Recherche…' : 'Rechercher solutions'}
          onPress={search}
          loading={loading}
          fullWidth
        />
      </View>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ marginBottom: spacing.l }}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.l, paddingBottom: 40 },
  title: { ...typography.h2, color: colors.text, marginBottom: spacing.xs },
  subtitle: { ...typography.small, color: colors.textMuted, marginBottom: spacing.l, lineHeight: 18 },
  sectionTitle: { ...typography.h3, color: colors.text, marginBottom: spacing.m },
  ctaBar: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    padding: spacing.l, backgroundColor: colors.bg,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
});
