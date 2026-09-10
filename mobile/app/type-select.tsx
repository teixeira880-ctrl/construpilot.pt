import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Svg, { Path, Line, Rect } from 'react-native-svg';
import { Button } from '../src/components/Button';
import { colors, radius, spacing, typography } from '../src/theme';
import type { StairType } from '../src/types';
import { STAIR_TYPE_LABELS, STAIR_TYPE_DESCRIPTIONS } from '../src/types';

const TYPES: StairType[] = ['straight', 'quarter-turn-bottom', 'quarter-turn-top', 'half-turn', 'helicoidal'];

export default function TypeSelectScreen() {
  const router = useRouter();
  const [selected, setSelected] = useState<StairType | null>(null);

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>Choisissez le type d'escalier</Text>
        <Text style={styles.subtitle}>4 typologies disponibles en Phase 1.</Text>

        <View style={styles.grid}>
          {TYPES.map((t) => {
            const active = selected === t;
            return (
              <TouchableOpacity
                key={t}
                testID={`type-card-${t}`}
                activeOpacity={0.85}
                onPress={() => setSelected(t)}
                style={[styles.card, active && styles.cardActive]}
              >
                <View style={styles.icon}>
                  <TypeIcon type={t} />
                </View>
                <Text style={styles.cardTitle}>{STAIR_TYPE_LABELS[t]}</Text>
                <Text style={styles.cardDesc}>{STAIR_TYPE_DESCRIPTIONS[t]}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </ScrollView>

      <View style={styles.ctaBar}>
        <Button
          testID="next-btn"
          label="Suivant"
          onPress={() => selected && router.push({ pathname: '/form', params: { type: selected } })}
          disabled={!selected}
          fullWidth
        />
      </View>
    </SafeAreaView>
  );
}

function TypeIcon({ type }: { type: StairType }) {
  const stroke = colors.text;
  if (type === 'straight') {
    return (
      <Svg width={64} height={40} viewBox="0 0 64 40">
        <Path d="M4,36 L4,30 L12,30 L12,24 L20,24 L20,18 L28,18 L28,12 L36,12 L36,6 L60,6"
          stroke={stroke} strokeWidth={1.5} fill="none" />
      </Svg>
    );
  }
  if (type === 'quarter-turn-bottom') {
    return (
      <Svg width={64} height={54} viewBox="0 0 64 54">
        <Rect x={4} y={4} width={20} height={46} stroke={stroke} strokeWidth={1.2} fill="none" />
        <Path d="M24,50 L60,50 L60,32" stroke={stroke} strokeWidth={1.5} fill="none" />
        <Line x1={30} y1={50} x2={30} y2={40} stroke={stroke} strokeWidth={1} />
        <Line x1={38} y1={50} x2={38} y2={40} stroke={stroke} strokeWidth={1} />
        <Line x1={46} y1={50} x2={46} y2={40} stroke={stroke} strokeWidth={1} />
        <Line x1={54} y1={50} x2={54} y2={40} stroke={stroke} strokeWidth={1} />
      </Svg>
    );
  }
  if (type === 'quarter-turn-top') {
    return (
      <Svg width={64} height={54} viewBox="0 0 64 54">
        <Path d="M4,50 L44,50 L44,10" stroke={stroke} strokeWidth={1.5} fill="none" />
        <Rect x={44} y={10} width={16} height={20} stroke={stroke} strokeWidth={1.2} fill="none" />
        <Line x1={12} y1={50} x2={12} y2={40} stroke={stroke} strokeWidth={1} />
        <Line x1={20} y1={50} x2={20} y2={40} stroke={stroke} strokeWidth={1} />
        <Line x1={28} y1={50} x2={28} y2={40} stroke={stroke} strokeWidth={1} />
        <Line x1={36} y1={50} x2={36} y2={40} stroke={stroke} strokeWidth={1} />
      </Svg>
    );
  }
  // half-turn
  if (type === 'half-turn') {
    return (
      <Svg width={64} height={54} viewBox="0 0 64 54">
        <Path d="M4,42 L38,42" stroke={stroke} strokeWidth={1.5} fill="none" />
        <Path d="M38,42 L52,42 L52,20 L38,20" stroke={stroke} strokeWidth={1.5} fill="none" />
        <Path d="M38,20 L4,20" stroke={stroke} strokeWidth={1.5} fill="none" />
        {[10, 18, 26, 34].map((x) => (
          <Line key={`b${x}`} x1={x} y1={42} x2={x} y2={36} stroke={stroke} strokeWidth={0.8} />
        ))}
        {[34, 26, 18, 10].map((x) => (
          <Line key={`t${x}`} x1={x} y1={20} x2={x} y2={26} stroke={stroke} strokeWidth={0.8} />
        ))}
      </Svg>
    );
  }
  // helicoidal
  return (
    <Svg width={64} height={54} viewBox="0 0 64 54">
      <Path d="M32,10 A22,22 0 1 1 31.99,10" stroke={stroke} strokeWidth={1.2} fill="none" />
      <Path d="M32,18 A14,14 0 1 1 31.99,18" stroke={stroke} strokeWidth={1} fill="none" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg, i) => {
        const rad = (deg - 90) * Math.PI / 180;
        return (
          <Line key={i}
            x1={32 + 14 * Math.cos(rad)} y1={32 + 14 * Math.sin(rad)}
            x2={32 + 22 * Math.cos(rad)} y2={32 + 22 * Math.sin(rad)}
            stroke={stroke} strokeWidth={0.8}
          />
        );
      })}
    </Svg>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.l, paddingBottom: 120 },
  title: { ...typography.h2, color: colors.text, marginBottom: spacing.xs },
  subtitle: { ...typography.small, color: colors.textMuted, marginBottom: spacing.l },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  card: {
    width: '48.5%',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.m,
    padding: spacing.l,
    marginBottom: spacing.m,
    backgroundColor: colors.bg,
    minHeight: 170,
  },
  cardActive: { borderColor: colors.primary, backgroundColor: colors.primaryBg },
  icon: { alignItems: 'flex-start', marginBottom: spacing.s },
  cardTitle: { ...typography.h3, color: colors.text, marginBottom: spacing.xs },
  cardDesc: { ...typography.small, color: colors.textMuted, lineHeight: 17 },
  ctaBar: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    padding: spacing.l, backgroundColor: colors.bg,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
});
