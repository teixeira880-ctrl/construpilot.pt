import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity, Alert as RNAlert, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { Button } from '../src/components/Button';
import { colors, radius, spacing, typography } from '../src/theme';
import { listProjects, deleteProject } from '../src/storage';
import type { StoredProject } from '../src/types';
import { STAIR_TYPE_LABELS } from '../src/types';

export default function HomeScreen() {
  const router = useRouter();
  const [projects, setProjects] = useState<StoredProject[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const p = await listProjects();
    setProjects(p);
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const handleDelete = (p: StoredProject) => {
    RNAlert.alert(
      'Supprimer le projet ?',
      `« ${p.name} » sera supprimé définitivement.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Supprimer',
          style: 'destructive',
          onPress: async () => {
            await deleteProject(p.id);
            load();
          },
        },
      ]
    );
  };

  const renderItem = ({ item }: { item: StoredProject }) => {
    const H = (item.input as any).floor_height_mm ?? 0;
    return (
      <TouchableOpacity
        testID={`project-card-${item.id}`}
        activeOpacity={0.7}
        onPress={() => router.push({
          pathname: '/form',
          params: { type: item.type, projectId: item.id },
        })}
        onLongPress={() => handleDelete(item)}
        style={styles.card}
      >
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>{item.name}</Text>
          <Text style={styles.cardType}>{STAIR_TYPE_LABELS[item.type]}</Text>
        </View>
        <View style={styles.cardMetaRow}>
          <Text style={styles.cardMeta}>H = {H} mm</Text>
          <Text style={styles.cardMeta}>
            {new Date(item.updated_at).toLocaleDateString('fr-FR')}
          </Text>
        </View>
        <View style={styles.cardActions}>
          <Text style={styles.hint}>Toucher pour ouvrir · Maintenir pour supprimer</Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>STAIRPILOT</Text>
        <Text style={styles.tagline}>Conception escaliers béton — DTU 36.3</Text>
      </View>

      <FlatList
        data={projects}
        keyExtractor={(p) => p.id}
        renderItem={renderItem}
        contentContainerStyle={styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => {
          setRefreshing(true); await load(); setRefreshing(false);
        }} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Aucun projet</Text>
            <Text style={styles.emptyBody}>
              Créez votre premier projet pour calculer un escalier béton.
            </Text>
          </View>
        }
      />

      <View style={styles.ctaBar}>
        <Button
          testID="new-project-btn"
          label="Nouveau projet"
          onPress={() => router.push('/type-select')}
          fullWidth
        />
        <View style={{ height: spacing.s }} />
        <Button
          testID="optimize-btn"
          label="Optimisation auto"
          variant="secondary"
          onPress={() => router.push('/optimize')}
          fullWidth
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    paddingHorizontal: spacing.l,
    paddingTop: spacing.s,
    paddingBottom: spacing.l,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: { ...typography.h1, color: colors.text, letterSpacing: 1 },
  tagline: { ...typography.small, color: colors.textMuted, marginTop: 2 },

  listContent: { padding: spacing.l, paddingBottom: 120, flexGrow: 1 },

  card: {
    backgroundColor: colors.bg,
    borderRadius: radius.m,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.l,
    marginBottom: spacing.m,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.s,
  },
  cardTitle: { ...typography.h3, color: colors.text, flex: 1, marginRight: 8 },
  cardType: {
    ...typography.caption,
    color: colors.primary,
    backgroundColor: colors.primaryBg,
    paddingHorizontal: spacing.s,
    paddingVertical: 3,
    borderRadius: radius.s,
    overflow: 'hidden',
  },
  cardMetaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.s,
  },
  cardMeta: { ...typography.monoSmall, color: colors.textMuted },
  cardActions: {},
  hint: { ...typography.small, color: colors.textDim },

  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.xxxl,
    padding: spacing.l,
  },
  emptyTitle: { ...typography.h2, color: colors.text, marginBottom: spacing.s },
  emptyBody: { ...typography.body, color: colors.textMuted, textAlign: 'center' },

  ctaBar: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    padding: spacing.l,
    backgroundColor: colors.bg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
});
