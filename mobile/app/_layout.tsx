import { Stack } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { colors } from '../src/theme';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.bg },
          headerTitleStyle: { color: colors.text, fontWeight: '700' },
          headerTintColor: colors.text,
          headerShadowVisible: false,
          contentStyle: { backgroundColor: colors.bg },
        }}
      >
        <Stack.Screen name="index" options={{ title: 'STAIRPILOT' }} />
        <Stack.Screen name="type-select" options={{ title: 'Type d\'escalier' }} />
        <Stack.Screen name="form" options={{ title: 'Dimensions' }} />
        <Stack.Screen name="result" options={{ title: 'Résultat' }} />
        <Stack.Screen name="optimize" options={{ title: 'Optimisation auto' }} />
        <Stack.Screen name="compare" options={{ title: 'Comparateur' }} />
        <Stack.Screen name="concrete" options={{ title: 'Analyse béton armé' }} />
        <Stack.Screen name="assistant" options={{ title: 'Assistant IA' }} />
        <Stack.Screen name="view-3d" options={{ title: 'Vue 3D' }} />
      </Stack>
    </SafeAreaProvider>
  );
}
