import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, radius, spacing, typography } from '../theme';
import type { AlertLevel } from '../types';

interface Props {
  level: AlertLevel;
  code: string;
  message: string;
}

const LEVEL_STYLES: Record<AlertLevel, { bg: string; fg: string; label: string }> = {
  red: { bg: colors.dangerBg, fg: colors.danger, label: 'CRITIQUE' },
  orange: { bg: colors.warnBg, fg: colors.warn, label: 'ATTENTION' },
  green: { bg: colors.okBg, fg: colors.ok, label: 'OK' },
};

export function AlertRow({ level, code, message }: Props) {
  const s = LEVEL_STYLES[level];
  return (
    <View
      testID={`alert-${code}`}
      style={[styles.wrap, { backgroundColor: s.bg }]}
    >
      <View style={[styles.dot, { backgroundColor: s.fg }]} />
      <View style={styles.body}>
        <View style={styles.row}>
          <Text style={[styles.tag, { color: s.fg }]}>{s.label}</Text>
          <Text style={styles.code}>{code}</Text>
        </View>
        <Text style={styles.message}>{message}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    borderRadius: radius.m,
    padding: spacing.m,
    marginBottom: spacing.s,
    alignItems: 'flex-start',
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginTop: 6,
    marginRight: spacing.m,
  },
  body: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', marginBottom: 2 },
  tag: { ...typography.caption, textTransform: 'uppercase', marginRight: spacing.s },
  code: { ...typography.monoSmall, color: colors.textMuted },
  message: { ...typography.small, color: colors.text, lineHeight: 18 },
});
