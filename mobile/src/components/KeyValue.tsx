import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, typography, radius } from '../theme';

interface Props {
  label: string;
  value: string;
  suffix?: string;
  testID?: string;
}

export function KeyValue({ label, value, suffix, testID }: Props) {
  return (
    <View style={styles.wrap} testID={testID}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text style={styles.value}>{value}</Text>
        {suffix ? <Text style={styles.suffix}>{suffix}</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: colors.bgSubtle,
    borderRadius: radius.m,
    padding: spacing.m,
    marginBottom: spacing.s,
  },
  label: {
    ...typography.caption,
    textTransform: 'uppercase',
    color: colors.textMuted,
    marginBottom: 4,
  },
  valueRow: { flexDirection: 'row', alignItems: 'baseline' },
  value: { ...typography.mono, fontSize: 18, color: colors.text },
  suffix: { ...typography.monoSmall, color: colors.textMuted, marginLeft: 4 },
});
