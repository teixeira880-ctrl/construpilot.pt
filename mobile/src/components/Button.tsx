import React from 'react';
import { Text, TouchableOpacity, StyleSheet, ActivityIndicator, View } from 'react-native';
import { colors, radius, spacing, typography } from '../theme';

interface Props {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  disabled?: boolean;
  loading?: boolean;
  testID?: string;
  fullWidth?: boolean;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  loading,
  testID,
  fullWidth,
}: Props) {
  const s = styles[variant];
  const inactive = disabled || loading;
  return (
    <TouchableOpacity
      testID={testID}
      onPress={onPress}
      disabled={inactive}
      activeOpacity={0.85}
      style={[
        styles.base,
        s.container,
        inactive && styles.disabled,
        fullWidth && styles.fullWidth,
      ]}
    >
      <View style={styles.inner}>
        {loading && <ActivityIndicator size="small" color={s.text.color} style={{ marginRight: 8 }} />}
        <Text style={[styles.labelBase, s.text]}>{label}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.m,
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.m,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
  },
  fullWidth: { alignSelf: 'stretch' },
  inner: { flexDirection: 'row', alignItems: 'center' },
  labelBase: { ...typography.bodyStrong },
  disabled: { opacity: 0.5 },
  primary: {
    container: { backgroundColor: colors.primary },
    text: { color: '#FFFFFF' },
  },
  secondary: {
    container: {
      backgroundColor: colors.bg,
      borderWidth: 1,
      borderColor: colors.border,
    },
    text: { color: colors.text },
  },
  ghost: {
    container: { backgroundColor: 'transparent' },
    text: { color: colors.primary },
  },
  danger: {
    container: { backgroundColor: colors.danger },
    text: { color: '#FFFFFF' },
  },
} as any);
