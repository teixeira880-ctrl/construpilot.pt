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
      </Stack>
    </SafeAreaProvider>
  );
}
