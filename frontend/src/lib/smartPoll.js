// Sondagem económica dos indicadores globais (agentes, estudos, notificações).
// Antes: pedidos a cada 2,5 s / 4 s em todas as páginas, mesmo com o separador escondido e sem nada a correr.
// Agora, com o mesmo comportamento visível:
//  - separador escondido → nenhuma sondagem; ao voltar ao separador → sondagem imediata;
//  - o intervalo é decidido a cada volta (rápido enquanto há um trabalho ativo, lento quando não há);
//  - qualquer POST para /agents/* ou /pc/* (lançar, cancelar…) provoca uma sondagem imediata
//    através do evento "cp:jobs-changed" (emitido em lib/api.js).

export const JOBS_CHANGED_EVENT = "cp:jobs-changed";

export function notifyJobsChanged() {
  try { window.dispatchEvent(new Event(JOBS_CHANGED_EVENT)); } catch { /* SSR / testes */ }
}

/**
 * @param {() => Promise<any>} fn  função de sondagem (os erros são ignorados aqui; fn trata os seus)
 * @param {() => number} nextDelayMs  intervalo até à próxima volta, avaliado depois de cada sondagem
 * @returns {() => void} função que pára a sondagem
 */
export function startSmartPoll(fn, nextDelayMs) {
  let stopped = false;
  let timer = null;
  let running = false;

  const hidden = () => typeof document !== "undefined" && document.visibilityState === "hidden";

  const schedule = () => {
    clearTimeout(timer);
    if (stopped || hidden()) return;
    timer = setTimeout(tick, Math.max(500, Number(nextDelayMs()) || 10000));
  };

  const tick = async () => {
    if (stopped || running) return;
    if (hidden()) return;          // retoma em visibilitychange
    running = true;
    try { await fn(); } catch { /* fn é responsável pelos seus erros */ }
    finally { running = false; schedule(); }
  };

  const onVisible = () => { if (!hidden()) { clearTimeout(timer); tick(); } };
  const onJobsChanged = () => { clearTimeout(timer); tick(); };

  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener(JOBS_CHANGED_EVENT, onJobsChanged);
  tick();

  return () => {
    stopped = true;
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener(JOBS_CHANGED_EVENT, onJobsChanged);
  };
}
