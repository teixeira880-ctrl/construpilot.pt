import React from 'react';
import { View, Text, StyleSheet, TextInput, KeyboardTypeOptions } from 'react-native';
import { colors, radius, spacing, typography } from '../theme';

interface Props {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  unit?: string;
  keyboardType?: KeyboardTypeOptions;
  testID?: string;
  helper?: string;
  error?: string;
  optional?: boolean;
}

export function InputField({
  label,
  value,
  onChangeText,
  placeholder,
  unit = 'mm',
  keyboardType = 'numeric',
  testID,
  helper,
  error,
  optional,
}: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.labelRow}>
        <Text style={styles.label}>{label}</Text>
        {optional && <Text style={styles.optional}>optionnel</Text>}
      </View>
      <View style={[styles.inputRow, error ? styles.inputRowError : null]}>
        <TextInput
          testID={testID}
          style={styles.input}
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder ?? ''}
          placeholderTextColor={colors.textDim}
          keyboardType={keyboardType}
        />
        <Text style={styles.unit}>{unit}</Text>
      </View>
      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : helper ? (
        <Text style={styles.helperText}>{helper}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.m },
  labelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  label: { ...typography.caption, color: colors.textMuted, textTransform: 'uppercase' },
  optional: { ...typography.caption, color: colors.textDim, textTransform: 'lowercase' },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.m,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.m,
    minHeight: 48,
  },
  inputRowError: { borderColor: colors.danger },
  input: {
    flex: 1,
    ...typography.mono,
    color: colors.text,
    paddingVertical: spacing.s,
  },
  unit: {
    ...typography.monoSmall,
    color: colors.textMuted,
    marginLeft: spacing.s,
  },
  helperText: {
    ...typography.small,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },
  errorText: {
    ...typography.small,
    color: colors.danger,
    marginTop: spacing.xs,
  },
});
