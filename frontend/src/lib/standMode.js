/**
 * Modo stand (Web Summit) — demo offline guiada para o stand.
 *
 * - `startStand()` activa a demo offline Pro e marca o browser como « stand ».
 * - `resetStand()` apaga tudo o que o visitante anterior fez (conversas, mutações, rascunhos)
 *   e volta a abrir a demo limpa na página /stand.
 * Contas reais nunca são tocadas: só a store local da demo e as chaves deste browser.
 */
import { enableDemoMode, resetDemoStore } from "@/lib/demoInterceptor";

export const STAND_FLAG = "cp_stand_mode";
export const STAND_IDLE_MS = 3 * 60 * 1000;

// Chaves que sobrevivem ao reinício entre visitantes (consentimento, idioma, onboarding, flags da demo).
const KEEP = ["cp_cookie_consent", "construpilot_onboarding_done", STAND_FLAG, "is_demo", "demo_kind",
              "construpilot_session", "construpilot_lang"];

export function isStandMode() {
  try { return localStorage.getItem(STAND_FLAG) === "1"; } catch { return false; }
}

export function startStand() {
  enableDemoMode({ kind: "pro" });
  try {
    localStorage.setItem(STAND_FLAG, "1");
    localStorage.setItem("construpilot_session", "1");
    localStorage.setItem("construpilot_onboarding_done", "1");
  } catch { /* noop */ }
}

export function stopStand() {
  try { localStorage.removeItem(STAND_FLAG); } catch { /* noop */ }
}

export async function resetStand() {
  await resetDemoStore();
  try {
    Object.keys(localStorage).filter((k) => !KEEP.includes(k)).forEach((k) => localStorage.removeItem(k));
    const seen = sessionStorage.getItem("cp_websummit_2026_seen");
    sessionStorage.clear();
    if (seen) sessionStorage.setItem("cp_websummit_2026_seen", seen);
  } catch { /* noop */ }
  startStand();
  window.location.assign("/stand");
}
