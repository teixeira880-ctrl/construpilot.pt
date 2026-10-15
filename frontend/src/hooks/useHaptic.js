/**
 * Hook para feedback táctil via Vibration API. Fallback silencioso em
 * browsers sem suporte (iOS Safari, desktop).
 */
export function useHaptic() {
  const vibrate = (pattern) => {
    try {
      if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
        navigator.vibrate(pattern);
      }
    } catch {
      /* ignorar */
    }
  };
  return {
    tap: () => vibrate(10),
    success: () => vibrate([15, 40, 15]),
    error: () => vibrate([80, 40, 80]),
    warn: () => vibrate([30, 60, 30]),
  };
}
