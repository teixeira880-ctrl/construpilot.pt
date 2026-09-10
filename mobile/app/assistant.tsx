import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TextInput, ActivityIndicator,
  TouchableOpacity, KeyboardAvoidingView, Platform, Alert as RNAlert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, Stack } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { colors, radius, spacing, typography } from '../src/theme';
import { assistantChat } from '../src/api';
import { saveProject } from '../src/storage';
import type { StairType } from '../src/types';

const STORAGE_KEY = 'stairpilot_assistant_conv_v1';

type Msg = { role: 'user' | 'assistant'; content: string; timestamp: string };
type Solution = {
  rank: number;
  type: string;
  variant?: string;
  score_global: number;
  num_steps: number;
  riser_height_mm: number;
  tread_depth_mm: number;
  blondel_value_mm: number;
  slope_deg: number;
  stair_run_mm: number;
  headroom_mm: number;
  is_buildable: boolean;
  alerts_top?: { level: string; code: string; message: string }[];
};

type StoredConv = {
  conversation_id: string | null;
  messages: Msg[];
  last_solutions: Solution[];
};

const EMPTY_CONV: StoredConv = {
  conversation_id: null,
  messages: [],
  last_solutions: [],
};

export default function AssistantScreen() {
  const router = useRouter();
  const [conv, setConv] = useState<StoredConv>(EMPTY_CONV);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    (async () => {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) {
        try {
          const parsed = JSON.parse(raw);
          setConv({ ...EMPTY_CONV, ...parsed });
        } catch { /* ignore */ }
      }
    })();
  }, []);

  const persist = useCallback(async (c: StoredConv) => {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(c));
  }, []);

  const handleNewConversation = () => {
    RNAlert.alert(
      'Nouvelle conversation',
      'Cela effacera la conversation en cours.',
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Effacer',
          style: 'destructive',
          onPress: async () => {
            setConv(EMPTY_CONV);
            setErrorBanner(null);
            await AsyncStorage.removeItem(STORAGE_KEY);
          },
        },
      ],
    );
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    setErrorBanner(null);
    const now = new Date().toISOString();
    const userMsg: Msg = { role: 'user', content: text, timestamp: now };
    const optimistic: StoredConv = {
      ...conv,
      messages: [...conv.messages, userMsg],
    };
    setConv(optimistic);
    setLoading(true);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);

    try {
      const res = await assistantChat({
        message: text,
        conversation_id: conv.conversation_id ?? null,
      });
      const asstMsg: Msg = {
        role: 'assistant',
        content: res.reply_text,
        timestamp: new Date().toISOString(),
      };
      const updated: StoredConv = {
        conversation_id: res.conversation_id,
        messages: [...optimistic.messages, asstMsg],
        last_solutions: res.computed_solutions.length ? res.computed_solutions as Solution[] : optimistic.last_solutions,
      };
      setConv(updated);
      await persist(updated);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    } catch (e: any) {
      setErrorBanner(e?.message ?? 'Assistant temporairement indisponible');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenSolution = async (s: Solution) => {
    // Créer un projet local à partir de la solution puis ouvrir /result
    const mapType: Record<string, StairType> = {
      'straight': 'straight',
      'quarter_turn_bottom': 'quarter-turn-bottom',
      'quarter_turn_top': 'quarter-turn-top',
      'half_turn': 'half-turn',
      'helicoidal': 'helicoidal',
    };
    const key = (s.type || '').split('_').slice(0, 2).join('_');
    const stairType = mapType[s.type] || mapType[key] || 'straight';

    // Créer un StairResult minimal (le vrai a été calculé côté serveur mais on n'a que le résumé)
    const stubResult = {
      stair_type: s.type,
      num_steps: s.num_steps,
      num_treads: Math.max(1, s.num_steps - 1),
      riser_height_mm: s.riser_height_mm,
      tread_depth_mm: s.tread_depth_mm,
      blondel_value_mm: s.blondel_value_mm,
      slope_deg: s.slope_deg,
      stair_run_mm: s.stair_run_mm,
      stair_length_mm: s.stair_run_mm,
      headroom_mm: s.headroom_mm,
      required_stairwell_mm: {},
      steps_per_flight: [s.num_steps],
      treads: [],
      alerts: (s.alerts_top ?? []).map(a => ({
        level: a.level as any,
        code: a.code,
        message: a.message,
        message_fr: a.message,
      })),
      is_buildable: s.is_buildable,
    };

    // Input minimal pour permettre l'affichage
    const stubInput = {
      floor_height_mm: Math.round(s.num_steps * s.riser_height_mm),
      available_length_mm: s.stair_run_mm + 500,
      available_width_mm: 1500,
      stair_width_mm: 900,
      slab_thickness_mm: 200,
    };

    const proj = await saveProject({
      name: `Assistant · ${s.type} #${s.rank}`,
      type: stairType,
      input: stubInput as any,
      result: stubResult as any,
    });
    router.push({ pathname: '/result', params: { projectId: proj.id } });
  };

  return (
    <SafeAreaView edges={['bottom']} style={styles.container} testID="assistant-screen">
      <Stack.Screen options={{
        title: 'Assistant IA',
        headerRight: () => (
          <TouchableOpacity onPress={handleNewConversation} testID="new-conversation-btn">
            <Text style={styles.headerAction}>Nouveau</Text>
          </TouchableOpacity>
        ),
      }} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={80}
      >
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={styles.chat}
          keyboardShouldPersistTaps="handled"
        >
          {conv.messages.length === 0 && (
            <View style={styles.empty} testID="assistant-empty">
              <Text style={styles.emptyTitle}>Assistant STAIRPILOT</Text>
              <Text style={styles.emptyBody}>
                {"Décrivez votre projet en français : hauteur d'étage, reculement disponible, trémie… L'assistant appellera le moteur déterministe pour vous proposer le meilleur escalier."}
              </Text>
              <View style={styles.suggestions}>
                {[
                  "Hauteur 2.85m, trémie 2.60×1.00, recul 3.20m — que me proposes-tu ?",
                  "Différence entre Blondel et pente ?",
                  "Escalier droit H=2800 recul=4200, quel giron ?",
                ].map((s, i) => (
                  <TouchableOpacity
                    key={i}
                    style={styles.suggestion}
                    onPress={() => setInput(s)}
                    testID={`suggestion-${i}`}
                  >
                    <Text style={styles.suggestionText}>{s}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {conv.messages.map((m, i) => (
            <View
              key={i}
              style={[styles.bubbleRow, m.role === 'user' ? styles.rowRight : styles.rowLeft]}
              testID={`msg-${i}`}
            >
              <View
                style={[
                  styles.bubble,
                  m.role === 'user' ? styles.bubbleUser : styles.bubbleAsst,
                ]}
              >
                <Text style={m.role === 'user' ? styles.bubbleTextUser : styles.bubbleTextAsst}>
                  {m.content}
                </Text>
              </View>
            </View>
          ))}

          {loading && (
            <View style={styles.thinking} testID="assistant-thinking">
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={styles.thinkingText}>{"L'assistant réfléchit…"}</Text>
            </View>
          )}

          {conv.last_solutions.length > 0 && (
            <View style={styles.solutionsBlock} testID="assistant-solutions">
              <Text style={styles.solutionsTitle}>Dernières solutions proposées</Text>
              {conv.last_solutions.map((s, i) => (
                <TouchableOpacity
                  key={i}
                  style={styles.solutionCard}
                  onPress={() => handleOpenSolution(s)}
                  testID={`solution-card-${s.rank}`}
                >
                  <View style={styles.solutionHeader}>
                    <Text style={styles.solutionRank}>#{s.rank}</Text>
                    <Text style={styles.solutionType}>{humanType(s.type)}</Text>
                    <View style={styles.solutionScore}>
                      <Text style={styles.solutionScoreText}>{s.score_global}</Text>
                    </View>
                  </View>
                  <View style={styles.solutionMeta}>
                    <Text style={styles.solutionMetaText}>
                      {s.num_steps} marches · h={s.riser_height_mm}mm · g={s.tread_depth_mm}mm · {s.slope_deg}°
                    </Text>
                  </View>
                  <Text style={styles.solutionCta}>Voir en détail →</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          {errorBanner && (
            <View style={styles.errorBanner} testID="assistant-error">
              <Text style={styles.errorText}>{errorBanner}</Text>
            </View>
          )}
        </ScrollView>

        <View style={styles.inputBar}>
          <TextInput
            testID="assistant-input"
            style={styles.textInput}
            placeholder="Décrivez votre projet…"
            placeholderTextColor={colors.textDim}
            value={input}
            onChangeText={setInput}
            multiline
            maxLength={800}
            editable={!loading}
          />
          <TouchableOpacity
            testID="assistant-send"
            onPress={handleSend}
            disabled={loading || !input.trim()}
            style={[
              styles.sendBtn,
              (loading || !input.trim()) && styles.sendBtnDisabled,
            ]}
            activeOpacity={0.85}
          >
            <Text style={styles.sendBtnText}>Envoyer</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function humanType(t: string): string {
  const M: Record<string, string> = {
    'straight': 'Escalier droit',
    'quarter_turn_bottom': 'Quart tournant bas',
    'quarter_turn_top': 'Quart tournant haut',
    'half_turn': 'Demi-tournant',
    'helicoidal': 'Hélicoïdal',
  };
  return M[t] ?? t;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  headerAction: { color: colors.primary, fontWeight: '600', paddingHorizontal: spacing.m },
  chat: { padding: spacing.l, paddingBottom: spacing.xxl, flexGrow: 1 },
  empty: { paddingTop: spacing.xl, alignItems: 'flex-start' },
  emptyTitle: { ...typography.h2, color: colors.text, marginBottom: spacing.s },
  emptyBody: { ...typography.body, color: colors.textMuted, marginBottom: spacing.l },
  suggestions: { alignSelf: 'stretch' },
  suggestion: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.m,
    padding: spacing.m, marginBottom: spacing.s, backgroundColor: colors.bgSubtle,
  },
  suggestionText: { ...typography.small, color: colors.text },
  bubbleRow: { flexDirection: 'row', marginBottom: spacing.s },
  rowLeft: { justifyContent: 'flex-start' },
  rowRight: { justifyContent: 'flex-end' },
  bubble: {
    maxWidth: '84%',
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.s + 2,
    borderRadius: radius.l,
  },
  bubbleUser: {
    backgroundColor: colors.primary,
    borderBottomRightRadius: radius.s,
  },
  bubbleAsst: {
    backgroundColor: colors.bgSubtle,
    borderBottomLeftRadius: radius.s,
    borderWidth: 1,
    borderColor: colors.border,
  },
  bubbleTextUser: { color: '#FFFFFF', ...typography.body, lineHeight: 21 },
  bubbleTextAsst: { color: colors.text, ...typography.body, lineHeight: 21 },
  thinking: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.s, gap: spacing.s as any },
  thinkingText: { ...typography.small, color: colors.textMuted, marginLeft: spacing.s },
  solutionsBlock: { marginTop: spacing.l },
  solutionsTitle: { ...typography.caption, color: colors.textMuted, textTransform: 'uppercase', marginBottom: spacing.s },
  solutionCard: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.m,
    padding: spacing.m, marginBottom: spacing.s, backgroundColor: colors.bg,
  },
  solutionHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  solutionRank: { ...typography.mono, color: colors.primary, marginRight: spacing.s },
  solutionType: { ...typography.bodyStrong, color: colors.text, flex: 1 },
  solutionScore: {
    backgroundColor: colors.primaryBg, paddingHorizontal: spacing.s, paddingVertical: 2,
    borderRadius: radius.s,
  },
  solutionScoreText: { color: colors.primary, ...typography.caption, fontWeight: '700' },
  solutionMeta: {},
  solutionMetaText: { ...typography.monoSmall, color: colors.textMuted },
  solutionCta: { color: colors.primary, ...typography.small, marginTop: spacing.xs, fontWeight: '600' },
  errorBanner: {
    marginTop: spacing.m, padding: spacing.m,
    backgroundColor: colors.dangerBg, borderRadius: radius.m,
    borderWidth: 1, borderColor: colors.danger,
  },
  errorText: { ...typography.small, color: colors.danger },
  inputBar: {
    flexDirection: 'row', alignItems: 'flex-end',
    padding: spacing.m, gap: spacing.s as any,
    borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.bg,
  },
  textInput: {
    flex: 1, minHeight: 44, maxHeight: 120,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.m,
    paddingHorizontal: spacing.m, paddingVertical: spacing.s,
    ...typography.body, color: colors.text,
  },
  sendBtn: {
    backgroundColor: colors.primary, borderRadius: radius.m,
    paddingHorizontal: spacing.l, paddingVertical: spacing.m,
    justifyContent: 'center',
  },
  sendBtnDisabled: { opacity: 0.4 },
  sendBtnText: { color: '#FFFFFF', ...typography.bodyStrong },
});
